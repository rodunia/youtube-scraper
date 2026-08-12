# KES 2026 Methods Audit Findings (2026-04-20)

This file records the current, manuscript-facing model implementation and reliability findings from the local codebase and refreshed outputs.

## Canonical Source Priority

1. `exports/paper_figures/kes_final/paper_figure_pack_manifest.json`
2. `exports/paper_figures/kes_final/figure_04_model_forest_effects.csv`
3. `src/youtube_scraper/conformity_cascade.py`
4. `src/youtube_scraper/paper_figures.py`
5. `data/irr_metrics_2026-04-03.json` (regenerated 2026-04-20)

Superseded intermediate files (for history only, not manuscript authority):

- `data/exports/conformity_v2_summary_20260405T051958Z.json`
- `paper.md` (legacy drafting file)

## New Outputs Refreshed On 2026-04-20

- Paper figure pack regenerated from freeze `KES-final` (`freeze_id=8`, `freeze_uuid=freeze-20260408T142800Z`) using:
  - `PYTHONPATH=src python -m youtube_scraper.cli paper-figure-pack --freeze-name KES-final --out-dir exports/paper_figures/kes_final`
- IRR metrics regenerated using:
  - `python calculate_irr.py`

## 1) Main Model

- Fitting package/function:
  - `statsmodels.genmod.bayes_mixed_glm.BinomialBayesMixedGLM.from_formula(...).fit_vb()`
- Estimator type:
  - Bayesian binomial mixed-effects logistic model (variational Bayes fit).
- Link:
  - logit.
- Random effects:
  - variance components / random intercepts for `channel_id` and `video_id`:
    - `channel_re: 0 + C(channel_id)`
    - `video_re: 0 + C(video_id)`
- Observational unit:
  - response comment rows ranked 2-20 per video thread (after ranking by like count, then timestamp tie-break).
- Freeze-scoped response frame from refreshed run:
  - `response_n = 787`
  - `videos_with_responses = 218`
  - `channels_with_responses = 46`
  - `cue_videos = {non_skeptical: 208, skeptical: 10}`
  - `cue_rows = {non_skeptical: 660, skeptical: 127}`

## 2) Inference Implementation

- p-values:
  - Wald-like normal approximation from `z = coef / sd`, `p = 2 * norm.sf(abs(z))`.
- 95% intervals:
  - `coef +/- 1.96 * sd`, then exponentiated to OR scale.
- Odds ratios:
  - `OR = exp(coef)`.
- Not implemented:
  - no LRT-based p-values, no profile likelihood CIs, no bootstrap CIs, no posterior quantile credible intervals.

## 3) Current Headline Effects (Refreshed Canonical Export)

From `exports/paper_figures/kes_final/figure_04_model_forest_effects.csv`:

- `top_comment_skeptical`: OR `17.257875`, 95% CI `[10.871683, 27.395416]`, `p=1.334750e-33`
- `top_comment_skeptical x Beauty`: OR `21.722177`, 95% CI `[11.241421, 41.974495]`, `p=5.220394e-20`
- `top_comment_skeptical x Tech`: OR `0.205412`, 95% CI `[0.089695, 0.470415]`, `p=1.812091e-04`
- `top_comment_skeptical x like_count_z`: OR `0.884876`, 95% CI `[0.139570, 5.610139]`, `p=8.967260e-01`
- `top_comment_skeptical x hours_since_top_comment_z`: OR `1.572356`, 95% CI `[0.297654, 8.305962]`, `p=5.940659e-01`

Manifest headline (same run):

- H1 OR: `17.257875475408724`
- H1 p-value: `1.334750488801457e-33`

## 4) Unit of Analysis and Nesting Clarification

- Comment-level variables:
  - `is_skeptical` (response label), `comment_timestamp`, response rank, text.
- Thread/video-level top-cue variables:
  - `top_comment_skeptical`, `top_comment_like_count`, `top_comment_timestamp`.
- Derived moderation variables:
  - `top_comment_like_count_z` (top-cue level, repeated over responses in thread),
  - `hours_since_top_comment_z` (response-level elapsed time from top cue).
- Grouping/nesting handled in model:
  - random intercept variance components for both `channel_id` and `video_id`.

## 5) Sparsity and Interaction Stability

Evidence of sparse cue-positive structure is present:

- skeptical top-cue videos: `10` total.
- skeptical-cue response rows: `127` total.

By niche (rows with skeptical top cue):

- Beauty: `57`
- Lifestyle: `22`
- Tech: `48`

Interpretation for reporting:

- H1 is strongly estimated and appropriate as the primary result.
- Interaction terms are less stable/fragile than H1, especially where CIs are very wide:
  - skeptical x like_count_z CI spans `0.139570` to `5.610139`
  - skeptical x time CI spans `0.297654` to `8.305962`

## 6) IRR Implementation and Limits

IRR script:

- `calculate_irr.py`
- Metrics:
  - Cohen's kappa via `sklearn.metrics.cohen_kappa_score`
  - Krippendorff's alpha via custom `krippendorff_alpha(...)`
  - percent agreement and confusion matrices

What subset IRR uses:

- only comments where two non-adjudicated coder records remain (`a1.is_adjudicated=0` and `a2.is_adjudicated=0`).
- current size: `242` pairs.

Current regenerated IRR output (`data/irr_metrics_2026-04-03.json` generated at `2026-04-20T14:49:39.802649`):

- skepticism: agreement `1.0`, kappa `1.0`, alpha `1.0`
- proof: agreement `1.0`, kappa `null` (undefined due to no positive class), alpha `1.0`
- normalization: agreement `1.0`, kappa `null` (undefined due to no positive class), alpha `1.0`
- adjudication status:
  - total double-coded `1322`
  - adjudicated `1080`
  - non-adjudicated `242`

Constraint:

- full-dataset pre-adjudication IRR is not recoverable from current workflow history; only the preserved non-adjudicated subset is estimable.

## 7) Manuscript-Safe Model Sentence

Use this sentence in the methods section:

"We estimated a binomial Bayesian mixed-effects logistic model in statsmodels (`BinomialBayesMixedGLM.from_formula`, `fit_vb`) with random-intercept variance components for `channel_id` and `video_id`, and summarized fixed effects as odds ratios with normal-approximation 95% intervals (`estimate +/- 1.96 x SD`, exponentiated) and two-sided z-approximate p-values (`2*Phi(-|estimate/SD|)`)."

## 8) Reproducibility Status (Latest Run)

From `exports/paper_figures/kes_final/figure_03_reproducibility_summary.json`:

- `max_abs_coef_diff = 1.128920408294265e-05`
- `max_abs_or_diff = 5.040762630059703e-05`
- `max_abs_p_diff = 9.504346804911634e-06`
- `tolerance = 0.0001`
- `pass_within_tolerance = true`

This confirms small numeric variability from VB reruns but no substantive change in interpretation.
