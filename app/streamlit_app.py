from __future__ import annotations

import csv
import html
import json
import re
import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from youtube_scraper.auto_analysis import (
    analyze_comment_text_features,
    append_comment_text_features,
    build_auto_analysis_frames,
)
from youtube_scraper.conformity_cascade import run_conformity_cascade
from youtube_scraper.config import load_config
from youtube_scraper.db import init_database, log_export
from youtube_scraper.pipeline import load_targets_csv, run_batch

st.set_page_config(page_title="YouTube Research Console", layout="wide")

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
SKEPTICISM_STRONG_REGEX = re.compile(
    r"(?:this is (?:so )?(?:fake|ai)|obvious(?:ly)? ai|100% ai|definitely ai|deepfake)",
    re.IGNORECASE,
)
PROOF_DEMAND_STRONG_REGEX = re.compile(
    r"(?:show (?:the )?(?:proof|source|bts)|where(?:'?s| is) (?:the )?(?:proof|source)|link (?:the )?source)",
    re.IGNORECASE,
)
NORMALIZATION_STRONG_REGEX = re.compile(
    r"(?:who cares if (?:its|it's) ai|nothing wrong with ai|everyone uses ai)",
    re.IGNORECASE,
)

DEFAULT_EXTRA_CODE_OPTIONS = [
    ("ai_usage_callout", "AI usage callout"),
    ("authenticity_challenge", "Authenticity challenge"),
    ("policy_or_ethics", "Policy / ethics"),
    ("humor_or_sarcasm", "Humor / sarcasm"),
    ("off_topic_or_noise", "Off-topic / noise"),
    ("possible_bot_behavior", "Possible bot behavior"),
]
REMEMBERED_LOGIN_PATH = Path("data/.remembered_login.json")
CODEBOOK_PATH = Path("data/annotation_codebook.json")
EVIDENCE_FREEZE_PATH = Path("data/evidence_base_freeze.json")
LABEL_SOURCE_OPTIONS = [
    ("rules", "Rules-based proxies"),
    ("my_annotations", "My annotations"),
    ("latest_annotation", "Latest saved annotation"),
    ("resolved_consensus", "Resolved consensus"),
    ("adjudicated", "Adjudicated only"),
]
DETERMINISTIC_LOGIC_REGISTRY = {
    "rules_version": "deterministic-rules-v1.1.0",
    "scoring_version": "assistive-scoring-v1.1.0",
    "preprocessing_profile": "clean_top20_v1",
    "preprocessing_rules_version": "preprocessing-v1.0.0",
    "signal_detection_rules_version": "signal-detection-v1.0.0",
    "triage_scoring_version": "triage-v1.0.0",
    "priority_scoring_version": "priority-v1.0.0",
}


@st.cache_resource
def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


@st.cache_data(ttl=20)
def run_df(_conn: sqlite3.Connection) -> pd.DataFrame:
    q = """
    SELECT
        id,
        started_at,
        ended_at,
        status,
        execution_mode,
        run_truncated,
        api_units_used,
        api_comment_count,
        playwright_comment_count,
        content_type,
        target_file,
        target_count_requested,
        study_profile_name,
        run_payload_json,
        spam_ruleset_version,
        rules_version,
        scoring_version,
        preprocessing_profile,
        compliance_reference
    FROM runs
    ORDER BY id DESC
    """
    return pd.read_sql_query(q, _conn)


def logic_registry() -> dict[str, str]:
    return dict(DETERMINISTIC_LOGIC_REGISTRY)


def _logic_summary_rows() -> list[dict[str, str]]:
    registry = logic_registry()
    return [
        {"component": "preprocessing_rules", "version": registry["preprocessing_rules_version"]},
        {"component": "signal_detection_rules", "version": registry["signal_detection_rules_version"]},
        {"component": "triage_scoring", "version": registry["triage_scoring_version"]},
        {"component": "priority_scoring", "version": registry["priority_scoring_version"]},
        {"component": "rules_version", "version": registry["rules_version"]},
        {"component": "scoring_version", "version": registry["scoring_version"]},
        {"component": "preprocessing_profile", "version": registry["preprocessing_profile"]},
    ]


def _parse_run_note_value(notes: object, key: str) -> str:
    text = _safe_text(notes)
    if not text:
        return ""
    parts = [p.strip() for p in text.split(";") if p.strip()]
    for part in parts:
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        if k.strip() == key:
            return v.strip()
    return ""


def _load_remembered_login() -> str:
    if not REMEMBERED_LOGIN_PATH.exists():
        return ""
    try:
        payload = json.loads(REMEMBERED_LOGIN_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""
    return _safe_text(payload.get("annotator_id")).strip()


def _save_remembered_login(annotator_id: str) -> None:
    REMEMBERED_LOGIN_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "annotator_id": _safe_text(annotator_id).strip(),
        "saved_at": datetime.now(tz=timezone.utc).isoformat(),
    }
    REMEMBERED_LOGIN_PATH.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def _clear_remembered_login() -> None:
    try:
        REMEMBERED_LOGIN_PATH.unlink(missing_ok=True)
    except OSError:
        pass


@st.cache_data(ttl=20)
def run_catalog_df(_conn: sqlite3.Connection) -> pd.DataFrame:
    q = """
    WITH video_stats AS (
        SELECT
            v.run_id,
            COUNT(*) AS videos,
            COUNT(DISTINCT v.channel_db_id) AS channels,
            SUM(CASE WHEN v.video_url LIKE '%/shorts/%' THEN 1 ELSE 0 END) AS shorts_videos,
            SUM(CASE WHEN v.video_url NOT LIKE '%/shorts/%' OR v.video_url IS NULL THEN 1 ELSE 0 END) AS long_videos,
            GROUP_CONCAT(DISTINCT ch.niche) AS niches
        FROM videos v
        JOIN channels ch ON ch.id = v.channel_db_id
        GROUP BY v.run_id
    ),
    comment_stats AS (
        SELECT
            c.run_id,
            COUNT(*) AS comments
        FROM comments c
        GROUP BY c.run_id
    )
    SELECT
        r.id,
        r.started_at,
        r.ended_at,
        r.status,
        r.execution_mode,
        r.run_truncated,
        r.notes,
        r.api_units_used,
        r.api_comment_count,
        r.playwright_comment_count,
        r.content_type,
        r.target_file,
        r.target_count_requested,
        r.study_profile_name,
        r.run_payload_json,
        r.rules_version,
        r.scoring_version,
        r.preprocessing_profile,
        COALESCE(vs.channels, 0) AS channels,
        COALESCE(vs.videos, 0) AS videos,
        COALESCE(cs.comments, 0) AS comments,
        COALESCE(vs.shorts_videos, 0) AS shorts_videos,
        COALESCE(vs.long_videos, 0) AS long_videos,
        COALESCE(vs.niches, '') AS niches
    FROM runs r
    LEFT JOIN video_stats vs ON vs.run_id = r.id
    LEFT JOIN comment_stats cs ON cs.run_id = r.id
    ORDER BY r.id DESC
    """
    df = pd.read_sql_query(q, _conn)
    if df.empty:
        return df
    df["content_type"] = (
        df["content_type"]
        .fillna("")
        .astype(str)
        .replace("", pd.NA)
        .fillna(df["notes"].apply(lambda x: _parse_run_note_value(x, "content_type") or "unknown"))
    )
    df["run_mode"] = (
        df["notes"]
        .fillna("")
        .astype(str)
        .apply(lambda t: (t.split(";", 1)[0].strip() if ";" in t else t.strip()) or "unknown")
    )
    # notes are stored as "live;content_type=videos" or "simulate;content_type=shorts"
    df["simulate_mode"] = df["notes"].astype(str).str.contains("simulate", case=False, na=False)
    return df


@st.cache_data(ttl=20)
def comments_df(_conn: sqlite3.Connection, run_id: int | None = None) -> pd.DataFrame:
    q = """
    SELECT
        c.id AS comment_db_id,
        c.run_id,
        ch.channel_id,
        ch.niche AS channel_niche,
        v.video_id,
        v.video_url,
        v.published_at AS video_publish_ts,
        c.comment_rank,
        c.language,
        c.like_count,
        c.reply_count,
        c.published_at AS comment_timestamp,
        c.cleaned_text,
        c.is_spam,
        c.is_template,
        c.is_duplicate,
        c.source_engine,
        c.extraction_ts
    FROM comments c
    JOIN channels ch ON c.channel_db_id = ch.id
    JOIN videos v ON c.video_db_id = v.id
    """
    params: tuple = ()
    if run_id is not None:
        q += " WHERE c.run_id = ?"
        params = (run_id,)
    q += " ORDER BY c.run_id DESC, ch.channel_id, c.comment_rank"
    return pd.read_sql_query(q, _conn, params=params)


@st.cache_data(ttl=20)
def videos_df(_conn: sqlite3.Connection, run_id: int | None = None) -> pd.DataFrame:
    q = """
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
        v.view_count,
        v.disclosure_quality
    FROM videos v
    JOIN channels ch ON v.channel_db_id = ch.id
    """
    params: tuple = ()
    if run_id is not None:
        q += " WHERE v.run_id = ?"
        params = (run_id,)
    q += " ORDER BY v.run_id DESC, ch.channel_id, v.upload_index"
    return pd.read_sql_query(q, _conn, params=params)


@st.cache_data(ttl=20)
def annotation_queue_df(
    _conn: sqlite3.Connection,
    annotator_id: str,
    run_id: int | None = None,
    comment_ids: tuple[int, ...] | None = None,
) -> pd.DataFrame:
    q = """
    SELECT
        c.id AS comment_db_id,
        c.run_id,
        ch.channel_id,
        ch.niche AS channel_niche,
        v.video_id,
        v.video_url,
        v.title,
        v.description,
        c.comment_rank,
        c.like_count,
        c.reply_count,
        c.cleaned_text,
        c.is_spam,
        c.is_template,
        c.is_duplicate,
        a.skepticism_fake_callout AS my_skepticism,
        a.proof_demand AS my_proof_demand,
        a.normalization_defense AS my_normalization_defense,
        a.extra_codes AS my_extra_codes,
        a.other_flag AS my_other_flag,
        a.other_text AS my_other_text,
        a.coded_at AS my_coded_at,
        a.was_disagreement_detected AS my_was_disagreement_detected,
        a.resolution_source AS my_resolution_source,
        a.adjudication_note AS my_adjudication_note,
        a.adjudicated_at AS my_adjudicated_at,
        a.pre_adjudication_skepticism AS my_pre_adjudication_skepticism,
        a.pre_adjudication_proof_demand AS my_pre_adjudication_proof_demand,
        a.pre_adjudication_normalization AS my_pre_adjudication_normalization,
        COALESCE(ac.n_coders, 0) AS coder_count,
        COALESCE(ac.has_adjudicated, 0) AS has_adjudicated,
        COALESCE(ac.skepticism_disagreement, 0) AS skepticism_disagreement,
        COALESCE(ac.proof_disagreement, 0) AS proof_disagreement,
        COALESCE(ac.normalization_disagreement, 0) AS normalization_disagreement,
        COALESCE(ac.other_disagreement, 0) AS other_disagreement,
        COALESCE(ac.extra_codes_disagreement, 0) AS extra_codes_disagreement,
        COALESCE(ac.any_disagreement, 0) AS any_disagreement,
        COALESCE(ac.label_summary, '') AS label_summary,
        COALESCE(ac.adjudicated_summary, '') AS adjudicated_summary
    FROM comments c
    JOIN videos v ON c.video_db_id = v.id
    JOIN channels ch ON c.channel_db_id = ch.id
    LEFT JOIN annotations a
        ON a.comment_db_id = c.id
       AND a.annotator_id = ?
    LEFT JOIN (
        SELECT
            comment_db_id,
            COUNT(DISTINCT annotator_id) AS n_coders,
            MAX(is_adjudicated) AS has_adjudicated,
            CASE
                WHEN COUNT(DISTINCT annotator_id) >= 2 AND MIN(skepticism_fake_callout) <> MAX(skepticism_fake_callout) THEN 1
                ELSE 0
            END AS skepticism_disagreement,
            CASE
                WHEN COUNT(DISTINCT annotator_id) >= 2 AND MIN(proof_demand) <> MAX(proof_demand) THEN 1
                ELSE 0
            END AS proof_disagreement,
            CASE
                WHEN COUNT(DISTINCT annotator_id) >= 2 AND MIN(normalization_defense) <> MAX(normalization_defense) THEN 1
                ELSE 0
            END AS normalization_disagreement,
            CASE
                WHEN COUNT(DISTINCT annotator_id) >= 2 AND MIN(COALESCE(other_flag, 0)) <> MAX(COALESCE(other_flag, 0)) THEN 1
                ELSE 0
            END AS other_disagreement,
            CASE
                WHEN COUNT(DISTINCT annotator_id) >= 2 AND MIN(COALESCE(extra_codes, '')) <> MAX(COALESCE(extra_codes, '')) THEN 1
                ELSE 0
            END AS extra_codes_disagreement,
            CASE
                WHEN COUNT(DISTINCT annotator_id) >= 2 AND (
                    MIN(skepticism_fake_callout) <> MAX(skepticism_fake_callout)
                    OR MIN(proof_demand) <> MAX(proof_demand)
                    OR MIN(normalization_defense) <> MAX(normalization_defense)
                    OR MIN(COALESCE(other_flag, 0)) <> MAX(COALESCE(other_flag, 0))
                    OR MIN(COALESCE(extra_codes, '')) <> MAX(COALESCE(extra_codes, ''))
                ) THEN 1
                ELSE 0
            END AS any_disagreement,
            GROUP_CONCAT(
                annotator_id || ': s=' || skepticism_fake_callout || ', p=' || proof_demand || ', n=' || normalization_defense
                || ', other=' || COALESCE(other_flag, 0) || ', extra=' || COALESCE(extra_codes, '[]'),
                ' | '
            ) AS label_summary,
            GROUP_CONCAT(
                CASE
                    WHEN is_adjudicated = 1 THEN annotator_id || ': s=' || skepticism_fake_callout || ', p=' || proof_demand || ', n=' || normalization_defense
                        || ', other=' || COALESCE(other_flag, 0) || ', extra=' || COALESCE(extra_codes, '[]')
                    ELSE NULL
                END,
                ' | '
            ) AS adjudicated_summary
        FROM annotations
        GROUP BY comment_db_id
    ) ac ON ac.comment_db_id = c.id
    """
    params: list[object] = [annotator_id]
    where_clauses: list[str] = []
    if run_id is not None:
        where_clauses.append("c.run_id = ?")
        params.append(run_id)
    if comment_ids:
        placeholders = ",".join(["?"] * len(comment_ids))
        where_clauses.append(f"c.id IN ({placeholders})")
        params.extend(comment_ids)
    if where_clauses:
        q += " WHERE " + " AND ".join(where_clauses)
    q += " ORDER BY c.id"
    return pd.read_sql_query(q, _conn, params=tuple(params))


@st.cache_data(ttl=20)
def run_video_status_df(_conn: sqlite3.Connection, run_id: int) -> pd.DataFrame:
    q = """
    SELECT
        comment_status,
        COUNT(*) AS videos
    FROM videos
    WHERE run_id = ?
    GROUP BY comment_status
    ORDER BY videos DESC
    """
    return pd.read_sql_query(q, _conn, params=(run_id,))


@st.cache_data(ttl=20)
def run_video_provenance_df(_conn: sqlite3.Connection, run_id: int) -> pd.DataFrame:
    q = """
    SELECT
        v.video_id,
        v.upload_index,
        ch.channel_id,
        ch.niche AS channel_niche,
        v.comment_status,
        COALESCE(v.collection_engine, 'unknown') AS collection_engine,
        COALESCE(v.comments_scanned, 0) AS comments_scanned,
        COALESCE(v.comments_saved, 0) AS comments_saved,
        COALESCE(v.comments_filtered, 0) AS comments_filtered,
        COALESCE(v.failure_reason, '') AS failure_reason,
        COALESCE(v.view_count, 0) AS view_count,
        v.title
    FROM videos v
    JOIN channels ch ON ch.id = v.channel_db_id
    WHERE v.run_id = ?
    ORDER BY v.upload_index, ch.channel_id, v.video_id
    """
    return pd.read_sql_query(q, _conn, params=(run_id,))


@st.cache_data(ttl=20)
def run_niche_summary_df(_conn: sqlite3.Connection, run_id: int) -> pd.DataFrame:
    q = """
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
    """
    return pd.read_sql_query(q, _conn, params=(run_id, run_id))


@st.cache_data(ttl=20)
def run_counts(_conn: sqlite3.Connection, run_id: int) -> dict[str, int]:
    row = _conn.execute(
        """
        SELECT
            (SELECT COUNT(DISTINCT channel_db_id) FROM videos WHERE run_id = ?) AS channels,
            (SELECT COUNT(*) FROM videos WHERE run_id = ?) AS videos,
            (SELECT COUNT(*) FROM comments WHERE run_id = ?) AS comments
        """,
        (run_id, run_id, run_id),
    ).fetchone()
    return {
        "channels": int(row["channels"] or 0),
        "videos": int(row["videos"] or 0),
        "comments": int(row["comments"] or 0),
    }


@st.cache_data(ttl=20)
def run_qa_payload(_conn: sqlite3.Connection, run_id: int) -> dict[str, object]:
    row = _conn.execute(
        """
        SELECT payload_json
        FROM qa_reports
        WHERE run_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return {}
    try:
        payload = json.loads(_safe_text(row["payload_json"]))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


@st.cache_data(ttl=20)
def run_annotation_progress(_conn: sqlite3.Connection, run_id: int) -> dict[str, int]:
    row = _conn.execute(
        """
        SELECT
            COUNT(*) AS annotation_rows,
            COUNT(DISTINCT a.comment_db_id) AS coded_comments,
            SUM(CASE WHEN COALESCE(a.is_adjudicated, 0) = 1 THEN 1 ELSE 0 END) AS adjudicated_rows,
            COUNT(DISTINCT CASE WHEN COALESCE(a.is_adjudicated, 0) = 1 THEN a.comment_db_id END) AS adjudicated_comments
        FROM annotations a
        JOIN comments c ON c.id = a.comment_db_id
        WHERE c.run_id = ?
        """,
        (run_id,),
    ).fetchone()
    if row is None:
        return {
            "annotation_rows": 0,
            "coded_comments": 0,
            "adjudicated_rows": 0,
            "adjudicated_comments": 0,
        }
    return {
        "annotation_rows": int(row["annotation_rows"] or 0),
        "coded_comments": int(row["coded_comments"] or 0),
        "adjudicated_rows": int(row["adjudicated_rows"] or 0),
        "adjudicated_comments": int(row["adjudicated_comments"] or 0),
    }


@st.cache_data(ttl=20)
def run_counts_multi(_conn: sqlite3.Connection, run_ids: tuple[int, ...]) -> dict[str, int]:
    if not run_ids:
        return {"channels": 0, "videos": 0, "comments": 0}
    placeholders = ",".join(["?"] * len(run_ids))
    row = _conn.execute(
        f"""
        SELECT
            (SELECT COUNT(DISTINCT channel_db_id) FROM videos WHERE run_id IN ({placeholders})) AS channels,
            (SELECT COUNT(*) FROM videos WHERE run_id IN ({placeholders})) AS videos,
            (SELECT COUNT(*) FROM comments WHERE run_id IN ({placeholders})) AS comments
        """,
        tuple(run_ids) + tuple(run_ids) + tuple(run_ids),
    ).fetchone()
    return {
        "channels": int(row["channels"] or 0),
        "videos": int(row["videos"] or 0),
        "comments": int(row["comments"] or 0),
    }


@st.cache_data(ttl=20)
def top_ranked_comments_df(_conn: sqlite3.Connection, run_id: int | None = None) -> pd.DataFrame:
    q = """
    SELECT
        c.run_id,
        v.video_id,
        c.id AS comment_db_id,
        c.comment_rank,
        c.like_count,
        c.reply_count,
        c.published_at AS comment_timestamp,
        c.cleaned_text
    FROM comments c
    JOIN videos v ON c.video_db_id = v.id
    WHERE c.comment_rank = 1
    """
    params: tuple[object, ...] = ()
    if run_id is not None:
        q += " AND c.run_id = ?"
        params = (run_id,)
    q += " ORDER BY c.run_id DESC, v.video_id"
    return pd.read_sql_query(q, _conn, params=params)


@st.cache_data(ttl=20)
def annotation_labels_df(
    _conn: sqlite3.Connection,
    run_id: int,
    label_source: str,
    annotator_id: str | None = None,
) -> pd.DataFrame:
    if label_source == "rules":
        return pd.DataFrame(
            columns=[
                "comment_db_id",
                "annotator_id",
                "is_adjudicated",
                "label_skepticism",
                "label_proof_demand",
                "label_normalization",
            ]
        )

    if label_source == "resolved_consensus":
        q = """
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
            WHERE c.run_id = ?
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
            WHERE c.run_id = ?
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
        return pd.read_sql_query(q, _conn, params=(int(run_id), int(run_id)))

    q = """
    WITH ranked AS (
        SELECT
            a.comment_db_id,
            a.annotator_id,
            a.is_adjudicated,
            a.skepticism_fake_callout AS label_skepticism,
            a.proof_demand AS label_proof_demand,
            a.normalization_defense AS label_normalization,
            ROW_NUMBER() OVER (
                PARTITION BY a.comment_db_id
                ORDER BY a.is_adjudicated DESC, a.coded_at DESC, a.id DESC
            ) AS rn
        FROM annotations a
        JOIN comments c ON c.id = a.comment_db_id
        WHERE c.run_id = ?
    """
    params: list[object] = [int(run_id)]
    if label_source == "my_annotations":
        q += " AND a.annotator_id = ?"
        params.append(_safe_text(annotator_id))
    elif label_source == "adjudicated":
        q += " AND a.is_adjudicated = 1"
    q += """
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
    ORDER BY comment_db_id
    """
    return pd.read_sql_query(q, _conn, params=tuple(params))


@st.cache_data(ttl=20)
def annotation_labels_runs_df(
    _conn: sqlite3.Connection,
    run_ids: tuple[int, ...],
    label_source: str,
    annotator_id: str | None = None,
) -> pd.DataFrame:
    if label_source == "rules" or not run_ids:
        return pd.DataFrame(
            columns=[
                "comment_db_id",
                "annotator_id",
                "is_adjudicated",
                "label_skepticism",
                "label_proof_demand",
                "label_normalization",
            ]
        )

    placeholders = ",".join(["?"] * len(run_ids))
    if label_source == "resolved_consensus":
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
        return pd.read_sql_query(q, _conn, params=params)

    q = f"""
    WITH ranked AS (
        SELECT
            a.comment_db_id,
            a.annotator_id,
            a.is_adjudicated,
            a.skepticism_fake_callout AS label_skepticism,
            a.proof_demand AS label_proof_demand,
            a.normalization_defense AS label_normalization,
            ROW_NUMBER() OVER (
                PARTITION BY a.comment_db_id
                ORDER BY a.is_adjudicated DESC, a.coded_at DESC, a.id DESC
            ) AS rn
        FROM annotations a
        JOIN comments c ON c.id = a.comment_db_id
        WHERE c.run_id IN ({placeholders})
    """
    params: list[object] = list(run_ids)
    if label_source == "my_annotations":
        q += " AND a.annotator_id = ?"
        params.append(_safe_text(annotator_id))
    elif label_source == "adjudicated":
        q += " AND a.is_adjudicated = 1"
    q += """
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
    ORDER BY comment_db_id
    """
    return pd.read_sql_query(q, _conn, params=tuple(params))


def _clear_cached_frames() -> None:
    run_df.clear()
    run_catalog_df.clear()
    run_qa_payload.clear()
    run_annotation_progress.clear()
    run_video_provenance_df.clear()
    comments_df.clear()
    videos_df.clear()
    run_video_status_df.clear()
    run_niche_summary_df.clear()
    run_counts.clear()
    run_counts_multi.clear()
    top_ranked_comments_df.clear()
    annotation_labels_df.clear()
    annotation_labels_runs_df.clear()
    load_annotation_subset_df.clear()
    load_codebook_config.clear()
    annotation_queue_df.clear()
    study_profiles_df.clear()
    evidence_freezes_df.clear()
    annotation_workflow_metrics.clear()
    conformity_frames.clear()
    conformity_frames_multi.clear()
    auto_analysis_frames.clear()


def _list_target_csv_files() -> list[str]:
    data_dir = Path("data")
    if not data_dir.exists():
        return []

    def _is_valid_target_csv(path: Path) -> bool:
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                fields = set(reader.fieldnames or [])
        except Exception:
            return False
        return {"channel_id", "channel_url", "channel_niche"}.issubset(fields) or {
            "channel_identifier",
            "channel_name",
            "niche",
        }.issubset(fields)

    files = sorted(
        [
            str(p)
            for p in data_dir.glob("*.csv")
            if p.is_file() and not p.name.startswith(".") and _is_valid_target_csv(p)
        ],
        key=lambda x: x.lower(),
    )
    return files


def _list_annotation_subset_files() -> list[str]:
    data_dir = Path("data")
    if not data_dir.exists():
        return []
    files = sorted(
        [
            str(p)
            for p in data_dir.glob("annotation_subset*.csv")
            if p.is_file() and not p.name.startswith(".")
        ],
        key=lambda x: x.lower(),
    )
    return files


def _quick_workflow_plan(conn: sqlite3.Connection, annotator_id: str) -> dict[str, object]:
    catalog = run_catalog_df(conn)
    freeze_library = evidence_freezes_df(conn, annotator_id)
    resolved_runs = set(resolved_consensus_run_ids(conn))
    if catalog.empty:
        return {
            "title": "Start with one small scrape run",
            "body": "No runs exist yet. The easiest first move is a tiny simulated scrape so we can verify the workflow without creating much noise.",
            "next_step": "Run a simulated batch with `data/targets_with_identifiers.csv`, `channel limit = 1`, and `videos per channel = 2`.",
            "after_that": "After it completes, inspect QA and then annotate one page.",
            "latest_run_id": None,
            "show_smoke_button": True,
        }

    latest = catalog.iloc[0]
    latest_run_id = int(latest["id"])
    latest_comments = int(latest["comments"] or 0)
    latest_videos = int(latest["videos"] or 0)
    latest_status = _safe_text(latest["status"]) or "unknown"
    progress = run_annotation_progress(conn, latest_run_id)

    if latest_status != "completed":
        return {
            "title": f"Check the latest run first",
            "body": f"Run {latest_run_id} is not marked completed yet. Before doing anything else, inspect its status and QA details.",
            "next_step": f"Open `Inspect run` for run {latest_run_id}.",
            "after_that": "If it failed or collected too little, rerun a tiny simulated batch.",
            "latest_run_id": latest_run_id,
            "show_smoke_button": True,
        }

    if latest_comments < 20:
        return {
            "title": f"Treat run {latest_run_id} as a smoke test",
            "body": f"It completed, but it only saved {latest_comments} comments across {latest_videos} videos. That is enough to verify the plumbing, not enough for meaningful coding or freezing.",
            "next_step": f"Inspect run {latest_run_id} to confirm the QA/provenance tables look sane, then launch one cleaner simulated run.",
            "after_that": "Use `data/targets_with_identifiers.csv`, `simulate = on`, `content type = videos`, `channel limit = 1`, `videos per channel = 2`, `min expected = 2`.",
            "latest_run_id": latest_run_id,
            "show_smoke_button": True,
        }

    if progress["coded_comments"] == 0:
        return {
            "title": f"Start coding run {latest_run_id}",
            "body": f"Run {latest_run_id} collected {latest_comments} comments and is ready for the next human step, but nothing from it has been coded yet.",
            "next_step": f"Go to the Annotation tab and save one page from run {latest_run_id}.",
            "after_that": "Come back here and check the Workflow metrics panel.",
            "latest_run_id": latest_run_id,
            "show_smoke_button": False,
        }

    if latest_run_id not in resolved_runs:
        return {
            "title": f"Finish the validation pass for run {latest_run_id}",
            "body": f"Run {latest_run_id} has coded comments, but it is not in the resolved-consensus evidence base yet.",
            "next_step": "Double-code or adjudicate the run until the disagreement state is resolved.",
            "after_that": "Then include it in a named evidence freeze.",
            "latest_run_id": latest_run_id,
            "show_smoke_button": False,
        }

    if freeze_library.empty:
        return {
            "title": "Save the first named freeze",
            "body": "You have resolved-consensus material but no saved DB freeze yet, so the next useful checkpoint is to lock the evidence base.",
            "next_step": "Use the Evidence Freeze section to save a named freeze.",
            "after_that": "Then build the final analysis pack from that frozen scope.",
            "latest_run_id": latest_run_id,
            "show_smoke_button": False,
        }

    return {
        "title": "You are in analysis/export mode",
        "body": "The basics are in place: recent runs exist, coding has progressed, and you already have at least one saved freeze.",
        "next_step": "Either extend coding on the latest useful run or build the final analysis/export pack from your frozen scope.",
        "after_that": "For the paper, prioritize the frozen evidence and final pack outputs over more exploratory scraping.",
        "latest_run_id": latest_run_id,
        "show_smoke_button": False,
    }


def _launch_safe_smoke_run(conn: sqlite3.Connection, config, target_files: list[str]) -> int:
    preferred_target = "data/targets_with_identifiers.csv"
    target_file = preferred_target if preferred_target in target_files else (target_files[0] if target_files else "")
    if not target_file:
        raise ValueError("No valid target CSV files are available for a smoke test.")
    targets = load_targets_csv(Path(target_file))[:1]
    if not targets:
        raise ValueError(f"No targets loaded from `{target_file}`.")
    run_payload = {
        "scrape": {
            "targets_csv": target_file,
            "execution_mode": "auto",
            "content_type": "videos",
            "channel_limit": 1,
            "videos_per_channel": 2,
            "min_expected_videos_per_channel": 2,
            "template_threshold": 0.90,
            "simulate": True,
            "study_profile_name": "",
        },
        "dataset_filters": {
            "niches": [],
            "include_shorts": False,
            "include_spam": False,
            "include_template": False,
            "include_duplicate": False,
            "comment_rank_min": 1,
            "comment_rank_max": 20,
            "min_comments_per_video": 0,
        },
        "run_meta": {
            "target_count_requested": len(targets),
            "target_file": target_file,
            "study_profile_name": "",
        },
    }
    run_cfg = replace(config, execution_mode="auto")
    return run_batch(
        conn,
        run_cfg,
        targets,
        template_threshold=0.90,
        simulate=True,
        videos_per_channel=2,
        min_expected_videos_per_channel=2,
        content_type="videos",
        target_file=target_file,
        study_profile_name=None,
        run_payload=run_payload,
    )


@st.cache_data(ttl=20)
def load_annotation_subset_df(path: str) -> pd.DataFrame:
    subset = pd.read_csv(path)
    if "comment_db_id" not in subset.columns:
        raise ValueError(f"Subset file {path} must contain a comment_db_id column.")
    subset["comment_db_id"] = pd.to_numeric(subset["comment_db_id"], errors="coerce").astype("Int64")
    subset = subset.dropna(subset=["comment_db_id"]).copy()
    subset["comment_db_id"] = subset["comment_db_id"].astype(int)
    return subset


def _slugify_code_id(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", _safe_text(text).strip().lower()).strip("_")
    return slug[:40] or "custom_code"


@st.cache_data(ttl=20)
def load_codebook_config(path: str) -> dict[str, object]:
    codebook_path = Path(path)
    if not codebook_path.exists():
        return {"extra_codes": []}
    try:
        payload = json.loads(codebook_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"extra_codes": []}
    extra_codes = payload.get("extra_codes")
    if not isinstance(extra_codes, list):
        extra_codes = []
    cleaned: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in extra_codes:
        if not isinstance(item, dict):
            continue
        code = _slugify_code_id(_safe_text(item.get("code")))
        label = _safe_text(item.get("label")).strip()
        if not code or not label or code in seen:
            continue
        cleaned.append({"code": code, "label": label})
        seen.add(code)
    return {"extra_codes": cleaned}


def save_codebook_config(path: str, payload: dict[str, object]) -> None:
    codebook_path = Path(path)
    codebook_path.parent.mkdir(parents=True, exist_ok=True)
    codebook_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


def extra_code_options() -> list[tuple[str, str]]:
    payload = load_codebook_config(str(CODEBOOK_PATH))
    custom_codes = payload.get("extra_codes", [])
    custom_options: list[tuple[str, str]] = []
    for item in custom_codes:
        if isinstance(item, dict):
            custom_options.append((_safe_text(item.get("code")), _safe_text(item.get("label"))))
    return DEFAULT_EXTRA_CODE_OPTIONS + custom_options


def _extra_code_ids(options: list[tuple[str, str]]) -> list[str]:
    return [code for code, _label in options]


def annotation_stats(conn: sqlite3.Connection) -> dict[str, int]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS annotations,
            COUNT(DISTINCT comment_db_id) AS coded_comments,
            COUNT(DISTINCT annotator_id) AS annotators
        FROM annotations
        """
    ).fetchone()
    return {
        "annotations": int(row["annotations"] or 0),
        "coded_comments": int(row["coded_comments"] or 0),
        "annotators": int(row["annotators"] or 0),
    }


def build_reproducibility_bundle(conn: sqlite3.Connection, annotator_id: str) -> dict[str, object]:
    runlab_payload = _current_runlab_payload()
    codebook = load_codebook_config(str(CODEBOOK_PATH))
    legacy_evidence_freeze = load_evidence_freeze(str(EVIDENCE_FREEZE_PATH))
    freeze_library = evidence_freezes_df(conn, annotator_id)
    latest_saved_freeze = (
        _evidence_freeze_payload_from_row(freeze_library.iloc[0])
        if not freeze_library.empty
        else {}
    )
    stats = annotation_stats(conn)
    latest_runs = run_catalog_df(conn)
    latest_run_snapshot = latest_runs.head(10).to_dict(orient="records") if not latest_runs.empty else []
    db_row = conn.execute("PRAGMA database_list").fetchone()
    database_path = _safe_text(db_row["file"]) if db_row else ""
    session_keys = [
        "cascade_run_id",
        "cascade_label_source",
        "pilot_analysis_run_id",
        "pilot_label_source",
        "combined_hypothesis_runs",
        "combined_hypothesis_label_source",
        "annot_run_id",
        "annotation_workflow_mode",
        "annotation_subset_file",
        "annotation_priority_mode",
        "annotation_triage_mode",
        "annotation_ai_focus_mode",
        "annotation_diversity_video_cap",
        "annotation_diversity_channel_cap",
    ]
    session_snapshot = {key: st.session_state.get(key) for key in session_keys if key in st.session_state}
    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "annotator_id": annotator_id,
        "database_path": database_path,
        "runlab_payload": runlab_payload,
        "codebook": codebook,
        "evidence_freeze": latest_saved_freeze or legacy_evidence_freeze,
        "legacy_evidence_freeze": legacy_evidence_freeze,
        "saved_evidence_freezes": (
            freeze_library[
                [
                    "id",
                    "freeze_uuid",
                    "name",
                    "created_at",
                    "notes",
                    "rules_version",
                    "scoring_version",
                    "preprocessing_profile",
                ]
            ].to_dict(orient="records")
            if not freeze_library.empty
            else []
        ),
        "annotation_stats": stats,
        "session_snapshot": session_snapshot,
        "latest_runs": latest_run_snapshot,
    }


def load_evidence_freeze(path: str) -> dict[str, object]:
    freeze_path = Path(path)
    if not freeze_path.exists():
        return {}
    try:
        payload = json.loads(freeze_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def save_evidence_freeze(path: str, payload: dict[str, object]) -> None:
    freeze_path = Path(path)
    freeze_path.parent.mkdir(parents=True, exist_ok=True)
    freeze_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")


@st.cache_data(ttl=20)
def evidence_freezes_df(_conn: sqlite3.Connection, created_by: str) -> pd.DataFrame:
    q = """
    SELECT
        id,
        freeze_uuid,
        name,
        created_by,
        created_at,
        notes,
        rules_version,
        scoring_version,
        preprocessing_profile,
        run_ids_json,
        summary_json,
        prevalence_overall_json,
        prevalence_by_run_niche_json
    FROM evidence_freezes
    WHERE created_by = ?
    ORDER BY created_at DESC, id DESC
    """
    return pd.read_sql_query(q, _conn, params=(created_by,))


def upsert_evidence_freeze(
    conn: sqlite3.Connection,
    *,
    created_by: str,
    name: str,
    notes: str,
    payload: dict[str, object],
) -> int:
    now = datetime.now(tz=timezone.utc).isoformat()
    freeze_uuid = _safe_text(payload.get("freeze_uuid")) or f"freeze-{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    conn.execute(
        """
        INSERT INTO evidence_freezes (
            freeze_uuid, name, created_by, created_at, notes, rules_version, scoring_version, preprocessing_profile,
            run_ids_json, summary_json, prevalence_overall_json, prevalence_by_run_niche_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(created_by, name)
        DO UPDATE SET
            freeze_uuid = excluded.freeze_uuid,
            created_at = excluded.created_at,
            notes = excluded.notes,
            rules_version = excluded.rules_version,
            scoring_version = excluded.scoring_version,
            preprocessing_profile = excluded.preprocessing_profile,
            run_ids_json = excluded.run_ids_json,
            summary_json = excluded.summary_json,
            prevalence_overall_json = excluded.prevalence_overall_json,
            prevalence_by_run_niche_json = excluded.prevalence_by_run_niche_json
        """,
        (
            freeze_uuid,
            name.strip(),
            created_by,
            now,
            notes.strip(),
            _safe_text(payload.get("rules_version")),
            _safe_text(payload.get("scoring_version")),
            _safe_text(payload.get("preprocessing_profile")),
            json.dumps(payload.get("run_ids", []), ensure_ascii=True),
            json.dumps(payload.get("snapshot_summary", {}), ensure_ascii=True),
            json.dumps(payload.get("prevalence_overall", []), ensure_ascii=True),
            json.dumps(payload.get("prevalence_by_run_niche", []), ensure_ascii=True),
        ),
    )
    row = conn.execute(
        "SELECT id FROM evidence_freezes WHERE created_by = ? AND name = ?",
        (created_by, name.strip()),
    ).fetchone()
    conn.commit()
    return int(row["id"]) if row else 0


@st.cache_data(ttl=20)
def export_records_df(_conn: sqlite3.Connection, *, freeze_id: int | None = None) -> pd.DataFrame:
    q = """
    SELECT
        e.id,
        e.exported_at,
        e.export_type,
        e.file_path,
        e.row_count,
        e.run_id,
        e.freeze_id,
        e.rules_version,
        e.scoring_version,
        e.preprocessing_profile
    FROM exports e
    """
    params: tuple[object, ...] = ()
    if freeze_id is not None:
        q += " WHERE e.freeze_id = ?"
        params = (int(freeze_id),)
    q += " ORDER BY e.exported_at DESC, e.id DESC"
    return pd.read_sql_query(q, _conn, params=params)


def delete_evidence_freeze(conn: sqlite3.Connection, *, created_by: str, freeze_id: int) -> None:
    conn.execute("DELETE FROM evidence_freezes WHERE id = ? AND created_by = ?", (int(freeze_id), created_by))
    conn.commit()


def _evidence_freeze_payload_from_row(row: pd.Series | sqlite3.Row | dict[str, object]) -> dict[str, object]:
    def _row_get(key: str, default: object = None) -> object:
        if isinstance(row, dict):
            return row.get(key, default)
        if isinstance(row, pd.Series):
            return row.get(key, default)
        try:
            return row[key]  # type: ignore[index]
        except (KeyError, IndexError, TypeError):
            return default

    def _decode_json(value: object, default: object) -> object:
        try:
            decoded = json.loads(_safe_text(value))
        except json.JSONDecodeError:
            return default
        return decoded if decoded is not None else default

    return {
        "id": int(_row_get("id", 0) or 0),
        "freeze_uuid": _safe_text(_row_get("freeze_uuid")),
        "name": _safe_text(_row_get("name")),
        "created_by": _safe_text(_row_get("created_by")),
        "created_at": _safe_text(_row_get("created_at")),
        "notes": _safe_text(_row_get("notes")),
        "rules_version": _safe_text(_row_get("rules_version")),
        "scoring_version": _safe_text(_row_get("scoring_version")),
        "preprocessing_profile": _safe_text(_row_get("preprocessing_profile")),
        "run_ids": _decode_json(_row_get("run_ids_json"), []),
        "snapshot_summary": _decode_json(_row_get("summary_json"), {}),
        "prevalence_overall": _decode_json(_row_get("prevalence_overall_json"), []),
        "prevalence_by_run_niche": _decode_json(_row_get("prevalence_by_run_niche_json"), []),
    }


def compare_freeze_snapshots(
    current_summary: dict[str, object],
    saved_summary: dict[str, object],
    *,
    current_runs: tuple[int, ...],
    saved_runs: list[int] | tuple[int, ...],
) -> pd.DataFrame:
    saved_run_set = {int(x) for x in saved_runs}
    current_run_set = {int(x) for x in current_runs}
    rows: list[dict[str, object]] = [
        {
            "metric": "run_set",
            "saved": ", ".join(str(x) for x in sorted(saved_run_set)) or "n/a",
            "current": ", ".join(str(x) for x in sorted(current_run_set)) or "n/a",
            "delta": (
                f"added {sorted(current_run_set - saved_run_set)}; removed {sorted(saved_run_set - current_run_set)}"
                if current_run_set != saved_run_set
                else "same"
            ),
        }
    ]
    numeric_metrics = [
        "resolved_comments",
        "double_coded_comments",
        "unresolved_disagreements",
        "any_core_positive",
        "skepticism_positive",
        "proof_positive",
        "normalization_positive",
    ]
    for metric in numeric_metrics:
        saved_value = int(saved_summary.get(metric, 0) or 0)
        current_value = int(current_summary.get(metric, 0) or 0)
        rows.append(
            {
                "metric": metric,
                "saved": saved_value,
                "current": current_value,
                "delta": current_value - saved_value,
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=20)
def resolved_consensus_run_ids(_conn: sqlite3.Connection) -> tuple[int, ...]:
    q = """
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
        GROUP BY a.comment_db_id
    )
    SELECT DISTINCT c.run_id
    FROM per_comment pc
    JOIN comments c ON c.id = pc.comment_db_id
    WHERE pc.coder_count >= 2
      AND (
          pc.has_adjudicated = 1
          OR (
              pc.min_skepticism = pc.max_skepticism
              AND pc.min_proof_demand = pc.max_proof_demand
              AND pc.min_normalization = pc.max_normalization
          )
      )
    ORDER BY c.run_id
    """
    df = pd.read_sql_query(q, _conn)
    if df.empty:
        return tuple()
    return tuple(int(x) for x in df["run_id"].tolist())


@st.cache_data(ttl=20)
def evidence_base_snapshot(_conn: sqlite3.Connection, run_ids: tuple[int, ...]) -> dict[str, object]:
    if not run_ids:
        return {
            "summary": {},
            "prevalence_overall": pd.DataFrame(),
            "prevalence_by_run_niche": pd.DataFrame(),
            "resolved_comments": pd.DataFrame(),
        }

    comments = comments_df(_conn)
    comments = comments[comments["run_id"].isin(list(run_ids))].copy()
    prepared, _label_meta = _apply_label_source_runs(
        comments,
        run_ids=run_ids,
        label_source="resolved_consensus",
        annotator_id=None,
        conn=_conn,
    )
    resolved = prepared[prepared["analysis_skepticism"].notna()].copy()
    if resolved.empty:
        return {
            "summary": {},
            "prevalence_overall": pd.DataFrame(),
            "prevalence_by_run_niche": pd.DataFrame(),
            "resolved_comments": resolved,
        }

    resolved["analysis_skepticism"] = pd.to_numeric(resolved["analysis_skepticism"], errors="coerce").fillna(0).astype(int)
    resolved["analysis_proof_demand"] = pd.to_numeric(resolved["analysis_proof_demand"], errors="coerce").fillna(0).astype(int)
    resolved["analysis_normalization"] = pd.to_numeric(resolved["analysis_normalization"], errors="coerce").fillna(0).astype(int)
    resolved["any_core_positive"] = (
        (resolved["analysis_skepticism"] == 1)
        | (resolved["analysis_proof_demand"] == 1)
        | (resolved["analysis_normalization"] == 1)
    ).astype(int)

    placeholders = ",".join(["?"] * len(run_ids))
    disagreement_row = _conn.execute(
        f"""
        WITH per_comment AS (
            SELECT
                a.comment_db_id,
                COUNT(DISTINCT a.annotator_id) AS coder_count,
                MAX(a.is_adjudicated) AS has_adjudicated
            FROM annotations a
            JOIN comments c ON c.id = a.comment_db_id
            WHERE c.run_id IN ({placeholders})
            GROUP BY a.comment_db_id
        ),
        disagreements AS (
            SELECT
                a.comment_db_id,
                CASE
                    WHEN COUNT(DISTINCT a.annotator_id) >= 2 AND (
                        MIN(COALESCE(a.skepticism_fake_callout, 0)) <> MAX(COALESCE(a.skepticism_fake_callout, 0))
                        OR MIN(COALESCE(a.proof_demand, 0)) <> MAX(COALESCE(a.proof_demand, 0))
                        OR MIN(COALESCE(a.normalization_defense, 0)) <> MAX(COALESCE(a.normalization_defense, 0))
                        OR MIN(COALESCE(a.other_flag, 0)) <> MAX(COALESCE(a.other_flag, 0))
                        OR MIN(COALESCE(a.extra_codes, '')) <> MAX(COALESCE(a.extra_codes, ''))
                    ) THEN 1
                    ELSE 0
                END AS any_disagreement
            FROM annotations a
            JOIN comments c ON c.id = a.comment_db_id
            WHERE c.run_id IN ({placeholders})
            GROUP BY a.comment_db_id
        )
        SELECT
            COUNT(*) AS double_coded_comments,
            SUM(COALESCE(d.any_disagreement, 0)) AS disagreement_comments,
            SUM(CASE WHEN COALESCE(d.any_disagreement, 0) = 1 AND p.has_adjudicated = 0 THEN 1 ELSE 0 END) AS unresolved_disagreements
        FROM per_comment p
        LEFT JOIN disagreements d ON d.comment_db_id = p.comment_db_id
        WHERE p.coder_count >= 2
        """,
        tuple(run_ids) + tuple(run_ids),
    ).fetchone()

    summary = {
        "runs": list(run_ids),
        "resolved_comments": int(len(resolved)),
        "double_coded_comments": int(disagreement_row["double_coded_comments"] or 0) if disagreement_row else 0,
        "disagreement_comments": int(disagreement_row["disagreement_comments"] or 0) if disagreement_row else 0,
        "unresolved_disagreements": int(disagreement_row["unresolved_disagreements"] or 0) if disagreement_row else 0,
        "any_core_positive": int(resolved["any_core_positive"].sum()),
        "skepticism_positive": int(resolved["analysis_skepticism"].sum()),
        "proof_positive": int(resolved["analysis_proof_demand"].sum()),
        "normalization_positive": int(resolved["analysis_normalization"].sum()),
        "channels": int(resolved["channel_id"].nunique()),
        "videos": int(resolved["video_id"].nunique()),
    }

    prevalence_overall = pd.DataFrame(
        [
            {"metric": "resolved_comments", "value": summary["resolved_comments"]},
            {"metric": "any_core_positive", "value": summary["any_core_positive"]},
            {"metric": "skepticism_positive", "value": summary["skepticism_positive"]},
            {"metric": "proof_positive", "value": summary["proof_positive"]},
            {"metric": "normalization_positive", "value": summary["normalization_positive"]},
            {
                "metric": "any_core_positive_rate",
                "value": summary["any_core_positive"] / summary["resolved_comments"] if summary["resolved_comments"] else 0,
            },
            {
                "metric": "skepticism_rate",
                "value": summary["skepticism_positive"] / summary["resolved_comments"] if summary["resolved_comments"] else 0,
            },
            {
                "metric": "proof_rate",
                "value": summary["proof_positive"] / summary["resolved_comments"] if summary["resolved_comments"] else 0,
            },
            {
                "metric": "normalization_rate",
                "value": summary["normalization_positive"] / summary["resolved_comments"] if summary["resolved_comments"] else 0,
            },
        ]
    )

    prevalence_by_run_niche = (
        resolved.groupby(["run_id", "channel_niche"], as_index=False)
        .agg(
            resolved_comments=("comment_db_id", "count"),
            any_core_positive=("any_core_positive", "sum"),
            skepticism_positive=("analysis_skepticism", "sum"),
            proof_positive=("analysis_proof_demand", "sum"),
            normalization_positive=("analysis_normalization", "sum"),
        )
        .sort_values(["run_id", "channel_niche"])
    )

    return {
        "summary": summary,
        "prevalence_overall": prevalence_overall,
        "prevalence_by_run_niche": prevalence_by_run_niche,
        "resolved_comments": resolved,
    }


@st.cache_data(ttl=20)
def corpus_overview_snapshot(_conn: sqlite3.Connection) -> dict[str, int]:
    row = _conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM runs) AS runs,
            (SELECT COUNT(*) FROM channels) AS channels,
            (SELECT COUNT(*) FROM videos) AS videos,
            (SELECT COUNT(*) FROM comments) AS comments,
            (SELECT COUNT(*) FROM annotations) AS annotations
        """
    ).fetchone()
    return {
        "runs": int(row["runs"] or 0),
        "channels": int(row["channels"] or 0),
        "videos": int(row["videos"] or 0),
        "comments": int(row["comments"] or 0),
        "annotations": int(row["annotations"] or 0),
    }


@st.cache_data(ttl=20)
def screened_corpus_count(_conn: sqlite3.Connection) -> int:
    row = _conn.execute(
        """
        SELECT COUNT(*) AS screened_comments
        FROM comments
        WHERE COALESCE(is_spam, 0) = 0
          AND COALESCE(is_template, 0) = 0
          AND COALESCE(is_duplicate, 0) = 0
        """
    ).fetchone()
    return int(row["screened_comments"] or 0)


@st.cache_data(ttl=20)
def labeled_comment_summary(_conn: sqlite3.Connection, run_ids: tuple[int, ...]) -> dict[str, int]:
    if not run_ids:
        return {
            "labeled_comments": 0,
            "double_coded_comments": 0,
            "disagreement_comments": 0,
            "adjudicated_comments": 0,
            "resolved_comments": 0,
        }
    placeholders = ",".join(["?"] * len(run_ids))
    row = _conn.execute(
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
            SUM(CASE WHEN has_adjudicated = 1 THEN 1 ELSE 0 END) AS adjudicated_comments,
            SUM(
                CASE
                    WHEN coder_count >= 2 AND (
                        has_adjudicated = 1
                        OR (
                            min_s = max_s
                            AND min_p = max_p
                            AND min_n = max_n
                            AND min_o = max_o
                            AND min_e = max_e
                        )
                    ) THEN 1
                    ELSE 0
                END
            ) AS resolved_comments
        FROM base
        """,
        tuple(run_ids),
    ).fetchone()
    return {
        "labeled_comments": int(row["labeled_comments"] or 0),
        "double_coded_comments": int(row["double_coded_comments"] or 0),
        "disagreement_comments": int(row["disagreement_comments"] or 0),
        "adjudicated_comments": int(row["adjudicated_comments"] or 0),
        "resolved_comments": int(row["resolved_comments"] or 0),
    }


def validation_summary_table(
    freeze_snapshot: dict[str, object],
    *,
    freeze_date: str,
    freeze_name: str,
    run_ids: tuple[int, ...],
    freeze_id: int | None = None,
    freeze_uuid: str = "",
    rules_version: str = "",
    scoring_version: str = "",
    preprocessing_profile: str = "",
) -> pd.DataFrame:
    summary = freeze_snapshot.get("summary", {}) if isinstance(freeze_snapshot, dict) else {}
    registry = logic_registry()
    return pd.DataFrame(
        [
            {"metric": "freeze_id", "value": int(freeze_id or 0) if freeze_id else "unsaved"},
            {"metric": "freeze_uuid", "value": freeze_uuid or "unsaved_current_selection"},
            {"metric": "freeze_name", "value": freeze_name or "unsaved_current_selection"},
            {"metric": "freeze_timestamp", "value": freeze_date or "current_session"},
            {"metric": "run_ids_included", "value": ", ".join(str(x) for x in run_ids)},
            {"metric": "rules_version", "value": rules_version or registry["rules_version"]},
            {"metric": "scoring_version", "value": scoring_version or registry["scoring_version"]},
            {"metric": "preprocessing_profile", "value": preprocessing_profile or registry["preprocessing_profile"]},
            {"metric": "preprocessing_rules_version", "value": registry["preprocessing_rules_version"]},
            {"metric": "signal_detection_rules_version", "value": registry["signal_detection_rules_version"]},
            {"metric": "triage_scoring_version", "value": registry["triage_scoring_version"]},
            {"metric": "priority_scoring_version", "value": registry["priority_scoring_version"]},
            {"metric": "resolved_comments", "value": int(summary.get("resolved_comments", 0) or 0)},
            {"metric": "double_coded_comments", "value": int(summary.get("double_coded_comments", 0) or 0)},
            {"metric": "disagreement_comments", "value": int(summary.get("disagreement_comments", 0) or 0)},
            {"metric": "unresolved_disagreements", "value": int(summary.get("unresolved_disagreements", 0) or 0)},
            {"metric": "any_core_positive", "value": int(summary.get("any_core_positive", 0) or 0)},
            {"metric": "skepticism_positive", "value": int(summary.get("skepticism_positive", 0) or 0)},
            {"metric": "proof_positive", "value": int(summary.get("proof_positive", 0) or 0)},
            {"metric": "normalization_positive", "value": int(summary.get("normalization_positive", 0) or 0)},
            {"metric": "resolved_definition", "value": "double-coded and either agreed or adjudicated"},
        ]
    )


def workflow_overview_table(
    corpus_summary: dict[str, int],
    labeled_summary: dict[str, int],
    freeze_snapshot: dict[str, object],
    *,
    screened_comments: int,
    freeze_count: int,
    latest_freeze_name: str,
    latest_freeze_date: str,
) -> pd.DataFrame:
    freeze_summary = freeze_snapshot.get("summary", {}) if isinstance(freeze_snapshot, dict) else {}
    raw_comments = int(corpus_summary.get("comments", 0) or 0)
    coded_comments = int(labeled_summary.get("labeled_comments", 0) or 0)
    adjudicated_comments = int(labeled_summary.get("adjudicated_comments", 0) or 0)
    resolved = int(freeze_summary.get("resolved_comments", 0) or 0)
    disagreement = int(labeled_summary.get("disagreement_comments", 0) or 0)
    unresolved = int(freeze_summary.get("unresolved_disagreements", 0) or 0)
    exploratory_extension = max(0, int(screened_comments) - resolved)
    return pd.DataFrame(
        [
            {
                "stage": "Raw corpus",
                "status": f"{raw_comments} comments across {int(corpus_summary.get('runs', 0) or 0)} runs",
                "current_artifact": "collection layer",
            },
            {
                "stage": "Screened corpus",
                "status": f"{int(screened_comments)} comments after spam/template/duplicate filters",
                "current_artifact": f"preprocessing {logic_registry()['preprocessing_profile']}",
            },
            {
                "stage": "Coded corpus",
                "status": f"{coded_comments} human-coded comments",
                "current_artifact": f"disagreements detected: {disagreement}",
            },
            {
                "stage": "Adjudicated / resolved corpus",
                "status": f"{adjudicated_comments} adjudicated; {resolved} resolved",
                "current_artifact": f"unresolved disagreements: {unresolved}",
            },
            {
                "stage": "Frozen validated evidence",
                "status": f"{resolved} resolved comments / {freeze_count} saved freezes",
                "current_artifact": latest_freeze_name or "current unsaved selection",
            },
            {
                "stage": "Exploratory extension",
                "status": f"{exploratory_extension} screened comments outside frozen resolved layer",
                "current_artifact": latest_freeze_date or "not tied to paper-facing claims",
            },
        ]
    )


def _record_export_event(
    conn: sqlite3.Connection,
    *,
    export_type: str,
    file_path: str,
    row_count: int,
    freeze_id: int | None = None,
    run_id: int | None = None,
) -> None:
    registry = logic_registry()
    log_export(
        conn,
        export_type=export_type,
        file_path=file_path,
        row_count=row_count,
        freeze_id=freeze_id,
        run_id=run_id,
        rules_version=registry["rules_version"],
        scoring_version=registry["scoring_version"],
        preprocessing_profile=registry["preprocessing_profile"],
    )
    export_records_df.clear()


def systems_summary_table(
    corpus_summary: dict[str, int],
    labeled_summary: dict[str, int],
    freeze_snapshot: dict[str, object],
) -> pd.DataFrame:
    freeze_summary = freeze_snapshot.get("summary", {}) if isinstance(freeze_snapshot, dict) else {}
    broader_comments = int(corpus_summary.get("comments", 0) or 0)
    labeled_comments = int(labeled_summary.get("labeled_comments", 0) or 0)
    resolved_comments = int(freeze_summary.get("resolved_comments", 0) or 0)
    exploratory_remainder = max(0, broader_comments - resolved_comments)
    return pd.DataFrame(
        [
            {
                "layer": "Broader collected corpus",
                "size_or_status": broader_comments,
                "human_vs_assistive_role": "collection plus assistive diagnostics",
                "analytical_use": "context only",
            },
            {
                "layer": "Labeled comments in frozen runs",
                "size_or_status": labeled_comments,
                "human_vs_assistive_role": "human coding with assistive context",
                "analytical_use": "candidate evidence layer",
            },
            {
                "layer": "Frozen resolved evidence",
                "size_or_status": resolved_comments,
                "human_vs_assistive_role": "human validated",
                "analytical_use": "main confirmatory analysis",
            },
            {
                "layer": "Disagreement cases",
                "size_or_status": int(labeled_summary.get("disagreement_comments", 0) or 0),
                "human_vs_assistive_role": "human adjudication",
                "analytical_use": "quality control",
            },
            {
                "layer": "Unresolved disagreements at freeze",
                "size_or_status": int(freeze_summary.get("unresolved_disagreements", 0) or 0),
                "human_vs_assistive_role": "n/a",
                "analytical_use": "frozen state",
            },
            {
                "layer": "Exploratory remainder",
                "size_or_status": exploratory_remainder,
                "human_vs_assistive_role": "assistive screening only",
                "analytical_use": "contextual mapping and future follow-up",
            },
        ]
    )


def workflow_boundary_figure_spec() -> str:
    return "\n".join(
        [
            "Raw corpus",
            "  -> Screened corpus",
            "  -> Coded corpus",
            "  -> Adjudicated / resolved corpus",
            "  -> Frozen validated evidence",
            "  -> Exploratory extension",
            "",
            "Figure note:",
            "Validated claims rely only on the frozen resolved layer.",
            "Automation supports screening, prioritization, and exploratory mapping, but does not expand the confirmatory evidence base.",
        ]
    )


@st.cache_data(ttl=20)
def annotation_workflow_metrics(_conn: sqlite3.Connection, run_ids: tuple[int, ...]) -> dict[str, object]:
    if not run_ids:
        return {
            "summary": pd.DataFrame(),
            "by_priority": pd.DataFrame(),
            "by_triage": pd.DataFrame(),
            "label_source_used": "n/a",
        }

    placeholders = ",".join(["?"] * len(run_ids))
    q = f"""
    WITH disagreement_flags AS (
        SELECT
            a.comment_db_id,
            CASE
                WHEN COUNT(DISTINCT a.annotator_id) >= 2 AND (
                    MIN(COALESCE(a.skepticism_fake_callout, 0)) <> MAX(COALESCE(a.skepticism_fake_callout, 0))
                    OR MIN(COALESCE(a.proof_demand, 0)) <> MAX(COALESCE(a.proof_demand, 0))
                    OR MIN(COALESCE(a.normalization_defense, 0)) <> MAX(COALESCE(a.normalization_defense, 0))
                    OR MIN(COALESCE(a.other_flag, 0)) <> MAX(COALESCE(a.other_flag, 0))
                    OR MIN(COALESCE(a.extra_codes, '')) <> MAX(COALESCE(a.extra_codes, ''))
                ) THEN 1
                ELSE 0
            END AS any_disagreement
        FROM annotations a
        JOIN comments c ON c.id = a.comment_db_id
        WHERE c.run_id IN ({placeholders})
        GROUP BY a.comment_db_id
    )
    SELECT
        a.comment_db_id,
        c.run_id,
        a.annotator_id,
        a.is_adjudicated,
        COALESCE(a.workflow_mode, '') AS workflow_mode,
        COALESCE(a.triage_bucket, '') AS triage_bucket,
        a.triage_score,
        COALESCE(a.priority_bucket, '') AS priority_bucket,
        a.priority_score,
        COALESCE(a.heuristic_language, '') AS heuristic_language,
        COALESCE(a.low_info_noise, 0) AS low_info_noise,
        COALESCE(a.comment_ai_signal, 0) AS comment_ai_signal,
        COALESCE(a.video_ai_signal, 0) AS video_ai_signal,
        COALESCE(df.any_disagreement, 0) AS any_disagreement
    FROM annotations a
    JOIN comments c ON c.id = a.comment_db_id
    LEFT JOIN disagreement_flags df ON df.comment_db_id = a.comment_db_id
    WHERE c.run_id IN ({placeholders})
      AND (
          a.workflow_mode IS NOT NULL
          OR a.triage_bucket IS NOT NULL
          OR a.priority_bucket IS NOT NULL
          OR a.heuristic_language IS NOT NULL
      )
    ORDER BY a.coded_at DESC, a.id DESC
    """
    rows = pd.read_sql_query(q, _conn, params=tuple(run_ids) + tuple(run_ids))
    if rows.empty:
        return {
            "summary": pd.DataFrame(),
            "by_priority": pd.DataFrame(),
            "by_triage": pd.DataFrame(),
            "label_source_used": "n/a",
        }

    labels = annotation_labels_runs_df(_conn, run_ids, "resolved_consensus", None)
    label_source_used = "resolved_consensus"
    if labels.empty:
        labels = annotation_labels_runs_df(_conn, run_ids, "latest_annotation", None)
        label_source_used = "latest_annotation"
    if not labels.empty:
        labels = labels.copy()
        labels["any_core_positive"] = (
            labels["label_skepticism"].fillna(0).astype(int)
            | labels["label_proof_demand"].fillna(0).astype(int)
            | labels["label_normalization"].fillna(0).astype(int)
        ).astype(int)
        rows = rows.merge(labels[["comment_db_id", "any_core_positive"]], on="comment_db_id", how="left")
    else:
        rows["any_core_positive"] = pd.NA

    rows["heuristic_language"] = rows["heuristic_language"].replace("", pd.NA)
    rows["label_available"] = rows["any_core_positive"].notna().astype(int)
    rows["is_positive"] = rows["any_core_positive"].fillna(0).astype(int)
    rows["non_english_flag"] = (
        rows["heuristic_language"].notna()
        & (rows["heuristic_language"] != "english_or_other_latin")
    ).astype(int)
    rows["ai_context_flag"] = ((rows["comment_ai_signal"] == 1) | (rows["video_ai_signal"] == 1)).astype(int)

    summary = pd.DataFrame(
        [
            {
                "annotated_rows": int(len(rows)),
                "rows_with_label_context": int(rows["label_available"].sum()),
                "adjudicated_rows": int(rows["is_adjudicated"].fillna(0).astype(int).sum()),
                "low_info_rate": float(rows["low_info_noise"].fillna(0).astype(float).mean()),
                "non_english_rate": float(rows["non_english_flag"].fillna(0).astype(float).mean()),
                "ai_context_rate": float(rows["ai_context_flag"].fillna(0).astype(float).mean()),
                "label_source_used": label_source_used,
            }
        ]
    )

    def _yield_table(group_col: str) -> pd.DataFrame:
        grouped = (
            rows[rows[group_col].astype(str) != ""]
            .groupby(group_col, as_index=False)
            .agg(
                annotated_rows=("comment_db_id", "count"),
                labeled_rows=("label_available", "sum"),
                positive_rows=("is_positive", "sum"),
                adjudicated_rows=("is_adjudicated", lambda s: int(pd.Series(s).fillna(0).astype(int).sum())),
                disagreement_rate=("any_disagreement", "mean"),
            )
        )
        if grouped.empty:
            return grouped
        grouped["positive_yield"] = grouped.apply(
            lambda row: float(row["positive_rows"]) / float(row["labeled_rows"]) if int(row["labeled_rows"]) else 0.0,
            axis=1,
        )
        return grouped.sort_values(["positive_yield", "annotated_rows"], ascending=[False, False])

    return {
        "summary": summary,
        "by_priority": _yield_table("priority_bucket"),
        "by_triage": _yield_table("triage_bucket"),
        "label_source_used": label_source_used,
    }


@st.cache_data(ttl=20)
def uncoded_extension_frames(
    _conn: sqlite3.Connection,
    run_ids: tuple[int, ...],
    include_flagged: bool,
) -> dict[str, pd.DataFrame]:
    if not run_ids:
        return {
            "summary": pd.DataFrame(),
            "uncoded_comments": pd.DataFrame(),
            "top_candidates": pd.DataFrame(),
            "by_run_niche": pd.DataFrame(),
        }

    comments = comments_df(_conn)
    comments = comments[comments["run_id"].isin(list(run_ids))].copy()
    if comments.empty:
        return {
            "summary": pd.DataFrame(),
            "uncoded_comments": pd.DataFrame(),
            "top_candidates": pd.DataFrame(),
            "by_run_niche": pd.DataFrame(),
        }

    placeholders = ",".join(["?"] * len(run_ids))
    coded_df = pd.read_sql_query(
        f"""
        SELECT DISTINCT a.comment_db_id
        FROM annotations a
        JOIN comments c ON c.id = a.comment_db_id
        WHERE c.run_id IN ({placeholders})
        """,
        _conn,
        params=tuple(run_ids),
    )
    coded_ids = set(coded_df["comment_db_id"].tolist()) if not coded_df.empty else set()
    uncoded = comments[~comments["comment_db_id"].isin(coded_ids)].copy()
    if not include_flagged:
        uncoded = uncoded[
            (uncoded["is_spam"] == 0)
            & (uncoded["is_template"] == 0)
            & (uncoded["is_duplicate"] == 0)
        ].copy()
    if uncoded.empty:
        return {
            "summary": pd.DataFrame(),
            "uncoded_comments": uncoded,
            "top_candidates": pd.DataFrame(),
            "by_run_niche": pd.DataFrame(),
        }

    videos = videos_df(_conn)
    videos = videos[["run_id", "video_id", "title", "description"]].drop_duplicates()
    uncoded = uncoded.merge(videos, on=["run_id", "video_id"], how="left")
    uncoded = _prepare_comment_rule_frame(uncoded)
    uncoded["title"] = uncoded["title"].fillna("")
    uncoded["description"] = uncoded["description"].fillna("")
    uncoded["video_ai_signal"] = (
        (uncoded["title"] + " " + uncoded["description"]).str.contains(AI_MENTION_REGEX, na=False).astype(int)
    )
    uncoded["comment_ai_signal"] = uncoded["has_ai_mention"].astype(int)
    uncoded["core_signal_count"] = (
        uncoded["rule_skepticism"].astype(int)
        + uncoded["rule_proof_demand"].astype(int)
        + uncoded["rule_normalization"].astype(int)
    )
    uncoded["signal_score"] = (
        uncoded["rule_skepticism"].astype(int) * 4
        + uncoded["rule_proof_demand"].astype(int) * 4
        + uncoded["rule_normalization"].astype(int) * 3
        + uncoded["comment_ai_signal"].astype(int) * 2
        + uncoded["video_ai_signal"].astype(int) * 1
        + uncoded["lex_request"].astype(int) * 0.5
        + uncoded["lex_negation"].astype(int) * 0.5
        - uncoded["low_info_noise"].astype(int) * 1.5
    )
    trace = uncoded.apply(
        lambda row: _build_signal_trace(
            comment_text=row.get("cleaned_text"),
            title=row.get("title"),
            description=row.get("description"),
        ),
        axis=1,
    )
    uncoded["trace_summary"] = trace.apply(lambda x: _safe_text(x.get("summary")))
    uncoded["auto_labels"] = trace.apply(lambda x: ", ".join(x.get("suggested_labels", [])) or "none")

    summary = pd.DataFrame(
        [
            {
                "runs": ", ".join(str(x) for x in run_ids),
                "uncoded_comments": int(len(uncoded)),
                "channels": int(uncoded["channel_id"].nunique()),
                "videos": int(uncoded["video_id"].nunique()),
                "core_signal_rows": int((uncoded["core_signal_count"] > 0).sum()),
                "ai_context_rows": int(((uncoded["comment_ai_signal"] == 1) | (uncoded["video_ai_signal"] == 1)).sum()),
                "non_english_rows": int((uncoded["heuristic_language"] != "english_or_other_latin").sum()),
                "low_info_rows": int(uncoded["low_info_noise"].sum()),
                "include_flagged": int(include_flagged),
            }
        ]
    )
    by_run_niche = (
        uncoded.groupby(["run_id", "channel_niche"], as_index=False)
        .agg(
            uncoded_comments=("comment_db_id", "count"),
            core_signal_rows=("core_signal_count", lambda s: int((s > 0).sum())),
            ai_context_rows=("comment_ai_signal", "sum"),
            low_info_rows=("low_info_noise", "sum"),
        )
        .sort_values(["run_id", "channel_niche"])
    )
    top_candidates = uncoded.sort_values(
        ["signal_score", "core_signal_count", "comment_rank", "like_count"],
        ascending=[False, False, True, False],
    ).copy()

    return {
        "summary": summary,
        "uncoded_comments": uncoded,
        "top_candidates": top_candidates,
        "by_run_niche": by_run_niche,
    }


def build_final_analysis_pack(
    conn: sqlite3.Connection,
    run_ids: tuple[int, ...],
    annotator_id: str,
) -> dict[str, object]:
    snapshot = evidence_base_snapshot(conn, run_ids)
    frames = conformity_frames_multi(conn, run_ids, False, "resolved_consensus", annotator_id)
    resolved = snapshot["resolved_comments"].copy()
    positives = resolved[
        (resolved["analysis_skepticism"].fillna(0).astype(int) == 1)
        | (resolved["analysis_proof_demand"].fillna(0).astype(int) == 1)
        | (resolved["analysis_normalization"].fillna(0).astype(int) == 1)
    ].copy()
    positive_appendix = positives[
        [
            "run_id",
            "channel_niche",
            "channel_id",
            "video_id",
            "comment_rank",
            "analysis_skepticism",
            "analysis_proof_demand",
            "analysis_normalization",
            "cleaned_text",
        ]
    ].sort_values(["run_id", "channel_niche", "video_id", "comment_rank"])

    extension = uncoded_extension_frames(conn, run_ids, include_flagged=False)
    extension_appendix = extension["top_candidates"].head(250).copy()
    if not extension_appendix.empty:
        extension_appendix = extension_appendix[
            [
                "run_id",
                "channel_niche",
                "channel_id",
                "video_id",
                "comment_rank",
                "signal_score",
                "auto_labels",
                "heuristic_language",
                "low_info_noise",
                "cleaned_text",
                "trace_summary",
            ]
        ]

    summary_row = frames["summary_df"].iloc[0].to_dict() if not frames["summary_df"].empty else {}
    pack = {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "annotator_id": annotator_id,
        "label_source": "resolved_consensus",
        "run_ids": list(run_ids),
        "snapshot_summary": snapshot["summary"],
        "hypothesis_summary": summary_row,
        "tables": {
            "prevalence_overall": snapshot["prevalence_overall"].to_dict(orient="records"),
            "prevalence_by_run_niche": snapshot["prevalence_by_run_niche"].to_dict(orient="records"),
            "combined_effects": frames["effects_df"].to_dict(orient="records"),
            "icc": frames["icc_df"].to_dict(orient="records"),
            "extension_uncoded_summary": extension["summary"].to_dict(orient="records"),
            "extension_by_run_niche": extension["by_run_niche"].to_dict(orient="records"),
        },
    }
    return {
        "bundle": pack,
        "snapshot": snapshot,
        "conformity_frames": frames,
        "positive_appendix": positive_appendix,
        "extension_appendix": extension_appendix,
    }


@st.cache_data(ttl=20)
def study_profiles_df(_conn: sqlite3.Connection, owner: str) -> pd.DataFrame:
    q = """
    SELECT
        id,
        name,
        owner,
        description,
        profile_json,
        created_at,
        updated_at
    FROM study_profiles
    WHERE owner = ?
    ORDER BY updated_at DESC, id DESC
    """
    return pd.read_sql_query(q, _conn, params=(owner,))


def upsert_study_profile(
    conn: sqlite3.Connection,
    *,
    owner: str,
    name: str,
    description: str,
    payload: dict[str, object],
) -> int:
    now = datetime.now(tz=timezone.utc).isoformat()
    payload_json = json.dumps(payload, ensure_ascii=True)
    conn.execute(
        """
        INSERT INTO study_profiles (
            name, owner, description, profile_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(owner, name)
        DO UPDATE SET
            description = excluded.description,
            profile_json = excluded.profile_json,
            updated_at = excluded.updated_at
        """,
        (name.strip(), owner, description.strip(), payload_json, now, now),
    )
    row = conn.execute(
        "SELECT id FROM study_profiles WHERE owner = ? AND name = ?",
        (owner, name.strip()),
    ).fetchone()
    conn.commit()
    return int(row["id"]) if row else 0


def delete_study_profile(conn: sqlite3.Connection, *, owner: str, profile_id: int) -> None:
    conn.execute("DELETE FROM study_profiles WHERE id = ? AND owner = ?", (int(profile_id), owner))
    conn.commit()


def _seed_runlab_state(config, target_files: list[str]) -> None:
    if "runlab_target_file" not in st.session_state:
        st.session_state["runlab_target_file"] = target_files[0] if target_files else ""
    if "runlab_execution_mode" not in st.session_state:
        st.session_state["runlab_execution_mode"] = config.execution_mode
    if "runlab_content" not in st.session_state:
        st.session_state["runlab_content"] = "videos"
    if "runlab_channel_limit" not in st.session_state:
        st.session_state["runlab_channel_limit"] = 30
    if "runlab_videos_per_channel" not in st.session_state:
        st.session_state["runlab_videos_per_channel"] = 20
    if "runlab_min_expected" not in st.session_state:
        st.session_state["runlab_min_expected"] = 20
    if "runlab_template_threshold" not in st.session_state:
        st.session_state["runlab_template_threshold"] = 0.90
    if "runlab_simulate" not in st.session_state:
        st.session_state["runlab_simulate"] = False
    if "runlab_dataset_niches" not in st.session_state:
        st.session_state["runlab_dataset_niches"] = ["Tech", "Beauty", "Lifestyle"]
    if "runlab_include_shorts_filter" not in st.session_state:
        st.session_state["runlab_include_shorts_filter"] = False
    if "runlab_include_spam_filter" not in st.session_state:
        st.session_state["runlab_include_spam_filter"] = False
    if "runlab_include_template_filter" not in st.session_state:
        st.session_state["runlab_include_template_filter"] = False
    if "runlab_include_duplicate_filter" not in st.session_state:
        st.session_state["runlab_include_duplicate_filter"] = False
    if "runlab_comment_rank_min" not in st.session_state:
        st.session_state["runlab_comment_rank_min"] = 1
    if "runlab_comment_rank_max" not in st.session_state:
        st.session_state["runlab_comment_rank_max"] = 20
    if "runlab_min_comments_video_filter" not in st.session_state:
        st.session_state["runlab_min_comments_video_filter"] = 0
    if "runlab_active_profile_name" not in st.session_state:
        st.session_state["runlab_active_profile_name"] = ""


def _current_runlab_payload() -> dict[str, object]:
    return {
        "logic_registry": logic_registry(),
        "scrape": {
            "targets_csv": _safe_text(st.session_state.get("runlab_target_file")),
            "execution_mode": _safe_text(st.session_state.get("runlab_execution_mode")),
            "content_type": _safe_text(st.session_state.get("runlab_content")),
            "channel_limit": int(st.session_state.get("runlab_channel_limit", 0) or 0),
            "videos_per_channel": int(st.session_state.get("runlab_videos_per_channel", 20) or 20),
            "min_expected_videos_per_channel": int(st.session_state.get("runlab_min_expected", 20) or 20),
            "template_threshold": float(st.session_state.get("runlab_template_threshold", 0.90) or 0.90),
            "simulate": bool(st.session_state.get("runlab_simulate", False)),
            "study_profile_name": _safe_text(st.session_state.get("runlab_active_profile_name")),
        },
        "dataset_filters": {
            "niches": list(st.session_state.get("runlab_dataset_niches", [])),
            "include_shorts": bool(st.session_state.get("runlab_include_shorts_filter", False)),
            "include_spam": bool(st.session_state.get("runlab_include_spam_filter", False)),
            "include_template": bool(st.session_state.get("runlab_include_template_filter", False)),
            "include_duplicate": bool(st.session_state.get("runlab_include_duplicate_filter", False)),
            "comment_rank_min": int(st.session_state.get("runlab_comment_rank_min", 1) or 1),
            "comment_rank_max": int(st.session_state.get("runlab_comment_rank_max", 20) or 20),
            "min_comments_per_video": int(st.session_state.get("runlab_min_comments_video_filter", 0) or 0),
        },
    }


def _apply_runlab_payload(payload: dict[str, object], target_files: list[str]) -> None:
    scrape = payload.get("scrape", {}) if isinstance(payload.get("scrape"), dict) else {}
    dfilter = payload.get("dataset_filters", {}) if isinstance(payload.get("dataset_filters"), dict) else {}

    target = _safe_text(scrape.get("targets_csv"))
    if target in target_files:
        st.session_state["runlab_target_file"] = target
    st.session_state["runlab_execution_mode"] = _safe_text(scrape.get("execution_mode")) or "auto"
    st.session_state["runlab_content"] = _safe_text(scrape.get("content_type")) or "videos"
    st.session_state["runlab_channel_limit"] = int(scrape.get("channel_limit", 0) or 0)
    st.session_state["runlab_videos_per_channel"] = int(scrape.get("videos_per_channel", 20) or 20)
    st.session_state["runlab_min_expected"] = int(scrape.get("min_expected_videos_per_channel", 20) or 20)
    st.session_state["runlab_template_threshold"] = float(scrape.get("template_threshold", 0.90) or 0.90)
    st.session_state["runlab_simulate"] = bool(scrape.get("simulate", False))
    st.session_state["runlab_active_profile_name"] = _safe_text(scrape.get("study_profile_name"))

    st.session_state["runlab_dataset_niches"] = list(dfilter.get("niches", []))
    st.session_state["runlab_include_shorts_filter"] = bool(dfilter.get("include_shorts", False))
    st.session_state["runlab_include_spam_filter"] = bool(dfilter.get("include_spam", False))
    st.session_state["runlab_include_template_filter"] = bool(dfilter.get("include_template", False))
    st.session_state["runlab_include_duplicate_filter"] = bool(dfilter.get("include_duplicate", False))
    st.session_state["runlab_comment_rank_min"] = int(dfilter.get("comment_rank_min", 1) or 1)
    st.session_state["runlab_comment_rank_max"] = int(dfilter.get("comment_rank_max", 20) or 20)
    st.session_state["runlab_min_comments_video_filter"] = int(dfilter.get("min_comments_per_video", 0) or 0)


def _sync_annotation_mode_state(workflow_mode: str) -> None:
    prev_mode = _safe_text(st.session_state.get("_annotation_prev_workflow_mode"))
    if workflow_mode != prev_mode:
        st.session_state["annotation_save_as_adjudicated"] = workflow_mode == "Adjudication"
        st.session_state["_annotation_prev_workflow_mode"] = workflow_mode


ANNOTATION_VIEW_STATE_KEYS = [
    "_annotation_prev_workflow_mode",
    "annot_run_id",
    "annotation_workflow_mode",
    "annotation_subset_file",
    "annotation_batch_size",
    "annotation_queue_limit",
    "annotation_priority_mode",
    "annotation_triage_mode",
    "annotation_triage_cutoff",
    "annotation_ai_focus_mode",
    "annotation_text_quality_mode",
    "annotation_diversity_video_cap",
    "annotation_diversity_channel_cap",
    "annotation_niche_filter",
    "annotation_adjudication_filter",
    "annotation_show_label_summary",
    "annotation_show_trace_details",
    "annotation_save_as_adjudicated",
]


def _latest_uncoded_run_id(conn: sqlite3.Connection, annotator_id: str) -> int | None:
    row = conn.execute(
        """
        SELECT c.run_id
        FROM comments c
        JOIN runs r ON r.id = c.run_id
        LEFT JOIN annotations a
            ON a.comment_db_id = c.id
           AND a.annotator_id = ?
        WHERE a.comment_db_id IS NULL
          AND r.status = 'completed'
          AND COALESCE(c.is_spam, 0) = 0
          AND COALESCE(c.is_template, 0) = 0
          AND COALESCE(c.is_duplicate, 0) = 0
        GROUP BY c.run_id
        HAVING COUNT(*) > 0
        ORDER BY c.run_id DESC
        LIMIT 1
        """,
        (annotator_id,),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else None


def _reset_annotation_view_state() -> None:
    for key in ANNOTATION_VIEW_STATE_KEYS:
        st.session_state.pop(key, None)


def _prime_annotation_simple_mode(run_id: int | None) -> None:
    _reset_annotation_view_state()
    st.session_state["annot_run_id"] = run_id
    st.session_state["annotation_workflow_mode"] = "Coding"
    st.session_state["annotation_subset_file"] = "(none)"
    st.session_state["annotation_priority_mode"] = "Active learning"
    st.session_state["annotation_triage_mode"] = "All"
    st.session_state["annotation_ai_focus_mode"] = "All comments"
    st.session_state["annotation_text_quality_mode"] = "All comments"
    st.session_state["annotation_diversity_video_cap"] = 2
    st.session_state["annotation_diversity_channel_cap"] = 6
    st.session_state["annotation_batch_size"] = 6
    st.session_state["annotation_queue_limit"] = 1000
    st.session_state["annotation_show_trace_details"] = False
    st.session_state["annotation_show_label_summary"] = False
    st.session_state["annotation_save_as_adjudicated"] = False


def _safe_text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _infer_disclosure_level(text: str) -> int:
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


def _disclosure_label(level: int) -> str:
    return {
        0: "0_none",
        1: "1_generic",
        2: "2_specific",
        3: "3_verifiable",
    }.get(level, "unknown")


def _prepare_video_disclosure_frame(videos: pd.DataFrame) -> pd.DataFrame:
    v = videos.copy()
    v["title"] = v["title"].fillna("")
    v["description"] = v["description"].fillna("")
    v["combined_text"] = (v["title"] + " " + v["description"]).str.strip()
    v["has_ai_mention"] = v["combined_text"].str.contains(AI_MENTION_REGEX, na=False)
    v["inferred_disclosure_level"] = v["combined_text"].apply(_infer_disclosure_level)
    v["inferred_disclosure_label"] = v["inferred_disclosure_level"].apply(_disclosure_label)
    return v


def _prepare_comment_rule_frame(comments: pd.DataFrame) -> pd.DataFrame:
    c = comments.copy()
    c["cleaned_text"] = c["cleaned_text"].fillna("")
    c = append_comment_text_features(c, text_col="cleaned_text")
    if "comment_timestamp" in c.columns:
        c["comment_timestamp"] = pd.to_datetime(c["comment_timestamp"], errors="coerce", utc=True)
    elif "extraction_ts" in c.columns:
        c["comment_timestamp"] = pd.to_datetime(c["extraction_ts"], errors="coerce", utc=True)
    c["rule_skepticism"] = c["cleaned_text"].str.contains(SKEPTICISM_REGEX, na=False).astype(int)
    c["rule_proof_demand"] = c["cleaned_text"].str.contains(PROOF_DEMAND_REGEX, na=False).astype(int)
    c["rule_normalization"] = c["cleaned_text"].str.contains(NORMALIZATION_REGEX, na=False).astype(int)
    c["has_ai_mention"] = c["cleaned_text"].str.contains(AI_MENTION_REGEX, na=False).astype(int)
    return c


def _choose_analysis_niche(label: str) -> str:
    if label in {"Tech", "Beauty"}:
        return "high_risk_proxy"
    return "low_risk_proxy"


def _format_proxy_value(value: object) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.4f}"


def _format_effect_term(term: object) -> str:
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


def _display_effects_df(effects_df: pd.DataFrame) -> pd.DataFrame:
    if effects_df is None or effects_df.empty:
        return effects_df
    display = effects_df.copy()
    if "term" in display.columns:
        display["term"] = display["term"].apply(_format_effect_term)
    return display


def _cue_rate_chart_df(summary_row: pd.Series | dict[str, object]) -> pd.DataFrame:
    skeptical = pd.to_numeric(summary_row.get("response_skepticism_after_skeptical_cue"), errors="coerce")
    non_skeptical = pd.to_numeric(summary_row.get("response_skepticism_after_non_skeptical_cue"), errors="coerce")
    data = pd.DataFrame(
        [
            {"cue_label": "Skeptical top cue", "skepticism_rate": skeptical},
            {"cue_label": "Non-skeptical top cue", "skepticism_rate": non_skeptical},
        ]
    )
    data = data.dropna(subset=["skepticism_rate"]).copy()
    return data


def _niche_cue_rate_chart_df(response_df: pd.DataFrame) -> pd.DataFrame:
    if response_df is None or response_df.empty:
        return pd.DataFrame()
    grouped = (
        response_df.groupby(["channel_niche", "top_comment_skeptical"], as_index=False)
        .agg(
            response_comments=("video_id", "count"),
            skepticism_rate=("is_skeptical", "mean"),
        )
        .sort_values(["channel_niche", "top_comment_skeptical"])
    )
    grouped["cue_label"] = grouped["top_comment_skeptical"].map(
        {1: "Skeptical top cue", 0: "Non-skeptical top cue"}
    )
    return grouped


def _effects_plot_df(effects_df: pd.DataFrame) -> pd.DataFrame:
    if effects_df is None or effects_df.empty:
        return pd.DataFrame()
    keep = effects_df.copy()
    keep = keep[keep["term"] != "Intercept"].copy()
    keep["term_display"] = keep["term"].apply(_format_effect_term)
    keep["odds_ratio"] = pd.to_numeric(keep["odds_ratio"], errors="coerce")
    keep["or_ci_95_low"] = pd.to_numeric(keep["or_ci_95_low"], errors="coerce")
    keep["or_ci_95_high"] = pd.to_numeric(keep["or_ci_95_high"], errors="coerce")
    keep["p_value_approx"] = pd.to_numeric(keep["p_value_approx"], errors="coerce")
    keep = keep[
        keep["odds_ratio"].notna()
        & keep["or_ci_95_low"].notna()
        & keep["or_ci_95_high"].notna()
        & (keep["or_ci_95_low"] > 0)
    ].copy()
    keep["significant"] = keep["p_value_approx"] < 0.05
    keep = keep.sort_values("odds_ratio", ascending=True).reset_index(drop=True)
    return keep


def render_hypothesis_visuals(
    *,
    summary_row: pd.Series | dict[str, object],
    effects_df: pd.DataFrame,
    response_df: pd.DataFrame,
) -> None:
    st.markdown("**Hypothesis visuals**")

    cue_chart_df = _cue_rate_chart_df(summary_row)
    niche_chart_df = _niche_cue_rate_chart_df(response_df)
    effects_chart_df = _effects_plot_df(effects_df)

    c1, c2 = st.columns(2)
    with c1:
        st.caption("Downstream skepticism after top-cue type")
        if cue_chart_df.empty:
            st.info("Not enough rows for cue comparison chart.")
        else:
            st.vega_lite_chart(
                cue_chart_df,
                {
                    "mark": {"type": "bar", "cornerRadiusTopLeft": 4, "cornerRadiusTopRight": 4},
                    "encoding": {
                        "x": {"field": "cue_label", "type": "nominal", "title": None},
                        "y": {
                            "field": "skepticism_rate",
                            "type": "quantitative",
                            "title": "Response skepticism rate",
                            "axis": {"format": "%"},
                            "scale": {"domain": [0, 1]},
                        },
                        "color": {
                            "field": "cue_label",
                            "type": "nominal",
                            "legend": None,
                            "scale": {
                                "domain": ["Non-skeptical top cue", "Skeptical top cue"],
                                "range": ["#9FB3C8", "#1F5A8A"],
                            },
                        },
                        "tooltip": [
                            {"field": "cue_label", "type": "nominal"},
                            {"field": "skepticism_rate", "type": "quantitative", "format": ".3f"},
                        ],
                    },
                    "height": 240,
                },
                use_container_width=True,
            )

    with c2:
        st.caption("Observed skepticism by niche and cue type")
        if niche_chart_df.empty:
            st.info("Not enough rows for niche chart.")
        else:
            st.vega_lite_chart(
                niche_chart_df,
                {
                    "mark": {"type": "line", "point": True, "strokeWidth": 3},
                    "encoding": {
                        "x": {"field": "channel_niche", "type": "nominal", "title": "Channel niche"},
                        "y": {
                            "field": "skepticism_rate",
                            "type": "quantitative",
                            "title": "Observed response skepticism rate",
                            "axis": {"format": "%"},
                            "scale": {"domain": [0, 1]},
                        },
                        "color": {
                            "field": "cue_label",
                            "type": "nominal",
                            "scale": {
                                "domain": ["Non-skeptical top cue", "Skeptical top cue"],
                                "range": ["#9FB3C8", "#1F5A8A"],
                            },
                            "legend": {"title": "Top cue"},
                        },
                        "tooltip": [
                            {"field": "channel_niche", "type": "nominal"},
                            {"field": "cue_label", "type": "nominal"},
                            {"field": "response_comments", "type": "quantitative"},
                            {"field": "skepticism_rate", "type": "quantitative", "format": ".3f"},
                        ],
                    },
                    "height": 240,
                },
                use_container_width=True,
            )

    st.caption("Model effects (odds ratio with 95% CI)")
    if effects_chart_df.empty:
        st.info("Not enough rows for effects plot.")
        return

    term_order = effects_chart_df["term_display"].tolist()
    st.vega_lite_chart(
        effects_chart_df,
        {
            "width": "container",
            "height": 320,
            "layer": [
                {
                    "mark": {"type": "rule", "strokeWidth": 2},
                    "encoding": {
                        "y": {"field": "term_display", "type": "nominal", "sort": term_order, "title": None},
                        "x": {"field": "or_ci_95_low", "type": "quantitative", "title": "Odds ratio (log scale)", "scale": {"type": "log"}},
                        "x2": {"field": "or_ci_95_high"},
                        "color": {
                            "field": "significant",
                            "type": "nominal",
                            "legend": None,
                            "scale": {"domain": [True, False], "range": ["#0F4C75", "#A9B8C4"]},
                        },
                        "tooltip": [
                            {"field": "term_display", "type": "nominal"},
                            {"field": "odds_ratio", "type": "quantitative", "format": ".3f"},
                            {"field": "or_ci_95_low", "type": "quantitative", "format": ".3f"},
                            {"field": "or_ci_95_high", "type": "quantitative", "format": ".3f"},
                            {"field": "p_value_approx", "type": "quantitative", "format": ".3g"},
                        ],
                    },
                },
                {
                    "mark": {"type": "point", "filled": True, "size": 75},
                    "encoding": {
                        "y": {"field": "term_display", "type": "nominal", "sort": term_order, "title": None},
                        "x": {"field": "odds_ratio", "type": "quantitative", "scale": {"type": "log"}},
                        "color": {
                            "field": "significant",
                            "type": "nominal",
                            "legend": None,
                            "scale": {"domain": [True, False], "range": ["#0F4C75", "#A9B8C4"]},
                        },
                    },
                },
                {
                    "data": {"values": [{"ref_or": 1}]},
                    "mark": {"type": "rule", "strokeDash": [4, 4], "color": "#555"},
                    "encoding": {"x": {"field": "ref_or", "type": "quantitative", "scale": {"type": "log"}}},
                },
            ],
        },
        use_container_width=True,
    )


def _label_source_label(label_source: str) -> str:
    for key, label in LABEL_SOURCE_OPTIONS:
        if key == label_source:
            return label
    return label_source


def inject_app_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --paper: #f7f7f5;
            --paper-strong: #ffffff;
            --ink: #1d2935;
            --muted: #667382;
            --line: rgba(29, 41, 53, 0.12);
            --accent: #1d2935;
            --accent-strong: #111827;
            --sage: #eef2f5;
            --gold: #f1f4f6;
            --shadow: 0 6px 18px rgba(29, 41, 53, 0.05);
            --radius-lg: 16px;
            --radius-md: 12px;
        }

        .stApp {
            color: var(--ink);
            background: var(--paper);
        }

        [data-testid="stAppViewContainer"] > .main {
            background: transparent;
        }

        .block-container {
            max-width: 1450px;
            padding-top: 1rem;
            padding-bottom: 2.25rem;
        }

        h1, h2, h3, .research-title {
            font-family: "SF Pro Display", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
            letter-spacing: -0.03em;
            color: var(--ink);
        }

        p, li, label, .stCaption, .stMarkdown, .stTextInput, .stSelectbox, .stMultiSelect {
            font-family: "SF Pro Text", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        }

        div[data-testid="stSidebar"] {
            background: #fbfbfa;
            border-right: 1px solid rgba(29, 41, 53, 0.08);
        }

        div[data-testid="stSidebar"] * {
            color: var(--ink);
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 0.2rem;
            padding: 0.2rem;
            margin: 0.1rem 0 1rem 0;
            border-radius: 12px;
            border: 1px solid rgba(29, 41, 53, 0.08);
            background: #fbfbfa;
            box-shadow: none;
        }

        .stTabs [data-baseweb="tab"] {
            min-height: 42px;
            padding: 0.45rem 0.85rem;
            border-radius: 10px;
            color: var(--muted);
            font-weight: 600;
            transition: background 160ms ease, color 160ms ease;
        }

        .stTabs [data-baseweb="tab"]:hover {
            color: var(--ink);
            background: #f1f4f6;
        }

        .stTabs [aria-selected="true"] {
            color: var(--ink) !important;
            background: #e9eef2;
            box-shadow: none;
        }

        div[data-testid="stMetric"] {
            background: var(--paper-strong);
            border: 1px solid rgba(29, 41, 53, 0.08);
            border-radius: 12px;
            padding: 0.7rem 0.85rem;
            box-shadow: none;
        }

        div[data-testid="stMetric"] label {
            color: var(--muted);
            font-weight: 600;
            text-transform: none;
            letter-spacing: 0;
            font-size: 0.7rem;
        }

        div[data-testid="stMetricValue"] {
            color: var(--ink);
            font-family: "SF Pro Display", "Segoe UI", sans-serif;
        }

        div[data-testid="stDataFrame"], div[data-testid="stTable"] {
            border: 1px solid rgba(29, 41, 53, 0.08);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: none;
            background: var(--paper-strong);
        }

        .streamlit-expanderHeader {
            color: var(--ink);
            font-weight: 600;
        }

        button[kind="primary"], .stDownloadButton button, .stButton button {
            border-radius: 10px;
            border: 1px solid rgba(29, 41, 53, 0.10);
            transition: background 160ms ease, border-color 160ms ease;
        }

        button[kind="primary"] {
            background: var(--accent);
            color: #ffffff;
            box-shadow: none;
        }

        .stDownloadButton button:hover, .stButton button:hover, button[kind="primary"]:hover {
            background: #eef2f5;
            border-color: rgba(29, 41, 53, 0.14);
            color: var(--ink);
        }

        .research-masthead, .section-intro, .research-card {
            border: 1px solid var(--line);
            border-radius: var(--radius-lg);
            background: var(--paper-strong);
            box-shadow: none;
        }

        .research-masthead {
            padding: 1.15rem 1.25rem;
            margin-bottom: 0.85rem;
        }

        .research-kicker {
            font-size: 0.72rem;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            font-weight: 700;
            color: var(--muted);
            margin-bottom: 0.22rem;
        }

        .research-title {
            font-size: clamp(1.9rem, 2.5vw, 2.6rem);
            line-height: 1.08;
            margin: 0;
        }

        .research-subtitle {
            color: var(--muted);
            margin-top: 0.45rem;
            max-width: 60rem;
            font-size: 0.96rem;
        }

        .research-chip-row {
            display: flex;
            gap: 0.45rem;
            flex-wrap: wrap;
            margin-top: 0.8rem;
        }

        .research-chip {
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            border-radius: 999px;
            padding: 0.32rem 0.65rem;
            font-size: 0.78rem;
            font-weight: 600;
            background: #f5f7f8;
            color: var(--ink);
            border: 1px solid rgba(29, 41, 53, 0.08);
        }

        .research-chip strong {
            color: var(--muted);
        }

        .section-intro {
            padding: 0.9rem 1rem;
            margin-bottom: 0.75rem;
        }

        .section-intro h3 {
            margin: 0.06rem 0 0.16rem 0;
            font-size: 1.28rem;
        }

        .section-intro p {
            margin: 0;
            color: var(--muted);
        }

        .tile-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 0.65rem;
            margin: 0.2rem 0 0.9rem 0;
        }

        .research-card.metric-tile {
            padding: 0.85rem 0.9rem;
            border-radius: var(--radius-md);
        }

        .metric-eyebrow {
            color: var(--muted);
            text-transform: none;
            letter-spacing: 0;
            font-size: 0.78rem;
            font-weight: 600;
        }

        .metric-number {
            margin-top: 0.18rem;
            font-size: 1.6rem;
            line-height: 1.1;
            font-family: "SF Pro Display", "Segoe UI", sans-serif;
            color: var(--ink);
        }

        .metric-footnote {
            margin-top: 0.3rem;
            color: var(--muted);
            font-size: 0.85rem;
        }

        .metric-tile.tone-accent {
            background: var(--paper-strong);
        }

        .metric-tile.tone-sage {
            background: var(--paper-strong);
        }

        .metric-tile.tone-gold {
            background: var(--paper-strong);
        }

        .note-banner {
            margin: 0.55rem 0 0.9rem 0;
            padding: 0.75rem 0.9rem;
            border-radius: 12px;
            background: #f8fafb;
            border: 1px solid rgba(29, 41, 53, 0.08);
            color: var(--ink);
        }

        .note-banner strong {
            color: var(--ink);
        }

        .layer-badge-row {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            flex-wrap: wrap;
            margin: 0.35rem 0 0.75rem 0;
        }

        .layer-badge {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.22rem 0.58rem;
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.03em;
            text-transform: uppercase;
        }

        .layer-badge-validated {
            background: #eef7f0;
            color: #355a3e;
        }

        .layer-badge-assistive {
            background: #f6f1e7;
            color: #6d5836;
        }

        .layer-badge-warning {
            background: #f8ecec;
            color: #7a4d4d;
        }

        .layer-badge-note {
            color: var(--muted);
            font-size: 0.85rem;
        }

        .hypothesis-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 0.65rem;
            margin: 0.7rem 0 0.9rem 0;
        }

        .hypothesis-card {
            padding: 0.9rem;
            border-radius: var(--radius-md);
        }

        .hypothesis-status {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 0.2rem 0.5rem;
            font-size: 0.69rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 0.5rem;
        }

        .status-supported {
            background: #eef4ef;
            color: #3e5c43;
        }

        .status-inconclusive {
            background: #f3f4f6;
            color: #59636d;
        }

        .status-caution {
            background: #f5efef;
            color: #705656;
        }

        .hypothesis-title {
            font-weight: 700;
            color: var(--ink);
            margin-bottom: 0.25rem;
        }

        .hypothesis-metric {
            font-family: "SF Pro Display", "Segoe UI", sans-serif;
            font-size: 1.35rem;
            margin-bottom: 0.2rem;
            color: var(--ink);
        }

        .hypothesis-note {
            color: var(--muted);
            font-size: 0.9rem;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


def render_masthead(title: str, subtitle: str, chips: list[tuple[str, object]]) -> None:
    st.title(title)
    st.caption(subtitle)
    if chips:
        chip_text = " | ".join(
            f"{_safe_text(label)}: {_safe_text(value) or 'n/a'}"
            for label, value in chips
        )
        st.caption(chip_text)


def render_section_intro(kicker: str, title: str, body: str) -> None:
    st.markdown(
        f"""
        <section class="section-intro">
            <div class="research-kicker">{html.escape(kicker)}</div>
            <h3>{html.escape(title)}</h3>
            <p>{html.escape(body)}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_note_banner(label: str, body: str) -> None:
    st.markdown(
        f"<div class='note-banner'><strong>{html.escape(label)}:</strong> {html.escape(body)}</div>",
        unsafe_allow_html=True,
    )


def render_layer_badge(kind: str, note: str = "") -> None:
    class_map = {
        "validated": ("layer-badge-validated", "Validated / paper-safe"),
        "assistive": ("layer-badge-assistive", "Assistive / exploratory only"),
        "warning": ("layer-badge-warning", "Not paper-safe by default"),
    }
    css_class, label = class_map.get(kind, ("layer-badge-assistive", _safe_text(kind) or "Layer"))
    note_html = f"<span class='layer-badge-note'>{html.escape(note)}</span>" if note else ""
    st.markdown(
        f"<div class='layer-badge-row'><span class='layer-badge {css_class}'>{html.escape(label)}</span>{note_html}</div>",
        unsafe_allow_html=True,
    )


def render_evidence_boundary_banner(scope_label: str, body: str) -> None:
    render_note_banner(scope_label, body)


def render_scope_badge(scope_label: str, body: str = "") -> None:
    normalized = _safe_text(scope_label).strip().lower()
    exploratory_note = (
        "This view includes exploratory or assistive outputs and should not be used directly for paper-facing claims."
    )
    validated_note = "This view is based only on the frozen validated evidence layer."
    if "validated" in normalized:
        render_layer_badge("validated", f"{validated_note} {_safe_text(body)}".strip())
    elif "assistive" in normalized or "exploratory" in normalized:
        render_layer_badge("warning", f"{exploratory_note} {_safe_text(body)}".strip())
    else:
        render_layer_badge("assistive", f"{exploratory_note} {_safe_text(body)}".strip())


def _label_source_scope(label_source: str) -> tuple[str, str]:
    normalized = _safe_text(label_source).strip().lower()
    if normalized == "resolved_consensus":
        return (
            "Validated evidence layer",
            "This view is using resolved human-coded evidence suitable for the paper's main confirmatory claims.",
        )
    if normalized == "adjudicated":
        return (
            "Human-coded but narrower layer",
            "This view is using adjudicated labels only. It is human-coded, but not the paper's default validated evidence layer unless stated explicitly.",
        )
    return (
        "Assistive / exploratory layer",
        "This view is not using the frozen resolved-consensus evidence base. Treat it as exploratory, supportive, or analyst-specific rather than confirmatory.",
    )


def render_metric_tiles(items: list[dict[str, object]]) -> None:
    if not items:
        return
    cols = st.columns(len(items))
    for col, item in zip(cols, items):
        with col:
            st.metric(_safe_text(item.get("label")), _safe_text(item.get("value")))
            note = _safe_text(item.get("note"))
            if note:
                st.caption(note)


def render_hypothesis_cards(cards: list[dict[str, object]]) -> None:
    status_map = {
        "supported": ("status-supported", "Supported"),
        "inconclusive": ("status-inconclusive", "Inconclusive"),
        "not_supported_or_inconclusive": ("status-caution", "Weak / mixed"),
        "caution": ("status-caution", "Caution"),
    }
    html_cards: list[str] = []
    for card in cards:
        key = _safe_text(card.get("status")) or "inconclusive"
        css_class, label = status_map.get(key, ("status-inconclusive", key.replace("_", " ").title()))
        html_cards.append(
            f"""
            <div class="research-card hypothesis-card">
                <div class="hypothesis-status {css_class}">{html.escape(label)}</div>
                <div class="hypothesis-title">{html.escape(_safe_text(card.get('title')))}</div>
                <div class="hypothesis-metric">{html.escape(_safe_text(card.get('metric')) or 'n/a')}</div>
                <div class="hypothesis-note">{html.escape(_safe_text(card.get('note')))}</div>
            </div>
            """
        )
    st.markdown(f"<div class='hypothesis-grid'>{''.join(html_cards)}</div>", unsafe_allow_html=True)


def _apply_label_source(
    comments: pd.DataFrame,
    *,
    run_id: int,
    label_source: str,
    annotator_id: str | None,
    conn: sqlite3.Connection,
) -> tuple[pd.DataFrame, dict[str, object]]:
    prepared = _prepare_comment_rule_frame(comments)
    prepared["analysis_skepticism"] = prepared["rule_skepticism"]
    prepared["analysis_proof_demand"] = prepared["rule_proof_demand"]
    prepared["analysis_normalization"] = prepared["rule_normalization"]

    meta: dict[str, object] = {
        "label_source": label_source,
        "label_source_label": _label_source_label(label_source),
        "labeled_comments": int(len(prepared)),
        "skepticism_labeled_comments": int(len(prepared)),
        "proof_labeled_comments": int(len(prepared)),
    }
    if label_source == "rules":
        return prepared, meta

    labels = annotation_labels_df(conn, run_id, label_source, annotator_id)
    if labels.empty:
        prepared["analysis_skepticism"] = pd.Series([pd.NA] * len(prepared), dtype="Int64")
        prepared["analysis_proof_demand"] = pd.Series([pd.NA] * len(prepared), dtype="Int64")
        prepared["analysis_normalization"] = pd.Series([pd.NA] * len(prepared), dtype="Int64")
        meta["labeled_comments"] = 0
        meta["skepticism_labeled_comments"] = 0
        meta["proof_labeled_comments"] = 0
        return prepared, meta

    merged = prepared.merge(labels, on="comment_db_id", how="left")
    merged["analysis_skepticism"] = pd.to_numeric(merged["label_skepticism"], errors="coerce").astype("Int64")
    merged["analysis_proof_demand"] = pd.to_numeric(merged["label_proof_demand"], errors="coerce").astype("Int64")
    merged["analysis_normalization"] = pd.to_numeric(merged["label_normalization"], errors="coerce").astype("Int64")
    meta["labeled_comments"] = int(merged["analysis_skepticism"].notna().sum())
    meta["skepticism_labeled_comments"] = int(merged["analysis_skepticism"].notna().sum())
    meta["proof_labeled_comments"] = int(merged["analysis_proof_demand"].notna().sum())
    return merged, meta


def _apply_label_source_runs(
    comments: pd.DataFrame,
    *,
    run_ids: tuple[int, ...],
    label_source: str,
    annotator_id: str | None,
    conn: sqlite3.Connection,
) -> tuple[pd.DataFrame, dict[str, object]]:
    prepared = _prepare_comment_rule_frame(comments)
    prepared["analysis_skepticism"] = prepared["rule_skepticism"]
    prepared["analysis_proof_demand"] = prepared["rule_proof_demand"]
    prepared["analysis_normalization"] = prepared["rule_normalization"]

    meta: dict[str, object] = {
        "label_source": label_source,
        "label_source_label": _label_source_label(label_source),
        "labeled_comments": int(len(prepared)),
        "skepticism_labeled_comments": int(len(prepared)),
        "proof_labeled_comments": int(len(prepared)),
    }
    if label_source == "rules":
        return prepared, meta

    labels = annotation_labels_runs_df(conn, run_ids, label_source, annotator_id)
    if labels.empty:
        prepared["analysis_skepticism"] = pd.Series([pd.NA] * len(prepared), dtype="Int64")
        prepared["analysis_proof_demand"] = pd.Series([pd.NA] * len(prepared), dtype="Int64")
        prepared["analysis_normalization"] = pd.Series([pd.NA] * len(prepared), dtype="Int64")
        meta["labeled_comments"] = 0
        meta["skepticism_labeled_comments"] = 0
        meta["proof_labeled_comments"] = 0
        return prepared, meta

    merged = prepared.merge(labels, on="comment_db_id", how="left")
    merged["analysis_skepticism"] = pd.to_numeric(merged["label_skepticism"], errors="coerce").astype("Int64")
    merged["analysis_proof_demand"] = pd.to_numeric(merged["label_proof_demand"], errors="coerce").astype("Int64")
    merged["analysis_normalization"] = pd.to_numeric(merged["label_normalization"], errors="coerce").astype("Int64")
    meta["labeled_comments"] = int(merged["analysis_skepticism"].notna().sum())
    meta["skepticism_labeled_comments"] = int(merged["analysis_skepticism"].notna().sum())
    meta["proof_labeled_comments"] = int(merged["analysis_proof_demand"].notna().sum())
    return merged, meta


@st.cache_data(ttl=20)
def conformity_frames(
    _conn: sqlite3.Connection,
    run_id: int,
    include_flagged: bool,
    label_source: str,
    annotator_id: str | None,
) -> dict[str, object]:
    comments = comments_df(_conn, run_id)
    if comments.empty:
        return {
            "error": "No comments available for selected run.",
            "input_df": pd.DataFrame(),
            "ranked_df": pd.DataFrame(),
            "response_df": pd.DataFrame(),
            "effects_df": pd.DataFrame(),
            "icc_df": pd.DataFrame(),
            "summary_df": pd.DataFrame(),
            "model_summary": "",
        }

    prepared, label_meta = _apply_label_source(
        comments,
        run_id=run_id,
        label_source=label_source,
        annotator_id=annotator_id,
        conn=_conn,
    )
    if not include_flagged:
        prepared = prepared[
            (prepared["is_spam"] == 0)
            & (prepared["is_template"] == 0)
            & (prepared["is_duplicate"] == 0)
        ].copy()

    input_df = prepared.rename(
        columns={
            "cleaned_text": "comment_text",
            "analysis_skepticism": "is_skeptical",
        }
    )[
        [
            "video_id",
            "channel_id",
            "channel_niche",
            "comment_text",
            "like_count",
            "comment_timestamp",
            "is_skeptical",
            "comment_rank",
            "reply_count",
            "run_id",
        ]
    ].copy()

    if input_df.empty:
        return {
            "error": "No comments left after active filters.",
            "input_df": input_df,
            "ranked_df": pd.DataFrame(),
            "response_df": pd.DataFrame(),
            "effects_df": pd.DataFrame(),
            "icc_df": pd.DataFrame(),
            "summary_df": pd.DataFrame(),
            "model_summary": "",
        }

    try:
        result = run_conformity_cascade(input_df)
    except Exception as exc:
        return {
            "error": str(exc),
            "input_df": input_df,
            "ranked_df": pd.DataFrame(),
            "response_df": pd.DataFrame(),
            "effects_df": pd.DataFrame(),
            "icc_df": pd.DataFrame(),
            "summary_df": pd.DataFrame(),
            "model_summary": "",
        }

    response_df = result.response_df.copy()
    skeptical_rate = response_df.loc[response_df["top_comment_skeptical"] == 1, "is_skeptical"].mean()
    nonskeptical_rate = response_df.loc[response_df["top_comment_skeptical"] == 0, "is_skeptical"].mean()
    h1_delta = (
        skeptical_rate - nonskeptical_rate
        if pd.notna(skeptical_rate) and pd.notna(nonskeptical_rate)
        else None
    )
    if "top_comment_like_count_z" in response_df.columns and len(response_df) > 1:
        skeptical_rows = response_df[response_df["top_comment_skeptical"] == 1]
        h2_corr = (
            skeptical_rows["top_comment_like_count_z"].corr(skeptical_rows["is_skeptical"])
            if len(skeptical_rows) > 1
            else None
        )
    else:
        h2_corr = None

    niche_effect = (
        response_df.groupby("channel_niche", as_index=False)
        .agg(
            response_comments=("video_id", "count"),
            skepticism_rate=("is_skeptical", "mean"),
            skeptical_cue_share=("top_comment_skeptical", "mean"),
        )
        .sort_values("channel_niche")
    )

    summary_df = pd.DataFrame(
        [
            {
                "run_id": int(run_id),
                "videos_ranked": int(result.ranked_df["video_id"].nunique()),
                "response_comments": int(len(response_df)),
                "skeptical_top_comment_videos": int(response_df.loc[response_df["top_comment_skeptical"] == 1, "video_id"].nunique()),
                "response_skepticism_after_skeptical_cue": skeptical_rate,
                "response_skepticism_after_non_skeptical_cue": nonskeptical_rate,
                "h1_delta_proxy": h1_delta,
                "h2_proxy_corr_within_skeptical_cue_videos": h2_corr,
                "label_source": _label_source_label(label_source),
                "labeled_comments": int(label_meta.get("labeled_comments", 0) or 0),
            }
        ]
    )

    return {
        "error": "",
        "input_df": input_df,
        "ranked_df": result.ranked_df,
        "response_df": response_df,
        "effects_df": result.effects_df,
        "icc_df": result.icc_df,
        "summary_df": summary_df,
        "niche_df": niche_effect,
        "model_summary": result.model_summary,
        "label_meta": label_meta,
    }


@st.cache_data(ttl=20)
def conformity_frames_multi(
    _conn: sqlite3.Connection,
    run_ids: tuple[int, ...],
    include_flagged: bool,
    label_source: str,
    annotator_id: str | None,
) -> dict[str, object]:
    if not run_ids:
        return {
            "error": "Select at least one run.",
            "input_df": pd.DataFrame(),
            "ranked_df": pd.DataFrame(),
            "response_df": pd.DataFrame(),
            "effects_df": pd.DataFrame(),
            "icc_df": pd.DataFrame(),
            "summary_df": pd.DataFrame(),
            "model_summary": "",
        }

    comments = comments_df(_conn)
    comments = comments[comments["run_id"].isin(list(run_ids))].copy()
    if comments.empty:
        return {
            "error": "No comments available for selected runs.",
            "input_df": pd.DataFrame(),
            "ranked_df": pd.DataFrame(),
            "response_df": pd.DataFrame(),
            "effects_df": pd.DataFrame(),
            "icc_df": pd.DataFrame(),
            "summary_df": pd.DataFrame(),
            "model_summary": "",
        }

    prepared, label_meta = _apply_label_source_runs(
        comments,
        run_ids=run_ids,
        label_source=label_source,
        annotator_id=annotator_id,
        conn=_conn,
    )
    if not include_flagged:
        prepared = prepared[
            (prepared["is_spam"] == 0)
            & (prepared["is_template"] == 0)
            & (prepared["is_duplicate"] == 0)
        ].copy()

    input_df = prepared.rename(
        columns={
            "cleaned_text": "comment_text",
            "analysis_skepticism": "is_skeptical",
        }
    )[
        [
            "video_id",
            "channel_id",
            "channel_niche",
            "comment_text",
            "like_count",
            "comment_timestamp",
            "is_skeptical",
            "comment_rank",
            "reply_count",
            "run_id",
        ]
    ].copy()

    if input_df.empty:
        return {
            "error": "No comments left after active filters.",
            "input_df": input_df,
            "ranked_df": pd.DataFrame(),
            "response_df": pd.DataFrame(),
            "effects_df": pd.DataFrame(),
            "icc_df": pd.DataFrame(),
            "summary_df": pd.DataFrame(),
            "model_summary": "",
        }

    try:
        result = run_conformity_cascade(input_df)
    except Exception as exc:
        return {
            "error": str(exc),
            "input_df": input_df,
            "ranked_df": pd.DataFrame(),
            "response_df": pd.DataFrame(),
            "effects_df": pd.DataFrame(),
            "icc_df": pd.DataFrame(),
            "summary_df": pd.DataFrame(),
            "model_summary": "",
            "label_meta": label_meta,
        }

    response_df = result.response_df.copy()
    skeptical_rate = response_df.loc[response_df["top_comment_skeptical"] == 1, "is_skeptical"].mean()
    nonskeptical_rate = response_df.loc[response_df["top_comment_skeptical"] == 0, "is_skeptical"].mean()
    h1_delta = (
        skeptical_rate - nonskeptical_rate
        if pd.notna(skeptical_rate) and pd.notna(nonskeptical_rate)
        else None
    )
    if "top_comment_like_count_z" in response_df.columns and len(response_df) > 1:
        skeptical_rows = response_df[response_df["top_comment_skeptical"] == 1]
        h2_corr = (
            skeptical_rows["top_comment_like_count_z"].corr(skeptical_rows["is_skeptical"])
            if len(skeptical_rows) > 1
            else None
        )
    else:
        h2_corr = None

    niche_effect = (
        response_df.groupby("channel_niche", as_index=False)
        .agg(
            response_comments=("video_id", "count"),
            skepticism_rate=("is_skeptical", "mean"),
            skeptical_cue_share=("top_comment_skeptical", "mean"),
        )
        .sort_values("channel_niche")
    )

    summary_df = pd.DataFrame(
        [
            {
                "run_scope": ", ".join(str(x) for x in run_ids),
                "videos_ranked": int(result.ranked_df["video_id"].nunique()),
                "response_comments": int(len(response_df)),
                "skeptical_top_comment_videos": int(response_df.loc[response_df["top_comment_skeptical"] == 1, "video_id"].nunique()),
                "response_skepticism_after_skeptical_cue": skeptical_rate,
                "response_skepticism_after_non_skeptical_cue": nonskeptical_rate,
                "h1_delta_proxy": h1_delta,
                "h2_proxy_corr_within_skeptical_cue_videos": h2_corr,
                "label_source": _label_source_label(label_source),
                "labeled_comments": int(label_meta.get("labeled_comments", 0) or 0),
            }
        ]
    )

    return {
        "error": "",
        "input_df": input_df,
        "ranked_df": result.ranked_df,
        "response_df": response_df,
        "effects_df": result.effects_df,
        "icc_df": result.icc_df,
        "summary_df": summary_df,
        "niche_df": niche_effect,
        "model_summary": result.model_summary,
        "label_meta": label_meta,
    }


def authenticate(users: dict[str, str]) -> tuple[bool, str | None]:
    remembered_user = _load_remembered_login()
    if not st.session_state.get("auth_ok") and remembered_user and remembered_user in users:
        st.session_state["auth_ok"] = True
        st.session_state["annotator_id"] = remembered_user

    auth_ok = bool(st.session_state.get("auth_ok", False))
    annotator_id = _safe_text(st.session_state.get("annotator_id")).strip() or None
    with st.sidebar:
        st.header("Login")
        if auth_ok and annotator_id:
            st.caption(f"Signed in as `{annotator_id}`.")
            if remembered_user == annotator_id:
                st.caption("This device is set to keep you signed in.")
            if st.button("Sign out", use_container_width=True):
                st.session_state["auth_ok"] = False
                st.session_state["annotator_id"] = ""
                _clear_remembered_login()
                st.rerun()
        else:
            st.caption("Use your local annotator account to enter the coding and analysis workspace.")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            remember_me = st.checkbox("Keep me signed in on this machine", value=True)
            if st.button("Sign in", use_container_width=True):
                if users.get(username) == password:
                    st.session_state["auth_ok"] = True
                    st.session_state["annotator_id"] = username
                    if remember_me:
                        _save_remembered_login(username)
                    else:
                        _clear_remembered_login()
                    st.rerun()
                else:
                    st.session_state["auth_ok"] = False
                    st.error("Invalid credentials")

    return auth_ok, annotator_id


def _parse_extra_codes(value: object) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(x) for x in parsed if str(x).strip()]
    except json.JSONDecodeError:
        pass
    return [x.strip() for x in text.split("|") if x.strip()]


def _bool01(value: object, default: int = 0) -> int:
    if value is None or pd.isna(value):
        return int(default)
    return 1 if int(value) == 1 else 0


def _optional_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    text = _safe_text(value).strip()
    if not text:
        return None
    return float(value)


def _triage_comment_uncertainty(text: object) -> tuple[str, float, list[str]]:
    raw = _safe_text(text).strip()
    if not raw:
        return ("unsure", 1.0, ["empty_text"])

    hints: list[str] = []
    weak_hits = 0
    strong_hits = 0

    if SKEPTICISM_REGEX.search(raw):
        weak_hits += 1
        hints.append("skepticism")
    if PROOF_DEMAND_REGEX.search(raw):
        weak_hits += 1
        hints.append("proof_demand")
    if NORMALIZATION_REGEX.search(raw):
        weak_hits += 1
        hints.append("normalization")

    if SKEPTICISM_STRONG_REGEX.search(raw):
        strong_hits += 1
        hints.append("strong_skepticism")
    if PROOF_DEMAND_STRONG_REGEX.search(raw):
        strong_hits += 1
        hints.append("strong_proof_demand")
    if NORMALIZATION_STRONG_REGEX.search(raw):
        strong_hits += 1
        hints.append("strong_normalization")

    if strong_hits == 1 and weak_hits == 1:
        bucket, score = "obvious", 0.10
    elif strong_hits >= 2 or weak_hits >= 2:
        bucket, score = "mixed", 0.45
    elif weak_hits == 1:
        bucket, score = "medium", 0.60
    else:
        bucket, score = "unsure", 0.90

    if len(raw) > 240:
        score = min(1.0, score + 0.05)
        hints.append("long_text")
    if "?" in raw and weak_hits == 0 and strong_hits == 0:
        score = min(1.0, score + 0.05)
        hints.append("question_without_keyword")

    return (bucket, score, hints)


def _extract_regex_hits(regex: re.Pattern[str], text: object, *, max_hits: int = 4) -> list[str]:
    raw = _safe_text(text)
    if not raw:
        return []
    hits: list[str] = []
    seen: set[str] = set()
    for match in regex.finditer(raw):
        hit = _safe_text(match.group(0)).strip()
        normalized = hit.lower()
        if not hit or normalized in seen:
            continue
        hits.append(hit)
        seen.add(normalized)
        if len(hits) >= max_hits:
            break
    return hits


def _build_signal_trace(
    *,
    comment_text: object,
    title: object = "",
    description: object = "",
    triage_bucket: str = "",
    triage_score: float = 0.0,
    triage_hints: list[str] | None = None,
    top_rule_skepticism: int = 0,
    comment_rank: int = 0,
) -> dict[str, object]:
    comment_text = _safe_text(comment_text)
    title = _safe_text(title)
    description = _safe_text(description)
    combined = (title + " " + description).strip()
    text_features = analyze_comment_text_features(comment_text)

    skepticism_hits = _extract_regex_hits(SKEPTICISM_REGEX, comment_text)
    proof_hits = _extract_regex_hits(PROOF_DEMAND_REGEX, comment_text)
    normalization_hits = _extract_regex_hits(NORMALIZATION_REGEX, comment_text)
    comment_ai_hits = _extract_regex_hits(AI_MENTION_REGEX, comment_text)
    video_ai_hits = _extract_regex_hits(AI_MENTION_REGEX, combined)
    disclosure_level = _infer_disclosure_level(combined)
    disclosure_label = _disclosure_label(disclosure_level)

    suggested_labels: list[str] = []
    if skepticism_hits:
        suggested_labels.append("skepticism")
    if proof_hits:
        suggested_labels.append("proof-demand")
    if normalization_hits:
        suggested_labels.append("normalization")

    context_bits: list[str] = []
    if int(top_rule_skepticism or 0) == 1 and int(comment_rank or 0) > 1:
        context_bits.append("response under skeptical top cue")
    if comment_ai_hits:
        context_bits.append("AI mention in comment")
    elif video_ai_hits:
        context_bits.append("AI mention in video")
    if disclosure_level > 0:
        context_bits.append(f"video disclosure {disclosure_label}")
    heuristic_language = _safe_text(text_features.get("heuristic_language"))
    if heuristic_language and heuristic_language not in {"english_or_other_latin", "empty"}:
        context_bits.append(f"language {heuristic_language}")
    if int(text_features.get("low_info_noise") or 0) == 1:
        context_bits.append("low-info/noise")
    if triage_bucket:
        context_bits.append(f"triage {triage_bucket} ({float(triage_score):.2f})")

    summary_parts: list[str] = []
    if suggested_labels:
        summary_parts.append("labels: " + ", ".join(suggested_labels))
    if context_bits:
        summary_parts.append("context: " + "; ".join(context_bits))
    if not summary_parts:
        summary_parts.append("no rule hits; surfaced for coverage")

    return {
        "suggested_labels": suggested_labels,
        "skepticism_hits": skepticism_hits,
        "proof_hits": proof_hits,
        "normalization_hits": normalization_hits,
        "comment_ai_hits": comment_ai_hits,
        "video_ai_hits": video_ai_hits,
        "disclosure_label": disclosure_label,
        "heuristic_language": heuristic_language,
        "low_info_noise": int(text_features.get("low_info_noise") or 0),
        "lex_certainty": int(text_features.get("lex_certainty") or 0),
        "lex_doubt": int(text_features.get("lex_doubt") or 0),
        "lex_negation": int(text_features.get("lex_negation") or 0),
        "lex_request": int(text_features.get("lex_request") or 0),
        "lex_affect": int(text_features.get("lex_affect") or 0),
        "lex_social": int(text_features.get("lex_social") or 0),
        "context_bits": context_bits,
        "summary": " | ".join(summary_parts),
        "triage_hints": triage_hints or [],
    }


def _human_override_summary(
    *,
    auto_labels: list[str],
    skepticism_value: bool,
    proof_value: bool,
    normalization_value: bool,
) -> str:
    auto_map = {
        "skepticism": "skepticism" in auto_labels,
        "proof-demand": "proof-demand" in auto_labels,
        "normalization": "normalization" in auto_labels,
    }
    human_map = {
        "skepticism": bool(skepticism_value),
        "proof-demand": bool(proof_value),
        "normalization": bool(normalization_value),
    }
    overrides: list[str] = []
    for key in ["skepticism", "proof-demand", "normalization"]:
        if auto_map[key] != human_map[key]:
            overrides.append(f"{key} auto={int(auto_map[key])} human={int(human_map[key])}")
    return ", ".join(overrides) if overrides else "human labels align with current auto hints"


def _annotation_priority_details(
    *,
    triage_bucket: str,
    triage_score: float,
    triage_hints: list[str],
    comment_ai_signal: bool,
    video_ai_signal: bool,
    top_rule_skepticism: int,
    comment_rank: int,
    like_count: int,
    reply_count: int,
    priority_mode: str,
) -> tuple[str, float, str]:
    weak_signal_hits = len([hint for hint in triage_hints if hint in {"skepticism", "proof_demand", "normalization"}])
    strong_signal_hits = len([hint for hint in triage_hints if hint.startswith("strong_")])
    high_uncertainty = triage_bucket in {"mixed", "unsure"} or float(triage_score) >= 0.75
    response_under_skeptical_top = int(top_rule_skepticism or 0) == 1 and int(comment_rank or 0) > 1
    ai_context = bool(comment_ai_signal) or bool(video_ai_signal)
    engagement = min(1.0, (max(int(like_count or 0), 0) + 3 * max(int(reply_count or 0), 0)) / 5000.0)

    if response_under_skeptical_top:
        bucket = "Skeptical-cue response"
    elif strong_signal_hits >= 1 or weak_signal_hits >= 2 or triage_bucket == "mixed":
        bucket = "Ambiguous signal"
    elif ai_context:
        bucket = "AI-context review"
    elif high_uncertainty:
        bucket = "Uncertain discovery"
    else:
        bucket = "Coverage fill"

    if priority_mode == "signal_first":
        score = (
            0.85 * min(2, weak_signal_hits) / 2
            + 0.80 * min(2, strong_signal_hits) / 2
            + 0.55 * float(response_under_skeptical_top)
            + 0.35 * float(ai_context)
            + 0.20 * float(triage_score)
            + 0.10 * engagement
        )
    elif priority_mode == "coverage_first":
        score = (
            0.70 * float(triage_score)
            + 0.20 * float(ai_context)
            + 0.15 * engagement
            + 0.15 * float(response_under_skeptical_top)
        )
    elif priority_mode == "triage_only":
        score = float(triage_score)
    else:
        score = (
            0.75 * float(triage_score)
            + 0.45 * min(2, weak_signal_hits) / 2
            + 0.35 * min(2, strong_signal_hits) / 2
            + 0.35 * float(ai_context)
            + 0.30 * float(response_under_skeptical_top)
            + 0.10 * engagement
        )

    reasons: list[str] = []
    if strong_signal_hits:
        reasons.append("strong rule hit")
    elif weak_signal_hits:
        reasons.append("rule hint")
    if high_uncertainty:
        reasons.append("high uncertainty")
    if response_under_skeptical_top:
        reasons.append("under skeptical top cue")
    if comment_ai_signal:
        reasons.append("AI mention in comment")
    elif video_ai_signal:
        reasons.append("AI mention in video")
    if engagement >= 0.35:
        reasons.append("higher engagement")
    if not reasons:
        reasons.append("coverage candidate")

    return (bucket, round(float(score), 3), ", ".join(reasons))


def _apply_diversity_caps(
    df: pd.DataFrame,
    *,
    max_per_video: int,
    max_per_channel: int,
) -> pd.DataFrame:
    if df.empty or (max_per_video <= 0 and max_per_channel <= 0):
        return df

    keep_rows: list[int] = []
    video_counts: dict[str, int] = {}
    channel_counts: dict[str, int] = {}

    for idx, row in df.iterrows():
        video_id = _safe_text(row.get("video_id"))
        channel_id = _safe_text(row.get("channel_id"))
        if max_per_video > 0 and video_counts.get(video_id, 0) >= int(max_per_video):
            continue
        if max_per_channel > 0 and channel_counts.get(channel_id, 0) >= int(max_per_channel):
            continue
        keep_rows.append(idx)
        video_counts[video_id] = video_counts.get(video_id, 0) + 1
        channel_counts[channel_id] = channel_counts.get(channel_id, 0) + 1

    return df.loc[keep_rows].copy()


def _clear_post_annotation_caches() -> None:
    for fn in [
        annotation_queue_df,
        resolved_consensus_run_ids,
        evidence_base_snapshot,
        annotation_workflow_metrics,
        uncoded_extension_frames,
        build_final_analysis_pack,
        conformity_frames,
        conformity_frames_multi,
    ]:
        clear_fn = getattr(fn, "clear", None)
        if callable(clear_fn):
            clear_fn()


def save_annotation(
    conn: sqlite3.Connection,
    comment_db_id: int,
    annotator_id: str,
    skepticism: int,
    proof_demand: int,
    normalization: int,
    extra_codes: list[str] | None = None,
    other_flag: int = 0,
    other_text: str = "",
    is_adjudicated: int = 0,
    workflow_mode: str = "",
    triage_bucket: str = "",
    triage_score: float | None = None,
    priority_bucket: str = "",
    priority_score: float | None = None,
    heuristic_language: str = "",
    low_info_noise: int = 0,
    comment_ai_signal: int = 0,
    video_ai_signal: int = 0,
    was_disagreement_detected: int | None = None,
    resolution_source: str = "",
    adjudication_note: str = "",
) -> None:
    now = datetime.now(tz=timezone.utc).isoformat()
    extra_codes_json = json.dumps(sorted(set(extra_codes or [])), ensure_ascii=True)
    conn.execute(
        """
        INSERT INTO annotations (
            comment_db_id,
            annotator_id,
            coded_at,
            skepticism_fake_callout,
            proof_demand,
            normalization_defense,
            extra_codes,
            other_flag,
            other_text,
            is_adjudicated,
            workflow_mode,
            triage_bucket,
            triage_score,
            priority_bucket,
            priority_score,
            heuristic_language,
            low_info_noise,
            comment_ai_signal,
            video_ai_signal,
            was_disagreement_detected,
            resolution_source,
            adjudication_note,
            adjudicated_at,
            pre_adjudication_skepticism,
            pre_adjudication_proof_demand,
            pre_adjudication_normalization
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(comment_db_id, annotator_id)
        DO UPDATE SET
            coded_at = excluded.coded_at,
            skepticism_fake_callout = excluded.skepticism_fake_callout,
            proof_demand = excluded.proof_demand,
            normalization_defense = excluded.normalization_defense,
            extra_codes = excluded.extra_codes,
            other_flag = excluded.other_flag,
            other_text = excluded.other_text,
            workflow_mode = excluded.workflow_mode,
            triage_bucket = excluded.triage_bucket,
            triage_score = excluded.triage_score,
            priority_bucket = excluded.priority_bucket,
            priority_score = excluded.priority_score,
            heuristic_language = excluded.heuristic_language,
            low_info_noise = excluded.low_info_noise,
            comment_ai_signal = excluded.comment_ai_signal,
            video_ai_signal = excluded.video_ai_signal,
            was_disagreement_detected = COALESCE(excluded.was_disagreement_detected, annotations.was_disagreement_detected),
            resolution_source = CASE
                WHEN excluded.is_adjudicated = 1 THEN COALESCE(NULLIF(excluded.resolution_source, ''), annotations.resolution_source, 'manual_adjudication')
                ELSE annotations.resolution_source
            END,
            adjudication_note = CASE
                WHEN excluded.is_adjudicated = 1 AND NULLIF(excluded.adjudication_note, '') IS NOT NULL THEN excluded.adjudication_note
                ELSE annotations.adjudication_note
            END,
            adjudicated_at = CASE
                WHEN excluded.is_adjudicated = 1 THEN COALESCE(annotations.adjudicated_at, excluded.adjudicated_at, excluded.coded_at)
                ELSE annotations.adjudicated_at
            END,
            pre_adjudication_skepticism = CASE
                WHEN excluded.is_adjudicated = 1 AND annotations.is_adjudicated = 0 THEN COALESCE(annotations.pre_adjudication_skepticism, annotations.skepticism_fake_callout)
                ELSE annotations.pre_adjudication_skepticism
            END,
            pre_adjudication_proof_demand = CASE
                WHEN excluded.is_adjudicated = 1 AND annotations.is_adjudicated = 0 THEN COALESCE(annotations.pre_adjudication_proof_demand, annotations.proof_demand)
                ELSE annotations.pre_adjudication_proof_demand
            END,
            pre_adjudication_normalization = CASE
                WHEN excluded.is_adjudicated = 1 AND annotations.is_adjudicated = 0 THEN COALESCE(annotations.pre_adjudication_normalization, annotations.normalization_defense)
                ELSE annotations.pre_adjudication_normalization
            END,
            is_adjudicated = CASE
                WHEN annotations.is_adjudicated = 1 THEN 1
                ELSE excluded.is_adjudicated
            END
        """,
        (
            comment_db_id,
            annotator_id,
            now,
            skepticism,
            proof_demand,
            normalization,
            extra_codes_json,
            int(other_flag),
            _safe_text(other_text).strip(),
            int(is_adjudicated),
            _safe_text(workflow_mode),
            _safe_text(triage_bucket),
            _optional_float(triage_score),
            _safe_text(priority_bucket),
            _optional_float(priority_score),
            _safe_text(heuristic_language),
            _bool01(low_info_noise),
            _bool01(comment_ai_signal),
            _bool01(video_ai_signal),
            _bool01(was_disagreement_detected) if was_disagreement_detected is not None else None,
            _safe_text(resolution_source),
            _safe_text(adjudication_note).strip(),
            now if int(is_adjudicated) else None,
            None,
            None,
            None,
        ),
    )
    conn.commit()
    _clear_post_annotation_caches()


def save_annotations_batch(conn: sqlite3.Connection, rows: list[dict[str, object]]) -> int:
    if not rows:
        return 0

    now = datetime.now(tz=timezone.utc).isoformat()
    payload = []
    for row in rows:
        payload.append(
            (
                int(row["comment_db_id"]),
                str(row["annotator_id"]),
                now,
                _bool01(row.get("skepticism")),
                _bool01(row.get("proof_demand")),
                _bool01(row.get("normalization")),
                json.dumps(sorted(set([str(x) for x in row.get("extra_codes", [])])), ensure_ascii=True),
                _bool01(row.get("other_flag")),
                _safe_text(row.get("other_text")).strip(),
                _bool01(row.get("is_adjudicated")),
                _safe_text(row.get("workflow_mode")),
                _safe_text(row.get("triage_bucket")),
                _optional_float(row.get("triage_score")),
                _safe_text(row.get("priority_bucket")),
                _optional_float(row.get("priority_score")),
                _safe_text(row.get("heuristic_language")),
                _bool01(row.get("low_info_noise")),
                _bool01(row.get("comment_ai_signal")),
                _bool01(row.get("video_ai_signal")),
                _bool01(row.get("was_disagreement_detected")) if row.get("was_disagreement_detected") is not None else None,
                _safe_text(row.get("resolution_source")),
                _safe_text(row.get("adjudication_note")).strip(),
                now if _bool01(row.get("is_adjudicated")) else None,
                None,
                None,
                None,
            )
        )

    conn.executemany(
        """
        INSERT INTO annotations (
            comment_db_id,
            annotator_id,
            coded_at,
            skepticism_fake_callout,
            proof_demand,
            normalization_defense,
            extra_codes,
            other_flag,
            other_text,
            is_adjudicated,
            workflow_mode,
            triage_bucket,
            triage_score,
            priority_bucket,
            priority_score,
            heuristic_language,
            low_info_noise,
            comment_ai_signal,
            video_ai_signal,
            was_disagreement_detected,
            resolution_source,
            adjudication_note,
            adjudicated_at,
            pre_adjudication_skepticism,
            pre_adjudication_proof_demand,
            pre_adjudication_normalization
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(comment_db_id, annotator_id)
        DO UPDATE SET
            coded_at = excluded.coded_at,
            skepticism_fake_callout = excluded.skepticism_fake_callout,
            proof_demand = excluded.proof_demand,
            normalization_defense = excluded.normalization_defense,
            extra_codes = excluded.extra_codes,
            other_flag = excluded.other_flag,
            other_text = excluded.other_text,
            workflow_mode = excluded.workflow_mode,
            triage_bucket = excluded.triage_bucket,
            triage_score = excluded.triage_score,
            priority_bucket = excluded.priority_bucket,
            priority_score = excluded.priority_score,
            heuristic_language = excluded.heuristic_language,
            low_info_noise = excluded.low_info_noise,
            comment_ai_signal = excluded.comment_ai_signal,
            video_ai_signal = excluded.video_ai_signal,
            was_disagreement_detected = COALESCE(excluded.was_disagreement_detected, annotations.was_disagreement_detected),
            resolution_source = CASE
                WHEN excluded.is_adjudicated = 1 THEN COALESCE(NULLIF(excluded.resolution_source, ''), annotations.resolution_source, 'manual_adjudication')
                ELSE annotations.resolution_source
            END,
            adjudication_note = CASE
                WHEN excluded.is_adjudicated = 1 AND NULLIF(excluded.adjudication_note, '') IS NOT NULL THEN excluded.adjudication_note
                ELSE annotations.adjudication_note
            END,
            adjudicated_at = CASE
                WHEN excluded.is_adjudicated = 1 THEN COALESCE(annotations.adjudicated_at, excluded.adjudicated_at, excluded.coded_at)
                ELSE annotations.adjudicated_at
            END,
            pre_adjudication_skepticism = CASE
                WHEN excluded.is_adjudicated = 1 AND annotations.is_adjudicated = 0 THEN COALESCE(annotations.pre_adjudication_skepticism, annotations.skepticism_fake_callout)
                ELSE annotations.pre_adjudication_skepticism
            END,
            pre_adjudication_proof_demand = CASE
                WHEN excluded.is_adjudicated = 1 AND annotations.is_adjudicated = 0 THEN COALESCE(annotations.pre_adjudication_proof_demand, annotations.proof_demand)
                ELSE annotations.pre_adjudication_proof_demand
            END,
            pre_adjudication_normalization = CASE
                WHEN excluded.is_adjudicated = 1 AND annotations.is_adjudicated = 0 THEN COALESCE(annotations.pre_adjudication_normalization, annotations.normalization_defense)
                ELSE annotations.pre_adjudication_normalization
            END,
            is_adjudicated = CASE
                WHEN annotations.is_adjudicated = 1 THEN 1
                ELSE excluded.is_adjudicated
            END
        """,
        payload,
    )
    conn.commit()
    _clear_post_annotation_caches()
    return len(payload)


def overview_tab(conn: sqlite3.Connection) -> None:
    df = run_df(conn)
    render_section_intro(
        "System snapshot",
        "Batch overview",
        "Use this page as the control-room view: latest run health, overall collection momentum, and the full run log in one place.",
    )
    if df.empty:
        st.info("No runs yet. Execute a batch from CLI first.")
        return

    latest = df.iloc[0]
    render_metric_tiles(
        [
            {"label": "Latest run", "value": int(latest["id"]), "note": _safe_text(latest["ended_at"]) or "active", "tone": "accent"},
            {"label": "Run status", "value": _safe_text(latest["status"]) or "unknown", "note": _safe_text(latest["execution_mode"]) or "mode n/a", "tone": "sage"},
            {"label": "API units", "value": int(latest["api_units_used"] or 0), "note": "latest batch consumption", "tone": "gold"},
            {"label": "Total runs", "value": len(df), "note": "history currently loaded", "tone": "accent"},
        ]
    )
    render_note_banner(
        "Read",
        f"Run {int(latest['id'])} is the newest batch. Status is {_safe_text(latest['status']) or 'unknown'} and truncation is {'on' if int(latest['run_truncated'] or 0) else 'off'}.",
    )

    st.dataframe(df, use_container_width=True)


def run_lab_tab(conn: sqlite3.Connection, config, annotator_id: str) -> None:
    render_section_intro(
        "Collection studio",
        "Run lab",
        "Inspect prior runs, preserve reusable study profiles, and launch new scrape jobs from a cleaner planning surface.",
    )
    st.session_state.setdefault("runlab_show_uncoded_extension", False)
    st.session_state.setdefault("runlab_show_final_analysis_pack", False)
    st.session_state.setdefault("runlab_extension_include_flagged", False)
    feedback = st.session_state.pop("runlab_feedback", None)
    if isinstance(feedback, dict):
        level = _safe_text(feedback.get("level")) or "success"
        message = _safe_text(feedback.get("message"))
        if message:
            getattr(st, level if level in {"success", "warning", "info", "error"} else "success")(message)

    target_files = _list_target_csv_files()
    _seed_runlab_state(config, target_files)

    quick_plan = _quick_workflow_plan(conn, annotator_id)
    st.markdown("**Quick workflow**")
    render_note_banner(
        _safe_text(quick_plan.get("title")) or "Next step",
        _safe_text(quick_plan.get("body")),
    )
    qp1, qp2 = st.columns(2)
    qp1.info(_safe_text(quick_plan.get("next_step")) or "Inspect the latest state and continue.")
    qp2.caption(f"After that: {_safe_text(quick_plan.get('after_that')) or 'Keep moving through the core workflow.'}")
    qa1, qa2 = st.columns(2)
    latest_run_id = quick_plan.get("latest_run_id")
    if latest_run_id is not None and qa1.button("Inspect Latest Run", key="runlab_quick_inspect_latest", use_container_width=True):
        st.session_state["runlab_inspect_run"] = int(latest_run_id)
        st.rerun()
    if quick_plan.get("show_smoke_button") and qa2.button(
        "Load Safe Smoke-Test Setup",
        key="runlab_quick_safe_smoke",
        use_container_width=True,
    ):
        preferred_target = "data/targets_with_identifiers.csv"
        if preferred_target in target_files:
            st.session_state["runlab_target_file"] = preferred_target
        elif target_files:
            st.session_state["runlab_target_file"] = target_files[0]
        st.session_state["runlab_simulate"] = True
        st.session_state["runlab_content"] = "videos"
        st.session_state["runlab_channel_limit"] = 1
        st.session_state["runlab_videos_per_channel"] = 2
        st.session_state["runlab_min_expected"] = 2
        st.session_state["runlab_active_profile_name"] = ""
        st.rerun()
    qb1, qb2 = st.columns(2)
    if qb1.button("Run Safe Smoke Test Now", key="runlab_quick_run_safe_smoke", use_container_width=True):
        try:
            with st.spinner("Running a built-in safe smoke test..."):
                run_id = _launch_safe_smoke_run(conn, config, target_files)
            _clear_cached_frames()
            st.session_state["runlab_inspect_run"] = int(run_id)
            st.session_state["runlab_feedback"] = {
                "level": "success",
                "message": f"Safe smoke test completed. New run_id={run_id}",
            }
            st.rerun()
        except Exception as exc:
            st.error(f"Safe smoke test failed: {exc}")
    qb2.caption("This bypasses the form and always runs a tiny simulated batch with a known-safe setup.")
    corpus_summary = corpus_overview_snapshot(conn)
    screened_comments = screened_corpus_count(conn)
    all_resolved_runs = resolved_consensus_run_ids(conn)
    freeze_library = evidence_freezes_df(conn, annotator_id)
    latest_freeze_payload = _evidence_freeze_payload_from_row(freeze_library.iloc[0]) if not freeze_library.empty else {}
    all_resolved_snapshot = evidence_base_snapshot(conn, all_resolved_runs)
    all_labeled_summary = labeled_comment_summary(conn, all_resolved_runs)
    st.markdown("**Workflow overview**")
    render_note_banner(
        "Research pipeline",
        "Collection, preprocessing, screening, coding, adjudication, freeze creation, and analysis remain in one auditable workflow.",
    )
    st.dataframe(
        workflow_overview_table(
            corpus_summary,
            all_labeled_summary,
            all_resolved_snapshot,
            screened_comments=screened_comments,
            freeze_count=len(freeze_library),
            latest_freeze_name=_safe_text(latest_freeze_payload.get("name")),
            latest_freeze_date=_safe_text(latest_freeze_payload.get("created_at")),
        ),
        use_container_width=True,
        height=320,
    )
    st.divider()

    st.markdown("**Study Profiles**")
    profiles = study_profiles_df(conn, annotator_id)
    if profiles.empty:
        st.info("No saved profiles yet for this user.")
    else:
        profile_options = profiles["id"].tolist()
        selected_profile_id = st.selectbox(
            "Saved profiles",
            options=profile_options,
            format_func=lambda pid: f"{profiles.loc[profiles['id'] == pid, 'name'].iloc[0]} (id={pid})",
            key="runlab_profile_select",
        )
        p_row = profiles[profiles["id"] == selected_profile_id].iloc[0]
        c1, c2 = st.columns(2)
        if c1.button("Load Profile", key="runlab_profile_load", use_container_width=True):
            try:
                payload = json.loads(_safe_text(p_row["profile_json"]) or "{}")
                _apply_runlab_payload(payload, target_files)
                st.session_state["runlab_active_profile_name"] = _safe_text(p_row["name"])
                st.success(f"Loaded profile: {_safe_text(p_row['name'])}")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to load profile: {exc}")
        if c2.button("Delete Profile", key="runlab_profile_delete", use_container_width=True):
            delete_study_profile(conn, owner=annotator_id, profile_id=int(selected_profile_id))
            study_profiles_df.clear()
            if _safe_text(st.session_state.get("runlab_active_profile_name")) == _safe_text(p_row["name"]):
                st.session_state["runlab_active_profile_name"] = ""
            st.success("Profile deleted.")
            st.rerun()
        st.caption(f"Description: {_safe_text(p_row['description']) or '(none)'}")
    active_profile_name = _safe_text(st.session_state.get("runlab_active_profile_name"))
    if active_profile_name:
        st.caption(f"Active profile snapshot for new runs: `{active_profile_name}`")

    with st.form("runlab_profile_save_form"):
        p1, p2 = st.columns([2, 3])
        profile_name = p1.text_input("Profile name", value="", placeholder="e.g. videos_tech_beauty_h1")
        profile_desc = p2.text_input(
            "Profile description",
            value="",
            placeholder="What idea/hypothesis this profile is for",
        )
        profile_saved = st.form_submit_button("Save Current Settings as Profile", use_container_width=True)
    if profile_saved:
        if not profile_name.strip():
            st.error("Profile name is required.")
        else:
            payload = _current_runlab_payload()
            upsert_study_profile(
                conn,
                owner=annotator_id,
                name=profile_name.strip(),
                description=profile_desc.strip(),
                payload=payload,
            )
            study_profiles_df.clear()
            st.session_state["runlab_active_profile_name"] = profile_name.strip()
            st.success(f"Saved profile: {profile_name.strip()}")
            st.rerun()

    with st.expander("Codebook And Reproducibility", expanded=False):
        st.markdown("**Extra Codebook Tags**")
        codebook_payload = load_codebook_config(str(CODEBOOK_PATH))
        custom_code_rows = codebook_payload.get("extra_codes", [])
        default_df = pd.DataFrame(DEFAULT_EXTRA_CODE_OPTIONS, columns=["code", "label"])
        st.caption("Default tags are fixed. Custom tags below are project-specific and editable.")
        st.dataframe(default_df, use_container_width=True, height=180)

        if custom_code_rows:
            custom_df = pd.DataFrame(custom_code_rows)
            st.markdown("**Custom Tags**")
            st.dataframe(custom_df, use_container_width=True, height=min(240, 35 * len(custom_df) + 40))
            for item in custom_code_rows:
                code = _safe_text(item.get("code"))
                label = _safe_text(item.get("label"))
                if st.button(f"Delete `{label}`", key=f"codebook_delete_{code}", use_container_width=True):
                    updated = [row for row in custom_code_rows if _safe_text(row.get("code")) != code]
                    save_codebook_config(str(CODEBOOK_PATH), {"extra_codes": updated})
                    load_codebook_config.clear()
                    st.success(f"Deleted custom tag: {label}")
                    st.rerun()
        else:
            st.info("No custom tags yet.")

        with st.form("codebook_add_custom_tag_form"):
            cb1, cb2 = st.columns([2, 1])
            custom_label = cb1.text_input("Custom tag label", placeholder="e.g. disclosure_request")
            custom_code = cb2.text_input("Custom tag code (optional)", placeholder="auto from label")
            add_custom_tag = st.form_submit_button("Add Custom Tag", use_container_width=True)
        if add_custom_tag:
            label = _safe_text(custom_label).strip()
            code = _slugify_code_id(_safe_text(custom_code).strip() or label)
            taken_codes = set(_extra_code_ids(extra_code_options()))
            if not label:
                st.error("Custom tag label is required.")
            elif code in taken_codes:
                st.error(f"Tag code `{code}` already exists.")
            else:
                updated = list(custom_code_rows) + [{"code": code, "label": label}]
                save_codebook_config(str(CODEBOOK_PATH), {"extra_codes": updated})
                load_codebook_config.clear()
                st.success(f"Added custom tag: {label}")
                st.rerun()

        st.divider()
        st.markdown("**Reproducibility Bundle**")
        bundle = build_reproducibility_bundle(conn, annotator_id)
        st.caption("Exports current scrape settings, codebook, key session selections, and annotation stats.")
        st.download_button(
            "Download Research Bundle JSON",
            data=json.dumps(bundle, ensure_ascii=True, indent=2).encode("utf-8"),
            file_name=f"research_bundle_{annotator_id}_{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
            mime="application/json",
            use_container_width=True,
        )
        st.markdown("**Deterministic logic registry**")
        st.dataframe(pd.DataFrame(_logic_summary_rows()), use_container_width=True, height=280)
        with st.expander("Ethics and reproducibility note", expanded=False):
            st.markdown(
                "\n".join(
                    [
                        "- Public platform comments are handled as research material, but paper-facing exports should avoid unnecessary user-identifying detail.",
                        "- The frozen evidence base is a scoped reproducibility artifact: it locks the selected runs, resolved labels, and prevalence tables used for the main claims.",
                        "- Assistive heuristics and weak labels support screening and prioritization, but they do not expand the confirmatory evidence layer.",
                        "- Named freezes, research bundles, and final-pack exports are the recommended audit trail for reporting and later verification.",
                    ]
                )
            )

    with st.expander("Evidence Freeze, Extension, And Final Pack", expanded=True):
        st.markdown("**Step 1. Freeze The Main Evidence Base**")
        render_evidence_boundary_banner(
            "Validated evidence layer",
            "Use this step to define the frozen resolved-consensus evidence base for the paper's main confirmatory claims.",
        )
        render_layer_badge(
            "validated",
            "This view is based only on the frozen validated evidence layer. Freeze records and exports in this step are paper-safe when tied to resolved evidence.",
        )
        legacy_freeze_payload = load_evidence_freeze(str(EVIDENCE_FREEZE_PATH))
        freeze_library = evidence_freezes_df(conn, annotator_id)
        selected_library_payload: dict[str, object] = {}
        if not freeze_library.empty:
            st.markdown("**Saved freeze versions**")
            freeze_options = freeze_library["id"].tolist()
            selected_freeze_id = st.selectbox(
                "Named freezes",
                options=freeze_options,
                format_func=lambda fid: f"{freeze_library.loc[freeze_library['id'] == fid, 'name'].iloc[0]} (id={fid})",
                key="runlab_saved_freeze_select",
            )
            selected_freeze_row = freeze_library[freeze_library["id"] == selected_freeze_id].iloc[0]
            selected_library_payload = _evidence_freeze_payload_from_row(selected_freeze_row)
            lf1, lf2 = st.columns(2)
            if lf1.button("Load Saved Freeze", key="runlab_load_saved_freeze", use_container_width=True):
                st.session_state["runlab_evidence_freeze_runs"] = list(selected_library_payload.get("run_ids", []))
                st.success(f"Loaded freeze: {_safe_text(selected_library_payload.get('name'))}")
                st.rerun()
            if lf2.button("Delete Saved Freeze", key="runlab_delete_saved_freeze", use_container_width=True):
                delete_evidence_freeze(conn, created_by=annotator_id, freeze_id=int(selected_freeze_id))
                evidence_freezes_df.clear()
                st.success("Saved freeze deleted.")
                st.rerun()
            st.caption(
                f"Saved at {_safe_text(selected_library_payload.get('created_at')) or 'n/a'} | "
                f"notes: {_safe_text(selected_library_payload.get('notes')) or '(none)'}"
            )

        freeze_payload = selected_library_payload or legacy_freeze_payload
        available_freeze_runs = resolved_consensus_run_ids(conn)
        default_freeze_runs = tuple(int(x) for x in freeze_payload.get("run_ids", [])) if freeze_payload else available_freeze_runs
        selected_evidence_runs = st.multiselect(
            "Runs in frozen evidence base",
            options=list(available_freeze_runs),
            default=list(default_freeze_runs),
            format_func=lambda x: f"Run {x}",
            key="runlab_evidence_freeze_runs",
        )
        evidence_run_ids = tuple(int(x) for x in selected_evidence_runs)
        freeze_snapshot = evidence_base_snapshot(conn, evidence_run_ids)
        freeze_summary = freeze_snapshot.get("summary", {})
        if freeze_summary:
            registry = logic_registry()
            freeze_name_for_exports = _safe_text(
                selected_library_payload.get("name")
                or freeze_payload.get("name")
                or "unsaved_current_selection"
            )
            freeze_date_for_exports = _safe_text(
                selected_library_payload.get("created_at")
                or freeze_payload.get("created_at")
                or freeze_payload.get("generated_at")
                or datetime.now(tz=timezone.utc).isoformat()
            )
            render_metric_tiles(
                [
                    {
                        "label": "Resolved comments",
                        "value": int(freeze_summary.get("resolved_comments", 0)),
                        "note": "main evidence rows",
                        "tone": "accent",
                    },
                    {
                        "label": "Double-coded comments",
                        "value": int(freeze_summary.get("double_coded_comments", 0)),
                        "note": "coder-agreement base",
                        "tone": "sage",
                    },
                    {
                        "label": "Unresolved disagreements",
                        "value": int(freeze_summary.get("unresolved_disagreements", 0)),
                        "note": "should be zero at freeze",
                        "tone": "gold",
                    },
                    {
                        "label": "Any core positives",
                        "value": int(freeze_summary.get("any_core_positive", 0)),
                        "note": "skepticism/proof/normalization",
                        "tone": "accent",
                    },
                ]
            )
            if freeze_payload:
                render_note_banner(
                    "Saved freeze",
                    f"Current saved freeze covers runs {', '.join(str(x) for x in freeze_payload.get('run_ids', [])) or 'n/a'} and was saved at {_safe_text(freeze_payload.get('created_at') or freeze_payload.get('generated_at')) or 'n/a'}.",
                )
            freeze_uuid = _safe_text(selected_library_payload.get("freeze_uuid") or freeze_payload.get("freeze_uuid"))
            if not freeze_uuid:
                freeze_uuid = f"freeze-{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            freeze_export = {
                "freeze_uuid": freeze_uuid,
                "freeze_id": int(selected_library_payload.get("id", 0) or 0) if selected_library_payload else None,
                "freeze_name": freeze_name_for_exports,
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
                "freeze_timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "annotator_id": annotator_id,
                "run_ids": list(evidence_run_ids),
                "run_ids_included": list(evidence_run_ids),
                "resolved_comment_count": int(freeze_summary.get("resolved_comments", 0) or 0),
                "double_coded_comment_count": int(freeze_summary.get("double_coded_comments", 0) or 0),
                "disagreement_count": int(freeze_summary.get("disagreement_comments", 0) or 0),
                "unresolved_disagreement_count": int(freeze_summary.get("unresolved_disagreements", 0) or 0),
                "rules_version": registry["rules_version"],
                "scoring_version": registry["scoring_version"],
                "preprocessing_profile": registry["preprocessing_profile"],
                "spam_ruleset_version": registry["preprocessing_rules_version"],
                "logic_registry": registry,
                "snapshot_summary": freeze_summary,
                "prevalence_overall": freeze_snapshot["prevalence_overall"].to_dict(orient="records"),
                "prevalence_by_run_niche": freeze_snapshot["prevalence_by_run_niche"].to_dict(orient="records"),
            }
            with st.form("runlab_save_named_freeze_form"):
                sf1, sf2 = st.columns([2, 3])
                freeze_name = sf1.text_input(
                    "Freeze name",
                    value=_safe_text(freeze_payload.get("name")) if freeze_payload else "",
                    placeholder="e.g. main_evidence_2026_03_31",
                )
                freeze_notes = sf2.text_input(
                    "Freeze notes",
                    value=_safe_text(freeze_payload.get("notes")) if freeze_payload else "",
                    placeholder="What changed or why this freeze matters",
                )
                freeze_saved = st.form_submit_button("Save Named Freeze", use_container_width=True)
            if freeze_saved:
                if not freeze_name.strip():
                    st.error("Freeze name is required.")
                else:
                    named_freeze_export = dict(freeze_export)
                    named_freeze_export["freeze_name"] = freeze_name.strip()
                    named_freeze_export["notes"] = freeze_notes.strip()
                    saved_freeze_id = upsert_evidence_freeze(
                        conn,
                        created_by=annotator_id,
                        name=freeze_name.strip(),
                        notes=freeze_notes.strip(),
                        payload=named_freeze_export,
                    )
                    named_freeze_export["freeze_id"] = saved_freeze_id
                    save_evidence_freeze(str(EVIDENCE_FREEZE_PATH), named_freeze_export)
                    _record_export_event(
                        conn,
                        export_type="freeze_record_json",
                        file_path=f"app://runlab/freeze/{freeze_name.strip()}",
                        row_count=int(freeze_summary.get("resolved_comments", 0) or 0),
                        freeze_id=saved_freeze_id,
                    )
                    evidence_freezes_df.clear()
                    st.success(f"Saved named freeze: {freeze_name.strip()}")
                    st.rerun()
            fz1, fz2 = st.columns(2)
            if fz1.button("Save Legacy Freeze File", use_container_width=True, key="runlab_save_evidence_freeze_file"):
                save_evidence_freeze(str(EVIDENCE_FREEZE_PATH), freeze_export)
                _record_export_event(
                    conn,
                    export_type="freeze_legacy_json",
                    file_path=str(EVIDENCE_FREEZE_PATH),
                    row_count=int(freeze_summary.get("resolved_comments", 0) or 0),
                    freeze_id=int(selected_library_payload.get("id", 0) or 0) if selected_library_payload else None,
                )
                st.success(f"Saved legacy freeze snapshot to `{EVIDENCE_FREEZE_PATH}`.")
            fz2.download_button(
                "Download Freeze JSON",
                data=json.dumps(freeze_export, ensure_ascii=True, indent=2).encode("utf-8"),
                file_name=f"evidence_freeze_{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
                mime="application/json",
                use_container_width=True,
            )
            freeze_summary_table = validation_summary_table(
                freeze_snapshot,
                freeze_date=freeze_date_for_exports,
                freeze_name=freeze_name_for_exports,
                run_ids=evidence_run_ids,
                freeze_id=int(selected_library_payload.get("id", 0) or 0) if selected_library_payload else None,
                freeze_uuid=freeze_uuid,
                rules_version=_safe_text(selected_library_payload.get("rules_version")) or registry["rules_version"],
                scoring_version=_safe_text(selected_library_payload.get("scoring_version")) or registry["scoring_version"],
                preprocessing_profile=_safe_text(selected_library_payload.get("preprocessing_profile")) or registry["preprocessing_profile"],
            )
            st.markdown("**Freeze record summary**")
            render_layer_badge(
                "validated",
                "This view is based only on the frozen validated evidence layer. Every freeze below is inspectable and exportable.",
            )
            render_note_banner(
                "Paper-facing reference point",
                "Use this freeze ID/UUID as the evidence anchor for all paper-facing claims and reproducibility checks.",
            )
            st.dataframe(freeze_summary_table, use_container_width=True, height=320)
            fr1, fr2 = st.columns(2)
            fr1.download_button(
                "Download freeze summary CSV",
                data=freeze_summary_table.to_csv(index=False).encode("utf-8"),
                file_name=f"freeze_summary_{'_'.join(str(x) for x in evidence_run_ids)}.csv",
                mime="text/csv",
                use_container_width=True,
            )
            fr2.download_button(
                "Download freeze snapshot summary JSON",
                data=json.dumps(freeze_summary, ensure_ascii=True, indent=2).encode("utf-8"),
                file_name=f"freeze_snapshot_summary_{'_'.join(str(x) for x in evidence_run_ids)}.json",
                mime="application/json",
                use_container_width=True,
            )
            version_df = pd.DataFrame(
                [
                    {
                        "component": "rules_version",
                        "version": _safe_text(selected_library_payload.get("rules_version")) or registry["rules_version"],
                    },
                    {
                        "component": "scoring_version",
                        "version": _safe_text(selected_library_payload.get("scoring_version")) or registry["scoring_version"],
                    },
                    {
                        "component": "preprocessing_profile",
                        "version": _safe_text(selected_library_payload.get("preprocessing_profile")) or registry["preprocessing_profile"],
                    },
                    {"component": "preprocessing_rules_version", "version": registry["preprocessing_rules_version"]},
                    {"component": "signal_detection_rules_version", "version": registry["signal_detection_rules_version"]},
                    {"component": "triage_scoring_version", "version": registry["triage_scoring_version"]},
                    {"component": "priority_scoring_version", "version": registry["priority_scoring_version"]},
                ]
            )
            st.markdown("**Logic and scoring versions used**")
            st.dataframe(version_df, use_container_width=True, height=260)
            with st.expander("Freeze prevalence by run and niche"):
                st.dataframe(freeze_snapshot["prevalence_by_run_niche"], use_container_width=True, height=280)
            if selected_library_payload:
                compare_df = compare_freeze_snapshots(
                    freeze_summary,
                    selected_library_payload.get("snapshot_summary", {}),
                    current_runs=evidence_run_ids,
                    saved_runs=selected_library_payload.get("run_ids", []),
                )
                st.markdown("**Freeze comparison**")
                st.dataframe(compare_df, use_container_width=True, height=320)

            workflow = annotation_workflow_metrics(conn, evidence_run_ids)
            workflow_summary = workflow["summary"]
            st.divider()
            st.markdown("**Workflow metrics**")
            if workflow_summary.empty:
                st.info("No annotation snapshot metrics available yet for the selected run scope.")
            else:
                wf_row = workflow_summary.iloc[0]
                render_metric_tiles(
                    [
                        {
                            "label": "Annotated rows",
                            "value": int(wf_row["annotated_rows"]),
                            "note": "with saved workflow context",
                            "tone": "accent",
                        },
                        {
                            "label": "Adjudicated rows",
                            "value": int(wf_row["adjudicated_rows"]),
                            "note": "saved under current scope",
                            "tone": "sage",
                        },
                        {
                            "label": "Low-info rate",
                            "value": _format_proxy_value(wf_row["low_info_rate"]),
                            "note": "annotated rows",
                            "tone": "gold",
                        },
                        {
                            "label": "Non-English rate",
                            "value": _format_proxy_value(wf_row["non_english_rate"]),
                            "note": f"labels from {workflow['label_source_used']}",
                            "tone": "accent",
                        },
                    ]
                )
                w1, w2 = st.columns(2)
                with w1:
                    st.markdown("**Positive yield by priority bucket**")
                    st.dataframe(workflow["by_priority"], use_container_width=True, height=240)
                with w2:
                    st.markdown("**Positive yield by triage bucket**")
                    st.dataframe(workflow["by_triage"], use_container_width=True, height=240)

            st.divider()
            st.markdown("**Paper outputs**")
            corpus_summary = corpus_overview_snapshot(conn)
            labeled_summary = labeled_comment_summary(conn, evidence_run_ids)
            validation_df = validation_summary_table(
                freeze_snapshot,
                freeze_date=freeze_date_for_exports,
                freeze_name=freeze_name_for_exports,
                run_ids=evidence_run_ids,
                freeze_id=int(selected_library_payload.get("id", 0) or 0) if selected_library_payload else None,
                freeze_uuid=freeze_uuid,
                rules_version=_safe_text(selected_library_payload.get("rules_version")) or registry["rules_version"],
                scoring_version=_safe_text(selected_library_payload.get("scoring_version")) or registry["scoring_version"],
                preprocessing_profile=_safe_text(selected_library_payload.get("preprocessing_profile")) or registry["preprocessing_profile"],
            )
            systems_df = systems_summary_table(corpus_summary, labeled_summary, freeze_snapshot)
            render_metric_tiles(
                [
                    {
                        "label": "Broader corpus",
                        "value": int(corpus_summary.get("comments", 0) or 0),
                        "note": "all collected comments",
                        "tone": "accent",
                    },
                    {
                        "label": "Labeled in frozen runs",
                        "value": int(labeled_summary.get("labeled_comments", 0) or 0),
                        "note": "human-coded rows",
                        "tone": "sage",
                    },
                    {
                        "label": "Disagreement cases",
                        "value": int(labeled_summary.get("disagreement_comments", 0) or 0),
                        "note": "quality-control workload",
                        "tone": "gold",
                    },
                    {
                        "label": "Resolved at freeze",
                        "value": int(freeze_summary.get("resolved_comments", 0) or 0),
                        "note": "main evidence rows",
                        "tone": "accent",
                    },
                ]
            )
            p1, p2 = st.columns(2)
            with p1:
                st.markdown("**Validation summary table**")
                st.dataframe(validation_df, use_container_width=True, height=360)
                st.download_button(
                    "Download validation summary CSV",
                    data=validation_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"validation_summary_{'_'.join(str(x) for x in evidence_run_ids)}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            with p2:
                st.markdown("**System contribution table**")
                st.dataframe(systems_df, use_container_width=True, height=360)
                st.download_button(
                    "Download system contribution CSV",
                    data=systems_df.to_csv(index=False).encode("utf-8"),
                    file_name=f"system_contribution_{'_'.join(str(x) for x in evidence_run_ids)}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            figure_spec = workflow_boundary_figure_spec()
            st.markdown("**Boundary figure spec**")
            st.code(figure_spec, language="text")
            q1, q2 = st.columns(2)
            q1.download_button(
                "Download boundary figure spec",
                data=figure_spec.encode("utf-8"),
                file_name=f"boundary_figure_spec_{'_'.join(str(x) for x in evidence_run_ids)}.txt",
                mime="text/plain",
                use_container_width=True,
            )
            q2.download_button(
                "Download workflow metrics CSV",
                data=workflow["by_priority"].to_csv(index=False).encode("utf-8"),
                file_name=f"workflow_priority_metrics_{'_'.join(str(x) for x in evidence_run_ids)}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.info("No resolved-consensus comments available for the selected runs yet.")

        st.divider()
        st.markdown("**Step 2. Explore The Uncoded Pool Automatically**")
        render_evidence_boundary_banner(
            "Assistive / exploratory layer",
            "This step is for contextual mapping and candidate discovery only. It does not expand the frozen validated evidence base.",
        )
        render_layer_badge(
            "warning",
            "This view includes exploratory or assistive outputs and should not be used directly for paper-facing claims.",
        )
        with st.form("runlab_uncoded_extension_form"):
            extension_include_flagged = st.checkbox(
                "Include filtered-out rows",
                value=bool(st.session_state.get("runlab_extension_include_flagged", False)),
                key="runlab_extension_include_flagged",
                help="Include spam/template/duplicate rows in this exploratory pool.",
            )
            prepare_uncoded_extension = st.form_submit_button("Prepare uncoded extension", use_container_width=True)
        if prepare_uncoded_extension:
            st.session_state["runlab_show_uncoded_extension"] = True
            st.session_state["runlab_log_uncoded_extension"] = True
        st.caption("Exploratory results refresh when you press `Prepare uncoded extension`.")
        if st.session_state.get("runlab_show_uncoded_extension") and evidence_run_ids:
            if st.button("Hide uncoded extension", key="runlab_hide_uncoded_extension", use_container_width=True):
                st.session_state["runlab_show_uncoded_extension"] = False
                st.rerun()
            extension_frames = uncoded_extension_frames(conn, evidence_run_ids, extension_include_flagged)
            extension_summary = extension_frames["summary"]
            if extension_summary.empty:
                st.info("No uncoded comments left in the selected runs under the current filters.")
            else:
                if st.session_state.pop("runlab_log_uncoded_extension", False):
                    _record_export_event(
                        conn,
                        export_type="uncoded_extension_ready",
                        file_path="app://runlab/uncoded_extension",
                        row_count=len(extension_frames["uncoded_comments"]),
                        freeze_id=int(selected_library_payload.get("id", 0) or 0) if selected_library_payload else None,
                    )
                ext_row = extension_summary.iloc[0]
                render_metric_tiles(
                    [
                        {
                            "label": "Uncoded comments",
                            "value": int(ext_row["uncoded_comments"]),
                            "note": "remaining exploration pool",
                            "tone": "accent",
                        },
                        {
                            "label": "Core-signal rows",
                            "value": int(ext_row["core_signal_rows"]),
                            "note": "rule-hit comments",
                            "tone": "sage",
                        },
                        {
                            "label": "AI-context rows",
                            "value": int(ext_row["ai_context_rows"]),
                            "note": "comment or video AI signal",
                            "tone": "gold",
                        },
                        {
                            "label": "Low-info rows",
                            "value": int(ext_row["low_info_rows"]),
                            "note": "likely weak/noisy candidates",
                            "tone": "accent",
                        },
                    ]
                )
                st.dataframe(extension_frames["by_run_niche"], use_container_width=True, height=220)
                appendix_candidates = extension_frames["top_candidates"].head(250).copy()
                appendix_cols = [
                    "run_id",
                    "channel_niche",
                    "channel_id",
                    "video_id",
                    "comment_rank",
                    "signal_score",
                    "auto_labels",
                    "heuristic_language",
                    "low_info_noise",
                    "cleaned_text",
                    "trace_summary",
                ]
                st.markdown("**Top uncoded candidates for exploratory extension**")
                st.dataframe(appendix_candidates[appendix_cols], use_container_width=True, height=320)
                e1, e2 = st.columns(2)
                e1.download_button(
                    "Download uncoded extension candidates CSV",
                    data=appendix_candidates[appendix_cols].to_csv(index=False).encode("utf-8"),
                    file_name=f"uncoded_extension_candidates_{'_'.join(str(x) for x in evidence_run_ids)}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
                e2.download_button(
                    "Download full uncoded extension CSV",
                    data=extension_frames["uncoded_comments"].to_csv(index=False).encode("utf-8"),
                    file_name=f"uncoded_extension_full_{'_'.join(str(x) for x in evidence_run_ids)}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

        st.divider()
        st.markdown("**Step 3. Export The Final Tables And Appendix Pack**")
        render_evidence_boundary_banner(
            "Validated evidence exports",
            "The main tables and model outputs here are intended to be generated from the selected frozen evidence runs.",
        )
        render_layer_badge(
            "validated",
            "This view is based only on the frozen validated evidence layer. Exports below are intended for paper-facing use when generated from the selected freeze.",
        )
        with st.form("runlab_final_pack_form"):
            prepare_final_pack = st.form_submit_button(
                "Prepare paper export files",
                use_container_width=True,
                help="Generates the resolved-consensus tables, model outputs, and appendix exports for the selected evidence runs.",
            )
        if prepare_final_pack:
            st.session_state["runlab_show_final_analysis_pack"] = True
            st.session_state["runlab_log_final_pack"] = True
        st.caption("Paper exports refresh when you press `Prepare paper export files`.")
        if st.session_state.get("runlab_show_final_analysis_pack") and evidence_run_ids:
            if st.button("Hide paper exports", key="runlab_hide_final_pack", use_container_width=True):
                st.session_state["runlab_show_final_analysis_pack"] = False
                st.rerun()
            final_pack = build_final_analysis_pack(conn, evidence_run_ids, annotator_id)
            pack_bundle = final_pack["bundle"]
            frames = final_pack["conformity_frames"]
            if st.session_state.pop("runlab_log_final_pack", False):
                _record_export_event(
                    conn,
                    export_type="paper_export_bundle_ready",
                    file_path="app://runlab/final_analysis_bundle",
                    row_count=len(final_pack["snapshot"]["resolved_comments"]),
                    freeze_id=int(selected_library_payload.get("id", 0) or 0) if selected_library_payload else None,
                )
            summary_df = frames["summary_df"]
            if not summary_df.empty:
                row = summary_df.iloc[0]
                render_metric_tiles(
                    [
                        {"label": "Response comments", "value": int(row["response_comments"]), "note": "used in pooled cue model", "tone": "accent"},
                        {"label": "Skeptical top-cue videos", "value": int(row["skeptical_top_comment_videos"]), "note": "cue-positive videos", "tone": "sage"},
                        {"label": "H1 delta", "value": _format_proxy_value(row["h1_delta_proxy"]), "note": "skeptical minus non-skeptical cue", "tone": "gold"},
                        {"label": "H2 cue correlation", "value": _format_proxy_value(row["h2_proxy_corr_within_skeptical_cue_videos"]), "note": "within skeptical-cue videos", "tone": "accent"},
                    ]
                )
            fp1, fp2, fp3 = st.columns(3)
            fp1.download_button(
                "Download final analysis bundle JSON",
                data=json.dumps(pack_bundle, ensure_ascii=True, indent=2).encode("utf-8"),
                file_name=f"final_analysis_bundle_{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
                mime="application/json",
                use_container_width=True,
            )
            fp2.download_button(
                "Download prevalence table CSV",
                data=final_pack["snapshot"]["prevalence_by_run_niche"].to_csv(index=False).encode("utf-8"),
                file_name=f"final_prevalence_by_run_niche_{'_'.join(str(x) for x in evidence_run_ids)}.csv",
                mime="text/csv",
                use_container_width=True,
            )
            fp3.download_button(
                "Download model effects CSV",
                data=frames["effects_df"].to_csv(index=False).encode("utf-8"),
                file_name=f"final_model_effects_{'_'.join(str(x) for x in evidence_run_ids)}.csv",
                mime="text/csv",
                use_container_width=True,
            )
            fa1, fa2 = st.columns(2)
            fa1.download_button(
                "Download positive-comment appendix CSV",
                data=final_pack["positive_appendix"].to_csv(index=False).encode("utf-8"),
                file_name=f"appendix_positive_comments_{'_'.join(str(x) for x in evidence_run_ids)}.csv",
                mime="text/csv",
                use_container_width=True,
            )
            fa2.download_button(
                "Download exploratory extension appendix CSV",
                data=final_pack["extension_appendix"].to_csv(index=False).encode("utf-8"),
                file_name=f"appendix_extension_candidates_{'_'.join(str(x) for x in evidence_run_ids)}.csv",
                mime="text/csv",
                use_container_width=True,
            )
            with st.expander("Final pack tables preview"):
                st.markdown("**Prevalence by run and niche**")
                st.dataframe(final_pack["snapshot"]["prevalence_by_run_niche"], use_container_width=True, height=220)
                st.markdown("**Combined effects**")
                st.dataframe(_display_effects_df(frames["effects_df"]), use_container_width=True, height=260)
                st.markdown("**ICC / variance**")
                st.dataframe(frames["icc_df"], use_container_width=True, height=180)
            export_records = export_records_df(
                conn,
                freeze_id=int(selected_library_payload.get("id", 0) or 0) if selected_library_payload else None,
            ).head(12)
            if not export_records.empty:
                st.markdown("**Recent export records**")
                st.dataframe(export_records, use_container_width=True, height=260)

    st.divider()

    catalog = run_catalog_df(conn)
    if catalog.empty:
        st.info("No runs found yet.")
    else:
        f1, f2, f3 = st.columns(3)
        status_opts = sorted([str(x) for x in catalog["status"].dropna().unique().tolist()])
        content_opts = sorted([str(x) for x in catalog["content_type"].dropna().unique().tolist()])
        mode_opts = sorted([str(x) for x in catalog["execution_mode"].dropna().unique().tolist()])
        statuses = f1.multiselect("Status", options=status_opts, default=status_opts, key="runlab_status")
        content_types = f2.multiselect(
            "Content type",
            options=content_opts,
            default=content_opts,
            key="runlab_content_type",
        )
        modes = f3.multiselect("Execution mode", options=mode_opts, default=mode_opts, key="runlab_mode")
        note_search = st.text_input("Search run notes", key="runlab_note_search")

        filtered = catalog.copy()
        if statuses:
            filtered = filtered[filtered["status"].isin(statuses)]
        if content_types:
            filtered = filtered[filtered["content_type"].isin(content_types)]
        if modes:
            filtered = filtered[filtered["execution_mode"].isin(modes)]
        if note_search.strip():
            filtered = filtered[filtered["notes"].astype(str).str.contains(note_search, case=False, na=False)]

        show_cols = [
            "id",
            "started_at",
            "status",
            "execution_mode",
            "content_type",
            "rules_version",
            "scoring_version",
            "preprocessing_profile",
            "run_mode",
            "channels",
            "videos",
            "comments",
            "api_units_used",
            "api_comment_count",
            "playwright_comment_count",
            "shorts_videos",
            "long_videos",
            "niches",
            "run_truncated",
            "notes",
        ]
        st.markdown("**Run Catalog**")
        st.dataframe(filtered[show_cols], use_container_width=True, height=280)

        if not filtered.empty:
            selected_run = st.selectbox(
                "Inspect run",
                options=filtered["id"].tolist(),
                format_func=lambda x: f"Run {x}",
                key="runlab_inspect_run",
            )
            row = filtered[filtered["id"] == selected_run].iloc[0]
            qa_payload = run_qa_payload(conn, int(selected_run))
            qa_meta = qa_payload.get("run_metadata", {}) if isinstance(qa_payload.get("run_metadata"), dict) else {}
            qa_attrition = qa_payload.get("attrition", {}) if isinstance(qa_payload.get("attrition"), dict) else {}
            provenance_df = run_video_provenance_df(conn, int(selected_run))
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Channels", int(row["channels"]))
            c2.metric("Videos", int(row["videos"]))
            c3.metric("Comments", int(row["comments"]))
            c4.metric("API units", int(row["api_units_used"] or 0))
            c5.metric("Truncated", "Yes" if int(row["run_truncated"] or 0) else "No")

            render_note_banner(
                "Run provenance",
                f"content `{_safe_text(row.get('content_type')) or 'unknown'}` | "
                f"target file `{_safe_text(row.get('target_file')) or 'n/a'}` | "
                f"requested targets `{int(row.get('target_count_requested') or 0)}` | "
                f"profile `{_safe_text(row.get('study_profile_name')) or 'n/a'}`",
            )

            qa1, qa2, qa3, qa4, qa5, qa6 = st.columns(6)
            qa1.metric("Comments scanned", int(qa_attrition.get("comments_scanned", 0) or 0))
            qa2.metric("Comments saved", int(qa_attrition.get("comments_saved", 0) or 0))
            qa3.metric("Comments filtered", int(qa_attrition.get("comments_filtered", 0) or 0))
            qa4.metric("Coverage shortfall ch.", int(qa_attrition.get("coverage_shortfall_channels", 0) or 0))
            qa5.metric("No-shorts ch.", int(qa_attrition.get("no_shorts_available_channels", 0) or 0))
            qa6.metric("Failed channels", int(qa_attrition.get("extraction_failed_channels", 0) or 0))

            left, right = st.columns(2)
            with left:
                status_df = run_video_status_df(conn, int(selected_run))
                st.markdown("**Video status breakdown**")
                if status_df.empty:
                    st.info("No video status rows.")
                else:
                    st.dataframe(status_df, use_container_width=True, height=180)
            with right:
                niche_df = run_niche_summary_df(conn, int(selected_run))
                st.markdown("**Niche breakdown**")
                if niche_df.empty:
                    st.info("No niche rows.")
                else:
                    st.dataframe(niche_df, use_container_width=True, height=180)

            engine1, engine2 = st.columns(2)
            with engine1:
                st.markdown("**Video collection engines**")
                video_engine_df = pd.DataFrame(qa_payload.get("video_engine_counts", []))
                if video_engine_df.empty:
                    st.info("No video-engine rows.")
                else:
                    st.dataframe(video_engine_df, use_container_width=True, height=180)
            with engine2:
                st.markdown("**Comment engine counts**")
                comment_engine_df = pd.DataFrame(qa_payload.get("comment_engine_counts", []))
                if comment_engine_df.empty:
                    st.info("No comment-engine rows.")
                else:
                    st.dataframe(comment_engine_df, use_container_width=True, height=180)

            st.markdown("**Niche attrition and QA**")
            niche_attrition_df = pd.DataFrame(qa_payload.get("niche_attrition", []))
            if niche_attrition_df.empty:
                st.info("No niche attrition rows.")
            else:
                st.dataframe(niche_attrition_df, use_container_width=True, height=220)

            st.markdown("**Per-video provenance**")
            if provenance_df.empty:
                st.info("No video provenance rows.")
            else:
                st.dataframe(provenance_df, use_container_width=True, height=280)

    st.divider()
    st.markdown("**Start New Scrape Job**")
    if not target_files:
        st.warning("No CSV files found in `data/`.")
        return
    if st.session_state.get("runlab_target_file") not in target_files:
        st.session_state["runlab_target_file"] = target_files[0]

    with st.form("runlab_launch_form"):
        c1, c2, c3 = st.columns(3)
        target_file = c1.selectbox("Targets CSV", options=target_files, key="runlab_target_file")
        execution_mode = c2.selectbox(
            "Execution mode",
            options=["auto", "api_only", "playwright_only"],
            index=["auto", "api_only", "playwright_only"].index(config.execution_mode)
            if config.execution_mode in {"auto", "api_only", "playwright_only"}
            else 0,
            key="runlab_execution_mode",
        )
        content_type = c3.selectbox("Content type", options=["videos", "shorts"], index=0, key="runlab_content")

        d1, d2, d3, d4 = st.columns(4)
        channel_limit = d1.number_input(
            "Channel limit (0 = all)",
            min_value=0,
            max_value=300,
            value=30,
            step=1,
            key="runlab_channel_limit",
        )
        videos_per_channel = d2.number_input(
            "Videos per channel",
            min_value=1,
            max_value=120,
            value=20,
            step=1,
            key="runlab_videos_per_channel",
        )
        min_expected = d3.number_input(
            "Min expected videos",
            min_value=1,
            max_value=120,
            value=20,
            step=1,
            key="runlab_min_expected",
        )
        template_threshold = d4.number_input(
            "Template threshold",
            min_value=0.80,
            max_value=0.99,
            value=0.90,
            step=0.01,
            format="%.2f",
            key="runlab_template_threshold",
        )
        simulate = st.checkbox("Simulate mode (no live web/API calls)", key="runlab_simulate")

        st.markdown("**Default Dataset Filters (saved in profile, for analysis tabs)**")
        f1, f2, f3, f4 = st.columns(4)
        default_niches = f1.multiselect(
            "Niches",
            options=["Tech", "Beauty", "Lifestyle"],
            default=st.session_state.get("runlab_dataset_niches", ["Tech", "Beauty", "Lifestyle"]),
            key="runlab_dataset_niches",
        )
        include_shorts_filter = f2.checkbox(
            "Include Shorts in analysis",
            key="runlab_include_shorts_filter",
        )
        include_spam_filter = f3.checkbox(
            "Include spam rows",
            key="runlab_include_spam_filter",
        )
        include_template_filter = f4.checkbox(
            "Include template rows",
            key="runlab_include_template_filter",
        )
        g1, g2, g3, g4 = st.columns(4)
        include_duplicate_filter = g1.checkbox(
            "Include duplicate rows",
            key="runlab_include_duplicate_filter",
        )
        comment_rank_min = g2.number_input(
            "Comment rank min",
            min_value=1,
            max_value=200,
            step=1,
            key="runlab_comment_rank_min",
        )
        comment_rank_max = g3.number_input(
            "Comment rank max",
            min_value=1,
            max_value=200,
            step=1,
            key="runlab_comment_rank_max",
        )
        min_comments_video_filter = g4.number_input(
            "Min comments per video",
            min_value=0,
            max_value=200,
            step=1,
            key="runlab_min_comments_video_filter",
        )
        # keep variables bound for clarity in Streamlit execution graph
        _ = (
            default_niches,
            include_shorts_filter,
            include_spam_filter,
            include_template_filter,
            include_duplicate_filter,
            comment_rank_min,
            comment_rank_max,
            min_comments_video_filter,
        )
        submitted = st.form_submit_button("Start Run", use_container_width=True)

    if submitted:
        try:
            targets = load_targets_csv(Path(target_file))
            if int(channel_limit) > 0:
                targets = targets[: int(channel_limit)]
            if not targets:
                st.error("No targets loaded from selected CSV after filters.")
                return

            min_expected_int = int(min(min_expected, videos_per_channel))
            run_cfg = replace(config, execution_mode=execution_mode)
            run_payload = _current_runlab_payload()
            run_payload["run_meta"] = {
                "target_count_requested": int(len(targets)),
                "target_file": _safe_text(target_file),
                "study_profile_name": _safe_text(st.session_state.get("runlab_active_profile_name")),
            }
            with st.spinner(
                f"Running batch on {len(targets)} channels "
                f"({content_type}, mode={execution_mode}, simulate={simulate})..."
            ):
                run_id = run_batch(
                    conn,
                    run_cfg,
                    targets,
                    template_threshold=float(template_threshold),
                    simulate=bool(simulate),
                    videos_per_channel=int(videos_per_channel),
                    min_expected_videos_per_channel=min_expected_int,
                    content_type=str(content_type),
                    target_file=_safe_text(target_file),
                    study_profile_name=_safe_text(st.session_state.get("runlab_active_profile_name")) or None,
                    run_payload=run_payload,
                )
            _clear_cached_frames()
            st.session_state["runlab_inspect_run"] = int(run_id)
            st.session_state["runlab_feedback"] = {
                "level": "success",
                "message": f"Run completed. New run_id={run_id}",
            }
            st.rerun()
        except Exception as exc:
            st.error(f"Run failed: {exc}")


def scraped_data_tab(conn: sqlite3.Connection, show_intro: bool = True) -> None:
    if show_intro:
        render_section_intro(
            "Dataset view",
            "Scraped data",
            "Inspect one run at a time, check collection quality, and move from top-line counts into raw comment previews.",
        )
    render_layer_badge(
        "warning",
        "This view includes exploratory or assistive outputs and should not be used directly for paper-facing claims. Raw collection and QA view for audit.",
    )
    runs = run_df(conn)
    if runs.empty:
        st.info("No runs found.")
        return

    run_choices = runs["id"].tolist()
    latest_run = run_choices[0]
    selected_run = st.selectbox(
        "Run ID",
        options=run_choices,
        index=0,
        format_func=lambda x: f"Run {x}",
        key="scraped_run_id",
    )
    run_row = runs[runs["id"] == selected_run].iloc[0]
    counts = run_counts(conn, selected_run)

    render_metric_tiles(
        [
            {"label": "Channels", "value": counts["channels"], "note": f"run {selected_run}", "tone": "accent"},
            {"label": "Videos", "value": counts["videos"], "note": "collected videos", "tone": "sage"},
            {"label": "Comments", "value": counts["comments"], "note": "raw comment rows", "tone": "gold"},
            {"label": "API comments", "value": int(run_row["api_comment_count"] or 0), "note": "YouTube API path", "tone": "accent"},
            {"label": "Fallback comments", "value": int(run_row["playwright_comment_count"] or 0), "note": "Playwright path", "tone": "sage"},
        ]
    )
    render_note_banner(
        "Run status",
        f"Status {_safe_text(run_row['status'])}, mode {_safe_text(run_row['execution_mode'])}, latest known run {latest_run}.",
    )

    status_df = run_video_status_df(conn, selected_run)
    niche_df = run_niche_summary_df(conn, selected_run)

    left, right = st.columns(2)
    with left:
        st.markdown("**Video Status Breakdown**")
        if status_df.empty:
            st.info("No video status rows.")
        else:
            st.bar_chart(status_df.set_index("comment_status"))
            st.dataframe(status_df, use_container_width=True, height=220)
    with right:
        st.markdown("**Niche Breakdown**")
        if niche_df.empty:
            st.info("No niche rows.")
        else:
            st.bar_chart(niche_df.set_index("niche")[["comments"]])
            st.dataframe(niche_df, use_container_width=True, height=220)

    st.markdown("**Sample Comments Preview**")
    preview = comments_df(conn, selected_run).head(300)
    if preview.empty:
        st.info("No comments available.")
    else:
        st.dataframe(preview, use_container_width=True, height=420)


def exploration_tab(conn: sqlite3.Connection, show_intro: bool = True) -> None:
    if show_intro:
        render_section_intro(
            "Exploration desk",
            "Data exploration",
            "Slice the raw comment pool before formal coding or modeling. This tab is for pattern hunting, not locked-in evidence.",
        )
    render_layer_badge(
        "warning",
        "This view includes exploratory or assistive outputs and should not be used directly for paper-facing claims. Exploratory filtering only.",
    )
    runs = run_df(conn)
    run_choices = [None] + runs["id"].tolist() if not runs.empty else [None]
    default_index = 1 if len(run_choices) > 1 else 0
    selected_run = st.selectbox(
        "Run ID",
        options=run_choices,
        index=default_index,
        format_func=lambda x: "All" if x is None else f"{x}",
    )

    df = comments_df(conn, selected_run)
    if df.empty:
        st.info("No comments available for current filters.")
        return

    niche_options = sorted(df["channel_niche"].dropna().unique().tolist())
    niches = st.multiselect("Niche", options=niche_options, default=niche_options)
    hide_spam = st.checkbox("Hide spam", value=True)
    hide_template = st.checkbox("Hide template", value=True)
    hide_duplicate = st.checkbox("Hide duplicate", value=True)
    search = st.text_input("Search text")

    filtered = df.copy()
    if niches:
        filtered = filtered[filtered["channel_niche"].isin(niches)]
    if hide_spam:
        filtered = filtered[filtered["is_spam"] == 0]
    if hide_template:
        filtered = filtered[filtered["is_template"] == 0]
    if hide_duplicate:
        filtered = filtered[filtered["is_duplicate"] == 0]
    if search.strip():
        filtered = filtered[filtered["cleaned_text"].str.contains(search, case=False, na=False)]

    st.caption(f"Rows shown: {len(filtered)}")
    st.dataframe(filtered, use_container_width=True, height=520)

    csv_bytes = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download filtered CSV",
        data=csv_bytes,
        file_name="comments_filtered.csv",
        mime="text/csv",
        use_container_width=True,
    )


def disclosure_search_tab(conn: sqlite3.Connection, show_intro: bool = True) -> None:
    if show_intro:
        st.subheader("AI Disclosure Search")
        st.caption("Exploratory supporting view for AI/disclosure language in titles, descriptions, and comments.")
    render_layer_badge(
        "warning",
        "This view includes exploratory or assistive outputs and should not be used directly for paper-facing claims. Signal detection and search only.",
    )
    runs = run_df(conn)
    run_choices = [None] + runs["id"].tolist() if not runs.empty else [None]
    default_index = 1 if len(run_choices) > 1 else 0
    selected_run = st.selectbox(
        "Run ID",
        options=run_choices,
        index=default_index,
        format_func=lambda x: "All" if x is None else f"{x}",
        key="disclosure_run_id",
    )

    videos = _prepare_video_disclosure_frame(videos_df(conn, selected_run))
    comments = _prepare_comment_rule_frame(comments_df(conn, selected_run))
    if videos.empty and comments.empty:
        st.info("No data available.")
        return

    scope = st.radio("Search scope", options=["Videos", "Comments", "Both"], horizontal=True)
    query = st.text_input("Keyword/regex filter", placeholder="e.g. made with ai|chatgpt|not real")
    only_ai = st.checkbox("Only rows with AI mention", value=True)
    hide_spam = st.checkbox("Hide spam comments", value=True)
    hide_template = st.checkbox("Hide template comments", value=True)
    hide_duplicate = st.checkbox("Hide duplicate comments", value=True)
    max_rows = st.slider("Max rows per table", min_value=50, max_value=5000, value=500, step=50)

    if not videos.empty:
        niches = sorted(videos["channel_niche"].dropna().unique().tolist())
    elif not comments.empty:
        niches = sorted(comments["channel_niche"].dropna().unique().tolist())
    else:
        niches = []
    selected_niches = st.multiselect(
        "Niche filter",
        options=niches,
        default=niches,
        key="disclosure_niche_filter",
    )

    if scope in {"Videos", "Both"}:
        v = videos.copy()
        if selected_niches:
            v = v[v["channel_niche"].isin(selected_niches)]
        if only_ai:
            v = v[v["has_ai_mention"]]
        if query.strip():
            try:
                v = v[v["combined_text"].str.contains(query, case=False, na=False, regex=True)]
            except re.error:
                st.error("Invalid regex in keyword/regex filter.")
                return

        st.markdown("**Video-Level Matches**")
        if v.empty:
            st.info("No matching videos.")
        else:
            level_counts = (
                v["inferred_disclosure_label"]
                .value_counts(dropna=False)
                .rename_axis("inferred_disclosure")
                .reset_index(name="videos")
            )
            c1, c2, c3 = st.columns(3)
            c1.metric("Matched videos", len(v))
            c2.metric("AI mentions", int(v["has_ai_mention"].sum()))
            c3.metric("Channels", int(v["channel_id"].nunique()))
            st.dataframe(level_counts, use_container_width=True, height=180)
            view_cols = [
                "run_id",
                "channel_niche",
                "channel_id",
                "video_id",
                "published_at",
                "inferred_disclosure_label",
                "video_url",
                "title",
                "description",
            ]
            v_show = v[view_cols].head(max_rows)
            st.dataframe(v_show, use_container_width=True, height=360)
            st.download_button(
                "Download matched videos CSV",
                data=v_show.to_csv(index=False).encode("utf-8"),
                file_name="ai_disclosure_video_matches.csv",
                mime="text/csv",
                use_container_width=True,
            )

    if scope in {"Comments", "Both"}:
        c = comments.copy()
        if selected_niches:
            c = c[c["channel_niche"].isin(selected_niches)]
        if hide_spam:
            c = c[c["is_spam"] == 0]
        if hide_template:
            c = c[c["is_template"] == 0]
        if hide_duplicate:
            c = c[c["is_duplicate"] == 0]
        if only_ai:
            c = c[c["has_ai_mention"] == 1]
        if query.strip():
            try:
                c = c[c["cleaned_text"].str.contains(query, case=False, na=False, regex=True)]
            except re.error:
                st.error("Invalid regex in keyword/regex filter.")
                return
        st.markdown("**Comment-Level Matches**")
        if c.empty:
            st.info("No matching comments.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Matched comments", len(c))
            c2.metric("Unique videos", int(c["video_id"].nunique()))
            c3.metric("Unique channels", int(c["channel_id"].nunique()))
            view_cols = [
                "run_id",
                "channel_niche",
                "channel_id",
                "video_id",
                "comment_rank",
                "like_count",
                "reply_count",
                "cleaned_text",
            ]
            c_show = c[view_cols].head(max_rows)
            st.dataframe(c_show, use_container_width=True, height=420)
            st.download_button(
                "Download matched comments CSV",
                data=c_show.to_csv(index=False).encode("utf-8"),
                file_name="ai_disclosure_comment_matches.csv",
                mime="text/csv",
                use_container_width=True,
            )


def _render_hypothesis_review_content(
    conn: sqlite3.Connection,
    annotator_id: str,
    selected_run: int,
    label_source: str,
    *,
    show_export: bool = True,
) -> None:
    runs = run_df(conn)
    if runs.empty:
        st.info("No runs available.")
        return

    counts = run_counts(conn, selected_run)
    run_row = runs[runs["id"] == selected_run].iloc[0]

    comments = comments_df(conn, selected_run)
    if comments.empty:
        st.info("Not enough data for hypothesis review.")
        return

    comments = comments[
        (comments["is_spam"] == 0)
        & (comments["is_template"] == 0)
        & (comments["is_duplicate"] == 0)
    ].copy()
    videos = videos_df(conn, selected_run)
    comments_labeled, label_meta = _apply_label_source(
        comments,
        run_id=selected_run,
        label_source=label_source,
        annotator_id=annotator_id,
        conn=conn,
    )
    cascade = conformity_frames(conn, selected_run, include_flagged=False, label_source=label_source, annotator_id=annotator_id)
    if cascade["error"]:
        st.warning(str(cascade["error"]))

    render_note_banner(
        "Evidence base",
        f"Using {label_meta.get('label_source_label', _label_source_label(label_source))}. Skepticism labels: {int(label_meta.get('skepticism_labeled_comments', 0) or 0)}. Proof-demand labels: {int(label_meta.get('proof_labeled_comments', 0) or 0)}.",
    )
    render_metric_tiles(
        [
            {"label": "Channels", "value": counts["channels"], "note": f"run {selected_run}", "tone": "accent"},
            {"label": "Videos", "value": counts["videos"], "note": "included in this run", "tone": "sage"},
            {"label": "Clean comments", "value": len(comments_labeled), "note": "after quality filters", "tone": "gold"},
            {"label": "API units used", "value": int(run_row["api_units_used"] or 0), "note": "collection cost signal", "tone": "accent"},
            {"label": "Labeled comments", "value": int(label_meta.get("labeled_comments", 0) or 0), "note": "usable under selected source", "tone": "sage"},
        ]
    )

    objective_rows = [
        {
            "objective": "O1 pipeline collection (Tech/Beauty/Lifestyle)",
            "pilot_result": f"{counts['channels']} channels, {counts['videos']} videos, {len(comments_labeled)} clean comments",
            "status": "met" if counts["channels"] > 0 and counts["videos"] > 0 and len(comments_labeled) > 0 else "not_met",
        },
        {
            "objective": "O2 relational queryable dataset",
            "pilot_result": f"Runs={len(runs)}, videos table rows={len(videos)}, comments table rows={len(comments)}",
            "status": "met" if len(videos) > 0 and len(comments) > 0 else "not_met",
        },
        {
            "objective": "O3 receiver-side verification signal",
            "pilot_result": (
                f"Skepticism rate={comments_labeled['analysis_skepticism'].dropna().mean():.3f}, "
                f"proof-demand rate={comments_labeled['analysis_proof_demand'].dropna().mean():.3f}"
            ),
            "status": "observed" if int(label_meta.get("labeled_comments", 0) or 0) > 0 else "inconclusive",
        },
    ]
    st.markdown("**Objectives**")
    st.dataframe(pd.DataFrame(objective_rows), use_container_width=True, height=180)

    proof_by_cue = pd.DataFrame()
    overall_corr = None
    if not cascade["response_df"].empty:
        response_df = cascade["response_df"].copy()
        proof_df = comments_labeled[
            ["video_id", "comment_rank", "analysis_proof_demand", "analysis_normalization"]
        ].copy()
        proof_df = proof_df.rename(columns={"comment_rank": "rank", "analysis_proof_demand": "is_proof_demand"})
        response_with_proof = response_df.merge(
            proof_df,
            on=["video_id", "rank"],
            how="left",
        )
        response_with_proof = response_with_proof.dropna(subset=["is_proof_demand"])
        response_with_proof["is_proof_demand"] = response_with_proof["is_proof_demand"].astype(int)
        proof_by_cue = (
            response_with_proof.groupby("top_comment_skeptical", as_index=False)
            .agg(
                response_comments=("video_id", "count"),
                response_skepticism_rate=("is_skeptical", "mean"),
                response_proof_demand_rate=("is_proof_demand", "mean"),
            )
            .sort_values("top_comment_skeptical", ascending=False)
        )
        overall_corr = (
            response_with_proof["is_skeptical"].corr(response_with_proof["is_proof_demand"])
            if len(response_with_proof) > 1
            else None
        )
    else:
        response_df = pd.DataFrame()

    h3_term = None
    if not cascade["effects_df"].empty:
        niche_terms = cascade["effects_df"][
            cascade["effects_df"]["term"].str.contains("top_comment_skeptical:C\\(channel_niche", na=False)
        ]
        if not niche_terms.empty:
            h3_term = niche_terms["coef_log_odds"].max()

    rq_rows = [
        {
            "research_question": "RQ1 ranked skeptical cue and response skepticism",
            "pilot_metric": (
                f"skeptical_cue_minus_non_skeptical_cue={_format_proxy_value(cascade['summary_df'].iloc[0]['h1_delta_proxy'])}"
                if not cascade["summary_df"].empty
                else "insufficient groups"
            ),
        },
        {
            "research_question": "RQ2 cue magnitude moderation",
            "pilot_metric": (
                f"corr(top_like_z, response_skepticism | skeptical cue)={_format_proxy_value(cascade['summary_df'].iloc[0]['h2_proxy_corr_within_skeptical_cue_videos'])}"
                if not cascade["summary_df"].empty
                else "insufficient rows"
            ),
        },
        {
            "research_question": "RQ3 cross-niche cascade variation",
            "pilot_metric": (
                f"max niche interaction coef={_format_proxy_value(h3_term)}"
                if h3_term is not None
                else "interaction not estimated"
            ),
        },
    ]
    st.markdown("**Research Questions (pilot metrics)**")
    st.dataframe(pd.DataFrame(rq_rows), use_container_width=True, height=180)

    if not proof_by_cue.empty:
        st.markdown("**Response Summary By Cue Type**")
        st.dataframe(proof_by_cue, use_container_width=True, height=180)

    niche_read = cascade.get("niche_df", pd.DataFrame())
    if not niche_read.empty:
        st.markdown("**Niche Moderation Snapshot**")
        st.dataframe(niche_read, use_container_width=True, height=220)

    h1_proxy = cascade["summary_df"].iloc[0]["h1_delta_proxy"] if not cascade["summary_df"].empty else None
    h2_proxy = (
        cascade["summary_df"].iloc[0]["h2_proxy_corr_within_skeptical_cue_videos"]
        if not cascade["summary_df"].empty
        else None
    )

    hyp_rows = [
        {
            "hypothesis": "H1 skeptical top-ranked cue -> higher response skepticism",
            "pilot_metric": _format_proxy_value(h1_proxy),
            "pilot_read": "supported" if h1_proxy is not None and float(h1_proxy) > 0 else "not_supported_or_inconclusive",
        },
        {
            "hypothesis": "H2 stronger cue effect when top-ranked comment has higher like count",
            "pilot_metric": _format_proxy_value(h2_proxy),
            "pilot_read": "supported" if h2_proxy is not None and float(h2_proxy) > 0 else "not_supported_or_inconclusive",
        },
        {
            "hypothesis": "H3 stronger cascade association in higher authenticity-stakes niches",
            "pilot_metric": _format_proxy_value(h3_term),
            "pilot_read": "supported" if h3_term is not None and float(h3_term) > 0 else "not_supported_or_inconclusive",
        },
    ]
    st.markdown("**Hypotheses (exploratory pilot read)**")
    render_hypothesis_cards(
        [
            {
                "title": "H1 skeptical top-ranked cue",
                "metric": _format_proxy_value(h1_proxy),
                "status": "supported" if h1_proxy is not None and float(h1_proxy) > 0 else "not_supported_or_inconclusive",
                "note": "Expected direction: more downstream skepticism after skeptical rank-1 cues.",
            },
            {
                "title": "H2 stronger cue when top cue is liked more",
                "metric": _format_proxy_value(h2_proxy),
                "status": "supported" if h2_proxy is not None and float(h2_proxy) > 0 else "inconclusive",
                "note": "This one usually stays weak unless skeptical-cue rows are plentiful.",
            },
            {
                "title": "H3 stronger in higher-stakes niches",
                "metric": _format_proxy_value(h3_term),
                "status": "supported" if h3_term is not None and float(h3_term) > 0 else "inconclusive",
                "note": "Positive interaction terms suggest a stronger cascade effect in the higher-risk niches.",
            },
        ]
    )
    with st.expander("Hypothesis audit table"):
        st.dataframe(pd.DataFrame(hyp_rows), use_container_width=True, height=220)

    if show_export:
        export_df = response_df.copy()
        st.download_button(
            "Download hypothesis response CSV",
            data=export_df.to_csv(index=False).encode("utf-8"),
            file_name=f"hypothesis_response_run_{selected_run}.csv",
            mime="text/csv",
            use_container_width=True,
        )


def conformity_cascade_tab(conn: sqlite3.Connection, annotator_id: str) -> None:
    render_section_intro(
        "Hypothesis workspace",
        "Main analysis",
        "This is the ranked-cue analysis desk. Use it to read whether skeptical top comments appear to shape downstream response skepticism.",
    )
    runs = run_df(conn)
    if runs.empty:
        st.info("No runs available.")
        return

    with st.form("cascade_controls_form"):
        c1, c2, c3 = st.columns([2, 1, 2])
        selected_run = c1.selectbox(
            "Run ID",
            options=runs["id"].tolist(),
            index=0,
            format_func=lambda x: f"Run {x}",
            key="cascade_run_id",
        )
        include_flagged = c2.checkbox(
            "Include filtered-out rows",
            value=False,
            help="Leave off for the clean proxy analysis by default.",
            key="cascade_include_flagged",
        )
        label_source = c3.selectbox(
            "Evidence source",
            options=[key for key, _label in LABEL_SOURCE_OPTIONS],
            index=0,
            format_func=_label_source_label,
            key="cascade_label_source",
        )
        st.form_submit_button("Run analysis", use_container_width=True)
    st.caption("Results refresh when you press `Run analysis`.")
    scope_label, scope_body = _label_source_scope(label_source)
    render_evidence_boundary_banner(scope_label, scope_body)
    render_scope_badge(scope_label, "Analytics and exports below inherit this evidence scope.")

    frames = conformity_frames(conn, selected_run, include_flagged, label_source, annotator_id)
    if frames["error"]:
        st.warning(str(frames["error"]))
        return

    summary = frames["summary_df"]
    response_df = frames["response_df"]
    effects_df = frames["effects_df"]
    effects_display = _display_effects_df(effects_df)
    icc_df = frames["icc_df"]
    ranked_df = frames["ranked_df"]
    niche_df = frames["niche_df"]
    label_meta = frames.get("label_meta", {})

    row = summary.iloc[0]
    render_note_banner(
        "Label source",
        f"Using {_safe_text(row.get('label_source')) or _safe_text(label_meta.get('label_source_label'))} with skepticism labels on {int(label_meta.get('skepticism_labeled_comments', 0) or 0)} comments in this run.",
    )
    render_metric_tiles(
        [
            {"label": "Videos ranked", "value": int(row["videos_ranked"]), "note": "ranked top-cue videos", "tone": "accent"},
            {"label": "Response comments", "value": int(row["response_comments"]), "note": "ranks 2-20", "tone": "sage"},
            {"label": "Skeptical top cues", "value": int(row["skeptical_top_comment_videos"]), "note": "videos with skeptical top rank", "tone": "gold"},
            {"label": "H1 delta", "value": _format_proxy_value(row["h1_delta_proxy"]), "note": "skeptical minus non-skeptical cue", "tone": "accent"},
            {"label": "Labeled comments", "value": int(row.get("labeled_comments", 0) or 0), "note": "available for this source", "tone": "sage"},
        ]
    )
    render_hypothesis_cards(
        [
            {
                "title": "H1 skeptical cue effect",
                "metric": _format_proxy_value(row["h1_delta_proxy"]),
                "status": "supported" if pd.notna(row["h1_delta_proxy"]) and float(row["h1_delta_proxy"]) > 0 else "not_supported_or_inconclusive",
                "note": "Positive values mean more response skepticism after skeptical top-ranked cues.",
            },
            {
                "title": "H2 cue magnitude moderation",
                "metric": _format_proxy_value(row["h2_proxy_corr_within_skeptical_cue_videos"]),
                "status": "supported" if pd.notna(row["h2_proxy_corr_within_skeptical_cue_videos"]) and float(row["h2_proxy_corr_within_skeptical_cue_videos"]) > 0 else "inconclusive",
                "note": "This checks whether stronger top-cue popularity aligns with more skeptical follow-up.",
            },
        ]
    )
    render_hypothesis_visuals(summary_row=row, effects_df=effects_df, response_df=response_df)

    left, right = st.columns(2)
    with left:
        st.markdown("**Cue Summary**")
        cue_summary = pd.DataFrame(
            [
                {
                    "metric": "Response skepticism after skeptical top cue",
                    "value": _format_proxy_value(row["response_skepticism_after_skeptical_cue"]),
                },
                {
                    "metric": "Response skepticism after non-skeptical top cue",
                    "value": _format_proxy_value(row["response_skepticism_after_non_skeptical_cue"]),
                },
                {
                    "metric": "H2 proxy correlation within skeptical-cue videos",
                    "value": _format_proxy_value(row["h2_proxy_corr_within_skeptical_cue_videos"]),
                },
            ]
        )
        st.dataframe(cue_summary, use_container_width=True, height=180)
    with right:
        st.markdown("**Niche Snapshot**")
        st.dataframe(niche_df, use_container_width=True, height=180)

    mid_left, mid_right = st.columns(2)
    with mid_left:
        st.markdown("**Model Results**")
        st.dataframe(effects_display, use_container_width=True, height=320)
        st.download_button(
            "Download model effects CSV",
            data=effects_df.to_csv(index=False).encode("utf-8"),
            file_name=f"conformity_effects_run_{selected_run}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with mid_right:
        st.markdown("**ICC / Variance Breakdown**")
        st.dataframe(icc_df, use_container_width=True, height=220)
        with st.expander("Model details"):
            st.text(str(frames["model_summary"]))

    with st.expander("Detailed response frame", expanded=False):
        st.markdown("**Response Comments (ranks 2-20)**")
        resp_cols = [
            "channel_niche",
            "channel_id",
            "video_id",
            "rank",
            "is_skeptical",
            "top_comment_skeptical",
            "top_comment_like_count",
            "top_comment_like_count_z",
            "hours_since_top_comment",
            "comment_text",
        ]
        st.dataframe(response_df[resp_cols], use_container_width=True, height=360)
    d1, d2 = st.columns(2)
    d1.download_button(
        "Download ranked comments CSV",
        data=ranked_df.to_csv(index=False).encode("utf-8"),
        file_name=f"conformity_ranked_run_{selected_run}.csv",
        mime="text/csv",
        use_container_width=True,
    )
    d2.download_button(
        "Download response frame CSV",
        data=response_df.to_csv(index=False).encode("utf-8"),
        file_name=f"conformity_response_run_{selected_run}.csv",
        mime="text/csv",
        use_container_width=True,
    )
    with st.expander("Hypothesis review", expanded=False):
        st.caption("This review uses the same run and evidence source as the main analysis above.")
        _render_hypothesis_review_content(
            conn,
            annotator_id,
            selected_run,
            label_source,
            show_export=True,
        )


def pilot_analysis_tab(conn: sqlite3.Connection, annotator_id: str, show_intro: bool = True) -> None:
    if show_intro:
        render_section_intro(
            "Interpretation layer",
            "Hypothesis review",
            "Translate the underlying cascade outputs into a thesis-ready read: what appears supported, what stays weak, and where the evidence base is still thin.",
        )
    runs = run_df(conn)
    if runs.empty:
        st.info("No runs available.")
        return

    with st.form("pilot_analysis_controls_form"):
        p1, p2 = st.columns(2)
        selected_run = p1.selectbox(
            "Run ID",
            options=runs["id"].tolist(),
            index=0,
            format_func=lambda x: f"Run {x}",
            key="pilot_analysis_run_id",
        )
        label_source = p2.selectbox(
            "Evidence source",
            options=[key for key, _label in LABEL_SOURCE_OPTIONS],
            index=0,
            format_func=_label_source_label,
            key="pilot_label_source",
        )
        st.form_submit_button("Refresh review", use_container_width=True)
    st.caption("Results refresh when you press `Refresh review`.")
    scope_label, scope_body = _label_source_scope(label_source)
    render_evidence_boundary_banner(scope_label, scope_body)
    render_scope_badge(scope_label, "Interpretive review inherits this evidence scope.")
    _render_hypothesis_review_content(
        conn,
        annotator_id,
        selected_run,
        label_source,
        show_export=True,
    )


def combined_hypotheses_tab(conn: sqlite3.Connection, annotator_id: str) -> None:
    render_section_intro(
        "Pooled evidence",
        "Cross-run analysis",
        "Pool multiple runs into one evidence view so the broader pattern is visible without hopping batch by batch.",
    )
    runs = run_df(conn)
    if runs.empty:
        st.info("No runs available.")
        return

    run_options = runs["id"].tolist()
    resolved_defaults = list(resolved_consensus_run_ids(conn))
    default_runs = resolved_defaults if resolved_defaults else (run_options[:2] if len(run_options) >= 2 else run_options)
    with st.form("combined_hypothesis_controls_form"):
        c1, c2, c3 = st.columns([3, 1, 2])
        selected_runs = c1.multiselect(
            "Runs to combine",
            options=run_options,
            default=default_runs,
            format_func=lambda x: f"Run {x}",
            key="combined_hypothesis_runs",
        )
        include_flagged = c2.checkbox(
            "Include filtered-out rows",
            value=False,
            key="combined_hypothesis_include_flagged",
        )
        label_source = c3.selectbox(
            "Evidence source",
            options=[key for key, _label in LABEL_SOURCE_OPTIONS],
            index=0,
            format_func=_label_source_label,
            key="combined_hypothesis_label_source",
        )
        st.form_submit_button("Run pooled analysis", use_container_width=True)
    st.caption("Results refresh when you press `Run pooled analysis`.")
    scope_label, scope_body = _label_source_scope(label_source)
    render_evidence_boundary_banner(scope_label, scope_body)
    render_scope_badge(scope_label, "Pooled analytics and exports below inherit this evidence scope.")

    if not selected_runs:
        st.info("Select at least one run.")
        return

    run_ids = tuple(int(x) for x in selected_runs)
    counts = run_counts_multi(conn, run_ids)
    frames = conformity_frames_multi(conn, run_ids, include_flagged, label_source, annotator_id)
    label_meta = frames.get("label_meta", {})

    render_note_banner(
        "Pooled setup",
        f"Runs {', '.join(str(x) for x in run_ids)} using {label_meta.get('label_source_label', _label_source_label(label_source))}. Skepticism labels available for {int(label_meta.get('skepticism_labeled_comments', 0) or 0)} comments.",
    )
    render_metric_tiles(
        [
            {"label": "Runs", "value": len(run_ids), "note": "currently pooled", "tone": "accent"},
            {"label": "Channels", "value": counts["channels"], "note": "combined channels", "tone": "sage"},
            {"label": "Videos", "value": counts["videos"], "note": "combined videos", "tone": "gold"},
            {"label": "Comments", "value": counts["comments"], "note": "combined comment rows", "tone": "accent"},
            {"label": "Labeled comments", "value": int(label_meta.get("labeled_comments", 0) or 0), "note": "usable under this source", "tone": "sage"},
        ]
    )

    if frames["error"]:
        message = str(frames["error"])
        st.warning(message)
        if "no variation in response dataframe" in message.lower():
            st.info(
                "The selected runs do not have enough variation for the pooled conformity model yet. "
                "This often happens with tiny smoke-test runs like 27. Try resolved-consensus runs instead."
            )
        return

    row = frames["summary_df"].iloc[0]
    render_metric_tiles(
        [
            {"label": "Response comments", "value": int(row["response_comments"]), "note": "ranks 2-20 pooled", "tone": "accent"},
            {"label": "Skeptical top cues", "value": int(row["skeptical_top_comment_videos"]), "note": "videos with skeptical rank-1 cue", "tone": "sage"},
            {"label": "H1 delta", "value": _format_proxy_value(row["h1_delta_proxy"]), "note": "skeptical minus non-skeptical cue", "tone": "gold"},
            {"label": "H2 cue corr", "value": _format_proxy_value(row["h2_proxy_corr_within_skeptical_cue_videos"]), "note": "within skeptical-cue videos", "tone": "accent"},
        ]
    )
    render_hypothesis_cards(
        [
            {
                "title": "H1 pooled skeptical cue effect",
                "metric": _format_proxy_value(row["h1_delta_proxy"]),
                "status": "supported" if pd.notna(row["h1_delta_proxy"]) and float(row["h1_delta_proxy"]) > 0 else "not_supported_or_inconclusive",
                "note": "Positive deltas indicate more skeptical responses after skeptical top-ranked cues.",
            },
            {
                "title": "H2 pooled cue-magnitude moderation",
                "metric": _format_proxy_value(row["h2_proxy_corr_within_skeptical_cue_videos"]),
                "status": "supported" if pd.notna(row["h2_proxy_corr_within_skeptical_cue_videos"]) and float(row["h2_proxy_corr_within_skeptical_cue_videos"]) > 0 else "inconclusive",
                "note": "This remains the harder relationship to detect because skeptical-cue rows are sparse.",
            },
        ]
    )
    render_hypothesis_visuals(summary_row=row, effects_df=frames["effects_df"], response_df=frames["response_df"])

    left, right = st.columns(2)
    with left:
        st.markdown("**Cue Summary**")
        cue_summary = pd.DataFrame(
            [
                {
                    "metric": "Response skepticism after skeptical top cue",
                    "value": _format_proxy_value(row["response_skepticism_after_skeptical_cue"]),
                },
                {
                    "metric": "Response skepticism after non-skeptical top cue",
                    "value": _format_proxy_value(row["response_skepticism_after_non_skeptical_cue"]),
                },
            ]
        )
        st.dataframe(cue_summary, use_container_width=True, height=140)
    with right:
        st.markdown("**Niche Snapshot**")
        st.dataframe(frames["niche_df"], use_container_width=True, height=180)

    mid_left, mid_right = st.columns(2)
    with mid_left:
        st.markdown("**Cross-Run Model Results**")
        st.dataframe(_display_effects_df(frames["effects_df"]), use_container_width=True, height=320)
    with mid_right:
        st.markdown("**ICC / Variance Breakdown**")
        st.dataframe(frames["icc_df"], use_container_width=True, height=220)
        with st.expander("Model details"):
            st.text(str(frames["model_summary"]))

    with st.expander("Detailed pooled response frame", expanded=False):
        st.markdown("**Combined Response Frame (ranks 2-20)**")
        response_cols = [
            "run_id",
            "channel_niche",
            "channel_id",
            "video_id",
            "rank",
            "is_skeptical",
            "top_comment_skeptical",
            "top_comment_like_count",
            "top_comment_like_count_z",
            "hours_since_top_comment",
            "comment_text",
        ]
        st.dataframe(frames["response_df"][response_cols], use_container_width=True, height=360)
    d1, d2 = st.columns(2)
    d1.download_button(
        "Download combined response CSV",
        data=frames["response_df"].to_csv(index=False).encode("utf-8"),
        file_name=f"combined_response_runs_{'_'.join(str(x) for x in run_ids)}.csv",
        mime="text/csv",
        use_container_width=True,
    )
    d2.download_button(
        "Download combined effects CSV",
        data=frames["effects_df"].to_csv(index=False).encode("utf-8"),
        file_name=f"combined_effects_runs_{'_'.join(str(x) for x in run_ids)}.csv",
        mime="text/csv",
        use_container_width=True,
    )


@st.cache_data(ttl=20)
def auto_analysis_frames(_conn: sqlite3.Connection, run_id: int, include_flagged: bool) -> dict[str, pd.DataFrame]:
    return build_auto_analysis_frames(_conn, run_id, include_flagged=include_flagged)


def auto_analysis_tab(conn: sqlite3.Connection, show_intro: bool = True) -> None:
    if show_intro:
        render_section_intro(
            "Screening layer",
            "Comment explorer",
            "Use this space for rapid weak-label screening, multilingual cleanup, and lexical triage before manual coding or formal analysis.",
        )
    runs = run_df(conn)
    if runs.empty:
        st.info("No runs available.")
        return
    render_evidence_boundary_banner(
        "Assistive / exploratory layer",
        "Auto-labeled signals are for screening, lexical cleanup, and follow-up prioritization. They are not the paper's validated evidence layer.",
    )
    render_layer_badge(
        "warning",
        "This view includes exploratory or assistive outputs and should not be used directly for paper-facing claims. Signal detection and triage support only.",
    )

    with st.form("auto_analysis_controls_form"):
        a1, a2 = st.columns([2, 1])
        selected_run = a1.selectbox(
            "Run ID",
            options=runs["id"].tolist(),
            index=0,
            format_func=lambda x: f"Run {x}",
            key="auto_analysis_run_id",
        )
        include_flagged = a2.checkbox(
            "Include filtered-out rows",
            value=False,
            help="Default off. Keep this off for clean pilot analysis.",
            key="auto_analysis_include_flagged",
        )
        st.form_submit_button("Load explorer", use_container_width=True)
    st.caption("Explorer results refresh when you press `Load explorer`.")
    frames = auto_analysis_frames(conn, selected_run, include_flagged)

    summary = frames["summary"]
    comments = frames["comments_auto"]
    videos = frames["videos_auto"]
    video_metrics = frames["video_metrics"]
    channel_metrics = frames["channel_metrics"]
    niche_metrics = frames["niche_metrics"]
    hypothesis_metrics = frames["hypothesis_metrics"]

    if summary.empty:
        st.info("No data available for selected run.")
        return

    row = summary.iloc[0]
    render_metric_tiles(
        [
            {"label": "Channels", "value": int(row["channels"]), "note": f"run {selected_run}", "tone": "accent"},
            {"label": "Videos", "value": int(row["videos"]), "note": "used in explorer", "tone": "sage"},
            {"label": "Comments used", "value": int(row["comments_used"]), "note": "after current clean/flag choice", "tone": "gold"},
            {"label": "AI-mention videos", "value": int(row["ai_mention_videos"]), "note": "rule-detected video context", "tone": "accent"},
            {"label": "Flagged rows", "value": "Included" if int(row["include_flagged"]) else "Excluded", "note": "current explorer mode", "tone": "sage"},
        ]
    )

    left, right = st.columns(2)
    with left:
        st.markdown("**Niche Metrics**")
        if niche_metrics.empty:
            st.info("No niche metrics.")
        else:
            st.dataframe(niche_metrics, use_container_width=True, height=260)
    with right:
        st.markdown("**Signal Metrics (Auto)**")
        if hypothesis_metrics.empty:
            st.info("No hypothesis metrics.")
        else:
            st.dataframe(hypothesis_metrics, use_container_width=True, height=260)

    st.markdown("**Auto-Labeled Comments**")
    if comments.empty:
        st.info("No comments for selected run.")
    else:
        with st.form("auto_analysis_filter_form"):
            f1, f2, f3 = st.columns(3)
            search = f1.text_input("Search comment text", key="auto_analysis_search")
            only_skeptic = f1.checkbox("Only skepticism=1", value=False, key="auto_analysis_only_skeptic")
            only_proof = f2.checkbox("Only proof_demand=1", value=False, key="auto_analysis_only_proof")
            only_norm = f2.checkbox("Only normalization=1", value=False, key="auto_analysis_only_norm")
            language_filter = f3.selectbox(
                "Language filter",
                options=[
                    "All",
                    "Likely English/neutral",
                    "Likely non-English",
                    "Spanish-like",
                    "Hinglish-like",
                    "Other script",
                ],
                index=0,
                key="auto_analysis_language_filter",
            )
            noise_filter = f3.selectbox(
                "Noise filter",
                options=["All", "Exclude low-info/noise", "Only low-info/noise"],
                index=0,
                key="auto_analysis_noise_filter",
            )
            show_trace_cols = st.checkbox(
                "Show explainability columns",
                value=True,
                help="Adds rule-hit and context summaries for each auto-labeled comment.",
                key="auto_analysis_show_trace_cols",
            )
            st.form_submit_button("Apply filters", use_container_width=True)
        st.caption("Table filters update when you press `Apply filters`.")

        filtered = comments.copy()
        if search.strip():
            filtered = filtered[filtered["cleaned_text"].str.contains(search, case=False, na=False)]
        if only_skeptic:
            filtered = filtered[filtered["auto_skepticism"] == 1]
        if only_proof:
            filtered = filtered[filtered["auto_proof_demand"] == 1]
        if only_norm:
            filtered = filtered[filtered["auto_normalization"] == 1]
        if language_filter == "Likely English/neutral":
            filtered = filtered[filtered["heuristic_language"] == "english_or_other_latin"]
        elif language_filter == "Likely non-English":
            filtered = filtered[filtered["heuristic_language"] != "english_or_other_latin"]
        elif language_filter == "Spanish-like":
            filtered = filtered[filtered["heuristic_language"] == "spanish_like"]
        elif language_filter == "Hinglish-like":
            filtered = filtered[filtered["heuristic_language"] == "hinglish_like"]
        elif language_filter == "Other script":
            filtered = filtered[filtered["heuristic_language"] == "other_script"]
        if noise_filter == "Exclude low-info/noise":
            filtered = filtered[filtered["low_info_noise"] == 0]
        elif noise_filter == "Only low-info/noise":
            filtered = filtered[filtered["low_info_noise"] == 1]

        if show_trace_cols and not filtered.empty:
            trace = filtered.apply(
                lambda row: _build_signal_trace(
                    comment_text=row.get("cleaned_text"),
                    title=row.get("title"),
                    description=row.get("description"),
                ),
                axis=1,
            )
            filtered = filtered.copy()
            filtered["auto_suggested_labels"] = trace.apply(lambda x: ", ".join(x["suggested_labels"]) or "none")
            filtered["auto_rule_hits"] = trace.apply(
                lambda x: " | ".join(
                    [
                        f"skepticism: {', '.join(x['skepticism_hits'])}" if x["skepticism_hits"] else "",
                        f"proof: {', '.join(x['proof_hits'])}" if x["proof_hits"] else "",
                        f"normalization: {', '.join(x['normalization_hits'])}" if x["normalization_hits"] else "",
                    ]
                ).strip(" |")
                or "none"
            )
            filtered["auto_context_trace"] = trace.apply(lambda x: "; ".join(x["context_bits"]) or "none")
            filtered["auto_lexical_profile"] = trace.apply(
                lambda x: (
                    f"lang={x['heuristic_language']} | low_info={x['low_info_noise']} | "
                    f"certainty={x['lex_certainty']} doubt={x['lex_doubt']} negation={x['lex_negation']} "
                    f"request={x['lex_request']} affect={x['lex_affect']} social={x['lex_social']}"
                )
            )

        st.caption(f"Rows shown: {len(filtered)}")
        show_cols = [
            "channel_niche",
            "channel_id",
            "video_id",
            "comment_rank",
            "like_count",
            "reply_count",
            "auto_skepticism",
            "auto_proof_demand",
            "auto_normalization",
            "auto_ai_mention",
            "heuristic_language",
            "low_info_noise",
            "cleaned_text",
        ]
        if show_trace_cols:
            show_cols = show_cols[:-1] + [
                "auto_suggested_labels",
                "auto_rule_hits",
                "auto_context_trace",
                "auto_lexical_profile",
                "cleaned_text",
            ]
        st.dataframe(filtered[show_cols], use_container_width=True, height=420)
        st.download_button(
            "Download auto-labeled comments CSV",
            data=filtered.to_csv(index=False).encode("utf-8"),
            file_name=f"auto_comments_run_{selected_run}.csv",
            mime="text/csv",
            use_container_width=True,
        )

    with st.expander("Additional explorer tables", expanded=False):
        st.markdown("**Auto Video Metrics**")
        if video_metrics.empty:
            st.info("No video metrics.")
        else:
            st.dataframe(video_metrics, use_container_width=True, height=320)
            st.download_button(
                "Download auto video-metrics CSV",
                data=video_metrics.to_csv(index=False).encode("utf-8"),
                file_name=f"auto_video_metrics_run_{selected_run}.csv",
                mime="text/csv",
                use_container_width=True,
            )

        if not channel_metrics.empty:
            st.markdown("**Auto Channel Metrics**")
            st.dataframe(channel_metrics, use_container_width=True, height=280)

        if not videos.empty:
            st.markdown("**Auto Video Signals**")
            show_video_cols = [
                "channel_niche",
                "channel_id",
                "video_id",
                "published_at",
                "auto_disclosure_label",
                "auto_has_ai_mention",
                "video_url",
                "title",
            ]
            st.dataframe(videos[show_video_cols], use_container_width=True, height=320)


def exploratory_hub_tab(conn: sqlite3.Connection) -> None:
    render_section_intro(
        "Secondary tools",
        "Exploratory",
        "Keep the paper workflow lean here: open the raw data and search tools only when you actually need them.",
    )
    tool_options = [
        "Scraped Data",
        "Data Exploration",
        "AI Disclosure Search",
        "Comment Explorer",
    ]
    tool_migrations = {
        "Scraped Data": "Scraped Data",
        "Data Exploration": "Data Exploration",
        "AI Disclosure Search": "AI Disclosure Search",
        "Comment Signals": "Comment Explorer",
    }
    current_tool = _safe_text(st.session_state.get("exploratory_tool"))
    if current_tool in tool_migrations:
        st.session_state["exploratory_tool"] = tool_migrations[current_tool]
    selected_tool = st.radio(
        "Exploratory tool",
        options=tool_options,
        horizontal=True,
        key="exploratory_tool",
    )
    if selected_tool == "Scraped Data":
        scraped_data_tab(conn, show_intro=False)
    elif selected_tool == "Data Exploration":
        exploration_tab(conn, show_intro=False)
    elif selected_tool == "AI Disclosure Search":
        disclosure_search_tab(conn, show_intro=False)
    elif selected_tool == "Comment Explorer":
        auto_analysis_tab(conn, show_intro=False)


def annotation_tab(conn: sqlite3.Connection, annotator_id: str) -> None:
    render_section_intro(
        "Coding desk",
        "Manual annotation",
        "Code response comments with the visible rank-1 cue, triage noisy text, and keep the automated hints visible without letting them drive the decision.",
    )
    current_extra_code_options = extra_code_options()
    current_extra_code_ids = _extra_code_ids(current_extra_code_options)
    feedback = st.session_state.pop("annotation_save_feedback", None)
    if isinstance(feedback, dict):
        level = _safe_text(feedback.get("level")).lower()
        message = _safe_text(feedback.get("message"))
        if message:
            if level == "warning":
                st.warning(message)
            else:
                st.success(message)
    runs = run_df(conn)
    run_options = [None] + runs["id"].tolist() if not runs.empty else [None]
    suggested_run_id = _latest_uncoded_run_id(conn, annotator_id)

    quick1, quick2 = st.columns(2)
    if quick1.button("Open latest uncoded run", width="stretch", key="annotation_open_latest_uncoded"):
        _prime_annotation_simple_mode(suggested_run_id)
        st.rerun()
    if quick2.button("Reset manual annotation view", width="stretch", key="annotation_reset_view"):
        _reset_annotation_view_state()
        st.rerun()
    if suggested_run_id is not None:
        st.caption(f"Suggested quick start: `Run {suggested_run_id}` has uncoded comments available for `{annotator_id}`.")

    default_run_value = st.session_state.get("annot_run_id")
    if default_run_value not in run_options:
        if suggested_run_id in run_options:
            default_run_value = suggested_run_id
        elif len(run_options) > 1:
            default_run_value = run_options[1]
        else:
            default_run_value = None
        st.session_state["annot_run_id"] = default_run_value

    subset_files = _list_annotation_subset_files()
    subset_options = ["(none)"] + subset_files
    if st.session_state.get("annotation_subset_file") not in subset_options:
        st.session_state["annotation_subset_file"] = "(none)"

    c1, c2, c3, c4 = st.columns(4)
    selected_run = c1.selectbox(
        "Run ID",
        options=run_options,
        index=run_options.index(default_run_value) if default_run_value in run_options else 0,
        format_func=lambda x: "All" if x is None else f"Run {x}",
        key="annot_run_id",
    )
    batch_size = c2.slider(
        "Comments per page",
        min_value=3,
        max_value=50,
        value=int(st.session_state.get("annotation_batch_size", 6) or 6),
        step=1,
        key="annotation_batch_size",
    )
    limit = c3.slider(
        "Candidate pool cap",
        min_value=200,
        max_value=5000,
        value=int(st.session_state.get("annotation_queue_limit", 1000) or 1000),
        step=200,
        key="annotation_queue_limit",
    )
    workflow_mode = c4.selectbox(
        "Workflow",
        options=["Coding", "Adjudication"],
        index=0,
        key="annotation_workflow_mode",
    )
    _sync_annotation_mode_state(workflow_mode)
    if workflow_mode == "Adjudication":
        render_evidence_boundary_banner(
            "Validation / adjudication mode",
            "Use this mode to resolve coder disagreements and strengthen the validated evidence layer. Adjudication decisions are human-only.",
        )
        render_layer_badge("validated", "Human-only resolution workflow. Adjudication strengthens the validated evidence layer.")
    else:
        render_evidence_boundary_banner(
            "Validated evidence production",
            "Use this mode to create first-pass human labels. Assistive hints may help you navigate the queue, but they do not determine the labels.",
        )
        render_layer_badge("validated", "Coding view for validated evidence production.")
    with st.expander("Core label guide", expanded=False):
        st.markdown(
            "\n".join(
                [
                    "- `Skepticism`: the comment questions authenticity, deception, or whether the content is fake / AI-generated.",
                    "- `Proof-demand`: the comment asks for evidence, disclosure, verification, or a demonstration that the claim/content is real.",
                    "- `Normalization / defense`: the comment dismisses concern, treats the issue as normal/acceptable, or defends the content against skepticism.",
                    "- `Other` and extra tags are descriptive support fields. They help organize review work, but the paper's core evidence layer is built from the three core labels above.",
                ]
            )
        )
    subset_file = st.selectbox(
        "Shared subset file",
        options=subset_options,
        index=0,
        key="annotation_subset_file",
    )

    subset_info = ""
    subset_ids_tuple: tuple[int, ...] | None = None
    if subset_file != "(none)":
        try:
            subset_df = load_annotation_subset_df(subset_file)
            subset_ids_tuple = tuple(int(x) for x in subset_df["comment_db_id"].tolist())
            subset_info = f"Subset loaded: `{Path(subset_file).name}` with `{len(subset_ids_tuple)}` comment IDs."
        except Exception as exc:
            st.error(f"Failed to load subset file: {exc}")
            return

    queue = annotation_queue_df(
        conn,
        annotator_id,
        selected_run,
        comment_ids=subset_ids_tuple,
    )
    if queue.empty:
        st.info("No comments available for annotation yet.")
        if suggested_run_id is not None and selected_run != suggested_run_id:
            if st.button(f"Switch to Run {suggested_run_id}", key="annotation_empty_switch_run"):
                _prime_annotation_simple_mode(suggested_run_id)
                st.rerun()
        if st.button("Reset to simple coding view", key="annotation_empty_reset"):
            _prime_annotation_simple_mode(suggested_run_id)
            st.rerun()
        return

    f1, f2, f3, f4 = st.columns(4)
    only_uncoded_by_me = f1.checkbox("Only uncoded by me", value=(workflow_mode == "Coding"))
    needs_second_coder = f2.checkbox("Only comments with <2 coders", value=False)
    hide_spam = f3.checkbox("Hide spam/template/duplicate", value=True)
    search = f4.text_input("Search comment text", value="", placeholder="keyword or phrase")

    adjudication_filter = "Disagreement only"
    adjudication_source = "manual_adjudication"
    adjudication_note = ""
    show_existing_labels = True
    if workflow_mode == "Adjudication":
        a1, a2 = st.columns(2)
        adjudication_filter = a1.selectbox(
            "Adjudication queue",
            options=[
                "Unresolved disagreement only",
                "All disagreements",
                "Two+ coders",
                "Already adjudicated",
                "Any labeled comment",
            ],
            index=0,
            key="annotation_adjudication_filter",
        )
        show_existing_labels = a2.checkbox(
            "Show saved label summaries",
            value=True,
            key="annotation_show_label_summary",
        )
        show_trace_details = True
        t1, t2 = st.columns([1, 2])
        adjudication_source = t1.selectbox(
            "Resolution source",
            options=["manual_adjudication", "manual_recheck"],
            index=0,
            key="annotation_resolution_source",
        )
        adjudication_note = t2.text_input(
            "Adjudication note",
            value=_safe_text(st.session_state.get("annotation_adjudication_note")),
            placeholder="Optional note on how the disagreement was resolved",
            key="annotation_adjudication_note",
        )
        st.caption("When an existing row is adjudicated, the previous core-label state is preserved on that annotation row for audit.")
    else:
        helper1, helper2 = st.columns(2)
        show_existing_labels = helper1.checkbox(
            "Show saved label summaries",
            value=bool(st.session_state.get("annotation_show_label_summary", False)),
            key="annotation_show_label_summary",
        )
        show_trace_details = helper2.checkbox(
            "Show automation trace details",
            value=bool(st.session_state.get("annotation_show_trace_details", False)),
            key="annotation_show_trace_details",
        )

    tri1, tri2, tri3 = st.columns(3)
    priority_mode = tri1.selectbox(
        "Priority strategy",
        options=["Active learning", "Triage only", "Signal first", "Coverage first"],
        index=0,
        key="annotation_priority_mode",
        help="Active learning balances uncertainty, rule hints, AI context, and cue relevance.",
    )
    triage_mode = tri2.selectbox(
        "Triage queue",
        options=["Unsure first", "All", "Unsure only", "Obvious only"],
        index=0,
        key="annotation_triage_mode",
    )
    triage_cutoff = tri3.slider(
        "Unsure score cutoff",
        min_value=0.50,
        max_value=0.95,
        value=0.75,
        step=0.05,
        key="annotation_triage_cutoff",
    )
    div1, div2 = st.columns(2)
    diversity_video_cap = div1.slider(
        "Max comments per video in queue",
        min_value=0,
        max_value=5,
        value=2,
        step=1,
        key="annotation_diversity_video_cap",
        help="Set 0 to disable. Helps avoid repeated comments from the same video.",
        disabled=(workflow_mode != "Coding"),
    )
    diversity_channel_cap = div2.slider(
        "Max comments per channel in queue",
        min_value=0,
        max_value=10,
        value=6,
        step=1,
        key="annotation_diversity_channel_cap",
        help="Set 0 to disable. Helps spread annotation effort across channels.",
        disabled=(workflow_mode != "Coding"),
    )
    ai_focus_mode = st.selectbox(
        "AI focus",
        options=[
            "All comments",
            "Only AI-signal comments",
            "Only AI-signal videos",
            "AI-signal comments OR videos",
        ],
        index=0,
        key="annotation_ai_focus_mode",
    )
    text_quality_mode = st.selectbox(
        "Text quality filter",
        options=[
            "All comments",
            "Exclude low-info/noise",
            "Only low-info/noise",
            "Likely non-English only",
            "Likely English/neutral only",
        ],
        index=0,
        key="annotation_text_quality_mode",
    )

    niches = sorted(queue["channel_niche"].dropna().unique().tolist())
    selected_niches = st.multiselect(
        "Niche filter",
        options=niches,
        default=niches,
        key="annotation_niche_filter",
    )

    filtered = queue.copy()
    filter_counts: list[tuple[str, int]] = [("Queue loaded", len(filtered))]
    if subset_file != "(none)":
        filter_counts.append(("After subset file", len(filtered)))
    if selected_niches:
        filtered = filtered[filtered["channel_niche"].isin(selected_niches)]
        filter_counts.append(("After niche filter", len(filtered)))
    if workflow_mode == "Coding" and only_uncoded_by_me:
        filtered = filtered[filtered["my_coded_at"].isna()]
        filter_counts.append(("After uncoded-by-me filter", len(filtered)))
    if workflow_mode == "Coding" and needs_second_coder:
        filtered = filtered[filtered["coder_count"] < 2]
        filter_counts.append(("After <2 coders filter", len(filtered)))
    if workflow_mode == "Adjudication":
        if adjudication_filter == "Unresolved disagreement only":
            filtered = filtered[(filtered["any_disagreement"] == 1) & (filtered["has_adjudicated"] == 0)]
        elif adjudication_filter == "All disagreements":
            filtered = filtered[filtered["any_disagreement"] == 1]
        elif adjudication_filter == "Two+ coders":
            filtered = filtered[filtered["coder_count"] >= 2]
        elif adjudication_filter == "Already adjudicated":
            filtered = filtered[filtered["has_adjudicated"] == 1]
        elif adjudication_filter == "Any labeled comment":
            filtered = filtered[filtered["coder_count"] >= 1]
        filter_counts.append((f"After adjudication filter ({adjudication_filter})", len(filtered)))
    if hide_spam:
        filtered = filtered[
            (filtered["is_spam"] == 0)
            & (filtered["is_template"] == 0)
            & (filtered["is_duplicate"] == 0)
        ]
        filter_counts.append(("After hide spam/template/duplicate", len(filtered)))
    if search.strip():
        filtered = filtered[filtered["cleaned_text"].str.contains(search, case=False, na=False)]
        filter_counts.append(("After search", len(filtered)))

    if not filtered.empty:
        top_context = top_ranked_comments_df(conn, selected_run)
        if not top_context.empty:
            top_context = _prepare_comment_rule_frame(top_context)
            top_context = top_context.rename(
                columns={
                    "comment_db_id": "top_comment_db_id",
                    "like_count": "top_like_count",
                    "reply_count": "top_reply_count",
                    "cleaned_text": "top_comment_text",
                    "comment_timestamp": "top_comment_timestamp",
                    "rule_skepticism": "top_rule_skepticism",
                    "rule_proof_demand": "top_rule_proof_demand",
                    "rule_normalization": "top_rule_normalization",
                }
            )
            filtered = filtered.merge(
                top_context[
                    [
                        "run_id",
                        "video_id",
                        "top_comment_db_id",
                        "top_like_count",
                        "top_reply_count",
                        "top_comment_timestamp",
                        "top_comment_text",
                        "top_rule_skepticism",
                        "top_rule_proof_demand",
                        "top_rule_normalization",
                    ]
                ],
                on=["run_id", "video_id"],
                how="left",
            )
        filtered = filtered.copy()
        filtered = append_comment_text_features(filtered, text_col="cleaned_text")
        filtered["comment_ai_signal"] = filtered["cleaned_text"].fillna("").str.contains(AI_MENTION_REGEX, na=False)
        filtered["video_ai_signal"] = (
            (filtered["title"].fillna("") + " " + filtered["description"].fillna("")).str.contains(
                AI_MENTION_REGEX, na=False
            )
        )
        if ai_focus_mode == "Only AI-signal comments":
            filtered = filtered[filtered["comment_ai_signal"]]
        elif ai_focus_mode == "Only AI-signal videos":
            filtered = filtered[filtered["video_ai_signal"]]
        elif ai_focus_mode == "AI-signal comments OR videos":
            filtered = filtered[filtered["comment_ai_signal"] | filtered["video_ai_signal"]]
        filter_counts.append((f"After AI focus ({ai_focus_mode})", len(filtered)))
        if text_quality_mode == "Exclude low-info/noise":
            filtered = filtered[filtered["low_info_noise"] == 0]
        elif text_quality_mode == "Only low-info/noise":
            filtered = filtered[filtered["low_info_noise"] == 1]
        elif text_quality_mode == "Likely non-English only":
            filtered = filtered[filtered["heuristic_language"] != "english_or_other_latin"]
        elif text_quality_mode == "Likely English/neutral only":
            filtered = filtered[filtered["heuristic_language"] == "english_or_other_latin"]
        filter_counts.append((f"After text quality ({text_quality_mode})", len(filtered)))

    if not filtered.empty:
        triage = filtered["cleaned_text"].apply(_triage_comment_uncertainty)
        filtered = filtered.copy()
        filtered["triage_bucket"] = triage.apply(lambda x: x[0])
        filtered["triage_score"] = triage.apply(lambda x: float(x[1]))
        filtered["triage_hints_list"] = triage.apply(lambda x: x[2])
        filtered["triage_hints"] = triage.apply(lambda x: ", ".join(x[2]))

        if triage_mode == "Unsure only":
            filtered = filtered[filtered["triage_score"] >= float(triage_cutoff)]
        elif triage_mode == "Obvious only":
            filtered = filtered[filtered["triage_score"] <= 0.25]
        filter_counts.append((f"After triage ({triage_mode})", len(filtered)))

    if not filtered.empty:
        normalized_priority_mode = priority_mode.lower().replace(" ", "_")
        priority = filtered.apply(
            lambda row: _annotation_priority_details(
                triage_bucket=_safe_text(row.get("triage_bucket")),
                triage_score=float(row.get("triage_score") or 0.0),
                triage_hints=row.get("triage_hints_list") if isinstance(row.get("triage_hints_list"), list) else [],
                comment_ai_signal=bool(row.get("comment_ai_signal")),
                video_ai_signal=bool(row.get("video_ai_signal")),
                top_rule_skepticism=int(row.get("top_rule_skepticism") or 0),
                comment_rank=int(row.get("comment_rank") or 0),
                like_count=int(row.get("like_count") or 0),
                reply_count=int(row.get("reply_count") or 0),
                priority_mode=normalized_priority_mode,
            ),
            axis=1,
        )
        filtered = filtered.copy()
        filtered["priority_bucket"] = priority.apply(lambda x: x[0])
        filtered["priority_score"] = priority.apply(lambda x: float(x[1]))
        filtered["priority_reason"] = priority.apply(lambda x: x[2])
        if triage_mode == "Unsure first":
            filtered = filtered.sort_values(
                ["priority_score", "triage_score", "comment_db_id"],
                ascending=[False, False, True],
            )
        elif priority_mode != "Triage only":
            filtered = filtered.sort_values(["priority_score", "comment_db_id"], ascending=[False, True])
        else:
            filtered = filtered.sort_values(["triage_score", "comment_db_id"], ascending=[False, True])

        if workflow_mode == "Coding" and (diversity_video_cap > 0 or diversity_channel_cap > 0):
            filtered = _apply_diversity_caps(
                filtered,
                max_per_video=int(diversity_video_cap),
                max_per_channel=int(diversity_channel_cap),
            )
            filter_counts.append(
                (
                    f"After diversity caps (video={diversity_video_cap}, channel={diversity_channel_cap})",
                    len(filtered),
                )
            )
        if limit > 0 and len(filtered) > int(limit):
            filtered = filtered.head(int(limit)).copy()
            filter_counts.append((f"After candidate cap ({int(limit)})", len(filtered)))
        filtered["priority_rank"] = range(1, len(filtered) + 1)

    coded_by_me = int(queue["my_coded_at"].notna().sum())
    unsure_rows = int((filtered["triage_score"] >= float(triage_cutoff)).sum()) if not filtered.empty else 0
    ai_rows = int((filtered["comment_ai_signal"] | filtered["video_ai_signal"]).sum()) if not filtered.empty else 0
    non_english_rows = int((filtered["heuristic_language"] != "english_or_other_latin").sum()) if not filtered.empty else 0
    low_info_rows = int(filtered["low_info_noise"].sum()) if not filtered.empty else 0
    disagreement_rows = int(filtered["any_disagreement"].sum()) if not filtered.empty else 0
    adjudicated_rows = int(filtered["has_adjudicated"].sum()) if not filtered.empty else 0
    priority_rows = int((filtered["priority_bucket"] != "Coverage fill").sum()) if not filtered.empty else 0
    c1, c2, c3, c4, c5, c6, c7, c8, c9, c10 = st.columns(10)
    c1.metric("Queue loaded", len(queue))
    c2.metric("Already coded by me", coded_by_me)
    c3.metric("Current filtered rows", len(filtered))
    c4.metric("Unsure rows", unsure_rows)
    c5.metric("AI-signal rows", ai_rows)
    c6.metric("Non-English rows", non_english_rows)
    c7.metric("Low-info rows", low_info_rows)
    c8.metric("Disagreement rows", disagreement_rows)
    c9.metric("Adjudicated rows", adjudicated_rows)
    c10.metric("Priority rows", priority_rows)
    if subset_info:
        st.caption(subset_info)
    st.caption(
        f"Priority strategy: `{priority_mode}`"
        + (
            f" | diversity caps video `{diversity_video_cap}`, channel `{diversity_channel_cap}`"
            if workflow_mode == "Coding"
            else ""
        )
    )

    if filtered.empty:
        st.info("No comments match current filters.")
        st.caption(
            "Try `Run ID = All`, `Workflow = Coding`, `AI focus = All comments`, `Triage queue = All`, and clear `Search`."
        )
        diag_df = pd.DataFrame(filter_counts, columns=["filter_step", "rows_left"])
        st.dataframe(diag_df, use_container_width=True, height=min(420, 35 * len(diag_df) + 40))
        action1, action2 = st.columns(2)
        if action1.button("Reset to simple coding view", key="annotation_filtered_reset", width="stretch"):
            _prime_annotation_simple_mode(suggested_run_id)
            st.rerun()
        if suggested_run_id is not None and selected_run != suggested_run_id:
            if action2.button(
                f"Open Run {suggested_run_id}",
                key="annotation_filtered_switch_run",
                width="stretch",
            ):
                _prime_annotation_simple_mode(suggested_run_id)
                st.rerun()
        return

    total_pages = (len(filtered) + batch_size - 1) // batch_size
    page = st.number_input("Page", min_value=1, max_value=total_pages, value=1, step=1)
    start_idx = (int(page) - 1) * batch_size
    page_df = filtered.iloc[start_idx : start_idx + batch_size].copy()
    st.caption(f"Showing comments {start_idx + 1}-{start_idx + len(page_df)} of {len(filtered)}")

    with st.form("annotation_batch_form"):
        if workflow_mode == "Adjudication":
            save_as_adjudicated = True
            st.info(
                f"Saving this page will mark the rows as adjudicated under `{annotator_id}`."
            )
        else:
            save_as_adjudicated = st.checkbox(
                "Mark all saved labels on this page as adjudicated",
                help="Leave this off for normal first-pass coding.",
                key="annotation_save_as_adjudicated",
            )
        payload: list[dict[str, object]] = []
        for _, row in page_df.iterrows():
            comment_db_id = int(row["comment_db_id"])
            comment_text = _safe_text(row["cleaned_text"])
            suggested = []
            if SKEPTICISM_REGEX.search(comment_text):
                suggested.append("skepticism")
            if PROOF_DEMAND_REGEX.search(comment_text):
                suggested.append("proof-demand")
            if NORMALIZATION_REGEX.search(comment_text):
                suggested.append("normalization")

            default_s = bool(_bool01(row.get("my_skepticism")))
            default_p = bool(_bool01(row.get("my_proof_demand")))
            default_n = bool(_bool01(row.get("my_normalization_defense")))
            default_other = bool(_bool01(row.get("my_other_flag")))
            default_other_text = _safe_text(row.get("my_other_text"))
            default_extra = [x for x in _parse_extra_codes(row.get("my_extra_codes")) if x in current_extra_code_ids]

            left, right = st.columns([3, 2])
            with left:
                triage_bucket = _safe_text(row.get("triage_bucket")) or "n/a"
                triage_score = float(row.get("triage_score") or 0.0)
                priority_bucket = _safe_text(row.get("priority_bucket")) or "Coverage fill"
                priority_score = float(row.get("priority_score") or 0.0)
                priority_rank = int(row.get("priority_rank") or 0)
                st.markdown(
                    f"**Comment #{comment_db_id}** | run `{row['run_id']}` | "
                    f"`{row['channel_id']}` ({row['channel_niche']}) | "
                    f"video `{row['video_id']}` | rank `{row['comment_rank']}` | "
                    f"likes `{row['like_count']}` replies `{row['reply_count']}` | "
                    f"coders `{row['coder_count']}` | triage `{triage_bucket}` ({triage_score:.2f}) | "
                    f"priority `{priority_bucket}` #{priority_rank} ({priority_score:.2f})"
                )
                st.markdown(f"**Title:** {_safe_text(row['title']) or '(no title)'}")
                top_comment_text = _safe_text(row.get("top_comment_text"))
                if top_comment_text:
                    top_comment_id = int(row["top_comment_db_id"]) if pd.notna(row.get("top_comment_db_id")) else 0
                    top_like_count = int(row["top_like_count"]) if pd.notna(row.get("top_like_count")) else 0
                    top_rule_skepticism = int(row["top_rule_skepticism"]) if pd.notna(row.get("top_rule_skepticism")) else 0
                    top_rule_proof = int(row["top_rule_proof_demand"]) if pd.notna(row.get("top_rule_proof_demand")) else 0
                    st.caption(
                        f"Top cue | comment `{top_comment_id}` | "
                        f"likes `{top_like_count}` | "
                        f"skepticism `{top_rule_skepticism}` | "
                        f"proof `{top_rule_proof}`"
                    )
                    st.warning(top_comment_text)
                st.info(comment_text)
                if suggested:
                    st.caption("Rule hints: " + ", ".join(suggested))
                triage_hints = _safe_text(row.get("triage_hints"))
                if triage_hints:
                    st.caption("Triage hints: " + triage_hints)
                priority_reason = _safe_text(row.get("priority_reason"))
                if priority_reason:
                    st.caption("Priority rationale: " + priority_reason)
                if show_trace_details:
                    trace = _build_signal_trace(
                        comment_text=comment_text,
                        title=row.get("title"),
                        description=row.get("description"),
                        triage_bucket=_safe_text(row.get("triage_bucket")),
                        triage_score=float(row.get("triage_score") or 0.0),
                        triage_hints=row.get("triage_hints_list")
                        if isinstance(row.get("triage_hints_list"), list)
                        else [],
                        top_rule_skepticism=int(row.get("top_rule_skepticism") or 0),
                        comment_rank=int(row.get("comment_rank") or 0),
                    )
                    with st.expander("Automation trace"):
                        st.markdown(
                            f"**Suggested auto labels:** {', '.join(trace['suggested_labels']) if trace['suggested_labels'] else 'none'}"
                        )
                        st.markdown(
                            f"**Rule hits:** skepticism `{', '.join(trace['skepticism_hits']) or 'none'}` | "
                            f"proof `{', '.join(trace['proof_hits']) or 'none'}` | "
                            f"normalization `{', '.join(trace['normalization_hits']) or 'none'}`"
                        )
                        st.markdown(
                            f"**AI / disclosure context:** comment AI `{', '.join(trace['comment_ai_hits']) or 'none'}` | "
                            f"video AI `{', '.join(trace['video_ai_hits']) or 'none'}` | "
                            f"video disclosure `{trace['disclosure_label']}`"
                        )
                        st.markdown(
                            f"**Language / lexical profile:** language `{trace['heuristic_language']}` | "
                            f"low-info `{trace['low_info_noise']}` | "
                            f"certainty `{trace['lex_certainty']}` | doubt `{trace['lex_doubt']}` | "
                            f"negation `{trace['lex_negation']}` | request `{trace['lex_request']}` | "
                            f"affect `{trace['lex_affect']}` | social `{trace['lex_social']}`"
                        )
                        st.markdown(
                            f"**Trace summary:** {_safe_text(trace['summary'])}"
                        )
                if show_existing_labels:
                    label_summary = _safe_text(row.get("label_summary"))
                    adjudicated_summary = _safe_text(row.get("adjudicated_summary"))
                    if label_summary:
                        st.caption("Saved labels: " + label_summary)
                    if adjudicated_summary:
                        st.caption("Adjudicated labels: " + adjudicated_summary)
                    saved_resolution_source = _safe_text(row.get("my_resolution_source"))
                    saved_adjudication_note = _safe_text(row.get("my_adjudication_note"))
                    saved_adjudicated_at = _safe_text(row.get("my_adjudicated_at"))
                    if saved_resolution_source or saved_adjudication_note or saved_adjudicated_at:
                        trace_parts = []
                        if saved_resolution_source:
                            trace_parts.append(f"source `{saved_resolution_source}`")
                        if saved_adjudicated_at:
                            trace_parts.append(f"at `{saved_adjudicated_at}`")
                        if int(row.get("my_was_disagreement_detected") or 0) == 1:
                            trace_parts.append("disagreement detected before resolution")
                        if trace_parts:
                            st.caption("Adjudication trace: " + " | ".join(trace_parts))
                        if saved_adjudication_note:
                            st.caption("Adjudication note: " + saved_adjudication_note)
                    pre_s = row.get("my_pre_adjudication_skepticism")
                    pre_p = row.get("my_pre_adjudication_proof_demand")
                    pre_n = row.get("my_pre_adjudication_normalization")
                    if pd.notna(pre_s) or pd.notna(pre_p) or pd.notna(pre_n):
                        st.caption(
                            "Preserved pre-adjudication core labels: "
                            + f"s={int(pre_s) if pd.notna(pre_s) else 'n/a'}, "
                            + f"p={int(pre_p) if pd.notna(pre_p) else 'n/a'}, "
                            + f"n={int(pre_n) if pd.notna(pre_n) else 'n/a'}"
                        )
                disagreement_bits = []
                if int(row.get("skepticism_disagreement") or 0) == 1:
                    disagreement_bits.append("skepticism")
                if int(row.get("proof_disagreement") or 0) == 1:
                    disagreement_bits.append("proof")
                if int(row.get("normalization_disagreement") or 0) == 1:
                    disagreement_bits.append("normalization")
                if int(row.get("other_disagreement") or 0) == 1:
                    disagreement_bits.append("other")
                if int(row.get("extra_codes_disagreement") or 0) == 1:
                    disagreement_bits.append("extra tags")
                if disagreement_bits:
                    st.caption("Disagreement flags: " + ", ".join(disagreement_bits))

            with right:
                skepticism = st.checkbox(
                    "Skepticism/Fake-Callout",
                    value=default_s,
                    key=f"ann_s_{comment_db_id}",
                )
                proof = st.checkbox(
                    "Proof-Demand",
                    value=default_p,
                    key=f"ann_p_{comment_db_id}",
                )
                defense = st.checkbox(
                    "Normalization/Defense",
                    value=default_n,
                    key=f"ann_n_{comment_db_id}",
                )
                st.markdown("**Extra tags**")
                selected_extra_codes: list[str] = []
                for i in range(0, len(current_extra_code_options), 3):
                    row_options = current_extra_code_options[i : i + 3]
                    cols = st.columns(3)
                    for j, (tag_code, tag_label) in enumerate(row_options):
                        is_checked = cols[j].checkbox(
                            tag_label,
                            value=(tag_code in default_extra),
                            key=f"ann_tag_{comment_db_id}_{tag_code}",
                        )
                        if is_checked:
                            selected_extra_codes.append(tag_code)
                other_flag = st.checkbox(
                    "Other",
                    value=default_other,
                    key=f"ann_other_flag_{comment_db_id}",
                )
                other_text = st.text_input(
                    "Other details",
                    value=default_other_text,
                    key=f"ann_other_text_{comment_db_id}",
                    disabled=not other_flag,
                )
                st.caption(
                    "Human vs auto: "
                    + _human_override_summary(
                        auto_labels=suggested,
                        skepticism_value=bool(skepticism),
                        proof_value=bool(proof),
                        normalization_value=bool(defense),
                    )
                )

            payload.append(
                {
                    "comment_db_id": comment_db_id,
                    "annotator_id": annotator_id,
                    "skepticism": int(skepticism),
                    "proof_demand": int(proof),
                    "normalization": int(defense),
                    "extra_codes": selected_extra_codes,
                    "other_flag": int(other_flag),
                    "other_text": other_text,
                    "is_adjudicated": int(save_as_adjudicated),
                    "workflow_mode": workflow_mode,
                    "triage_bucket": _safe_text(row.get("triage_bucket")),
                    "triage_score": _optional_float(row.get("triage_score")),
                    "priority_bucket": _safe_text(row.get("priority_bucket")),
                    "priority_score": _optional_float(row.get("priority_score")),
                    "heuristic_language": _safe_text(row.get("heuristic_language")),
                    "low_info_noise": int(row.get("low_info_noise") or 0),
                    "comment_ai_signal": int(bool(row.get("comment_ai_signal"))),
                    "video_ai_signal": int(bool(row.get("video_ai_signal"))),
                    "was_disagreement_detected": int(row.get("any_disagreement") or 0),
                    "resolution_source": adjudication_source if save_as_adjudicated else "",
                    "adjudication_note": adjudication_note if save_as_adjudicated else "",
                }
            )
            st.divider()

        submit_label = "Save Adjudication Page" if workflow_mode == "Adjudication" else "Save This Page"
        submitted = st.form_submit_button(submit_label, use_container_width=True)

    if submitted:
        saved = save_annotations_batch(conn, payload)
        _clear_cached_frames()
        if save_as_adjudicated:
            st.session_state["annotation_save_feedback"] = {
                "level": "success",
                "message": f"Saved and adjudicated {saved} annotations.",
            }
        else:
            st.session_state["annotation_save_feedback"] = {
                "level": "warning",
                "message": f"Saved {saved} annotations, but they were not marked as adjudicated.",
            }
        st.rerun()


def main() -> None:
    config = load_config()
    init_database(config)
    users = config.local_auth_users
    inject_app_theme()

    if not users:
        st.error("No LOCAL_AUTH_USERS configured. Check .env")
        return

    auth_ok, annotator_id = authenticate(users)
    if not auth_ok or not annotator_id:
        st.warning("Please sign in from the sidebar.")
        return

    conn = get_connection(str(config.database_path))
    render_masthead(
        "YouTube Research Console",
        "A human-in-the-loop research system for scraping, coding, and interpreting verification signals around generative-AI content.",
        [
            ("Signed in", annotator_id),
            ("Database", Path(config.database_path).name),
            ("Core evidence", "900 resolved comments"),
            ("Mode", "Analysis and coding"),
        ],
    )

    section_options = [
        "Run Lab",
        "Main Analysis",
        "Cross-Run Analysis",
        "Exploratory",
        "Manual Annotation",
    ]
    section_migrations = {
        "Overview": "Run Lab",
        "Scraped Data": "Exploratory",
        "Data Exploration": "Exploratory",
        "Conformity Cascade": "Main Analysis",
        "Hypothesis Readout": "Main Analysis",
        "Hypothesis Review": "Main Analysis",
        "Combined Hypotheses": "Cross-Run Analysis",
        "AI Disclosure Search": "Exploratory",
        "Comment Signals": "Exploratory",
        "Comment Explorer": "Exploratory",
    }
    current_section = _safe_text(st.session_state.get("active_workspace_section"))
    if current_section in section_migrations:
        st.session_state["active_workspace_section"] = section_migrations[current_section]
    active_section = st.radio(
        "Workspace section",
        options=section_options,
        horizontal=True,
        key="active_workspace_section",
        label_visibility="collapsed",
    )

    if active_section == "Run Lab":
        run_lab_tab(conn, config, annotator_id)
    elif active_section == "Main Analysis":
        conformity_cascade_tab(conn, annotator_id)
    elif active_section == "Cross-Run Analysis":
        combined_hypotheses_tab(conn, annotator_id)
    elif active_section == "Exploratory":
        exploratory_hub_tab(conn)
    elif active_section == "Manual Annotation":
        annotation_tab(conn, annotator_id)


if __name__ == "__main__":
    main()
