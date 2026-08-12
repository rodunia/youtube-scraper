from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Any

from .db import get_connection


def export_dataset_summary(*, db_path: Path, out_dir: Path, dataset_name: str | None = None) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    with get_connection(db_path) as conn:
        overview = _overview(conn, dataset_name)
        judge_rows = _judge_summary(conn, dataset_name)

    files = {
        "summary_markdown": out_dir / "dataset_summary.md",
        "judge_summary_csv": out_dir / "judge_summary.csv",
    }
    files["summary_markdown"].write_text(_summary_markdown(overview, judge_rows), encoding="utf-8")
    _write_csv(files["judge_summary_csv"], judge_rows)
    return files


def _overview(conn: sqlite3.Connection, dataset_name: str | None) -> dict[str, Any]:
    dataset_filter = ""
    params: list[Any] = []
    if dataset_name:
        dataset_filter = "WHERE d.name = ?"
        params.append(dataset_name)
    row = conn.execute(
        f"""
        SELECT
            COUNT(DISTINCT d.id) AS datasets,
            COUNT(DISTINCT m.id) AS materials,
            COUNT(DISTINCT ja.id) AS judge_assessments,
            COUNT(DISTINCT hr.id) AS human_reviews,
            COUNT(DISTINCT ad.id) AS adjudications
        FROM datasets d
        LEFT JOIN materials m ON m.dataset_id = d.id
        LEFT JOIN judge_assessments ja ON ja.material_id = m.id
        LEFT JOIN human_reviews hr ON hr.material_id = m.id
        LEFT JOIN adjudications ad ON ad.material_id = m.id
        {dataset_filter}
        """,
        params,
    ).fetchone()
    return dict(row) if row else {}


def _judge_summary(conn: sqlite3.Connection, dataset_name: str | None) -> list[dict[str, Any]]:
    dataset_filter = ""
    params: list[Any] = []
    if dataset_name:
        dataset_filter = "WHERE d.name = ?"
        params.append(dataset_name)
    rows = conn.execute(
        f"""
        SELECT
            ja.judge_name,
            ja.approach,
            ja.assessment_status,
            COUNT(*) AS assessments,
            SUM(CASE WHEN ja.is_noncompliant = 1 THEN 1 ELSE 0 END) AS noncompliant,
            SUM(CASE WHEN ja.is_noncompliant = 0 THEN 1 ELSE 0 END) AS compliant,
            SUM(CASE WHEN UPPER(COALESCE(ja.max_severity, '')) = 'CRITICAL' THEN 1 ELSE 0 END) AS critical,
            SUM(CASE WHEN UPPER(COALESCE(ja.max_severity, '')) = 'HIGH' THEN 1 ELSE 0 END) AS high,
            SUM(CASE WHEN UPPER(COALESCE(ja.max_severity, '')) = 'MEDIUM' THEN 1 ELSE 0 END) AS medium,
            SUM(CASE WHEN UPPER(COALESCE(ja.max_severity, '')) = 'LOW' THEN 1 ELSE 0 END) AS low,
            COUNT(DISTINCT m.product_id) AS products,
            COUNT(DISTINCT m.material_type) AS material_types,
            COUNT(DISTINCT m.engine || ':' || m.model) AS engines_models,
            COUNT(DISTINCT m.time_of_day_label) AS time_of_day_labels,
            COUNT(DISTINCT m.scheduled_day_of_week) AS scheduled_days
        FROM judge_assessments ja
        JOIN materials m ON m.id = ja.material_id
        JOIN datasets d ON d.id = m.dataset_id
        {dataset_filter}
        GROUP BY ja.judge_name, ja.approach, ja.assessment_status
        ORDER BY ja.judge_name, ja.approach, ja.assessment_status
        """,
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def _summary_markdown(overview: dict[str, Any], judge_rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Compliance Validation Dataset Summary",
        "",
        "## Overview",
        "",
        f"- Datasets: `{overview.get('datasets', 0)}`",
        f"- Materials: `{overview.get('materials', 0)}`",
        f"- Judge assessments: `{overview.get('judge_assessments', 0)}`",
        f"- Human reviews: `{overview.get('human_reviews', 0)}`",
        f"- Adjudications: `{overview.get('adjudications', 0)}`",
        "",
        "## Judge Summary",
        "",
        "| Judge | Approach | Status | Assessments | Non-compliant | Compliant | Critical | High | Medium | Low | Time labels | Days |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in judge_rows:
        lines.append(
            "| "
            f"{row.get('judge_name', '')} | "
            f"{row.get('approach', '')} | "
            f"{row.get('assessment_status', '')} | "
            f"{row.get('assessments', 0)} | "
            f"{row.get('noncompliant', 0)} | "
            f"{row.get('compliant', 0)} | "
            f"{row.get('critical', 0)} | "
            f"{row.get('high', 0)} | "
            f"{row.get('medium', 0)} | "
            f"{row.get('low', 0)} | "
            f"{row.get('time_of_day_labels', 0)} | "
            f"{row.get('scheduled_days', 0)} |"
        )
    return "\n".join(lines) + "\n"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
