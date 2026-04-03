from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .auto_analysis import build_auto_analysis_frames


def build_no_disclosure_ai_signal_frames(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    include_flagged: bool = False,
    min_ai_signal_comments: int = 1,
) -> dict[str, pd.DataFrame]:
    frames = build_auto_analysis_frames(conn, run_id, include_flagged=include_flagged)
    comments = frames["comments_auto"].copy()
    videos = frames["videos_auto"].copy()

    if comments.empty or videos.empty:
        empty = pd.DataFrame()
        summary = pd.DataFrame(
            [
                {
                    "run_id": run_id,
                    "include_flagged": int(include_flagged),
                    "videos_total": int(len(videos)),
                    "comments_total": int(len(comments)),
                    "videos_no_disclosure": 0,
                    "comments_no_disclosure": 0,
                    "comments_ai_signal_no_disclosure": 0,
                    "videos_with_ai_signal_no_disclosure": 0,
                }
            ]
        )
        return {
            "summary": summary,
            "signal_comments": empty,
            "video_signal_summary": empty,
            "channel_signal_summary": empty,
            "niche_signal_summary": empty,
            "candidate_videos": empty,
        }

    merge_cols = [
        "video_id",
        "channel_id",
        "channel_niche",
        "auto_disclosure_level",
        "auto_disclosure_label",
        "video_url",
        "title",
        "published_at",
    ]
    cm = comments.merge(videos[merge_cols], on=["video_id", "channel_id", "channel_niche"], how="left")

    no_disclosure = cm[cm["auto_disclosure_level"] == 0].copy()
    no_disclosure["ai_signal_comment"] = no_disclosure["auto_ai_mention"].astype(int)

    signal_comments = no_disclosure[no_disclosure["ai_signal_comment"] == 1].copy()
    signal_comments = signal_comments.sort_values(
        ["channel_niche", "channel_id", "video_id", "comment_rank"],
        ascending=[True, True, True, True],
    )

    video_signal_summary = (
        no_disclosure.groupby(
            [
                "channel_niche",
                "channel_id",
                "video_id",
                "published_at",
                "video_url",
                "title",
                "auto_disclosure_label",
            ],
            as_index=False,
        )
        .agg(
            comments_no_disclosure=("comment_db_id", "count"),
            ai_signal_comments=("ai_signal_comment", "sum"),
            skepticism_comments=("auto_skepticism", "sum"),
            proof_demand_comments=("auto_proof_demand", "sum"),
            normalization_comments=("auto_normalization", "sum"),
        )
        .sort_values(["ai_signal_comments", "skepticism_comments"], ascending=[False, False])
    )
    if not video_signal_summary.empty:
        video_signal_summary["ai_signal_rate"] = (
            video_signal_summary["ai_signal_comments"] / video_signal_summary["comments_no_disclosure"]
        )
    else:
        video_signal_summary["ai_signal_rate"] = []

    channel_signal_summary = (
        video_signal_summary.groupby(["channel_niche", "channel_id"], as_index=False)
        .agg(
            videos_no_disclosure=("video_id", "count"),
            comments_no_disclosure=("comments_no_disclosure", "sum"),
            ai_signal_comments=("ai_signal_comments", "sum"),
            skepticism_comments=("skepticism_comments", "sum"),
            proof_demand_comments=("proof_demand_comments", "sum"),
        )
        .sort_values(["ai_signal_comments", "videos_no_disclosure"], ascending=[False, False])
    )
    if not channel_signal_summary.empty:
        channel_signal_summary["ai_signal_rate"] = (
            channel_signal_summary["ai_signal_comments"] / channel_signal_summary["comments_no_disclosure"]
        )
    else:
        channel_signal_summary["ai_signal_rate"] = []

    niche_signal_summary = (
        video_signal_summary.groupby("channel_niche", as_index=False)
        .agg(
            videos_no_disclosure=("video_id", "count"),
            comments_no_disclosure=("comments_no_disclosure", "sum"),
            ai_signal_comments=("ai_signal_comments", "sum"),
            skepticism_comments=("skepticism_comments", "sum"),
            proof_demand_comments=("proof_demand_comments", "sum"),
        )
        .sort_values("channel_niche")
    )
    if not niche_signal_summary.empty:
        niche_signal_summary["ai_signal_rate"] = (
            niche_signal_summary["ai_signal_comments"] / niche_signal_summary["comments_no_disclosure"]
        )
    else:
        niche_signal_summary["ai_signal_rate"] = []

    candidate_videos = video_signal_summary[
        video_signal_summary["ai_signal_comments"] >= int(max(min_ai_signal_comments, 1))
    ].copy()

    summary = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "include_flagged": int(include_flagged),
                "videos_total": int(len(videos)),
                "comments_total": int(len(comments)),
                "videos_no_disclosure": int(video_signal_summary["video_id"].nunique()),
                "comments_no_disclosure": int(len(no_disclosure)),
                "comments_ai_signal_no_disclosure": int(len(signal_comments)),
                "videos_with_ai_signal_no_disclosure": int(candidate_videos["video_id"].nunique()),
            }
        ]
    )

    return {
        "summary": summary,
        "signal_comments": signal_comments,
        "video_signal_summary": video_signal_summary,
        "channel_signal_summary": channel_signal_summary,
        "niche_signal_summary": niche_signal_summary,
        "candidate_videos": candidate_videos,
    }


def export_exploratory_report(
    conn: sqlite3.Connection,
    run_id: int,
    out_dir: Path,
    *,
    include_flagged: bool = False,
    min_ai_signal_comments: int = 1,
) -> dict[str, Path]:
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir.mkdir(parents=True, exist_ok=True)

    frames = build_no_disclosure_ai_signal_frames(
        conn,
        run_id,
        include_flagged=include_flagged,
        min_ai_signal_comments=min_ai_signal_comments,
    )

    files = {
        "exploratory_summary": out_dir / f"exploratory_summary_run_{run_id}_{stamp}.csv",
        "exploratory_signal_comments": out_dir / f"exploratory_signal_comments_run_{run_id}_{stamp}.csv",
        "exploratory_video_summary": out_dir / f"exploratory_video_summary_run_{run_id}_{stamp}.csv",
        "exploratory_channel_summary": out_dir / f"exploratory_channel_summary_run_{run_id}_{stamp}.csv",
        "exploratory_niche_summary": out_dir / f"exploratory_niche_summary_run_{run_id}_{stamp}.csv",
        "exploratory_candidate_videos": out_dir / f"exploratory_candidate_videos_run_{run_id}_{stamp}.csv",
    }

    for key, path in files.items():
        frame_key = key.replace("exploratory_", "")
        if frame_key == "candidate_videos":
            frames["candidate_videos"].to_csv(path, index=False)
        elif frame_key == "signal_comments":
            frames["signal_comments"].to_csv(path, index=False)
        elif frame_key == "video_summary":
            frames["video_signal_summary"].to_csv(path, index=False)
        elif frame_key == "channel_summary":
            frames["channel_signal_summary"].to_csv(path, index=False)
        elif frame_key == "niche_summary":
            frames["niche_signal_summary"].to_csv(path, index=False)
        elif frame_key == "summary":
            frames["summary"].to_csv(path, index=False)

    return files
