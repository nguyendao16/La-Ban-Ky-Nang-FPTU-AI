from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from app.json_utils import digest, json_read, json_text
from app.services.errors import IncompatibleDatabaseError


def token_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def utc_timestamp(now: float) -> str:
    return datetime.fromtimestamp(now, timezone.utc).isoformat(timespec="microseconds")


class Database:
    """Each operation owns its connection; inference never owns a transaction."""

    def __init__(self, path: Path | str, *, clock=time.time, lease_seconds=60):
        self.path = Path(path)
        self.clock = clock
        self.lease_seconds = lease_seconds

    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _check_domain(self):
        # Read-only inspection precedes WAL/migrations: never rewrite an old DB.
        from .migrations import APPLICATION_ID, SCHEMA_VERSION
        if not self.path.is_file() or self.path.stat().st_size == 0:
            return
        connection = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            app_id = connection.execute("PRAGMA application_id").fetchone()[0]
            if not tables and version == 0 and app_id == 0:
                return
            if (app_id != APPLICATION_ID or version not in (1, SCHEMA_VERSION)
                    or tables != {"clo_sets", "sessions", "jobs", "requests", "workers"}):
                raise IncompatibleDatabaseError("Incompatible database. Select a new CLO-JD SQLite path; existing data was not migrated or reset.")
        finally:
            connection.close()

    def initialize(self):
        from .migrations import migrate
        self._check_domain()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        connection = self.connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            migrate(connection)
        finally:
            connection.close()

    @contextmanager
    def transaction(self, *, write=False):
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
