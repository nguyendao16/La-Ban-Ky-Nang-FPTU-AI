import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from app.services.errors import IncompatibleDatabaseError
from app.storage.migrations import migrate


def test_openapi_has_only_new_clo_jd_contracts(api_backend):
    schema = api_backend.client.get('/openapi.json').json()
    assert '/api/v1/profiles' not in schema['paths'] and '/api/v1/selections' in schema['paths']
    assert sum(m in ['get','post'] for route in schema['paths'].values() for m in route) == 12
    components = schema['components']['schemas']
    assert set(components['PublicEvidence']['properties']) == {'course_code'}
    assert not {'CLO', 'CLOSet', 'EvidenceReference'}.intersection(components)
    assert 'comparison' in components['SessionResponse']['properties']
    assert not any('Academic' in name or 'Grade' in name or name == 'ProfileRequest' for name in components)
    assert '/api/v1/career-profiles' in schema['paths']
    assert not {'coverage', 'score'}.intersection(components['PublicCareerFinding']['properties'])


def test_session_exposes_comparison_job_and_version_three(api_backend, queued_session):
    path = '/api/v1/advisor/sessions/' + queued_session['session_id']
    result = api_backend.client.get(path,headers=queued_session['headers']).json()
    assert result['comparison_job']['job_type'] == 'initial_comparison'
    assert not {'academic_state','initial_review','profile_id'}.intersection(result)
    stored = api_backend.backend.sessions.get(queued_session['session_id'],queued_session['access_token'])['snapshot']
    assert stored['version'] == 3 and set(stored['clo_set']) == {'courses'}
    assert set(stored['fingerprints']) == {'clo_set','jd'}


@pytest.mark.parametrize('version', [0,1,2])
def test_migration_entrypoint_also_refuses_old_schema(tmp_path, version):
    path = tmp_path/'old.sqlite3'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE profiles (id TEXT)')
        c.execute(f'PRAGMA user_version={version}')
    before = path.read_bytes()
    with sqlite3.connect(path) as c:
        with pytest.raises(IncompatibleDatabaseError): migrate(c)
    assert path.read_bytes() == before


def test_worker_cli_reports_old_database_without_dispatch_or_mutation(tmp_path):
    path = tmp_path/'old.sqlite3'
    with sqlite3.connect(path) as c: c.execute('CREATE TABLE profiles (id TEXT)')
    before = path.read_bytes()
    result = subprocess.run([sys.executable,'-m','app.jobs.worker_cli','--once'],
        env={**os.environ,'SKILLBRIDGE_DATABASE_PATH':str(path)},capture_output=True,text=True)
    assert result.returncode == 1
    error = json.loads(result.stdout)['error']
    assert error['code'] == 'incompatible_database' and 'Select a new CLO-JD SQLite path' in error['message']
    assert path.read_bytes() == before


def test_archived_sources_are_byte_identical_to_pre_refactor_manifest():
    directory = Path('archive/academic_v1')
    files = json.loads((directory/'manifest.json').read_text())['files']
    assert len(files) == 117
    for name, fingerprint in files.items():
        assert hashlib.sha256((directory/name).read_bytes()).hexdigest() == fingerprint, name
