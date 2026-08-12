PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS datasets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_uuid TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    source_path TEXT,
    source_format TEXT,
    row_count INTEGER NOT NULL DEFAULT 0,
    mapping_json TEXT NOT NULL,
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER NOT NULL,
    material_uid TEXT NOT NULL,
    run_id TEXT,
    output_path TEXT,
    product_id TEXT,
    product_name TEXT,
    material_type TEXT,
    engine TEXT,
    model TEXT,
    temperature TEXT,
    time_of_day_label TEXT,
    repetition_id TEXT,
    scheduled_day_of_week TEXT,
    prompt TEXT,
    material_text TEXT NOT NULL,
    product_ground_truth TEXT,
    expected_claims TEXT,
    prohibited_claims TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    UNIQUE(dataset_id, material_uid),
    FOREIGN KEY(dataset_id) REFERENCES datasets(id)
);

CREATE TABLE IF NOT EXISTS judge_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL,
    judge_name TEXT NOT NULL,
    approach TEXT NOT NULL,
    judge_model TEXT,
    assessment_status TEXT NOT NULL
        CHECK(assessment_status IN ('completed','error','timeout','not_run','abandoned','unknown')),
    is_noncompliant INTEGER CHECK(is_noncompliant IN (0,1)),
    violation_count INTEGER,
    max_severity TEXT,
    raw_label TEXT,
    rationale TEXT,
    source_record_id TEXT,
    raw_payload_json TEXT NOT NULL DEFAULT '{}',
    assessed_at TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(material_id, judge_name, approach),
    FOREIGN KEY(material_id) REFERENCES materials(id)
);

CREATE TABLE IF NOT EXISTS violation_findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER,
    review_id INTEGER,
    material_id INTEGER NOT NULL,
    finding_uid TEXT,
    source_type TEXT NOT NULL
        CHECK(source_type IN ('machine','human','adjudication','imported')),
    source_name TEXT NOT NULL,
    category TEXT,
    severity TEXT,
    verdict TEXT,
    claim_text TEXT,
    output_span TEXT,
    ground_truth_reference TEXT,
    evidence_text TEXT,
    confidence REAL,
    rationale TEXT,
    raw_payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(assessment_id) REFERENCES judge_assessments(id),
    FOREIGN KEY(review_id) REFERENCES human_reviews(id),
    FOREIGN KEY(material_id) REFERENCES materials(id)
);

CREATE TABLE IF NOT EXISTS human_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL,
    assignment_item_id INTEGER,
    reviewer_id TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    review_round TEXT NOT NULL DEFAULT 'initial',
    rubric_version TEXT,
    decision_status TEXT NOT NULL DEFAULT 'completed'
        CHECK(decision_status IN ('completed','deferred','skipped')),
    review_status TEXT NOT NULL
        CHECK(review_status IN ('compliant','non_compliant','inconclusive','error')),
    violation_count INTEGER NOT NULL DEFAULT 0,
    max_severity TEXT,
    rationale TEXT,
    defer_reason TEXT,
    review_duration_sec INTEGER,
    blind_to_machine_labels INTEGER NOT NULL DEFAULT 1 CHECK(blind_to_machine_labels IN (0,1)),
    raw_payload_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE(material_id, reviewer_id, review_round),
    FOREIGN KEY(assignment_item_id) REFERENCES review_assignment_items(id),
    FOREIGN KEY(material_id) REFERENCES materials(id)
);

CREATE TABLE IF NOT EXISTS adjudications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL UNIQUE,
    adjudicator_id TEXT NOT NULL,
    adjudicated_at TEXT NOT NULL,
    final_status TEXT NOT NULL
        CHECK(final_status IN ('compliant','non_compliant','inconclusive','error')),
    violation_count INTEGER NOT NULL DEFAULT 0,
    max_severity TEXT,
    resolution_source TEXT NOT NULL,
    rationale TEXT,
    raw_payload_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(material_id) REFERENCES materials(id)
);

CREATE TABLE IF NOT EXISTS review_queue_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL,
    queue_name TEXT NOT NULL,
    priority_score REAL NOT NULL DEFAULT 0,
    priority_bucket TEXT NOT NULL,
    reason TEXT NOT NULL,
    queue_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(material_id, queue_name, queue_version),
    FOREIGN KEY(material_id) REFERENCES materials(id)
);

CREATE TABLE IF NOT EXISTS review_assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assignment_uuid TEXT NOT NULL UNIQUE,
    dataset_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    reviewer_id TEXT NOT NULL,
    queue_name TEXT NOT NULL,
    blind_mode INTEGER NOT NULL DEFAULT 1 CHECK(blind_mode IN (0,1)),
    rubric_version TEXT NOT NULL DEFAULT 'compliance-rubric-v1',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK(status IN ('active','completed','archived')),
    notes TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(dataset_id, name),
    FOREIGN KEY(dataset_id) REFERENCES datasets(id)
);

CREATE TABLE IF NOT EXISTS review_assignment_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assignment_id INTEGER NOT NULL,
    material_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    item_status TEXT NOT NULL DEFAULT 'pending'
        CHECK(item_status IN ('pending','in_progress','completed','deferred','skipped')),
    assigned_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT,
    defer_reason TEXT,
    skip_reason TEXT,
    last_review_id INTEGER,
    UNIQUE(assignment_id, material_id),
    FOREIGN KEY(assignment_id) REFERENCES review_assignments(id),
    FOREIGN KEY(material_id) REFERENCES materials(id),
    FOREIGN KEY(last_review_id) REFERENCES human_reviews(id)
);

CREATE TABLE IF NOT EXISTS validation_freezes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    freeze_uuid TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL UNIQUE,
    dataset_id INTEGER NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    resolution_rule TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    notes TEXT,
    FOREIGN KEY(dataset_id) REFERENCES datasets(id)
);

CREATE TABLE IF NOT EXISTS validation_exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset_id INTEGER,
    freeze_id INTEGER,
    exported_at TEXT NOT NULL,
    export_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(dataset_id) REFERENCES datasets(id),
    FOREIGN KEY(freeze_id) REFERENCES validation_freezes(id)
);

CREATE INDEX IF NOT EXISTS idx_materials_dataset ON materials(dataset_id);
CREATE INDEX IF NOT EXISTS idx_materials_product ON materials(product_id);
CREATE INDEX IF NOT EXISTS idx_materials_type_model ON materials(material_type, engine, model);
CREATE INDEX IF NOT EXISTS idx_materials_temporal ON materials(time_of_day_label, scheduled_day_of_week, repetition_id);
CREATE INDEX IF NOT EXISTS idx_judge_assessments_material ON judge_assessments(material_id);
CREATE INDEX IF NOT EXISTS idx_judge_assessments_judge ON judge_assessments(judge_name, approach);
CREATE INDEX IF NOT EXISTS idx_violation_findings_material ON violation_findings(material_id);
CREATE INDEX IF NOT EXISTS idx_human_reviews_material ON human_reviews(material_id);
CREATE INDEX IF NOT EXISTS idx_review_queue_name ON review_queue_items(queue_name, queue_version);
CREATE INDEX IF NOT EXISTS idx_review_assignments_dataset ON review_assignments(dataset_id);
CREATE INDEX IF NOT EXISTS idx_review_assignment_items_assignment ON review_assignment_items(assignment_id);
CREATE INDEX IF NOT EXISTS idx_review_assignment_items_status ON review_assignment_items(item_status);
