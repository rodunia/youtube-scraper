from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def _utc_stamp() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def export_query_to_csv(conn: sqlite3.Connection, query: str, params: tuple, output_file: Path) -> int:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    rows = conn.execute(query, params).fetchall()
    if not rows:
        output_file.write_text("", encoding="utf-8")
        return 0

    with output_file.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow([row[k] for k in row.keys()])
    return len(rows)


def export_run_datasets(conn: sqlite3.Connection, run_id: int, out_dir: Path) -> dict[str, Path]:
    stamp = _utc_stamp()

    comment_file = out_dir / f"comments_clean_run_{run_id}_{stamp}.csv"
    video_file = out_dir / f"videos_panel_run_{run_id}_{stamp}.csv"
    qa_file = out_dir / f"qa_run_{run_id}_{stamp}.csv"

    export_query_to_csv(
        conn,
        """
        SELECT
            c.id AS comment_db_id,
            c.run_id,
            ch.channel_id,
            ch.niche AS channel_niche,
            v.video_id,
            v.video_url,
            v.published_at AS video_publish_ts,
            c.comment_rank,
            c.extraction_ts,
            c.language,
            c.reply_count,
            c.like_count,
            c.published_at AS comment_timestamp,
            c.commenter_hash_id,
            c.raw_text,
            c.cleaned_text,
            c.is_spam,
            c.is_template,
            c.is_duplicate,
            c.spam_rule_hits,
            c.source_engine
        FROM comments c
        JOIN channels ch ON c.channel_db_id = ch.id
        JOIN videos v ON c.video_db_id = v.id
        WHERE c.run_id = ?
        ORDER BY ch.channel_id, v.upload_index, c.comment_rank
        """,
        (run_id,),
        comment_file,
    )

    export_query_to_csv(
        conn,
        """
        SELECT
            v.run_id,
            ch.channel_id,
            ch.niche AS channel_niche,
            v.video_id,
            v.video_url,
            v.published_at,
            v.upload_index,
            v.comment_status,
            v.view_count,
            v.disclosure_quality,
            AVG(c.is_spam) AS spam_rate,
            AVG(c.is_template) AS template_rate,
            AVG(c.is_duplicate) AS duplicate_rate,
            AVG(a.skepticism_fake_callout) AS skepticism_rate,
            AVG(a.proof_demand) AS proof_demand_rate,
            AVG(a.normalization_defense) AS normalization_rate
        FROM videos v
        JOIN channels ch ON v.channel_db_id = ch.id
        LEFT JOIN comments c ON c.video_db_id = v.id
        LEFT JOIN annotations a ON a.comment_db_id = c.id AND a.is_adjudicated = 1
        WHERE v.run_id = ?
        GROUP BY v.id
        ORDER BY ch.channel_id, v.upload_index
        """,
        (run_id,),
        video_file,
    )

    export_query_to_csv(
        conn,
        """
        SELECT
            qr.run_id,
            qr.created_at,
            qr.payload_json
        FROM qa_reports qr
        WHERE qr.run_id = ?
        ORDER BY qr.created_at DESC
        """,
        (run_id,),
        qa_file,
    )

    return {
        "comments": comment_file,
        "videos": video_file,
        "qa": qa_file,
    }
