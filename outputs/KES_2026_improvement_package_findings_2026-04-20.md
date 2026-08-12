# KES 2026 Integrated Improvement Package Findings (2026-04-20)

## Stage 1 - Repo and data audit

### What was found
- Freeze logic is implemented through `evidence_freezes` and freeze-scoped resolved-consensus selection paths in:
  - `app/streamlit_app.py` (`resolved_consensus_run_ids`, `evidence_base_snapshot`, `upsert_evidence_freeze`)
  - `src/youtube_scraper/paper_figures.py` (freeze loading and freeze-linked exports)
- Run metadata and provenance are stored in:
  - `runs`, `qa_reports`, `exports`, `evidence_freezes` tables (`src/youtube_scraper/schema.sql`, `src/youtube_scraper/db.py`)
- Assistive logic and deterministic screening signals are in:
  - `src/youtube_scraper/auto_analysis.py`
  - queue/priority logic in `app/streamlit_app.py` (`_triage_comment_uncertainty`, `_annotation_priority_details`, `uncoded_extension_frames`)
- Coding/disagreement/adjudication traces are stored in `annotations`.
- Safe acquisition insertion points are:
  - `resolve-targets` in `src/youtube_scraper/cli.py`
  - `run-batch` in `src/youtube_scraper/pipeline.py`
  - export/report scripts in `scripts/` and `outputs/`

### Risk note (from current DB snapshot)
- `annotations` rows: 3767.
- Rows with priority/triage traces: 622.
- Rows with populated `was_disagreement_detected`: 0.
- Rows with populated `adjudicated_at`: 0.
- Rows with populated `pre_adjudication_*`: 0.
- Implication: workflow evaluation is credible for instrumented subset analysis, but not for full-corpus time/process reconstruction.

### Files changed
- None.

### Outputs generated
- Audit performed in-session; no Stage 1 export artifact file was previously present.

### Assumptions
- `KES-final` is the paper-facing freeze anchor in current local state.

### Fallback used
- None.

---

## Stage 2 - Workflow-evaluation package

### What was implemented
- Added reproducible workflow-value script:
  - `scripts/workflow_eval.py`
- Uses freeze-scoped resolved labels only.
- Uses only comments with recorded priority traces.
- Computes:
  - top-slice positive yield lift,
  - disagreement concentration,
  - review-burden proxy vs random ordering for fixed positive-recovery target.

### Outputs generated
- `outputs/workflow_eval_summary.csv`
- `outputs/workflow_eval_table.md`
- `outputs/workflow_eval_notes.md`
- `outputs/workflow_eval_instrumented_comments.csv`

### Key current results (newest run)
- Freeze: `KES-final` (id=8, uuid=`freeze-20260408T142800Z`)
- Instrumented subset: 222 comments, 95 positives.
- Top-priority slice (25%): positive rate 0.8929 vs 0.2711 in remainder (lift 3.2937).
- 80% positive recovery depth:
  - priority ordering: 86
  - random mean: 176.6358 (p05=164, p95=188)
  - burden reduction proxy: 0.5131
- Disagreement rate: 0.4643 (top slice) vs 0.3012 (remainder).

### Files changed
- `scripts/workflow_eval.py` (existing in workspace from this package run context)

### Assumptions
- Earliest priority-scored annotation touch approximates queue-order signal.

### Fallback used
- None required (instrumented overlap was sufficient).

---

## Stage 3 - Workflow-comparison package

### What was implemented
- Added governance/architecture comparison artifact script:
  - `scripts/workflow_comparison.py`
- Comparison is workflow-governance only (not model performance).

### Outputs generated
- `outputs/workflow_comparison_table.csv`
- `outputs/workflow_comparison_table.md`
- `outputs/workflow_comparison_notes.md`

### Files changed
- `scripts/workflow_comparison.py` (existing in workspace from this package run context)

### Assumptions
- Non-repo columns are explicit reference archetypes and conservatively characterized.

### Fallback used
- None.

---

## Stage 4 - Targeted exploratory acquisition package

### What was implemented
- Added deterministic targeted queue builder:
  - `scripts/targeted_skeptical_queue.py`
- Heuristics are explainable and versioned (`targeted_skeptical_queue.v1`):
  - skepticism/proof-demand lexical cues,
  - top-rank preference,
  - AI-discourse metadata/context,
  - channel prior from frozen resolved evidence,
  - engagement/disagreement context,
  - low-info penalty.
- Added dedup safeguard: `(video_id, normalized_comment_text)` before ranking.
- Added explicit staging label and recommended next-step fields for coder handoff.
- Preserved validated/exploratory boundary:
  - no write path into frozen evidence,
  - no auto-promotion of candidates into validated claims.

### Outputs generated
- `outputs/targeted_candidate_videos.csv`
- `outputs/targeted_candidate_threads.csv`
- `outputs/targeted_acquisition_report.md`
- `outputs/targeted_acquisition_run_metadata.json`

### Key current results (newest run)
- Candidate threads exported: 400.
- Candidate videos exported: 200.
- Candidate channels represented: 43.
- Comments after resolved/flag filters: 29198.
- Comments after scoring (before cap): 2394.
- Newly acquired external channels/videos/comments in this run: 0.
- Exploratory material already outside selected freeze runs: 88 channels, 248 videos, 4869 comments.

### Files changed
- `scripts/targeted_skeptical_queue.py`

### Assumptions
- In this offline/local execution, targeted generation from existing local corpus is the highest-confidence non-contaminating option.

### Fallback used
- Because no new scrape was executed in this stage, output is an exploratory targeting queue and report with explicit `new_external_acquisition_executed = 0`.

---

## Stage 5 - Final output package

### 1. Implementation summary
- Delivered one integrated package with:
  - workflow-value signal (Stage 2),
  - workflow comparison artifact (Stage 3),
  - targeted exploratory queue capacity (Stage 4).
- All components preserve frozen validated evidence boundary.

### 2. Files changed
- Added:
  - `scripts/workflow_eval.py`
  - `scripts/workflow_comparison.py`
  - `scripts/targeted_skeptical_queue.py`
- Generated:
  - `outputs/workflow_eval_summary.csv`
  - `outputs/workflow_eval_table.md`
  - `outputs/workflow_eval_notes.md`
  - `outputs/workflow_eval_instrumented_comments.csv`
  - `outputs/workflow_comparison_table.csv`
  - `outputs/workflow_comparison_table.md`
  - `outputs/workflow_comparison_notes.md`
  - `outputs/targeted_candidate_videos.csv`
  - `outputs/targeted_candidate_threads.csv`
  - `outputs/targeted_acquisition_report.md`
  - `outputs/targeted_acquisition_run_metadata.json`

### 3. Schema changes
- None.

### 4. Scripts/notebooks added
- `scripts/workflow_eval.py`
- `scripts/workflow_comparison.py`
- `scripts/targeted_skeptical_queue.py`

### 5. Migrations or backfill notes
- None required.

### 6. Outputs generated
- See full list above under Files changed / Generated.

### 7. Limitations and unresolved risks
- Workflow-evaluation metric is instrumented-subset only, not full-corpus benchmark.
- Several adjudication/provenance fields exist in schema but are sparsely populated in this DB snapshot.
- Stage 4 produced targeted exploratory queues but did not execute external scraping in this run.
- Candidate queues are assistive only; human validation + adjudication + freeze linkage remain mandatory for paper-facing claims.

### 8. How this helps the paper
- Adds a compact, reproducible practical-value signal for reviewer scrutiny.
- Adds a clear governance comparison table that foregrounds systems/method novelty without overclaiming model novelty.
- Adds a deterministic targeted extension path to address skeptical top-cue sparsity while preserving evidence governance boundaries.

---

## Paper-ready text fragments

### Workflow evaluation paragraph
Using the `KES-final` freeze scope and resolved human labels only, we evaluated assistive queue value on the subset of comments with recorded priority traces. For each comment, we retained the earliest priority-scored touch and compared positive-yield concentration between the top-priority slice and the remainder, then estimated review burden as the number of reviews required to recover 80% of positives under priority ordering versus random ordering (fixed-seed Monte Carlo baseline).

### Workflow comparison paragraph
Table X reports workflow-governance capabilities rather than model performance. Compared with reference pipeline archetypes, this repository integrates double coding, explicit disagreement detection, adjudication traceability, freeze-scoped validated evidence, and freeze-linked export provenance while keeping assistive logic explicitly non-binding for confirmatory claims.

### Targeted extension / future-work paragraph
To address sparse skeptical top-cue structure without broad uncontrolled scraping, we added a deterministic targeted exploratory queue that prioritizes videos and threads using transparent lexical, rank, context, and channel-prior heuristics. The output is a coder-ready exploratory staging layer designed to increase likely skeptical top-cue yield for subsequent human coding and adjudication cycles.

### Limitations paragraph
The new targeted queue and any newly collected material remain exploratory by default and are not paper-safe evidence until they are human-coded, disagreement-resolved, adjudicated where needed, and linked to a named evidence freeze.
