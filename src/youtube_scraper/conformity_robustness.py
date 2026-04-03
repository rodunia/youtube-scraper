from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from math import exp, pi
from pathlib import Path

import pandas as pd
from scipy.stats import norm
from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM

from .auto_analysis import SKEPTICISM_REGEX
from .conformity_cascade import build_response_frame, rank_comments


@dataclass
class RobustnessFrames:
    input_df: pd.DataFrame
    ranked_df: pd.DataFrame
    response_df: pd.DataFrame
    effects_df: pd.DataFrame


def _load_comments_for_runs(
    conn: sqlite3.Connection,
    run_ids: list[int],
    *,
    include_flagged: bool,
    non_shorts_only: bool,
) -> pd.DataFrame:
    if not run_ids:
        raise ValueError("run_ids cannot be empty")

    placeholders = ",".join(["?"] * len(run_ids))
    query = f"""
    SELECT
        c.run_id,
        v.video_id,
        ch.channel_id,
        ch.niche AS channel_niche,
        c.cleaned_text AS comment_text,
        c.like_count,
        c.published_at AS comment_timestamp,
        v.video_url
    FROM comments c
    JOIN videos v ON c.video_db_id = v.id
    JOIN channels ch ON c.channel_db_id = ch.id
    WHERE c.run_id IN ({placeholders})
    """
    params: list[object] = list(run_ids)

    if not include_flagged:
        query += " AND c.is_spam = 0 AND c.is_template = 0 AND c.is_duplicate = 0"
    if non_shorts_only:
        query += " AND (v.video_url IS NULL OR v.video_url NOT LIKE '%/shorts/%')"

    df = pd.read_sql_query(query, conn, params=params)
    if df.empty:
        return df

    df["comment_text"] = df["comment_text"].fillna("")
    df["channel_niche"] = df["channel_niche"].fillna("Unknown")
    df["is_skeptical"] = df["comment_text"].str.contains(SKEPTICISM_REGEX, na=False).astype(int)
    return df


def _fit_row(
    *,
    model_name: str,
    response_df: pd.DataFrame,
    formula: str,
    vc_formulas: dict[str, str],
) -> dict[str, object]:
    row: dict[str, object] = {
        "model": model_name,
        "n_rows": int(len(response_df)),
        "videos": int(response_df["video_id"].nunique()),
        "channels": int(response_df["channel_id"].nunique()),
    }

    if response_df.empty:
        row["error"] = "empty_response_df"
        return row
    if response_df["is_skeptical"].nunique() < 2:
        row["error"] = "no_variation_in_dependent_variable"
        return row
    if response_df["top_comment_skeptical"].nunique() < 2:
        row["error"] = "no_variation_in_independent_variable"
        return row

    try:
        model = BinomialBayesMixedGLM.from_formula(formula, vc_formulas, response_df)
        fit = model.fit_vb()
    except Exception as exc:
        row["error"] = str(exc)
        return row

    for i, term in enumerate(model.exog_names):
        coef = float(fit.fe_mean[i])
        sd = float(fit.fe_sd[i])
        z_val = coef / sd if sd > 0 else 0.0
        p_val = float(2 * norm.sf(abs(z_val)))
        ci_low = coef - 1.96 * sd
        ci_high = coef + 1.96 * sd

        row[f"{term}__coef"] = coef
        row[f"{term}__or"] = exp(coef)
        row[f"{term}__p"] = p_val
        row[f"{term}__or_ci_low"] = exp(ci_low)
        row[f"{term}__or_ci_high"] = exp(ci_high)

    var_by_group: dict[str, float] = {}
    for name, log_sd in zip(model.vcp_names, fit.vcp_mean):
        var = float(exp(2 * float(log_sd)))
        var_by_group[name] = var
        row[f"var_{name}"] = var

    resid_var = (pi**2) / 3.0
    total_var = sum(var_by_group.values()) + resid_var
    for name, var in var_by_group.items():
        row[f"icc_{name}"] = (var / total_var) if total_var > 0 else 0.0
    row["icc_residual"] = resid_var / total_var if total_var > 0 else 0.0
    return row


def _build_full_formula(response_df: pd.DataFrame) -> str:
    niches = sorted([str(x) for x in response_df["channel_niche"].dropna().unique() if str(x)])
    if not niches:
        raise ValueError("No channel_niche values available for full moderated model")

    ref = "Lifestyle" if "Lifestyle" in niches else niches[0]
    niche_term = f"C(channel_niche, Treatment(reference='{ref}'))"
    return (
        "is_skeptical ~ "
        f"top_comment_skeptical * {niche_term} + "
        "top_comment_skeptical * top_comment_like_count_z + "
        "top_comment_skeptical * hours_since_top_comment_z + "
        "top_comment_like_count_z + "
        "hours_since_top_comment_z"
    )


def run_robustness_suite(
    conn: sqlite3.Connection,
    *,
    run_ids: list[int],
    include_flagged: bool = False,
    non_shorts_only: bool = True,
    min_response_comments: int = 10,
) -> RobustnessFrames:
    input_df = _load_comments_for_runs(
        conn,
        run_ids,
        include_flagged=include_flagged,
        non_shorts_only=non_shorts_only,
    )
    if input_df.empty:
        empty = pd.DataFrame()
        return RobustnessFrames(input_df=empty, ranked_df=empty, response_df=empty, effects_df=empty)

    ranked = rank_comments(input_df)
    response = build_response_frame(ranked)

    rows: list[dict[str, object]] = []
    base_formula = "is_skeptical ~ top_comment_skeptical"

    rows.append(
        _fit_row(
            model_name="base_channel_re",
            response_df=response,
            formula=base_formula,
            vc_formulas={"channel_re": "0 + C(channel_id)"},
        )
    )

    rows.append(
        _fit_row(
            model_name="robust_channel_video_re",
            response_df=response,
            formula=base_formula,
            vc_formulas={"channel_re": "0 + C(channel_id)", "video_re": "0 + C(video_id)"},
        )
    )

    if min_response_comments > 1:
        counts = response.groupby("video_id", as_index=False).size().rename(columns={"size": "response_n"})
        keep_videos = set(counts.loc[counts["response_n"] >= min_response_comments, "video_id"])
        response_min = response[response["video_id"].isin(keep_videos)].copy()
    else:
        response_min = response
    rows.append(
        _fit_row(
            model_name=f"robust_min{int(min_response_comments)}_response_comments",
            response_df=response_min,
            formula=base_formula,
            vc_formulas={"channel_re": "0 + C(channel_id)"},
        )
    )

    rows.append(
        _fit_row(
            model_name="robust_full_moderated",
            response_df=response,
            formula=_build_full_formula(response),
            vc_formulas={"channel_re": "0 + C(channel_id)", "video_re": "0 + C(video_id)"},
        )
    )

    effects_df = pd.DataFrame(rows)
    return RobustnessFrames(input_df=input_df, ranked_df=ranked, response_df=response, effects_df=effects_df)


def export_robustness_suite(
    conn: sqlite3.Connection,
    *,
    run_ids: list[int],
    out_dir: Path,
    include_flagged: bool = False,
    non_shorts_only: bool = True,
    min_response_comments: int = 10,
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    run_label = "_".join(str(x) for x in sorted(run_ids))
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    frames = run_robustness_suite(
        conn,
        run_ids=run_ids,
        include_flagged=include_flagged,
        non_shorts_only=non_shorts_only,
        min_response_comments=min_response_comments,
    )

    files = {
        "input": out_dir / f"conformity_input_runs_{run_label}_{stamp}.csv",
        "ranked": out_dir / f"conformity_ranked_runs_{run_label}_{stamp}.csv",
        "response": out_dir / f"conformity_response_runs_{run_label}_{stamp}.csv",
        "robustness_effects": out_dir / f"conformity_nonshorts_robustness_runs_{run_label}_{stamp}.csv",
    }
    frames.input_df.to_csv(files["input"], index=False)
    frames.ranked_df.to_csv(files["ranked"], index=False)
    frames.response_df.to_csv(files["response"], index=False)
    frames.effects_df.to_csv(files["robustness_effects"], index=False)
    return files
