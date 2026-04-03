from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from . import __version__
from .config import AppConfig


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _schema_sql() -> str:
    schema_path = Path(__file__).with_name("schema.sql")
    return schema_path.read_text(encoding="utf-8")


@contextmanager
def get_connection(db_path: Path) -> Iterator[sqlite3.Connection]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database(config: AppConfig) -> None:
    with get_connection(config.database_path) as conn:
        conn.executescript(_schema_sql())
        _ensure_schema_migrations(conn)


def _ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    run_columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(runs)").fetchall()
    }
    if "content_type" not in run_columns:
        conn.execute("ALTER TABLE runs ADD COLUMN content_type TEXT")
    if "target_file" not in run_columns:
        conn.execute("ALTER TABLE runs ADD COLUMN target_file TEXT")
    if "target_count_requested" not in run_columns:
        conn.execute("ALTER TABLE runs ADD COLUMN target_count_requested INTEGER")
    if "study_profile_name" not in run_columns:
        conn.execute("ALTER TABLE runs ADD COLUMN study_profile_name TEXT")
    if "run_payload_json" not in run_columns:
        conn.execute("ALTER TABLE runs ADD COLUMN run_payload_json TEXT")

    channel_columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(channels)").fetchall()
    }
    if "no_shorts_available" not in channel_columns:
        conn.execute(
            """
            ALTER TABLE channels
            ADD COLUMN no_shorts_available INTEGER NOT NULL DEFAULT 0
            CHECK(no_shorts_available IN (0,1))
            """
        )

    video_columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(videos)").fetchall()
    }
    if "collection_engine" not in video_columns:
        conn.execute(
            """
            ALTER TABLE videos
            ADD COLUMN collection_engine TEXT
            CHECK(collection_engine IN ('api','ytdlp','playwright'))
            """
        )
    if "comments_scanned" not in video_columns:
        conn.execute("ALTER TABLE videos ADD COLUMN comments_scanned INTEGER")
    if "comments_saved" not in video_columns:
        conn.execute("ALTER TABLE videos ADD COLUMN comments_saved INTEGER")
    if "comments_filtered" not in video_columns:
        conn.execute("ALTER TABLE videos ADD COLUMN comments_filtered INTEGER")
    if "failure_reason" not in video_columns:
        conn.execute("ALTER TABLE videos ADD COLUMN failure_reason TEXT")

    annotation_columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(annotations)").fetchall()
    }
    if "extra_codes" not in annotation_columns:
        conn.execute(
            """
            ALTER TABLE annotations
            ADD COLUMN extra_codes TEXT
            """
        )
    if "other_flag" not in annotation_columns:
        conn.execute(
            """
            ALTER TABLE annotations
            ADD COLUMN other_flag INTEGER NOT NULL DEFAULT 0
            CHECK(other_flag IN (0,1))
            """
        )
    if "other_text" not in annotation_columns:
        conn.execute(
            """
            ALTER TABLE annotations
            ADD COLUMN other_text TEXT
            """
        )
    if "workflow_mode" not in annotation_columns:
        conn.execute("ALTER TABLE annotations ADD COLUMN workflow_mode TEXT")
    if "triage_bucket" not in annotation_columns:
        conn.execute("ALTER TABLE annotations ADD COLUMN triage_bucket TEXT")
    if "triage_score" not in annotation_columns:
        conn.execute("ALTER TABLE annotations ADD COLUMN triage_score REAL")
    if "priority_bucket" not in annotation_columns:
        conn.execute("ALTER TABLE annotations ADD COLUMN priority_bucket TEXT")
    if "priority_score" not in annotation_columns:
        conn.execute("ALTER TABLE annotations ADD COLUMN priority_score REAL")
    if "heuristic_language" not in annotation_columns:
        conn.execute("ALTER TABLE annotations ADD COLUMN heuristic_language TEXT")
    if "low_info_noise" not in annotation_columns:
        conn.execute("ALTER TABLE annotations ADD COLUMN low_info_noise INTEGER")
    if "comment_ai_signal" not in annotation_columns:
        conn.execute("ALTER TABLE annotations ADD COLUMN comment_ai_signal INTEGER")
    if "video_ai_signal" not in annotation_columns:
        conn.execute("ALTER TABLE annotations ADD COLUMN video_ai_signal INTEGER")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS study_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            owner TEXT NOT NULL,
            description TEXT,
            profile_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(owner, name)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_study_profiles_owner ON study_profiles(owner)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS evidence_freezes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            notes TEXT,
            run_ids_json TEXT NOT NULL,
            summary_json TEXT NOT NULL,
            prevalence_overall_json TEXT NOT NULL,
            prevalence_by_run_niche_json TEXT NOT NULL,
            UNIQUE(created_by, name)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_freezes_owner ON evidence_freezes(created_by)")


def create_run(
    conn: sqlite3.Connection,
    config: AppConfig,
    notes: str | None = None,
    *,
    content_type: str | None = None,
    target_file: str | None = None,
    target_count_requested: int | None = None,
    study_profile_name: str | None = None,
    run_payload: dict[str, Any] | None = None,
) -> int:
    run_uuid = str(uuid.uuid4())
    cur = conn.execute(
        """
        INSERT INTO runs (
            run_uuid, started_at, status, execution_mode, run_truncated,
            spam_ruleset_version, compliance_reference, api_quota_limit,
            api_failover_threshold, app_version, content_type, target_file,
            target_count_requested, study_profile_name, run_payload_json, notes
        ) VALUES (?, ?, 'running', ?, 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_uuid,
            utc_now_iso(),
            config.execution_mode,
            config.spam_ruleset_version,
            config.compliance_reference,
            config.api_daily_quota,
            config.api_failover_threshold,
            __version__,
            content_type,
            target_file,
            int(target_count_requested) if target_count_requested is not None else None,
            study_profile_name,
            json.dumps(run_payload, ensure_ascii=True) if run_payload is not None else None,
            notes,
        ),
    )
    return int(cur.lastrowid)


def finalize_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    status: str,
    run_truncated: bool = False,
    api_units_used: int = 0,
    api_comment_count: int = 0,
    playwright_comment_count: int = 0,
) -> None:
    conn.execute(
        """
        UPDATE runs
        SET ended_at = ?,
            status = ?,
            run_truncated = ?,
            api_units_used = ?,
            api_comment_count = ?,
            playwright_comment_count = ?
        WHERE id = ?
        """,
        (
            utc_now_iso(),
            status,
            int(run_truncated),
            api_units_used,
            api_comment_count,
            playwright_comment_count,
            run_id,
        ),
    )


def upsert_channel(
    conn: sqlite3.Connection,
    *,
    channel_id: str,
    channel_url: str,
    niche: str,
    coverage_shortfall: bool = False,
    no_shorts_available: bool = False,
    extraction_failed: bool = False,
) -> int:
    conn.execute(
        """
        INSERT INTO channels (
            channel_id, channel_url, niche, coverage_shortfall, no_shorts_available, extraction_failed, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(channel_id)
        DO UPDATE SET
            channel_url = excluded.channel_url,
            niche = excluded.niche,
            coverage_shortfall = excluded.coverage_shortfall,
            no_shorts_available = excluded.no_shorts_available,
            extraction_failed = excluded.extraction_failed
        """,
        (
            channel_id,
            channel_url,
            niche,
            int(coverage_shortfall),
            int(no_shorts_available),
            int(extraction_failed),
            utc_now_iso(),
        ),
    )
    row = conn.execute("SELECT id FROM channels WHERE channel_id = ?", (channel_id,)).fetchone()
    if row is None:
        raise RuntimeError("Failed to upsert channel")
    return int(row["id"])


def insert_video(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    channel_db_id: int,
    video_id: str,
    video_url: str,
    title: str,
    description: str,
    published_at: str,
    upload_index: int,
    comment_status: str,
    view_count: int | None,
    disclosure_quality: int | None,
    collection_engine: str | None,
    comments_scanned: int | None,
    comments_saved: int | None,
    comments_filtered: int | None,
    failure_reason: str | None,
    extraction_failed: bool,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO videos (
            video_id, run_id, channel_db_id, video_url, title, description,
            published_at, upload_index, comment_status, view_count,
            disclosure_quality, collection_engine, comments_scanned, comments_saved,
            comments_filtered, failure_reason, extracted_at, extraction_failed
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            video_id,
            run_id,
            channel_db_id,
            video_url,
            title,
            description,
            published_at,
            upload_index,
            comment_status,
            view_count,
            disclosure_quality,
            collection_engine,
            comments_scanned,
            comments_saved,
            comments_filtered,
            failure_reason,
            utc_now_iso(),
            int(extraction_failed),
        ),
    )
    return int(cur.lastrowid)


def insert_comment(
    conn: sqlite3.Connection,
    *,
    run_id: int,
    channel_db_id: int,
    video_db_id: int,
    comment_id: str | None,
    commenter_hash_id: str,
    raw_text: str,
    cleaned_text: str,
    like_count: int,
    reply_count: int,
    published_at: str,
    language: str,
    comment_rank: int,
    is_spam: bool,
    is_template: bool,
    is_duplicate: bool,
    spam_rule_hits: list[str],
    source_engine: str,
) -> int:
    cur = conn.execute(
        """
        INSERT INTO comments (
            run_id, channel_db_id, video_db_id, comment_id, commenter_hash_id,
            raw_text, cleaned_text, like_count, reply_count, published_at,
            language, comment_rank, is_spam, is_template, is_duplicate,
            spam_rule_hits, source_engine, extraction_ts
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            channel_db_id,
            video_db_id,
            comment_id,
            commenter_hash_id,
            raw_text,
            cleaned_text,
            like_count,
            reply_count,
            published_at,
            language,
            comment_rank,
            int(is_spam),
            int(is_template),
            int(is_duplicate),
            json.dumps(spam_rule_hits, ensure_ascii=True),
            source_engine,
            utc_now_iso(),
        ),
    )
    return int(cur.lastrowid)


def insert_qa_report(conn: sqlite3.Connection, run_id: int, payload: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO qa_reports (run_id, created_at, payload_json) VALUES (?, ?, ?)",
        (run_id, utc_now_iso(), json.dumps(payload, ensure_ascii=True)),
    )
