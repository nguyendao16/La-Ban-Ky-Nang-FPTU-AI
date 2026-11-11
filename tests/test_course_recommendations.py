"""Offline Coursera provenance, privacy, durable jobs, migration and saved Chat context."""
import copy
import json
import multiprocessing
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.engines.errors import ComparisonError
from app.engines.recommendations import (
    RECOMMENDATION_INSTRUCTIONS, generate_recommendations, recommendation_context,
    validate_recommendations, coursera_url,
)
from app.engines.chat import CLOChatSession
from app.jobs.review_worker import ReviewWorker
from app.json_utils import digest, json_text
from app.llm import LLMSettings
from app.services import AdvisorService
from app.services.errors import OwnershipLostError, StorageIntegrityError, IncompatibleDatabaseError
from app.storage.database import Database
from app.storage.migrations import APPLICATION_ID, JOB_TABLE_SQL
from examples.services_integration import mock_recommendation_response

pytestmark = pytest.mark.usefixtures('service_offline')


@pytest.fixture
def rec_ready(api_backend, queued_session, sdk_client):
    # Give the JD an actual saved content gap, without changing any real artifact.
    raw = api_backend.review_client.responses.parse.return_value.output_parsed
    if api_backend.domain == 'jd':
        raw['requirement_reviews'][0].update(coverage='related',
            comment='Nội dung mới đề cập SQL cơ bản; chưa thể hiện tối ưu truy vấn và vận hành dữ liệu.')
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor)
    worker.run_once()
    worker.close()
    snapshot = api_backend.backend.sessions.get(queued_session['session_id'], queued_session['access_token'])['snapshot']
    response = mock_recommendation_response(recommendation_context(snapshot))
    client = sdk_client(response.output_parsed)
    client.responses.parse.return_value = response
    api_backend.advisor._recommendation_client = client
    return SimpleNamespace(**queued_session, snapshot=snapshot, client=client,
        path='/api/v1/advisor/sessions/' + queued_session['session_id'] + '/recommendations')


def enqueue(api, rec, key='rec-key'):
    response = api.client.post(rec.path, headers={**rec.headers, 'Idempotency-Key': key}, json={})
    assert response.status_code == 202, response.text
    return response.json()


def run_worker(api):
    worker = ReviewWorker(api.backend.jobs, api.advisor)
    try: return worker.run_once()
    finally: worker.close()


@pytest.mark.parametrize('target_domain', ['jd', 'cwa'], indirect=True)
def test_manual_one_set_replay_refresh_and_immutable_comparison(api_backend, rec_ready):
    rec = rec_ready
    before = copy.deepcopy(rec.snapshot)
    initial = api_backend.client.get(rec.path, headers=rec.headers)
    assert initial.status_code == 200 and initial.json()['status'] == 'not_requested'
    rec.client.responses.parse.assert_not_called()
    first = enqueue(api_backend, rec)
    assert enqueue(api_backend, rec) == enqueue(api_backend, rec, 'second-tab-key') == first
    assert rec.client.responses.parse.call_count == 0
    assert run_worker(api_backend) == first['job_id']
    assert run_worker(api_backend) is None
    view = api_backend.client.get(rec.path, headers=rec.headers).json()
    assert view['status'] == 'ready' and len(view['result']['courses']) == 1
    assert view['result']['courses'][0]['provider'] is None
    assert view['result']['courses'][0]['price'] is None
    assert view['gaps'][0]['gap_id'] == 'gap-1'
    assert view['job']['attempt_count'] == 1
    assert enqueue(api_backend, rec) == first
    assert api_backend.backend.sessions.get(rec.session_id, rec.access_token)['snapshot'] == before
    assert api_backend.backend.sessions.get(rec.session_id, rec.access_token)['revision'] == 1
    assert api_backend.client.get('/api/v1/advisor/sessions/' + rec.session_id, headers=rec.headers).json()['status'] == 'ready'
    assert api_backend.client.get(rec.path, headers=rec.headers).json() == view
    request = rec.client.responses.parse.call_args.kwargs
    preflight = rec.client.responses.input_tokens.count.call_args.kwargs
    assert request['instructions'] == preflight['instructions'] == RECOMMENDATION_INSTRUCTIONS
    assert request['tools'] == preflight['tools'] == [{'type': 'web_search', 'filters': {'allowed_domains': ['coursera.org']}}]
    assert request['tool_choice'] == preflight['tool_choice'] == 'required'
    assert request['max_tool_calls'] == 5 and request['include'] == ['web_search_call.action.sources']
    assert request['store'] is False and request['truncation'] == 'disabled'
    assert request['model'] == api_backend.advisor._review_settings.model
    assert rec.client.responses.parse.call_count == rec.client.responses.input_tokens.count.call_count == 1
    rec.client.close.assert_not_called()
    with api_backend.database.transaction() as connection:
        assert connection.execute("SELECT count(*) FROM jobs WHERE job_type='course_recommendations'").fetchone()[0] == 1


@pytest.mark.parametrize('target_domain', ['jd', 'cwa'], indirect=True)
def test_capability_and_pending_guards_without_any_generation(api_backend, queued_session):
    path = '/api/v1/advisor/sessions/' + queued_session['session_id'] + '/recommendations'
    assert api_backend.client.get(path).status_code == 401
    assert api_backend.client.get(path, headers={'Authorization': 'Bearer wrong'}).status_code == 403
    assert api_backend.client.post(path, headers=queued_session['headers'], json={}).status_code == 409
    assert api_backend.client.get('/api/v1/advisor/sessions/missing/recommendations', headers=queued_session['headers']).status_code == 404
    api_backend.review_client.responses.parse.assert_not_called()


def test_search_context_excludes_private_clos_raw_jd_grades_metadata_and_scores(service_clo_set, service_review, sdk_client):
    source = copy.deepcopy(service_clo_set)
    source['courses'][0]['clos'][0]['description'] = 'Private source content with long confidential descriptions that must never enter the search request'
    jd = 'SECRET EMPLOYER STRATEGY: raw-job-description-7531'
    raw = copy.deepcopy(service_review)
    raw['requirement_reviews'][0].update(coverage='related', comment='Chưa thể hiện tối ưu truy vấn SQL.')
    with CLOChatSession.from_data(source, jd, raw) as session: snapshot = session.export_snapshot()
    context = recommendation_context(snapshot)
    assert set(context) == {'target', 'gaps'}
    client = sdk_client({})
    client.responses.parse.return_value = mock_recommendation_response(context)
    advisor = AdvisorService(review_settings=LLMSettings(api_key='offline', model='gpt-5.4', max_output_tokens=32768, request_timeout=360), recommendation_client=client)
    result = advisor.recommend_snapshot(snapshot)
    request = client.responses.parse.call_args.kwargs
    data = json.dumps(request['input'], ensure_ascii=False)
    assert jd not in data and source['courses'][0]['clos'][0]['description'] not in data
    for key in ['"clo"', '"clos"', 'metadata', 'grade', 'overall_score', 'api_key', 'fingerprint']:
        assert key not in data
    assert request['model'] == 'gpt-5.4' and request['timeout'] == 360 and request['max_output_tokens'] == 32768
    assert request['reasoning'] == {'effort': 'high'}
    assert result.result.courses


@pytest.mark.parametrize('bad_url', [
    'http://www.coursera.org/learn/data', 'https://coursera.org.evil.test/learn/data',
    'https://www.coursera.org@evil.test/learn/data', 'https://user@www.coursera.org/learn/data',
    'https://www.coursera.org:444/learn/data', 'javascript:alert(1)',
    'https://www.coursera.org/search?query=data', 'https://www.coursera.org/degrees/data',
    'https://www.coursera.org/projects/data', 'https://www.coursera.org/partners/google',
])
def test_only_public_coursera_course_program_urls(bad_url):
    with pytest.raises(ComparisonError): coursera_url(bad_url)


def test_canonicalization_preserves_course_identity_and_prevents_tracking_duplicates():
    assert coursera_url('https://coursera.org/learn/data/?utm_source=x#about') == 'https://www.coursera.org/learn/data'


@pytest.mark.parametrize('failure', ['url', 'title', 'citation', 'gap', 'duplicate_gap', 'duplicate_course', 'six_courses', 'wrong_type', 'six_calls', 'unfinished_search', 'outside_open', 'leak', 'incomplete', 'missing_output'])
@pytest.mark.parametrize('target_domain', ['jd', 'cwa'], indirect=True)
def test_invalid_or_incomplete_search_rolls_back_once(api_backend, rec_ready, failure):
    rec = rec_ready
    response = rec.client.responses.parse.return_value
    course = response.output_parsed['courses'][0]
    if failure == 'url': course['url'] = 'https://www.coursera.org/learn/invented-course'
    elif failure == 'title': course['title'] = 'Invented unrelated title'
    elif failure == 'citation': response.output[1].content[0].annotations = []
    elif failure == 'gap': course['gap_ids'] = ['gap-999']
    elif failure == 'duplicate_gap': course['gap_ids'] *= 2
    elif failure == 'duplicate_course': response.output_parsed['courses'] *= 2
    elif failure == 'six_courses': response.output_parsed['courses'] *= 6
    elif failure == 'wrong_type': course['program_type'] = 'specialization'
    elif failure == 'six_calls': response.output = [response.output[0]]*6 + [response.output[1]]
    elif failure == 'unfinished_search': response.output[0].status = 'failed'
    elif failure == 'outside_open': response.output[0].action = SimpleNamespace(type='open_page', url='https://evil.test/collect')
    elif failure == 'leak': course['reason'] = 'Trần điểm nội bộ là 1/5.'
    elif failure == 'incomplete': response.status = 'incomplete'
    else: response.output_parsed = None
    created = enqueue(api_backend, rec)
    run_worker(api_backend)
    assert run_worker(api_backend) is None
    view = api_backend.client.get(rec.path, headers=rec.headers).json()
    assert view['status'] == 'failed' and view['result'] is None
    assert view['job']['attempt_count'] == 1
    assert api_backend.backend.sessions.get(rec.session_id, rec.access_token)['snapshot'] == rec.snapshot
    assert enqueue(api_backend, rec) == created
    assert enqueue(api_backend, rec, 'new-key-cannot-regenerate') == created
    assert rec.client.responses.parse.call_count == 1
    # A failed suggestion operation must not prevent ordinary Chat.
    chat = api_backend.client.post('/api/v1/advisor/sessions/' + rec.session_id + '/messages',
        headers={**rec.headers, 'Idempotency-Key': 'chat-after-rec-failure'}, json={'message': 'SQL?'})
    assert chat.status_code == 200


@pytest.mark.parametrize('target_domain', ['jd', 'cwa'], indirect=True)
def test_saved_courses_are_only_chat_resource_context_and_never_rescore(api_backend, rec_ready):
    rec = rec_ready
    enqueue(api_backend, rec)
    run_worker(api_backend)
    view = api_backend.client.get(rec.path, headers=rec.headers).json()
    course = view['result']['courses'][0]
    api_backend.chat_client.responses.parse.return_value.output_parsed = {'reply': f"Khóa gợi ý: {course['url']}. Thông tin từ kết quả tìm kiếm cần được xem thêm.", 'evidence': []}
    path = '/api/v1/advisor/sessions/' + rec.session_id + '/messages'
    headers = {**rec.headers, 'Idempotency-Key': 'explain-saved-course'}
    response = api_backend.client.post(path, headers=headers, json={'message': 'Khóa nào liên quan?'})
    assert response.status_code == 200
    assert api_backend.client.post(path, headers=headers, json={'message': 'Khóa nào liên quan?'}).json() == response.json()
    request = api_backend.chat_client.responses.parse.call_args.kwargs
    assert json.loads(request['input'][2]['content'])['saved_recommendations'] == {**view['result'], 'gaps': view['gaps']}
    assert 'tools' not in request and 'web_search' not in json.dumps(request.get('tools'))
    assert api_backend.chat_client.responses.parse.call_count == 1
    snapshot = api_backend.backend.sessions.get(rec.session_id, rec.access_token)['snapshot']
    assert snapshot['comparison'] == rec.snapshot['comparison'] and snapshot['fingerprints'] == rec.snapshot['fingerprints']
    api_backend.chat_client.responses.parse.return_value.output_parsed = {'reply': 'Thử https://www.coursera.org/learn/unapproved-course', 'evidence': []}
    denied = api_backend.client.post(path, headers={**headers, 'Idempotency-Key': 'unapproved-course'}, json={'message': 'Khóa khác?'})
    assert denied.status_code == 502
    assert len(api_backend.backend.sessions.history(rec.session_id, rec.access_token)) == 1


def test_empty_gap_context_needs_no_search_client_or_invented_courses(service_clo_set, service_review, sdk_client):
    with CLOChatSession.from_data(service_clo_set, 'SQL', service_review) as session: context = recommendation_context(session.export_snapshot())
    client = sdk_client({})
    result = generate_recommendations(context, LLMSettings(api_key='offline'), client=client)
    assert result.result.courses == []
    client.responses.parse.assert_not_called()
    client.responses.input_tokens.count.assert_not_called()


@pytest.mark.parametrize('invalid', [False, True])
def test_recommendation_owned_client_closes_after_success_or_validation_failure(api_backend, rec_ready, monkeypatch, invalid):
    rec = rec_ready
    api_backend.advisor._recommendation_client = None
    constructor = Mock(return_value=rec.client)
    monkeypatch.setattr('app.llm.openai.OpenAI', constructor)
    if invalid:
        rec.client.responses.parse.return_value.output_parsed['courses'][0]['title'] = 'Invented course'
        with pytest.raises(ComparisonError): api_backend.advisor.recommend_snapshot(rec.snapshot)
    else:
        assert api_backend.advisor.recommend_snapshot(rec.snapshot).result.courses
    assert constructor.call_args.kwargs['max_retries'] == 0
    rec.client.close.assert_called_once()
    rec.client.responses.parse.assert_called_once()


@pytest.mark.parametrize('target_domain', ['jd', 'cwa'], indirect=True)
def test_recommendation_interruption_releases_chat_without_publishing_partial_result(api_backend, rec_ready):
    rec = rec_ready
    enqueue(api_backend, rec)
    def stop(**request):
        blocked = api_backend.client.post('/api/v1/advisor/sessions/' + rec.session_id + '/messages',
            headers={**rec.headers, 'Idempotency-Key': 'chat-wait-for-search'}, json={'message': 'SQL?'})
        assert blocked.status_code == 409
        raise KeyboardInterrupt()
    rec.client.responses.parse.side_effect = stop
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor)
    try:
        with pytest.raises(KeyboardInterrupt): worker.run_once()
    finally:
        worker.close()
    view = api_backend.client.get(rec.path, headers=rec.headers).json()
    assert view['status'] == 'interrupted' and view['result'] is None
    assert api_backend.backend.sessions.get(rec.session_id, rec.access_token)['snapshot'] == rec.snapshot
    chat = api_backend.client.post('/api/v1/advisor/sessions/' + rec.session_id + '/messages',
        headers={**rec.headers, 'Idempotency-Key': 'chat-wait-for-search'}, json={'message': 'SQL?'})
    assert chat.status_code == 200
    assert run_worker(api_backend) is None and rec.client.responses.parse.call_count == 1


@pytest.mark.parametrize('target_domain', ['jd', 'cwa'], indirect=True)
def test_heartbeat_recovery_and_fencing_preserve_ready_comparison(api_backend, rec_ready):
    rec = rec_ready
    created = enqueue(api_backend, rec)
    lease = api_backend.backend.jobs.claim_next()
    assert lease.operation_id == created['job_id']
    api_backend.clock.advance(20)
    api_backend.backend.sessions.renew(lease)
    api_backend.clock.advance(20)
    assert api_backend.backend.sessions.recover_expired() == 0
    api_backend.backend.sessions.mark_dispatched(lease)
    api_backend.clock.advance(31)
    assert api_backend.backend.sessions.recover_expired() == 1
    generated = api_backend.advisor.recommend_snapshot(rec.snapshot)
    with pytest.raises(OwnershipLostError): api_backend.backend.jobs.commit_recommendations(lease, generated)
    assert api_backend.client.get(rec.path, headers=rec.headers).json()['status'] == 'interrupted'
    assert api_backend.backend.sessions.get(rec.session_id, rec.access_token)['snapshot'] == rec.snapshot
    assert enqueue(api_backend, rec) == created
    assert run_worker(api_backend) is None


@pytest.mark.parametrize('target_domain', ['jd', 'cwa'], indirect=True)
def test_save_failure_does_not_publish_and_never_automatically_regenerates(api_backend, rec_ready, monkeypatch):
    rec = rec_ready
    enqueue(api_backend, rec)
    def fail(*args): raise sqlite3.OperationalError('offline save failure')
    monkeypatch.setattr(api_backend.backend.jobs, 'commit_recommendations', fail)
    run_worker(api_backend)
    assert api_backend.client.get(rec.path, headers=rec.headers).json()['status'] == 'interrupted'
    assert api_backend.backend.sessions.get(rec.session_id, rec.access_token)['snapshot'] == rec.snapshot
    assert run_worker(api_backend) is None and rec.client.responses.parse.call_count == 1


@pytest.mark.parametrize('target_domain', ['jd', 'cwa'], indirect=True)
def test_result_tampering_is_rejected_on_get_and_replay_does_not_regenerate(api_backend, rec_ready):
    rec = rec_ready
    created = enqueue(api_backend, rec)
    run_worker(api_backend)
    with api_backend.database.transaction(write=True) as connection:
        row = connection.execute('SELECT result_json FROM jobs WHERE job_id=?', (created['job_id'],)).fetchone()
        value = json.loads(row[0]); value['generation']['result']['summary'] += ' tampered'
        connection.execute('UPDATE jobs SET result_json=? WHERE job_id=?', (json_text(value), created['job_id']))
    assert api_backend.client.get(rec.path, headers=rec.headers).status_code == 500
    assert enqueue(api_backend, rec) == created
    assert run_worker(api_backend) is None and rec.client.responses.parse.call_count == 1


def recommendation_process_worker(path, raw, barrier, events):
    from app.storage.job_repository import JobRepository
    from app.storage.session_repository import SessionRepository
    def engine(*args, **kwargs): events.put('generation'); return raw
    database = Database(path, lease_seconds=60); database.initialize()
    advisor = AdvisorService(recommendation_engine=engine, review_settings=LLMSettings(api_key='offline'))
    jobs = JobRepository(database, SessionRepository(database, advisor.validate_snapshot))
    worker = ReviewWorker(jobs, advisor)
    barrier.wait(timeout=20)
    events.put(bool(worker.run_once()))
    worker.close()


@pytest.mark.parametrize('target_domain', ['cwa'], indirect=True)
def test_two_worker_processes_claim_one_recommendation_job(api_backend, rec_ready):
    rec = rec_ready
    enqueue(api_backend, rec)
    response = rec.client.responses.parse.return_value
    raw = {'result': response.output_parsed, 'sources': [{'url': response.output_parsed['courses'][0]['url'], 'title': response.output_parsed['courses'][0]['title']}]}
    context = multiprocessing.get_context('spawn')
    barrier, events = context.Barrier(2), context.Queue()
    processes = [context.Process(target=recommendation_process_worker,
        args=(str(api_backend.database.path), raw, barrier, events)) for _ in range(2)]
    for process in processes: process.start()
    try:
        for process in processes: process.join(timeout=30); assert process.exitcode == 0
        received = [events.get(timeout=5) for _ in range(3)]
        assert received.count('generation') == 1 and received.count(True) == 1
        assert api_backend.client.get(rec.path, headers=rec.headers).json()['status'] == 'ready'
    finally:
        for process in processes:
            if process.is_alive(): process.terminate()
            process.join(timeout=5)
        events.close()


def test_v1_migration_preserves_all_existing_rows_and_pending_ownership(api_backend, rec_ready):
    # Downgrade a test-owned DB to the exact legacy job shape, then exercise startup.
    rec = rec_ready
    selection_id = api_backend.backend.sessions.get(rec.session_id, rec.access_token)['clo_set_id']
    queued = api_backend.client.post('/api/v1/advisor/sessions',
        headers={**rec.headers, 'Idempotency-Key': 'migration-pending-owner'},
        json={'selection_id': selection_id, 'job_description': 'Pending SQL comparison'}).json()
    lease = api_backend.backend.jobs.claim_next()
    assert lease.session_id == queued['session_id']
    api_backend.backend.sessions.mark_dispatched(lease)
    with api_backend.database.transaction(write=True) as connection:
        tables = ['clo_sets', 'sessions', 'requests', 'jobs', 'workers']
        before = {t: [dict(row) for row in connection.execute(f'SELECT * FROM {t}')] for t in tables}
        columns = [r[1] for r in connection.execute('PRAGMA table_info(jobs)') if r[1] not in {'result_json', 'result_fingerprint'}]
        original_sql = JOB_TABLE_SQL.replace('CREATE TABLE jobs', 'CREATE TABLE legacy_jobs').replace(
            "CHECK(job_type IN ('initial_comparison','course_recommendations'))", "CHECK(job_type='initial_comparison')").replace(
            ", result_json TEXT, result_fingerprint TEXT", '').replace('UNIQUE(session_id, job_type)', 'UNIQUE(session_id)')
        connection.execute(original_sql)
        names = ','.join(columns)
        connection.execute(f'INSERT INTO legacy_jobs({names}) SELECT {names} FROM jobs')
        connection.execute('DROP TABLE jobs'); connection.execute('ALTER TABLE legacy_jobs RENAME TO jobs')
        connection.execute('CREATE INDEX queued_jobs ON jobs(status,created_at,job_id)')
        connection.execute('PRAGMA user_version=1')
    api_backend.database.initialize(); api_backend.database.initialize()
    with api_backend.database.transaction() as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0] == 2
        for table in tables:
            after = [dict(row) for row in connection.execute(f'SELECT * FROM {table}')]
            if table == 'jobs':
                assert [{k: v for k,v in r.items() if k not in {'result_json', 'result_fingerprint'}} for r in after] == [{k: v for k,v in r.items() if k not in {'result_json', 'result_fingerprint'}} for r in before[table]]
            else: assert after == before[table]
    enqueue(api_backend, rec)
    run_worker(api_backend)
    assert api_backend.client.get(rec.path, headers=rec.headers).json()['status'] == 'ready'
