#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Allow imports from src/ when running as: python scripts/targeted_skeptical_queue.py
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from youtube_scraper.auto_analysis import (  # noqa: E402
    AI_MENTION_REGEX,
    PROOF_DEMAND_REGEX,
    SKEPTICISM_REGEX,
    analyze_comment_text_features,
)


DEFAULT_DB_PATH = Path("data/youtube_comments.db")
DEFAULT_OUT_DIR = Path("outputs")
DEFAULT_FREEZE_NAME = "KES-final"
DEFAULT_MAX_THREADS = 400
DEFAULT_MAX_VIDEOS = 200
DEFAULT_MIN_THREAD_SCORE = 3.0
DEFAULT_MIN_CHANNEL_RESOLVED = 12
DEFAULT_MIN_CHANNEL_SKEPTICISM_RATE = 0.08

EXPLORATORY_LABEL = "Exploratory candidate for validation - not paper-safe by default"
LOGIC_VERSION = "targeted_skeptical_queue.v1"


@dataclass(frozen=True)
class FreezeRecord:
    freeze_id: int
    freeze_uuid: str
    freeze_name: str
    created_at: str
    run_ids: list[int]


def _placeholders(n: int) -> str:
    return ",".join(["?"] * n)


def _load_freeze(conn: sqlite3.Connection, freeze_name: str) -> FreezeRecord:
    row = conn.execute(
        """
        SELECT id, freeze_uuid, name, created_at, run_ids_json
        FROM evidence_freezes
        WHERE name = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (freeze_name.strip(),),
    ).fetchone()
    if row is None:
        raise RuntimeError(f"Freeze `{freeze_name}` not found.")
    run_ids = json.loads(row["run_ids_json"]) if row["run_ids_json"] else []
    if not isinstance(run_ids, list) or not run_ids:
        raise RuntimeError(f"Freeze `{freeze_name}` has no run IDs.")
    return FreezeRecord(
        freeze_id=int(row["id"]),
        freeze_uuid=str(row["freeze_uuid"] or ""),
        freeze_name=str(row["name"] or ""),
        created_at=str(row["created_at"] or ""),
        run_ids=[int(x) for x in run_ids],
    )


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
            c.run_id,
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
        run_id,
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


def _annotation_status(conn: sqlite3.Connection) -> pd.DataFrame:
    q = """
    SELECT
        a.comment_db_id,
        COUNT(*) AS annotation_count,
        COUNT(DISTINCT a.annotator_id) AS coder_count,
        MAX(a.is_adjudicated) AS has_adjudicated,
        MIN(COALESCE(a.skepticism_fake_callout, 0)) AS min_skepticism,
        MAX(COALESCE(a.skepticism_fake_callout, 0)) AS max_skepticism,
        MIN(COALESCE(a.proof_demand, 0)) AS min_proof_demand,
        MAX(COALESCE(a.proof_demand, 0)) AS max_proof_demand,
        MIN(COALESCE(a.normalization_defense, 0)) AS min_normalization,
        MAX(COALESCE(a.normalization_defense, 0)) AS max_normalization
    FROM annotations a
    GROUP BY a.comment_db_id
    """
    df = pd.read_sql_query(q, conn)
    if df.empty:
        return df
    df["has_disagreement"] = (
        (df["coder_count"] >= 2)
        & (
            (df["min_skepticism"] != df["max_skepticism"])
            | (df["min_proof_demand"] != df["max_proof_demand"])
            | (df["min_normalization"] != df["max_normalization"])
        )
    ).astype(int)
    return df


def _comment_pool(conn: sqlite3.Connection) -> pd.DataFrame:
    q = """
    SELECT
        c.id AS comment_db_id,
        c.run_id,
        ch.channel_id,
        ch.niche AS channel_niche,
        v.video_id,
        v.video_url,
        COALESCE(v.title, '') AS title,
        COALESCE(v.description, '') AS description,
        COALESCE(v.published_at, '') AS published_at,
        COALESCE(v.comments_scanned, 0) AS comments_scanned,
        c.comment_rank,
        c.like_count,
        c.reply_count,
        COALESCE(c.cleaned_text, '') AS cleaned_text,
        c.is_spam,
        c.is_template,
        c.is_duplicate
    FROM comments c
    JOIN channels ch ON ch.id = c.channel_db_id
    JOIN videos v ON v.id = c.video_db_id
    """
    return pd.read_sql_query(q, conn)


def _normalize_text_for_dedup(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _selection_reasons(row: pd.Series) -> str:
    reasons: list[str] = []
    if int(row.get("rule_skepticism", 0)) == 1:
        reasons.append("skepticism lexical cue")
    if int(row.get("rule_proof_demand", 0)) == 1:
        reasons.append("proof-demand lexical cue")
    if int(row.get("comment_rank", 99)) <= 3:
        reasons.append("top-ranked comment")
    if int(row.get("comment_ai_signal", 0)) == 1:
        reasons.append("AI mention in comment")
    elif int(row.get("video_ai_signal", 0)) == 1:
        reasons.append("AI mention in video metadata")
    if int(row.get("historical_skeptic_channel", 0)) == 1:
        reasons.append("historically skepticism-rich channel")
    if int(row.get("has_disagreement", 0)) == 1:
        reasons.append("existing coder disagreement")
    if float(row.get("engagement_norm", 0.0)) >= 0.45:
        reasons.append("higher engagement")
    if int(row.get("low_info_noise", 0)) == 1:
        reasons.append("low-info signal penalty applied")
    if not reasons:
        reasons.append("coverage candidate")
    return "; ".join(reasons)


def build_targeted_queue(
    *,
    db_path: Path,
    freeze_name: str,
    max_threads: int,
    max_videos: int,
    min_thread_score: float,
    min_channel_resolved: int,
    min_channel_skepticism_rate: float,
) -> dict[str, object]:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        freeze = _load_freeze(conn, freeze_name)
        pool = _comment_pool(conn)
        ann = _annotation_status(conn)
        resolved = _resolved_labels_for_runs(conn, freeze.run_ids)
    finally:
        conn.close()

    if pool.empty:
        raise RuntimeError("No comments found in database.")

    resolved_ids = set(resolved["comment_db_id"].tolist()) if not resolved.empty else set()
    freeze_run_set = set(freeze.run_ids)

    candidate = pool.copy()
    candidate["in_freeze_runs"] = candidate["run_id"].isin(freeze.run_ids).astype(int)
    candidate["in_resolved_freeze_layer"] = candidate["comment_db_id"].isin(resolved_ids).astype(int)
    candidate = candidate[candidate["in_resolved_freeze_layer"] == 0].copy()
    candidate = candidate[
        (candidate["is_spam"] == 0)
        & (candidate["is_template"] == 0)
        & (candidate["is_duplicate"] == 0)
    ].copy()
    post_boundary_filters_n = int(len(candidate))

    if candidate.empty:
        return {
            "freeze": freeze,
            "metadata": {
                "status": "no_candidates_after_filtering",
                "total_comments": int(len(pool)),
            },
            "threads": pd.DataFrame(),
            "videos": pd.DataFrame(),
        }

    if ann.empty:
        candidate["annotation_count"] = 0
        candidate["coder_count"] = 0
        candidate["has_disagreement"] = 0
    else:
        candidate = candidate.merge(
            ann[["comment_db_id", "annotation_count", "coder_count", "has_disagreement"]],
            on="comment_db_id",
            how="left",
        )
        for col in ["annotation_count", "coder_count", "has_disagreement"]:
            candidate[col] = pd.to_numeric(candidate[col], errors="coerce").fillna(0).astype(int)

    text = candidate["cleaned_text"].fillna("").astype(str)
    meta_text = (candidate["title"].fillna("").astype(str) + " " + candidate["description"].fillna("").astype(str)).str.strip()
    candidate["rule_skepticism"] = text.str.contains(SKEPTICISM_REGEX, na=False).astype(int)
    candidate["rule_proof_demand"] = text.str.contains(PROOF_DEMAND_REGEX, na=False).astype(int)
    candidate["comment_ai_signal"] = text.str.contains(AI_MENTION_REGEX, na=False).astype(int)
    candidate["video_ai_signal"] = meta_text.str.contains(AI_MENTION_REGEX, na=False).astype(int)
    candidate["top_rank_comment"] = (pd.to_numeric(candidate["comment_rank"], errors="coerce").fillna(999).astype(int) <= 3).astype(int)
    candidate["top_comment_only"] = (pd.to_numeric(candidate["comment_rank"], errors="coerce").fillna(999).astype(int) == 1).astype(int)
    candidate["high_comment_volume_video"] = (
        pd.to_numeric(candidate["comments_scanned"], errors="coerce").fillna(0).astype(float) >= 100
    ).astype(int)

    text_features = candidate["cleaned_text"].apply(lambda x: analyze_comment_text_features(str(x)))
    candidate["heuristic_language"] = text_features.apply(lambda x: str(x.get("heuristic_language", "unknown")))
    candidate["low_info_noise"] = text_features.apply(lambda x: int(x.get("low_info_noise", 0)))

    likes = pd.to_numeric(candidate["like_count"], errors="coerce").fillna(0).clip(lower=0)
    replies = pd.to_numeric(candidate["reply_count"], errors="coerce").fillna(0).clip(lower=0)
    candidate["engagement_norm"] = np.clip((np.log1p(likes) + 0.7 * np.log1p(1 + 3 * replies)) / 8.0, 0.0, 1.0)

    if resolved.empty:
        channel_history = pd.DataFrame(columns=["channel_id", "channel_resolved_n", "channel_skepticism_rate"])
    else:
        history = resolved[["comment_db_id", "label_skepticism", "label_proof_demand"]].merge(
            pool[["comment_db_id", "channel_id"]],
            on="comment_db_id",
            how="left",
        )
        history["skeptic_or_proof"] = (
            (history["label_skepticism"].fillna(0).astype(int) == 1)
            | (history["label_proof_demand"].fillna(0).astype(int) == 1)
        ).astype(int)
        channel_history = (
            history.groupby("channel_id", as_index=False)
            .agg(
                channel_resolved_n=("comment_db_id", "count"),
                channel_skepticism_rate=("label_skepticism", "mean"),
                channel_skeptic_or_proof_rate=("skeptic_or_proof", "mean"),
            )
            .sort_values(["channel_skepticism_rate", "channel_resolved_n"], ascending=[False, False])
        )
    candidate = candidate.merge(channel_history, on="channel_id", how="left")
    candidate["channel_resolved_n"] = pd.to_numeric(candidate["channel_resolved_n"], errors="coerce").fillna(0).astype(int)
    candidate["channel_skepticism_rate"] = pd.to_numeric(candidate["channel_skepticism_rate"], errors="coerce").fillna(0.0)
    candidate["channel_skeptic_or_proof_rate"] = pd.to_numeric(
        candidate["channel_skeptic_or_proof_rate"], errors="coerce"
    ).fillna(0.0)
    candidate["historical_skeptic_channel"] = (
        (candidate["channel_resolved_n"] >= int(min_channel_resolved))
        & (candidate["channel_skepticism_rate"] >= float(min_channel_skepticism_rate))
    ).astype(int)

    candidate["thread_score"] = (
        3.5 * candidate["rule_skepticism"]
        + 3.0 * candidate["rule_proof_demand"]
        + 1.3 * candidate["top_rank_comment"]
        + 0.9 * candidate["top_comment_only"]
        + 1.0 * candidate["comment_ai_signal"]
        + 1.1 * candidate["video_ai_signal"]
        + 1.2 * candidate["historical_skeptic_channel"]
        + 0.8 * candidate["has_disagreement"]
        + 0.5 * candidate["high_comment_volume_video"]
        + 1.0 * candidate["engagement_norm"]
        - 0.8 * candidate["low_info_noise"]
    )

    candidate["any_signal"] = (
        (candidate["rule_skepticism"] == 1)
        | (candidate["rule_proof_demand"] == 1)
        | (candidate["comment_ai_signal"] == 1)
        | (candidate["video_ai_signal"] == 1)
    ).astype(int)
    candidate = candidate[
        (candidate["thread_score"] >= float(min_thread_score))
        | ((candidate["any_signal"] == 1) & (candidate["top_rank_comment"] == 1))
    ].copy()
    post_scoring_n = int(len(candidate))
    if candidate.empty:
        return {
            "freeze": freeze,
            "metadata": {
                "status": "no_candidates_after_scoring",
                "total_comments": int(len(pool)),
            },
            "threads": pd.DataFrame(),
            "videos": pd.DataFrame(),
        }

    candidate["dedup_text"] = candidate["cleaned_text"].apply(_normalize_text_for_dedup)
    candidate["thread_dedup_key"] = candidate["video_id"].astype(str) + "|" + candidate["dedup_text"]
    candidate = candidate.sort_values(
        ["thread_score", "like_count", "reply_count", "comment_rank", "comment_db_id"],
        ascending=[False, False, False, True, True],
        kind="mergesort",
    )
    candidate = candidate.drop_duplicates(subset=["thread_dedup_key"], keep="first").copy()
    candidate["selection_reasons"] = candidate.apply(_selection_reasons, axis=1)
    candidate["staging_label"] = EXPLORATORY_LABEL
    candidate["run_in_selected_freeze"] = candidate["run_id"].isin(freeze.run_ids).astype(int)
    candidate["coder_packet_hint"] = np.where(
        candidate["run_in_selected_freeze"] == 1,
        "Unresolved item from freeze-scoped run: human coding/adjudication required before freeze refresh.",
        "Outside selected freeze runs: human coding and adjudication required before any paper-facing use.",
    )
    candidate["recommended_action"] = np.where(
        candidate["run_in_selected_freeze"] == 1,
        "code_or_adjudicate_existing_video_then_refresh_freeze",
        "validate_and_adjudicate_before_future_freeze_inclusion",
    )
    candidate = candidate.head(int(max_threads)).copy()
    candidate["thread_queue_rank"] = range(1, len(candidate) + 1)

    candidate["skeptic_or_proof"] = ((candidate["rule_skepticism"] == 1) | (candidate["rule_proof_demand"] == 1)).astype(int)
    candidate["skeptic_or_proof_top_rank"] = ((candidate["skeptic_or_proof"] == 1) & (candidate["top_rank_comment"] == 1)).astype(int)
    candidate["skeptic_or_proof_top_comment"] = (
        (candidate["skeptic_or_proof"] == 1) & (candidate["top_comment_only"] == 1)
    ).astype(int)
    video_candidates = (
        candidate.groupby(
            [
                "run_id",
                "channel_id",
                "channel_niche",
                "video_id",
                "video_url",
                "title",
                "published_at",
                "run_in_selected_freeze",
            ],
            as_index=False,
        )
        .agg(
            candidate_threads=("comment_db_id", "count"),
            skeptical_or_proof_threads=("skeptic_or_proof", "sum"),
            skeptical_or_proof_top_rank_threads=("skeptic_or_proof_top_rank", "sum"),
            top_comment_skeptical_or_proof=("skeptic_or_proof_top_comment", "sum"),
            max_thread_score=("thread_score", "max"),
            mean_thread_score=("thread_score", "mean"),
            high_engagement_threads=("engagement_norm", lambda s: int((s >= 0.45).sum())),
            disagreement_threads=("has_disagreement", "sum"),
            video_ai_signal=("video_ai_signal", "max"),
            historical_skeptic_channel=("historical_skeptic_channel", "max"),
        )
    )
    video_candidates["video_score"] = (
        video_candidates["max_thread_score"]
        + 0.6 * np.log1p(video_candidates["candidate_threads"])
        + 0.35 * video_candidates["skeptical_or_proof_threads"]
        + 0.30 * video_candidates["video_ai_signal"]
        + 0.25 * video_candidates["historical_skeptic_channel"]
    )
    video_candidates["staging_label"] = EXPLORATORY_LABEL
    video_candidates["recommended_action"] = np.where(
        video_candidates["run_in_selected_freeze"] == 1,
        "queue_for_additional_coding_or_adjudication_before_next_freeze",
        "queue_for_human_validation_then_optional_future_freeze_inclusion",
    )
    video_candidates = video_candidates.sort_values(
        ["video_score", "max_thread_score", "candidate_threads"],
        ascending=[False, False, False],
        kind="mergesort",
    ).head(int(max_videos)).copy()
    video_candidates["video_queue_rank"] = range(1, len(video_candidates) + 1)

    outside_freeze = pool[~pool["run_id"].isin(list(freeze_run_set))].copy()
    metadata = {
        "status": "ok",
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(),
        "logic_version": LOGIC_VERSION,
        "db_path": str(db_path),
        "freeze_id": freeze.freeze_id,
        "freeze_uuid": freeze.freeze_uuid,
        "freeze_name": freeze.freeze_name,
        "freeze_created_at": freeze.created_at,
        "freeze_run_ids": freeze.run_ids,
        "total_comments": int(len(pool)),
        "comments_after_resolved_and_flag_filters": post_boundary_filters_n,
        "comments_after_scoring_before_cap": post_scoring_n,
        "candidate_threads_exported": int(len(candidate)),
        "candidate_videos_exported": int(len(video_candidates)),
        "candidate_channels_exported": int(candidate["channel_id"].nunique()),
        "outside_freeze_comments_available": int(len(outside_freeze)),
        "outside_freeze_videos_available": int(outside_freeze["video_id"].nunique()),
        "outside_freeze_channels_available": int(outside_freeze["channel_id"].nunique()),
        "new_external_acquisition_executed": 0,
    }
    return {
        "freeze": freeze,
        "metadata": metadata,
        "threads": candidate,
        "videos": video_candidates,
    }


def _write_markdown_report(
    *,
    out_path: Path,
    metadata: dict[str, object],
    videos: pd.DataFrame,
    threads: pd.DataFrame,
) -> None:
    lines: list[str] = []
    lines.append("# Targeted exploratory acquisition report")
    lines.append("")
    lines.append("## Scope")
    lines.append(f"- Generated at (UTC): `{metadata.get('generated_at_utc', '')}`")
    lines.append(f"- Logic version: `{metadata.get('logic_version', '')}`")
    lines.append(
        f"- Freeze anchor: `{metadata.get('freeze_name', '')}` "
        f"(id={metadata.get('freeze_id', '')}, uuid={metadata.get('freeze_uuid', '')})"
    )
    lines.append(f"- Freeze runs: `{metadata.get('freeze_run_ids', [])}`")
    lines.append(f"- Staging label: `{EXPLORATORY_LABEL}`")
    lines.append("")
    lines.append("## Safe insertion points in current pipeline")
    lines.append("- `resolve-targets` for converting seed channels/handles into stable IDs.")
    lines.append("- `run-batch` for controlled acquisition from curated target lists.")
    lines.append("- This queue script as a pre-acquisition and pre-coding targeting layer.")
    lines.append("- Human coding + adjudication + freeze refresh required before paper-facing claims.")
    lines.append("")
    lines.append("## Candidate selection heuristics (deterministic)")
    lines.append("- Skepticism and proof-demand lexical hits in comment text.")
    lines.append("- Top-rank position preference (rank <= 3, especially rank = 1).")
    lines.append("- AI-discourse context via comment text or video metadata mentions.")
    lines.append("- Channel prior from frozen resolved data (skepticism-rich channels).")
    lines.append("- Engagement and disagreement context to prioritize informative cases.")
    lines.append("- Dedup safeguard by `(video_id, normalized_comment_text)` before ranking.")
    lines.append("")
    lines.append("## Output counts")
    lines.append(f"- Total comments in DB: `{metadata.get('total_comments', 0)}`")
    lines.append(f"- Candidate threads exported: `{metadata.get('candidate_threads_exported', 0)}`")
    lines.append(f"- Candidate videos exported: `{metadata.get('candidate_videos_exported', 0)}`")
    lines.append(f"- Candidate channels represented: `{metadata.get('candidate_channels_exported', 0)}`")
    lines.append(
        "- Newly acquired channels/videos/comments in this run: `0` "
        "(this package generated a targeted queue from local data only)."
    )
    lines.append(
        f"- Exploratory material already outside selected freeze runs: "
        f"`{metadata.get('outside_freeze_channels_available', 0)}` channels, "
        f"`{metadata.get('outside_freeze_videos_available', 0)}` videos, "
        f"`{metadata.get('outside_freeze_comments_available', 0)}` comments."
    )
    lines.append("")
    if not videos.empty:
        lines.append("## Top 10 candidate videos")
        lines.append("")
        lines.append("| rank | run_id | channel_niche | video_id | video_score | candidate_threads | skeptical_or_proof_threads |")
        lines.append("|---:|---:|---|---|---:|---:|---:|")
        for _, row in videos.head(10).iterrows():
            lines.append(
                f"| {int(row['video_queue_rank'])} | {int(row['run_id'])} | "
                f"{row['channel_niche']} | {row['video_id']} | "
                f"{float(row['video_score']):.3f} | {int(row['candidate_threads'])} | "
                f"{int(row['skeptical_or_proof_threads'])} |"
            )
        lines.append("")
    if not threads.empty:
        lines.append("## Top 10 candidate threads")
        lines.append("")
        lines.append("| rank | run_id | video_id | comment_db_id | comment_rank | thread_score | reasons |")
        lines.append("|---:|---:|---|---:|---:|---:|---|")
        for _, row in threads.head(10).iterrows():
            lines.append(
                f"| {int(row['thread_queue_rank'])} | {int(row['run_id'])} | {row['video_id']} | "
                f"{int(row['comment_db_id'])} | {int(row['comment_rank'])} | "
                f"{float(row['thread_score']):.3f} | {str(row['selection_reasons'])} |"
            )
        lines.append("")
    lines.append("## Validation boundary")
    lines.append(
        "- These outputs are exploratory candidate queues only and must not be used as validated evidence."
    )
    lines.append(
        "- Any paper-facing update requires human coding, disagreement handling, adjudication, and freeze linkage."
    )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_outputs(
    *,
    out_dir: Path,
    payload: dict[str, object],
) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    threads = payload["threads"].copy()
    videos = payload["videos"].copy()
    metadata = payload["metadata"]

    thread_cols = [
        "thread_queue_rank",
        "thread_score",
        "staging_label",
        "recommended_action",
        "coder_packet_hint",
        "run_id",
        "run_in_selected_freeze",
        "channel_niche",
        "channel_id",
        "video_id",
        "video_url",
        "title",
        "published_at",
        "comment_db_id",
        "comment_rank",
        "like_count",
        "reply_count",
        "annotation_count",
        "coder_count",
        "has_disagreement",
        "rule_skepticism",
        "rule_proof_demand",
        "comment_ai_signal",
        "video_ai_signal",
        "historical_skeptic_channel",
        "channel_resolved_n",
        "channel_skepticism_rate",
        "channel_skeptic_or_proof_rate",
        "heuristic_language",
        "low_info_noise",
        "selection_reasons",
        "cleaned_text",
    ]
    video_cols = [
        "video_queue_rank",
        "video_score",
        "staging_label",
        "recommended_action",
        "run_id",
        "run_in_selected_freeze",
        "channel_niche",
        "channel_id",
        "video_id",
        "video_url",
        "title",
        "published_at",
        "candidate_threads",
        "skeptical_or_proof_threads",
        "top_comment_skeptical_or_proof",
        "max_thread_score",
        "mean_thread_score",
        "high_engagement_threads",
        "disagreement_threads",
        "video_ai_signal",
        "historical_skeptic_channel",
    ]
    if not threads.empty:
        threads = threads[thread_cols].copy()
    if not videos.empty:
        videos = videos[video_cols].copy()

    files = {
        "targeted_candidate_videos": out_dir / "targeted_candidate_videos.csv",
        "targeted_candidate_threads": out_dir / "targeted_candidate_threads.csv",
        "targeted_acquisition_report": out_dir / "targeted_acquisition_report.md",
        "targeted_acquisition_run_metadata": out_dir / "targeted_acquisition_run_metadata.json",
    }
    videos.to_csv(files["targeted_candidate_videos"], index=False)
    threads.to_csv(files["targeted_candidate_threads"], index=False)
    files["targeted_acquisition_run_metadata"].write_text(json.dumps(metadata, ensure_ascii=True, indent=2), encoding="utf-8")
    _write_markdown_report(
        out_path=files["targeted_acquisition_report"],
        metadata=metadata,
        videos=videos,
        threads=threads,
    )
    return files


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build targeted exploratory candidate queues for likely skeptical top-cue follow-up."
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH, help="SQLite database path.")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR, help="Output directory.")
    parser.add_argument("--freeze-name", default=DEFAULT_FREEZE_NAME, help="Named evidence freeze anchor.")
    parser.add_argument("--max-threads", type=int, default=DEFAULT_MAX_THREADS, help="Maximum thread candidates to export.")
    parser.add_argument("--max-videos", type=int, default=DEFAULT_MAX_VIDEOS, help="Maximum video candidates to export.")
    parser.add_argument(
        "--min-thread-score",
        type=float,
        default=DEFAULT_MIN_THREAD_SCORE,
        help="Minimum heuristic thread score threshold.",
    )
    parser.add_argument(
        "--min-channel-resolved",
        type=int,
        default=DEFAULT_MIN_CHANNEL_RESOLVED,
        help="Minimum resolved comments to treat channel prior as stable.",
    )
    parser.add_argument(
        "--min-channel-skepticism-rate",
        type=float,
        default=DEFAULT_MIN_CHANNEL_SKEPTICISM_RATE,
        help="Minimum historical skepticism rate for channel-level prior boost.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = build_targeted_queue(
        db_path=args.db_path,
        freeze_name=args.freeze_name,
        max_threads=max(1, int(args.max_threads)),
        max_videos=max(1, int(args.max_videos)),
        min_thread_score=float(args.min_thread_score),
        min_channel_resolved=max(1, int(args.min_channel_resolved)),
        min_channel_skepticism_rate=float(args.min_channel_skepticism_rate),
    )
    files = _write_outputs(out_dir=args.out_dir, payload=payload)
    metadata = payload["metadata"]
    print("Targeted exploratory queue generated:")
    print(f"- status: {metadata.get('status')}")
    print(f"- freeze: {metadata.get('freeze_name')} (id={metadata.get('freeze_id')}, uuid={metadata.get('freeze_uuid')})")
    print(f"- candidate videos: {metadata.get('candidate_videos_exported')}")
    print(f"- candidate threads: {metadata.get('candidate_threads_exported')}")
    print("- files:")
    for key, path in files.items():
        print(f"  - {key}: {path}")


if __name__ == "__main__":
    main()
