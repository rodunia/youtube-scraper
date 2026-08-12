from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .db import get_connection, new_uuid, utc_now_iso


DEFAULT_RUBRIC_VERSION = "compliance-rubric-v1"


@dataclass(frozen=True)
class AssignmentCreateResult:
    assignment_id: int
    assignment_name: str
    item_count: int


def create_assignment_from_queue(
    *,
    db_path: Path,
    dataset_name: str,
    assignment_name: str,
    reviewer_id: str,
    queue_name: str,
    item_limit: int,
    blind_mode: bool = True,
    rubric_version: str = DEFAULT_RUBRIC_VERSION,
    notes: str | None = None,
) -> AssignmentCreateResult:
    if item_limit <= 0:
        raise ValueError("item_limit must be greater than 0.")
    now = utc_now_iso()
    with get_connection(db_path) as conn:
        dataset_id = _dataset_id(conn, dataset_name)
        material_rows = conn.execute(
            """
            SELECT
                rqi.material_id,
                rqi.priority_score,
                m.material_uid
            FROM review_queue_items rqi
            JOIN materials m ON m.id = rqi.material_id
            WHERE m.dataset_id = ?
              AND rqi.queue_name = ?
              AND NOT EXISTS (
                  SELECT 1
                  FROM review_assignment_items rai
                  JOIN review_assignments ra ON ra.id = rai.assignment_id
                  WHERE rai.material_id = rqi.material_id
                    AND ra.dataset_id = m.dataset_id
                    AND ra.reviewer_id = ?
                    AND rai.item_status IN ('pending','in_progress','deferred')
              )
            ORDER BY rqi.priority_score DESC, m.material_uid
            LIMIT ?
            """,
            (dataset_id, queue_name, reviewer_id, int(item_limit)),
        ).fetchall()
        if not material_rows:
            raise RuntimeError(f"No available materials found for queue `{queue_name}`.")

        conn.execute(
            """
            INSERT INTO review_assignments (
                assignment_uuid, dataset_id, name, reviewer_id, queue_name,
                blind_mode, rubric_version, status, notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            ON CONFLICT(dataset_id, name) DO UPDATE SET
                reviewer_id=excluded.reviewer_id,
                queue_name=excluded.queue_name,
                blind_mode=excluded.blind_mode,
                rubric_version=excluded.rubric_version,
                status='active',
                notes=excluded.notes
            """,
            (
                new_uuid("assignment"),
                dataset_id,
                assignment_name,
                reviewer_id,
                queue_name,
                1 if blind_mode else 0,
                rubric_version,
                notes,
                now,
            ),
        )
        row = conn.execute(
            "SELECT id FROM review_assignments WHERE dataset_id = ? AND name = ?",
            (dataset_id, assignment_name),
        ).fetchone()
        if row is None:
            raise RuntimeError("Assignment creation failed.")
        assignment_id = int(row["id"])
        conn.execute("DELETE FROM review_assignment_items WHERE assignment_id = ?", (assignment_id,))
        for position, material_row in enumerate(material_rows, start=1):
            conn.execute(
                """
                INSERT INTO review_assignment_items (
                    assignment_id, material_id, position, item_status, assigned_at
                )
                VALUES (?, ?, ?, 'pending', ?)
                """,
                (assignment_id, int(material_row["material_id"]), position, now),
            )

    return AssignmentCreateResult(
        assignment_id=assignment_id,
        assignment_name=assignment_name,
        item_count=len(material_rows),
    )


def list_assignments(db_path: Path, dataset_name: str | None = None) -> pd.DataFrame:
    params: list[Any] = []
    where = ""
    if dataset_name:
        where = "WHERE d.name = ?"
        params.append(dataset_name)
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            f"""
            SELECT
                ra.id AS assignment_id,
                d.name AS dataset_name,
                ra.name,
                ra.reviewer_id,
                ra.queue_name,
                ra.blind_mode,
                ra.rubric_version,
                ra.status,
                COUNT(rai.id) AS items,
                COALESCE(SUM(CASE WHEN rai.item_status = 'completed' THEN 1 ELSE 0 END), 0) AS completed,
                COALESCE(SUM(CASE WHEN rai.item_status = 'deferred' THEN 1 ELSE 0 END), 0) AS deferred,
                COALESCE(SUM(CASE WHEN rai.item_status = 'skipped' THEN 1 ELSE 0 END), 0) AS skipped,
                COALESCE(SUM(CASE WHEN rai.item_status IN ('pending','in_progress') THEN 1 ELSE 0 END), 0) AS remaining,
                ra.created_at
            FROM review_assignments ra
            JOIN datasets d ON d.id = ra.dataset_id
            LEFT JOIN review_assignment_items rai ON rai.assignment_id = ra.id
            {where}
            GROUP BY ra.id
            ORDER BY ra.created_at DESC, ra.id DESC
            """,
            conn,
            params=params,
        )


def list_queue_names(db_path: Path, dataset_name: str) -> list[str]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT rqi.queue_name
            FROM review_queue_items rqi
            JOIN materials m ON m.id = rqi.material_id
            JOIN datasets d ON d.id = m.dataset_id
            WHERE d.name = ?
            ORDER BY rqi.queue_name
            """,
            (dataset_name,),
        ).fetchall()
    return [str(row["queue_name"]) for row in rows]


def load_assignment_items(db_path: Path, assignment_id: int) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT
                rai.id AS assignment_item_id,
                rai.position,
                rai.item_status,
                rai.defer_reason,
                rai.skip_reason,
                rai.started_at,
                rai.completed_at,
                m.id AS material_id,
                m.material_uid,
                m.product_id,
                m.product_name,
                m.material_type,
                m.engine,
                m.model,
                m.temperature,
                m.time_of_day_label,
                m.repetition_id,
                m.scheduled_day_of_week,
                m.prompt,
                m.material_text,
                m.product_ground_truth,
                COALESCE(rqi.priority_bucket, '') AS priority_bucket,
                COALESCE(rqi.priority_score, 0) AS priority_score,
                COALESCE(rqi.reason, '') AS reason
            FROM review_assignment_items rai
            JOIN review_assignments ra ON ra.id = rai.assignment_id
            JOIN materials m ON m.id = rai.material_id
            LEFT JOIN review_queue_items rqi
                ON rqi.material_id = m.id
               AND rqi.queue_name = ra.queue_name
            WHERE rai.assignment_id = ?
            ORDER BY
                CASE rai.item_status
                    WHEN 'in_progress' THEN 0
                    WHEN 'pending' THEN 1
                    WHEN 'deferred' THEN 2
                    WHEN 'skipped' THEN 3
                    ELSE 4
                END,
                rai.position
            """,
            conn,
            params=(int(assignment_id),),
        )


def mark_assignment_item_started(db_path: Path, assignment_item_id: int) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE review_assignment_items
            SET item_status = CASE WHEN item_status = 'pending' THEN 'in_progress' ELSE item_status END,
                started_at = COALESCE(started_at, ?)
            WHERE id = ?
            """,
            (utc_now_iso(), int(assignment_item_id)),
        )


def complete_assignment_item(db_path: Path, assignment_item_id: int, review_id: int) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE review_assignment_items
            SET item_status = 'completed',
                completed_at = ?,
                last_review_id = ?,
                defer_reason = NULL,
                skip_reason = NULL
            WHERE id = ?
            """,
            (utc_now_iso(), int(review_id), int(assignment_item_id)),
        )


def defer_assignment_item(db_path: Path, assignment_item_id: int, reason: str) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE review_assignment_items
            SET item_status = 'deferred',
                completed_at = ?,
                defer_reason = ?
            WHERE id = ?
            """,
            (utc_now_iso(), reason.strip(), int(assignment_item_id)),
        )


def skip_assignment_item(db_path: Path, assignment_item_id: int, reason: str) -> None:
    with get_connection(db_path) as conn:
        conn.execute(
            """
            UPDATE review_assignment_items
            SET item_status = 'skipped',
                completed_at = ?,
                skip_reason = ?
            WHERE id = ?
            """,
            (utc_now_iso(), reason.strip(), int(assignment_item_id)),
        )


def assignment_progress(db_path: Path, assignment_id: int) -> dict[str, int]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT item_status, COUNT(*) AS n
            FROM review_assignment_items
            WHERE assignment_id = ?
            GROUP BY item_status
            """,
            (int(assignment_id),),
        ).fetchall()
    counts = {str(row["item_status"]): int(row["n"]) for row in rows}
    counts["total"] = sum(counts.values())
    return counts


def _dataset_id(conn: sqlite3.Connection, dataset_name: str) -> int:
    row = conn.execute("SELECT id FROM datasets WHERE name = ?", (dataset_name,)).fetchone()
    if row is None:
        raise RuntimeError(f"Dataset `{dataset_name}` not found.")
    return int(row["id"])
