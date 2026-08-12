from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


DEFAULT_DB_PATH = Path("data/compliance/compliance_validation.db")


def utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def new_uuid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _schema_sql() -> str:
    return Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")


@contextmanager
def get_connection(db_path: Path = DEFAULT_DB_PATH) -> Iterator[sqlite3.Connection]:
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


def init_database(db_path: Path = DEFAULT_DB_PATH) -> None:
    with get_connection(db_path) as conn:
        conn.executescript(_schema_sql())
        _ensure_schema_migrations(conn)


def _ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    _ensure_human_review_columns(conn)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_uuid TEXT NOT NULL UNIQUE,
            dataset_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            reviewer_id TEXT NOT NULL,
            queue_name TEXT NOT NULL,
            blind_mode INTEGER NOT NULL DEFAULT 1 CHECK(blind_mode IN (0,1)),
            rubric_version TEXT NOT NULL DEFAULT 'compliance-rubric-v1',
            status TEXT NOT NULL DEFAULT 'active'
                CHECK(status IN ('active','completed','archived')),
            notes TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(dataset_id, name),
            FOREIGN KEY(dataset_id) REFERENCES datasets(id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS review_assignment_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            item_status TEXT NOT NULL DEFAULT 'pending'
                CHECK(item_status IN ('pending','in_progress','completed','deferred','skipped')),
            assigned_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            defer_reason TEXT,
            skip_reason TEXT,
            last_review_id INTEGER,
            UNIQUE(assignment_id, material_id),
            FOREIGN KEY(assignment_id) REFERENCES review_assignments(id),
            FOREIGN KEY(material_id) REFERENCES materials(id),
            FOREIGN KEY(last_review_id) REFERENCES human_reviews(id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_review_assignments_dataset ON review_assignments(dataset_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_review_assignment_items_assignment ON review_assignment_items(assignment_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_review_assignment_items_status ON review_assignment_items(item_status)")


def _ensure_human_review_columns(conn: sqlite3.Connection) -> None:
    columns = {
        str(row["name"])
        for row in conn.execute("PRAGMA table_info(human_reviews)").fetchall()
    }
    if not columns:
        return
    additions = {
        "assignment_item_id": "ALTER TABLE human_reviews ADD COLUMN assignment_item_id INTEGER",
        "rubric_version": "ALTER TABLE human_reviews ADD COLUMN rubric_version TEXT",
        "decision_status": "ALTER TABLE human_reviews ADD COLUMN decision_status TEXT NOT NULL DEFAULT 'completed'",
        "defer_reason": "ALTER TABLE human_reviews ADD COLUMN defer_reason TEXT",
        "review_duration_sec": "ALTER TABLE human_reviews ADD COLUMN review_duration_sec INTEGER",
    }
    for column, sql in additions.items():
        if column not in columns:
            conn.execute(sql)
