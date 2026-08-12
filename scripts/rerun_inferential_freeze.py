#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from dataclasses import dataclass
from math import exp
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import norm
from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM


DEFAULT_DB_PATH = Path("data/youtube_comments.db")
DEFAULT_OUT_DIR = Path("outputs/inferential_rerun_freeze10")
DEFAULT_BASELINE_RESPONSE = Path("data/conformity_response_17videos_2026-04-03.csv")
DEFAULT_BASELINE_EFFECTS = Path("data/conformity_effects_17videos_2026-04-03.csv")

EXPECTED_FREEZE_ID = 10
EXPECTED_FREEZE_UUID = "freeze-20260422T131415Z"
EXPECTED_FREEZE_NAME = "freeze-20-4a"


@dataclass(frozen=True)
class FreezeSpec:
    freeze_id: int
    freeze_uuid: str
    freeze_name: str
    created_by: str
    created_at: str
    run_ids: tuple[int, ...]
    summary: dict[str, Any]


def _placeholders(n: int) -> str:
    return ",".join(["?"] * n)


def _zscore(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    mean = float(numeric.mean()) if len(numeric) else 0.0
    std = float(numeric.std(ddof=0)) if len(numeric) else 0.0
    if std <= 0:
        return pd.Series(0.0, index=series.index)
    return (numeric - mean) / std


def load_freeze(conn: sqlite3.Connection, freeze_id: int) -> FreezeSpec:
    row = conn.execute(
        """
        SELECT id, freeze_uuid, name, created_by, created_at, run_ids_json, summary_json
        FROM evidence_freezes
        WHERE id = ?
        """,
        (int(freeze_id),),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Freeze id={freeze_id} not found.")

    run_ids_raw = json.loads(row["run_ids_json"]) if row["run_ids_json"] else []
    if not isinstance(run_ids_raw, list) or not run_ids_raw:
        raise RuntimeError(f"Freeze id={freeze_id} has empty run_ids_json.")
    summary_raw = json.loads(row["summary_json"]) if row["summary_json"] else {}
    if not isinstance(summary_raw, dict):
        summary_raw = {}
    return FreezeSpec(
        freeze_id=int(row["id"]),
        freeze_uuid=str(row["freeze_uuid"] or ""),
        freeze_name=str(row["name"] or ""),
        created_by=str(row["created_by"] or ""),
        created_at=str(row["created_at"] or ""),
        run_ids=tuple(int(x) for x in run_ids_raw),
        summary=summary_raw,
    )


def _freeze_comments(conn: sqlite3.Connection, run_ids: tuple[int, ...]) -> pd.DataFrame:
    ph = _placeholders(len(run_ids))
    q = f"""
    SELECT
        c.id AS comment_db_id,
        c.run_id,
        ch.channel_id,
        ch.niche AS channel_niche,
        v.video_id,
        c.comment_rank,
        c.like_count,
        c.reply_count,
        c.published_at AS comment_timestamp,
        c.cleaned_text,
        c.is_spam,
        c.is_template,
        c.is_duplicate
    FROM comments c
    JOIN channels ch ON c.channel_db_id = ch.id
    JOIN videos v ON c.video_db_id = v.id
    WHERE c.run_id IN ({ph})
    """
    return pd.read_sql_query(q, conn, params=run_ids)


def _resolved_labels(conn: sqlite3.Connection, run_ids: tuple[int, ...]) -> pd.DataFrame:
    ph = _placeholders(len(run_ids))
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
        WHERE c.run_id IN ({ph})
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
        WHERE c.run_id IN ({ph})
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
    """
    return pd.read_sql_query(q, conn, params=run_ids + run_ids)


def _reference_niche(response_df: pd.DataFrame) -> str:
    levels = sorted(
        {
            str(v).strip()
            for v in response_df["channel_niche"].dropna().tolist()
            if str(v).strip()
        }
    )
    if not levels:
        raise RuntimeError("channel_niche has no usable levels.")
    if "Lifestyle" in levels:
        return "Lifestyle"
    return levels[0]


def _fit_model(response_df: pd.DataFrame) -> tuple[Any, Any, str]:
    if response_df.empty:
        raise RuntimeError("Response dataframe is empty after exclusions.")
    if response_df["is_skeptical"].nunique() < 2:
        raise RuntimeError(
            "Dependent variable has no variation. "
            f"is_skeptical counts={response_df['is_skeptical'].value_counts(dropna=False).to_dict()}"
        )
    if response_df["top_comment_skeptical"].nunique() < 2:
        raise RuntimeError(
            "Main predictor has no variation. "
            f"top_comment_skeptical counts={response_df['top_comment_skeptical'].value_counts(dropna=False).to_dict()}"
        )
    reference = _reference_niche(response_df)
    formula = (
        "is_skeptical ~ "
        f"top_comment_skeptical * C(channel_niche, Treatment(reference='{reference}')) + "
        "top_comment_skeptical * top_comment_like_count_z + "
        "top_comment_skeptical * hours_since_top_comment_z + "
        "top_comment_like_count_z + hours_since_top_comment_z"
    )
    vc_formulas = {
        "channel_re": "0 + C(channel_id)",
        "video_re": "0 + C(video_id)",
    }
    model = BinomialBayesMixedGLM.from_formula(formula, vc_formulas, response_df)
    fit = model.fit_vb()
    return model, fit, formula


def _effects_table(model: Any, fit: Any) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for i, term in enumerate(model.exog_names):
        beta = float(fit.fe_mean[i])
        sd = float(fit.fe_sd[i])
        z = beta / sd if sd > 0 else float("nan")
        p = float(2.0 * norm.sf(abs(z))) if np.isfinite(z) else float("nan")
        low = beta - 1.96 * sd
        high = beta + 1.96 * sd
        rows.append(
            {
                "term": term,
                "coef_log_odds": beta,
                "sd": sd,
                "z_approx": z,
                "p_value_approx": p,
                "odds_ratio": exp(beta),
                "or_ci_95_low": exp(low),
                "or_ci_95_high": exp(high),
            }
        )
    return pd.DataFrame(rows)


def _forest_plot(effects_df: pd.DataFrame, out_path: Path) -> None:
    view = effects_df[effects_df["term"] != "Intercept"].copy()
    if view.empty:
        return
    view = view.sort_values("odds_ratio", ascending=True).reset_index(drop=True)
    y = np.arange(len(view))

    fig_h = max(4.0, len(view) * 0.35)
    plt.figure(figsize=(11, fig_h))
    for i, row in view.iterrows():
        color = "#1f5a8a" if float(row["p_value_approx"]) < 0.05 else "#8ea6ba"
        plt.plot([row["or_ci_95_low"], row["or_ci_95_high"]], [i, i], color=color, linewidth=2)
        plt.scatter([row["odds_ratio"]], [i], color=color, s=40, zorder=3)
    plt.axvline(1.0, color="#666666", linestyle="--", linewidth=1)
    plt.xscale("log")
    plt.yticks(y, view["term"].tolist())
    plt.xlabel("Odds ratio (log scale)")
    plt.title("Freeze-Scoped Cue-Response Model Effects")
    plt.tight_layout()
    plt.savefig(out_path, dpi=180)
    plt.close()


def _crosstab(response_df: pd.DataFrame) -> pd.DataFrame:
    tab = (
        response_df.groupby("top_comment_skeptical", as_index=False)
        .agg(
            response_rows=("video_id", "count"),
            skeptical_rows=("is_skeptical", "sum"),
            skepticism_rate=("is_skeptical", "mean"),
            unique_videos=("video_id", "nunique"),
        )
        .sort_values("top_comment_skeptical", ascending=False)
        .reset_index(drop=True)
    )
    tab["cue_group"] = tab["top_comment_skeptical"].map(
        {1: "skeptical top cue", 0: "non-skeptical top cue"}
    )
    return tab


def _baseline_metrics(response_csv: Path, effects_csv: Path | None) -> dict[str, Any]:
    baseline: dict[str, Any] = {
        "baseline_response_source": str(response_csv),
        "baseline_effects_source": str(effects_csv) if effects_csv else "",
    }
    if not response_csv.exists():
        baseline["available"] = False
        baseline["error"] = "baseline_response_csv_not_found"
        return baseline

    df = pd.read_csv(response_csv)
    required = {"video_id", "top_comment_skeptical", "is_skeptical"}
    missing = sorted(required - set(df.columns))
    if missing:
        baseline["available"] = False
        baseline["error"] = f"baseline_missing_columns:{missing}"
        return baseline

    df["top_comment_skeptical"] = pd.to_numeric(df["top_comment_skeptical"], errors="coerce")
    df["is_skeptical"] = pd.to_numeric(df["is_skeptical"], errors="coerce")
    df = df.dropna(subset=["top_comment_skeptical", "is_skeptical"]).copy()
    df["top_comment_skeptical"] = df["top_comment_skeptical"].astype(int)
    df["is_skeptical"] = df["is_skeptical"].astype(int)

    baseline["available"] = True
    baseline["response_rows"] = int(len(df))
    baseline["videos"] = int(df["video_id"].nunique())
    baseline["skeptical_top_cue_videos"] = int(df.loc[df["top_comment_skeptical"] == 1, "video_id"].nunique())
    baseline["skeptical_cue_response_rows"] = int((df["top_comment_skeptical"] == 1).sum())
    baseline["rate_after_skeptical_cue"] = float(
        df.loc[df["top_comment_skeptical"] == 1, "is_skeptical"].mean()
    ) if int((df["top_comment_skeptical"] == 1).sum()) else float("nan")
    baseline["rate_after_non_skeptical_cue"] = float(
        df.loc[df["top_comment_skeptical"] == 0, "is_skeptical"].mean()
    ) if int((df["top_comment_skeptical"] == 0).sum()) else float("nan")

    if effects_csv and effects_csv.exists():
        eff = pd.read_csv(effects_csv)
        row = eff.loc[eff["term"] == "top_comment_skeptical"]
        if not row.empty:
            baseline["h1_or"] = float(row["odds_ratio"].iloc[0])
            baseline["h1_p"] = float(row["p_value_approx"].iloc[0])
    return baseline


def _comparison_table(new_metrics: dict[str, Any], baseline: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    mapping = [
        ("response_rows", "Response rows"),
        ("videos", "Videos in response frame"),
        ("skeptical_top_cue_videos", "Skeptical top-cue videos"),
        ("skeptical_cue_response_rows", "Skeptical-cue response rows"),
        ("rate_after_skeptical_cue", "Downstream skepticism rate | skeptical cue"),
        ("rate_after_non_skeptical_cue", "Downstream skepticism rate | non-skeptical cue"),
        ("h1_or", "Top-cue main effect OR"),
    ]
    for key, label in mapping:
        new_v = new_metrics.get(key, np.nan)
        old_v = baseline.get(key, np.nan) if baseline.get("available") else np.nan
        delta = (
            float(new_v) - float(old_v)
            if pd.notna(new_v) and pd.notna(old_v)
            else np.nan
        )
        rows.append(
            {
                "metric": label,
                "baseline_old_frame": old_v,
                "freeze10_rerun": new_v,
                "delta_new_minus_old": delta,
            }
        )
    return pd.DataFrame(rows)


def _write_report(
    *,
    out_path: Path,
    freeze: FreezeSpec,
    handling: dict[str, Any],
    exclusions: dict[str, Any],
    new_metrics: dict[str, Any],
    baseline: dict[str, Any],
    sparse_flag: bool,
    claim_note: str,
) -> None:
    lines: list[str] = []
    lines.append("# Freeze-Scoped Inferential Rerun Report")
    lines.append("")
    lines.append("## Freeze Anchor")
    lines.append(f"- freeze_id: `{freeze.freeze_id}`")
    lines.append(f"- freeze_uuid: `{freeze.freeze_uuid}`")
    lines.append(f"- freeze_name: `{freeze.freeze_name}`")
    lines.append(f"- run_ids: `{list(freeze.run_ids)}`")
    lines.append("")
    lines.append("## Data Handling")
    lines.append(
        f"- Missing like_count values before ranking: `{handling['missing_like_count_before_fill']}` "
        "(handled as `0` for ranking and top-cue like predictor)."
    )
    lines.append(
        f"- Missing/unusable timestamps before response filtering: `{handling['missing_timestamp_before_filter']}`."
    )
    lines.append(
        "- Elapsed hours computed as `(response_timestamp - top_timestamp)`; "
        "negative values clipped to `0`; rows missing either timestamp excluded."
    )
    lines.append("")
    lines.append("## Exclusion Audit")
    for k in [
        "resolved_comments_before_screen",
        "excluded_flagged_comments",
        "resolved_comments_after_screen",
        "videos_after_screen",
        "videos_excluded_no_response_candidates_ranks_2_20",
        "videos_excluded_top_timestamp_missing",
        "videos_excluded_all_response_rows_invalid",
        "videos_in_final_response_frame",
        "response_rows_before_timestamp_and_label_filters",
        "excluded_rows_missing_response_or_top_timestamp",
        "excluded_rows_missing_response_label",
        "final_response_rows",
    ]:
        lines.append(f"- {k}: `{exclusions.get(k)}`")
    lines.append("")
    lines.append("## Required Counts")
    lines.append(f"- rebuilt freeze-scoped response frame count: `{new_metrics['response_rows']}`")
    lines.append(f"- skeptical top-cue videos: `{new_metrics['skeptical_top_cue_videos']}`")
    lines.append(f"- skeptical-cue response rows: `{new_metrics['skeptical_cue_response_rows']}`")
    lines.append("")
    lines.append("## Old vs New Frame Baseline")
    if baseline.get("available"):
        lines.append(f"- baseline response source: `{baseline.get('baseline_response_source')}`")
        if baseline.get("baseline_effects_source"):
            lines.append(f"- baseline effects source: `{baseline.get('baseline_effects_source')}`")
        lines.append(
            f"- baseline response_rows: `{baseline.get('response_rows')}` | new: `{new_metrics['response_rows']}`"
        )
        lines.append(
            f"- baseline skeptical_top_cue_videos: `{baseline.get('skeptical_top_cue_videos')}` | "
            f"new: `{new_metrics['skeptical_top_cue_videos']}`"
        )
    else:
        lines.append(f"- baseline unavailable: `{baseline.get('error', 'unknown')}`")
    lines.append("")
    lines.append("## Interaction Stability")
    lines.append(f"- sparse_cue_structure_flag: `{int(sparse_flag)}`")
    lines.append(f"- interpretation: {claim_note}")
    lines.append("")
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> None:
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(args.db_path))
    conn.row_factory = sqlite3.Row
    try:
        freeze = load_freeze(conn, args.freeze_id)
        if args.expected_freeze_uuid and freeze.freeze_uuid != args.expected_freeze_uuid:
            raise RuntimeError(
                f"Freeze UUID mismatch: expected `{args.expected_freeze_uuid}`, got `{freeze.freeze_uuid}`"
            )
        if args.expected_freeze_name and freeze.freeze_name != args.expected_freeze_name:
            raise RuntimeError(
                f"Freeze name mismatch: expected `{args.expected_freeze_name}`, got `{freeze.freeze_name}`"
            )

        comments = _freeze_comments(conn, freeze.run_ids)
        labels = _resolved_labels(conn, freeze.run_ids)
    finally:
        conn.close()

    if comments.empty:
        raise RuntimeError("No comments found for freeze run scope.")
    if labels.empty:
        raise RuntimeError("No resolved labels found for freeze run scope.")

    merged = comments.merge(labels, on="comment_db_id", how="inner").copy()
    merged["analysis_skepticism"] = pd.to_numeric(merged["label_skepticism"], errors="coerce")
    merged["comment_timestamp"] = pd.to_datetime(merged["comment_timestamp"], errors="coerce", utc=True)

    exclusions: dict[str, Any] = {}
    exclusions["resolved_comments_before_screen"] = int(len(merged))
    exclusions["videos_before_screen"] = int(merged["video_id"].nunique())
    excluded_flagged = (
        (pd.to_numeric(merged["is_spam"], errors="coerce").fillna(0).astype(int) == 1)
        | (pd.to_numeric(merged["is_template"], errors="coerce").fillna(0).astype(int) == 1)
        | (pd.to_numeric(merged["is_duplicate"], errors="coerce").fillna(0).astype(int) == 1)
    )
    exclusions["excluded_flagged_comments"] = int(excluded_flagged.sum())
    frame = merged.loc[~excluded_flagged].copy()
    exclusions["resolved_comments_after_screen"] = int(len(frame))
    exclusions["videos_after_screen"] = int(frame["video_id"].nunique())

    handling = {
        "missing_like_count_before_fill": int(pd.to_numeric(frame["like_count"], errors="coerce").isna().sum()),
        "missing_timestamp_before_filter": int(frame["comment_timestamp"].isna().sum()),
    }

    frame["like_count"] = pd.to_numeric(frame["like_count"], errors="coerce").fillna(0).astype(int)
    frame["analysis_skepticism"] = pd.to_numeric(frame["analysis_skepticism"], errors="coerce")

    ranked = frame.sort_values(
        ["video_id", "like_count", "comment_timestamp"],
        ascending=[True, False, True],
        kind="mergesort",
    ).copy()
    ranked["rank"] = ranked.groupby("video_id").cumcount() + 1

    top = ranked.loc[ranked["rank"] == 1, ["video_id", "analysis_skepticism", "like_count", "comment_timestamp"]].rename(
        columns={
            "analysis_skepticism": "top_comment_skeptical",
            "like_count": "top_comment_like_count",
            "comment_timestamp": "top_comment_timestamp",
        }
    )
    response_candidates = ranked.loc[(ranked["rank"] > 1) & (ranked["rank"] <= 20)].copy()
    exclusions["response_rows_before_timestamp_and_label_filters"] = int(len(response_candidates))

    videos_all = set(ranked["video_id"].dropna().astype(str).tolist())
    videos_with_responses = set(response_candidates["video_id"].dropna().astype(str).tolist())
    videos_no_response_candidates = videos_all - videos_with_responses
    exclusions["videos_excluded_no_response_candidates_ranks_2_20"] = int(len(videos_no_response_candidates))

    top_missing_ts = set(
        top.loc[top["top_comment_timestamp"].isna(), "video_id"].dropna().astype(str).tolist()
    )
    exclusions["videos_excluded_top_timestamp_missing"] = int(len(top_missing_ts))

    response = response_candidates.merge(top, on="video_id", how="left")
    missing_ts_mask = response["comment_timestamp"].isna() | response["top_comment_timestamp"].isna()
    missing_label_mask = response["analysis_skepticism"].isna() | response["top_comment_skeptical"].isna()
    exclusions["excluded_rows_missing_response_or_top_timestamp"] = int(missing_ts_mask.sum())
    exclusions["excluded_rows_missing_response_label"] = int(missing_label_mask.sum())

    response = response.loc[~missing_ts_mask & ~missing_label_mask].copy()
    response["is_skeptical"] = pd.to_numeric(response["analysis_skepticism"], errors="coerce").astype(int)
    response["top_comment_skeptical"] = pd.to_numeric(response["top_comment_skeptical"], errors="coerce").astype(int)

    delta_hours = (
        (response["comment_timestamp"] - response["top_comment_timestamp"]).dt.total_seconds() / 3600.0
    )
    response["hours_since_top_comment_raw"] = delta_hours
    response["hours_since_top_comment"] = delta_hours.clip(lower=0.0)
    response["top_comment_like_count_z"] = _zscore(response["top_comment_like_count"])
    response["hours_since_top_comment_z"] = _zscore(response["hours_since_top_comment"])

    clean_videos = set(response["video_id"].dropna().astype(str).tolist())
    exclusions["videos_excluded_all_response_rows_invalid"] = int(len(videos_with_responses - clean_videos))
    exclusions["videos_in_final_response_frame"] = int(len(clean_videos))
    exclusions["final_response_rows"] = int(len(response))

    response_df = response[
        [
            "run_id",
            "video_id",
            "channel_id",
            "channel_niche",
            "comment_db_id",
            "comment_rank",
            "rank",
            "is_skeptical",
            "top_comment_skeptical",
            "top_comment_like_count",
            "top_comment_like_count_z",
            "hours_since_top_comment",
            "hours_since_top_comment_z",
            "comment_timestamp",
            "top_comment_timestamp",
            "cleaned_text",
        ]
    ].rename(columns={"cleaned_text": "comment_text"})

    # Save analytic dataset before model fit so failure still preserves exact frame.
    analytic_csv = out_dir / "freeze10_analytic_response_frame.csv"
    response_df.to_csv(analytic_csv, index=False)
    ranked_csv = out_dir / "freeze10_ranked_resolved_comments.csv"
    ranked.to_csv(ranked_csv, index=False)
    pd.DataFrame([handling]).to_csv(out_dir / "freeze10_handling_summary.csv", index=False)
    pd.DataFrame([exclusions]).to_csv(out_dir / "freeze10_exclusion_audit.csv", index=False)

    try:
        model, fit, formula = _fit_model(response_df)
        effects_df = _effects_table(model, fit)
    except Exception as exc:
        fail_md = out_dir / "freeze10_model_failure.md"
        fail_md.write_text(
            "\n".join(
                [
                    "# Model Failure",
                    "",
                    f"- freeze_id: `{freeze.freeze_id}`",
                    f"- freeze_name: `{freeze.freeze_name}`",
                    f"- failure_point: `BinomialBayesMixedGLM.from_formula(...).fit_vb()`",
                    f"- error: `{exc}`",
                    "",
                    "No substitute estimator was run.",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        raise RuntimeError(f"Model failed at fit_vb: {exc}") from exc

    ctab = _crosstab(response_df)
    ctab_csv = out_dir / "freeze10_cue_rate_crosstab.csv"
    ctab.to_csv(ctab_csv, index=False)

    effects_csv = out_dir / "freeze10_model_effects.csv"
    effects_df.to_csv(effects_csv, index=False)
    (out_dir / "freeze10_model_summary.txt").write_text(str(fit.summary()), encoding="utf-8")
    (out_dir / "freeze10_model_formula.txt").write_text(formula + "\n", encoding="utf-8")
    _forest_plot(effects_df, out_dir / "freeze10_forest_plot.png")

    baseline = _baseline_metrics(args.baseline_response_csv, args.baseline_effects_csv)
    h1_row = effects_df.loc[effects_df["term"] == "top_comment_skeptical"]
    h1_or = float(h1_row["odds_ratio"].iloc[0]) if not h1_row.empty else float("nan")
    h1_p = float(h1_row["p_value_approx"].iloc[0]) if not h1_row.empty else float("nan")
    skeptical_videos = int(response_df.loc[response_df["top_comment_skeptical"] == 1, "video_id"].nunique())
    skeptical_rows = int((response_df["top_comment_skeptical"] == 1).sum())
    total_videos = int(response_df["video_id"].nunique())

    new_metrics = {
        "response_rows": int(len(response_df)),
        "videos": total_videos,
        "skeptical_top_cue_videos": skeptical_videos,
        "skeptical_cue_response_rows": skeptical_rows,
        "rate_after_skeptical_cue": float(
            response_df.loc[response_df["top_comment_skeptical"] == 1, "is_skeptical"].mean()
        ) if skeptical_rows else float("nan"),
        "rate_after_non_skeptical_cue": float(
            response_df.loc[response_df["top_comment_skeptical"] == 0, "is_skeptical"].mean()
        ) if int((response_df["top_comment_skeptical"] == 0).sum()) else float("nan"),
        "h1_or": h1_or,
        "h1_p": h1_p,
    }

    comp_df = _comparison_table(new_metrics, baseline)
    comp_df.to_csv(out_dir / "freeze10_old_vs_new_comparison.csv", index=False)

    interaction_terms = effects_df[
        effects_df["term"].str.contains("top_comment_skeptical:C\\(channel_niche", regex=True, na=False)
    ].copy()
    sparse_flag = bool(
        skeptical_videos < 30
        or skeptical_rows < 150
        or (total_videos > 0 and (skeptical_videos / total_videos) < 0.20)
    )
    if sparse_flag or interaction_terms.empty or (interaction_terms["p_value_approx"] >= 0.05).all():
        claim_note = (
            "H1 can be treated as the primary confirmatory effect if its main cue term remains in the expected direction; "
            "H3 (niche interactions) should be framed as fragile/secondary."
        )
    else:
        claim_note = (
            "Some interaction terms show signal, but they should still be presented as secondary unless replicated in additional freeze-scoped data."
        )

    _write_report(
        out_path=out_dir / "freeze10_rerun_report.md",
        freeze=freeze,
        handling=handling,
        exclusions=exclusions,
        new_metrics=new_metrics,
        baseline=baseline,
        sparse_flag=sparse_flag,
        claim_note=claim_note,
    )

    manifest = {
        "freeze_id": freeze.freeze_id,
        "freeze_uuid": freeze.freeze_uuid,
        "freeze_name": freeze.freeze_name,
        "run_ids": list(freeze.run_ids),
        "outputs_dir": str(out_dir),
        "required_outputs": {
            "analytic_dataset": str(analytic_csv),
            "model_effects": str(effects_csv),
            "crosstab": str(ctab_csv),
            "forest_plot": str(out_dir / "freeze10_forest_plot.png"),
            "comparison_old_vs_new": str(out_dir / "freeze10_old_vs_new_comparison.csv"),
            "report": str(out_dir / "freeze10_rerun_report.md"),
        },
    }
    (out_dir / "freeze10_rerun_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

    print("Rerun complete.")
    print(f"- freeze_id: {freeze.freeze_id}")
    print(f"- freeze_name: {freeze.freeze_name}")
    print(f"- response_rows: {new_metrics['response_rows']}")
    print(f"- skeptical_top_cue_videos: {new_metrics['skeptical_top_cue_videos']}")
    print(f"- skeptical_cue_response_rows: {new_metrics['skeptical_cue_response_rows']}")
    print(f"- h1_or: {new_metrics['h1_or']:.6f}")
    print(f"- h1_p: {new_metrics['h1_p']:.6g}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Freeze-scoped inferential rerun for cue-response model."
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--freeze-id", type=int, default=EXPECTED_FREEZE_ID)
    parser.add_argument("--expected-freeze-uuid", default=EXPECTED_FREEZE_UUID)
    parser.add_argument("--expected-freeze-name", default=EXPECTED_FREEZE_NAME)
    parser.add_argument("--baseline-response-csv", type=Path, default=DEFAULT_BASELINE_RESPONSE)
    parser.add_argument("--baseline-effects-csv", type=Path, default=DEFAULT_BASELINE_EFFECTS)
    return parser.parse_args()


if __name__ == "__main__":
    run(parse_args())
