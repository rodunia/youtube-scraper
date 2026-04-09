# YouTube Scraper Research App (Python)

This repository contains a working local implementation of the hybrid YouTube comments research pipeline for the KES 2026 project.

## Current Status Snapshot (2026-04-09)

This snapshot reflects the local SQLite database at `data/youtube_comments.db` and the current paper-facing freeze workflow.

- Application status: working local package + Streamlit research console with validated-vs-exploratory separation.
- Database status:
  - `27` total runs
  - `205` channels
  - `3,463` videos
  - `33,467` comments
  - `3,767` saved annotations across `2,445` unique comments
  - `2` annotators active in the DB
- Run modes observed:
  - `22` runs in `auto`
  - `3` runs in `api_only`
  - `2` runs in `playwright_only`
- Niche coverage in current DB snapshot:
  - Beauty: `58` channels, `1,792` videos, `16,660` comments
  - Lifestyle: `43` channels, `602` videos, `6,175` comments
  - Tech: `104` channels, `1,069` videos, `10,632` comments
- Video comment-status distribution:
  - `1,277` videos `ok`
  - `2,108` videos `not_enough_comments`
  - `75` videos `comments_disabled`
  - `3` videos `extraction_failed`

## Paper-Facing Readiness Snapshot

The project now has a named freeze-based confirmatory workflow.

- Canonical writing source: `conference_paper.md`
- Canonical freeze: `KES-final` (`freeze_id=8`, `freeze_uuid=freeze-20260408T142800Z`)
- Freeze scope: runs `11, 18, 20, 22, 23, 24`
- Freeze counts:
  - `1,322` resolved double-coded comments
  - `224` disagreement cases
  - `0` unresolved disagreements at freeze

Methodologically, this means:
- validated paper-facing claims are anchored to a specific freeze artifact
- exploratory/assistive outputs stay visible but are not paper-safe by default
- re-export from the same freeze can be used for reproducibility checks

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

## Generate Paper Figure Pack From A Named Freeze

```bash
PYTHONPATH=src python -m youtube_scraper.cli paper-figure-pack \
  --freeze-name KES-final \
  --out-dir exports/paper_figures/kes_final
```

Optional:
- use `--freeze-id 8` to anchor by freeze ID.
- add `--include-flagged` only for sensitivity checks.

See `PAPER_FIGURE_PACK_RUNBOOK_2026-04-09.md` for the full output map.

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
