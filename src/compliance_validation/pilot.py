from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .assignments import (
    DEFAULT_RUBRIC_VERSION,
    AssignmentCreateResult,
    create_assignment_from_queue,
    list_assignments,
)
from .db import DEFAULT_DB_PATH, init_database
from .importer import ImportResult, import_records, read_records
from .queues import QueueBuildResult, build_review_queues


DEFAULT_PILOT_DATA_DIR = Path("data/compliance")
DEFAULT_PILOT_DATASET_NAME = "old-compliance-pilot"
DEFAULT_PILOT_ASSIGNMENT_NAME = "start-here-calibration"
DEFAULT_PILOT_REVIEWER_ID = "reviewer_a"
DEFAULT_PILOT_QUEUE_NAME = "calibration"
DEFAULT_PILOT_ASSIGNMENT_SIZE = 20


@dataclass(frozen=True)
class PilotImportResult:
    import_result: ImportResult
    skipped_missing_material_text: int
    warnings: list[str]


@dataclass(frozen=True)
class StarterWorkflowResult:
    pilot_import: PilotImportResult
    queues: QueueBuildResult
    assignment: AssignmentCreateResult | None
    existing_assignment_name: str | None
    warnings: list[str]


def import_old_pilot_dataset(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    data_dir: Path = DEFAULT_PILOT_DATA_DIR,
    dataset_name: str = DEFAULT_PILOT_DATASET_NAME,
    notes: str | None = None,
) -> PilotImportResult:
    experiments_path = data_dir / "experiments.csv"
    gpt4o_path = data_dir / "gpt4o_compliance_audit.csv"
    final_audit_path = data_dir / "final_audit_results.csv"
    _require_file(experiments_path)
    _require_file(gpt4o_path)

    experiments = read_records(experiments_path)
    gpt4o_by_run = _aggregate_gpt4o(read_records(gpt4o_path))
    nli_by_run = _aggregate_historical_nli(read_records(final_audit_path)) if final_audit_path.exists() else {}

    records: list[dict[str, Any]] = []
    skipped_missing_text = 0
    for row in experiments:
        run_id = str(row.get("run_id") or "").strip()
        if not run_id:
            continue
        gpt4o = gpt4o_by_run.get(run_id, {})
        material_text = str(gpt4o.get("material_text") or "").strip()
        if not material_text:
            skipped_missing_text += 1
            continue
        nli = nli_by_run.get(run_id, {})
        records.append(
            {
                "material_uid": run_id,
                "run_id": run_id,
                "output_path": row.get("output_path", ""),
                "product_id": row.get("product_id") or gpt4o.get("product_id", ""),
                "product_name": "",
                "material_type": row.get("material_type") or gpt4o.get("material_type", ""),
                "engine": row.get("engine") or gpt4o.get("engine", ""),
                "model": row.get("model") or row.get("model_version", ""),
                "temperature": row.get("temperature") or gpt4o.get("temperature", ""),
                "time_of_day_label": row.get("time_of_day_label") or gpt4o.get("time_of_day", ""),
                "repetition_id": row.get("repetition_id", ""),
                "scheduled_day_of_week": row.get("scheduled_day_of_week", ""),
                "prompt": row.get("prompt_id") or row.get("prompt_text_path", ""),
                "material_text": material_text,
                "product_ground_truth": "",
                "expected_claims": "",
                "prohibited_claims": "",
                "experiment_status": row.get("status", ""),
                "scheduled_datetime": row.get("scheduled_datetime", ""),
                "date_of_run": row.get("date_of_run", ""),
                "gpt4o_status": "completed",
                "gpt4o_noncompliant": "1" if gpt4o.get("is_noncompliant") else "0",
                "gpt4o_violation_count": str(gpt4o.get("violation_count") or 0),
                "gpt4o_max_severity": gpt4o.get("max_severity", ""),
                "gpt4o_raw_label": "non_compliant" if gpt4o.get("is_noncompliant") else "compliant",
                "gpt4o_rationale": gpt4o.get("rationale", ""),
                "gpt4o_raw_json": json.dumps(gpt4o.get("raw_payload", {}), ensure_ascii=False, sort_keys=True),
                "nli_status": "completed" if nli else "not_run",
                "nli_noncompliant": "1" if nli.get("is_noncompliant") else ("0" if nli else ""),
                "nli_violation_count": str(nli.get("violation_count") or 0) if nli else "",
                "nli_raw_label": nli.get("raw_label", ""),
                "nli_rationale": nli.get("rationale", ""),
                "nli_raw_json": json.dumps(nli.get("raw_payload", {}), ensure_ascii=False, sort_keys=True),
            }
        )

    if not records:
        raise RuntimeError("No importable pilot materials found. Check that GPT-4o audit rows include material_text.")

    mapping = _old_pilot_mapping()
    warnings = [
        "Old pilot import has no product ground-truth fields; use it for workflow setup or bring truth later.",
    ]
    if skipped_missing_text:
        warnings.append(f"Skipped {skipped_missing_text} experiment rows with no available material_text.")
    result = import_records(
        db_path=db_path,
        records=records,
        mapping=mapping,
        dataset_name=dataset_name,
        source_path=data_dir,
        source_format="old_compliance_pilot_csv_bundle",
        notes=notes,
    )
    return PilotImportResult(
        import_result=result,
        skipped_missing_material_text=skipped_missing_text,
        warnings=[*result.warnings, *warnings],
    )


def prepare_starter_workflow(
    *,
    db_path: Path = DEFAULT_DB_PATH,
    data_dir: Path = DEFAULT_PILOT_DATA_DIR,
    dataset_name: str = DEFAULT_PILOT_DATASET_NAME,
    reviewer_id: str = DEFAULT_PILOT_REVIEWER_ID,
    assignment_name: str = DEFAULT_PILOT_ASSIGNMENT_NAME,
    assignment_size: int = DEFAULT_PILOT_ASSIGNMENT_SIZE,
    queue_name: str = DEFAULT_PILOT_QUEUE_NAME,
    notes: str | None = None,
) -> StarterWorkflowResult:
    init_database(db_path)
    pilot_import = import_old_pilot_dataset(
        db_path=db_path,
        data_dir=data_dir,
        dataset_name=dataset_name,
        notes=notes,
    )
    queues = build_review_queues(
        db_path=db_path,
        out_dir=Path("outputs/compliance"),
        dataset_name=dataset_name,
        calibration_size=max(int(assignment_size) * 4, 80),
        negative_audit_size=max(int(assignment_size), 20),
    )

    existing_assignments = list_assignments(db_path, dataset_name)
    existing_assignment = existing_assignments.loc[existing_assignments["name"] == assignment_name]
    if not existing_assignment.empty:
        return StarterWorkflowResult(
            pilot_import=pilot_import,
            queues=queues,
            assignment=None,
            existing_assignment_name=assignment_name,
            warnings=pilot_import.warnings,
        )

    assignment = create_assignment_from_queue(
        db_path=db_path,
        dataset_name=dataset_name,
        assignment_name=assignment_name,
        reviewer_id=reviewer_id,
        queue_name=queue_name,
        item_limit=int(assignment_size),
        blind_mode=True,
        rubric_version=DEFAULT_RUBRIC_VERSION,
        notes="Starter packet created by Start Here.",
    )
    return StarterWorkflowResult(
        pilot_import=pilot_import,
        queues=queues,
        assignment=assignment,
        existing_assignment_name=None,
        warnings=pilot_import.warnings,
    )


def _require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required pilot file not found: {path}")


def _aggregate_gpt4o(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        run_id = str(row.get("run_id") or "").strip()
        if run_id:
            grouped[run_id].append(row)

    result: dict[str, dict[str, Any]] = {}
    for run_id, group in grouped.items():
        first = group[0]
        is_noncompliant = any(_parse_compliant(row.get("compliant")) is False for row in group)
        violation_count = max((_parse_int(row.get("violation_count")) or 0 for row in group), default=0)
        max_severity = _max_severity(
            [row.get("overall_severity", "") for row in group] + [row.get("severity", "") for row in group]
        )
        rationales = [str(row.get("reasoning") or "").strip() for row in group if str(row.get("reasoning") or "").strip()]
        material_text = next((str(row.get("material_text") or "").strip() for row in group if row.get("material_text")), "")
        result[run_id] = {
            "product_id": first.get("product_id", ""),
            "engine": first.get("engine", ""),
            "temperature": first.get("temperature", ""),
            "material_type": first.get("material_type", ""),
            "time_of_day": first.get("time_of_day", ""),
            "material_text": material_text,
            "is_noncompliant": is_noncompliant,
            "violation_count": violation_count,
            "max_severity": max_severity,
            "rationale": " | ".join(rationales[:3]),
            "raw_payload": {
                "source": "gpt4o_compliance_audit.csv",
                "rows": [_compact_gpt4o_row(row) for row in group[:20]],
                "source_row_count": len(group),
            },
        }
    return result


def _aggregate_historical_nli(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        run_id = str(row.get("run_id") or "").strip()
        if run_id:
            grouped[run_id].append(row)

    result: dict[str, dict[str, Any]] = {}
    for run_id, group in grouped.items():
        fail_rows = [row for row in group if str(row.get("Status") or "").strip().upper() == "FAIL"]
        pass_rows = [row for row in group if str(row.get("Status") or "").strip().upper() == "PASS"]
        result[run_id] = {
            "is_noncompliant": bool(fail_rows),
            "violation_count": len(fail_rows),
            "raw_label": "FAIL" if fail_rows else ("PASS" if pass_rows else "unknown"),
            "rationale": f"Historical extraction/NLI audit flagged {len(fail_rows)} failed claim checks.",
            "raw_payload": {
                "source": "final_audit_results.csv",
                "failed_rows": fail_rows[:20],
                "pass_count": len(pass_rows),
                "source_row_count": len(group),
            },
        }
    return result


def _old_pilot_mapping() -> dict[str, Any]:
    return {
        "materials": {
            "material_uid": "material_uid",
            "run_id": "run_id",
            "output_path": "output_path",
            "product_id": "product_id",
            "product_name": "product_name",
            "material_type": "material_type",
            "engine": "engine",
            "model": "model",
            "temperature": "temperature",
            "time_of_day_label": "time_of_day_label",
            "repetition_id": "repetition_id",
            "scheduled_day_of_week": "scheduled_day_of_week",
            "prompt": "prompt",
            "material_text": "material_text",
            "product_ground_truth": "product_ground_truth",
            "expected_claims": "expected_claims",
            "prohibited_claims": "prohibited_claims",
        },
        "metadata_columns": [
            "experiment_status",
            "scheduled_datetime",
            "date_of_run",
        ],
        "judge_assessments": [
            {
                "judge_name": {"literal": "gpt4o"},
                "approach": {"literal": "direct_audit_old"},
                "judge_model": {"literal": "gpt-4o"},
                "status": "gpt4o_status",
                "is_noncompliant": "gpt4o_noncompliant",
                "violation_count": "gpt4o_violation_count",
                "max_severity": "gpt4o_max_severity",
                "raw_label": "gpt4o_raw_label",
                "rationale": "gpt4o_rationale",
                "raw_payload": "gpt4o_raw_json",
            },
            {
                "judge_name": {"literal": "historical_extraction_nli"},
                "approach": {"literal": "claim_extraction_nli_old"},
                "judge_model": {"literal": "legacy"},
                "status": "nli_status",
                "is_noncompliant": "nli_noncompliant",
                "violation_count": "nli_violation_count",
                "raw_label": "nli_raw_label",
                "rationale": "nli_rationale",
                "raw_payload": "nli_raw_json",
            },
        ],
    }


def _parse_compliant(value: Any) -> bool | None:
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "compliant", "pass", "passed"}:
        return True
    if text in {"0", "false", "no", "n", "non_compliant", "non-compliant", "fail", "failed"}:
        return False
    return None


def _compact_gpt4o_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in row.items()
        if key not in {"material_text"}
    }


def _parse_int(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _max_severity(values: list[Any]) -> str:
    rank = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    best = ""
    best_rank = 0
    for value in values:
        text = str(value or "").strip().upper()
        if rank.get(text, 0) > best_rank:
            best = text
            best_rank = rank[text]
    return best
