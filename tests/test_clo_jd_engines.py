import copy
import json
from types import SimpleNamespace

import pytest

from app.engines.chat import CLOChatSession, snapshot_fingerprints
from app.engines.errors import ComparisonAlreadyReadyError, ComparisonError, ComparisonNotReadyError
from app.engines.models import CLOJDComparison, validate_comparison, validate_clo_set
from app.engines.prompts import COMPARISON_INSTRUCTIONS, CHAT_INSTRUCTIONS
from app.llm import LLMSettings, request_structured_response
from app.services import AdvisorService

pytestmark = pytest.mark.usefixtures('service_offline')


def test_pending_requires_no_settings_and_ready_generation_only_once(service_clo_set, service_review, sdk_client):
    client = sdk_client(service_review)
    with CLOChatSession.from_data(service_clo_set, ' SQL\n') as session:
        assert session.export_snapshot()['version'] == 3
        with pytest.raises(ComparisonNotReadyError): session.send('SQL?')
        calls = []
        def generate(source, jd, settings, *, client=None):
            calls.append((source, jd)); return service_review
        session.run_initial_comparison(generate, LLMSettings(api_key='offline'))
        with pytest.raises(ComparisonAlreadyReadyError): session.run_initial_comparison(generate, LLMSettings(api_key='offline'))
        assert len(calls) == 1 and calls[0][1] == ' SQL\n'


def test_engine_payload_is_only_enriched_clos_jd_and_conversation(service_clo_set, service_review, service_reply, sdk_client):
    source = copy.deepcopy(service_clo_set)
    clients = [sdk_client(service_review), sdk_client(service_reply)]
    advisor = AdvisorService(review_settings=LLMSettings(api_key='offline', stage='review'), chat_settings=LLMSettings(api_key='offline', stage='chat'), review_client=clients[0], chat_client=clients[1])
    snapshot = advisor.create_snapshot(source, 'SQL JD')
    source['courses'][0]['clos'][0]['description'] = 'outside mutation'
    updated, comparison = advisor.review_snapshot(snapshot)
    assert snapshot['comparison'] is None
    request = clients[0].responses.parse.call_args.kwargs
    assert request['instructions'] == COMPARISON_INSTRUCTIONS
    assert [json.loads(m['content']) for m in request['input']] == [{'clo_set': service_clo_set}, {'job_description': 'SQL JD'}]
    for question in ['CLO nào liên quan?', 'Giải thích thêm.']:
        updated, _ = advisor.chat_snapshot(updated, question)
    request = clients[1].responses.parse.call_args.kwargs
    assert request['instructions'] == CHAT_INSTRUCTIONS
    context = json.loads(request['input'][1]['content'])
    assert context['initial_comparison']['comparison_type'] == 'course_jd_comparison'
    assert {(e['course_code'],e['clo']) for e in context['permitted_evidence']} == {('TEST101','CLO1')}
    assert 'clos' not in json.dumps(request['input'])
    assert all(c['description'] not in json.dumps(request['input']) for course in service_clo_set['courses'] for c in course['clos'])
    assert request['input'][-3]['content'] == 'CLO nào liên quan?'
    assert request['input'][-1]['content'] == 'Giải thích thêm.'
    assert len(updated['messages']) == 4 and clients[0].responses.parse.call_count == 1
    assert clients[1].responses.parse.call_count == 2
    raw = json.dumps(request['input'])
    for forbidden in ['metadata', 'achievement', 'grades', 'assessments', 'profile_id', 'access_token', 'academic']:
        assert forbidden not in raw


@pytest.mark.parametrize('field,value', [('score', 8), ('achievement', 'good'), ('metadata', {}), ('assessments', [])])
def test_text_only_contract_rejects_extra_fields(service_clo_set, field, value):
    source = copy.deepcopy(service_clo_set)
    source['courses'][0]['clos'][0][field] = value
    with pytest.raises(ComparisonError): validate_clo_set(source)


@pytest.mark.parametrize('change', ['kind','missing_evidence','not_evidenced_refs','unknown_course','wrong_clo','duplicate','metadata','old_type'])
def test_comparison_schema_and_course_scoped_evidence(service_clo_set, service_review, change):
    raw = copy.deepcopy(service_review); row = raw['requirement_reviews'][0]
    if change == 'kind': raw['comparison_type'] = 'other'
    elif change == 'missing_evidence': row['evidence'] = []
    elif change == 'not_evidenced_refs': row['coverage'] = 'not_evidenced'
    elif change == 'unknown_course': row['evidence'][0]['course_code'] = 'OTHER201'
    elif change == 'wrong_clo': row['evidence'][0]['clo'] = 'CLO999'
    elif change == 'duplicate': row['evidence'] *= 2
    elif change == 'metadata': row['evidence'] = [{'course_code':'TEST101','metadata_field':'tools'}]
    else: raw = {'review_type':'academic_knowledge_review', **{k:v for k,v in raw.items() if k!='comparison_type'}}
    with pytest.raises(ComparisonError): validate_comparison(raw, service_clo_set)


def test_no_requirements_and_real_absence_are_valid(service_clo_set, service_review):
    raw = copy.deepcopy(service_review)
    raw['requirement_reviews'][0].update(coverage='not_evidenced', evidence=[])
    assert validate_comparison(raw, service_clo_set)
    raw['requirement_reviews'] = []
    assert validate_comparison(raw, service_clo_set)


@pytest.mark.parametrize('change', ['v1','v2','id','fingerprint','clo','jd','pending_history','extra_key','history_order','history_evidence'])
def test_snapshot_v3_validation_and_tamper_rejection(service_clo_set, service_review, change):
    with CLOChatSession.from_data(service_clo_set, 'SQL', None if change == 'pending_history' else service_review) as session:
        snapshot = session.export_snapshot()
    if change in ['v1','v2']: snapshot['version'] = int(change[-1])
    elif change == 'id': snapshot['session_id'] = 'invalid'
    elif change == 'fingerprint': snapshot['fingerprints']['clo_set'] = '0'*64
    elif change == 'clo': snapshot['clo_set']['courses'][0]['clos'][0]['description'] += 'changed'
    elif change == 'jd': snapshot['job_description'] += '\n'
    elif change == 'extra_key': snapshot['api_key'] = 'must-not-persist'
    elif change == 'history_order': snapshot['messages'] = [{'role':'assistant','content':'Wrong order','evidence':[]}, {'role':'user','content':'SQL?'}]
    elif change == 'history_evidence': snapshot['messages'] = [{'role':'user','content':'SQL?'},{'role':'assistant','content':'bad','evidence':[{'course_code':'TEST101','clo':'CLO999'}]}]
    else: snapshot['messages'] = [{'role':'user','content':'unfinished'}]
    with pytest.raises(ComparisonError): CLOChatSession.from_snapshot(snapshot)


def test_restored_snapshot_is_detached_and_session_pairing_isolated(service_clo_set, service_review, service_reply, sdk_client):
    advisor = AdvisorService(review_settings=LLMSettings(api_key='offline'), chat_settings=LLMSettings(api_key='offline',stage='chat'), review_client=sdk_client(service_review), chat_client=sdk_client(service_reply))
    a, b = advisor.create_snapshot(service_clo_set, 'JD A'), advisor.create_snapshot(service_clo_set, 'JD B')
    restored = advisor.validate_snapshot(a); restored['clo_set']['courses'].clear()
    assert a['clo_set']['courses'] and a['fingerprints'] != b['fingerprints']
    a, _ = advisor.review_snapshot(a); a, _ = advisor.chat_snapshot(a,'Question A')
    assert not b['messages'] and b['comparison'] is None
    assert advisor.validate_snapshot(a) == a


@pytest.mark.parametrize('failure', ['incomplete','refusal','empty','invalid_schema','invalid_evidence','exception','interrupt'])
def test_chat_failure_never_commits_partial_state(service_clo_set, service_review, service_reply, sdk_client, failure):
    client = sdk_client(service_reply)
    if failure == 'incomplete': client.responses.parse.return_value.status = 'incomplete'
    elif failure == 'refusal': client.responses.parse.return_value.output = [SimpleNamespace(type='message',content=[SimpleNamespace(type='refusal')])]
    elif failure == 'empty': client.responses.parse.return_value.output_parsed = None
    elif failure == 'invalid_schema': client.responses.parse.return_value.output_parsed = {'reply':'x','evidence':[],'extra':True}
    elif failure == 'invalid_evidence': client.responses.parse.return_value.output_parsed = {'reply':'x','evidence':[{'course_code':'TEST101','clo':'missing'}]}
    elif failure == 'exception': client.responses.parse.side_effect = RuntimeError('mock failure')
    else: client.responses.parse.side_effect = KeyboardInterrupt()
    with CLOChatSession.from_data(service_clo_set, 'SQL', service_review, settings=LLMSettings(api_key='offline',stage='chat'),client=client) as session:
        before = session.export_snapshot()
        with pytest.raises((ComparisonError, RuntimeError, KeyboardInterrupt)): session.send('SQL?')
        assert session.export_snapshot() == before and client.responses.parse.call_count == 1


def test_context_and_turn_limits_fail_without_silent_truncation(service_clo_set, service_review, service_reply, sdk_client):
    client = sdk_client(service_reply); settings = LLMSettings(api_key='offline', stage='chat')
    with CLOChatSession.from_data(service_clo_set, 'SQL', service_review, settings=settings, client=client, max_turns=1,max_message_chars=4) as session:
        with pytest.raises(ComparisonError): session.send('12345')
        session.send('SQL?')
        with pytest.raises(ComparisonError): session.send('SQL?')
        assert client.responses.parse.call_count == 1
    client.responses.input_tokens.count.return_value.input_tokens = settings.context_window
    with CLOChatSession.from_data(service_clo_set, 'SQL', service_review, settings=settings,client=client) as session:
        with pytest.raises(ComparisonError): session.send('SQL?')
        assert not session.export_snapshot()['messages'] and client.responses.parse.call_count == 1


def test_runtime_does_not_import_retired_modules():
    import subprocess, sys
    code = 'import app.main,app.settings_diagnostics,examples.offline_demo,sys; assert not any("academic" in m or m=="scripts.clo_scoring" or m.startswith("archive.") for m in sys.modules)'
    subprocess.run([sys.executable,'-c',code],check=True)
