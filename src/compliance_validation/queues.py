from __future__ import annotations

import csv
import random
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import get_connection, utc_now_iso


QUEUE_VERSION = "compliance-human-loop-v1"
SEVERITY_WEIGHTS = {
    "CRITICAL": 100.0,
    "HIGH": 70.0,
    "MEDIUM": 35.0,
    "LOW": 10.0,
}


@dataclass(frozen=True)
class QueueBuildResult:
    files: dict[str, Path]
    counts: dict[str, int]


def build_review_queues(
    *,
    db_path: Path,
    out_dir: Path,
    dataset_name: str | None = None,
    calibration_size: int = 300,
    negative_audit_size: int = 150,
    high_risk_limit: int | None = None,
    seed: int = 20260625,
) -> QueueBuildResult:
    out_dir.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        rows = _load_material_signal_rows(conn, dataset_name)
        scored = [_score_material(row) for row in rows]
        _persist_queue_items(conn, scored)

    calibration = _round_robin_stratified_sample(scored, calibration_size, seed)
    high_risk = [row for row in sorted(scored, key=lambda item: (-item["priority_score"], item["material_uid"])) if row_is_high_risk(row)]
    if high_risk_limit is not None:
        high_risk = high_risk[:high_risk_limit]
    all_machine_negative_audit = _round_robin_stratified_sample(
        [row for row in scored if row["all_machine_negative"]],
        negative_audit_size,
        seed + 1,
    )
    disagreements = [row for row in scored if row["judge_disagreement"]]
    errors = [row for row in scored if row["any_machine_error"]]

    with get_connection(db_path) as conn:
        _persist_named_queue_items(conn, "calibration", calibration)
        _persist_named_queue_items(conn, "high_risk", high_risk)
        _persist_named_queue_items(conn, "all_machine_negative_audit", all_machine_negative_audit)
        _persist_named_queue_items(conn, "judge_disagreement", disagreements)
        _persist_named_queue_items(conn, "machine_error", errors)

    files = {
        "calibration_queue": out_dir / "calibration_queue.csv",
        "high_risk_queue": out_dir / "high_risk_queue.csv",
        "all_machine_negative_audit_queue": out_dir / "all_machine_negative_audit_queue.csv",
        "judge_disagreement_queue": out_dir / "judge_disagreement_queue.csv",
        "machine_error_queue": out_dir / "machine_error_queue.csv",
        "human_review_template": out_dir / "human_review_template.csv",
    }
    _write_queue(files["calibration_queue"], calibration)
    _write_queue(files["high_risk_queue"], high_risk)
    _write_queue(files["all_machine_negative_audit_queue"], all_machine_negative_audit)
    _write_queue(files["judge_disagreement_queue"], disagreements)
    _write_queue(files["machine_error_queue"], errors)
    _write_human_review_template(files["human_review_template"])

    return QueueBuildResult(
        files=files,
        counts={
            "materials_scored": len(scored),
            "calibration_queue": len(calibration),
            "high_risk_queue": len(high_risk),
            "all_machine_negative_audit_queue": len(all_machine_negative_audit),
            "judge_disagreement_queue": len(disagreements),
            "machine_error_queue": len(errors),
        },
    )


def row_is_high_risk(row: dict[str, Any]) -> bool:
    return bool(
        row["any_machine_error"]
        or row["judge_disagreement"]
        or row["high_or_critical"]
        or row["priority_score"] >= 60
    )


def _load_material_signal_rows(conn: sqlite3.Connection, dataset_name: str | None) -> list[sqlite3.Row]:
    params: list[Any] = []
    dataset_filter = ""
    if dataset_name:
        dataset_filter = "WHERE d.name = ?"
        params.append(dataset_name)
    return conn.execute(
        f"""
        SELECT
            d.name AS dataset_name,
            m.id AS material_id,
            m.material_uid,
            m.run_id,
            m.output_path,
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
            COUNT(ja.id) AS judge_count,
            SUM(CASE WHEN ja.is_noncompliant = 1 THEN 1 ELSE 0 END) AS positive_judges,
            SUM(CASE WHEN ja.is_noncompliant = 0 THEN 1 ELSE 0 END) AS negative_judges,
            SUM(CASE WHEN ja.assessment_status IN ('error','timeout') THEN 1 ELSE 0 END) AS error_judges,
            SUM(CASE
                WHEN LOWER(ja.judge_name) LIKE '%claude%'
                 AND LOWER(ja.approach) LIKE '%direct%'
                 AND ja.is_noncompliant = 1 THEN 1 ELSE 0 END
            ) AS claude_direct_positive,
            SUM(CASE
                WHEN LOWER(ja.judge_name) LIKE '%claude%'
                 AND LOWER(ja.approach) LIKE '%direct%'
                 AND ja.is_noncompliant = 0 THEN 1 ELSE 0 END
            ) AS claude_direct_negative,
            SUM(CASE
                WHEN UPPER(COALESCE(ja.max_severity, '')) IN ('CRITICAL','HIGH')
                THEN 1 ELSE 0 END
            ) AS high_or_critical_count,
            MAX(COALESCE(ja.violation_count, 0)) AS max_violation_count,
            GROUP_CONCAT(
                ja.judge_name || ':' || ja.approach || ':' ||
                COALESCE(ja.assessment_status, '') || ':' ||
                COALESCE(CAST(ja.is_noncompliant AS TEXT), 'null') || ':' ||
                COALESCE(ja.max_severity, ''),
                ' | '
            ) AS judge_signal_summary
        FROM materials m
        JOIN datasets d ON d.id = m.dataset_id
        LEFT JOIN judge_assessments ja ON ja.material_id = m.id
        {dataset_filter}
        GROUP BY m.id
        ORDER BY d.name, m.material_uid
        """,
        params,
    ).fetchall()


def _score_material(row: sqlite3.Row) -> dict[str, Any]:
    positive_judges = int(row["positive_judges"] or 0)
    negative_judges = int(row["negative_judges"] or 0)
    error_judges = int(row["error_judges"] or 0)
    max_violation_count = int(row["max_violation_count"] or 0)
    high_or_critical = int(row["high_or_critical_count"] or 0) > 0
    judge_disagreement = positive_judges > 0 and negative_judges > 0
    any_machine_error = error_judges > 0
    any_machine_positive = positive_judges > 0
    claude_direct_negative = int(row["claude_direct_negative"] or 0) > 0
    all_machine_negative = negative_judges > 0 and positive_judges == 0 and error_judges == 0

    score = 0.0
    if high_or_critical:
        score += 75.0
    if judge_disagreement:
        score += 45.0
    if any_machine_error:
        score += 35.0
    if any_machine_positive:
        score += 25.0
    score += min(max_violation_count, 10) * 4.0
    if int(row["claude_direct_positive"] or 0) > 0:
        score += 15.0

    if score >= 90:
        bucket = "urgent"
    elif score >= 55:
        bucket = "high"
    elif score >= 25:
        bucket = "medium"
    else:
        bucket = "audit_sample"

    reasons: list[str] = []
    if high_or_critical:
        reasons.append("high_or_critical_machine_severity")
    if judge_disagreement:
        reasons.append("machine_judge_disagreement")
    if any_machine_error:
        reasons.append("machine_error_or_timeout")
    if any_machine_positive:
        reasons.append("machine_positive")
    if claude_direct_negative:
        reasons.append("claude_direct_negative_candidate")
    if not reasons:
        reasons.append("stratified_calibration_candidate")

    return {
        "dataset_name": row["dataset_name"],
        "material_id": int(row["material_id"]),
        "material_uid": row["material_uid"],
        "run_id": row["run_id"] or "",
        "output_path": row["output_path"] or "",
        "product_id": row["product_id"] or "",
        "product_name": row["product_name"] or "",
        "material_type": row["material_type"] or "",
        "engine": row["engine"] or "",
        "model": row["model"] or "",
        "temperature": row["temperature"] or "",
        "time_of_day_label": row["time_of_day_label"] or "",
        "repetition_id": row["repetition_id"] or "",
        "scheduled_day_of_week": row["scheduled_day_of_week"] or "",
        "priority_score": round(score, 3),
        "priority_bucket": bucket,
        "reason": "; ".join(reasons),
        "judge_count": int(row["judge_count"] or 0),
        "positive_judges": positive_judges,
        "negative_judges": negative_judges,
        "error_judges": error_judges,
        "max_violation_count": max_violation_count,
        "any_machine_positive": any_machine_positive,
        "any_machine_error": any_machine_error,
        "judge_disagreement": judge_disagreement,
        "high_or_critical": high_or_critical,
        "claude_direct_negative": claude_direct_negative,
        "all_machine_negative": all_machine_negative,
        "judge_signal_summary": row["judge_signal_summary"] or "",
        "prompt": row["prompt"] or "",
        "material_text": row["material_text"] or "",
        "product_ground_truth": row["product_ground_truth"] or "",
    }


def _persist_queue_items(conn: sqlite3.Connection, scored: list[dict[str, Any]]) -> None:
    now = utc_now_iso()
    for row in scored:
        conn.execute(
            """
            INSERT INTO review_queue_items (
                material_id, queue_name, priority_score, priority_bucket,
                reason, queue_version, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(material_id, queue_name, queue_version) DO UPDATE SET
                priority_score=excluded.priority_score,
                priority_bucket=excluded.priority_bucket,
                reason=excluded.reason
            """,
            (
                row["material_id"],
                "human_validation_master",
                row["priority_score"],
                row["priority_bucket"],
                row["reason"],
                QUEUE_VERSION,
                now,
            ),
        )


def _persist_named_queue_items(conn: sqlite3.Connection, queue_name: str, rows: list[dict[str, Any]]) -> None:
    now = utc_now_iso()
    for row in rows:
        conn.execute(
            """
            INSERT INTO review_queue_items (
                material_id, queue_name, priority_score, priority_bucket,
                reason, queue_version, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(material_id, queue_name, queue_version) DO UPDATE SET
                priority_score=excluded.priority_score,
                priority_bucket=excluded.priority_bucket,
                reason=excluded.reason
            """,
            (
                row["material_id"],
                queue_name,
                row["priority_score"],
                row["priority_bucket"],
                row["reason"],
                QUEUE_VERSION,
                now,
            ),
        )


def _round_robin_stratified_sample(rows: list[dict[str, Any]], target_size: int, seed: int) -> list[dict[str, Any]]:
    if target_size <= 0 or not rows:
        return []
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        state = _machine_state(row)
        key = (
            str(row.get("product_id") or row.get("product_name") or "unknown_product"),
            str(row.get("material_type") or "unknown_type"),
            str(row.get("engine") or "unknown_engine"),
            str(row.get("model") or "unknown_model"),
            str(row.get("temperature") or "unknown_temperature"),
            str(row.get("time_of_day_label") or "unknown_time_of_day"),
            str(row.get("scheduled_day_of_week") or "unknown_day"),
            str(row.get("repetition_id") or "unknown_repetition"),
            state,
        )
        groups.setdefault(key, []).append(row)

    rng = random.Random(seed)
    for group_rows in groups.values():
        rng.shuffle(group_rows)

    selected: list[dict[str, Any]] = []
    keys: list[tuple[str, ...]] = sorted(groups.keys())
    while len(selected) < target_size and keys:
        next_keys: list[tuple[str, ...]] = []
        for key in keys:
            group_rows = groups[key]
            if group_rows and len(selected) < target_size:
                selected.append(group_rows.pop())
            if group_rows:
                next_keys.append(key)
        keys = next_keys
    return selected


def _machine_state(row: dict[str, Any]) -> str:
    if row["any_machine_error"]:
        return "error"
    if row["judge_disagreement"]:
        return "mixed"
    if row["any_machine_positive"]:
        return "positive"
    if row["claude_direct_negative"] or row["negative_judges"] > 0:
        return "negative"
    return "unknown"


def _write_queue(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "dataset_name",
        "material_uid",
        "run_id",
        "output_path",
        "product_id",
        "product_name",
        "material_type",
        "engine",
        "model",
        "temperature",
        "time_of_day_label",
        "repetition_id",
        "scheduled_day_of_week",
        "priority_score",
        "priority_bucket",
        "reason",
        "judge_count",
        "positive_judges",
        "negative_judges",
        "error_judges",
        "max_violation_count",
        "judge_signal_summary",
        "prompt",
        "material_text",
        "product_ground_truth",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def _write_human_review_template(path: Path) -> None:
    fieldnames = [
        "material_uid",
        "reviewer_id",
        "review_round",
        "review_status",
        "violation_count",
        "max_severity",
        "finding_category",
        "claim_text",
        "output_span",
        "ground_truth_reference",
        "rationale",
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
