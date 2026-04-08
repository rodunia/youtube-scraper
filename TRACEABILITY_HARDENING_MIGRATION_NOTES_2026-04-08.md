# Traceability Hardening Migration Notes (2026-04-08)

This note summarizes the schema and workflow hardening introduced on branch `submission-traceability-hardening`.

## Scope

Files changed:

- `app/streamlit_app.py`
- `src/youtube_scraper/db.py`
- `src/youtube_scraper/schema.sql`

## Schema additions

### `runs`

- `rules_version TEXT`
- `scoring_version TEXT`
- `preprocessing_profile TEXT`

### `annotations`

- `was_disagreement_detected INTEGER`
- `resolution_source TEXT`
- `adjudication_note TEXT`
- `adjudicated_at TEXT`
- `pre_adjudication_skepticism INTEGER`
- `pre_adjudication_proof_demand INTEGER`
- `pre_adjudication_normalization INTEGER`

### `evidence_freezes`

- `freeze_uuid TEXT`
- `rules_version TEXT`
- `scoring_version TEXT`
- `preprocessing_profile TEXT`

### `exports`

- `freeze_id INTEGER`
- `rules_version TEXT`
- `scoring_version TEXT`
- `preprocessing_profile TEXT`

Also fixed SQL syntax in `exports` table foreign keys.

## Migration behavior

- Migrations are applied by `init_database()` through `_ensure_schema_migrations()`.
- Existing DBs are upgraded in place using additive `ALTER TABLE` operations.
- No destructive migration is introduced.

## Runtime behavior updates

- Run creation now persists deterministic logic metadata.
- Freeze records now carry explicit metadata (`freeze_id`, `freeze_uuid`, run scope, disagreement metrics, rules/scoring/profile versions).
- Export events can be logged with freeze linkage and version metadata.
- Adjudication captures trace fields (`resolution_source`, `adjudication_note`, `adjudicated_at`, disagreement flag).
- On first adjudication of an existing annotation row, previous core labels are preserved in `pre_adjudication_*`.

## Validation executed

- `python -m py_compile app/streamlit_app.py src/youtube_scraper/db.py`
- In-memory schema load from `src/youtube_scraper/schema.sql`
- Existing DB column checks for required new fields in `runs`, `annotations`, `evidence_freezes`, `exports`
- Local Streamlit smoke start on port `8502`

## Notes for analysis continuity

- Historical rows will have `NULL` in new fields until touched by new runs/adjudications/freezes/exports.
- Pre-adjudication preserved labels are forward-only (not reconstructable for past adjudications).
- This hardening does not change core modeling logic; it adds auditability and reproducibility metadata.
