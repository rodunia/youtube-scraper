#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

import pandas as pd


DEFAULT_OUT_DIR = Path("outputs")


def build_comparison_table() -> pd.DataFrame:
    rows = [
        {
            "feature": "Double coding support",
            "fully_manual_coding_pipeline": "Partial",
            "generic_annotation_interface": "Partial",
            "ai_assisted_no_strict_freeze_separation": "Partial",
            "this_evidence_governed_workflow": "Yes",
            "support_note": "Implemented in annotation workflow and freeze readiness checks.",
        },
        {
            "feature": "Explicit disagreement detection",
            "fully_manual_coding_pipeline": "Partial",
            "generic_annotation_interface": "Partial",
            "ai_assisted_no_strict_freeze_separation": "Partial",
            "this_evidence_governed_workflow": "Yes",
            "support_note": "Computed per comment from coder divergence across core labels.",
        },
        {
            "feature": "Adjudication trace fields",
            "fully_manual_coding_pipeline": "Partial",
            "generic_annotation_interface": "Partial",
            "ai_assisted_no_strict_freeze_separation": "Partial",
            "this_evidence_governed_workflow": "Yes",
            "support_note": "Annotations schema includes adjudication and resolution metadata.",
        },
        {
            "feature": "Frozen validated evidence layer",
            "fully_manual_coding_pipeline": "No",
            "generic_annotation_interface": "No",
            "ai_assisted_no_strict_freeze_separation": "No",
            "this_evidence_governed_workflow": "Yes",
            "support_note": "Named evidence freezes persisted with run scope and summary JSON.",
        },
        {
            "feature": "Explicit exploratory layer kept separate from confirmatory claims",
            "fully_manual_coding_pipeline": "No",
            "generic_annotation_interface": "No",
            "ai_assisted_no_strict_freeze_separation": "No",
            "this_evidence_governed_workflow": "Yes",
            "support_note": "UI/workflow language and export paths distinguish validated vs exploratory outputs.",
        },
        {
            "feature": "Assistive logic visible but non-binding",
            "fully_manual_coding_pipeline": "No",
            "generic_annotation_interface": "No",
            "ai_assisted_no_strict_freeze_separation": "Partial",
            "this_evidence_governed_workflow": "Yes",
            "support_note": "Triage/priority hints are displayed but manual labels and adjudication remain human-decided.",
        },
        {
            "feature": "Versioned deterministic rules/scoring metadata",
            "fully_manual_coding_pipeline": "No",
            "generic_annotation_interface": "No",
            "ai_assisted_no_strict_freeze_separation": "Partial",
            "this_evidence_governed_workflow": "Yes",
            "support_note": "Rules/scoring/preprocessing versions recorded in freeze and export metadata.",
        },
        {
            "feature": "Freeze-linked export provenance",
            "fully_manual_coding_pipeline": "No",
            "generic_annotation_interface": "No",
            "ai_assisted_no_strict_freeze_separation": "Partial",
            "this_evidence_governed_workflow": "Yes",
            "support_note": "Exports table stores export type, timestamp, and linked freeze_id.",
        },
        {
            "feature": "Run-level collection/provenance metadata",
            "fully_manual_coding_pipeline": "No",
            "generic_annotation_interface": "No",
            "ai_assisted_no_strict_freeze_separation": "Partial",
            "this_evidence_governed_workflow": "Yes",
            "support_note": "Runs/videos/comments tables capture extraction engine, statuses, and QA payloads.",
        },
        {
            "feature": "Auditable resolution path from coding to freeze",
            "fully_manual_coding_pipeline": "Partial",
            "generic_annotation_interface": "Partial",
            "ai_assisted_no_strict_freeze_separation": "Partial",
            "this_evidence_governed_workflow": "Yes",
            "support_note": "Resolved consensus logic plus freeze snapshots and export records provide auditable linkage.",
        },
    ]
    return pd.DataFrame(rows)


def _write_markdown(df: pd.DataFrame, path: Path) -> None:
    header = [
        "| Feature | Fully manual coding pipeline | Generic annotation interface | AI-assisted workflow without strict freeze separation | This evidence-governed workflow |",
        "|---|---|---|---|---|",
    ]
    body = []
    for _, row in df.iterrows():
        body.append(
            "| "
            + " | ".join(
                [
                    str(row["feature"]),
                    str(row["fully_manual_coding_pipeline"]),
                    str(row["generic_annotation_interface"]),
                    str(row["ai_assisted_no_strict_freeze_separation"]),
                    str(row["this_evidence_governed_workflow"]),
                ]
            )
            + " |"
        )
    path.write_text("\n".join(header + body) + "\n", encoding="utf-8")


def _write_notes(path: Path) -> None:
    paragraph = (
        "Table X compares workflow-governance capabilities rather than model accuracy. "
        "The first three columns are reference archetypes (typical patterns that can vary by implementation), "
        "while the final column reports capabilities implemented in this repository. "
        "The main contribution is the integrated evidence-governance path: double coding, explicit disagreement detection, "
        "human adjudication, freeze-scoped validated evidence, and freeze-linked exports with versioned assistive logic metadata."
    )
    caption = (
        "Table X. Workflow-governance comparison across reference pipeline archetypes and the evidence-governed research console."
    )
    caution = (
        "Caution: This is not a benchmark table. It documents architectural and governance differences; "
        "non-repo archetype cells are conservative reference characterizations and may vary in specific tools."
    )
    path.write_text(
        "\n".join(
            [
                "# Workflow Comparison Notes",
                "",
                "## Paragraph (paper-ready)",
                "",
                paragraph,
                "",
                "## Caption (paper-ready)",
                "",
                caption,
                "",
                "## Scope note",
                "",
                caution,
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    out_dir = DEFAULT_OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    df = build_comparison_table()
    df.to_csv(out_dir / "workflow_comparison_table.csv", index=False)
    _write_markdown(df, out_dir / "workflow_comparison_table.md")
    _write_notes(out_dir / "workflow_comparison_notes.md")
    print("workflow_comparison rows:", len(df))


if __name__ == "__main__":
    main()
