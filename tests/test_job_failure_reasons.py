import copy
from types import SimpleNamespace

import pytest
import httpx
import openai

from app.engines.errors import ComparisonError
from app.jobs.review_worker import ReviewWorker


@pytest.mark.parametrize('failure,code', [
    ('output_limit', 'model_output_limit'),
    ('incomplete', 'model_response_incomplete'),
    ('refusal', 'model_refusal'),
    ('missing_output', 'missing_structured_output'),
    ('schema', 'invalid_structured_output'),
    ('evidence', 'invalid_evidence'),
    ('duplicate', 'invalid_evidence'),
    ('coverage', 'invalid_coverage'),
    ('private_text', 'private_source_disclosure'),
    ('unknown', 'generation_failed'),
    ('authentication', 'authentication_failed'),
    ('quota', 'quota_exhausted'),
    ('rate_limit', 'rate_limited'),
    ('provider', 'upstream_api_error'),
])
def test_jd_worker_records_safe_failure_reason_without_retry(api_backend, stored_clo_set, failure, code, caplog):
    response = api_backend.review_client.responses.parse.return_value
    raw = copy.deepcopy(response.output_parsed)
    row = raw['requirement_reviews'][0]
    secret = 'sk-secret-private-payload-that-must-never-be-persisted'
    if failure in {'output_limit', 'incomplete'}:
        response.status = 'incomplete'
        response.incomplete_details = SimpleNamespace(reason='max_output_tokens' if failure == 'output_limit' else secret)
    elif failure == 'refusal':
        response.output = [SimpleNamespace(type='message', content=[SimpleNamespace(type='refusal', refusal=secret)])]
    elif failure == 'missing_output':
        response.output_parsed = None
    elif failure == 'schema':
        raw['conclusion'] = {'untrusted': secret}
    elif failure == 'evidence':
        row['evidence'][0]['clo'] = secret
    elif failure == 'duplicate':
        row['evidence'] *= 2
    elif failure == 'coverage':
        row['evidence'] = []
    elif failure == 'private_text':
        source = copy.deepcopy(stored_clo_set['clo_set'])
        source['courses'][0]['clos'][0]['description'] = secret
        stored_clo_set = api_backend.backend.clo_sets.create('configured', ['TEST101'], source)
        raw['overview'] = secret
    elif failure in {'authentication', 'quota', 'rate_limit', 'provider'}:
        status = 401 if failure == 'authentication' else 400 if failure == 'provider' else 429
        cls = openai.AuthenticationError if status == 401 else openai.BadRequestError if status == 400 else openai.RateLimitError
        error_body = {'message': secret, 'code': 'insufficient_quota' if failure == 'quota' else 'other'}
        api_backend.review_client.responses.parse.side_effect = cls(secret,
            response=httpx.Response(status, request=httpx.Request('POST', 'https://example.invalid')),
            body=error_body)
    else:
        api_backend.review_client.responses.parse.side_effect = ComparisonError(secret)
    if failure != 'missing_output':
        response.output_parsed = raw
    queued_session = api_backend.backend.persistent.create_session(
        stored_clo_set['clo_set_id'], stored_clo_set['access_token'], 'SQL internship', 'failure-reason')
    worker = ReviewWorker(api_backend.backend.jobs, api_backend.advisor)
    try:
        worker.run_once()
        job = api_backend.backend.jobs.get(queued_session['comparison_job']['job_id'])
        assert job['status'] == 'failed'
        assert job['error_code'] == code
        assert job['attempt_count'] == 1
        assert secret not in str(job) and secret not in caplog.text
        stored = api_backend.backend.sessions.get(queued_session['session_id'], stored_clo_set['access_token'])
        assert stored['snapshot']['comparison'] is None and stored['revision'] == 0
        public = api_backend.client.get('/api/v1/advisor/sessions/' + queued_session['session_id'],
            headers={'Authorization': 'Bearer ' + stored_clo_set['access_token']})
        assert public.status_code == 200 and public.json()['status'] == 'failed'
        assert public.json()['comparison_job']['error_code'] == code
        assert secret not in public.text
        assert worker.run_once() is None
        assert api_backend.review_client.responses.parse.call_count == 1
    finally:
        worker.close()


def test_only_allowlisted_error_codes_are_persisted():
    from app.jobs.failures import classify_failure
    secret = 'sk-untrusted-error-code'
    for code in [secret, {}, None]:
        error = ComparisonError(secret, code=code)
        status, stored_code, message = classify_failure(error, 'inference')
        assert status == 'failed' and stored_code == 'generation_failed'
        assert secret not in message
    error = ComparisonError(secret, code='invalid_evidence')
    assert classify_failure(error, 'commit')[:2] == ('interrupted', 'result_not_committed')
    error.__cause__ = openai.APITimeoutError(request=httpx.Request('POST', 'https://example.invalid'))
    assert classify_failure(error, 'inference')[:2] == ('interrupted', 'remote_outcome_unknown')
