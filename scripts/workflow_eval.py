#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd


DEFAULT_DB_PATH = Path("data/youtube_comments.db")
DEFAULT_OUT_DIR = Path("outputs")
DEFAULT_FREEZE_NAME = "KES-final"
RNG_SEED = 20260420


def _placeholders(n: int) -> str:
    return ",".join(["?"] * n)


def _load_freeze(conn: sqlite3.Connection, freeze_name: str) -> dict[str, object]:
    row = conn.execute(
        """
        SELECT
            id,
            freeze_uuid,
            name,
            created_at,
            run_ids_json,
            summary_json
        FROM evidence_freezes
        WHERE name = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (freeze_name.strip(),),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Freeze `{freeze_name}` not found in evidence_freezes.")

    run_ids = json.loads(row["run_ids_json"]) if row["run_ids_json"] else []
    if not isinstance(run_ids, list) or not run_ids:
        raise RuntimeError(f"Freeze `{freeze_name}` has empty run_ids_json.")
    summary = json.loads(row["summary_json"]) if row["summary_json"] else {}
    if not isinstance(summary, dict):
        summary = {}
    return {
        "freeze_id": int(row["id"]),
        "freeze_uuid": str(row["freeze_uuid"] or ""),
        "freeze_name": str(row["name"] or ""),
        "freeze_timestamp": str(row["created_at"] or ""),
        "run_ids": [int(x) for x in run_ids],
        "summary": summary,
    }


def _resolved_labels_for_runs(conn: sqlite3.Connection, run_ids: list[int]) -> pd.DataFrame:
    placeholders = _placeholders(len(run_ids))
    q = f"""
    WITH per_comment AS (
        SELECT
            a.comment_db_id,
            COUNT(DISTINCT a.annotator_id) AS coder_count,
            MAX(a.is_adjudicated) AS has_adjudicated,
            MIN(a.skepticism_fake_callout) AS min_skepticism,
            MAX(a.skepticism_fake_callout) AS max_skepticism,
            MIN(a.proof_demand) AS min_proof_demand,
            MAX(a.proof_demand) AS max_proof_demand,
            MIN(a.normalization_defense) AS min_normalization,
            MAX(a.normalization_defense) AS max_normalization
        FROM annotations a
        JOIN comments c ON c.id = a.comment_db_id
        WHERE c.run_id IN ({placeholders})
        GROUP BY a.comment_db_id
    ),
    ranked AS (
        SELECT
            a.comment_db_id,
            a.skepticism_fake_callout AS label_skepticism,
            a.proof_demand AS label_proof_demand,
            a.normalization_defense AS label_normalization,
            ROW_NUMBER() OVER (
                PARTITION BY a.comment_db_id
                ORDER BY
                    CASE
                        WHEN pc.coder_count >= 2 AND pc.has_adjudicated = 1 AND a.is_adjudicated = 1 THEN 0
                        WHEN pc.coder_count >= 2
                             AND pc.has_adjudicated = 0
                             AND pc.min_skepticism = pc.max_skepticism
                             AND pc.min_proof_demand = pc.max_proof_demand
                             AND pc.min_normalization = pc.max_normalization THEN 1
                        ELSE 2
                    END,
                    a.is_adjudicated DESC,
                    a.coded_at DESC,
                    a.id DESC
            ) AS rn
        FROM annotations a
        JOIN comments c ON c.id = a.comment_db_id
        JOIN per_comment pc ON pc.comment_db_id = a.comment_db_id
        WHERE c.run_id IN ({placeholders})
    )
    SELECT
        comment_db_id,
        label_skepticism,
        label_proof_demand,
        label_normalization
    FROM ranked
    WHERE rn = 1
      AND comment_db_id IN (
          SELECT comment_db_id
          FROM per_comment
          WHERE coder_count >= 2
            AND (
                has_adjudicated = 1
                OR (
                    min_skepticism = max_skepticism
                    AND min_proof_demand = max_proof_demand
                    AND min_normalization = max_normalization
                )
            )
      )
    ORDER BY comment_db_id
    """
    df = pd.read_sql_query(q, conn, params=tuple(run_ids) + tuple(run_ids))
    if df.empty:
        return df
    for col in ["label_skepticism", "label_proof_demand", "label_normalization"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["any_core_positive"] = (
        (df["label_skepticism"] == 1)
        | (df["label_proof_demand"] == 1)
        | (df["label_normalization"] == 1)
    ).astype(int)
    return df


def _comment_disagreement_flags(conn: sqlite3.Connection, run_ids: list[int]) -> pd.DataFrame:
    placeholders = _placeholders(len(run_ids))
    q = f"""
    SELECT
        a.comment_db_id,
        CASE
            WHEN COUNT(DISTINCT a.annotator_id) >= 2
             AND (
                 MIN(COALESCE(a.skepticism_fake_callout, 0)) <> MAX(COALESCE(a.skepticism_fake_callout, 0))
                 OR MIN(COALESCE(a.proof_demand, 0)) <> MAX(COALESCE(a.proof_demand, 0))
                 OR MIN(COALESCE(a.normalization_defense, 0)) <> MAX(COALESCE(a.normalization_defense, 0))
                 OR MIN(COALESCE(a.other_flag, 0)) <> MAX(COALESCE(a.other_flag, 0))
                 OR MIN(COALESCE(a.extra_codes, '')) <> MAX(COALESCE(a.extra_codes, ''))
             )
            THEN 1 ELSE 0
        END AS any_disagreement
    FROM annotations a
    JOIN comments c ON c.id = a.comment_db_id
    WHERE c.run_id IN ({placeholders})
    GROUP BY a.comment_db_id
    """
    return pd.read_sql_query(q, conn, params=tuple(run_ids))


def _priority_instrumented_rows(conn: sqlite3.Connection, run_ids: list[int]) -> pd.DataFrame:
    placeholders = _placeholders(len(run_ids))
    q = f"""
    SELECT
        a.id AS annotation_id,
        a.comment_db_id,
        c.run_id,
        ch.niche AS channel_niche,
        c.comment_rank,
        c.like_count,
        c.reply_count,
        a.annotator_id,
        a.coded_at,
        COALESCE(a.workflow_mode, '') AS workflow_mode,
        COALESCE(a.priority_bucket, '') AS priority_bucket,
        a.priority_score,
        COALESCE(a.triage_bucket, '') AS triage_bucket,
        a.triage_score
    FROM annotations a
    JOIN comments c ON c.id = a.comment_db_id
    JOIN channels ch ON ch.id = c.channel_db_id
    WHERE c.run_id IN ({placeholders})
      AND a.priority_score IS NOT NULL
    """
    df = pd.read_sql_query(q, conn, params=tuple(run_ids))
    if df.empty:
        return df
    df["coded_at"] = pd.to_datetime(df["coded_at"], errors="coerce", utc=True)
    df = df.sort_values(
        ["comment_db_id", "coded_at", "annotation_id"],
        ascending=[True, True, True],
        kind="mergesort",
    )
    # Use the earliest priority-scored touch per comment as the queue signal.
    df = df.drop_duplicates(subset=["comment_db_id"], keep="first").reset_index(drop=True)
    return df


def _review_depth_for_positive_share(is_positive: np.ndarray, share: float) -> int:
    total_pos = int(is_positive.sum())
    if total_pos <= 0:
        return 0
    target = max(1, int(math.ceil(total_pos * float(share))))
    cum = np.cumsum(is_positive.astype(int))
    reached = np.where(cum >= target)[0]
    if len(reached) == 0:
        return int(len(is_positive))
    return int(reached[0] + 1)


def _fmt(value: float | int | str | None, *, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, str):
        return value
    if isinstance(value, int):
        return str(value)
    if pd.isna(value):
        return "n/a"
    return f"{float(value):.{digits}f}"


def run_workflow_eval(
    *,
    db_path: Path,
    out_dir: Path,
    freeze_name: str,
    top_share: float,
    target_positive_share: float,
    random_simulations: int,
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        freeze = _load_freeze(conn, freeze_name)
        run_ids = list(freeze["run_ids"])
        resolved = _resolved_labels_for_runs(conn, run_ids)
        instrumented = _priority_instrumented_rows(conn, run_ids)
        disagreements = _comment_disagreement_flags(conn, run_ids)
    finally:
        conn.close()

    if resolved.empty or instrumented.empty:
        summary = pd.DataFrame(
            [
                {"metric": "status", "value": "insufficient_data"},
                {"metric": "resolved_rows", "value": int(len(resolved))},
                {"metric": "instrumented_rows", "value": int(len(instrumented))},
            ]
        )
        summary.to_csv(out_dir / "workflow_eval_summary.csv", index=False)
        (out_dir / "workflow_eval_table.md").write_text(
            "| Metric | Value |\n|---|---|\n| status | insufficient_data |\n",
            encoding="utf-8",
        )
        (out_dir / "workflow_eval_notes.md").write_text(
            "Insufficient overlap between resolved labels and priority-instrumented rows; generated descriptive status only.\n",
            encoding="utf-8",
        )
        return {
            "status": "insufficient_data",
            "freeze": freeze,
            "resolved_rows": len(resolved),
            "instrumented_rows": len(instrumented),
        }

    df = instrumented.merge(
        resolved[["comment_db_id", "any_core_positive"]],
        on="comment_db_id",
        how="inner",
    )
    if not disagreements.empty:
        df = df.merge(disagreements, on="comment_db_id", how="left")
        df["any_disagreement"] = pd.to_numeric(df["any_disagreement"], errors="coerce").fillna(0).astype(int)
    else:
        df["any_disagreement"] = 0

    df["priority_score"] = pd.to_numeric(df["priority_score"], errors="coerce")
    df = df[df["priority_score"].notna()].copy()
    df["is_positive"] = pd.to_numeric(df["any_core_positive"], errors="coerce").fillna(0).astype(int)
    if df.empty:
        raise RuntimeError("No usable rows after joining resolved labels with instrumented priority rows.")

    n_rows = int(len(df))
    n_pos = int(df["is_positive"].sum())
    n_top = max(1, int(math.ceil(float(top_share) * n_rows)))

    ranked = df.sort_values(
        ["priority_score", "comment_db_id"],
        ascending=[False, True],
        kind="mergesort",
    ).reset_index(drop=True)
    ranked["priority_rank"] = ranked.index + 1
    ranked["in_top_priority_slice"] = (ranked["priority_rank"] <= n_top).astype(int)

    top_df = ranked[ranked["in_top_priority_slice"] == 1]
    rest_df = ranked[ranked["in_top_priority_slice"] == 0]

    top_pos = int(top_df["is_positive"].sum())
    rest_pos = int(rest_df["is_positive"].sum())
    top_rate = float(top_df["is_positive"].mean()) if len(top_df) else float("nan")
    rest_rate = float(rest_df["is_positive"].mean()) if len(rest_df) else float("nan")
    lift = (top_rate / rest_rate) if (pd.notna(top_rate) and pd.notna(rest_rate) and rest_rate > 0) else float("nan")
    capture_top = (top_pos / n_pos) if n_pos > 0 else float("nan")
    disagreement_top = float(top_df["any_disagreement"].mean()) if len(top_df) else float("nan")
    disagreement_rest = float(rest_df["any_disagreement"].mean()) if len(rest_df) else float("nan")

    priority_depth = _review_depth_for_positive_share(
        ranked["is_positive"].to_numpy(dtype=int),
        target_positive_share,
    )

    rng = np.random.default_rng(RNG_SEED)
    random_depths = []
    positive_array = ranked["is_positive"].to_numpy(dtype=int)
    for _ in range(int(random_simulations)):
        perm = rng.permutation(positive_array)
        random_depths.append(_review_depth_for_positive_share(perm, target_positive_share))
    random_depths_arr = np.array(random_depths, dtype=float)
    random_mean_depth = float(random_depths_arr.mean()) if len(random_depths_arr) else float("nan")
    random_p05_depth = float(np.quantile(random_depths_arr, 0.05)) if len(random_depths_arr) else float("nan")
    random_p95_depth = float(np.quantile(random_depths_arr, 0.95)) if len(random_depths_arr) else float("nan")
    burden_reduction = (
        1.0 - (float(priority_depth) / random_mean_depth)
        if pd.notna(random_mean_depth) and random_mean_depth > 0
        else float("nan")
    )

    summary_rows = [
        {"metric": "freeze_name", "value": freeze["freeze_name"]},
        {"metric": "freeze_id", "value": int(freeze["freeze_id"])},
        {"metric": "freeze_uuid", "value": freeze["freeze_uuid"]},
        {"metric": "run_ids", "value": ", ".join(str(x) for x in run_ids)},
        {"metric": "instrumented_rows", "value": n_rows},
        {"metric": "instrumented_positive_rows", "value": n_pos},
        {"metric": "top_priority_rows", "value": n_top},
        {"metric": "top_priority_positive_rows", "value": top_pos},
        {"metric": "top_priority_positive_rate", "value": top_rate},
        {"metric": "rest_positive_rate", "value": rest_rate},
        {"metric": "priority_lift_top_vs_rest", "value": lift},
        {"metric": "positive_capture_in_top_slice", "value": capture_top},
        {"metric": "disagreement_rate_top_slice", "value": disagreement_top},
        {"metric": "disagreement_rate_rest_slice", "value": disagreement_rest},
        {"metric": "target_positive_share", "value": float(target_positive_share)},
        {"metric": "priority_review_depth_for_target_share", "value": int(priority_depth)},
        {"metric": "random_mean_review_depth_for_target_share", "value": random_mean_depth},
        {"metric": "random_p05_review_depth", "value": random_p05_depth},
        {"metric": "random_p95_review_depth", "value": random_p95_depth},
        {"metric": "review_burden_reduction_vs_random", "value": burden_reduction},
        {"metric": "random_simulations", "value": int(random_simulations)},
        {"metric": "random_seed", "value": int(RNG_SEED)},
    ]
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(out_dir / "workflow_eval_summary.csv", index=False)
    ranked.to_csv(out_dir / "workflow_eval_instrumented_comments.csv", index=False)

    table_lines = [
        "| Metric | Value |",
        "|---|---|",
        f"| Instrumented comments (with priority + resolved label) | {n_rows} |",
        f"| Instrumented positives | {n_pos} |",
        f"| Top-priority review slice (top {int(round(top_share * 100))}%) | {n_top} |",
        f"| Positive rate in top slice | {_fmt(top_rate)} |",
        f"| Positive rate in remainder | {_fmt(rest_rate)} |",
        f"| Priority lift (top vs remainder) | {_fmt(lift)} |",
        f"| Positive capture in top slice | {_fmt(capture_top)} |",
        f"| Reviews needed for {int(round(target_positive_share * 100))}% positives (priority order) | {priority_depth} |",
        f"| Reviews needed for {int(round(target_positive_share * 100))}% positives (random mean) | {_fmt(random_mean_depth)} |",
        f"| Random review depth 5th-95th percentile | {_fmt(random_p05_depth)} to {_fmt(random_p95_depth)} |",
        f"| Review-burden reduction vs random | {_fmt(burden_reduction)} |",
        f"| Disagreement rate in top slice | {_fmt(disagreement_top)} |",
        f"| Disagreement rate in remainder | {_fmt(disagreement_rest)} |",
    ]
    (out_dir / "workflow_eval_table.md").write_text("\n".join(table_lines) + "\n", encoding="utf-8")

    methods_paragraph = (
        "Workflow evaluation used freeze-scoped resolved labels only and did not treat assistive outputs as ground truth. "
        "We selected comments that had recorded annotation priority scores, kept the earliest priority-scored touch per comment, "
        "and compared top-priority versus remainder yield on the resolved any-core-positive outcome. "
        "As a practical review-effort proxy, we computed how many reviews are needed to recover 80% of positives under priority order "
        "and under random ordering using a fixed-seed Monte Carlo simulation."
    )
    results_paragraph = (
        f"In the instrumented subset (n={n_rows}, positives={n_pos}), the top-priority slice (n={n_top}) had a positive rate of {_fmt(top_rate)} "
        f"versus {_fmt(rest_rate)} in the remainder (lift={_fmt(lift)}), capturing {_fmt(capture_top)} of all positives in this subset. "
        f"To recover 80% of positives, priority ordering required {priority_depth} reviews versus a random-order mean of {_fmt(random_mean_depth)} "
        f"(5th-95th percentile {_fmt(random_p05_depth)} to {_fmt(random_p95_depth)}), implying a review-burden reduction of {_fmt(burden_reduction)}."
    )
    limitation_sentence = (
        "This metric is limited to comments with recorded priority traces and should be interpreted as an instrumented-subset workflow signal rather than a full-corpus benchmark."
    )

    notes_lines = [
        "# Workflow Evaluation Notes",
        "",
        f"- Freeze: `{freeze['freeze_name']}` (id={freeze['freeze_id']}, uuid={freeze['freeze_uuid']})",
        f"- Run scope: `{', '.join(str(x) for x in run_ids)}`",
        f"- Random baseline seed: `{RNG_SEED}`",
        f"- Random simulations: `{int(random_simulations)}`",
        "",
        "## Methods paragraph (paper-ready)",
        "",
        methods_paragraph,
        "",
        "## Results paragraph (paper-ready)",
        "",
        results_paragraph,
        "",
        "## Limitation sentence (paper-ready)",
        "",
        limitation_sentence,
        "",
        "## Interpretation guardrail",
        "",
        "Use this as a practical workflow-value signal for the instrumented queueing subset only. "
        "Do not interpret it as classifier accuracy or as evidence that assistive labels replace human validation.",
    ]
    (out_dir / "workflow_eval_notes.md").write_text("\n".join(notes_lines) + "\n", encoding="utf-8")

    return {
        "status": "ok",
        "freeze": freeze,
        "instrumented_rows": n_rows,
        "instrumented_positives": n_pos,
        "top_rows": n_top,
        "top_rate": top_rate,
        "rest_rate": rest_rate,
        "lift": lift,
        "capture_top": capture_top,
        "priority_depth": priority_depth,
        "random_mean_depth": random_mean_depth,
        "random_p05_depth": random_p05_depth,
        "random_p95_depth": random_p95_depth,
        "burden_reduction": burden_reduction,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute freeze-scoped workflow evaluation metrics.")
    parser.add_argument("--db-path", default=str(DEFAULT_DB_PATH))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--freeze-name", default=DEFAULT_FREEZE_NAME)
    parser.add_argument("--top-share", type=float, default=0.25, help="Top priority share for lift comparison.")
    parser.add_argument(
        "--target-positive-share",
        type=float,
        default=0.80,
        help="Positive-capture share for review-burden proxy.",
    )
    parser.add_argument(
        "--random-simulations",
        type=int,
        default=5000,
        help="Number of random-order simulations for review-burden proxy.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_workflow_eval(
        db_path=Path(args.db_path),
        out_dir=Path(args.out_dir),
        freeze_name=str(args.freeze_name),
        top_share=float(args.top_share),
        target_positive_share=float(args.target_positive_share),
        random_simulations=int(args.random_simulations),
    )
    print("workflow_eval status:", result.get("status"))
    if result.get("status") == "ok":
        print(
            "instrumented_rows=",
            result.get("instrumented_rows"),
            "lift=",
            result.get("lift"),
            "burden_reduction=",
            result.get("burden_reduction"),
        )


if __name__ == "__main__":
    main()
