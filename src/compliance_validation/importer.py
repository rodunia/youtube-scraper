from __future__ import annotations

import csv
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import get_connection, new_uuid, utc_now_iso


REQUIRED_MATERIAL_FIELDS = (
    "material_uid",
    "run_id",
    "output_path",
    "product_id",
    "material_type",
    "engine",
    "model",
    "temperature",
    "time_of_day_label",
    "repetition_id",
    "scheduled_day_of_week",
    "material_text",
)
RECOMMENDED_MATERIAL_FIELDS = (
    "prompt",
    "product_ground_truth",
)
ASSESSMENT_VALUE_KEYS = (
    "status",
    "is_noncompliant",
    "violation_count",
    "max_severity",
    "raw_label",
    "rationale",
    "raw_payload",
)


@dataclass(frozen=True)
class InputInspection:
    path: Path
    input_format: str
    row_count: int
    columns: list[str]
    non_empty_counts: dict[str, int]


@dataclass(frozen=True)
class MappingCheck:
    ok: bool
    errors: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class ImportResult:
    dataset_id: int
    dataset_name: str
    materials_imported: int
    judge_assessments_imported: int
    warnings: list[str]


def infer_input_format(path: Path, explicit_format: str | None = None) -> str:
    if explicit_format:
        return explicit_format.lower()
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix in {".jsonl", ".ndjson"}:
        return "jsonl"
    if suffix == ".json":
        return "json"
    raise ValueError(f"Cannot infer input format from `{path}`. Use --input-format.")


def read_records(path: Path, input_format: str | None = None) -> list[dict[str, Any]]:
    fmt = infer_input_format(path, input_format)
    if fmt == "csv":
        with path.open(newline="", encoding="utf-8-sig") as f:
            return [dict(row) for row in csv.DictReader(f)]
    if fmt == "jsonl":
        records: list[dict[str, Any]] = []
        with path.open(encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                text = line.strip()
                if not text:
                    continue
                value = json.loads(text)
                if not isinstance(value, dict):
                    raise ValueError(f"JSONL line {line_number} is not an object.")
                records.append(value)
        return records
    if fmt == "json":
        value = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(value, list):
            if not all(isinstance(row, dict) for row in value):
                raise ValueError("JSON list must contain only objects.")
            return list(value)
        if isinstance(value, dict):
            for key in ("records", "materials", "rows", "data"):
                maybe_records = value.get(key)
                if isinstance(maybe_records, list) and all(isinstance(row, dict) for row in maybe_records):
                    return list(maybe_records)
        raise ValueError("JSON input must be a list of objects or contain records/materials/rows/data.")
    raise ValueError(f"Unsupported input format `{fmt}`.")


def inspect_input(path: Path, input_format: str | None = None, sample_limit: int = 200) -> InputInspection:
    records = read_records(path, input_format)
    columns = sorted({str(key) for row in records for key in row.keys()})
    non_empty_counts: dict[str, int] = {column: 0 for column in columns}
    for row in records[:sample_limit]:
        for column in columns:
            if _stringify(row.get(column)).strip():
                non_empty_counts[column] += 1
    return InputInspection(
        path=path,
        input_format=infer_input_format(path, input_format),
        row_count=len(records),
        columns=columns,
        non_empty_counts=non_empty_counts,
    )


def load_mapping(mapping_path: Path) -> dict[str, Any]:
    value = json.loads(mapping_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Mapping file must contain a JSON object.")
    return value


def validate_mapping(records: list[dict[str, Any]], mapping: dict[str, Any]) -> MappingCheck:
    errors: list[str] = []
    warnings: list[str] = []
    columns = {str(key) for row in records for key in row.keys()}
    material_mapping = _as_dict(mapping.get("materials"))

    for field in REQUIRED_MATERIAL_FIELDS:
        if field not in material_mapping:
            errors.append(f"Missing required materials mapping: `{field}`.")
            continue
        _check_spec_columns(material_mapping[field], columns, errors, f"materials.{field}")

    for field in RECOMMENDED_MATERIAL_FIELDS:
        if field not in material_mapping:
            warnings.append(f"Recommended materials mapping not set: `{field}`.")
        else:
            _check_spec_columns(material_mapping[field], columns, errors, f"materials.{field}")

    for field in ("product_name", "expected_claims", "prohibited_claims"):
        if field in material_mapping:
            _check_spec_columns(material_mapping[field], columns, errors, f"materials.{field}")

    for column in mapping.get("metadata_columns", []):
        if column not in columns:
            errors.append(f"metadata_columns contains unknown column `{column}`.")

    assessments = mapping.get("judge_assessments", [])
    if not isinstance(assessments, list):
        errors.append("`judge_assessments` must be a list.")
        assessments = []
    if not assessments:
        warnings.append("No judge assessments configured; importer will load materials only.")

    for index, assessment in enumerate(assessments):
        if not isinstance(assessment, dict):
            errors.append(f"judge_assessments[{index}] must be an object.")
            continue
        for field in ("judge_name", "approach"):
            if field not in assessment:
                errors.append(f"judge_assessments[{index}] missing `{field}`.")
            else:
                _check_spec_columns(assessment[field], columns, errors, f"judge_assessments[{index}].{field}")
        for field in ASSESSMENT_VALUE_KEYS + ("judge_model", "source_record_id", "assessed_at"):
            if field in assessment:
                _check_spec_columns(assessment[field], columns, errors, f"judge_assessments[{index}].{field}")

    if records and "material_text" in material_mapping:
        missing_output = sum(1 for row in records if not _field_value(row, material_mapping["material_text"]).strip())
        if missing_output:
            errors.append(f"{missing_output} records have empty mapped material_text.")

    return MappingCheck(ok=not errors, errors=errors, warnings=warnings)


def import_dataset(
    *,
    db_path: Path,
    input_path: Path,
    mapping_path: Path,
    dataset_name: str,
    input_format: str | None = None,
    notes: str | None = None,
) -> ImportResult:
    records = read_records(input_path, input_format)
    mapping = load_mapping(mapping_path)
    return import_records(
        db_path=db_path,
        records=records,
        mapping=mapping,
        dataset_name=dataset_name,
        source_path=input_path,
        source_format=infer_input_format(input_path, input_format),
        notes=notes,
    )


def import_records(
    *,
    db_path: Path,
    records: list[dict[str, Any]],
    mapping: dict[str, Any],
    dataset_name: str,
    source_path: Path | str,
    source_format: str,
    notes: str | None = None,
) -> ImportResult:
    check = validate_mapping(records, mapping)
    if not check.ok:
        joined = "\n".join(f"- {error}" for error in check.errors)
        raise ValueError(f"Mapping validation failed:\n{joined}")

    now = utc_now_iso()
    material_mapping = _as_dict(mapping.get("materials"))
    metadata_columns = [str(column) for column in mapping.get("metadata_columns", [])]
    assessment_mappings = [item for item in mapping.get("judge_assessments", []) if isinstance(item, dict)]

    with get_connection(db_path) as conn:
        dataset_id = _upsert_dataset(
            conn,
            name=dataset_name,
            source_path=str(source_path),
            source_format=source_format,
            row_count=len(records),
            mapping=mapping,
            notes=notes,
            created_at=now,
        )
        materials_imported = 0
        assessments_imported = 0
        for row in records:
            material_id = _upsert_material(conn, dataset_id, row, material_mapping, metadata_columns, now)
            materials_imported += 1
            for assessment_mapping in assessment_mappings:
                if not _assessment_has_content(row, assessment_mapping):
                    continue
                _upsert_assessment(conn, material_id, row, assessment_mapping, now)
                assessments_imported += 1

    return ImportResult(
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        materials_imported=materials_imported,
        judge_assessments_imported=assessments_imported,
        warnings=check.warnings,
    )


def _upsert_dataset(
    conn: sqlite3.Connection,
    *,
    name: str,
    source_path: str,
    source_format: str,
    row_count: int,
    mapping: dict[str, Any],
    notes: str | None,
    created_at: str,
) -> int:
    conn.execute(
        """
        INSERT INTO datasets (
            dataset_uuid, name, source_path, source_format, row_count,
            mapping_json, notes, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(name) DO UPDATE SET
            source_path=excluded.source_path,
            source_format=excluded.source_format,
            row_count=excluded.row_count,
            mapping_json=excluded.mapping_json,
            notes=excluded.notes
        """,
        (
            new_uuid("dataset"),
            name,
            source_path,
            source_format,
            int(row_count),
            json.dumps(mapping, ensure_ascii=False, sort_keys=True),
            notes,
            created_at,
        ),
    )
    row = conn.execute("SELECT id FROM datasets WHERE name = ?", (name,)).fetchone()
    if row is None:
        raise RuntimeError(f"Dataset `{name}` was not created.")
    return int(row["id"])


def _upsert_material(
    conn: sqlite3.Connection,
    dataset_id: int,
    row: dict[str, Any],
    material_mapping: dict[str, Any],
    metadata_columns: list[str],
    created_at: str,
) -> int:
    metadata = {column: row.get(column) for column in metadata_columns if column in row}
    values = {
        "material_uid": _field_value(row, material_mapping["material_uid"]),
        "run_id": _field_value(row, material_mapping.get("run_id")),
        "output_path": _field_value(row, material_mapping.get("output_path")),
        "product_id": _field_value(row, material_mapping.get("product_id")),
        "product_name": _field_value(row, material_mapping.get("product_name")),
        "material_type": _field_value(row, material_mapping.get("material_type")),
        "engine": _field_value(row, material_mapping.get("engine")),
        "model": _field_value(row, material_mapping.get("model")),
        "temperature": _field_value(row, material_mapping.get("temperature")),
        "time_of_day_label": _field_value(row, material_mapping.get("time_of_day_label")),
        "repetition_id": _field_value(row, material_mapping.get("repetition_id")),
        "scheduled_day_of_week": _field_value(row, material_mapping.get("scheduled_day_of_week")),
        "prompt": _field_value(row, material_mapping.get("prompt")),
        "material_text": _field_value(row, material_mapping["material_text"]),
        "product_ground_truth": _field_value(row, material_mapping.get("product_ground_truth")),
        "expected_claims": _field_value(row, material_mapping.get("expected_claims")),
        "prohibited_claims": _field_value(row, material_mapping.get("prohibited_claims")),
    }
    conn.execute(
        """
        INSERT INTO materials (
            dataset_id, material_uid, run_id, output_path, product_id,
            product_name, material_type, engine, model, temperature,
            time_of_day_label, repetition_id, scheduled_day_of_week,
            prompt, material_text, product_ground_truth, expected_claims,
            prohibited_claims, metadata_json, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(dataset_id, material_uid) DO UPDATE SET
            run_id=excluded.run_id,
            output_path=excluded.output_path,
            product_id=excluded.product_id,
            product_name=excluded.product_name,
            material_type=excluded.material_type,
            engine=excluded.engine,
            model=excluded.model,
            temperature=excluded.temperature,
            time_of_day_label=excluded.time_of_day_label,
            repetition_id=excluded.repetition_id,
            scheduled_day_of_week=excluded.scheduled_day_of_week,
            prompt=excluded.prompt,
            material_text=excluded.material_text,
            product_ground_truth=excluded.product_ground_truth,
            expected_claims=excluded.expected_claims,
            prohibited_claims=excluded.prohibited_claims,
            metadata_json=excluded.metadata_json
        """,
        (
            dataset_id,
            values["material_uid"],
            _null_if_empty(values["run_id"]),
            _null_if_empty(values["output_path"]),
            _null_if_empty(values["product_id"]),
            _null_if_empty(values["product_name"]),
            _null_if_empty(values["material_type"]),
            _null_if_empty(values["engine"]),
            _null_if_empty(values["model"]),
            _null_if_empty(values["temperature"]),
            _null_if_empty(values["time_of_day_label"]),
            _null_if_empty(values["repetition_id"]),
            _null_if_empty(values["scheduled_day_of_week"]),
            _null_if_empty(values["prompt"]),
            values["material_text"],
            _null_if_empty(values["product_ground_truth"]),
            _null_if_empty(values["expected_claims"]),
            _null_if_empty(values["prohibited_claims"]),
            json.dumps(metadata, ensure_ascii=False, sort_keys=True),
            created_at,
        ),
    )
    material = conn.execute(
        "SELECT id FROM materials WHERE dataset_id = ? AND material_uid = ?",
        (dataset_id, values["material_uid"]),
    ).fetchone()
    if material is None:
        raise RuntimeError(f"Material `{values['material_uid']}` was not created.")
    return int(material["id"])


def _upsert_assessment(
    conn: sqlite3.Connection,
    material_id: int,
    row: dict[str, Any],
    assessment_mapping: dict[str, Any],
    created_at: str,
) -> None:
    raw_payload = _raw_payload_value(row, assessment_mapping.get("raw_payload"))
    status = _normalize_status(_field_value(row, assessment_mapping.get("status")))
    is_noncompliant = _parse_bool(_field_value(row, assessment_mapping.get("is_noncompliant")))
    if status == "unknown" and is_noncompliant is not None:
        status = "completed"

    conn.execute(
        """
        INSERT INTO judge_assessments (
            material_id, judge_name, approach, judge_model, assessment_status,
            is_noncompliant, violation_count, max_severity, raw_label, rationale,
            source_record_id, raw_payload_json, assessed_at, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(material_id, judge_name, approach) DO UPDATE SET
            judge_model=excluded.judge_model,
            assessment_status=excluded.assessment_status,
            is_noncompliant=excluded.is_noncompliant,
            violation_count=excluded.violation_count,
            max_severity=excluded.max_severity,
            raw_label=excluded.raw_label,
            rationale=excluded.rationale,
            source_record_id=excluded.source_record_id,
            raw_payload_json=excluded.raw_payload_json,
            assessed_at=excluded.assessed_at
        """,
        (
            material_id,
            _field_value(row, assessment_mapping["judge_name"]),
            _field_value(row, assessment_mapping["approach"]),
            _null_if_empty(_field_value(row, assessment_mapping.get("judge_model"))),
            status,
            is_noncompliant,
            _parse_int(_field_value(row, assessment_mapping.get("violation_count"))),
            _normalize_severity(_field_value(row, assessment_mapping.get("max_severity"))),
            _null_if_empty(_field_value(row, assessment_mapping.get("raw_label"))),
            _null_if_empty(_field_value(row, assessment_mapping.get("rationale"))),
            _null_if_empty(_field_value(row, assessment_mapping.get("source_record_id"))),
            json.dumps(raw_payload, ensure_ascii=False, sort_keys=True),
            _null_if_empty(_field_value(row, assessment_mapping.get("assessed_at"))),
            created_at,
        ),
    )


def _assessment_has_content(row: dict[str, Any], mapping: dict[str, Any]) -> bool:
    for key in ASSESSMENT_VALUE_KEYS:
        if key in mapping and _field_value(row, mapping[key]).strip():
            return True
    return False


def _check_spec_columns(spec: Any, columns: set[str], errors: list[str], label: str) -> None:
    for column in _spec_columns(spec):
        if column not in columns:
            errors.append(f"{label} references unknown column `{column}`.")


def _spec_columns(spec: Any) -> list[str]:
    if spec is None:
        return []
    if isinstance(spec, str):
        return [spec]
    if isinstance(spec, dict):
        if "literal" in spec:
            return []
        if "column" in spec:
            return [str(spec["column"])]
        if "columns" in spec and isinstance(spec["columns"], list):
            return [str(column) for column in spec["columns"]]
    return []


def _field_value(row: dict[str, Any], spec: Any) -> str:
    if spec is None:
        return ""
    if isinstance(spec, str):
        return _stringify(row.get(spec))
    if isinstance(spec, dict):
        if "literal" in spec:
            return _stringify(spec.get("literal"))
        if "column" in spec:
            return _stringify(row.get(str(spec["column"])))
        if "columns" in spec and isinstance(spec["columns"], list):
            payload = {str(column): row.get(str(column)) for column in spec["columns"]}
            return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return _stringify(spec)


def _raw_payload_value(row: dict[str, Any], spec: Any) -> Any:
    if spec is None:
        return {}
    text = _field_value(row, spec).strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def _null_if_empty(value: str) -> str | None:
    text = value.strip()
    return text or None


def _parse_bool(value: str) -> int | None:
    text = value.strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "y", "non_compliant", "non-compliant", "fail", "failed", "violation"}:
        return 1
    if text in {"0", "false", "no", "n", "compliant", "pass", "passed", "clean"}:
        return 0
    return None


def _parse_int(value: str) -> int | None:
    text = value.strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _normalize_status(value: str) -> str:
    text = value.strip().lower().replace("-", "_").replace(" ", "_")
    if not text:
        return "unknown"
    if text in {"ok", "complete", "completed", "success", "succeeded"}:
        return "completed"
    if text in {"error", "errored", "failed", "failure"}:
        return "error"
    if text in {"timeout", "timed_out", "quota_exceeded"}:
        return "timeout"
    if text in {"not_run", "not_tested", "not_applicable", "missing"}:
        return "not_run"
    if text in {"abandoned", "rejected"}:
        return "abandoned"
    return "unknown"


def _normalize_severity(value: str) -> str | None:
    text = value.strip().upper()
    return text or None
