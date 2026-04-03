# YouTube Scraper Research App (Python)

This repository contains a working local implementation of the hybrid YouTube comments research pipeline for the KES 2026 project.

## Current Status Snapshot (2026-03-21)

This snapshot reflects the local SQLite database at `data/youtube_comments.db`, populated through `2026-03-07`.

- Application status: working local package + Streamlit research console.
- Git status: most implementation work is still local and uncommitted; git history does not yet reflect the full app state.
- Database status:
  - `24` total runs (`17` live, `7` simulated)
  - `204` channels
  - `3,453` videos
  - `33,417` comments
  - `174` saved annotations across `174` unique comments
  - `1` annotator currently active in the DB (`annotator_a`)
- Run modes observed:
  - `19` runs in `auto`
  - `3` runs in `api_only`
  - `2` runs in `playwright_only`
- Niche coverage in the current DB snapshot:
  - Beauty: `58` channels, `1,792` videos, `16,660` comments
  - Lifestyle: `43` channels, `602` videos, `6,175` comments
  - Tech: `103` channels, `1,059` videos, `10,582` comments
- Video comment-status distribution:
  - `1,275` videos `ok`
  - `2,100` videos `not_enough_comments`
  - `75` videos `comments_disabled`
  - `3` videos `extraction_failed`

## Hypothesis Readiness Snapshot

The analytic plan is defined in `analysis_plan_v1.md`. The current project state is best described as data-collection and pilot-analysis ready, but not yet confirmatory-analysis ready.

- RQ1 / H1: a skeptical top-liked comment is associated with higher skepticism in subsequent comments.
  - Status: partially ready.
  - Why: the ranking structure, comment text, engagement counts, timestamps, and niche labels are already collected; confirmatory testing still depends on validated skepticism labels.
- RQ2 / H2: the cascade association is stronger when the top-ranked comment has higher like count.
  - Status: partially ready.
  - Why: top-comment like counts are already stored, but the same label-validation requirement applies to the skepticism outcome.
- RQ3 / H3: the cascade association varies across creator ecosystems and is stronger in higher authenticity-stakes niches.
  - Status: partially ready.
  - Why: `channel_niche` is already collected, but the confirmatory version still requires a final lock on the niche mapping, especially if `Faceless Lifestyle` is intended as a distinct analytic baseline rather than the broader `Lifestyle` bucket.

In practical terms:
- The pipeline is ready for continued collection, QA, export, exploratory summaries, and manual annotation.
- The Streamlit app already supports hypothesis-proxy exploration, disclosure search, and the conformity-cascade workflow.
- Final confirmatory testing still depends on annotation completion, label validation, and freezing the final niche framing for the moderation analysis.

## What Is Implemented Now

- SQLite-first data model aligned with the planning document.
- Batch run orchestration with execution modes:
  - `auto`
  - `api_only`
  - `playwright_only`
- Rules-based preprocessing:
  - spam flags (`is_spam`) with S1-S8 rules
  - template and duplicate flags
- Run metadata tracking for reproducibility:
  - `spam_ruleset_version`
  - compliance reference
  - truncation status
- CSV exports for R workflows:
  - comments dataset
  - video-level panel dataset
  - QA dataset
- Streamlit research interface:
  - Overview dashboard
  - Run Lab for launching and filtering runs
  - Scraped Data browser
  - Data exploration with filters/search
  - AI disclosure search
  - Pilot analysis
  - Automatic analysis tab (rules-based labels + hypothesis proxy metrics)
  - Manual annotation view (3 binary variables)

## Current Scope Note

`run-batch` supports:
- `--simulate` for safe pipeline testing.
- live mode (without `--simulate`) using YouTube API with auto failover to Playwright based on quota threshold.
- live mode now also includes `yt-dlp` non-API fallback for channel/video/comment extraction when API quota is exhausted.

Important scope note for analysis:
- `analysis_plan_v1.md` treats regular long-form videos as the primary confirmatory analysis set.
- Shorts runs are being collected separately for exploratory robustness work and should not be merged into the confirmatory core by default.

## Setup

1. Create environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Create local config:

```bash
cp .env.example .env
```

Set these in `.env` before live runs:
- `YOUTUBE_API_KEY`
- `YOUTUBE_API_KEYS` (optional comma-separated pool; if set, app rotates keys on quota exhaustion)
- `HASH_SALT` (long random secret)
- `COMPLIANCE_REFERENCE` (IRB or GDPR format)

3. Initialize SQLite database:

```bash
PYTHONPATH=src python -m youtube_scraper.cli init-db
```

## Run a Simulated Batch

Use a CSV with either schema:
- `channel_id`, `channel_url`, `channel_niche`
- `channel_identifier`, `channel_name`, `niche`

```bash
cp data/targets.example.csv data/targets.csv
PYTHONPATH=src python -m youtube_scraper.cli run-batch --targets data/targets.csv --simulate --channel-limit 3
```

## Run a Live Batch (API + Playwright Fallback)

Install browser dependency once:

```bash
playwright install chromium
```

Run live extraction:

```bash
PYTHONPATH=src python -m youtube_scraper.cli run-batch --targets data/targets.csv --channel-limit 30 --videos-per-channel 20 --min-expected-videos-per-channel 20
```

Collect Shorts in a separate run:

```bash
PYTHONPATH=src python -m youtube_scraper.cli run-batch --targets data/targets.csv --channel-limit 30 --videos-per-channel 20 --min-expected-videos-per-channel 20 --content-type shorts
```

Engine mode is controlled by `EXECUTION_MODE` in `.env`:
- `auto` (default): API first, Playwright fallback at threshold.
- `api_only`
- `playwright_only`

Content mode is controlled per run with `--content-type`:
- `videos` (default)
- `shorts`

In Shorts mode, channels without a Shorts tab are flagged as `no_shorts_available` (not extraction failure).

## Resolve Channel IDs First (Recommended)

```bash
PYTHONPATH=src python -m youtube_scraper.cli resolve-targets \
  --input data/shorts_seed_channels_2026-03-07.normalized.csv \
  --output data/targets_shorts_seed_2026-03-07.resolved.csv
```

## Export CSV for R

```bash
PYTHONPATH=src python -m youtube_scraper.cli export-csv --out-dir exports
```

## Run Automatic Analysis Exports

```bash
PYTHONPATH=src python -m youtube_scraper.cli auto-analyze --run-id 11 --out-dir exports
```

Optional:
- add `--include-flagged` to include spam/template/duplicate rows.

## Run Conformity Cascade Analysis

Input CSV must include:
- `video_id`
- `channel_id`
- `channel_niche`
- `comment_text`
- `like_count`
- `comment_timestamp`
- `is_skeptical` (0/1)

```bash
PYTHONPATH=src python -m youtube_scraper.cli conformity-cascade \
  --input-csv exports/conformity_input_runs_23_24_with_niche.csv \
  --out-ranked-csv exports/conformity_ranked_runs_23_24.csv \
  --out-response-csv exports/conformity_response_runs_23_24.csv \
  --out-effects-csv exports/conformity_effects_runs_23_24.csv \
  --out-icc-csv exports/conformity_icc_runs_23_24.csv
```

## Run Conformity Robustness From DB Runs (Non-Shorts Default)

```bash
PYTHONPATH=src python -m youtube_scraper.cli conformity-robustness \
  --run-ids 11 17 18 \
  --out-dir exports
```

Optional:
- add `--include-shorts` to include Shorts URLs.
- add `--include-flagged` to include spam/template/duplicate rows.
- tune min-comments check with `--min-response-comments 10`.

## Launch Web App

```bash
PYTHONPATH=src streamlit run app/streamlit_app.py
```

Login credentials come from `LOCAL_AUTH_USERS` in `.env`.

## Project Structure

- `implementation.md`: locked planning and methodology decisions
- `analysis_plan_v1.md`: confirmatory model formulas and table/figure plan
- `src/youtube_scraper/`: application package
- `app/streamlit_app.py`: web interface
- `data/`: input target CSV files
- `exports/`: generated CSV exports for R

## Next Build Steps

- Bring documentation and git history in sync with the implemented codebase.
- Finish the planned `300`-comment double-coding workflow and adjudication set.
- Freeze the final niche taxonomy for the moderation hypothesis, including whether `Faceless Lifestyle` is a distinct coded subgroup.
- Promote the conformity-cascade models and outputs from pilot mode into the primary confirmatory analysis workflow.
- Add automated tests for pipeline, exports, and key Streamlit data paths.
- Expand IRR and model-performance reporting utilities for the final analysis freeze.
