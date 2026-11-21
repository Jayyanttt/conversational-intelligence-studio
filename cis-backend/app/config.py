"""Environment-driven configuration. Secrets never appear in repr/logs."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ApiKey:
    key_id: str
    secret: str = field(repr=False)  # never printed


@dataclass(frozen=True)
class Settings:
    api_keys: tuple[ApiKey, ...]
    database_path: str
    allowed_origins: tuple[str, ...]
    enable_failure_simulation: bool
    cache_enabled: bool
    model: str


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_api_keys(raw: str | None) -> tuple[ApiKey, ...]:
    """Comma-separated keys -> key_1, key_2, ... in order. Blanks are skipped."""
    parts = [p.strip() for p in (raw or "").split(",")]
    secrets = [p for p in parts if p]
    return tuple(ApiKey(key_id=f"key_{i}", secret=s) for i, s in enumerate(secrets, start=1))


def parse_database_path(url: str) -> str:
    """sqlite:////data/app.db -> /data/app.db ; sqlite:///./app.db -> ./app.db"""
    prefix = "sqlite:///"
    if not url.startswith(prefix):
        raise ValueError("DATABASE_URL must start with 'sqlite:///'")
    path = url[len(prefix):]
    if not path or path == ":memory:":
        raise ValueError("DATABASE_URL must point to a file")
    return path


def parse_origins(raw: str | None) -> tuple[str, ...]:
    return tuple(o.strip() for o in (raw or "").split(",") if o.strip())


def load_settings() -> Settings:
    return Settings(
        api_keys=parse_api_keys(os.getenv("LLM_API_KEYS")),
        database_path=parse_database_path(os.getenv("DATABASE_URL", "sqlite:///./data/app.db")),
        allowed_origins=parse_origins(os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")),
        enable_failure_simulation=_truthy(os.getenv("ENABLE_FAILURE_SIMULATION"), False),
        cache_enabled=_truthy(os.getenv("CACHE_ENABLED"), True),
        model=os.getenv("LLM_MODEL", "gemini/gemini-2.0-flash"),
    )
