from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover - optional dependency fallback
    def load_dotenv() -> None:
        return None


@dataclass(frozen=True)
class AppConfig:
    app_env: str
    database_path: Path
    compliance_reference: str
    spam_ruleset_version: str
    raw_retention_days: int
    execution_mode: str
    api_daily_quota: int
    api_failover_threshold: float
    youtube_api_key: str
    youtube_api_keys: list[str]
    hash_salt: str
    local_auth_users: dict[str, str]


ALLOWED_EXECUTION_MODES = {"auto", "api_only", "playwright_only"}


def _parse_auth_users(value: str) -> dict[str, str]:
    users: dict[str, str] = {}
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            continue
        username, password = part.split(":", 1)
        users[username.strip()] = password.strip()
    return users


def _parse_api_keys(keys_value: str, single_key: str) -> list[str]:
    keys: list[str] = []
    for part in (keys_value or "").split(","):
        key = part.strip()
        if key:
            keys.append(key)
    if not keys and single_key.strip():
        keys.append(single_key.strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def load_config() -> AppConfig:
    load_dotenv()

    execution_mode = os.getenv("EXECUTION_MODE", "auto").strip()
    if execution_mode not in ALLOWED_EXECUTION_MODES:
        raise ValueError(
            f"Invalid EXECUTION_MODE={execution_mode}. Must be one of {sorted(ALLOWED_EXECUTION_MODES)}"
        )

    database_path = Path(os.getenv("DATABASE_PATH", "data/youtube_comments.db"))
    compliance_reference = os.getenv(
        "COMPLIANCE_REFERENCE", "IRB: IRB-2026-045 (University X)"
    ).strip()

    return AppConfig(
        app_env=os.getenv("APP_ENV", "dev").strip(),
        database_path=database_path,
        compliance_reference=compliance_reference,
        spam_ruleset_version=os.getenv("SPAM_RULESET_VERSION", "v1.0.0").strip(),
        raw_retention_days=int(os.getenv("RAW_RETENTION_DAYS", "180")),
        execution_mode=execution_mode,
        api_daily_quota=int(os.getenv("API_DAILY_QUOTA", "10000")),
        api_failover_threshold=float(os.getenv("API_FAILOVER_THRESHOLD", "0.90")),
        youtube_api_key=os.getenv("YOUTUBE_API_KEY", "").strip(),
        youtube_api_keys=_parse_api_keys(
            os.getenv("YOUTUBE_API_KEYS", "").strip(),
            os.getenv("YOUTUBE_API_KEY", "").strip(),
        ),
        hash_salt=os.getenv("HASH_SALT", "").strip(),
        local_auth_users=_parse_auth_users(
            os.getenv("LOCAL_AUTH_USERS", "annotator_a:change_me,annotator_b:change_me")
        ),
    )
