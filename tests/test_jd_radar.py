import copy
import json

import pytest

from app.engines.chat import snapshot_fingerprints
from app.engines.comparison import generate_comparison
from app.engines.errors import ComparisonError
from app.engines.models import ScoredCLOJDComparison, validate_comparison
from app.json_utils import digest
from app.llm import LLMSettings
from app.public_view import comparison as public_comparison
from app.services import AdvisorService

pytestmark = pytest.mark.usefixtures('service_offline')


def test_new_jd_generation_requires_five_axes_and_preserves_model_scores(service_clo_set, service_review, sdk_client):
    schema = ScoredCLOJDComparison.model_json_schema()
    assert 'radar' in schema['required']
    assert schema['$defs']['CareerRadar']['properties']['axes']['minItems'] == 5
    client = sdk_client(service_review)
    result = generate_comparison(service_clo_set, 'Python AND SQL, Docker preferred', LLMSettings(api_key='offline'), client=client)
    assert result.radar.overall_score == 3.7
    assert result.radar.overall_score != sum(a.score for a in result.radar.axes) / 5
    request = client.responses.parse.call_args.kwargs
    assert request['text_format'] is ScoredCLOJDComparison
    assert request['store'] is False and request['truncation'] == 'disabled'
    assert json.loads(request['input'][1]['content']) == {'job_description': 'Python AND SQL, Docker preferred'}
    assert client.responses.parse.call_count == client.responses.input_tokens.count.call_count == 1


@pytest.mark.parametrize('change', ['missing', 'null', 'four', 'duplicate_name', 'wrong_clo', 'duplicate_evidence', 'no_evidence', 'private_text'])
def test_jd_radar_validation_is_atomic(service_clo_set, service_review, sdk_client, change):
    raw = copy.deepcopy(service_review)
    if change == 'missing': raw.pop('radar')
    elif change == 'null': raw['radar'] = None
    elif change == 'four': raw['radar']['axes'].pop()
    elif change == 'duplicate_name': raw['radar']['axes'][1]['name'] = raw['radar']['axes'][0]['name'].upper()
    elif change == 'wrong_clo': raw['radar']['axes'][0]['evidence'][0]['clo'] = 'CLO999'
    elif change == 'duplicate_evidence': raw['radar']['axes'][0]['evidence'] *= 2
    elif change == 'no_evidence': raw['radar']['axes'][0]['evidence'] = []
    else:
        secret = 'Confidential course source definitions must never be copied into public responses'
        service_clo_set['courses'][0]['clos'][0]['description'] = secret
        raw['radar']['axes'][0]['description'] = secret
    client = sdk_client(raw)
    advisor = AdvisorService(review_settings=LLMSettings(api_key='offline'), review_client=client)
    pending = advisor.create_snapshot(service_clo_set, 'SQL')
    before = copy.deepcopy(pending)
    with pytest.raises(ComparisonError): advisor.review_snapshot(pending)
    assert pending == before and client.responses.parse.call_count == 1


def test_jd_radar_empty_sources_require_zero_scores(service_review):
    service_review['requirement_reviews'] = []
    service_review['radar']['overall_score'] = 0
    for axis in service_review['radar']['axes']: axis.update(score=0, evidence=[])
    assert validate_comparison(service_review, {'courses': []}, require_radar=True)
    service_review['radar']['overall_score'] = 1
    with pytest.raises(ComparisonError): validate_comparison(service_review, {'courses': []}, require_radar=True)


def test_jd_without_comparable_requirements_does_not_need_fabricated_axes(service_clo_set, service_review, sdk_client):
    service_review.update(requirement_reviews=[], radar=None)
    assert validate_comparison(service_review, service_clo_set, require_radar=True).radar is None
    client = sdk_client(ScoredCLOJDComparison.model_validate(service_review))
    result = generate_comparison(service_clo_set, 'Salary and location only', LLMSettings(api_key='offline'), client=client)
    assert 'radar' not in result.model_dump()


def test_legacy_jd_snapshot_keeps_exact_fingerprint_and_can_chat(service_clo_set, service_review, service_reply, sdk_client):
    legacy = copy.deepcopy(service_review)
    legacy.pop('radar')
    advisor = AdvisorService(chat_settings=LLMSettings(api_key='offline', stage='chat'), chat_client=sdk_client(service_reply))
    snapshot = advisor.create_snapshot(service_clo_set, 'SQL')
    snapshot['comparison'] = legacy
    snapshot['fingerprints']['comparison'] = digest(legacy)
    assert advisor.validate_snapshot(snapshot) == snapshot
    assert snapshot_fingerprints(service_clo_set, 'SQL', legacy)['comparison'] == digest(legacy)
    updated, _ = advisor.chat_snapshot(snapshot, 'Giải thích kết quả cũ')
    assert updated['comparison'] == legacy and updated['fingerprints'] == snapshot['fingerprints']
    assert 'radar' not in public_comparison(legacy, service_clo_set)


def test_jd_radar_evidence_is_publicly_projected_and_available_to_chat(service_clo_set, service_review, sdk_client):
    service_review['radar']['axes'][0]['evidence'] = [{'course_code': 'TEST101', 'clo': 'CLO2'}]
    review = sdk_client(service_review)
    chat = sdk_client({'reply': 'Giải thích điểm đã lưu theo JD.', 'evidence': [{'course_code': 'TEST101', 'clo': 'CLO2'}]})
    advisor = AdvisorService(review_settings=LLMSettings(api_key='offline'), review_client=review,
        chat_settings=LLMSettings(api_key='offline', stage='chat'), chat_client=chat)
    snapshot, result = advisor.review_snapshot(advisor.create_snapshot(service_clo_set, 'SQL'))
    public = public_comparison(result.model_dump(), service_clo_set)
    assert public['radar']['axes'][0]['evidence'] == [{'course_code': 'TEST101'}]
    assert '"clo"' not in json.dumps(public)
    snapshot, _ = advisor.chat_snapshot(snapshot, 'Giải thích radar')
    context = json.loads(chat.responses.parse.call_args.kwargs['input'][1]['content'])
    assert context['initial_comparison']['radar']['overall_score'] == 3.7
    assert {'course_code': 'TEST101', 'clo': 'CLO2'} in context['permitted_evidence']
    assert review.responses.parse.call_count == chat.responses.parse.call_count == 1
    snapshot['comparison']['radar']['overall_score'] = 4.9
    with pytest.raises(ComparisonError): advisor.validate_snapshot(snapshot)
