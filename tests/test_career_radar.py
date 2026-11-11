"""Strict LLM radar output, evidence privacy and unchanged legacy snapshots."""
import copy
import json

import pytest

from app.engines.career import ScoredCareerComparison, validate_career_comparison
from app.engines.chat import CLOChatSession, career_fingerprints
from app.engines.errors import ComparisonError
from app.json_utils import digest
from app.llm import LLMSettings
from app.public_view import comparison as public_comparison
from app.services import AdvisorService, CareerCatalog

pytestmark = pytest.mark.usefixtures('service_offline')


@pytest.mark.parametrize('where', ['axis', 'overall'])
@pytest.mark.parametrize('score', [-0.1, 5.1, True, '3', float('nan'), float('inf'), -float('inf')])
def test_scores_are_finite_numbers_on_five_point_scale(service_clo_set, career_review, where, score):
    raw = copy.deepcopy(career_review)
    if where == 'axis': raw['radar']['axes'][0]['score'] = score
    else: raw['radar']['overall_score'] = score
    with pytest.raises(ComparisonError): validate_career_comparison(raw, service_clo_set, require_radar=True)


@pytest.mark.parametrize('change', ['four', 'six', 'duplicate', 'no_radar', 'null_radar', 'no_evidence', 'wrong_clo', 'duplicate_evidence', 'metadata'])
def test_exactly_five_distinct_grounded_axes(service_clo_set, career_review, change):
    raw = copy.deepcopy(career_review)
    axes = raw['radar']['axes']
    if change == 'four': axes.pop()
    elif change == 'six': axes.append(copy.deepcopy(axes[0]))
    elif change == 'duplicate': axes[1]['name'] = '  ' + axes[0]['name'].upper() + '  '
    elif change == 'no_radar': raw.pop('radar')
    elif change == 'null_radar': raw['radar'] = None
    elif change == 'no_evidence': axes[0]['evidence'] = []
    elif change == 'wrong_clo': axes[0]['evidence'][0]['clo'] = 'CLO999'
    elif change == 'duplicate_evidence': axes[0]['evidence'] *= 2
    else: axes[0]['evidence'] = [{'course_code': 'TEST101', 'metadata_field': 'tools'}]
    with pytest.raises(ComparisonError): validate_career_comparison(raw, service_clo_set, require_radar=True)


def test_model_overall_is_not_recomputed_and_boundary_scores_are_valid(service_clo_set, career_review):
    raw = copy.deepcopy(career_review)
    raw['radar']['overall_score'] = 4.8
    raw['radar']['axes'][0]['score'] = 5
    result = validate_career_comparison(raw, service_clo_set, require_radar=True)
    assert result.radar.overall_score == 4.8
    assert result.radar.axes[0].score == 5
    assert result.radar.axes[3].score == 0
    assert result.radar.overall_score != sum(a.score for a in result.radar.axes) / 5


def test_empty_course_source_requires_zero_scores_without_fake_evidence(career_review):
    raw = copy.deepcopy(career_review)
    raw['related_content'] = []
    raw['radar']['overall_score'] = 0
    for axis in raw['radar']['axes']: axis.update(score=0, evidence=[])
    assert validate_career_comparison(raw, {'courses': []}, require_radar=True)
    raw['radar']['overall_score'] = 1
    with pytest.raises(ComparisonError): validate_career_comparison(raw, {'courses': []}, require_radar=True)


@pytest.mark.parametrize('field', ['description', 'comment', 'overall_comment'])
def test_radar_prose_cannot_disclose_course_source(service_clo_set, career_review, field):
    secret = 'Confidential academic source definitions must never be copied into public responses'
    service_clo_set['courses'][0]['clos'][0]['description'] = secret
    if field == 'overall_comment': career_review['radar'][field] = secret
    else: career_review['radar']['axes'][0][field] = secret
    with pytest.raises(ComparisonError): validate_career_comparison(career_review, service_clo_set, require_radar=True)


def test_radar_projection_keeps_model_numbers_and_only_public_evidence(service_clo_set, career_review):
    career_review['radar']['axes'][0]['evidence'].append({'course_code': 'TEST101', 'clo': 'CLO2'})
    result = validate_career_comparison(career_review, service_clo_set, require_radar=True)
    public = public_comparison(result.model_dump(), service_clo_set)
    assert public['radar']['overall_score'] == 3.7
    assert public['radar']['axes'][0]['evidence'] == [{'course_code': 'TEST101'}]
    assert '"clo"' not in json.dumps(public)
    assert len(public['radar']['axes']) == 5


def test_old_v4_snapshot_retains_exact_fingerprint_and_can_chat_without_generation(service_clo_set, career_review, service_reply, sdk_client):
    legacy = copy.deepcopy(career_review)
    legacy.pop('radar')
    advisor = AdvisorService(chat_settings=LLMSettings(api_key='offline', stage='chat'), chat_client=sdk_client(service_reply))
    snapshot = advisor.create_career_snapshot(service_clo_set, CareerCatalog().get('data-analyst'))
    snapshot['career_profile'].pop('target')
    snapshot['fingerprints'] = career_fingerprints(service_clo_set, snapshot['career_profile'], None)
    snapshot['comparison'] = legacy
    snapshot['fingerprints'] = {**snapshot['fingerprints'], 'comparison': digest(legacy)}
    assert advisor.validate_snapshot(snapshot) == snapshot
    assert career_fingerprints(service_clo_set, snapshot['career_profile'], legacy)['comparison'] == digest(legacy)
    updated, _ = advisor.chat_snapshot(snapshot, 'Giải thích kết quả cũ')
    assert updated['comparison'] == legacy and 'radar' not in updated['comparison']
    assert updated['fingerprints'] == snapshot['fingerprints']
    assert len(updated['messages']) == 2


def test_radar_only_evidence_is_available_to_chat_and_fingerprint_detects_score_tampering(service_clo_set, career_review_for, sdk_client):
    career_review = career_review_for('data-scientist')
    career_review['radar']['axes'][0]['evidence'] = [{'course_code': 'TEST101', 'clo': 'CLO2'}]
    chat = sdk_client({'reply': 'Trục này phản ánh nội dung trong môn đã chọn.', 'evidence': [{'course_code': 'TEST101', 'clo': 'CLO2'}]})
    review = sdk_client(career_review)
    advisor = AdvisorService(review_settings=LLMSettings(api_key='offline'), review_client=review,
        chat_settings=LLMSettings(api_key='offline', stage='chat'), chat_client=chat)
    snapshot = advisor.create_career_snapshot(service_clo_set, CareerCatalog().get('data-scientist'))
    snapshot, _ = advisor.review_snapshot(snapshot)
    before = copy.deepcopy(snapshot)
    snapshot, _ = advisor.chat_snapshot(snapshot, 'Giải thích radar')
    assert review.responses.parse.call_count == review.responses.input_tokens.count.call_count == 1
    request = chat.responses.parse.call_args.kwargs
    context = json.loads(request['input'][1]['content'])
    assert context['initial_comparison']['radar']['overall_score'] == 3.7
    assert {'course_code': 'TEST101', 'clo': 'CLO2'} in context['permitted_evidence']
    assert '"clos"' not in json.dumps(request['input'])
    before['comparison']['radar']['overall_score'] = 4.9
    with pytest.raises(ComparisonError): advisor.validate_snapshot(before)


@pytest.mark.parametrize('failure', ['missing', 'invalid_score'])
@pytest.mark.parametrize('target_domain', ['cwa'], indirect=True)
def test_invalid_radar_worker_output_rolls_back_without_another_generation(api_backend, queued_session, failure):
    from app.jobs.review_worker import ReviewWorker
    raw = copy.deepcopy(api_backend.review_client.responses.parse.return_value.output_parsed)
    if failure == 'missing': raw.pop('radar')
    else: raw['radar']['overall_score'] = 9
    api_backend.review_client.responses.parse.return_value.output_parsed = raw
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor)
    try:
        worker.run_once()
        assert worker.run_once() is None
    finally: worker.close()
    record = api_backend.backend.sessions.get(queued_session['session_id'], queued_session['access_token'])
    assert record['job']['status'] == 'failed'
    assert record['snapshot']['comparison'] is None and record['revision'] == 0
    assert api_backend.review_client.responses.parse.call_count == 1


def test_generation_schema_requires_radar_without_optional_legacy_default():
    schema = ScoredCareerComparison.model_json_schema()
    assert 'radar' in schema['required']
    assert schema['properties']['radar'] == {'$ref': '#/$defs/CareerRadar'}
    axes = schema['$defs']['CareerRadar']['properties']['axes']
    assert axes['minItems'] == axes['maxItems'] == 5
