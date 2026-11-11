"""Local infrastructure configuration; OpenAI settings stay in their engine."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class BackendSettings:
    database_path: Path = ROOT / "var/skillbridge.sqlite3"
    curriculum_mapping: dict[str, str] = field(default_factory=dict)
    default_curriculum: str | None = None
    max_turns: int = 20
    max_message_chars: int = 4000
    max_jd_chars: int = 100000
    max_body_bytes: int = 524288
    lease_seconds: float = 60
    heartbeat_interval: float = 10
    worker_poll_interval: float = 1
    cors_origins: tuple[str, ...] = ()

    def __post_init__(self):
        for name in ["max_turns", "max_message_chars", "max_jd_chars", "max_body_bytes"]:
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be a positive integer")
        for name in ["lease_seconds", "heartbeat_interval", "worker_poll_interval"]:
            value = getattr(self, name)
            if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a finite positive number")
        if self.heartbeat_interval >= self.lease_seconds / 2:
            raise ValueError("Heartbeat interval must be less than half the lease duration")
        if not isinstance(self.curriculum_mapping, dict) or any(
            not isinstance(k, str) or not k.strip() or not isinstance(v, str) or not v.strip()
            for k, v in self.curriculum_mapping.items()
        ):
            raise ValueError("Curriculum mapping must be an explicit JSON code/source-ID object")
        if self.curriculum_mapping and self.default_curriculum not in self.curriculum_mapping:
            raise ValueError("Default curriculum must be explicitly present in mapping")
        for origin in self.cors_origins:
            parsed = urlparse(origin)
            if origin == "*" or parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path:
                raise ValueError("CORS origins must be explicit HTTP(S) origins without paths")
        if str(self.database_path) == ":memory:":
            raise ValueError("Use a database file: independent connections cannot share :memory:")

    @classmethod
    def from_env(cls):
        prefix = "SKILLBRIDGE_"
        kwargs = {}
        for field_name, env_name, converter in [
            ("database_path", "DATABASE_PATH", Path), ("default_curriculum", "DEFAULT_CURRICULUM", str),
            ("max_turns", "MAX_TURNS", int), ("max_message_chars", "MAX_MESSAGE_CHARS", int),
            ("max_jd_chars", "MAX_JD_CHARS", int), ("max_body_bytes", "MAX_BODY_BYTES", int),
            ("lease_seconds", "LEASE_SECONDS", float), ("heartbeat_interval", "HEARTBEAT_INTERVAL", float),
            ("worker_poll_interval", "WORKER_POLL_INTERVAL", float),
        ]:
            if prefix + env_name in os.environ:
                kwargs[field_name] = converter(os.environ[prefix + env_name])
        if prefix + "CURRICULUM_MAPPING" in os.environ:
            kwargs["curriculum_mapping"] = json.loads(os.environ[prefix + "CURRICULUM_MAPPING"])
        if prefix + "CORS_ORIGINS" in os.environ:
            origins = json.loads(os.environ[prefix + "CORS_ORIGINS"])
            if not isinstance(origins, list) or any(not isinstance(x, str) for x in origins):
                raise ValueError("CORS_ORIGINS must be a JSON array of origins")
            kwargs["cors_origins"] = tuple(origins)
        return cls(**kwargs)
