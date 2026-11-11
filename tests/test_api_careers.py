"""Career targets use the same durable queue, capabilities and committed history."""
import copy
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from app.engines.chat import career_fingerprints
from app.main import create_app
from app.services.career_catalog import CareerCatalog, PROFILES
from app.services.errors import StorageIntegrityError

pytestmark = pytest.mark.parametrize('target_domain', ['cwa'], indirect=True)


def test_public_catalog_and_target_contract(api_backend, queued_session):
    catalog = api_backend.client.get('/api/v1/career-profiles')
    assert catalog.status_code == 200 and catalog.headers['cache-control'] == 'no-store'
    assert len(catalog.json()['profiles']) == 8
    value = api_backend.client.get('/api/v1/advisor/sessions/' + queued_session['session_id'], headers=queued_session['headers']).json()
    assert value['target']['type'] == 'cwa'
    assert value['target']['career_profile']['profile_id'] == 'data-analyst'
    assert value['comparison'] is None and value['turn_count'] == 0
    assert not {'clo_set', 'fingerprints', 'job_description'}.intersection(value)
    api_backend.review_client.responses.parse.assert_not_called()


@pytest.mark.parametrize('target', [{}, {'job_description': 'SQL', 'career_profile_id': 'data-analyst'},
                                     {'career_profile_id': ''}, {'career_profile_id': 3}])
def test_exactly_one_target_and_no_silent_default(api_backend, stored_clo_set, target):
    headers = {'Authorization': 'Bearer ' + stored_clo_set['access_token'], 'Idempotency-Key': 'invalid'}
    response = api_backend.client.post('/api/v1/advisor/sessions', headers=headers,
        json={'selection_id': stored_clo_set['selection_id'], **target})
    assert response.status_code == 422
    with api_backend.database.transaction() as c: assert c.execute('SELECT count(*) FROM jobs').fetchone()[0] == 0


def test_career_idempotency_isolates_target_and_owner(api_backend, stored_clo_set, queued_session):
    body = {'selection_id': stored_clo_set['selection_id'], 'career_profile_id': 'data-analyst'}
    post = lambda b, h=queued_session['headers']: api_backend.client.post('/api/v1/advisor/sessions', headers=h, json=b)
    assert post(body).json()['session_id'] == queued_session['session_id']
    for target in [{'career_profile_id': 'data-scientist'}, {'job_description': 'SQL internship'}]:
        response = post({'selection_id': stored_clo_set['selection_id'], **target})
        assert response.status_code == 409 and response.json()['error']['code'] == 'idempotency_conflict'
    wrong = {**queued_session['headers'], 'Authorization': 'Bearer wrong-owner'}
    assert post(body, wrong).status_code == 403
    assert api_backend.client.get('/api/v1/advisor/sessions/' + queued_session['session_id'], headers=wrong).status_code == 403
    unknown = post({**body, 'career_profile_id': 'not-a-career'}, {**queued_session['headers'], 'Idempotency-Key': 'new-key'})
    assert unknown.status_code == 404
    api_backend.review_client.responses.parse.assert_not_called()


def test_snapshot_pins_exact_career_source_and_replay_survives_catalog_changes(api_backend, stored_clo_set, tmp_path):
    original = CareerCatalog()
    source_dir = tmp_path / 'careers'
    shutil.copytree(original.directory, source_dir)
    api_backend.backend.persistent.careers = CareerCatalog(source_dir)
    headers = {'Authorization': 'Bearer ' + stored_clo_set['access_token'], 'Idempotency-Key': 'pinned'}
    body = {'selection_id': stored_clo_set['selection_id'], 'career_profile_id': 'data-analyst'}
    response = api_backend.client.post('/api/v1/advisor/sessions', headers=headers, json=body)
    assert response.status_code == 202
    first = response.json()
    source_file = source_dir / PROFILES['data-analyst']
    source_file.write_bytes(source_file.read_bytes() + '\nNội dung mới\n'.encode())
    same = api_backend.client.post('/api/v1/advisor/sessions', headers=headers, json=body)
    assert same.json() == first
    stored = api_backend.backend.sessions.get(first['session_id'], stored_clo_set['access_token'])['snapshot']
    assert stored['career_profile'] == original.get('data-analyst')
    second = api_backend.client.post('/api/v1/advisor/sessions', headers={**headers, 'Idempotency-Key': 'new'}, json=body)
    newer = api_backend.backend.sessions.get(second.json()['session_id'], stored_clo_set['access_token'])['snapshot']
    assert newer['career_profile']['fingerprint'] != stored['career_profile']['fingerprint']
    source_file.unlink()
    assert api_backend.client.post('/api/v1/advisor/sessions', headers=headers, json=body).json() == first
    assert api_backend.advisor.validate_snapshot(stored) == stored


def test_career_chat_replay_two_turns_and_new_api_instance(api_backend, ready_session):
    path = '/api/v1/advisor/sessions/' + ready_session['session_id']
    view = api_backend.client.get(path, headers=ready_session['headers']).json()
    assert view['comparison']['comparison_type'] == 'career_comparison'
    assert set(view['comparison']) == {'comparison_type', 'overview', 'related_content', 'gaps', 'conclusion', 'radar'}
    assert view['comparison']['related_content'][0]['evidence'] == [{'course_code': 'TEST101'}]
    headers = {**ready_session['headers'], 'Idempotency-Key': 'chat-1'}
    first = api_backend.client.post(path + '/messages', headers=headers, json={'message': 'Công việc này liên quan thế nào?'})
    assert first.status_code == 200
    app = create_app(api_backend.settings, advisor_service=api_backend.advisor, course_service=api_backend.catalog, database=api_backend.database)
    with TestClient(app) as fresh:
        assert fresh.post(path + '/messages', headers=headers, json={'message': 'Công việc này liên quan thế nào?'}).json() == first.json()
        assert fresh.post(path + '/messages', headers={**headers, 'Idempotency-Key': 'chat-2'}, json={'message': 'Còn khoảng trống?'}).status_code == 200
        history = fresh.get(path + '/messages', headers=headers).json()['turns']
        assert [turn['sequence'] for turn in history] == [1, 2]
        assert history[0]['message_id'] == first.json()['message_id']
        assert fresh.get(path, headers=headers).json()['turn_count'] == 2
    assert api_backend.review_client.responses.parse.call_count == 1
    assert api_backend.chat_client.responses.parse.call_count == 2
    assert '"clo"' not in json.dumps(view) and '"clos"' not in json.dumps(history)


@pytest.mark.parametrize('mutation', ['target', 'kind'])
def test_commit_cannot_change_target_even_with_recomputed_fingerprints(api_backend, queued_session, mutation):
    lease = api_backend.backend.jobs.claim_next()
    pending = api_backend.backend.sessions.load_owned(lease)
    updated, _ = api_backend.advisor.review_snapshot(pending)
    if mutation == 'target':
        updated['career_profile'] = CareerCatalog().get('data-scientist')
        for axis, definition in zip(updated['comparison']['radar']['axes'], updated['career_profile']['target']['axes'], strict=True):
            axis.update(definition)
        updated['fingerprints'] = career_fingerprints(updated['clo_set'], updated['career_profile'], updated['comparison'])
    else:
        updated = api_backend.advisor.create_snapshot(updated['clo_set'], 'SQL')
        updated['session_id'] = pending['session_id']
    with pytest.raises(StorageIntegrityError): api_backend.backend.jobs.commit_review(lease, updated)
    assert api_backend.backend.sessions.get(lease.session_id, queued_session['access_token'])['revision'] == 0


def test_tampered_persisted_target_fails_before_inference(api_backend, queued_session):
    with api_backend.database.transaction(write=True) as c:
        row = c.execute('SELECT snapshot_json FROM sessions').fetchone()
        snapshot = json.loads(row[0])
        snapshot['career_profile']['content'] += '\nchanged'
        c.execute('UPDATE sessions SET snapshot_json=?', (json.dumps(snapshot),))
    response = api_backend.client.get('/api/v1/advisor/sessions/' + queued_session['session_id'], headers=queued_session['headers'])
    assert response.status_code == 500 and response.json()['error']['code'] == 'storage_integrity_error'
    api_backend.review_client.responses.parse.assert_not_called()
