from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from compliance_validation.assignments import (
    DEFAULT_RUBRIC_VERSION,
    assignment_progress,
    complete_assignment_item,
    create_assignment_from_queue,
    defer_assignment_item,
    list_assignments,
    list_queue_names,
    load_assignment_items,
    mark_assignment_item_started,
    skip_assignment_item,
)
from compliance_validation.db import DEFAULT_DB_PATH, get_connection, init_database
from compliance_validation.human_reviews import save_adjudication, save_human_review
from compliance_validation.importer import import_dataset, inspect_input, load_mapping, read_records, validate_mapping
from compliance_validation.pilot import (
    DEFAULT_PILOT_ASSIGNMENT_NAME,
    DEFAULT_PILOT_ASSIGNMENT_SIZE,
    DEFAULT_PILOT_DATA_DIR,
    DEFAULT_PILOT_DATASET_NAME,
    DEFAULT_PILOT_REVIEWER_ID,
    prepare_starter_workflow,
)
from compliance_validation.queues import build_review_queues
from compliance_validation.reports import export_dataset_summary


APP_TITLE = "Compliance Validation Console"
DEFAULT_OUTPUT_DIR = Path("outputs/compliance")
FULL_MAPPING_TEMPLATE = Path("src/compliance_validation/templates/mapping_template.json")
REGISTRY_MAPPING_TEMPLATE = Path("src/compliance_validation/templates/material_registry_mapping_template.json")
REVIEW_STATUSES = ["compliant", "non_compliant", "inconclusive", "error"]
SEVERITIES = ["", "LOW", "MEDIUM", "HIGH", "CRITICAL"]
DEFER_REASONS = ["needs_product_truth", "unclear_context", "needs_second_reviewer", "technical_issue", "other"]


st.set_page_config(page_title=APP_TITLE, layout="wide")


def main() -> None:
    st.title(APP_TITLE)
    st.caption("Separate human-in-the-loop workflow for LLM marketing-material validation.")

    db_path = Path(
        st.sidebar.text_input(
            "Compliance DB path",
            value=str(DEFAULT_DB_PATH),
            help="This is separate from the YouTube/KES SQLite database.",
        )
    )
    if st.sidebar.button("Initialize DB", use_container_width=True):
        init_database(db_path)
        st.sidebar.success("Compliance DB initialized.")

    if not db_path.exists():
        init_database(db_path)

    datasets = list_datasets(db_path)
    dataset_name = dataset_selector(datasets)

    tabs = st.tabs(["Start Here", "Review", "Overview", "Import", "Queues", "Assignments", "Adjudication", "Exports"])
    with tabs[0]:
        start_here_tab(db_path, dataset_name)
    with tabs[1]:
        review_tab(db_path, dataset_name)
    with tabs[2]:
        overview_tab(db_path, dataset_name)
    with tabs[3]:
        import_tab(db_path)
    with tabs[4]:
        queues_tab(db_path, dataset_name)
    with tabs[5]:
        assignments_tab(db_path, dataset_name)
    with tabs[6]:
        adjudication_tab(db_path, dataset_name)
    with tabs[7]:
        exports_tab(db_path, dataset_name)


def dataset_selector(datasets: pd.DataFrame) -> str | None:
    st.sidebar.divider()
    if datasets.empty:
        st.sidebar.info("No compliance datasets imported yet.")
        return None
    options = datasets["name"].astype(str).tolist()
    return st.sidebar.selectbox("Dataset", options=options)


def overview_tab(db_path: Path, dataset_name: str | None) -> None:
    st.subheader("Dataset Overview")
    if dataset_name is None:
        st.info("Import a material registry or full judge file to begin.")
        return

    overview = load_overview(db_path, dataset_name)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Materials", overview.get("materials", 0))
    c2.metric("Judge Assessments", overview.get("judge_assessments", 0))
    c3.metric("Human Reviews", overview.get("human_reviews", 0))
    c4.metric("Adjudications", overview.get("adjudications", 0))
    c5.metric("Queued", overview.get("queued", 0))

    st.markdown("#### Machine Judge Summary")
    judge_summary = load_judge_summary(db_path, dataset_name)
    if judge_summary.empty:
        st.info("No machine judge assessments imported for this dataset.")
    else:
        st.dataframe(judge_summary, use_container_width=True, hide_index=True)

    st.markdown("#### Experiment Coverage")
    coverage = load_experiment_coverage(db_path, dataset_name)
    if coverage.empty:
        st.info("No materials found.")
    else:
        st.dataframe(coverage, use_container_width=True, hide_index=True)

    st.markdown("#### Review Coverage")
    review_coverage = load_review_coverage(db_path, dataset_name)
    if review_coverage.empty:
        st.info("No human review coverage yet.")
    else:
        st.dataframe(review_coverage, use_container_width=True, hide_index=True)


def start_here_tab(db_path: Path, dataset_name: str | None) -> None:
    st.subheader("Start Here")
    st.write("This is the shortest path: load the old pilot CSV bundle, build queues, create one blind review packet.")

    status = starter_status(db_path)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pilot Dataset", "Ready" if status["dataset_ready"] else "Not yet")
    c2.metric("Queued Items", status["queued_items"])
    c3.metric("Assignments", status["assignments"])
    c4.metric("Human Reviews", status["human_reviews"])

    notice = st.session_state.pop("starter_workflow_notice", None)
    if notice:
        st.success(notice["message"])
        for line in notice.get("details", []):
            st.write(line)
        if notice.get("queue_counts"):
            st.dataframe(
                pd.DataFrame([{"queue": key, "count": value} for key, value in notice["queue_counts"].items()]),
                use_container_width=True,
                hide_index=True,
            )
        for warning in notice.get("warnings", []):
            st.warning(warning)

    with st.expander("Settings", expanded=not status["dataset_ready"]):
        data_dir = Path(st.text_input("Old pilot CSV folder", value=str(DEFAULT_PILOT_DATA_DIR)))
        starter_dataset_name = st.text_input("Dataset name", value=dataset_name or DEFAULT_PILOT_DATASET_NAME)
        reviewer_id = st.text_input("Reviewer ID", value=DEFAULT_PILOT_REVIEWER_ID)
        assignment_name = st.text_input("First packet name", value=DEFAULT_PILOT_ASSIGNMENT_NAME)
        assignment_size = st.number_input("First packet size", min_value=5, max_value=200, value=DEFAULT_PILOT_ASSIGNMENT_SIZE, step=5)

    if st.button("Prepare First Review Packet", type="primary", use_container_width=True):
        try:
            result = prepare_starter_workflow(
                db_path=db_path,
                data_dir=data_dir,
                dataset_name=starter_dataset_name,
                reviewer_id=reviewer_id,
                assignment_name=assignment_name,
                assignment_size=int(assignment_size),
            )
            details = [
                (
                    f"Imported {result.pilot_import.import_result.materials_imported} materials and "
                    f"{result.pilot_import.import_result.judge_assessments_imported} machine assessments."
                )
            ]
            if result.assignment:
                details.append(f"Created `{result.assignment.assignment_name}` with {result.assignment.item_count} items.")
            elif result.existing_assignment_name:
                details.append(f"`{result.existing_assignment_name}` already exists, so I left it untouched.")
            st.session_state["starter_workflow_notice"] = {
                "message": "Ready. Open the Review tab and start coding the packet.",
                "details": details,
                "queue_counts": result.queues.counts,
                "warnings": result.warnings,
            }
            st.rerun()
        except Exception as exc:
            st.error(str(exc))

    st.markdown("#### What You Do After This")
    st.write("1. Go to **Review**.")
    st.write("2. Pick the starter packet.")
    st.write("3. Read one material, choose a decision, write a short rationale, then press **Save And Next**.")
    st.info("Machine labels stay hidden by default, so this remains a blind human coding workflow.")


def import_tab(db_path: Path) -> None:
    st.subheader("Import Materials And Machine Signals")
    st.write("Use the registry template for pending canonical rows, or the full template when judge outputs are present.")

    col_a, col_b = st.columns(2)
    col_a.code(str(REGISTRY_MAPPING_TEMPLATE), language="text")
    col_b.code(str(FULL_MAPPING_TEMPLATE), language="text")

    input_path = Path(st.text_input("Input file path", value="results/experiments.csv"))
    mapping_path = Path(
        st.text_input(
            "Mapping JSON path",
            value=str(REGISTRY_MAPPING_TEMPLATE),
        )
    )
    dataset_name = st.text_input("Dataset name", value="llm-marketing-materials-v1")
    input_format = st.selectbox("Input format", options=["auto", "csv", "json", "jsonl"], index=0)
    notes = st.text_area("Import notes", value="", height=80)
    input_format_arg = None if input_format == "auto" else input_format

    actions = st.columns(4)
    if actions[0].button("Inspect Input", use_container_width=True):
        try:
            inspection = inspect_input(input_path, input_format_arg)
            st.success(f"Found {inspection.row_count} rows.")
            st.dataframe(
                pd.DataFrame(
                    {
                        "column": inspection.columns,
                        "non_empty_in_sample": [inspection.non_empty_counts.get(column, 0) for column in inspection.columns],
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
        except Exception as exc:
            st.error(str(exc))

    if actions[1].button("Validate Mapping", use_container_width=True):
        try:
            records = read_records(input_path, input_format_arg)
            mapping = load_mapping(mapping_path)
            check = validate_mapping(records, mapping)
            if check.ok:
                st.success("Mapping is valid.")
            for warning in check.warnings:
                st.warning(warning)
            for error in check.errors:
                st.error(error)
        except Exception as exc:
            st.error(str(exc))

    if actions[2].button("Import Dataset", use_container_width=True):
        try:
            result = import_dataset(
                db_path=db_path,
                input_path=input_path,
                mapping_path=mapping_path,
                dataset_name=dataset_name,
                input_format=input_format_arg,
                notes=notes or None,
            )
            st.success(
                f"Imported {result.materials_imported} materials and "
                f"{result.judge_assessments_imported} judge assessments."
            )
            for warning in result.warnings:
                st.warning(warning)
        except Exception as exc:
            st.error(str(exc))

    if actions[3].button("Refresh Page", use_container_width=True):
        st.rerun()


def queues_tab(db_path: Path, dataset_name: str | None) -> None:
    st.subheader("Human Review Queues")
    if dataset_name is None:
        st.info("Import a dataset before building queues.")
        return

    c1, c2, c3, c4 = st.columns(4)
    calibration_size = c1.number_input("Calibration size", min_value=0, value=300, step=25)
    negative_audit_size = c2.number_input("All-machine-negative audit size", min_value=0, value=150, step=25)
    high_risk_limit = c3.number_input("High-risk limit", min_value=0, value=0, step=25)
    seed = c4.number_input("Sampling seed", min_value=1, value=20260625, step=1)
    out_dir = Path(st.text_input("Queue output directory", value=str(DEFAULT_OUTPUT_DIR)))

    if st.button("Build Queues", type="primary"):
        try:
            result = build_review_queues(
                db_path=db_path,
                out_dir=out_dir,
                dataset_name=dataset_name,
                calibration_size=int(calibration_size),
                negative_audit_size=int(negative_audit_size),
                high_risk_limit=None if int(high_risk_limit) == 0 else int(high_risk_limit),
                seed=int(seed),
            )
            st.success("Queues built.")
            st.dataframe(
                pd.DataFrame([{"queue": key, "count": value} for key, value in result.counts.items()]),
                use_container_width=True,
                hide_index=True,
            )
            st.write("Files")
            st.dataframe(
                pd.DataFrame([{"queue": key, "path": str(value)} for key, value in result.files.items()]),
                use_container_width=True,
                hide_index=True,
            )
        except Exception as exc:
            st.error(str(exc))

    queue = load_master_queue(db_path, dataset_name)
    if queue.empty:
        st.info("No queue rows yet. Build queues to populate the master priority queue.")
    else:
        st.markdown("#### Master Priority Queue")
        st.dataframe(queue, use_container_width=True, hide_index=True)


def assignments_tab(db_path: Path, dataset_name: str | None) -> None:
    st.subheader("Assignment Packets")
    if dataset_name is None:
        st.info("Import a dataset before creating assignments.")
        return

    queue_names = list_queue_names(db_path, dataset_name)
    if not queue_names:
        st.info("Build queues before creating assignments.")
        return

    st.markdown("#### Create Packet")
    with st.form("create_assignment_form"):
        c1, c2, c3 = st.columns(3)
        assignment_name = c1.text_input("Packet name", value="calibration-a")
        reviewer_id = c2.text_input("Reviewer ID", value="reviewer_a")
        queue_name = c3.selectbox("Source queue", queue_names)
        c4, c5, c6 = st.columns(3)
        item_limit = c4.number_input("Items", min_value=1, value=50, step=10)
        blind_mode = c5.checkbox("Blind machine labels", value=True)
        rubric_version = c6.text_input("Rubric version", value=DEFAULT_RUBRIC_VERSION)
        notes = st.text_area("Packet notes", height=70)
        submitted = st.form_submit_button("Create Assignment", type="primary")
        if submitted:
            try:
                result = create_assignment_from_queue(
                    db_path=db_path,
                    dataset_name=dataset_name,
                    assignment_name=assignment_name,
                    reviewer_id=reviewer_id,
                    queue_name=queue_name,
                    item_limit=int(item_limit),
                    blind_mode=blind_mode,
                    rubric_version=rubric_version,
                    notes=notes or None,
                )
                st.success(f"Created `{result.assignment_name}` with {result.item_count} items.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    st.markdown("#### Active Packets")
    assignments = list_assignments(db_path, dataset_name)
    if assignments.empty:
        st.info("No assignments yet.")
    else:
        st.dataframe(assignments, use_container_width=True, hide_index=True)


def review_tab(db_path: Path, dataset_name: str | None) -> None:
    st.subheader("Coding Workbench")
    if dataset_name is None:
        st.info("Import a dataset before reviewing materials.")
        return

    assignments = list_assignments(db_path, dataset_name)
    if assignments.empty:
        st.info("Create an assignment packet before reviewing.")
        return
    assignments = assignments.fillna({"items": 0, "completed": 0, "deferred": 0, "skipped": 0, "remaining": 0})

    assignment_labels = {
        (
            f"{row.name} | {row.reviewer_id} | {row.queue_name} | "
            f"{int(row.completed or 0)}/{int(row.items or 0)} done"
        ): int(row.assignment_id)
        for row in assignments.itertuples(index=False)
    }
    selected_assignment_label = st.selectbox("Assignment packet", list(assignment_labels.keys()))
    assignment_id = assignment_labels[selected_assignment_label]
    assignment_row = assignments.loc[assignments["assignment_id"] == assignment_id].iloc[0]
    progress = assignment_progress(db_path, assignment_id)
    total = max(progress.get("total", 0), 1)
    completed = progress.get("completed", 0)
    progress_cols = st.columns(5)
    progress_cols[0].metric("Progress", f"{completed}/{progress.get('total', 0)}")
    progress_cols[1].metric("Remaining", progress.get("pending", 0) + progress.get("in_progress", 0))
    progress_cols[2].metric("Deferred", progress.get("deferred", 0))
    progress_cols[3].metric("Skipped", progress.get("skipped", 0))
    progress_cols[4].metric("Blind", "Yes" if int(assignment_row["blind_mode"]) else "No")
    st.progress(min(completed / total, 1.0))

    items = load_assignment_items(db_path, assignment_id)
    if items.empty:
        st.warning("This assignment has no items.")
        return

    active_items = items[items["item_status"].isin(["in_progress", "pending", "deferred"])].copy()
    if active_items.empty:
        st.success("This assignment packet is complete.")
        st.dataframe(items, use_container_width=True, hide_index=True)
        return

    active_items["select_label"] = active_items.apply(
        lambda row: (
            f"{int(row['position'])}. {row['material_uid']} | {row['product_id'] or row['product_name'] or 'unknown'} | "
            f"{row['material_type'] or 'unknown'} | {row['item_status']}"
        ),
        axis=1,
    )
    selected_label = st.selectbox("Item", active_items["select_label"].tolist())
    item = active_items.loc[active_items["select_label"] == selected_label].iloc[0]
    mark_assignment_item_started(db_path, int(item["assignment_item_id"]))
    material = load_material_detail(db_path, int(item["material_id"]))

    st.caption(f"Packet: {assignment_row['name']} | Queue: {assignment_row['queue_name']} | Reason: {item['reason']}")
    show_material_panel(material)

    blind_mode = bool(int(assignment_row["blind_mode"]))
    reveal_signals = False if blind_mode else True
    if blind_mode:
        reveal_signals = st.checkbox("Reveal machine signals for this item", value=False)
    if reveal_signals:
        show_machine_signals(db_path, int(item["material_id"]))
    else:
        st.info("Machine signals are hidden for blind review.")
    show_existing_reviews(db_path, int(item["material_id"]))

    st.markdown("#### Decision")
    with st.form("human_review_form"):
        review_status = st.radio(
            "Material decision",
            REVIEW_STATUSES,
            horizontal=True,
            help="Use inconclusive when product truth or context is insufficient.",
        )
        c1, c2, c3 = st.columns(3)
        reviewer_id = c1.text_input("Reviewer ID", value=str(assignment_row["reviewer_id"]))
        review_round = c2.text_input("Review round", value=str(assignment_row["name"]))
        max_severity = c3.selectbox("Max severity", SEVERITIES)
        violation_count = 0
        findings: list[dict[str, str]] = []
        if review_status == "non_compliant":
            violation_count = st.number_input("Violation count", min_value=1, value=1, step=1)
            st.markdown("Finding evidence")
            f1, f2 = st.columns(2)
            finding_category = f1.text_input("Finding category")
            claim_text = f2.text_input("Claim text")
            output_span = st.text_area("Output span", height=80)
            ground_truth_reference = st.text_area("Ground-truth reference", height=80)
            finding_rationale = st.text_area("Finding rationale", height=80)
            findings = [
                {
                    "finding_category": finding_category,
                    "claim_text": claim_text,
                    "output_span": output_span,
                    "ground_truth_reference": ground_truth_reference,
                    "rationale": finding_rationale,
                    "max_severity": max_severity,
                }
            ]
        elif review_status == "inconclusive":
            st.info("Use the rationale field to explain what context or product truth is missing.")
        rationale = st.text_area("Decision rationale", height=90)
        submitted = st.form_submit_button("Save And Next", type="primary")
        if submitted:
            try:
                review_id = save_human_review(
                    db_path=db_path,
                    material_id=int(item["material_id"]),
                    assignment_item_id=int(item["assignment_item_id"]),
                    reviewer_id=reviewer_id,
                    review_round=review_round,
                    review_status=review_status,
                    violation_count=int(violation_count),
                    max_severity=max_severity or None,
                    rationale=rationale or None,
                    findings=findings,
                    rubric_version=str(assignment_row["rubric_version"]),
                    decision_status="completed",
                    blind_to_machine_labels=blind_mode and not reveal_signals,
                )
                complete_assignment_item(db_path, int(item["assignment_item_id"]), review_id)
                st.success("Review saved.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with st.expander("Defer Or Skip"):
        d1, d2 = st.columns(2)
        defer_reason = d1.selectbox("Defer reason", DEFER_REASONS)
        defer_note = d1.text_input("Defer note")
        if d1.button("Defer Item", use_container_width=True):
            reason = defer_reason if not defer_note.strip() else f"{defer_reason}: {defer_note.strip()}"
            defer_assignment_item(db_path, int(item["assignment_item_id"]), reason)
            st.rerun()
        skip_reason = d2.text_input("Skip reason")
        if d2.button("Skip Item", use_container_width=True):
            skip_assignment_item(db_path, int(item["assignment_item_id"]), skip_reason or "skipped_by_reviewer")
            st.rerun()


def adjudication_tab(db_path: Path, dataset_name: str | None) -> None:
    st.subheader("Adjudication")
    if dataset_name is None:
        st.info("Import a dataset before adjudication.")
        return

    candidates = load_adjudication_candidates(db_path, dataset_name)
    if candidates.empty:
        st.info("No adjudication candidates yet. Materials appear here after multiple or conflicting human reviews.")
        return

    selected_label = st.selectbox("Adjudication material", candidates["select_label"].tolist())
    material_id = int(candidates.loc[candidates["select_label"] == selected_label, "material_id"].iloc[0])
    material = load_material_detail(db_path, material_id)
    show_material_panel(material)
    show_existing_reviews(db_path, material_id)
    show_existing_adjudication(db_path, material_id)

    with st.form("adjudication_form"):
        c1, c2, c3 = st.columns(3)
        adjudicator_id = c1.text_input("Adjudicator ID", value="adjudicator_a")
        final_status = c2.selectbox("Final status", REVIEW_STATUSES)
        max_severity = c3.selectbox("Max severity", SEVERITIES)
        violation_count = st.number_input("Final violation count", min_value=0, value=0, step=1)
        resolution_source = st.text_input("Resolution source", value="human_adjudication")
        rationale = st.text_area("Adjudication rationale", height=120)
        submitted = st.form_submit_button("Save Adjudication", type="primary")
        if submitted:
            try:
                save_adjudication(
                    db_path=db_path,
                    material_id=material_id,
                    adjudicator_id=adjudicator_id,
                    final_status=final_status,
                    violation_count=int(violation_count),
                    max_severity=max_severity or None,
                    resolution_source=resolution_source,
                    rationale=rationale or None,
                )
                st.success("Adjudication saved.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))


def exports_tab(db_path: Path, dataset_name: str | None) -> None:
    st.subheader("Exports")
    if dataset_name is None:
        st.info("Import a dataset before exporting summaries.")
        return
    out_dir = Path(st.text_input("Summary output directory", value=str(DEFAULT_OUTPUT_DIR)))
    if st.button("Export Summary Files", type="primary"):
        try:
            files = export_dataset_summary(db_path=db_path, out_dir=out_dir, dataset_name=dataset_name)
            st.success("Summary files exported.")
            st.dataframe(
                pd.DataFrame([{"name": key, "path": str(value)} for key, value in files.items()]),
                use_container_width=True,
                hide_index=True,
            )
        except Exception as exc:
            st.error(str(exc))


def list_datasets(db_path: Path) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT id, name, row_count, source_format, source_path, created_at
            FROM datasets
            ORDER BY created_at DESC, id DESC
            """,
            conn,
        )


def starter_status(db_path: Path) -> dict[str, int | bool]:
    if not db_path.exists():
        return {
            "dataset_ready": False,
            "queued_items": 0,
            "assignments": 0,
            "human_reviews": 0,
        }
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(DISTINCT d.id) AS datasets,
                COUNT(DISTINCT rqi.id) AS queued_items,
                COUNT(DISTINCT ra.id) AS assignments,
                COUNT(DISTINCT hr.id) AS human_reviews
            FROM datasets d
            LEFT JOIN materials m ON m.dataset_id = d.id
            LEFT JOIN review_queue_items rqi ON rqi.material_id = m.id
            LEFT JOIN review_assignments ra ON ra.dataset_id = d.id
            LEFT JOIN human_reviews hr ON hr.material_id = m.id
            WHERE d.name = ?
            """,
            (DEFAULT_PILOT_DATASET_NAME,),
        ).fetchone()
    return {
        "dataset_ready": bool(row and int(row["datasets"] or 0)),
        "queued_items": int(row["queued_items"] or 0) if row else 0,
        "assignments": int(row["assignments"] or 0) if row else 0,
        "human_reviews": int(row["human_reviews"] or 0) if row else 0,
    }


def load_overview(db_path: Path, dataset_name: str) -> dict[str, Any]:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(DISTINCT m.id) AS materials,
                COUNT(DISTINCT ja.id) AS judge_assessments,
                COUNT(DISTINCT hr.id) AS human_reviews,
                COUNT(DISTINCT ad.id) AS adjudications,
                COUNT(DISTINCT rqi.id) AS queued
            FROM datasets d
            LEFT JOIN materials m ON m.dataset_id = d.id
            LEFT JOIN judge_assessments ja ON ja.material_id = m.id
            LEFT JOIN human_reviews hr ON hr.material_id = m.id
            LEFT JOIN adjudications ad ON ad.material_id = m.id
            LEFT JOIN review_queue_items rqi ON rqi.material_id = m.id
            WHERE d.name = ?
            """,
            (dataset_name,),
        ).fetchone()
    return dict(row) if row else {}


def load_judge_summary(db_path: Path, dataset_name: str) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT
                ja.judge_name,
                ja.approach,
                ja.assessment_status,
                COUNT(*) AS assessments,
                SUM(CASE WHEN ja.is_noncompliant = 1 THEN 1 ELSE 0 END) AS noncompliant,
                SUM(CASE WHEN ja.is_noncompliant = 0 THEN 1 ELSE 0 END) AS compliant,
                SUM(CASE WHEN ja.assessment_status IN ('error','timeout') THEN 1 ELSE 0 END) AS errors,
                SUM(COALESCE(ja.violation_count, 0)) AS total_violations
            FROM judge_assessments ja
            JOIN materials m ON m.id = ja.material_id
            JOIN datasets d ON d.id = m.dataset_id
            WHERE d.name = ?
            GROUP BY ja.judge_name, ja.approach, ja.assessment_status
            ORDER BY ja.judge_name, ja.approach, ja.assessment_status
            """,
            conn,
            params=(dataset_name,),
        )


def load_experiment_coverage(db_path: Path, dataset_name: str) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT
                COALESCE(product_id, product_name, 'unknown') AS product,
                COALESCE(material_type, 'unknown') AS material_type,
                COALESCE(engine, 'unknown') AS engine,
                COALESCE(model, 'unknown') AS model,
                COALESCE(temperature, 'unknown') AS temperature,
                COALESCE(time_of_day_label, 'unknown') AS time_of_day_label,
                COALESCE(scheduled_day_of_week, 'unknown') AS scheduled_day_of_week,
                COUNT(*) AS materials
            FROM materials m
            JOIN datasets d ON d.id = m.dataset_id
            WHERE d.name = ?
            GROUP BY product, material_type, engine, model, temperature, time_of_day_label, scheduled_day_of_week
            ORDER BY product, material_type, engine, model, temperature, time_of_day_label, scheduled_day_of_week
            """,
            conn,
            params=(dataset_name,),
        )


def load_master_queue(db_path: Path, dataset_name: str) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT
                m.material_uid,
                m.product_id,
                m.material_type,
                m.engine,
                m.model,
                m.temperature,
                m.time_of_day_label,
                m.repetition_id,
                m.scheduled_day_of_week,
                rqi.priority_bucket,
                rqi.priority_score,
                rqi.reason,
                rqi.queue_version
            FROM review_queue_items rqi
            JOIN materials m ON m.id = rqi.material_id
            JOIN datasets d ON d.id = m.dataset_id
            WHERE d.name = ?
            ORDER BY rqi.priority_score DESC, m.material_uid
            LIMIT 500
            """,
            conn,
            params=(dataset_name,),
        )


def load_review_candidates(db_path: Path, dataset_name: str) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        df = pd.read_sql_query(
            """
            SELECT
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
                COALESCE(rqi.priority_bucket, 'not_queued') AS priority_bucket,
                COALESCE(rqi.priority_score, 0) AS priority_score,
                COALESCE(rqi.reason, '') AS reason,
                COUNT(DISTINCT hr.id) AS human_review_count
            FROM materials m
            JOIN datasets d ON d.id = m.dataset_id
            LEFT JOIN review_queue_items rqi
                ON rqi.material_id = m.id
               AND rqi.queue_name = 'human_validation_master'
            LEFT JOIN human_reviews hr ON hr.material_id = m.id
            WHERE d.name = ?
            GROUP BY m.id
            ORDER BY priority_score DESC, m.material_uid
            """,
            conn,
            params=(dataset_name,),
        )
    if df.empty:
        return df
    df["select_label"] = df.apply(
        lambda row: (
            f"{row['material_uid']} | {row['product_id'] or row['product_name'] or 'unknown'} | "
            f"{row['material_type'] or 'unknown'} | {row['engine'] or 'unknown'}/{row['model'] or 'unknown'} | "
            f"{row['priority_bucket']} | reviews={row['human_review_count']}"
        ),
        axis=1,
    )
    return df


def load_material_detail(db_path: Path, material_id: int) -> sqlite3.Row:
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM materials
            WHERE id = ?
            """,
            (material_id,),
        ).fetchone()
    if row is None:
        raise RuntimeError(f"Material id={material_id} not found.")
    return row


def load_machine_signals(db_path: Path, material_id: int) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT
                judge_name,
                approach,
                judge_model,
                assessment_status,
                is_noncompliant,
                violation_count,
                max_severity,
                raw_label,
                rationale,
                assessed_at
            FROM judge_assessments
            WHERE material_id = ?
            ORDER BY judge_name, approach
            """,
            conn,
            params=(material_id,),
        )


def load_reviews(db_path: Path, material_id: int) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT
                reviewer_id,
                review_round,
                rubric_version,
                decision_status,
                review_status,
                violation_count,
                max_severity,
                defer_reason,
                review_duration_sec,
                blind_to_machine_labels,
                reviewed_at,
                rationale
            FROM human_reviews
            WHERE material_id = ?
            ORDER BY reviewed_at DESC
            """,
            conn,
            params=(material_id,),
        )


def load_review_coverage(db_path: Path, dataset_name: str) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT
                COALESCE(m.product_id, m.product_name, 'unknown') AS product,
                COALESCE(m.material_type, 'unknown') AS material_type,
                COALESCE(m.engine, 'unknown') AS engine,
                COALESCE(m.model, 'unknown') AS model,
                COALESCE(m.temperature, 'unknown') AS temperature,
                COALESCE(m.time_of_day_label, 'unknown') AS time_of_day_label,
                COALESCE(m.scheduled_day_of_week, 'unknown') AS scheduled_day_of_week,
                COUNT(DISTINCT m.id) AS materials,
                COUNT(DISTINCT hr.id) AS human_reviews,
                COUNT(DISTINCT ad.id) AS adjudications,
                SUM(CASE WHEN hr.review_status = 'non_compliant' THEN 1 ELSE 0 END) AS human_non_compliant,
                SUM(CASE WHEN hr.review_status = 'inconclusive' THEN 1 ELSE 0 END) AS human_inconclusive
            FROM materials m
            JOIN datasets d ON d.id = m.dataset_id
            LEFT JOIN human_reviews hr ON hr.material_id = m.id
            LEFT JOIN adjudications ad ON ad.material_id = m.id
            WHERE d.name = ?
            GROUP BY product, material_type, engine, model, temperature, time_of_day_label, scheduled_day_of_week
            HAVING human_reviews > 0 OR adjudications > 0
            ORDER BY product, material_type, engine, model, temperature, time_of_day_label, scheduled_day_of_week
            """,
            conn,
            params=(dataset_name,),
        )


def load_adjudication_candidates(db_path: Path, dataset_name: str) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        df = pd.read_sql_query(
            """
            SELECT
                m.id AS material_id,
                m.material_uid,
                m.product_id,
                m.material_type,
                m.engine,
                m.model,
                COUNT(DISTINCT hr.id) AS review_count,
                COUNT(DISTINCT hr.review_status) AS status_count,
                GROUP_CONCAT(DISTINCT hr.review_status) AS statuses
            FROM materials m
            JOIN datasets d ON d.id = m.dataset_id
            JOIN human_reviews hr ON hr.material_id = m.id
            WHERE d.name = ?
            GROUP BY m.id
            HAVING review_count >= 2 OR status_count >= 2
            ORDER BY status_count DESC, review_count DESC, m.material_uid
            """,
            conn,
            params=(dataset_name,),
        )
    if df.empty:
        return df
    df["select_label"] = df.apply(
        lambda row: (
            f"{row['material_uid']} | {row['product_id'] or 'unknown'} | {row['material_type'] or 'unknown'} | "
            f"{row['engine'] or 'unknown'}/{row['model'] or 'unknown'} | reviews={row['review_count']} | {row['statuses']}"
        ),
        axis=1,
    )
    return df


def load_existing_adjudication(db_path: Path, material_id: int) -> pd.DataFrame:
    with get_connection(db_path) as conn:
        return pd.read_sql_query(
            """
            SELECT
                adjudicator_id,
                adjudicated_at,
                final_status,
                violation_count,
                max_severity,
                resolution_source,
                rationale
            FROM adjudications
            WHERE material_id = ?
            """,
            conn,
            params=(material_id,),
        )


def show_material_panel(material: sqlite3.Row) -> None:
    meta_cols = st.columns(4)
    meta_cols[0].metric("Product", material["product_id"] or material["product_name"] or "unknown")
    meta_cols[1].metric("Material Type", material["material_type"] or "unknown")
    meta_cols[2].metric("Model", f"{material['engine'] or 'unknown'} / {material['model'] or 'unknown'}")
    meta_cols[3].metric("Temporal", f"{material['time_of_day_label'] or 'unknown'} / {material['scheduled_day_of_week'] or 'unknown'}")

    with st.expander("Prompt", expanded=False):
        st.write(material["prompt"] or "")
    left, right = st.columns(2)
    with left:
        st.markdown("#### Material Text")
        st.text_area("Generated material", value=material["material_text"] or "", height=260, disabled=True)
    with right:
        st.markdown("#### Product Ground Truth")
        st.text_area("Ground truth", value=material["product_ground_truth"] or "", height=260, disabled=True)


def show_machine_signals(db_path: Path, material_id: int) -> None:
    st.markdown("#### Machine Signals")
    signals = load_machine_signals(db_path, material_id)
    if signals.empty:
        st.info("No machine signals imported for this material.")
    else:
        st.dataframe(signals, use_container_width=True, hide_index=True)


def show_existing_reviews(db_path: Path, material_id: int) -> None:
    st.markdown("#### Existing Human Reviews")
    reviews = load_reviews(db_path, material_id)
    if reviews.empty:
        st.info("No human reviews saved yet.")
    else:
        st.dataframe(reviews, use_container_width=True, hide_index=True)


def show_existing_adjudication(db_path: Path, material_id: int) -> None:
    st.markdown("#### Existing Adjudication")
    adjudication = load_existing_adjudication(db_path, material_id)
    if adjudication.empty:
        st.info("No adjudication saved yet.")
    else:
        st.dataframe(adjudication, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
