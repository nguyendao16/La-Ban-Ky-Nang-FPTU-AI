"""Fixed CWA scopes, eight role choices, rollback and unchanged JD/legacy contracts."""
import copy
from contextlib import closing
import json
from unittest.mock import Mock

import pytest

from app.engines.career import (
    CAREER_INSTRUCTIONS, CWA_RADAR_SCORING_RULES, CareerProfile,
    _DYNAMIC_AXES, _WHOLE_TARGET, validate_career_comparison,
)
from app.engines.chat import career_fingerprints
from app.engines.errors import ComparisonError
from app.engines.models import ChatResponse, ScoredCLOJDComparison, parse_model
from app.engines.prompts import CHAT_INSTRUCTIONS, COMPARISON_INSTRUCTIONS, RADAR_SCORING_RULES, SOURCE_RULES
from app.jobs.review_worker import ReviewWorker
from app.json_utils import digest
from app.llm import LLMSettings
from app.services import AdvisorService, CareerCatalog
from app.services.errors import StorageIntegrityError

pytestmark = pytest.mark.usefixtures('service_offline')

# Independently pin the reviewed names and order, including punctuation/spelling.
EXPECTED = {
    'data-scientist': ['Data Preparation & Governance', 'Business Problem Modelling', 'Statistical Analysis', 'AI/ML Modelling & Evaluation', 'Visualization & Communication'],
    'data-analyst': ['Data Collection & Modelling', 'Data Quality & Transformation', 'Data Analysis & Interpretation', 'Visualization & Business Insights', 'Data Governance & Protection'],
    'ai-ml-engineer': ['AI Tooling & Workflows', 'Model & Component Development', 'Testing & Troubleshooting', 'Integration & Deployment', 'Secure & Responsible AI Engineering'],
    'computer-vision-engineer': ['Image & Video Processing', 'Vision Model Development', 'Testing & Troubleshooting', 'Vision Integration & Deployment', 'Secure & Responsible Vision Engineering'],
    'nlp-llm-engineer': ['Text Processing', 'Model Adaptation & Prompting', 'NLP/LLM Testing & Troubleshooting', 'Application Integration & Deployment', 'Secure & Responsible AI Engineering'],
    'mlops-engineer': ['Model & Data Lifecycle', 'Infrastructure & Scalability', 'Pipeline & Deployment Automation', 'Monitoring & Recovery', 'Security & Compliance'],
    'ai-researcher': ['Theoretical Foundations', 'Algorithm & Model Innovation', 'Scientific Experimentation', 'Generalization, Interpretability & Alignment', 'Research Communication & Impact'],
    'ai-data-platform-engineer': ['Data Architecture', 'Data Engineering', 'AI Infrastructure & Cost Efficiency', 'Platform Automation & Deployment', 'Reliability, Security & Observability'],
}


@pytest.mark.parametrize('profile_id', EXPECTED)
def test_every_target_generates_its_exact_pinned_scopes_once_and_can_chat(
        profile_id, service_clo_set, career_review_for, service_reply, sdk_client):
    profile = CareerCatalog().get(profile_id)
    assert [axis['name'] for axis in profile['target']['axes']] == EXPECTED[profile_id]
    assert all(any(ord(c) > 127 for c in axis['description']) for axis in profile['target']['axes'])
    raw = career_review_for(profile_id)
    review, chat = sdk_client(raw), sdk_client(service_reply)
    advisor = AdvisorService(review_settings=LLMSettings(api_key='offline'), review_client=review,
        chat_settings=LLMSettings(api_key='offline', stage='chat'), chat_client=chat)
    pending = advisor.create_career_snapshot(service_clo_set, profile)
    before = copy.deepcopy(pending)
    profile['target']['axes'].clear()
    ready, result = advisor.review_snapshot(pending)
    assert pending == before
    assert [(a.name, a.description) for a in result.radar.axes] == [
        (a['name'], a['description']) for a in before['career_profile']['target']['axes']]
    assert result.radar.overall_score == raw['radar']['overall_score']  # Never average/clamp.
    request = review.responses.parse.call_args.kwargs
    assert request['instructions'] == CAREER_INSTRUCTIONS
    assert [json.loads(m['content']) for m in request['input']] == [
        {'clo_set': service_clo_set}, {'career_profile': before['career_profile']}]
    assert request['store'] is False and request['truncation'] == 'disabled'
    ready, _ = advisor.chat_snapshot(ready, 'Giải thích phạm vi đối chiếu')
    assert ready['comparison'] == result.model_dump()
    assert ready['fingerprints']['career_profile'] == before['fingerprints']['career_profile']
    for client in (review, chat):
        assert client.responses.parse.call_count == client.responses.input_tokens.count.call_count == 1
        client.close.assert_not_called()


@pytest.mark.parametrize('mutation', ['name', 'case', 'translation', 'order', 'scope', 'missing'])
def test_injected_engine_cannot_change_fixed_axes_before_commit(
        service_clo_set, career_review, mutation):
    raw = copy.deepcopy(career_review)
    axes = raw['radar']['axes']
    if mutation == 'name': axes[0]['name'] = 'Another topic'
    elif mutation == 'case': axes[0]['name'] = axes[0]['name'].lower()
    elif mutation == 'translation': axes[0]['name'] = 'Thu thập dữ liệu'
    elif mutation == 'order': axes.reverse()
    elif mutation == 'scope': axes[0]['description'] = 'Chỉ học SQL cơ bản.'
    else: raw.pop('radar')
    engine = Mock(return_value=raw)
    advisor = AdvisorService(career_engine=engine, review_settings=LLMSettings(api_key='offline'))
    pending = advisor.create_career_snapshot(service_clo_set, CareerCatalog().get('data-analyst'))
    before = copy.deepcopy(pending)
    with pytest.raises(ComparisonError): advisor.review_snapshot(pending)
    assert pending == before
    engine.assert_called_once()


@pytest.mark.parametrize('target_domain', ['cwa'], indirect=True)
@pytest.mark.parametrize('mutation', ['order', 'scope', 'wrong_role'])
def test_worker_rolls_back_wrong_fixed_contract_and_replay_does_not_dispatch(
        api_backend, queued_session, career_review_for, mutation):
    raw = copy.deepcopy(api_backend.review_client.responses.parse.return_value.output_parsed)
    if mutation == 'order': raw['radar']['axes'].reverse()
    elif mutation == 'scope': raw['radar']['axes'][0]['description'] = 'Phạm vi tùy ý.'
    else: raw = career_review_for('computer-vision-engineer')
    api_backend.review_client.responses.parse.return_value.output_parsed = raw
    before = api_backend.backend.sessions.get(queued_session['session_id'], queued_session['access_token'])
    with closing(ReviewWorker(api_backend.backend.jobs, api_backend.advisor)) as worker:
        worker.run_once()
        assert worker.run_once() is None
    after = api_backend.backend.sessions.get(queued_session['session_id'], queued_session['access_token'])
    assert after['snapshot'] == before['snapshot'] and after['revision'] == 0
    assert after['job']['status'] == 'failed' and after['job']['attempt_count'] == 1
    assert after['job']['error_code'] == 'invalid_structured_output'
    replay = api_backend.client.post('/api/v1/advisor/sessions', headers=queued_session['headers'],
        json={'selection_id': before['clo_set_id'], 'career_profile_id': 'data-analyst'})
    assert replay.status_code == 202 and replay.json()['session_id'] == queued_session['session_id']
    assert api_backend.review_client.responses.parse.call_count == 1


def test_specialties_share_original_source_but_have_distinct_pinned_targets(service_clo_set):
    catalog = CareerCatalog()
    profiles = [catalog.get(key) for key in ['ai-ml-engineer', 'computer-vision-engineer', 'nlp-llm-engineer']]
    assert len({p['content'] for p in profiles}) == len({p['fingerprint'] for p in profiles}) == 1
    assert all(p['role_codes'] == ['2.3'] for p in profiles)
    assert [p['target']['title'] for p in profiles] == ['Machine Learning Engineer', 'Computer Vision Engineer', 'NLP / LLM Engineer']
    assert len({digest(p) for p in profiles}) == 3
    assert 'Không bắt buộc chuyên môn Computer Vision hoặc NLP/LLM' in profiles[0]['target']['scope']
    assert 'Không bắt buộc chuyên môn NLP/LLM' in profiles[1]['target']['scope']
    assert 'huấn luyện LLM từ đầu' in profiles[2]['target']['scope']
    first = AdvisorService().create_career_snapshot(service_clo_set, profiles[1])
    profiles[1]['target']['title'] = 'Changed externally'
    assert first['career_profile']['target']['title'] == 'Computer Vision Engineer'
    assert catalog.get('computer-vision-engineer')['target'] == first['career_profile']['target']


@pytest.mark.parametrize('change', ['scope', 'name', 'order', 'title'])
def test_target_tampering_is_detected_by_snapshot_fingerprint(service_clo_set, change):
    advisor = AdvisorService()
    snapshot = advisor.create_career_snapshot(service_clo_set, CareerCatalog().get('data-analyst'))
    target = snapshot['career_profile']['target']
    if change == 'scope': target['scope'] += ' Changed'
    elif change == 'title': target['title'] += ' Changed'
    elif change == 'name': target['axes'][0]['name'] = 'Changed'
    else: target['axes'].reverse()
    with pytest.raises(ComparisonError): advisor.validate_snapshot(snapshot)


@pytest.mark.parametrize('target_domain', ['cwa'], indirect=True)
def test_pinned_definitions_survive_catalog_change_and_commit_cannot_change_them(
        api_backend, queued_session, monkeypatch):
    before = api_backend.backend.sessions.get(queued_session['session_id'], queued_session['access_token'])['snapshot']
    monkeypatch.setattr(api_backend.backend.persistent.careers, 'get', Mock(side_effect=AssertionError('Catalog must not be consulted')))
    with closing(ReviewWorker(api_backend.backend.jobs, api_backend.advisor)) as worker: worker.run_once()
    ready = api_backend.backend.sessions.get(queued_session['session_id'], queued_session['access_token'])['snapshot']
    assert ready['career_profile'] == before['career_profile']
    lease, _ = api_backend.backend.sessions.claim_chat(queued_session['session_id'], queued_session['access_token'], 'SQL?', 'changed-target')
    updated, response = api_backend.advisor.chat_snapshot(ready, 'SQL?')
    updated['career_profile']['target']['scope'] += ' Changed'
    updated['fingerprints'] = career_fingerprints(updated['clo_set'], updated['career_profile'], updated['comparison'])
    with pytest.raises(StorageIntegrityError): api_backend.backend.sessions.commit_chat(lease, updated, response)
    assert api_backend.backend.sessions.history(queued_session['session_id'], queued_session['access_token']) == []


@pytest.mark.parametrize('profile_id', ['computer-vision-engineer', 'nlp-llm-engineer'])
@pytest.mark.parametrize('target_domain', ['cwa'], indirect=True)
def test_new_specialty_api_targets_keep_idempotency_and_replay_pinned_definition(
        api_backend, stored_clo_set, profile_id, career_review_for):
    headers = {'Authorization': 'Bearer ' + stored_clo_set['access_token'], 'Idempotency-Key': 'specialty-key'}
    body = {'selection_id': stored_clo_set['selection_id'], 'career_profile_id': profile_id}
    first = api_backend.client.post('/api/v1/advisor/sessions', headers=headers, json=body)
    assert first.status_code == 202
    api_backend.review_client.responses.parse.return_value.output_parsed = career_review_for(profile_id)
    with closing(ReviewWorker(api_backend.backend.jobs, api_backend.advisor)) as worker: worker.run_once()
    api_backend.backend.persistent.careers.get = Mock(side_effect=AssertionError('Replay must use stored request'))
    assert api_backend.client.post('/api/v1/advisor/sessions', headers=headers, json=body).json() == first.json()
    other_id = 'nlp-llm-engineer' if profile_id == 'computer-vision-engineer' else 'computer-vision-engineer'
    conflict = api_backend.client.post('/api/v1/advisor/sessions', headers=headers, json={**body, 'career_profile_id': other_id})
    assert conflict.status_code == 409
    view = api_backend.client.get('/api/v1/advisor/sessions/' + first.json()['session_id'], headers=headers).json()
    assert view['status'] == 'ready'
    assert [a['name'] for a in view['comparison']['radar']['axes']] == EXPECTED[profile_id]
    assert api_backend.review_client.responses.parse.call_count == 1


def test_legacy_dynamic_snapshot_keeps_names_scores_fingerprints_and_chat(
        service_clo_set, career_review, career_radar, service_reply, sdk_client, monkeypatch):
    profile = CareerCatalog().get('ai-ml-engineer')
    profile.pop('target')
    assert parse_model(CareerProfile, profile).model_dump() == profile
    old_review = copy.deepcopy(career_review)
    old_review['radar'] = career_radar
    chat = sdk_client(service_reply)
    advisor = AdvisorService(chat_settings=LLMSettings(api_key='offline', stage='chat'), chat_client=chat)
    pending = advisor.create_career_snapshot(service_clo_set, profile)
    pending['comparison'] = old_review
    pending['fingerprints'] = career_fingerprints(service_clo_set, profile, old_review)
    monkeypatch.setattr(CareerCatalog, 'get', Mock(side_effect=AssertionError('Old snapshots do not consult catalog')))
    before = copy.deepcopy(pending)
    updated, _ = advisor.chat_snapshot(pending, 'Giải thích kết quả đã lưu')
    assert updated['comparison'] == before['comparison']
    assert updated['career_profile'] == profile and 'target' not in updated['career_profile']
    assert updated['fingerprints'] == before['fingerprints']
    assert advisor.validate_snapshot(pending) == before
    assert chat.responses.parse.call_count == 1


def test_jd_prompt_policy_and_generation_schemas_are_byte_identical_to_baseline():
    assert {key: digest(value) for key, value in {
        'source': SOURCE_RULES, 'instructions': COMPARISON_INSTRUCTIONS, 'chat': CHAT_INSTRUCTIONS,
        'radar_rules': RADAR_SCORING_RULES, 'generation_schema': ScoredCLOJDComparison.model_json_schema(),
        'chat_schema': ChatResponse.model_json_schema(),
    }.items()} == {
        'source': '8ea3c158ff08336da984caab3d33e2430d3f6c43c043d860f970d970d6acc783',
        'instructions': 'cc9102e01b04790866ebb1a8da88a2b4bed6f6406f3d66b9c5b7cbc76c298f2b',
        'chat': '5744c23f8fafa6ae25860032595482360f02f11d3add9ec3421de4f02f1fdcb6',
        'radar_rules': '23ccf96c12d43aa9a0450ba5b9dfddd9c2851e2bb3cf152d85af795ea073a734',
        'generation_schema': '1fe7148691d791be029d4cab3d72efdea615296f98691b14c706c4ebbd681efa',
        'chat_schema': '9ba8522902ebfd2c428cee046f2150dd4efe31eb0752ba3fb0db36545bda566b',
    }
    assert RADAR_SCORING_RULES.count(_DYNAMIC_AXES) == RADAR_SCORING_RULES.count(_WHOLE_TARGET) == 1
    assert _DYNAMIC_AXES not in CWA_RADAR_SCORING_RULES and _WHOLE_TARGET not in CWA_RADAR_SCORING_RULES
    assert 'overall_score only against' in CWA_RADAR_SCORING_RULES
