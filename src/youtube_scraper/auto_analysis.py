from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

AI_MENTION_REGEX = re.compile(
    r"\b(?:ai|artificial intelligence|chatgpt|gpt-?4|gpt|midjourney|stable diffusion|deepfake|synthetic|generated)\b",
    re.IGNORECASE,
)
DISCLOSURE_GENERIC_REGEX = re.compile(
    r"(?:made with ai|created with ai|ai[- ]generated|generated with ai|this is ai|using ai)",
    re.IGNORECASE,
)
DISCLOSURE_SPECIFIC_REGEX = re.compile(
    r"(?:midjourney|runway|elevenlabs|suno|pika|stable diffusion|comfyui|tool|workflow|prompt|voice model)",
    re.IGNORECASE,
)
DISCLOSURE_VERIFIABLE_REGEX = re.compile(
    r"(?:behind the scenes|bts|raw file|source file|project file|process footage|proof)",
    re.IGNORECASE,
)
SKEPTICISM_REGEX = re.compile(
    r"(?:fake|not real|is this real|deepfake|ai crap|ai slop|scam|lying|cap|staged)",
    re.IGNORECASE,
)
PROOF_DEMAND_REGEX = re.compile(
    r"(?:show (?:us|me) (?:the )?(?:proof|source|evidence|receipts|bts)|"
    r"where(?:'s| is) (?:the )?(?:proof|source|evidence)|"
    r"(?:need|want|got) (?:proof|source|evidence|receipts)|"
    r"(?:link|send|drop|post) (?:the )?(?:source|proof|evidence|receipts|bts)|"
    r"\breceipts\b|\bbts\b|behind the scenes)",
    re.IGNORECASE,
)
NORMALIZATION_REGEX = re.compile(
    r"(?:who cares|its fine|it's fine|nothing wrong|everyone does|not that deep|doesn't matter|no problem)",
    re.IGNORECASE,
)
SPANISH_HINT_REGEX = re.compile(
    r"\b(?:pero|porque|para|por|una|uno|gracias|mira|esta|este|está|sí|quiero|llorando|orgullosa|historia|verdadero)\b",
    re.IGNORECASE,
)
HINGLISH_HINT_REGEX = re.compile(
    r"\b(?:ki|hai|nhi|mujhe|sirf|toh|laga|marzi|paise|shadi|kyun|yrr|didi|woh|sab|phir|lagegi)\b",
    re.IGNORECASE,
)
NON_LATIN_SCRIPT_REGEX = re.compile(r"[\u0900-\u097F\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
LOW_INFO_GENERIC_REGEX = re.compile(
    r"^(?:\W|_)*(?:thanks?|thank you|nice|beautiful|awesome|congratulations|great advice|great video|love this|love it|wow|cool|amazing|yes|true|facts|exactly|bro|sir|please|ok|okay|lol|lmao|omg|rip|\u2705)(?:[\W_]+(?:thanks?|thank you|nice|beautiful|awesome|congratulations|great advice|great video|love this|love it|wow|cool|amazing|yes|true|facts|exactly|bro|sir|please|ok|okay|lol|lmao|omg|rip))*[\W_]*$",
    re.IGNORECASE,
)
OPEN_LEXICON_REGEXES: dict[str, re.Pattern[str]] = {
    "certainty": re.compile(r"\b(?:definitely|obviously|clearly|certainly|for sure|undeniably|always|never)\b", re.I),
    "doubt": re.compile(r"\b(?:maybe|perhaps|seems|looks like|probably|might|could|unsure|doubt)\b", re.I),
    "negation": re.compile(r"\b(?:not|never|no|nothing|none|don't|doesn't|isn't|can't|won't)\b", re.I),
    "request": re.compile(r"\b(?:please|show|explain|why|how|what|where|link|source|proof|can you)\b", re.I),
    "affect": re.compile(r"\b(?:love|hate|amazing|awful|scary|funny|sad|angry|crying|annoying)\b", re.I),
    "social": re.compile(r"\b(?:people|everyone|they|them|we|us|community|audience|creator)\b", re.I),
}


def infer_disclosure_level(text: str) -> int:
    if not text:
        return 0
    if DISCLOSURE_VERIFIABLE_REGEX.search(text):
        return 3
    if AI_MENTION_REGEX.search(text) and DISCLOSURE_SPECIFIC_REGEX.search(text):
        return 2
    if AI_MENTION_REGEX.search(text) and DISCLOSURE_GENERIC_REGEX.search(text):
        return 1
    if AI_MENTION_REGEX.search(text):
        return 1
    return 0


def disclosure_label(level: int) -> str:
    return {
        0: "0_none",
        1: "1_generic",
        2: "2_specific",
        3: "3_verifiable",
    }.get(level, "unknown")


def _choose_analysis_niche(label: str) -> str:
    if label in {"Tech", "Beauty"}:
        return "high_risk_proxy"
    return "low_risk_proxy"


def analyze_comment_text_features(text: str) -> dict[str, object]:
    raw = (text or "").strip()
    if not raw:
        return {
            "heuristic_language": "empty",
            "low_info_noise": 1,
            "lex_certainty": 0,
            "lex_doubt": 0,
            "lex_negation": 0,
            "lex_request": 0,
            "lex_affect": 0,
            "lex_social": 0,
        }

    if NON_LATIN_SCRIPT_REGEX.search(raw):
        heuristic_language = "other_script"
    elif re.search(r"[áéíóúñ¿¡]", raw, re.IGNORECASE) or len(SPANISH_HINT_REGEX.findall(raw)) >= 2:
        heuristic_language = "spanish_like"
    elif len(HINGLISH_HINT_REGEX.findall(raw)) >= 2:
        heuristic_language = "hinglish_like"
    else:
        heuristic_language = "english_or_other_latin"

    alnum_len = len(re.sub(r"[^A-Za-z0-9]+", "", raw))
    ascii_words = re.findall(r"[A-Za-z0-9]+", raw)
    low_info_noise = int(bool(LOW_INFO_GENERIC_REGEX.match(raw)) or (len(ascii_words) < 3 and alnum_len < 12))

    features = {
        "heuristic_language": heuristic_language,
        "low_info_noise": low_info_noise,
    }
    for key, regex in OPEN_LEXICON_REGEXES.items():
        features[f"lex_{key}"] = int(len(regex.findall(raw)))
    return features


def append_comment_text_features(df: pd.DataFrame, *, text_col: str = "cleaned_text") -> pd.DataFrame:
    c = df.copy()
    if c.empty:
        c["heuristic_language"] = []
        c["low_info_noise"] = []
        c["lex_certainty"] = []
        c["lex_doubt"] = []
        c["lex_negation"] = []
        c["lex_request"] = []
        c["lex_affect"] = []
        c["lex_social"] = []
        return c

    features_df = c[text_col].fillna("").apply(lambda x: pd.Series(analyze_comment_text_features(str(x))))
    return pd.concat([c.reset_index(drop=True), features_df.reset_index(drop=True)], axis=1)


def _load_comments(conn: sqlite3.Connection, run_id: int) -> pd.DataFrame:
    query = """
    SELECT
        c.id AS comment_db_id,
        c.run_id,
        ch.channel_id,
        ch.niche AS channel_niche,
        v.video_id,
        c.comment_rank,
        c.like_count,
        c.reply_count,
        c.cleaned_text,
        c.is_spam,
        c.is_template,
        c.is_duplicate,
        c.extraction_ts
    FROM comments c
    JOIN channels ch ON c.channel_db_id = ch.id
    JOIN videos v ON c.video_db_id = v.id
    WHERE c.run_id = ?
    ORDER BY ch.channel_id, v.video_id, c.comment_rank
    """
    return pd.read_sql_query(query, conn, params=(run_id,))


def _load_videos(conn: sqlite3.Connection, run_id: int) -> pd.DataFrame:
    query = """
    SELECT
        v.id AS video_db_id,
        v.run_id,
        ch.channel_id,
        ch.niche AS channel_niche,
        v.video_id,
        v.video_url,
        v.title,
        v.description,
        v.published_at,
        v.upload_index,
        v.comment_status,
        v.view_count
    FROM videos v
    JOIN channels ch ON v.channel_db_id = ch.id
    WHERE v.run_id = ?
    ORDER BY ch.channel_id, v.upload_index
    """
    return pd.read_sql_query(query, conn, params=(run_id,))


def _label_comments(df: pd.DataFrame) -> pd.DataFrame:
    c = df.copy()
    if c.empty:
        c["auto_skepticism"] = []
        c["auto_proof_demand"] = []
        c["auto_normalization"] = []
        c["auto_ai_mention"] = []
        return c
    c["cleaned_text"] = c["cleaned_text"].fillna("")
    c = append_comment_text_features(c, text_col="cleaned_text")
    c["auto_skepticism"] = c["cleaned_text"].str.contains(SKEPTICISM_REGEX, na=False).astype(int)
    c["auto_proof_demand"] = c["cleaned_text"].str.contains(PROOF_DEMAND_REGEX, na=False).astype(int)
    c["auto_normalization"] = c["cleaned_text"].str.contains(NORMALIZATION_REGEX, na=False).astype(int)
    c["auto_ai_mention"] = c["cleaned_text"].str.contains(AI_MENTION_REGEX, na=False).astype(int)
    return c


def _label_videos(df: pd.DataFrame) -> pd.DataFrame:
    v = df.copy()
    if v.empty:
        v["combined_text"] = []
        v["auto_has_ai_mention"] = []
        v["auto_disclosure_level"] = []
        v["auto_disclosure_label"] = []
        v["risk_group_proxy"] = []
        return v
    v["title"] = v["title"].fillna("")
    v["description"] = v["description"].fillna("")
    v["combined_text"] = (v["title"] + " " + v["description"]).str.strip()
    v["auto_has_ai_mention"] = v["combined_text"].str.contains(AI_MENTION_REGEX, na=False).astype(int)
    v["auto_disclosure_level"] = v["combined_text"].apply(infer_disclosure_level)
    v["auto_disclosure_label"] = v["auto_disclosure_level"].apply(disclosure_label)
    v["risk_group_proxy"] = v["channel_niche"].apply(_choose_analysis_niche)
    return v


def _compute_video_metrics(videos: pd.DataFrame, comments: pd.DataFrame) -> pd.DataFrame:
    if comments.empty:
        panel = videos.copy()
        panel["comments_n"] = 0
        panel["skepticism_rate"] = 0.0
        panel["proof_demand_rate"] = 0.0
        panel["normalization_rate"] = 0.0
        panel["ai_mention_rate"] = 0.0
        return panel

    comment_stats = (
        comments.groupby(["video_id", "channel_id", "channel_niche"], as_index=False)
        .agg(
            comments_n=("comment_db_id", "count"),
            skepticism_rate=("auto_skepticism", "mean"),
            proof_demand_rate=("auto_proof_demand", "mean"),
            normalization_rate=("auto_normalization", "mean"),
            ai_mention_rate=("auto_ai_mention", "mean"),
            avg_comment_like_count=("like_count", "mean"),
            avg_comment_reply_count=("reply_count", "mean"),
        )
    )
    panel = videos.merge(comment_stats, on=["video_id", "channel_id", "channel_niche"], how="left")
    fill_zero_cols = [
        "comments_n",
        "skepticism_rate",
        "proof_demand_rate",
        "normalization_rate",
        "ai_mention_rate",
        "avg_comment_like_count",
        "avg_comment_reply_count",
    ]
    for col in fill_zero_cols:
        panel[col] = panel[col].fillna(0)
    return panel


def _compute_hypothesis_metrics(panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty:
        return pd.DataFrame(columns=["metric", "value"])

    mean_none = panel.loc[panel["auto_disclosure_level"] == 0, "skepticism_rate"].mean()
    mean_generic = panel.loc[panel["auto_disclosure_level"] == 1, "skepticism_rate"].mean()
    mean_specific = panel.loc[panel["auto_disclosure_level"] >= 2, "skepticism_rate"].mean()
    h1_delta = mean_generic - mean_none if pd.notna(mean_generic) and pd.notna(mean_none) else None
    h2_delta = mean_specific - mean_generic if pd.notna(mean_specific) and pd.notna(mean_generic) else None
    h3_corr = panel["skepticism_rate"].corr(panel["proof_demand_rate"]) if len(panel) > 1 else None

    high = panel[panel["risk_group_proxy"] == "high_risk_proxy"]
    low = panel[panel["risk_group_proxy"] == "low_risk_proxy"]
    high_delta = (
        high.loc[high["auto_disclosure_level"] == 1, "skepticism_rate"].mean()
        - high.loc[high["auto_disclosure_level"] == 0, "skepticism_rate"].mean()
    )
    low_delta = (
        low.loc[low["auto_disclosure_level"] == 1, "skepticism_rate"].mean()
        - low.loc[low["auto_disclosure_level"] == 0, "skepticism_rate"].mean()
    )
    h5_delta = high_delta - low_delta if pd.notna(high_delta) and pd.notna(low_delta) else None

    lag_panel = panel.copy()
    lag_panel["published_at"] = pd.to_datetime(lag_panel["published_at"], errors="coerce")
    lag_panel = lag_panel.sort_values(["channel_id", "published_at", "upload_index"])
    lag_panel["lag1_skepticism_rate"] = lag_panel.groupby("channel_id")["skepticism_rate"].shift(1)
    lag_panel = lag_panel.dropna(subset=["lag1_skepticism_rate"])
    h4_corr = (
        lag_panel["lag1_skepticism_rate"].corr(lag_panel["auto_disclosure_level"])
        if len(lag_panel) > 1
        else None
    )

    rows = [
        ("mean_skepticism_none", mean_none),
        ("mean_skepticism_generic", mean_generic),
        ("mean_skepticism_specific_plus", mean_specific),
        ("h1_generic_minus_none", h1_delta),
        ("h2_specific_minus_generic", h2_delta),
        ("h3_corr_skepticism_proof_demand", h3_corr),
        ("h4_corr_lag1_skepticism_next_disclosure", h4_corr),
        ("h5_high_minus_low_h1_delta", h5_delta),
    ]
    return pd.DataFrame(rows, columns=["metric", "value"])


def build_auto_analysis_frames(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    include_flagged: bool = False,
) -> dict[str, pd.DataFrame]:
    comments_raw = _load_comments(conn, run_id)
    videos_raw = _load_videos(conn, run_id)

    if not include_flagged and not comments_raw.empty:
        comments_raw = comments_raw[
            (comments_raw["is_spam"] == 0)
            & (comments_raw["is_template"] == 0)
            & (comments_raw["is_duplicate"] == 0)
        ]

    comments = _label_comments(comments_raw)
    videos = _label_videos(videos_raw)
    video_metrics = _compute_video_metrics(videos, comments)

    if video_metrics.empty:
        channel_metrics = pd.DataFrame()
        niche_metrics = pd.DataFrame()
    else:
        channel_metrics = (
            video_metrics.groupby(["channel_id", "channel_niche"], as_index=False)
            .agg(
                videos=("video_id", "count"),
                comments=("comments_n", "sum"),
                skepticism_rate=("skepticism_rate", "mean"),
                proof_demand_rate=("proof_demand_rate", "mean"),
                normalization_rate=("normalization_rate", "mean"),
                disclosure_level_mean=("auto_disclosure_level", "mean"),
            )
            .sort_values(["channel_niche", "channel_id"])
        )

        niche_metrics = (
            video_metrics.groupby("channel_niche", as_index=False)
            .agg(
                channels=("channel_id", "nunique"),
                videos=("video_id", "count"),
                comments=("comments_n", "sum"),
                skepticism_rate=("skepticism_rate", "mean"),
                proof_demand_rate=("proof_demand_rate", "mean"),
                normalization_rate=("normalization_rate", "mean"),
                disclosure_level_mean=("auto_disclosure_level", "mean"),
            )
            .sort_values("channel_niche")
        )

    hypothesis_metrics = _compute_hypothesis_metrics(video_metrics)
    summary = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "videos": int(len(videos)),
                "comments_used": int(len(comments)),
                "channels": int(videos["channel_id"].nunique()) if not videos.empty else 0,
                "ai_mention_videos": int(videos["auto_has_ai_mention"].sum()) if not videos.empty else 0,
                "include_flagged": int(include_flagged),
            }
        ]
    )

    return {
        "summary": summary,
        "comments_auto": comments,
        "videos_auto": videos,
        "video_metrics": video_metrics,
        "channel_metrics": channel_metrics,
        "niche_metrics": niche_metrics,
        "hypothesis_metrics": hypothesis_metrics,
    }


def export_auto_analysis(
    conn: sqlite3.Connection,
    run_id: int,
    out_dir: Path,
    *,
    include_flagged: bool = False,
) -> dict[str, Path]:
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)

    frames = build_auto_analysis_frames(conn, run_id, include_flagged=include_flagged)
    files = {
        "auto_summary": out_dir / f"auto_summary_run_{run_id}_{stamp}.csv",
        "auto_comments": out_dir / f"auto_comments_run_{run_id}_{stamp}.csv",
        "auto_videos": out_dir / f"auto_videos_run_{run_id}_{stamp}.csv",
        "auto_video_metrics": out_dir / f"auto_video_metrics_run_{run_id}_{stamp}.csv",
        "auto_channel_metrics": out_dir / f"auto_channel_metrics_run_{run_id}_{stamp}.csv",
        "auto_niche_metrics": out_dir / f"auto_niche_metrics_run_{run_id}_{stamp}.csv",
        "auto_hypothesis_metrics": out_dir / f"auto_hypothesis_metrics_run_{run_id}_{stamp}.csv",
    }

    frame_map = {
        "auto_summary": frames["summary"],
        "auto_comments": frames["comments_auto"],
        "auto_videos": frames["videos_auto"],
        "auto_video_metrics": frames["video_metrics"],
        "auto_channel_metrics": frames["channel_metrics"],
        "auto_niche_metrics": frames["niche_metrics"],
        "auto_hypothesis_metrics": frames["hypothesis_metrics"],
    }

    for key, path in files.items():
        frame_map[key].to_csv(path, index=False)

    return files
