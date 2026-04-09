from __future__ import annotations

import json
import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from .conformity_cascade import run_conformity_cascade

try:
    import altair as alt
except Exception:  # pragma: no cover - optional dependency at runtime
    alt = None


DEFAULT_LOGIC_REGISTRY = {
    "rules_version": "deterministic-rules-v1.1.0",
    "scoring_version": "assistive-scoring-v1.1.0",
    "preprocessing_profile": "clean_top20_v1",
    "preprocessing_rules_version": "preprocessing-v1.0.0",
    "signal_detection_rules_version": "signal-detection-v1.0.0",
    "triage_scoring_version": "triage-v1.0.0",
    "priority_scoring_version": "priority-v1.0.0",
    "spam_ruleset_version": "spam-v1.0",
}


@dataclass(frozen=True)
class FreezeRecord:
    freeze_id: int
    freeze_uuid: str
    freeze_name: str
    created_by: str
    freeze_timestamp: str
    notes: str
    run_ids: tuple[int, ...]
    summary: dict[str, Any]
    prevalence_overall: list[dict[str, Any]]
    prevalence_by_run_niche: list[dict[str, Any]]
    rules_version: str
    scoring_version: str
    preprocessing_profile: str


def _json_load(value: Any, fallback: Any) -> Any:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return fallback
    return parsed


def _placeholders(n: int) -> str:
    return ",".join(["?"] * n)


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _format_effect_term(term: str) -> str:
    raw = _safe_text(term)
    if not raw:
        return ""
    if raw == "Intercept":
        return "Baseline (intercept)"
    if raw == "top_comment_skeptical":
        return "H1: skeptical top cue"
    if raw == "top_comment_like_count_z":
        return "Top cue like count (z)"
    if raw == "hours_since_top_comment_z":
        return "Hours since top cue (z)"
    if raw == "top_comment_skeptical:top_comment_like_count_z":
        return "H2: skeptical cue x like count (z)"
    if raw == "top_comment_skeptical:hours_since_top_comment_z":
        return "Skeptical cue x time since top cue (z)"

    niche_interaction = re.match(
        r"top_comment_skeptical:C\(channel_niche, Treatment\(reference='([^']+)'\)\)\[T\.([^\]]+)\]",
        raw,
    )
    if niche_interaction:
        reference, niche = niche_interaction.groups()
        return f"H1: skeptical cue x niche ({niche} vs {reference})"

    niche_main = re.match(
        r"C\(channel_niche, Treatment\(reference='([^']+)'\)\)\[T\.([^\]]+)\]",
        raw,
    )
    if niche_main:
        reference, niche = niche_main.groups()
        return f"Niche main effect ({niche} vs {reference})"

    return raw


def _load_freeze(
    conn: sqlite3.Connection,
    *,
    freeze_id: int | None = None,
    freeze_name: str | None = None,
) -> FreezeRecord:
    if freeze_id is not None:
        row = conn.execute(
            """
            SELECT
                id, freeze_uuid, name, created_by, created_at, notes,
                run_ids_json, summary_json, prevalence_overall_json, prevalence_by_run_niche_json,
                rules_version, scoring_version, preprocessing_profile
            FROM evidence_freezes
            WHERE id = ?
            LIMIT 1
            """,
            (int(freeze_id),),
        ).fetchone()
    elif freeze_name:
        row = conn.execute(
            """
            SELECT
                id, freeze_uuid, name, created_by, created_at, notes,
                run_ids_json, summary_json, prevalence_overall_json, prevalence_by_run_niche_json,
                rules_version, scoring_version, preprocessing_profile
            FROM evidence_freezes
            WHERE name = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (freeze_name.strip(),),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT
                id, freeze_uuid, name, created_by, created_at, notes,
                run_ids_json, summary_json, prevalence_overall_json, prevalence_by_run_niche_json,
                rules_version, scoring_version, preprocessing_profile
            FROM evidence_freezes
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        raise RuntimeError("No evidence freeze found. Save a named freeze first in the app.")

    run_ids_raw = _json_load(row["run_ids_json"], [])
    summary_raw = _json_load(row["summary_json"], {})
    prevalence_overall = _json_load(row["prevalence_overall_json"], [])
    prevalence_by_run_niche = _json_load(row["prevalence_by_run_niche_json"], [])
    run_ids = tuple(int(x) for x in run_ids_raw) if isinstance(run_ids_raw, list) else tuple()
    if not run_ids:
        raise RuntimeError(f"Freeze `{row['name']}` has no run IDs.")

    return FreezeRecord(
        freeze_id=int(row["id"]),
        freeze_uuid=_safe_text(row["freeze_uuid"]) or f"freeze-id-{int(row['id'])}",
        freeze_name=_safe_text(row["name"]) or f"freeze-{int(row['id'])}",
        created_by=_safe_text(row["created_by"]),
        freeze_timestamp=_safe_text(row["created_at"]),
        notes=_safe_text(row["notes"]),
        run_ids=run_ids,
        summary=summary_raw if isinstance(summary_raw, dict) else {},
        prevalence_overall=prevalence_overall if isinstance(prevalence_overall, list) else [],
        prevalence_by_run_niche=prevalence_by_run_niche if isinstance(prevalence_by_run_niche, list) else [],
        rules_version=_safe_text(row["rules_version"]) or DEFAULT_LOGIC_REGISTRY["rules_version"],
        scoring_version=_safe_text(row["scoring_version"]) or DEFAULT_LOGIC_REGISTRY["scoring_version"],
        preprocessing_profile=_safe_text(row["preprocessing_profile"]) or DEFAULT_LOGIC_REGISTRY["preprocessing_profile"],
    )


def _comments_for_runs(conn: sqlite3.Connection, run_ids: tuple[int, ...]) -> pd.DataFrame:
    placeholders = _placeholders(len(run_ids))
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
    WHERE c.run_id IN ({placeholders})
    ORDER BY c.run_id DESC, ch.channel_id, c.comment_rank
    """
    return pd.read_sql_query(q, conn, params=run_ids)


def _resolved_labels_for_runs(conn: sqlite3.Connection, run_ids: tuple[int, ...]) -> pd.DataFrame:
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
            a.annotator_id,
            a.is_adjudicated,
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
        annotator_id,
        is_adjudicated,
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
    params = tuple(run_ids) + tuple(run_ids)
    return pd.read_sql_query(q, conn, params=params)


def _resolved_frame(
    conn: sqlite3.Connection,
    run_ids: tuple[int, ...],
    *,
    include_flagged: bool,
) -> pd.DataFrame:
    comments = _comments_for_runs(conn, run_ids)
    labels = _resolved_labels_for_runs(conn, run_ids)
    if comments.empty or labels.empty:
        return pd.DataFrame()

    merged = comments.merge(labels, on="comment_db_id", how="left")
    merged["analysis_skepticism"] = pd.to_numeric(merged["label_skepticism"], errors="coerce").astype("Int64")
    merged["analysis_proof_demand"] = pd.to_numeric(merged["label_proof_demand"], errors="coerce").astype("Int64")
    merged["analysis_normalization"] = pd.to_numeric(merged["label_normalization"], errors="coerce").astype("Int64")
    merged["comment_timestamp"] = pd.to_datetime(merged["comment_timestamp"], errors="coerce", utc=True)

    if not include_flagged:
        merged = merged[
            (merged["is_spam"] == 0)
            & (merged["is_template"] == 0)
            & (merged["is_duplicate"] == 0)
        ].copy()
    return merged


def _corpus_counts_for_runs(conn: sqlite3.Connection, run_ids: tuple[int, ...]) -> dict[str, int]:
    placeholders = _placeholders(len(run_ids))
    row = conn.execute(
        f"""
        SELECT
            (SELECT COUNT(*) FROM comments WHERE run_id IN ({placeholders})) AS raw_comments,
            (
                SELECT COUNT(*)
                FROM comments
                WHERE run_id IN ({placeholders})
                  AND COALESCE(is_spam, 0) = 0
                  AND COALESCE(is_template, 0) = 0
                  AND COALESCE(is_duplicate, 0) = 0
            ) AS screened_comments
        """,
        tuple(run_ids) + tuple(run_ids),
    ).fetchone()
    return {
        "raw_comments": int(row["raw_comments"] or 0),
        "screened_comments": int(row["screened_comments"] or 0),
    }


def _labeled_summary_for_runs(conn: sqlite3.Connection, run_ids: tuple[int, ...]) -> dict[str, int]:
    placeholders = _placeholders(len(run_ids))
    row = conn.execute(
        f"""
        WITH base AS (
            SELECT
                c.id AS comment_db_id,
                COUNT(DISTINCT a.annotator_id) AS coder_count,
                MAX(a.is_adjudicated) AS has_adjudicated,
                MIN(COALESCE(a.skepticism_fake_callout, 0)) AS min_s,
                MAX(COALESCE(a.skepticism_fake_callout, 0)) AS max_s,
                MIN(COALESCE(a.proof_demand, 0)) AS min_p,
                MAX(COALESCE(a.proof_demand, 0)) AS max_p,
                MIN(COALESCE(a.normalization_defense, 0)) AS min_n,
                MAX(COALESCE(a.normalization_defense, 0)) AS max_n,
                MIN(COALESCE(a.other_flag, 0)) AS min_o,
                MAX(COALESCE(a.other_flag, 0)) AS max_o,
                MIN(COALESCE(a.extra_codes, '')) AS min_e,
                MAX(COALESCE(a.extra_codes, '')) AS max_e
            FROM comments c
            JOIN annotations a ON a.comment_db_id = c.id
            WHERE c.run_id IN ({placeholders})
            GROUP BY c.id
        )
        SELECT
            COUNT(*) AS labeled_comments,
            SUM(CASE WHEN coder_count >= 2 THEN 1 ELSE 0 END) AS double_coded_comments,
            SUM(
                CASE
                    WHEN coder_count >= 2 AND (
                        min_s <> max_s
                        OR min_p <> max_p
                        OR min_n <> max_n
                        OR min_o <> max_o
                        OR min_e <> max_e
                    ) THEN 1
                    ELSE 0
                END
            ) AS disagreement_comments,
            SUM(CASE WHEN has_adjudicated = 1 THEN 1 ELSE 0 END) AS adjudicated_comments
        FROM base
        """,
        tuple(run_ids),
    ).fetchone()
    return {
        "labeled_comments": int(row["labeled_comments"] or 0),
        "double_coded_comments": int(row["double_coded_comments"] or 0),
        "disagreement_comments": int(row["disagreement_comments"] or 0),
        "adjudicated_comments": int(row["adjudicated_comments"] or 0),
    }


def _conformity_input_df(resolved_frame: pd.DataFrame) -> pd.DataFrame:
    cols = [
        "video_id",
        "channel_id",
        "channel_niche",
        "cleaned_text",
        "like_count",
        "comment_timestamp",
        "analysis_skepticism",
        "comment_rank",
        "reply_count",
        "run_id",
    ]
    use = resolved_frame[cols].rename(
        columns={
            "cleaned_text": "comment_text",
            "analysis_skepticism": "is_skeptical",
        }
    )
    use["is_skeptical"] = pd.to_numeric(use["is_skeptical"], errors="coerce")
    return use


def _workflow_mermaid_spec() -> str:
    return "\n".join(
        [
            "flowchart LR",
            "    A[Raw corpus] --> B[Screened corpus]",
            "    B --> C[Coded corpus]",
            "    C --> D[Disagreement detection]",
            "    D --> E[Adjudicated / resolved corpus]",
            "    E --> F[Frozen validated evidence]",
            "    F --> G[Paper-facing analysis]",
            "    E --> H[Exploratory extension]",
            "    H -. not paper-safe by default .-> G",
            "",
            "%% Human validation governs F; assistive outputs remain exploratory.",
        ]
    )


def _build_evidence_funnel_df(
    freeze: FreezeRecord,
    corpus_counts: dict[str, int],
    labeled_summary: dict[str, int],
) -> pd.DataFrame:
    resolved = int(freeze.summary.get("resolved_comments", 0) or 0)
    screened = int(corpus_counts.get("screened_comments", 0) or 0)
    exploratory_extension = max(0, screened - resolved)
    rows = [
        {"order": 1, "stage": "Raw corpus", "count": int(corpus_counts.get("raw_comments", 0) or 0), "layer": "assistive"},
        {"order": 2, "stage": "Screened corpus", "count": screened, "layer": "assistive"},
        {"order": 3, "stage": "Coded corpus", "count": int(labeled_summary.get("labeled_comments", 0) or 0), "layer": "human"},
        {
            "order": 4,
            "stage": "Disagreement cases",
            "count": int(freeze.summary.get("disagreement_comments", labeled_summary.get("disagreement_comments", 0)) or 0),
            "layer": "human",
        },
        {
            "order": 5,
            "stage": "Adjudicated / resolved corpus",
            "count": resolved,
            "layer": "human",
        },
        {"order": 6, "stage": "Frozen validated evidence", "count": resolved, "layer": "validated"},
        {"order": 7, "stage": "Exploratory extension", "count": exploratory_extension, "layer": "assistive"},
    ]
    return pd.DataFrame(rows)


def _freeze_metadata_df(freeze: FreezeRecord) -> pd.DataFrame:
    summary = freeze.summary
    rows = [
        {"metric": "freeze_id", "value": freeze.freeze_id},
        {"metric": "freeze_uuid", "value": freeze.freeze_uuid},
        {"metric": "freeze_name", "value": freeze.freeze_name},
        {"metric": "freeze_timestamp", "value": freeze.freeze_timestamp},
        {"metric": "run_ids_included", "value": ", ".join(str(x) for x in freeze.run_ids)},
        {"metric": "resolved_comment_count", "value": int(summary.get("resolved_comments", 0) or 0)},
        {"metric": "double_coded_comment_count", "value": int(summary.get("double_coded_comments", 0) or 0)},
        {"metric": "disagreement_count", "value": int(summary.get("disagreement_comments", 0) or 0)},
        {"metric": "unresolved_disagreement_count", "value": int(summary.get("unresolved_disagreements", 0) or 0)},
        {"metric": "rules_version", "value": freeze.rules_version},
        {"metric": "scoring_version", "value": freeze.scoring_version},
        {"metric": "preprocessing_profile", "value": freeze.preprocessing_profile},
        {"metric": "spam_ruleset_version", "value": DEFAULT_LOGIC_REGISTRY["spam_ruleset_version"]},
        {"metric": "preprocessing_rules_version", "value": DEFAULT_LOGIC_REGISTRY["preprocessing_rules_version"]},
        {"metric": "signal_detection_rules_version", "value": DEFAULT_LOGIC_REGISTRY["signal_detection_rules_version"]},
        {"metric": "triage_scoring_version", "value": DEFAULT_LOGIC_REGISTRY["triage_scoring_version"]},
        {"metric": "priority_scoring_version", "value": DEFAULT_LOGIC_REGISTRY["priority_scoring_version"]},
        {"metric": "paper_reference_note", "value": "Use this freeze ID/UUID as the paper-facing evidence anchor."},
    ]
    return pd.DataFrame(rows)


def _reference_niche_from_effects(effects_df: pd.DataFrame) -> str:
    terms = effects_df["term"].astype(str).tolist()
    for term in terms:
        m = re.search(r"Treatment\(reference='([^']+)'\)", term)
        if m:
            return m.group(1)
    return "Lifestyle"


def _predicted_probs_df(effects_df: pd.DataFrame, niches: list[str]) -> pd.DataFrame:
    coef = {str(r["term"]): float(r["coef_log_odds"]) for _, r in effects_df.iterrows()}
    ref = _reference_niche_from_effects(effects_df)
    if ref not in niches:
        niches = sorted(set(niches + [ref]))

    intercept = float(coef.get("Intercept", 0.0))
    cue_beta = float(coef.get("top_comment_skeptical", 0.0))
    rows: list[dict[str, Any]] = []
    for niche in niches:
        niche_beta = float(coef.get(f"C(channel_niche, Treatment(reference='{ref}'))[T.{niche}]", 0.0))
        niche_inter = float(
            coef.get(
                f"top_comment_skeptical:C(channel_niche, Treatment(reference='{ref}'))[T.{niche}]",
                0.0,
            )
        )
        for cue in (0, 1):
            eta = intercept + niche_beta + cue * cue_beta + cue * niche_inter
            p = 1.0 / (1.0 + math.exp(-eta))
            rows.append(
                {
                    "channel_niche": niche,
                    "top_comment_skeptical": cue,
                    "cue_label": "skeptical top cue" if cue == 1 else "non-skeptical top cue",
                    "predicted_probability": p,
                    "reference_niche": ref,
                }
            )
    return pd.DataFrame(rows).sort_values(["channel_niche", "top_comment_skeptical"]).reset_index(drop=True)


def _reproducibility_tables(input_df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    run1 = run_conformity_cascade(input_df)
    run2 = run_conformity_cascade(input_df)

    effects1 = run1.effects_df.copy()
    effects2 = run2.effects_df.copy()

    merged = effects1.merge(
        effects2,
        on="term",
        how="outer",
        suffixes=("_run1", "_run2"),
    )
    for col in [
        "coef_log_odds",
        "odds_ratio",
        "p_value_approx",
        "or_ci_95_low",
        "or_ci_95_high",
    ]:
        merged[f"{col}_abs_diff"] = (merged[f"{col}_run1"] - merged[f"{col}_run2"]).abs()

    summary = {
        "max_abs_coef_diff": float(merged["coef_log_odds_abs_diff"].max()),
        "max_abs_or_diff": float(merged["odds_ratio_abs_diff"].max()),
        "max_abs_p_diff": float(merged["p_value_approx_abs_diff"].max()),
        "tolerance": 1e-4,
    }
    summary["pass_within_tolerance"] = bool(
        summary["max_abs_coef_diff"] <= summary["tolerance"]
        and summary["max_abs_or_diff"] <= summary["tolerance"]
        and summary["max_abs_p_diff"] <= summary["tolerance"]
    )
    return merged, summary, run1.response_df


def _save_altair_html(chart, path: Path) -> str:
    if alt is None:
        return "altair_not_available"
    chart.save(str(path))
    return ""


def _chart_evidence_funnel(df: pd.DataFrame):
    if alt is None:
        return None
    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("count:Q", title="Comments"),
            y=alt.Y("stage:N", sort=alt.SortField(field="order", order="ascending"), title=None),
            color=alt.Color(
                "layer:N",
                scale=alt.Scale(
                    domain=["validated", "human", "assistive"],
                    range=["#176087", "#2E8B57", "#C47C2C"],
                ),
                legend=alt.Legend(title="Layer"),
            ),
            tooltip=["stage:N", "count:Q", "layer:N"],
        )
        .properties(width=860, height=300, title="Evidence Funnel and Workflow Boundary")
    )


def _chart_forest(effects_df: pd.DataFrame):
    if alt is None:
        return None
    view = effects_df.copy()
    view = view[view["term"] != "Intercept"].copy()
    view["term_display"] = view["term"].apply(_format_effect_term)
    view = view.sort_values("odds_ratio", ascending=True).reset_index(drop=True)
    view["term_order"] = view.index

    domain_min = max(float(view["or_ci_95_low"].min()) * 0.9, 1e-6)
    domain_max = float(view["or_ci_95_high"].max()) * 1.1
    base = alt.Chart(view).encode(
        y=alt.Y("term_display:N", sort=alt.SortField(field="term_order", order="ascending"), title=None),
        tooltip=[
            "term_display:N",
            alt.Tooltip("odds_ratio:Q", format=".3f"),
            alt.Tooltip("or_ci_95_low:Q", format=".3f"),
            alt.Tooltip("or_ci_95_high:Q", format=".3f"),
            alt.Tooltip("p_value_approx:Q", format=".3g"),
        ],
    )
    intervals = base.mark_rule(strokeWidth=2).encode(
        x=alt.X("or_ci_95_low:Q", scale=alt.Scale(type="log", domain=[domain_min, domain_max]), title="Odds ratio (log scale)"),
        x2="or_ci_95_high:Q",
        color=alt.condition("datum.p_value_approx < 0.05", alt.value("#176087"), alt.value("#8FA6B8")),
    )
    points = base.mark_point(filled=True, size=80).encode(
        x=alt.X("odds_ratio:Q", scale=alt.Scale(type="log", domain=[domain_min, domain_max]), title="Odds ratio (log scale)"),
        color=alt.condition("datum.p_value_approx < 0.05", alt.value("#0F4C75"), alt.value("#A9B8C4")),
    )
    ref_rule = alt.Chart(pd.DataFrame({"x": [1.0]})).mark_rule(strokeDash=[4, 4], color="#555").encode(x="x:Q")
    return (intervals + points + ref_rule).properties(
        width=860,
        height=340,
        title="Model Effects Forest Plot (OR with 95% CI)",
    )


def _chart_predicted_probs(df: pd.DataFrame):
    if alt is None:
        return None
    return (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
        .encode(
            x=alt.X("channel_niche:N", title="Channel niche"),
            xOffset=alt.XOffset("cue_label:N"),
            y=alt.Y("predicted_probability:Q", title="Predicted skepticism probability", scale=alt.Scale(domain=[0, 1])),
            color=alt.Color(
                "cue_label:N",
                scale=alt.Scale(
                    domain=["non-skeptical top cue", "skeptical top cue"],
                    range=["#9FB3C8", "#1F5A8A"],
                ),
                legend=alt.Legend(title="Top cue"),
            ),
            tooltip=["channel_niche:N", "cue_label:N", alt.Tooltip("predicted_probability:Q", format=".3f")],
        )
        .properties(width=860, height=320, title="Predicted Probability by Niche and Top-Cue Skepticism")
    )


def _chart_prevalence_heatmap(df: pd.DataFrame):
    if alt is None or df.empty:
        return None
    plot = df.copy()
    plot["skepticism_rate"] = plot["skepticism_positive"] / plot["resolved_comments"].where(plot["resolved_comments"] > 0, 1)
    return (
        alt.Chart(plot)
        .mark_rect()
        .encode(
            x=alt.X("run_id:O", title="Run ID"),
            y=alt.Y("channel_niche:N", title=None),
            color=alt.Color("skepticism_rate:Q", title="Skepticism rate", scale=alt.Scale(scheme="blues")),
            tooltip=[
                "run_id:O",
                "channel_niche:N",
                "resolved_comments:Q",
                "skepticism_positive:Q",
                alt.Tooltip("skepticism_rate:Q", format=".3f"),
            ],
        )
        .properties(width=860, height=220, title="Validated Skepticism Prevalence by Run and Niche")
    )


def export_paper_figure_pack(
    conn: sqlite3.Connection,
    *,
    out_dir: Path,
    freeze_id: int | None = None,
    freeze_name: str | None = None,
    include_flagged: bool = False,
) -> dict[str, Any]:
    freeze = _load_freeze(conn, freeze_id=freeze_id, freeze_name=freeze_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    metadata_df = _freeze_metadata_df(freeze)
    metadata_csv = out_dir / "figure_03_freeze_metadata.csv"
    metadata_df.to_csv(metadata_csv, index=False)

    prevalence_df = pd.DataFrame(freeze.prevalence_by_run_niche)
    prevalence_csv = out_dir / "figure_appendix_prevalence_by_run_niche.csv"
    prevalence_df.to_csv(prevalence_csv, index=False)

    corpus_counts = _corpus_counts_for_runs(conn, freeze.run_ids)
    labeled_summary = _labeled_summary_for_runs(conn, freeze.run_ids)
    funnel_df = _build_evidence_funnel_df(freeze, corpus_counts, labeled_summary)
    funnel_csv = out_dir / "figure_02_evidence_funnel.csv"
    funnel_df.to_csv(funnel_csv, index=False)

    workflow_mmd = out_dir / "figure_01_workflow_boundary.mmd"
    workflow_mmd.write_text(_workflow_mermaid_spec(), encoding="utf-8")

    resolved = _resolved_frame(conn, freeze.run_ids, include_flagged=include_flagged)
    if resolved.empty:
        raise RuntimeError("No resolved comments available for selected freeze scope.")
    input_df = _conformity_input_df(resolved)
    effects_repro_df, repro_summary, response_df = _reproducibility_tables(input_df)

    effects = effects_repro_df[
        [
            "term",
            "coef_log_odds_run1",
            "odds_ratio_run1",
            "p_value_approx_run1",
            "or_ci_95_low_run1",
            "or_ci_95_high_run1",
        ]
    ].rename(
        columns={
            "coef_log_odds_run1": "coef_log_odds",
            "odds_ratio_run1": "odds_ratio",
            "p_value_approx_run1": "p_value_approx",
            "or_ci_95_low_run1": "or_ci_95_low",
            "or_ci_95_high_run1": "or_ci_95_high",
        }
    )
    effects["term_display"] = effects["term"].apply(_format_effect_term)
    effects_csv = out_dir / "figure_04_model_forest_effects.csv"
    effects.to_csv(effects_csv, index=False)

    repro_csv = out_dir / "figure_03_reproducibility_term_diffs.csv"
    effects_repro_df.to_csv(repro_csv, index=False)
    repro_json = out_dir / "figure_03_reproducibility_summary.json"
    repro_json.write_text(json.dumps(repro_summary, ensure_ascii=True, indent=2), encoding="utf-8")

    niches = sorted({str(x).strip() for x in response_df["channel_niche"].dropna().tolist() if str(x).strip()})
    predicted_df = _predicted_probs_df(effects, niches)
    predicted_csv = out_dir / "figure_05_predicted_probabilities.csv"
    predicted_df.to_csv(predicted_csv, index=False)

    chart_errors: list[str] = []
    funnel_chart = _chart_evidence_funnel(funnel_df)
    if funnel_chart is not None:
        err = _save_altair_html(funnel_chart, out_dir / "figure_02_evidence_funnel.html")
        if err:
            chart_errors.append(err)

    forest_chart = _chart_forest(effects)
    if forest_chart is not None:
        err = _save_altair_html(forest_chart, out_dir / "figure_04_model_forest_plot.html")
        if err:
            chart_errors.append(err)

    predicted_chart = _chart_predicted_probs(predicted_df)
    if predicted_chart is not None:
        err = _save_altair_html(predicted_chart, out_dir / "figure_05_predicted_probabilities.html")
        if err:
            chart_errors.append(err)

    heatmap_chart = _chart_prevalence_heatmap(prevalence_df)
    if heatmap_chart is not None:
        err = _save_altair_html(heatmap_chart, out_dir / "figure_appendix_prevalence_heatmap.html")
        if err:
            chart_errors.append(err)

    headline_term = effects.loc[effects["term"] == "top_comment_skeptical"]
    headline_or = float(headline_term["odds_ratio"].iloc[0]) if not headline_term.empty else None
    headline_p = float(headline_term["p_value_approx"].iloc[0]) if not headline_term.empty else None

    manifest = {
        "freeze_id": freeze.freeze_id,
        "freeze_uuid": freeze.freeze_uuid,
        "freeze_name": freeze.freeze_name,
        "freeze_timestamp": freeze.freeze_timestamp,
        "run_ids_included": list(freeze.run_ids),
        "resolved_comment_count": int(freeze.summary.get("resolved_comments", 0) or 0),
        "chart_engine": "altair" if alt is not None else "csv_only",
        "chart_errors": chart_errors,
        "headline_h1_odds_ratio": headline_or,
        "headline_h1_p_value_approx": headline_p,
        "reproducibility_summary": repro_summary,
        "generated_files": sorted([p.name for p in out_dir.iterdir() if p.is_file()]),
    }
    (out_dir / "paper_figure_pack_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )

    return {
        "manifest": manifest,
        "files": {p.name: str(p) for p in sorted(out_dir.iterdir()) if p.is_file()},
    }
