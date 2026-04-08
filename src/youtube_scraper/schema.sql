PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_uuid TEXT NOT NULL UNIQUE,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('running','completed','failed')),
    execution_mode TEXT NOT NULL CHECK(execution_mode IN ('auto','api_only','playwright_only')),
    run_truncated INTEGER NOT NULL DEFAULT 0 CHECK(run_truncated IN (0,1)),
    spam_ruleset_version TEXT NOT NULL,
    rules_version TEXT,
    scoring_version TEXT,
    preprocessing_profile TEXT,
    compliance_reference TEXT NOT NULL,
    api_quota_limit INTEGER NOT NULL,
    api_failover_threshold REAL NOT NULL,
    api_units_used INTEGER NOT NULL DEFAULT 0,
    api_comment_count INTEGER NOT NULL DEFAULT 0,
    playwright_comment_count INTEGER NOT NULL DEFAULT 0,
    content_type TEXT,
    target_file TEXT,
    target_count_requested INTEGER,
    study_profile_name TEXT,
    run_payload_json TEXT,
    notes TEXT,
    app_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id TEXT NOT NULL UNIQUE,
    channel_url TEXT,
    niche TEXT NOT NULL,
    coverage_shortfall INTEGER NOT NULL DEFAULT 0 CHECK(coverage_shortfall IN (0,1)),
    no_shorts_available INTEGER NOT NULL DEFAULT 0 CHECK(no_shorts_available IN (0,1)),
    extraction_failed INTEGER NOT NULL DEFAULT 0 CHECK(extraction_failed IN (0,1)),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    run_id INTEGER NOT NULL,
    channel_db_id INTEGER NOT NULL,
    video_url TEXT,
    title TEXT,
    description TEXT,
    published_at TEXT,
    upload_index INTEGER,
    comment_status TEXT NOT NULL CHECK(comment_status IN ('ok','not_enough_comments','comments_disabled','extraction_failed')),
    view_count INTEGER,
    disclosure_quality INTEGER CHECK(disclosure_quality BETWEEN 0 AND 3),
    collection_engine TEXT CHECK(collection_engine IN ('api','ytdlp','playwright')),
    comments_scanned INTEGER,
    comments_saved INTEGER,
    comments_filtered INTEGER,
    failure_reason TEXT,
    extracted_at TEXT NOT NULL,
    extraction_failed INTEGER NOT NULL DEFAULT 0 CHECK(extraction_failed IN (0,1)),
    UNIQUE(video_id, run_id),
    FOREIGN KEY(run_id) REFERENCES runs(id),
    FOREIGN KEY(channel_db_id) REFERENCES channels(id)
);

CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    channel_db_id INTEGER NOT NULL,
    video_db_id INTEGER NOT NULL,
    comment_id TEXT,
    commenter_hash_id TEXT,
    raw_text TEXT NOT NULL,
    cleaned_text TEXT NOT NULL,
    like_count INTEGER NOT NULL,
    reply_count INTEGER NOT NULL,
    published_at TEXT,
    language TEXT,
    comment_rank INTEGER NOT NULL,
    is_spam INTEGER NOT NULL DEFAULT 0 CHECK(is_spam IN (0,1)),
    is_template INTEGER NOT NULL DEFAULT 0 CHECK(is_template IN (0,1)),
    is_duplicate INTEGER NOT NULL DEFAULT 0 CHECK(is_duplicate IN (0,1)),
    spam_rule_hits TEXT,
    source_engine TEXT NOT NULL CHECK(source_engine IN ('api','playwright')),
    extraction_ts TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id),
    FOREIGN KEY(channel_db_id) REFERENCES channels(id),
    FOREIGN KEY(video_db_id) REFERENCES videos(id)
);

CREATE TABLE IF NOT EXISTS annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    comment_db_id INTEGER NOT NULL,
    annotator_id TEXT NOT NULL,
    coded_at TEXT NOT NULL,
    skepticism_fake_callout INTEGER NOT NULL CHECK(skepticism_fake_callout IN (0,1)),
    proof_demand INTEGER NOT NULL CHECK(proof_demand IN (0,1)),
    normalization_defense INTEGER NOT NULL CHECK(normalization_defense IN (0,1)),
    extra_codes TEXT,
    other_flag INTEGER NOT NULL DEFAULT 0 CHECK(other_flag IN (0,1)),
    other_text TEXT,
    is_adjudicated INTEGER NOT NULL DEFAULT 0 CHECK(is_adjudicated IN (0,1)),
    workflow_mode TEXT,
    triage_bucket TEXT,
    triage_score REAL,
    priority_bucket TEXT,
    priority_score REAL,
    heuristic_language TEXT,
    low_info_noise INTEGER,
    comment_ai_signal INTEGER,
    video_ai_signal INTEGER,
    was_disagreement_detected INTEGER,
    resolution_source TEXT,
    adjudication_note TEXT,
    adjudicated_at TEXT,
    pre_adjudication_skepticism INTEGER,
    pre_adjudication_proof_demand INTEGER,
    pre_adjudication_normalization INTEGER,
    UNIQUE(comment_db_id, annotator_id),
    FOREIGN KEY(comment_db_id) REFERENCES comments(id)
);

CREATE TABLE IF NOT EXISTS qa_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES runs(id)
);

CREATE TABLE IF NOT EXISTS exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    freeze_id INTEGER,
    exported_at TEXT NOT NULL,
    export_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    rules_version TEXT,
    scoring_version TEXT,
    preprocessing_profile TEXT,
    FOREIGN KEY(run_id) REFERENCES runs(id),
    FOREIGN KEY(freeze_id) REFERENCES evidence_freezes(id)
);

CREATE TABLE IF NOT EXISTS study_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    owner TEXT NOT NULL,
    description TEXT,
    profile_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner, name)
);

CREATE TABLE IF NOT EXISTS evidence_freezes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    freeze_uuid TEXT,
    name TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    notes TEXT,
    rules_version TEXT,
    scoring_version TEXT,
    preprocessing_profile TEXT,
    run_ids_json TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    prevalence_overall_json TEXT NOT NULL,
    prevalence_by_run_niche_json TEXT NOT NULL,
    UNIQUE(created_by, name)
);

CREATE INDEX IF NOT EXISTS idx_videos_run_id ON videos(run_id);
CREATE INDEX IF NOT EXISTS idx_comments_run_id ON comments(run_id);
CREATE INDEX IF NOT EXISTS idx_comments_video ON comments(video_db_id);
CREATE INDEX IF NOT EXISTS idx_comments_channel ON comments(channel_db_id);
CREATE INDEX IF NOT EXISTS idx_comments_flags ON comments(is_spam, is_template, is_duplicate);
CREATE INDEX IF NOT EXISTS idx_annotations_comment ON annotations(comment_db_id);
CREATE INDEX IF NOT EXISTS idx_study_profiles_owner ON study_profiles(owner);
CREATE INDEX IF NOT EXISTS idx_evidence_freezes_owner ON evidence_freezes(created_by);
