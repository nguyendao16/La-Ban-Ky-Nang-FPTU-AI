"""Persist real result content across fresh sessions without sharing history or capabilities."""
import copy
import json
import stat
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.engines.errors import ComparisonError
from app.engines.recommendations import recommendation_context
from app.jobs.review_worker import ReviewWorker
from app.services import AdvisorService
from app.services.errors import StorageIntegrityError
from app.services.result_cache import ResultCache
from examples.services_integration import mock_recommendation_response


@pytest.mark.parametrize('target_domain', ['jd', 'cwa'], indirect=True)
def test_disk_cache_reuses_both_stages_in_a_fresh_session(api_backend, queued_session, tmp_path,
                                                        sdk_client, monkeypatch):
    api = api_backend
    api.advisor._result_cache = ResultCache(tmp_path / 'cache')
    if api.domain == 'jd':
        api.review_client.responses.parse.return_value.output_parsed['requirement_reviews'][0].update(
            coverage='related', comment='Nội dung liên quan SQL nhưng chưa thể hiện tối ưu truy vấn.')
    worker = ReviewWorker(api.backend.jobs, api.advisor)
    try:
        assert worker.run_once() == queued_session['comparison_job']['job_id']
    finally:
        worker.close()
    saved = api.backend.sessions.get(queued_session['session_id'], queued_session['access_token'])['snapshot']
    rec_client = sdk_client({})
    rec_client.responses.parse.return_value = mock_recommendation_response(recommendation_context(saved))
    api.advisor._recommendation_client = rec_client
    recommendations = api.advisor.recommend_snapshot(saved)
    assert api.review_client.responses.parse.call_count == rec_client.responses.parse.call_count == 1

    # A new instance models a worker restart; no SDK client may be constructed on either hit.
    constructor = Mock(side_effect=AssertionError('Cache hit must not call OpenAI'))
    monkeypatch.setattr('app.llm.openai.OpenAI', constructor)
    with AdvisorService(review_settings=api.advisor._review_settings,
                        chat_settings=api.advisor._chat_options['settings'],
                        result_cache_dir=tmp_path / 'cache') as restored:
        fresh = (restored.create_career_snapshot(saved['clo_set'], saved['career_profile'])
                 if api.domain == 'cwa' else restored.create_snapshot(saved['clo_set'],
                    '#### **'+saved['job_description']+'**\n\n'))
        updated, response = restored.review_snapshot(fresh)
        assert updated['session_id'] != saved['session_id']
        assert updated['messages'] == [] and updated['comparison'] == saved['comparison']
        assert response.model_dump() == saved['comparison']
        assert restored.recommend_snapshot(updated) == recommendations
    constructor.assert_not_called()
    assert fresh['comparison'] is None  # No mutation of the caller's pending snapshot.
    for path in (tmp_path / 'cache').glob('*.json'):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        raw = path.read_text()
        assert queued_session['access_token'] not in raw
        assert saved['session_id'] not in raw


def test_cache_is_scoped_to_source_target_model_policy_and_comparison(tmp_path, service_clo_set):
    from app.llm import LLMSettings
    cache = ResultCache(tmp_path)
    settings = LLMSettings(api_key='not-persisted', stage='review')
    snapshot = {'clo_set': service_clo_set, 'job_description': 'SQL', 'comparison': None}
    key = cache.key('comparison', snapshot, settings)
    cache.put(key, {'example': 'saved'})
    changed_source = copy.deepcopy(snapshot)
    changed_source['clo_set']['courses'][0]['clos'][0]['description'] = 'Different course content'
    for changed in [changed_source, {**snapshot, 'job_description': 'SQL and MongoDB'}]:
        assert cache.get(cache.key('comparison', changed, settings)) is None
    other_model = replace(settings, model='gpt-5.4', context_window=None, temperature=None)
    assert cache.get(cache.key('comparison', snapshot, other_model)) is None
    assert cache.key('recommendations', {**snapshot, 'comparison': {'a': 1}}, settings) != cache.key(
        'recommendations', {**snapshot, 'comparison': {'a': 2}}, settings)
    cache.policy = 'updated-policy'
    assert cache.get(cache.key('comparison', snapshot, settings)) is None


def test_markdown_and_rendered_jd_share_cache_but_requirement_changes_do_not(tmp_path, service_clo_set):
    from app.llm import LLMSettings
    cache = ResultCache(tmp_path)
    settings = LLMSettings(api_key='offline', stage='review')
    jd = (Path(__file__).resolve().parents[1] / 'examples/ai_engineer_intern_jd.md').read_text()
    # Reproduce copying rendered Markdown: headings, bold and list markers disappear.
    plain = '\n'.join(line.removeprefix('## ').removeprefix('- ').replace('**', '')
                      for line in jd.splitlines() if line.strip())
    snapshot = {'clo_set': service_clo_set, 'job_description': jd, 'comparison': None}
    key = cache.key('comparison', snapshot, settings)
    cache.put(key, {'example': 'prepared'})
    for pasted in (plain, '#### '+jd, jd.replace('\n', '\r\n\r\n')):
        assert cache.get(cache.key('comparison', {**snapshot, 'job_description': pasted}, settings)) == {'example': 'prepared'}
    for changed in (plain.replace('SQL and MongoDB', 'SQL or MongoDB'),
                    plain.replace('is an advantage', 'is required'),
                    plain+' Five years of experience required.'):
        assert cache.get(cache.key('comparison', {**snapshot, 'job_description': changed}, settings)) is None


def test_corrupt_cache_and_invalid_cached_output_fail_without_generation(tmp_path, service_offline,
                                                                       service_clo_set, service_review):
    from app.llm import LLMSettings
    engine = Mock(side_effect=AssertionError('Invalid cache must not trigger inference'))
    advisor = AdvisorService(review_engine=engine, result_cache_dir=tmp_path,
                             review_settings=LLMSettings(api_key='offline', stage='review'))
    snapshot = advisor.create_snapshot(service_clo_set, 'SQL')
    key = advisor._result_cache.key('comparison', snapshot, advisor.prepare_review_settings())
    advisor._result_cache.put(key, service_review)
    path = tmp_path / f'{key}.json'
    record = json.loads(path.read_text())
    record['value']['overview'] = 'Modified without updating the digest'
    path.write_text(json.dumps(record))
    with pytest.raises(StorageIntegrityError):
        advisor.review_snapshot(snapshot)
    invalid = copy.deepcopy(service_review)
    invalid['radar']['overall_score'] = 6
    advisor._result_cache.put(key, invalid)
    with pytest.raises(ComparisonError):
        advisor.review_snapshot(snapshot)
    engine.assert_not_called()
