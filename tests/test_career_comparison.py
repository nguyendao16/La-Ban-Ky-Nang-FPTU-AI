"""Offline career contracts: exact local sources, free analysis, private evidence."""
import copy
import hashlib
import json
from unittest.mock import Mock

import pytest

from app.engines.career import CareerComparison, ScoredCareerComparison, CAREER_INSTRUCTIONS, validate_career_comparison
from app.engines.chat import CLOChatSession
from app.engines.errors import ComparisonError, ComparisonAlreadyReadyError, ComparisonNotReadyError
from app.llm import LLMSettings, openai
from app.public_view import comparison as public_comparison
from app.services import AdvisorService
from app.services.career_catalog import CareerCatalog, PROFILES
from app.services.errors import BackendUnavailableError, ResourceNotFoundError

pytestmark = pytest.mark.usefixtures('service_offline')


def test_eight_targets_preserve_six_whole_sources_and_combined_role_codes():
    catalog = CareerCatalog()
    profiles = catalog.list_profiles()
    assert [p['profile_id'] for p in profiles] == list(PROFILES)
    assert len(profiles) == 8 and len(set(PROFILES.values())) == 6
    for p in profiles:
        raw = (catalog.directory / PROFILES[p['profile_id']]).read_bytes()
        assert p['content'].encode('utf-8') == raw
        assert p['fingerprint'] == hashlib.sha256(raw).hexdigest()
        assert 'MAIN TASKS' in p['content'] and 'KEY DELIVERABLES' in p['content']
    assert profiles[-1]['role_codes'] == ['2.12', '1.4']
    assert 'Computer Vision' in profiles[2]['content'] and 'NLP' in profiles[2]['content']
    profiles[0]['role_codes'].clear()
    assert catalog.list_profiles()[0]['role_codes'] == ['1.1']
    with pytest.raises(ResourceNotFoundError): catalog.get('../data-scientist')


@pytest.mark.parametrize('content', [None, '', 'VỊ TRÍ: Fake\nMÃ VỊ TRÍ: 1.1\nTIÊU CHUẨN: wrong'])
def test_missing_or_malformed_career_source_fails_closed(tmp_path, content):
    if content is not None: (tmp_path / PROFILES['data-scientist']).write_text(content)
    with pytest.raises(BackendUnavailableError): CareerCatalog(tmp_path).get('data-scientist')


def test_career_payload_settings_counts_ownership_and_chat_source_isolation(service_clo_set, career_review, service_reply, sdk_client):
    profile = CareerCatalog().get('data-analyst')
    review_client, chat_client = sdk_client(career_review), sdk_client(service_reply)
    review_settings = LLMSettings(api_key='offline', stage='review', model='gpt-5.4', max_output_tokens=32768, request_timeout=360)
    chat_settings = LLMSettings(api_key='offline', stage='chat', model='gpt-5.4-mini')
    advisor = AdvisorService(review_settings=review_settings, chat_settings=chat_settings,
                             review_client=review_client, chat_client=chat_client)
    snapshot = advisor.create_career_snapshot(service_clo_set, profile)
    assert snapshot['version'] == 4 and 'job_description' not in snapshot
    with CLOChatSession.from_snapshot(snapshot) as pending:
        with pytest.raises(ComparisonNotReadyError): pending.send('Giải thích?')
    profile['content'] = 'external mutation'
    updated, result = advisor.review_snapshot(snapshot)
    assert snapshot['comparison'] is None
    with pytest.raises(ComparisonAlreadyReadyError): advisor.review_snapshot(updated)
    assert review_client.responses.parse.call_count == review_client.responses.input_tokens.count.call_count == 1
    request = review_client.responses.parse.call_args.kwargs
    assert request['instructions'] == CAREER_INSTRUCTIONS and request['text_format'] is ScoredCareerComparison
    assert [json.loads(m['content']) for m in request['input']] == [{'clo_set': service_clo_set}, {'career_profile': snapshot['career_profile']}]
    assert request['model'] == 'gpt-5.4' and request['max_output_tokens'] == 32768
    assert request['store'] is False and request['truncation'] == 'disabled'
    for question in ['Nền tảng liên quan thế nào?', 'Khoảng trống nào?']:
        updated, _ = advisor.chat_snapshot(updated, question)
    chat_request = chat_client.responses.parse.call_args.kwargs
    assert chat_request['model'] == 'gpt-5.4-mini'
    assert json.loads(chat_request['input'][0]['content']) == {'career_profile': snapshot['career_profile']}
    assert json.loads(chat_request['input'][1]['content'])['initial_comparison'] == public_comparison(result.model_dump(), service_clo_set)
    assert [m['role'] for m in chat_request['input']] == ['user', 'user', 'user', 'assistant', 'user']
    assert len(updated['messages']) == 4 and advisor.validate_snapshot(updated) == updated
    payload = json.dumps(chat_request['input'])
    for c in service_clo_set['courses']:
        for clo in c['clos']: assert clo['description'] not in payload
    assert '"clos"' not in payload and '"metadata"' not in payload
    assert chat_client.responses.parse.call_count == chat_client.responses.input_tokens.count.call_count == 2
    advisor.close()
    review_client.close.assert_not_called()
    chat_client.close.assert_not_called()


def test_career_owned_clients_disable_retries_and_close(service_clo_set, career_review_for, service_reply, sdk_client, monkeypatch):
    career_review = career_review_for('mlops-engineer')
    clients = [sdk_client(career_review), sdk_client(service_reply)]
    constructor = Mock(side_effect=clients)
    monkeypatch.setattr(openai, 'OpenAI', constructor)
    advisor = AdvisorService(review_settings=LLMSettings(api_key='offline'), chat_settings=LLMSettings(api_key='offline', stage='chat'))
    source = advisor.create_career_snapshot(service_clo_set, CareerCatalog().get('mlops-engineer'))
    source, _ = advisor.review_snapshot(source)
    advisor.chat_snapshot(source, 'Giải thích')
    assert constructor.call_count == 2
    for call in constructor.call_args_list: assert call.kwargs['max_retries'] == 0
    for client in clients: client.close.assert_called_once()


@pytest.mark.parametrize('change', ['type', 'coverage', 'score', 'no_evidence', 'duplicate', 'wrong_course', 'wrong_clo', 'metadata', 'leak'])
def test_career_schema_and_confidential_evidence(service_clo_set, career_review, change):
    raw = copy.deepcopy(career_review)
    finding = raw['related_content'][0]
    if change == 'type': raw['comparison_type'] = 'clo_jd_comparison'
    elif change in ['coverage', 'score']: finding[change] = 'covered' if change == 'coverage' else 90
    elif change == 'no_evidence': finding['evidence'] = []
    elif change == 'duplicate': finding['evidence'] *= 2
    elif change == 'wrong_course': finding['evidence'][0]['course_code'] = 'OTHER201'
    elif change == 'wrong_clo': finding['evidence'][0]['clo'] = 'CLO999'
    elif change == 'metadata': finding['evidence'][0] = {'course_code': 'TEST101', 'metadata_field': 'tools'}
    else:
        service_clo_set['courses'][0]['clos'][0]['description'] = 'Confidential course source with many exact words for privacy validation'
        raw['overview'] = service_clo_set['courses'][0]['clos'][0]['description']
    with pytest.raises(ComparisonError): validate_career_comparison(raw, service_clo_set)


def test_empty_source_and_freely_grouped_findings_are_valid(career_review):
    raw = copy.deepcopy(career_review)
    raw['related_content'] = []
    raw.pop('radar')
    assert validate_career_comparison(raw, {'courses': []})
    raw['gaps'] = []
    assert validate_career_comparison(raw, {'courses': []})


@pytest.mark.parametrize('change', ['source', 'content', 'title', 'codes', 'fingerprint', 'comparison', 'history', 'history_evidence', 'target_kind'])
def test_career_snapshot_tampering_rejected(service_clo_set, career_review_for, sdk_client, change):
    career_review = career_review_for('data-scientist')
    advisor = AdvisorService(review_settings=LLMSettings(api_key='offline'), review_client=sdk_client(career_review))
    snapshot = advisor.create_career_snapshot(service_clo_set, CareerCatalog().get('data-scientist'))
    snapshot, _ = advisor.review_snapshot(snapshot)
    if change == 'source': snapshot['clo_set']['courses'].clear()
    elif change == 'content': snapshot['career_profile']['content'] += '\nmodified'
    elif change == 'title': snapshot['career_profile']['title'] = 'Another role'
    elif change == 'codes': snapshot['career_profile']['role_codes'] = ['9.9']
    elif change == 'fingerprint': snapshot['fingerprints']['career_profile'] = '0'*64
    elif change == 'comparison': snapshot['comparison']['overview'] += 'modified'
    elif change == 'target_kind': snapshot['job_description'] = 'not a JD session'
    elif change == 'history': snapshot['messages'] = [{'role': 'user', 'content': 'incomplete'}]
    else: snapshot['messages'] = [{'role': 'user', 'content': 'Question'}, {'role': 'assistant', 'content': 'Answer', 'evidence': [{'course_code': 'TEST101', 'clo': 'CLO2'}]}]
    with pytest.raises(ComparisonError): advisor.validate_snapshot(snapshot)


def test_career_session_returns_detached_copies(service_clo_set):
    profile = CareerCatalog().get('data-scientist')
    advisor = AdvisorService()
    a = advisor.create_career_snapshot(service_clo_set, profile)
    b = advisor.create_career_snapshot(service_clo_set, CareerCatalog().get('data-analyst'))
    service_clo_set['courses'].clear()
    profile['role_codes'].clear()
    copy_a = advisor.validate_snapshot(a)
    copy_a['career_profile']['role_codes'].clear()
    assert a['clo_set']['courses'] and a['career_profile']['role_codes'] == ['1.1']
    assert a['session_id'] != b['session_id'] and a['fingerprints']['career_profile'] != b['fingerprints']['career_profile']


def test_career_preflight_rejects_budget_without_generation_or_mutation(service_clo_set, career_review, sdk_client):
    client = sdk_client(career_review)
    settings = LLMSettings(api_key='offline')
    client.responses.input_tokens.count.return_value.input_tokens = settings.context_window
    advisor = AdvisorService(review_settings=settings, review_client=client)
    snapshot = advisor.create_career_snapshot(service_clo_set, CareerCatalog().get('data-analyst'))
    before = copy.deepcopy(snapshot)
    with pytest.raises(ComparisonError): advisor.review_snapshot(snapshot)
    assert snapshot == before
    client.responses.parse.assert_not_called()
    assert client.responses.input_tokens.count.call_count == 1
