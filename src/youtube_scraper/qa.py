from __future__ import annotations

import sqlite3
from typing import Any


def build_run_qa_report(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    runtime_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_row = conn.execute(
        """
        SELECT
            id,
            execution_mode,
            content_type,
            target_file,
            target_count_requested,
            study_profile_name,
            run_truncated
        FROM runs
        WHERE id = ?
        """,
        (run_id,),
    ).fetchone()
    total_channels = conn.execute(
        "SELECT COUNT(DISTINCT channel_db_id) AS c FROM videos WHERE run_id = ?", (run_id,)
    ).fetchone()["c"]
    total_videos = conn.execute("SELECT COUNT(*) AS c FROM videos WHERE run_id = ?", (run_id,)).fetchone()[
        "c"
    ]
    total_comments = conn.execute(
        "SELECT COUNT(*) AS c FROM comments WHERE run_id = ?", (run_id,)
    ).fetchone()["c"]

    flags = conn.execute(
        """
        SELECT
            SUM(is_spam) AS spam_count,
            SUM(is_template) AS template_count,
            SUM(is_duplicate) AS duplicate_count
        FROM comments
        WHERE run_id = ?
        """,
        (run_id,),
    ).fetchone()

    engine = conn.execute(
        """
        SELECT
            COALESCE(v.collection_engine, 'unknown') AS source_engine,
            COUNT(c.id) AS c
        FROM videos v
        LEFT JOIN comments c ON c.video_db_id = v.id
        WHERE v.run_id = ?
        GROUP BY COALESCE(v.collection_engine, 'unknown')
        """,
        (run_id,),
    ).fetchall()

    niche_breakdown = conn.execute(
        """
        WITH video_counts AS (
            SELECT channel_db_id, COUNT(*) AS videos
            FROM videos
            WHERE run_id = ?
            GROUP BY channel_db_id
        ),
        comment_counts AS (
            SELECT channel_db_id, COUNT(*) AS comments
            FROM comments
            WHERE run_id = ?
            GROUP BY channel_db_id
        )
        SELECT
            ch.niche AS niche,
            COALESCE(SUM(vc.videos), 0) AS videos,
            COALESCE(SUM(cc.comments), 0) AS comments
        FROM channels ch
        LEFT JOIN video_counts vc ON vc.channel_db_id = ch.id
        LEFT JOIN comment_counts cc ON cc.channel_db_id = ch.id
        GROUP BY ch.niche
        ORDER BY ch.niche
        """,
        (run_id, run_id),
    ).fetchall()

    engine_counts = {row["source_engine"]: row["c"] for row in engine}
    video_engine = conn.execute(
        """
        SELECT
            COALESCE(collection_engine, 'unknown') AS collection_engine,
            COUNT(*) AS c
        FROM videos
        WHERE run_id = ?
        GROUP BY COALESCE(collection_engine, 'unknown')
        """,
        (run_id,),
    ).fetchall()
    comment_status_rows = conn.execute(
        """
        SELECT
            comment_status,
            COUNT(*) AS c
        FROM videos
        WHERE run_id = ?
        GROUP BY comment_status
        ORDER BY c DESC
        """,
        (run_id,),
    ).fetchall()
    attrition = conn.execute(
        """
        SELECT
            SUM(COALESCE(v.comments_scanned, 0)) AS comments_scanned,
            SUM(COALESCE(v.comments_saved, 0)) AS comments_saved,
            SUM(COALESCE(v.comments_filtered, 0)) AS comments_filtered,
            COUNT(DISTINCT CASE WHEN ch.coverage_shortfall = 1 THEN v.channel_db_id END) AS coverage_shortfall_channels,
            COUNT(DISTINCT CASE WHEN ch.no_shorts_available = 1 THEN v.channel_db_id END) AS no_shorts_available_channels,
            SUM(CASE WHEN v.extraction_failed = 1 THEN 1 ELSE 0 END) AS extraction_failed_videos
        FROM videos v
        JOIN channels ch ON ch.id = v.channel_db_id
        WHERE v.run_id = ?
        """,
        (run_id,),
    ).fetchone()
    niche_attrition = conn.execute(
        """
        WITH video_niche AS (
            SELECT
                ch.niche AS niche,
                COUNT(DISTINCT v.channel_db_id) AS channels,
                COUNT(v.id) AS videos,
                SUM(COALESCE(v.comments_scanned, 0)) AS comments_scanned,
                SUM(COALESCE(v.comments_saved, 0)) AS comments_saved,
                SUM(COALESCE(v.comments_filtered, 0)) AS comments_filtered,
                COUNT(DISTINCT CASE WHEN ch.coverage_shortfall = 1 THEN v.channel_db_id END) AS coverage_shortfall_channels,
                COUNT(DISTINCT CASE WHEN ch.no_shorts_available = 1 THEN v.channel_db_id END) AS no_shorts_available_channels,
                SUM(CASE WHEN v.comment_status = 'not_enough_comments' THEN 1 ELSE 0 END) AS not_enough_comment_videos,
                SUM(CASE WHEN v.comment_status = 'comments_disabled' THEN 1 ELSE 0 END) AS comments_disabled_videos,
                SUM(CASE WHEN v.extraction_failed = 1 THEN 1 ELSE 0 END) AS extraction_failed_videos
            FROM videos v
            JOIN channels ch ON ch.id = v.channel_db_id
            WHERE v.run_id = ?
            GROUP BY ch.niche
        ),
        comment_niche AS (
            SELECT
                ch.niche AS niche,
                COUNT(c.id) AS comments
            FROM comments c
            JOIN channels ch ON ch.id = c.channel_db_id
            WHERE c.run_id = ?
            GROUP BY ch.niche
        ),
        all_niches AS (
            SELECT niche FROM video_niche
            UNION
            SELECT niche FROM comment_niche
        )
        SELECT
            n.niche AS niche,
            COALESCE(v.channels, 0) AS channels,
            COALESCE(v.videos, 0) AS videos,
            COALESCE(c.comments, 0) AS comments,
            COALESCE(v.comments_scanned, 0) AS comments_scanned,
            COALESCE(v.comments_saved, 0) AS comments_saved,
            COALESCE(v.comments_filtered, 0) AS comments_filtered,
            COALESCE(v.coverage_shortfall_channels, 0) AS coverage_shortfall_channels,
            COALESCE(v.no_shorts_available_channels, 0) AS no_shorts_available_channels,
            COALESCE(v.not_enough_comment_videos, 0) AS not_enough_comment_videos,
            COALESCE(v.comments_disabled_videos, 0) AS comments_disabled_videos,
            COALESCE(v.extraction_failed_videos, 0) AS extraction_failed_videos
        FROM all_niches n
        LEFT JOIN video_niche v ON v.niche = n.niche
        LEFT JOIN comment_niche c ON c.niche = n.niche
        ORDER BY n.niche
        """,
        (run_id, run_id),
    ).fetchall()

    runtime_summary = runtime_summary or {}
    runtime_niche_attrition = runtime_summary.get("niche_attrition", {})
    merged_niche_attrition: dict[str, dict[str, Any]] = {
        str(row["niche"]): dict(row) for row in niche_attrition
    }
    for niche, stats in runtime_niche_attrition.items() if isinstance(runtime_niche_attrition, dict) else []:
        base = merged_niche_attrition.setdefault(
            str(niche),
            {
                "niche": str(niche),
                "channels": 0,
                "videos": 0,
                "comments": 0,
                "comments_scanned": 0,
                "comments_saved": 0,
                "comments_filtered": 0,
                "coverage_shortfall_channels": 0,
                "no_shorts_available_channels": 0,
                "not_enough_comment_videos": 0,
                "comments_disabled_videos": 0,
                "extraction_failed_videos": 0,
            },
        )
        if isinstance(stats, dict):
            base["requested_channels"] = int(stats.get("requested_channels", 0) or 0)
            base["collected_channels"] = int(stats.get("collected_channels", base.get("channels", 0)) or 0)
            base["coverage_shortfall_channels"] = int(stats.get("coverage_shortfall_channels", base.get("coverage_shortfall_channels", 0)) or 0)
            base["no_shorts_available_channels"] = int(stats.get("no_shorts_available_channels", base.get("no_shorts_available_channels", 0)) or 0)
            base["extraction_failed_channels"] = int(stats.get("extraction_failed_channels", 0) or 0)
    merged_niche_rows = []
    for niche_name in sorted(merged_niche_attrition):
        row = merged_niche_attrition[niche_name]
        row.setdefault("requested_channels", int(row.get("channels", 0) or 0))
        row.setdefault("collected_channels", int(row.get("channels", 0) or 0))
        row.setdefault("extraction_failed_channels", 0)
        merged_niche_rows.append(row)

    return {
        "run_id": run_id,
        "run_metadata": {
            "execution_mode": run_row["execution_mode"] if run_row else None,
            "content_type": run_row["content_type"] if run_row else None,
            "target_file": run_row["target_file"] if run_row else None,
            "target_count_requested": int(run_row["target_count_requested"] or 0) if run_row else 0,
            "study_profile_name": run_row["study_profile_name"] if run_row else None,
            "run_truncated": int(run_row["run_truncated"] or 0) if run_row else 0,
        },
        "channels_collected": int(total_channels or 0),
        "videos_collected": int(total_videos or 0),
        "comments_collected": int(total_comments or 0),
        "spam_count": int(flags["spam_count"] or 0),
        "template_count": int(flags["template_count"] or 0),
        "duplicate_count": int(flags["duplicate_count"] or 0),
        "api_comment_count": int(engine_counts.get("api", 0)),
        "playwright_comment_count": int(engine_counts.get("playwright", 0)),
        "video_engine_counts": [dict(row) for row in video_engine],
        "comment_engine_counts": [dict(row) for row in engine],
        "comment_status_counts": [dict(row) for row in comment_status_rows],
        "attrition": {
            "comments_scanned": int(attrition["comments_scanned"] or 0),
            "comments_saved": int(attrition["comments_saved"] or 0),
            "comments_filtered": int(attrition["comments_filtered"] or 0),
            "coverage_shortfall_channels": int(
                runtime_summary.get("coverage_shortfall_channels", attrition["coverage_shortfall_channels"] or 0) or 0
            ),
            "no_shorts_available_channels": int(
                runtime_summary.get("no_shorts_available_channels", attrition["no_shorts_available_channels"] or 0) or 0
            ),
            "extraction_failed_channels": int(runtime_summary.get("extraction_failed_channels", 0) or 0),
            "extraction_failed_videos": int(attrition["extraction_failed_videos"] or 0),
        },
        "niche_breakdown": [dict(row) for row in niche_breakdown],
        "niche_attrition": merged_niche_rows,
    }
