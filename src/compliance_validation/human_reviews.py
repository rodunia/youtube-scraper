from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import get_connection, utc_now_iso


REQUIRED_REVIEW_COLUMNS = ("material_uid", "reviewer_id", "review_status")
FINDING_COLUMNS = (
    "finding_category",
    "claim_text",
    "output_span",
    "ground_truth_reference",
    "rationale",
)


@dataclass(frozen=True)
class HumanReviewImportResult:
    reviews_imported: int
    findings_imported: int
    warnings: list[str]


def save_human_review(
    *,
    db_path: Path,
    material_id: int,
    reviewer_id: str,
    review_round: str,
    review_status: str,
    violation_count: int,
    max_severity: str | None,
    rationale: str | None,
    findings: list[dict[str, str]],
    assignment_item_id: int | None = None,
    rubric_version: str | None = None,
    decision_status: str = "completed",
    defer_reason: str | None = None,
    review_duration_sec: int | None = None,
    blind_to_machine_labels: bool = True,
) -> int:
    now = utc_now_iso()
    normalized_status = _normalize_review_status(review_status)
    if normalized_status == "error" and review_status.strip().lower() != "error":
        raise ValueError(f"Unsupported review_status `{review_status}`.")
    with get_connection(db_path) as conn:
        review_id = _upsert_review(
            conn,
            material_id=int(material_id),
            assignment_item_id=assignment_item_id,
            reviewer_id=reviewer_id,
            review_round=review_round or "initial",
            rubric_version=rubric_version,
            decision_status=decision_status,
            review_status=normalized_status,
            violation_count=int(violation_count),
            max_severity=_null_if_empty(max_severity or ""),
            rationale=_null_if_empty(rationale or ""),
            defer_reason=_null_if_empty(defer_reason or ""),
            review_duration_sec=review_duration_sec,
            blind_to_machine_labels=blind_to_machine_labels,
            reviewed_at=now,
        )
        conn.execute(
            """
            DELETE FROM violation_findings
            WHERE review_id = ? AND source_type = 'human'
            """,
            (review_id,),
        )
        for finding in findings:
            if not any(str(finding.get(column, "")).strip() for column in FINDING_COLUMNS):
                continue
            _insert_human_finding(
                conn,
                review_id=review_id,
                material_id=int(material_id),
                reviewer_id=reviewer_id,
                finding={**finding, "review_status": normalized_status},
                created_at=now,
            )
    return review_id


def save_adjudication(
    *,
    db_path: Path,
    material_id: int,
    adjudicator_id: str,
    final_status: str,
    violation_count: int,
    max_severity: str | None,
    resolution_source: str,
    rationale: str | None,
) -> int:
    now = utc_now_iso()
    normalized_status = _normalize_review_status(final_status)
    if normalized_status == "error" and final_status.strip().lower() != "error":
        raise ValueError(f"Unsupported final_status `{final_status}`.")
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO adjudications (
                material_id, adjudicator_id, adjudicated_at, final_status,
                violation_count, max_severity, resolution_source, rationale,
                raw_payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(material_id) DO UPDATE SET
                adjudicator_id=excluded.adjudicator_id,
                adjudicated_at=excluded.adjudicated_at,
                final_status=excluded.final_status,
                violation_count=excluded.violation_count,
                max_severity=excluded.max_severity,
                resolution_source=excluded.resolution_source,
                rationale=excluded.rationale,
                raw_payload_json=excluded.raw_payload_json
            """,
            (
                int(material_id),
                adjudicator_id,
                now,
                normalized_status,
                int(violation_count),
                _null_if_empty(max_severity or ""),
                resolution_source,
                _null_if_empty(rationale or ""),
                "{}",
            ),
        )
        row = conn.execute(
            "SELECT id FROM adjudications WHERE material_id = ?",
            (int(material_id),),
        ).fetchone()
        if row is None:
            raise RuntimeError("Adjudication upsert failed.")
        return int(row["id"])


def import_human_reviews(
    *,
    db_path: Path,
    input_path: Path,
    dataset_name: str,
    blind_to_machine_labels: bool = True,
) -> HumanReviewImportResult:
    rows = _read_review_rows(input_path)
    warnings = _validate_review_rows(rows)
    grouped = _group_review_rows(rows)

    with get_connection(db_path) as conn:
        material_ids = _material_lookup(conn, dataset_name)
        reviews_imported = 0
        findings_imported = 0
        now = utc_now_iso()
        for key, group_rows in grouped.items():
            material_uid, reviewer_id, review_round = key
            material_id = material_ids.get(material_uid)
            if material_id is None:
                warnings.append(f"Skipped unknown material_uid `{material_uid}`.")
                continue
            first = group_rows[0]
            review_id = _upsert_review(
                conn,
                material_id=material_id,
                assignment_item_id=None,
                reviewer_id=reviewer_id,
                review_round=review_round,
                rubric_version=_null_if_empty(first.get("rubric_version", "")),
                decision_status=_null_if_empty(first.get("decision_status", "")) or "completed",
                review_status=_normalize_review_status(first.get("review_status", "")),
                violation_count=_review_violation_count(group_rows),
                max_severity=_null_if_empty(first.get("max_severity", "")),
                rationale=_null_if_empty(first.get("rationale", "")),
                defer_reason=_null_if_empty(first.get("defer_reason", "")),
                review_duration_sec=_parse_optional_int(first.get("review_duration_sec", "")),
                blind_to_machine_labels=blind_to_machine_labels,
                reviewed_at=_null_if_empty(first.get("reviewed_at", "")) or now,
            )
            reviews_imported += 1
            conn.execute(
                """
                DELETE FROM violation_findings
                WHERE review_id = ? AND source_type = 'human'
                """,
                (review_id,),
            )
            for finding in _finding_rows(group_rows):
                _insert_human_finding(
                    conn,
                    review_id=review_id,
                    material_id=material_id,
                    reviewer_id=reviewer_id,
                    finding=finding,
                    created_at=now,
                )
                findings_imported += 1

    return HumanReviewImportResult(
        reviews_imported=reviews_imported,
        findings_imported=findings_imported,
        warnings=warnings,
    )


def _read_review_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        return [dict(row) for row in csv.DictReader(f)]


def _validate_review_rows(rows: list[dict[str, str]]) -> list[str]:
    warnings: list[str] = []
    if not rows:
        warnings.append("Review file is empty.")
        return warnings
    columns = set(rows[0].keys())
    for column in REQUIRED_REVIEW_COLUMNS:
        if column not in columns:
            raise ValueError(f"Human review file missing required column `{column}`.")
    for index, row in enumerate(rows, start=2):
        for column in REQUIRED_REVIEW_COLUMNS:
            if not str(row.get(column, "")).strip():
                warnings.append(f"Row {index} has empty required column `{column}`.")
        status = _normalize_review_status(row.get("review_status", ""))
        if status == "error":
            warnings.append(f"Row {index} has unrecognized or error review_status `{row.get('review_status', '')}`.")
    return warnings


def _group_review_rows(rows: list[dict[str, str]]) -> dict[tuple[str, str, str], list[dict[str, str]]]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    for row in rows:
        key = (
            str(row.get("material_uid", "")).strip(),
            str(row.get("reviewer_id", "")).strip(),
            str(row.get("review_round", "") or "initial").strip(),
        )
        grouped.setdefault(key, []).append(row)
    return grouped


def _material_lookup(conn: sqlite3.Connection, dataset_name: str) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT m.material_uid, m.id
        FROM materials m
        JOIN datasets d ON d.id = m.dataset_id
        WHERE d.name = ?
        """,
        (dataset_name,),
    ).fetchall()
    return {str(row["material_uid"]): int(row["id"]) for row in rows}


def _upsert_review(
    conn: sqlite3.Connection,
    *,
    material_id: int,
    assignment_item_id: int | None,
    reviewer_id: str,
    review_round: str,
    rubric_version: str | None,
    decision_status: str,
    review_status: str,
    violation_count: int,
    max_severity: str | None,
    rationale: str | None,
    defer_reason: str | None,
    review_duration_sec: int | None,
    blind_to_machine_labels: bool,
    reviewed_at: str,
) -> int:
    conn.execute(
        """
        INSERT INTO human_reviews (
            material_id, assignment_item_id, reviewer_id, reviewed_at, review_round,
            rubric_version, decision_status, review_status, violation_count,
            max_severity, rationale, defer_reason, review_duration_sec,
            blind_to_machine_labels, raw_payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(material_id, reviewer_id, review_round) DO UPDATE SET
            assignment_item_id=excluded.assignment_item_id,
            reviewed_at=excluded.reviewed_at,
            rubric_version=excluded.rubric_version,
            decision_status=excluded.decision_status,
            review_status=excluded.review_status,
            violation_count=excluded.violation_count,
            max_severity=excluded.max_severity,
            rationale=excluded.rationale,
            defer_reason=excluded.defer_reason,
            review_duration_sec=excluded.review_duration_sec,
            blind_to_machine_labels=excluded.blind_to_machine_labels,
            raw_payload_json=excluded.raw_payload_json
        """,
        (
            material_id,
            assignment_item_id,
            reviewer_id,
            reviewed_at,
            review_round,
            rubric_version,
            decision_status,
            review_status,
            int(violation_count),
            max_severity,
            rationale,
            defer_reason,
            review_duration_sec,
            1 if blind_to_machine_labels else 0,
            "{}",
        ),
    )
    row = conn.execute(
        """
        SELECT id
        FROM human_reviews
        WHERE material_id = ? AND reviewer_id = ? AND review_round = ?
        """,
        (material_id, reviewer_id, review_round),
    ).fetchone()
    if row is None:
        raise RuntimeError("Human review upsert failed.")
    return int(row["id"])


def _insert_human_finding(
    conn: sqlite3.Connection,
    *,
    review_id: int,
    material_id: int,
    reviewer_id: str,
    finding: dict[str, str],
    created_at: str,
) -> None:
    conn.execute(
        """
        INSERT INTO violation_findings (
            review_id, material_id, finding_uid, source_type, source_name,
            category, severity, verdict, claim_text, output_span,
            ground_truth_reference, evidence_text, confidence, rationale,
            raw_payload_json, created_at
        )
        VALUES (?, ?, ?, 'human', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            review_id,
            material_id,
            None,
            reviewer_id,
            _null_if_empty(finding.get("finding_category", "")),
            _null_if_empty(finding.get("max_severity", "")),
            _normalize_review_status(finding.get("review_status", "")),
            _null_if_empty(finding.get("claim_text", "")),
            _null_if_empty(finding.get("output_span", "")),
            _null_if_empty(finding.get("ground_truth_reference", "")),
            None,
            None,
            _null_if_empty(finding.get("rationale", "")),
            json.dumps(finding, ensure_ascii=False, sort_keys=True),
            created_at,
        ),
    )


def _finding_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for row in rows:
        if any(str(row.get(column, "")).strip() for column in FINDING_COLUMNS):
            findings.append(row)
    return findings


def _review_violation_count(rows: list[dict[str, str]]) -> int:
    explicit_counts = [
        _parse_int(row.get("violation_count", ""))
        for row in rows
        if str(row.get("violation_count", "")).strip()
    ]
    if explicit_counts:
        return max(explicit_counts)
    return len(_finding_rows(rows))


def _normalize_review_status(value: str) -> str:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"compliant", "pass", "clean", "no_violation", "no_violations"}:
        return "compliant"
    if text in {"non_compliant", "noncompliant", "fail", "failed", "violation", "violations"}:
        return "non_compliant"
    if text in {"inconclusive", "unclear", "insufficient_ground_truth", "unknown"}:
        return "inconclusive"
    return "error"


def _parse_int(value: str) -> int:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _parse_optional_int(value: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _null_if_empty(value: str) -> str | None:
    text = str(value or "").strip()
    return text or None
