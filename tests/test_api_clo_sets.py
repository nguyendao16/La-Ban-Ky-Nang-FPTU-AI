import copy
import sqlite3
import hashlib

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.config import BackendSettings
from app.services import CLOSetService
from app.services.errors import IncompatibleDatabaseError
from app.storage.database import Database


def body():
    return {"curriculum_code": "configured", "selected_courses": ["TEST101"]}


def test_stored_set_equals_service_and_capability_is_only_returned_once(api_backend, stored_clo_set):
    result = api_backend.client.get('/api/v1/selections/' + stored_clo_set['clo_set_id'], headers={'Authorization': 'Bearer ' + stored_clo_set['access_token']})
    assert result.status_code == 200 and 'access_token' not in result.json()
    assert 'clo_set' not in result.json() and 'fingerprint' not in result.json()
    assert api_backend.backend.clo_sets.get(stored_clo_set['clo_set_id'],stored_clo_set['access_token'])['clo_set'] == CLOSetService(api_backend.catalog).build_clo_set(['TEST101'])
    assert result.json()['summary'] == {'course_count': 1}
    with api_backend.database.transaction() as c:
        row = dict(c.execute('SELECT * FROM clo_sets').fetchone())
        assert stored_clo_set['access_token'] not in str(row) and len(row['owner_hash']) == 64
        assert 'grades_json' not in row
    assert result.headers['cache-control'] == 'no-store'


@pytest.mark.parametrize('case', ['empty','duplicate','unknown','foreign','old_grades','old_profile'])
def test_rejected_input_creates_no_partial_rows(api_backend, case):
    value = body()
    if case == 'empty': value['selected_courses'] = []
    elif case == 'duplicate': value['selected_courses'] *= 2
    elif case == 'unknown': value['selected_courses'] = ['unknown']
    elif case == 'foreign': value['selected_courses'] += ['FOREIGN301']
    elif case == 'old_grades': value['grades'] = []
    else: value['profile_type'] = 'academic'
    response = api_backend.client.post('/api/v1/selections', json=value)
    assert response.status_code in [404,422]
    with api_backend.database.transaction() as c: assert c.execute('SELECT COUNT(*) FROM clo_sets').fetchone()[0] == 0


def test_immutable_versions_and_cross_capability_boundaries(api_backend, stored_clo_set):
    new = api_backend.client.post('/api/v1/selections', json=body()).json()
    assert new['selection_id'] != stored_clo_set['clo_set_id'] and new['selected_courses'] == stored_clo_set['selected_courses']
    path = '/api/v1/selections/' + stored_clo_set['clo_set_id']
    assert api_backend.client.get(path).status_code == 401
    assert api_backend.client.get(path, headers={'Authorization': 'Bearer ' + new['access_token']}).status_code == 403
    assert api_backend.client.post('/api/v1/profiles', json={}).status_code == 404
    with pytest.raises(sqlite3.IntegrityError), api_backend.database.transaction(write=True) as c:
        c.execute("UPDATE clo_sets SET curriculum_code='changed'")


def test_catalog_details_expose_clos_without_assessments(api_backend):
    result = api_backend.client.get('/api/v1/courses/TEST101').json()
    assert not {'clos','metadata','availability','assessments'}.intersection(result)
    (api_backend.catalog.courses_dir / 'TEST101/metadata.json').unlink()
    assert api_backend.client.post('/api/v1/selections', json=body()).status_code == 201


def test_body_limits_json_and_safe_error_responses(api_backend):
    client = api_backend.client
    assert client.post('/api/v1/selections', content='{"x":1,"x":2}', headers={'Content-Type':'application/json'}).status_code == 422
    assert client.post('/api/v1/selections', content='{"x":NaN}', headers={'Content-Type':'application/json'}).status_code == 422
    assert client.post('/api/v1/selections', json={'secret': 'x'*10000}).status_code == 413
    result = client.post('/api/v1/selections', json={'secret':'sk-do-not-echo'})
    assert result.status_code == 422 and 'sk-do-not-echo' not in result.text
    def chunks():
        yield b'{"message":"'; yield b'x'*5000; yield b'"}'
    assert client.post('/api/v1/selections', content=chunks(), headers={'Content-Type':'application/json'}).status_code == 413


def test_old_database_is_rejected_without_migration_or_reset(tmp_path, service_offline):
    path = tmp_path/'old.sqlite3'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE profiles (profile_id TEXT)')
        c.execute("INSERT INTO profiles VALUES ('preserved')")
        c.execute('PRAGMA user_version=1')
    before = path.read_bytes()
    with pytest.raises(IncompatibleDatabaseError, match='new CLO-JD SQLite path'): Database(path).initialize()
    with TestClient(create_app(BackendSettings(database_path=path))) as client:
        response = client.get('/api/v1/health')
        assert response.status_code == 503 and response.json()['error_code'] == 'incompatible_database'
        assert 'not migrated or reset' in response.json()['message']
    assert path.read_bytes() == before
    assert not path.with_name(path.name+'-wal').exists()
