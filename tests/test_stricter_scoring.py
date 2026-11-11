"""Offline score consistency, one-generation rollback and historical policy reads."""
import copy
import json
from unittest.mock import Mock

import pytest

from app.engines.career import validate_career_comparison, CWA_RADAR_SCORING_RULES
from app.engines.errors import ComparisonError
from app.engines.models import validate_comparison
from app.engines.prompts import RADAR_SCORING_RULES
from app.jobs.review_worker import ReviewWorker
from app.json_utils import digest
from app.llm import LLMSettings
from app.public_view import comparison as public_comparison
from app.services import AdvisorService, CareerCatalog

pytestmark = [
    pytest.mark.usefixtures('service_offline'),
    pytest.mark.parametrize('target_domain', ['jd', 'cwa'], indirect=True),
]


@pytest.fixture
def scoring_case(target_domain, service_review, career_review):
    return ((service_review, validate_comparison) if target_domain == 'jd'
            else (career_review, validate_career_comparison))


def set_scores(raw, scores, overall):
    raw['radar']['overall_score'] = overall
    for axis, score in zip(raw['radar']['axes'], scores, strict=True):
        axis.update(score=score, evidence=[{'course_code': 'TEST101', 'clo': 'CLO1'}] if score else [])


def create_pending(advisor, source, domain):
    return (advisor.create_snapshot(source, 'SQL required; Docker preferred') if domain == 'jd'
            else advisor.create_career_snapshot(source, CareerCatalog().get('data-analyst')))


@pytest.mark.parametrize('scores,overall', [
    ([0, 0, 0, 0, 0], 5),
    ([1, 0.5, 0, 0, 0], 3),
    ([2.9, 2, 1, 0, 0], 2.91),
])
def test_new_result_rejects_overall_above_best_axis_even_with_real_reference(
        scoring_case, service_clo_set, scores, overall):
    raw, validate = scoring_case
    set_scores(raw, scores, overall)
    raw['radar']['axes'][0]['evidence'] = [{'course_code': 'TEST101', 'clo': 'CLO1'}]
    before = copy.deepcopy(raw)
    with pytest.raises(ComparisonError) as caught:
        validate(raw, service_clo_set, require_radar=True)
    assert caught.value.code == 'invalid_structured_output'
    assert raw == before  # Reject, never clamp either overall or axis scores.


@pytest.mark.parametrize('scores,overall', [
    ([0, 0, 0, 0, 0], 0),
    ([5, 4, 3, 2, 1], 5),
    ([5, 1, 0, 0, 0], 4.8),
    ([1, 1, 1, 0, 0], 0.8),
    ([3, 2, 1, 0, 0], 0),
])
def test_consistent_scores_keep_the_models_holistic_estimate(
        scoring_case, service_clo_set, scores, overall):
    raw, validate = scoring_case
    set_scores(raw, scores, overall)
    before = copy.deepcopy(raw)
    result = validate(raw, service_clo_set, require_radar=True)
    assert result.radar.model_dump() == before['radar']
    assert raw == before


@pytest.mark.parametrize('all_zero', [False, True])
def test_old_radar_snapshot_retains_scores_fingerprint_and_chat(
        target_domain, scoring_case, service_clo_set, service_reply, sdk_client, all_zero):
    raw, validate = scoring_case
    set_scores(raw, [0] * 5 if all_zero else [3, 2, 1, 0, 0], 5)
    raw['radar']['axes'][0]['evidence'] = [{'course_code': 'TEST101', 'clo': 'CLO1'}]
    raw = validate(raw, service_clo_set).model_dump()
    review, chat = sdk_client(raw), sdk_client(service_reply)
    advisor = AdvisorService(review_settings=LLMSettings(api_key='offline'), review_client=review,
        chat_settings=LLMSettings(api_key='offline', stage='chat'), chat_client=chat)
    snapshot = create_pending(advisor, service_clo_set, target_domain)
    if target_domain == 'cwa':
        from app.engines.chat import career_fingerprints
        snapshot['career_profile'].pop('target')
        snapshot['fingerprints'] = career_fingerprints(service_clo_set, snapshot['career_profile'], None)
    snapshot['comparison'] = copy.deepcopy(raw)
    snapshot['fingerprints']['comparison'] = digest(raw)
    before = copy.deepcopy(snapshot)
    assert advisor.validate_snapshot(snapshot) == before
    updated, _ = advisor.chat_snapshot(snapshot, 'Giải thích điểm trong kết quả đã lưu')
    assert updated['comparison'] == before['comparison']
    assert updated['fingerprints'] == before['fingerprints']
    assert snapshot == before
    assert public_comparison(updated['comparison'], service_clo_set)['radar']['overall_score'] == 5
    review.responses.parse.assert_not_called()
    review.responses.input_tokens.count.assert_not_called()
    assert chat.responses.parse.call_count == chat.responses.input_tokens.count.call_count == 1
    request = chat.responses.parse.call_args.kwargs
    approved = json.loads(request['input'][1]['content'])['initial_comparison']
    assert approved == public_comparison(before['comparison'], service_clo_set)
    assert RADAR_SCORING_RULES not in request['instructions']
    assert 'student with less than 1 year' not in request['instructions']


@pytest.mark.parametrize('all_zero', [False, True])
def test_inconsistent_worker_result_rolls_back_without_regeneration(api_backend, queued_session, all_zero):
    client = api_backend.review_client
    raw = copy.deepcopy(client.responses.parse.return_value.output_parsed)
    set_scores(raw, [0] * 5 if all_zero else [3, 2, 1, 0, 0], 5)
    raw['radar']['axes'][0]['evidence'] = [{'course_code': 'TEST101', 'clo': 'CLO1'}]
    client.responses.parse.return_value.output_parsed = raw
    sessions = api_backend.backend.sessions
    before = sessions.get(queued_session['session_id'], queued_session['access_token'])
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor)
    try:
        assert worker.run_once() == queued_session['comparison_job']['job_id']
        assert worker.run_once() is None
    finally:
        worker.close()
    stored = sessions.get(queued_session['session_id'], queued_session['access_token'])
    assert stored['job']['status'] == 'failed'
    assert stored['job']['error_code'] == 'invalid_structured_output'
    assert stored['job']['attempt_count'] == 1
    assert stored['snapshot'] == before['snapshot'] and stored['revision'] == before['revision']
    assert client.responses.parse.call_count == client.responses.input_tokens.count.call_count == 1
    assert raw['radar']['overall_score'] == 5


def test_session_checks_injected_engine_results_before_commit(
        target_domain, scoring_case, service_clo_set):
    raw, _ = scoring_case
    set_scores(raw, [1, 0, 0, 0, 0], 5)
    engine = Mock(return_value=raw)
    advisor = AdvisorService(review_engine=engine, career_engine=engine,
        review_settings=LLMSettings(api_key='offline'))
    snapshot = create_pending(advisor, service_clo_set, target_domain)
    before = copy.deepcopy(snapshot)
    with pytest.raises(ComparisonError):
        advisor.review_snapshot(snapshot)
    assert snapshot == before
    engine.assert_called_once()


def test_shared_scoring_policy_reaches_one_generation_without_changing_source_or_settings(
        target_domain, scoring_case, service_clo_set, sdk_client):
    raw, _ = scoring_case
    client = sdk_client(raw)
    settings = LLMSettings(api_key='offline', model='gpt-5.4', reasoning_effort='high',
        max_output_tokens=32768, request_timeout=360)
    advisor = AdvisorService(review_settings=settings, review_client=client)
    snapshot = create_pending(advisor, service_clo_set, target_domain)
    advisor.review_snapshot(snapshot)
    preflight = client.responses.input_tokens.count.call_args.kwargs
    request = client.responses.parse.call_args.kwargs
    assert (RADAR_SCORING_RULES if target_domain == 'jd' else CWA_RADAR_SCORING_RULES) in request['instructions']
    assert preflight['instructions'] == request['instructions']
    assert [json.loads(m['content']) for m in request['input']] == [
        {'clo_set': service_clo_set},
        {'job_description': snapshot['job_description']} if target_domain == 'jd'
        else {'career_profile': snapshot['career_profile']},
    ]
    assert request['model'] == settings.model and request['reasoning'] == {'effort': 'high'}
    assert request['max_output_tokens'] == 32768 and request['timeout'] == 360
    assert request['store'] is False and request['truncation'] == 'disabled'
    assert client.responses.parse.call_count == client.responses.input_tokens.count.call_count == 1
    client.close.assert_not_called()


def test_public_depth_explanation_flows_to_chat_without_private_policy(
        target_domain, scoring_case, service_clo_set, sdk_client):
    raw, _ = scoring_case
    depth = 'Môn học thể hiện mức hiểu; nhiệm vụ cần thực hiện độc lập; còn thiếu độ sâu thực hành.'
    set_scores(raw, [1, 1, 1, 0, 1], 1)
    raw['conclusion'] = depth
    raw['radar']['overall_comment'] = depth
    for axis in raw['radar']['axes']:
        axis['comment'] = depth
    if target_domain == 'jd':
        raw['requirement_reviews'][0].update(
            jd_requirement='SQL; minimum 3 years professional experience', coverage='related',
            comment=depth + ' Dữ liệu học phần không chứng minh kinh nghiệm thực tế.')
    review, chat = sdk_client(raw), sdk_client({'reply': depth, 'evidence': []})
    advisor = AdvisorService(review_settings=LLMSettings(api_key='offline'), review_client=review,
        chat_settings=LLMSettings(api_key='offline', stage='chat'), chat_client=chat)
    pending = (advisor.create_snapshot(service_clo_set, 'SQL; minimum 3 years professional experience')
               if target_domain == 'jd' else create_pending(advisor, service_clo_set, target_domain))
    ready, result = advisor.review_snapshot(pending)
    request = review.responses.parse.call_args.kwargs
    assert 'student with less than 1 year' in request['instructions']
    assert request['instructions'] == review.responses.input_tokens.count.call_args.kwargs['instructions']
    assert (RADAR_SCORING_RULES if target_domain == 'jd' else CWA_RADAR_SCORING_RULES) in request['instructions']
    assert ready['clo_set'] == service_clo_set and pending['comparison'] is None
    assert result.conclusion == raw['conclusion']
    assert result.radar.overall_comment == raw['radar']['overall_comment']
    updated, reply = advisor.chat_snapshot(ready, 'Giải thích khoảng cách về độ sâu')
    approved = json.loads(chat.responses.parse.call_args.kwargs['input'][1]['content'])['initial_comparison']
    assert approved == public_comparison(ready['comparison'], service_clo_set)
    assert approved['conclusion'] == reply.reply == depth
    assert updated['comparison'] == ready['comparison']
    assert updated['fingerprints'] == ready['fingerprints']
    for client in (review, chat):
        assert client.responses.parse.call_count == client.responses.input_tokens.count.call_count == 1
