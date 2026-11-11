"""Numbered idempotent initialization without destructive startup resets."""

from app.services.errors import IncompatibleDatabaseError

SCHEMA_VERSION = 2
APPLICATION_ID = 0x5342434A
JOB_TABLE_SQL = """CREATE TABLE jobs (
    job_id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(session_id),
    request_id TEXT NOT NULL REFERENCES requests(request_id),
    job_type TEXT NOT NULL CHECK(job_type IN ('initial_comparison','course_recommendations')),
    status TEXT NOT NULL CHECK(status IN ('queued','processing','succeeded','failed','interrupted')),
    created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, attempt_count INTEGER NOT NULL DEFAULT 0,
    error_code TEXT, error_message TEXT, lease_token TEXT, lease_generation INTEGER NOT NULL DEFAULT 0,
    lease_expires_at REAL, last_heartbeat TEXT, dispatched_at TEXT,
    recovery_log_json TEXT NOT NULL DEFAULT '[]', result_json TEXT, result_fingerprint TEXT,
    UNIQUE(session_id, job_type))"""
STATEMENTS = [
    """CREATE TABLE clo_sets (
        clo_set_id TEXT PRIMARY KEY, owner_hash TEXT NOT NULL UNIQUE,
        curriculum_code TEXT NOT NULL, selected_courses_json TEXT NOT NULL,
         clo_set_json TEXT NOT NULL, fingerprint TEXT NOT NULL,
        diagnostics_json TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TRIGGER immutable_clo_sets BEFORE UPDATE ON clo_sets BEGIN
        SELECT RAISE(ABORT, 'Comparison clo_set snapshots are immutable'); END""",
    """CREATE TABLE sessions (
        session_id TEXT PRIMARY KEY, clo_set_id TEXT NOT NULL REFERENCES clo_sets(clo_set_id),
        owner_hash TEXT NOT NULL, snapshot_json TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        lease_token TEXT, lease_generation INTEGER NOT NULL DEFAULT 0,
        lease_expires_at REAL, last_heartbeat TEXT, lease_operation_id TEXT)""",
    """CREATE TABLE requests (
        request_id TEXT PRIMARY KEY, owner_hash TEXT NOT NULL, scope TEXT NOT NULL, key_hash TEXT NOT NULL,
        request_fingerprint TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES sessions(session_id),
        status TEXT NOT NULL CHECK(status IN ('processing','succeeded','failed','interrupted')),
        response_json TEXT, turn_number INTEGER, created_at TEXT NOT NULL,
        finished_at TEXT, dispatched_at TEXT, error_code TEXT, error_message TEXT,
        UNIQUE(owner_hash, scope, key_hash))""",
    JOB_TABLE_SQL,
    "CREATE INDEX queued_jobs ON jobs(status, created_at, job_id)",
    "CREATE INDEX owned_sessions ON sessions(owner_hash, session_id)",
    "CREATE INDEX expiring_sessions ON sessions(lease_expires_at) WHERE lease_token IS NOT NULL",
    "CREATE UNIQUE INDEX committed_chat_turn ON requests(session_id, turn_number) WHERE turn_number IS NOT NULL",
    """CREATE TABLE workers (worker_id TEXT PRIMARY KEY, started_at TEXT NOT NULL,
        last_heartbeat TEXT NOT NULL, last_seen_epoch REAL NOT NULL, state TEXT NOT NULL)""",
]


def migrate(connection):
    connection.execute("BEGIN IMMEDIATE")
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        app_id = connection.execute("PRAGMA application_id").fetchone()[0]
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if (version not in (0, 1, SCHEMA_VERSION) or (version == 0 and tables)
                or (version in (1, SCHEMA_VERSION) and (app_id != APPLICATION_ID
                    or tables != {'clo_sets', 'sessions', 'jobs', 'requests', 'workers'}))):
            raise IncompatibleDatabaseError("Incompatible database. Select a new CLO-JD SQLite path; existing data was not migrated or reset.")
        if version == 0:
            for statement in STATEMENTS:
                connection.execute(statement)
        elif version == 1:
            # Only the recognized CLO/JD schema is upgraded; snapshots/ledgers stay byte-identical.
            columns = ('job_id,session_id,request_id,job_type,status,created_at,started_at,finished_at,'
                       'attempt_count,error_code,error_message,lease_token,lease_generation,lease_expires_at,'
                       'last_heartbeat,dispatched_at,recovery_log_json')
            connection.execute(JOB_TABLE_SQL.replace('CREATE TABLE jobs', 'CREATE TABLE jobs_v2'))
            connection.execute(f'INSERT INTO jobs_v2({columns}) SELECT {columns} FROM jobs')
            connection.execute('DROP TABLE jobs')
            connection.execute('ALTER TABLE jobs_v2 RENAME TO jobs')
            connection.execute('CREATE INDEX queued_jobs ON jobs(status, created_at, job_id)')
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.execute(f"PRAGMA application_id = {APPLICATION_ID}")
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
