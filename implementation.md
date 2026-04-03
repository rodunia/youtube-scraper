# YouTube Comments Scraper App - Implementation Plan

## Status
- Planning baseline below was frozen on 2026-03-02 and remains the decision log for scope/methodology.
- The repository has progressed beyond planning and now includes a working Python package, Streamlit app, local SQLite database, and export artifacts.
- As of 2026-03-21, the local DB snapshot contains `24` runs, `204` channels, `3,453` videos, `33,417` comments, and `174` saved annotations.
- The confirmatory analytic focus is being readjusted toward a conformity-cascade framework centered on ranked skeptical cues, engagement magnitude, and cross-niche moderation.
- Confirmatory hypothesis testing is not yet frozen: the planned `300`-comment double-coded annotation set is incomplete, and the final niche framing for the moderation hypothesis still needs to be locked.
- Detailed statistical specification is maintained in `analysis_plan_v1.md` (formulas, robustness, tables, figures).

## Agreed Objectives
- Build an app to collect YouTube comments data from selected YouTube accounts/channels.
- Intended use: academic research and text analysis.
- Work process: define complete plan first, then implement.

## Decision Log

### 1. Research Scope
- Unit of analysis: comments on videos published by selected channels.
- Out of scope: comments authored by those channels on other channels/videos.
- Channel niches are predefined as: Tech, Beauty, Lifestyle.

### 2. Data Sources and Access Method
- Collection must use a hybrid method:
- Primary: YouTube Data API v3.
- Fallback: Playwright-based web scraping module when API quota constraints block required extraction.
- Rationale: default API quota is 10,000 units/day, which is insufficient for full-scale batch needs.
- Fallback activation is proactive at 90% daily quota usage (9,000/10,000 units), not only after hard `quotaExceeded` failures.
- Fallback execution mode: automatic failover in the same batch run to preserve extraction continuity and timeline coherence.
- Execution mode controls must support:
- `auto` (API then Playwright failover at threshold).
- `api_only` (debug/audit).
- `playwright_only` (debug/audit).

### 3. Legal, Compliance, and Ethics Requirements
- Dataset must align with academic ethics and privacy constraints (including GDPR-style principles as specified by project requirements).
- Identifiable commenter details must not be persisted in final analysis dataset.
- Usernames must not be stored in raw form.
- A stable hashed commenter ID should be stored for pseudonymous user-level analysis (e.g., cross-video repetition/spam controls).
- Raw commenter identifiers must be transformed in-memory at pipeline edge before database insert.
- Data retention/deletion policy:
- Intermediate raw extracts retained for 180 days or deleted immediately after successful cleaning/hashing completion (whichever occurs first).
- Fully pseudonymized final dataset may be retained for replication package requirements.
- Compliance reference policy for run metadata:
- Preferred institutional format: `IRB: <protocol_id> (<institution>)` (example: `IRB: IRB-2026-045 (University X)`).
- Non-institutional EU fallback: `Legal Basis: GDPR Article 89(1) - Scientific Research`.

### 4. Data Schema and Storage
- Data storage must be relational.
- Primary execution DB for this project: SQLite (user-friendly, local workflow).
- PostgreSQL remains an optional future scaling backend.
- Schema must support hierarchical relationships:
- Channel -> Video -> Comment.
- Comments table must retain both `raw_text` and `cleaned_text` for reproducibility.
- Top-level comment records must include `reply_count`.
- Channels with fewer than 30 recent uploads must be retained and marked with `coverage_shortfall=true`.
- CSV export for R is a mandatory feature:
- Export cleaned analysis-ready comment-level dataset.
- Export video-level aggregated dataset for panel modeling.
- Export metadata/QA tables used in manuscript reporting.

### 5. Scraping/Collection Workflow
- Input targets come from a static CSV containing 300 pre-selected channel IDs/URLs with niche labeling.
- Content stream selection must support separate batch runs by content type:
- `videos` (default, long-form feed).
- `shorts` (Shorts feed).
- The hybrid extraction engine remains available in both content modes (`auto`, `api_only`, `playwright_only`).
- Per channel video selection rule: collect most recent uploads in reverse chronological order.
- Video coverage per channel: adaptive range of 30-80 most recent videos depending on channel activity.
- Per video comment selection:
- Only top-level comments (no replies).
- Fetch a larger candidate pool (target scan up to 200 top-level comments when available), rank by like count, then keep up to 20 clean comments.
- Clean inclusion rule for saved rows: exclude comments flagged as spam/template/duplicate before applying the 20-comment cap.
- If a video has fewer than 20 top-level comments, collect all available comments and do not replace the video.
- If fewer than 20 clean comments remain after filtering, save all clean comments and mark `not_enough_comments`.
- For equal like counts, ranking tie-break should prefer older comment timestamp.
- Video-level comment availability status must be stored (`ok`, `not_enough_comments`, `comments_disabled`).
- For Shorts mode, channels with no Shorts feed should be explicitly flagged as `no_shorts_available=true` (channel-level) instead of `extraction_failed`.
- Two execution modes are required:
- Pilot batch.
- Full batch.

### 6. Cleaning, Preprocessing, and Quality Controls
- Built-in preprocessing is required.
- Mandatory filtering targets:
- Duplicate comments.
- Templated comments.
- Spam/bot-like comments.
- Duplicate checks must run at both levels:
- Within-video duplicate detection.
- Global cross-dataset duplicate detection.
- Templated comment detection must combine:
- Pilot-calibrated text similarity threshold (initial reference: 0.90, then locked after pilot QA).
- Phrase/pattern repetition rules for near-duplicate bot-style variants.
- Current pilot execution policy: save only clean comments into `comments` table (spam/template/duplicate candidates are filtered out before insert).
- Required boolean flags include: `is_spam`, `is_template`, `is_duplicate`.
- Spam filtering baseline starts as rules-only for transparency and reproducibility.
- Lightweight model scoring is optional only if pilot evidence shows rules-only underperformance.
- v1 deterministic `is_spam` rule set (pre-pilot):
- Rule S1 (URL density): flag if text contains >=2 URLs.
- Rule S2 (promo handle patterns): flag if regex matches promotional patterns such as `(?i)(dm\\s+me|check\\s+my\\s+channel|subscribe\\s+back|promo\\s+code)`.
- Rule S3 (contact bait): flag if regex matches `(?i)(whatsapp|telegram|kik|snapchat)\\b` with additional solicitation terms.
- Rule S4 (token repetition): flag if any token repeats >=8 times in one comment after normalization.
- Rule S5 (character flooding): flag if any character repeats >=12 times consecutively.
- Rule S6 (cross-video burst repetition): flag if same normalized text appears across >=5 distinct videos in a run.
- Rule S7 (blacklist exact-match): flag if normalized text equals known spam templates in a maintained blacklist table.
- Rule S8 (emoji/symbol saturation): flag if non-alphanumeric characters exceed 60% of text length and text length > 15.
- Rule merge policy: `is_spam=true` if any S-rule triggers; all triggered rule IDs must be stored for audit.
- These filters are required as a sensitivity check for downstream statistical models.
- Approved pilot thresholds for v1 spam rules:
- S1 URL density `>=2`
- S4 token repetition `>=8`
- S5 character flooding `>=12`
- S6 cross-video repeat `>=5`
- S8 non-alphanumeric saturation `>60%` with length guard `>15`
- Template calibration protocol:
- Random sample of 500 comments from pilot corpus.
- Double-coded by two human reviewers as template/non-template.
- Threshold sweep across [0.80, 0.98].
- Final threshold chosen to maximize precision with recall floor fixed at 0.80.
- Ruleset versioning is mandatory:
- Each run must persist `spam_ruleset_version` (e.g., `v1.0.0`).
- Any threshold/rule changes require semantic version bump (e.g., `v1.1.0`) and run-level traceability.

### 7. App Architecture and Tech Stack
- Primary implementation language: Python.
- Core stack direction:
- Extraction/API orchestration: Python.
- Fallback browser automation: Playwright (Python).
- Web interface: Streamlit (Python).
- Storage/export pipeline: SQLite + CSV exports for R.
- Fallback scraping runtime is standardized on Playwright.

### 8. Operations (Scheduling, Monitoring, Re-runs)
- Collection is batch-based, not continuous streaming.
- Planned runs:
- Pilot: ~12,000 comments (30 channels x 20 videos x 20 comments).
- Full run: ~300,000 comments (300 channels x avg. 50 videos x 20 comments).
- Each batch must produce a QA report with:
- Channels attempted/succeeded.
- Videos collected.
- Comments collected.
- Filtered counts by reason.
- API vs Playwright extraction share.
- Per-niche QA breakdowns are required (Tech/Beauty/Lifestyle) for all key coverage and attrition metrics.
- Retry policy:
- Maximum 3 retries per entity (video/channel extraction unit).
- Exponential backoff schedule: 5s -> 15s -> 60s.
- After 3 failures, log and flag `extraction_failed=true`, then continue.
- Hard stop behavior:
- Strict upper cap of 20 top-level comments per video (never overflow above 20).
- Run-level global safety caps are required:
- `max_channels=300`
- `max_videos=24000`
- `max_comments=480000`
- Global-cap behavior on limit hit:
- Gracefully stop intake.
- Persist partial outputs and run logs.
- Mark run status with `run_truncated=true` (no hard failure by default).

### 9. Reproducibility for Academic Use
- Pipeline design must support reproducible batch execution and traceability of extraction settings.
- Run metadata must include:
- `spam_ruleset_version`
- execution mode (`auto`/`api_only`/`playwright_only`)
- extraction engine share (API vs Playwright)
- cap/truncation status (`run_truncated`)
- compliance reference string (IRB/legal basis)
- parameter snapshot and code/app version identifiers

### 10. Deliverables and Success Criteria
- Deliverable: queryable relational dataset for text analysis and market-response proxy analysis.
- Deliverable must support non-programmer analysis flow:
- Local SQLite database file.
- One-click or command-triggered CSV exports for R ingestion.
- Required minimum comment fields:
- Comment text.
- Like count.
- Timestamp.
- Confirmed extended metadata fields:
- `channel_id`
- `channel_niche`
- `video_id`
- `video_url`
- `video_publish_ts`
- `comment_rank`
- `extraction_ts`
- `language`
- `reply_count`
- Pseudonymous commenter identity:
- `commenter_hash_id` generated with SHA-256 and project secret salt stored outside DB.
- `commenter_hash_id` must be generated at pipeline edge before insert (not from DB-side raw identifiers).
- Secret/salt policy:
- Keep salt only in local `.env`.
- Never store salt in DB and never commit it to repository.
- Do not rotate salt during this study to preserve longitudinal pseudonymous linkage.

### 11. Web Interface (Planning Scope)
- A web UI is in scope to support workflow visibility, exploratory analysis, and manual coding.
- Preferred framework direction: Streamlit (subject to final confirmation during architecture decisions).
- Web UI must support authenticated multi-user operation for annotation workflows.
- Initial auth architecture: local credentials (not institutional SSO/OAuth) to support pilot velocity.
- Annotation workflow must preserve coder blinding (annotators cannot see each other's labels).
- Interface must support hierarchical progressive disclosure:
- Landing overview with batch pulse metrics (coverage, quota usage, API/Playwright share).
- Separate views/tabs for Data Exploration and Manual Annotation.
- Data Exploration view must include search and granular filters:
- Filter by `channel_niche`.
- Filter by video recency/age.
- Filter by preprocessing flags (`is_spam`, `is_duplicate`, `is_template`).
- Search across comment text and key identifiers.
- Add dedicated AI disclosure search module:
- Search both video metadata (`title`, `description`) and comment text.
- Support keyword/regex search, run-level filtering, and niche filtering.
- Provide inferred disclosure buckets for video metadata (`none`, `generic`, `specific`, `verifiable`) for pilot triage.
- Allow CSV export of matched video and comment subsets for manual review and R workflows.
- Add automatic analysis module in UI:
- Rules-based auto-labeling for `skepticism`, `proof_demand`, and `normalization`.
- Auto-generated video/channel/niche rate tables and hypothesis-proxy metrics.
- CSV download for auto-labeled comments and auto-aggregated metrics.
- Include export controls for CSV outputs (respecting active filters or predefined export profiles).
- Manual Annotation view must support streamlined coding workflow for IRR validation subset:
- Show target comment with adjacent video context (title/description metadata).
- Show coding inputs inline using required binary variables:
- `skepticism_fake_callout` (0/1)
- `proof_demand` (0/1)
- `normalization_defense` (0/1)
- Support efficient batch coding pages (multiple comments per screen) with tick/checkbox inputs and one-click page save.
- Support optional auxiliary coding fields for exploratory tagging:
- `extra_codes` (multi-tag list)
- `other_flag` + `other_text`
- Save confirmation and next-item continuity without losing position.
- Annotation records must include at least: `annotator_id`, `coded_at`.
- Data model and exports must support IRR metrics (Cohen's Kappa and/or Krippendorff's alpha).
- Pilot IRR protocol:
- 300-comment set is fully double-coded by two independent annotators.
- IRR target threshold: Cohen's Kappa or Krippendorff's alpha >= 0.80.
- Disagreements are adjudicated after blind coding; adjudicated labels form gold-standard validation set.
- Performance requirements:
- Use cache-backed query layers for repeated reads.
- Pre-aggregate summary metrics in DB where possible.
- Avoid loading full raw corpus into UI memory on every interaction.
- Visual hierarchy requirements:
- Predictable layout with intentional signal colors.
- Highlight model/dictionary tags (e.g., skepticism/proof-demand) for rapid human audit.

### 12. Analytic Structure (Planning Scope)
- Analytic design will be finalized before implementation starts.
- Data structure is intentionally multi-level:
- Comment-level outcomes/labels.
- Video-level context and engagement.
- Channel-level niche and temporal structure.
- Primary inference centers on comment-level conformity dynamics within videos:
- whether a skeptical rank-1 cue is associated with skepticism in later comments.
- whether the strength of that association varies with cue magnitude (`like_count`).
- whether that association varies across creator ecosystems (`channel_niche`).
- Time specification must include both:
- Relative upload sequence index (within-channel dynamics).
- Calendar fixed effects (month/year) for external shock control.
- Default model covariates include:
- `channel_niche`
- channel size proxy (e.g., subscriber tier)
- video age
- baseline engagement (view count)
- `like_count`
- `reply_count`
- Fixed receiver-side manual outcomes:
- `skepticism_fake_callout`
- `proof_demand`
- `normalization_defense`
- Required sensitivity analyses include:
- Include vs exclude rows flagged as spam/template/duplicate.
- Include vs exclude channels with `coverage_shortfall=true`.
- Restrict response sample to comments ranked `2-20`, excluding the top-ranked cue comment.
- Boundary-condition analysis requires explicit cross-niche comparisons with reported niche-specific coverage/attrition.
- NLP validation reporting is mandatory:
- Report Precision, Recall, and F1 for automated classification against the 300-comment adjudicated gold-standard set.
- Validation benchmark design is mandatory multi-model:
- Include transparent dictionary/rules baseline.
- Include at least one advanced classifier (e.g., GPT-4o or NLI model).
- Current benchmark plan includes both advanced classifiers: GPT-4o and NLI/RoBERTa.
- Final primary production classifier will be selected after pilot performance review.
- Report absolute and relative performance gain of advanced classifier over baseline.
- Pilot exploratory analytics must be available in UI before final modeling:
- Compute pilot-ready descriptive metrics for Objectives, RQ1-RQ3, and H1-H3 from currently available data.
- Until adjudicated labels are complete, display these as rule-based proxy estimates (not confirmatory inference).

### 15. Conformity Cascade Module (Primary Confirmatory Focus)
- Use the conformity-cascade mechanism as the primary confirmatory analytic framework:
- Independent cue: whether the rank-1 (most-liked) comment is skeptical (`top_comment_skeptical`).
- Dependent response: skepticism status in subsequent comments (ranks 2-20).
- Ranking rule: within each `video_id`, sort by `like_count` desc, tie-break by `comment_timestamp` asc.
- Modeling rule: logistic mixed-effects style model with channel-level random intercepts.
- Implementation note: `statsmodels.formula.api` does not provide logistic `MixedLM`; use `BinomialBayesMixedGLM.from_formula` for binomial mixed modeling.
- Required outputs:
- fixed-effect table with log-odds, OR, and approximate 95% CI (`exp(beta ± 1.96*sd)`), plus approximate p-values.
- interaction terms for niche moderation (`top_comment_skeptical * channel_niche`).
- cue-magnitude moderation (`top_comment_skeptical * top_comment_like_count_z`).
- temporal-decay moderation (`top_comment_skeptical * hours_since_top_comment_z`).
- ICC decomposition from random intercepts for both channel and video using logistic residual variance `pi^2/3`.
- Export a per-video analysis table containing top-comment cue indicators, cue magnitude, skepticism/proof-demand proxy rates, and niche group for downstream statistical work.
- Required manuscript/reproducibility outputs:
- STROBE-style data flow diagram (screened/eligible/included/filtered).
- Niche-wise coverage and attrition table.
- Human IRR table (agreement metrics and per-label agreement).
- Main model coefficient tables (H1-H3).
- Robustness/sensitivity appendix tables.
- Key trend plots over upload sequence and calendar time.
- NLP classification performance table (Precision, Recall, F1 vs adjudicated gold standard).

### 13. Objective/RQ/Hypothesis Coverage Checklist
- This section links research goals to concrete scraping fields and planned analytics so coverage is auditable before full run.

#### Objectives
- O1 (build pipeline for Tech/Beauty/Lifestyle collection):
- Scraping coverage: `channel_id`, `channel_niche`, `video_id`, `video_publish_ts`, top-level comments, `like_count`, `reply_count`, `comment_rank`.
- Analytics/readout: batch QA coverage tables by niche, channel/video/comment counts, missingness/attrition.
- Coverage status: covered.

- O2 (produce queryable relational dataset):
- Scraping coverage: hierarchical schema `channels -> videos -> comments`, run metadata, QA metadata, CSV exports.
- Analytics/readout: reproducible extraction + export artifacts for R.
- Coverage status: covered.

- O3 (study receiver-side verification under degraded signals):
- Scraping coverage: comment text + engagement + timing + channel/video context.
- Analytics/readout: skepticism/proof-demand rates and multilevel models after annotation/classification.
- Coverage status: partially covered (requires validated labels).

#### Research Questions
- RQ1 (to what extent is an algorithmically elevated forensic cue, operationalized as an AI-skeptical top-liked comment, associated with higher skepticism in subsequent audience discourse?):
- Required inputs: ranked comments within video, top-comment skepticism label, subsequent-comment skepticism label.
- Planned analysis: mixed-effects skepticism model on response comments (ranks `2-20`) with `top_comment_skeptical` as the focal predictor.
- Coverage status: partially covered (ranking and comment metadata exist; confirmatory version requires adjudicated/validated skepticism labels).

- RQ2 (how do algorithmic engagement metrics, especially top-comment like count, shape the strength of that association?):
- Required inputs: top-comment skepticism label, top-comment like count, subsequent-comment skepticism label.
- Planned analysis: interaction model adding `top_comment_skeptical * top_comment_like_count_z`.
- Coverage status: partially covered (engagement metrics are collected; confirmatory version still depends on validated skepticism labels).

- RQ3 (how does audience epistemic vigilance and narrative contestation vary across creator ecosystems with different stakes around perceived human authenticity?):
- Required inputs: validated skepticism labels, channel niche labels, top-comment cue indicators, and response-comment outcomes.
- Planned analysis: cross-niche moderation model with `top_comment_skeptical * channel_niche`, plus descriptive niche-wise skepticism and proof-demand rates.
- Coverage status: partially covered (niche labels are collected; confirmatory version requires a final lock on the niche taxonomy, especially if `Faceless Lifestyle` is treated as a distinct analytic baseline).

#### Hypotheses
- H1 (conformity cascade): when the top-ranked comment expresses AI skepticism, subsequent comments are more likely to express skepticism as well.
- Inputs covered by scraping: ranked comments, comment text, like counts, timestamps, channel/video structure.
- Additional labeling required: validated skepticism labels.
- Planned test: mixed-effects skepticism model with `top_comment_skeptical` as the focal predictor.
- Coverage status: partial (pilot proxy-ready, confirmatory pending validated labels).

- H2 (cue magnitude): the association between a skeptical top-ranked comment and subsequent skepticism is stronger when the top-ranked comment has a higher like count.
- Inputs covered by scraping: same as H1 plus top-comment like counts.
- Additional labeling required: validated skepticism labels.
- Planned test: interaction model with `top_comment_skeptical * top_comment_like_count_z`.
- Coverage status: partial.

- H3 (boundary condition): the association between a skeptical top-ranked comment and subsequent skepticism is stronger in higher authenticity-stakes niches such as Tech and Beauty than in lower-stakes entertainment baselines such as Faceless Lifestyle.
- Inputs covered by scraping: ranked comments, skepticism outcomes, `channel_niche`.
- Additional labeling required: validated skepticism labels and a final coded mapping from current niche labels to the confirmatory niche contrast.
- Planned test: moderation model with `top_comment_skeptical * channel_niche`, reported with niche-specific marginal effects.
- Coverage status: partial.

#### Mandatory Labeling/Model Readiness Before Confirmatory Inference
- Complete 300-comment double-coding, compute IRR (target >=0.80), and adjudicate gold standard.
- Benchmark baseline dictionary vs advanced classifiers (GPT-4o and NLI/RoBERTa) with Precision/Recall/F1.
- Freeze the final top-comment skepticism coding rule for confirmatory use.
- Freeze the final hypothesis-to-niche mapping for H3, including whether `Faceless Lifestyle` is a formal coded subgroup or an analytic recode of the broader `Lifestyle` category.

### 14. Dual-Sampling Design (Agreed Next Phase)
- A two-dataset strategy will be used to improve signal density while preserving panel validity.

#### Dataset A: Core Channel Panel (Confirmatory)
- Unit: selected channels -> recent uploads in sequence.
- Purpose: primary confirmatory inference for H1-H3.
- Sampling: channel-first (existing design), balanced niche quotas where feasible.
- Modeling: multilevel comment/video/channel models centered on ranked skeptical cues and response comments.
- Constraint: preserve within-video rank information and timestamps so top-comment cue ordering remains auditable.

#### Dataset B: AI-Enriched Video Stratum (Exploratory/Power Augmentation)
- Unit: videos selected by AI/disclosure-related metadata filters.
- Purpose: increase event density for skepticism, proof-demand, and contestation analysis.
- Selection logic (v1): include videos where title/description matches AI/disclosure lexicon.
- Initial lexicon examples: `ai`, `artificial intelligence`, `chatgpt`, `gpt`, `midjourney`, `deepfake`, `made with ai`, `ai generated`.
- This stratum may be pooled across channels but must keep channel/video IDs for linkage.

#### Inference Boundary Rules
- Confirmatory manuscript claims for H1-H3 rely on Dataset A as primary.
- Dataset B is explicitly labeled exploratory/robustness unless a pre-registered integration rule is defined.
- Report results separately (`core_panel`, `ai_enriched`) before any combined sensitivity analyses.

#### Operational Requirements
- Runs must store a dataset tag in metadata (`dataset_type`: `core_panel` or `ai_enriched`).
- QA outputs must be stratified by `dataset_type` and niche.
- Exports must include dataset tags so R models can separate confirmatory vs exploratory analyses.

## Open Questions
### Analytics Design
- After pilot benchmarking, select final primary production classifier (GPT-4o vs NLI/RoBERTa vs ensemble).

## Next Interview Block
- Finalize post-pilot primary classifier selection policy.
