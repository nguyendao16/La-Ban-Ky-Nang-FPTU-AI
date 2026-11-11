"""Numbered idempotent initialization without destructive startup resets."""

SCHEMA_VERSION = 1
STATEMENTS = [
    """CREATE TABLE profiles (
        profile_id TEXT PRIMARY KEY, owner_hash TEXT NOT NULL UNIQUE,
        curriculum_code TEXT NOT NULL, selected_courses_json TEXT NOT NULL,
        grades_json TEXT NOT NULL, profile_json TEXT NOT NULL, fingerprint TEXT NOT NULL,
        diagnostics_json TEXT NOT NULL, created_at TEXT NOT NULL)""",
    """CREATE TRIGGER immutable_profiles BEFORE UPDATE ON profiles BEGIN
        SELECT RAISE(ABORT, 'Academic profile snapshots are immutable'); END""",
    """CREATE TABLE sessions (
        session_id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(profile_id),
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
    """CREATE TABLE jobs (
        job_id TEXT PRIMARY KEY, session_id TEXT NOT NULL UNIQUE REFERENCES sessions(session_id),
        request_id TEXT NOT NULL REFERENCES requests(request_id), job_type TEXT NOT NULL CHECK(job_type='initial_review'),
        status TEXT NOT NULL CHECK(status IN ('queued','processing','succeeded','failed','interrupted')),
        created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, attempt_count INTEGER NOT NULL DEFAULT 0,
        error_code TEXT, error_message TEXT, lease_token TEXT, lease_generation INTEGER NOT NULL DEFAULT 0,
        lease_expires_at REAL, last_heartbeat TEXT, dispatched_at TEXT,
        recovery_log_json TEXT NOT NULL DEFAULT '[]')""",
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
        if version > SCHEMA_VERSION:
            raise RuntimeError("Database schema is newer than this application")
        if version == 0:
            for statement in STATEMENTS:
                connection.execute(statement)
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.execute("COMMIT")
    except BaseException:
        connection.execute("ROLLBACK")
        raise
