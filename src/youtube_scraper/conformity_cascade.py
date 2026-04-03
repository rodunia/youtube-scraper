from __future__ import annotations

from dataclasses import dataclass
from math import exp, pi
from pathlib import Path

import pandas as pd
from scipy.stats import norm
from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM


REQUIRED_COLUMNS = {
    "video_id",
    "channel_id",
    "channel_niche",
    "comment_text",
    "like_count",
    "comment_timestamp",
    "is_skeptical",
}


@dataclass
class ConformityCascadeResult:
    ranked_df: pd.DataFrame
    top_comment_skeptical: dict[str, int]
    response_df: pd.DataFrame
    effects_df: pd.DataFrame
    icc_df: pd.DataFrame
    model_summary: str


def _validate_columns(df: pd.DataFrame) -> None:
    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"Input dataframe missing required columns: {missing}")


def _zscore(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    mean = float(s.mean()) if len(s) else 0.0
    sd = float(s.std(ddof=0)) if len(s) else 0.0
    if sd <= 0:
        return pd.Series(0.0, index=series.index)
    return (s - mean) / sd


def rank_comments(df: pd.DataFrame) -> pd.DataFrame:
    _validate_columns(df)
    ranked = df.copy()
    ranked["like_count"] = pd.to_numeric(ranked["like_count"], errors="coerce").fillna(0).astype(int)
    ranked["comment_timestamp"] = pd.to_datetime(ranked["comment_timestamp"], errors="coerce", utc=True)
    ranked["is_skeptical"] = pd.to_numeric(ranked["is_skeptical"], errors="coerce")
    ranked["channel_niche"] = ranked["channel_niche"].fillna("").astype(str)

    ranked = ranked.sort_values(
        by=["video_id", "like_count", "comment_timestamp"],
        ascending=[True, False, True],
        kind="mergesort",
    )
    ranked["rank"] = ranked.groupby("video_id").cumcount() + 1
    return ranked


def build_top_comment_mapping(ranked: pd.DataFrame) -> dict[str, int]:
    top = ranked.loc[ranked["rank"] == 1, ["video_id", "is_skeptical"]].dropna(subset=["is_skeptical"])
    top = top.drop_duplicates("video_id")
    top["is_skeptical"] = top["is_skeptical"].astype(int)
    return dict(zip(top["video_id"], top["is_skeptical"]))


def build_response_frame(ranked: pd.DataFrame) -> pd.DataFrame:
    top = ranked.loc[ranked["rank"] == 1, ["video_id", "is_skeptical", "like_count", "comment_timestamp"]].copy()
    top = top.rename(
        columns={
            "is_skeptical": "top_comment_skeptical",
            "like_count": "top_comment_like_count",
            "comment_timestamp": "top_comment_timestamp",
        }
    )

    response = ranked.loc[(ranked["rank"] > 1) & (ranked["rank"] <= 20)].copy()
    response = response.merge(top, on="video_id", how="left")
    response = response.dropna(
        subset=["is_skeptical", "top_comment_skeptical", "top_comment_timestamp", "comment_timestamp"]
    )

    response["is_skeptical"] = response["is_skeptical"].astype(int)
    response["top_comment_skeptical"] = response["top_comment_skeptical"].astype(int)
    response["top_comment_like_count"] = pd.to_numeric(
        response["top_comment_like_count"], errors="coerce"
    ).fillna(0.0)
    delta_hours = (
        (response["comment_timestamp"] - response["top_comment_timestamp"]).dt.total_seconds() / 3600.0
    )
    response["hours_since_top_comment"] = delta_hours.clip(lower=0.0)
    response["top_comment_like_count_z"] = _zscore(response["top_comment_like_count"])
    response["hours_since_top_comment_z"] = _zscore(response["hours_since_top_comment"])
    return response


def _reference_niche(response_df: pd.DataFrame) -> str:
    levels = sorted(
        {
            str(value).strip()
            for value in response_df["channel_niche"].dropna().tolist()
            if str(value).strip()
        }
    )
    if not levels:
        raise ValueError("channel_niche has no usable levels in response dataframe.")
    if "Lifestyle" in levels:
        return "Lifestyle"
    return levels[0]


def _fit_conformity_model(response_df: pd.DataFrame):
    if response_df.empty:
        raise ValueError("Response dataframe is empty after filtering to ranks 2..20.")
    if response_df["is_skeptical"].nunique() < 2:
        counts = response_df["is_skeptical"].value_counts(dropna=False).to_dict()
        raise ValueError(
            "Dependent variable has no variation in response dataframe. "
            f"is_skeptical counts={counts}"
        )
    if response_df["top_comment_skeptical"].nunique() < 2:
        counts = response_df["top_comment_skeptical"].value_counts(dropna=False).to_dict()
        raise ValueError(
            "Independent variable has no variation in response dataframe. "
            f"top_comment_skeptical counts={counts}"
        )

    reference_niche = _reference_niche(response_df)
    formula = (
        "is_skeptical ~ "
        f"top_comment_skeptical * C(channel_niche, Treatment(reference='{reference_niche}')) + "
        "top_comment_skeptical * top_comment_like_count_z + "
        "top_comment_skeptical * hours_since_top_comment_z + "
        "top_comment_like_count_z + hours_since_top_comment_z"
    )
    vc_formulas = {
        "channel_re": "0 + C(channel_id)",
        "video_re": "0 + C(video_id)",
    }
    model = BinomialBayesMixedGLM.from_formula(formula, vc_formulas, response_df)
    result = model.fit_vb()
    return model, result


def _fixed_effects_table(model, result) -> pd.DataFrame:
    rows = []
    for i, name in enumerate(model.exog_names):
        coef = float(result.fe_mean[i])
        sd = float(result.fe_sd[i])
        z_value = coef / sd if sd > 0 else 0.0
        p_value = float(2 * norm.sf(abs(z_value)))
        ci_low = coef - 1.96 * sd
        ci_high = coef + 1.96 * sd
        rows.append(
            {
                "term": name,
                "coef_log_odds": coef,
                "sd": sd,
                "z_approx": z_value,
                "p_value_approx": p_value,
                "odds_ratio": exp(coef),
                "or_ci_95_low": exp(ci_low),
                "or_ci_95_high": exp(ci_high),
            }
        )
    return pd.DataFrame(rows)


def _icc_table(model, result) -> pd.DataFrame:
    var_by_group: dict[str, float] = {}
    for name, log_sd in zip(model.vcp_names, result.vcp_mean):
        var_by_group[name] = float(exp(2 * float(log_sd)))

    # Logistic latent residual variance.
    resid_var = (pi**2) / 3.0
    total = sum(var_by_group.values()) + resid_var

    rows = []
    for name, var in var_by_group.items():
        rows.append(
            {
                "group": name,
                "variance_component": var,
                "icc": (var / total) if total > 0 else 0.0,
            }
        )
    rows.append({"group": "residual_logistic", "variance_component": resid_var, "icc": resid_var / total})
    return pd.DataFrame(rows)


def run_conformity_cascade(df: pd.DataFrame) -> ConformityCascadeResult:
    ranked = rank_comments(df)
    top_mapping = build_top_comment_mapping(ranked)
    response = build_response_frame(ranked)
    model, result = _fit_conformity_model(response)
    effects_df = _fixed_effects_table(model, result)
    icc_df = _icc_table(model, result)

    return ConformityCascadeResult(
        ranked_df=ranked,
        top_comment_skeptical=top_mapping,
        response_df=response,
        effects_df=effects_df,
        icc_df=icc_df,
        model_summary=str(result.summary()),
    )


def run_from_csv(
    *,
    input_csv: Path,
    output_ranked_csv: Path | None = None,
    output_response_csv: Path | None = None,
    output_effects_csv: Path | None = None,
    output_icc_csv: Path | None = None,
) -> ConformityCascadeResult:
    df = pd.read_csv(input_csv)
    res = run_conformity_cascade(df)

    if output_ranked_csv:
        output_ranked_csv.parent.mkdir(parents=True, exist_ok=True)
        res.ranked_df.to_csv(output_ranked_csv, index=False)
    if output_response_csv:
        output_response_csv.parent.mkdir(parents=True, exist_ok=True)
        res.response_df.to_csv(output_response_csv, index=False)
    if output_effects_csv:
        output_effects_csv.parent.mkdir(parents=True, exist_ok=True)
        res.effects_df.to_csv(output_effects_csv, index=False)
    if output_icc_csv:
        output_icc_csv.parent.mkdir(parents=True, exist_ok=True)
        res.icc_df.to_csv(output_icc_csv, index=False)
    return res
