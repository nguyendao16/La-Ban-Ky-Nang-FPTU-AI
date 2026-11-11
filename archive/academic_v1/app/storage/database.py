from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from scripts.academic_review import unique_json_fields


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def json_read(value):
    def invalid_constant(raw):
        raise ValueError("Nonfinite JSON constant")
    return json.loads(value, object_pairs_hook=unique_json_fields, parse_constant=invalid_constant)


def digest(value) -> str:
    canonical = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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

    def initialize(self):
        from .migrations import migrate
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
