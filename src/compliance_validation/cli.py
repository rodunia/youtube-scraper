from __future__ import annotations

import argparse
from pathlib import Path

from .db import DEFAULT_DB_PATH, init_database
from .human_reviews import import_human_reviews
from .importer import import_dataset, inspect_input, load_mapping, read_records, validate_mapping
from .pilot import prepare_starter_workflow
from .queues import build_review_queues
from .reports import export_dataset_summary


def cmd_init_db(args: argparse.Namespace) -> None:
    init_database(Path(args.db))
    print(f"Initialized compliance validation DB at: {args.db}")


def cmd_inspect_input(args: argparse.Namespace) -> None:
    inspection = inspect_input(Path(args.input), args.input_format)
    print(f"Input: {inspection.path}")
    print(f"Format: {inspection.input_format}")
    print(f"Rows: {inspection.row_count}")
    print("Columns:")
    for column in inspection.columns:
        print(f"- {column} (non-empty in sample: {inspection.non_empty_counts.get(column, 0)})")


def cmd_validate_mapping(args: argparse.Namespace) -> None:
    records = read_records(Path(args.input), args.input_format)
    mapping = load_mapping(Path(args.mapping))
    check = validate_mapping(records, mapping)
    if check.errors:
        print("Errors:")
        for error in check.errors:
            print(f"- {error}")
    if check.warnings:
        print("Warnings:")
        for warning in check.warnings:
            print(f"- {warning}")
    if not check.ok:
        raise SystemExit(1)
    print("Mapping is valid.")


def cmd_import_dataset(args: argparse.Namespace) -> None:
    init_database(Path(args.db))
    result = import_dataset(
        db_path=Path(args.db),
        input_path=Path(args.input),
        mapping_path=Path(args.mapping),
        dataset_name=args.dataset_name,
        input_format=args.input_format,
        notes=args.notes,
    )
    print(f"Imported dataset: {result.dataset_name} (id={result.dataset_id})")
    print(f"- materials: {result.materials_imported}")
    print(f"- judge assessments: {result.judge_assessments_imported}")
    for warning in result.warnings:
        print(f"Warning: {warning}")


def cmd_build_queues(args: argparse.Namespace) -> None:
    init_database(Path(args.db))
    result = build_review_queues(
        db_path=Path(args.db),
        out_dir=Path(args.out_dir),
        dataset_name=args.dataset_name,
        calibration_size=args.calibration_size,
        negative_audit_size=args.negative_audit_size,
        high_risk_limit=args.high_risk_limit,
        seed=args.seed,
    )
    print("Built human validation queues:")
    for name, path in result.files.items():
        print(f"- {name}: {path}")
    print("Counts:")
    for name, count in result.counts.items():
        print(f"- {name}: {count}")


def cmd_summary(args: argparse.Namespace) -> None:
    init_database(Path(args.db))
    files = export_dataset_summary(
        db_path=Path(args.db),
        out_dir=Path(args.out_dir),
        dataset_name=args.dataset_name,
    )
    print("Exported compliance summary:")
    for name, path in files.items():
        print(f"- {name}: {path}")


def cmd_import_human_reviews(args: argparse.Namespace) -> None:
    init_database(Path(args.db))
    result = import_human_reviews(
        db_path=Path(args.db),
        input_path=Path(args.input),
        dataset_name=args.dataset_name,
        blind_to_machine_labels=not args.not_blinded,
    )
    print("Imported human reviews:")
    print(f"- reviews: {result.reviews_imported}")
    print(f"- findings: {result.findings_imported}")
    for warning in result.warnings:
        print(f"Warning: {warning}")


def cmd_start_here(args: argparse.Namespace) -> None:
    result = prepare_starter_workflow(
        db_path=Path(args.db),
        data_dir=Path(args.data_dir),
        dataset_name=args.dataset_name,
        reviewer_id=args.reviewer_id,
        assignment_name=args.assignment_name,
        assignment_size=args.assignment_size,
    )
    print("Starter compliance workflow is ready.")
    print(f"- dataset: {result.pilot_import.import_result.dataset_name}")
    print(f"- materials: {result.pilot_import.import_result.materials_imported}")
    print(f"- judge assessments: {result.pilot_import.import_result.judge_assessments_imported}")
    print("- queues:")
    for name, count in result.queues.counts.items():
        print(f"  - {name}: {count}")
    if result.assignment:
        print(f"- assignment: {result.assignment.assignment_name} ({result.assignment.item_count} items)")
    elif result.existing_assignment_name:
        print(f"- assignment already exists: {result.existing_assignment_name}")
    for warning in result.warnings:
        print(f"Warning: {warning}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compliance validation workflow CLI")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Compliance SQLite DB path")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init-db", help="Initialize the compliance validation schema")
    p_init.set_defaults(func=cmd_init_db)

    p_inspect = sub.add_parser("inspect-input", help="Inspect columns and row counts before mapping")
    p_inspect.add_argument("--input", required=True, help="CSV, JSON, or JSONL dataset file")
    p_inspect.add_argument("--input-format", choices=["csv", "json", "jsonl"], default=None)
    p_inspect.set_defaults(func=cmd_inspect_input)

    p_validate = sub.add_parser("validate-mapping", help="Validate a mapping JSON against an input file")
    p_validate.add_argument("--input", required=True, help="CSV, JSON, or JSONL dataset file")
    p_validate.add_argument("--mapping", required=True, help="Mapping JSON path")
    p_validate.add_argument("--input-format", choices=["csv", "json", "jsonl"], default=None)
    p_validate.set_defaults(func=cmd_validate_mapping)

    p_import = sub.add_parser("import-dataset", help="Import materials and machine-judge assessments")
    p_import.add_argument("--input", required=True, help="CSV, JSON, or JSONL dataset file")
    p_import.add_argument("--mapping", required=True, help="Mapping JSON path")
    p_import.add_argument("--dataset-name", required=True, help="Stable name for this dataset version")
    p_import.add_argument("--input-format", choices=["csv", "json", "jsonl"], default=None)
    p_import.add_argument("--notes", default=None)
    p_import.set_defaults(func=cmd_import_dataset)

    p_queues = sub.add_parser("build-queues", help="Build targeted human-in-the-loop review queues")
    p_queues.add_argument("--out-dir", default="outputs/compliance")
    p_queues.add_argument("--dataset-name", default=None, help="Optional dataset filter")
    p_queues.add_argument("--calibration-size", type=int, default=300)
    p_queues.add_argument(
        "--negative-audit-size",
        type=int,
        default=150,
        help="Sample size for all-machine-negative audit rows",
    )
    p_queues.add_argument("--high-risk-limit", type=int, default=None)
    p_queues.add_argument("--seed", type=int, default=20260625)
    p_queues.set_defaults(func=cmd_build_queues)

    p_reviews = sub.add_parser("import-human-reviews", help="Import completed human review CSVs")
    p_reviews.add_argument("--input", required=True, help="Human review CSV path")
    p_reviews.add_argument("--dataset-name", required=True, help="Dataset name used at import")
    p_reviews.add_argument(
        "--not-blinded",
        action="store_true",
        help="Mark reviews as not blinded to machine labels",
    )
    p_reviews.set_defaults(func=cmd_import_human_reviews)

    p_start = sub.add_parser("start-here", help="Prepare the old pilot dataset, queues, and first review packet")
    p_start.add_argument("--data-dir", default="data/compliance")
    p_start.add_argument("--dataset-name", default="old-compliance-pilot")
    p_start.add_argument("--reviewer-id", default="reviewer_a")
    p_start.add_argument("--assignment-name", default="start-here-calibration")
    p_start.add_argument("--assignment-size", type=int, default=20)
    p_start.set_defaults(func=cmd_start_here)

    p_summary = sub.add_parser("summary", help="Export current dataset and judge summary files")
    p_summary.add_argument("--out-dir", default="outputs/compliance")
    p_summary.add_argument("--dataset-name", default=None, help="Optional dataset filter")
    p_summary.set_defaults(func=cmd_summary)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
