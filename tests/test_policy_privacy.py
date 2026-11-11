"""Private scoring stays server-side; historic reads are filtered, never rewritten."""
import copy
import json

import pytest

from app.engines.career import validate_career_comparison
from app.engines.errors import ComparisonError
from app.engines.models import validate_comparison
from app.engines.prompts import SOURCE_RULES
from app.jobs.review_worker import ReviewWorker
from app.json_utils import digest, json_text
from app.public_view import comparison, discloses_policy, protect_text

pytestmark = pytest.mark.usefixtures('service_offline')

LEAKS = [
    'Trục này còn chịu tác động của yêu cầu bắt buộc 5 năm kinh nghiệm xử lý ảnh, nên điểm chỉ ở mức hỗ trợ gián tiếp.',
    'Yêu cầu bắt buộc tối thiểu 5 năm kinh nghiệm xử lý ảnh áp vào trục này. Vì vậy mức phù hợp bị giới hạn ở 1.0.',
    'Bối cảnh giả định: sinh viên, dưới 1 năm kinh nghiệm nghề nghiệp.',
    'Kết quả được đánh giá trong bối cảnh sinh viên.',
    'Người dùng là sinh viên.',
    'Diem tong bi gioi han o 1/5.',
    'Trần điểm nội bộ là 1/5.',
    'Điểm tổng tối đa 2/5 khi thiếu chức năng lõi.',
    'The overall score is capped at 1.0 because of the experience requirement.',
    'Trục này bị ảnh hưởng bởi yêu cầu kinh nghiệm.',
    'Vì thiếu kinh nghiệm nên mức phù hợp thấp.',
    'This axis is affected by the experience requirement.',
    'The experience requirement affects this axis.',
    'We assume the user is a student with less than one year of experience.',
    'Giả định kinh nghiệm nghề nghiệp của người dùng còn ít.',
    '1–2 năm → 3/5; 2–3 năm → 2/5; 3 năm → 1/5.',
    'Theo bảng quy đổi, kinh nghiệm áp dụng trần 1/5.',
    'RADAR_SCORING_RULES: DEPTH CEILINGS.',
    ' '.join(SOURCE_RULES.split()[:35]),
]


@pytest.mark.parametrize('text', LEAKS)
def test_private_policy_patterns_are_blocked_and_projected_to_neutral_text(text):
    assert discloses_policy(text)
    public = protect_text(text, {'courses': []})
    assert public != text and not discloses_policy(public)


@pytest.mark.parametrize('text', [
    'JD yêu cầu tối thiểu 5 năm kinh nghiệm xử lý ảnh; dữ liệu học phần chưa chứng minh kinh nghiệm thực tế.',
    'Môn học có hỗ trợ nội dung trực tiếp, nhưng chưa thể hiện thực thi độc lập trong bối cảnh nghề nghiệp.',
    'Điểm tổng là 1/5. Trục dữ liệu đạt 2/5.',
    'Điểm tổng là 1/5. JD nhận ứng viên có tối đa 2 năm kinh nghiệm.',
    'Nội dung học phần hiện có chưa bao phủ nội dung này.',
    'JD yêu cầu chứng chỉ IELTS với điểm tối thiểu 6.5 và GPA 3.0/4.',
    'JD nhận ứng viên mới tốt nghiệp với dưới 1 năm kinh nghiệm.',
    'Tôi không cung cấp hướng dẫn nội bộ. Tôi có thể giải thích kết quả và khoảng trống chuyên môn.',
])
def test_public_target_requirements_results_and_professional_gaps_remain_allowed(text):
    assert not discloses_policy(text)
    assert protect_text(text, {'courses': []}) == text


@pytest.mark.parametrize('variant', [str.upper, lambda text: text.replace(' ', '\n'), lambda text: text.replace('điểm', 'đi\u200bểm')])
def test_private_text_normalization_handles_case_spacing_and_format_characters(variant):
    assert discloses_policy(variant('Trần điểm nội bộ là 1/5.'))


@pytest.mark.parametrize('domain', ['jd', 'cwa'])
@pytest.mark.parametrize('field', ['overview', 'conclusion', 'title', 'comment', 'overall_comment', 'axis_name', 'axis_description', 'axis_comment'])
def test_all_generated_prose_fields_are_guarded_while_legacy_projection_keeps_scores(
        service_clo_set, service_review, career_review, domain, field):
    raw = copy.deepcopy(service_review if domain == 'jd' else career_review)
    validate = validate_comparison if domain == 'jd' else validate_career_comparison
    row = raw['requirement_reviews'][0] if domain == 'jd' else raw['related_content'][0]
    if field in {'overview', 'conclusion'}: target, key = raw, field
    elif field == 'title': target, key = row, 'jd_requirement' if domain == 'jd' else 'title'
    elif field == 'comment': target, key = row, 'comment'
    elif field == 'overall_comment': target, key = raw['radar'], field
    else: target, key = raw['radar']['axes'][0], field.removeprefix('axis_')
    target[key] = 'Trần điểm nội bộ là 1/5.'
    before = copy.deepcopy(raw)
    with pytest.raises(ComparisonError) as caught:
        validate(raw, service_clo_set, require_radar=True)
    assert caught.value.code == 'private_policy_disclosure'
    legacy = validate(raw, service_clo_set)
    public = comparison(legacy.model_dump(), service_clo_set)
    assert 'Trần điểm' not in json.dumps(public, ensure_ascii=False)
    assert public['radar']['overall_score'] == before['radar']['overall_score']
    assert [a['score'] for a in public['radar']['axes']] == [a['score'] for a in before['radar']['axes']]
    assert public['radar']['axes'][0]['evidence'] == [{'course_code': 'TEST101'}]
    assert raw == before


@pytest.mark.parametrize('target_domain', ['jd', 'cwa'], indirect=True)
def test_worker_disclosure_fails_once_without_commit_or_leaking_diagnostics(api_backend, queued_session, caplog):
    raw = copy.deepcopy(api_backend.review_client.responses.parse.return_value.output_parsed)
    raw['conclusion'] = LEAKS[0]
    api_backend.review_client.responses.parse.return_value.output_parsed = raw
    sessions = api_backend.backend.sessions
    before = sessions.get(queued_session['session_id'], queued_session['access_token'])
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor)
    try:
        worker.run_once()
        assert worker.run_once() is None
    finally: worker.close()
    after = sessions.get(queued_session['session_id'], queued_session['access_token'])
    assert after['snapshot'] == before['snapshot'] and after['revision'] == before['revision']
    assert after['job']['status'] == 'failed' and after['job']['attempt_count'] == 1
    assert after['job']['error_code'] == 'private_policy_disclosure'
    assert LEAKS[0] not in str(after['job']) + caplog.text
    assert api_backend.review_client.responses.parse.call_count == 1


@pytest.mark.parametrize('target_domain', ['jd', 'cwa'], indirect=True)
def test_chat_disclosure_rolls_back_and_same_key_replay_never_regenerates(api_backend, ready_session):
    api_backend.chat_client.responses.parse.return_value.output_parsed = {'reply': LEAKS[1], 'evidence': []}
    before = api_backend.backend.sessions.get(ready_session['session_id'], ready_session['access_token'])
    path = '/api/v1/advisor/sessions/' + ready_session['session_id'] + '/messages'
    headers = {**ready_session['headers'], 'Idempotency-Key': 'private-chat'}
    for _ in range(2):
        response = api_backend.client.post(path, headers=headers, json={'message': 'Giải thích kết quả'})
        assert response.status_code == 502 and LEAKS[1] not in response.text
    after = api_backend.backend.sessions.get(ready_session['session_id'], ready_session['access_token'])
    assert after['snapshot'] == before['snapshot'] and after['revision'] == before['revision']
    assert api_backend.client.get(path, headers=headers).json()['turns'] == []
    assert api_backend.chat_client.responses.parse.call_count == 1
    with api_backend.database.transaction() as connection:
        row = connection.execute("SELECT error_code,error_message FROM requests WHERE scope LIKE 'chat:%'").fetchone()
    assert row['error_code'] == 'private_policy_disclosure' and LEAKS[1] not in row['error_message']


@pytest.mark.parametrize('target_domain', ['jd', 'cwa'], indirect=True)
def test_legacy_get_replay_history_and_chat_context_are_filtered_without_rewriting_storage(api_backend, ready_session):
    path = '/api/v1/advisor/sessions/' + ready_session['session_id']
    headers = {**ready_session['headers'], 'Idempotency-Key': 'historic-reply'}
    first = api_backend.client.post(path + '/messages', headers=headers, json={'message': 'SQL?'})
    assert first.status_code == 200
    snapshot = api_backend.backend.sessions.get(ready_session['session_id'], ready_session['access_token'])['snapshot']
    snapshot['comparison']['conclusion'] = LEAKS[0]
    snapshot['comparison']['radar']['overall_comment'] = LEAKS[2]
    snapshot['fingerprints']['comparison'] = digest(snapshot['comparison'])
    snapshot['messages'][1]['content'] = LEAKS[1]
    cached = {**first.json(), 'reply': LEAKS[1], 'evidence': [{'course_code': 'TEST101', 'clo': 'CLO1'}]}
    with api_backend.database.transaction(write=True) as connection:
        connection.execute('UPDATE sessions SET snapshot_json=? WHERE session_id=?', (json_text(snapshot), ready_session['session_id']))
        connection.execute("UPDATE requests SET response_json=? WHERE session_id=? AND scope LIKE 'chat:%'", (json_text(cached), ready_session['session_id']))
    stored = api_backend.backend.sessions.get(ready_session['session_id'], ready_session['access_token'])
    report = api_backend.client.get(path, headers=headers)
    replay = api_backend.client.post(path + '/messages', headers=headers, json={'message': 'SQL?'})
    history = api_backend.client.get(path + '/messages', headers=headers)
    for response in (report, replay, history):
        assert response.status_code == 200
        assert all(leak not in response.text for leak in LEAKS[:3])
    assert replay.json()['message_id'] == first.json()['message_id']
    assert report.json()['comparison']['radar']['overall_score'] == snapshot['comparison']['radar']['overall_score']
    assert history.json()['turns'][0]['reply'] == replay.json()['reply']
    assert api_backend.backend.sessions.get(ready_session['session_id'], ready_session['access_token']) == stored
    assert api_backend.chat_client.responses.parse.call_count == 1
    response = api_backend.client.post(path + '/messages', headers={**headers, 'Idempotency-Key': 'safe-follow-up'}, json={'message': 'Giải thích nội dung môn'})
    assert response.status_code == 200
    messages = api_backend.chat_client.responses.parse.call_args.kwargs['input']
    context = json.dumps(messages, ensure_ascii=False)
    assert all(leak not in context for leak in LEAKS[:3])
    current = api_backend.backend.sessions.get(ready_session['session_id'], ready_session['access_token'])
    assert current['snapshot']['comparison'] == snapshot['comparison']
    assert current['snapshot']['fingerprints'] == snapshot['fingerprints']
    assert current['snapshot']['messages'][:2] == snapshot['messages']
    assert api_backend.review_client.responses.parse.call_count == 1
