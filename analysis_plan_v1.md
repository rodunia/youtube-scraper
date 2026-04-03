# Analysis Plan v1 (Conformity Cascade Focus)

## 1) Scope and Analysis Sets
- Primary confirmatory scope: regular YouTube videos (non-Shorts), not replies.
- Unit of collection: top-level comments on sampled channel videos.
- Comment cap policy (primary): up to 20 clean comments per video.
- If a video has <20 clean comments: keep all available clean comments and retain video.
- Shorts are analyzed separately as exploratory robustness, not merged into confirmatory core.

## 2) Hypotheses Mapped to Models
- H1: when the top-ranked comment expresses AI skepticism, subsequent comments are more likely to express skepticism as well.
- H2: the association between a skeptical top-ranked comment and subsequent skepticism is stronger when the top-ranked comment has higher like count.
- H3: the association between a skeptical top-ranked comment and subsequent skepticism is stronger in higher authenticity-stakes niches than in lower-stakes entertainment baselines.

## 3) Variables (Operational)
- Comment-level outcomes:
  - `skepticism` (0/1)
  - `proof_demand` (0/1)
  - `normalization_defense` (0/1; descriptive/secondary)
- Cue-level predictors:
  - `top_comment_skeptical` in {0,1} from rank 1
  - `top_comment_like_count_z`
  - `hours_since_top_comment_z` (timing robustness)
- Response sample:
  - comments ranked `2-20` within each video
- Key exposure for H1:
  - `top_comment_skeptical`
- Key exposure for H2:
  - `top_comment_skeptical * top_comment_like_count_z`
- Key exposure for H3:
  - `top_comment_skeptical * channel_niche`
- Controls (default):
  - `channel_niche`
  - `subscriber_tier` (or log subscribers if available)
  - `video_age_days`
  - `view_count` (log1p)
  - `comment_like_count` (log1p) for comment-level models
  - `comment_reply_count` (log1p) for comment-level models
  - calendar fixed effects: `month_year`
  - within-channel sequence index: `upload_index`

## 4) Primary Confirmatory Models (Exact Formulas)

### Model M1 (H1): Comment-level skepticism mixed logit
- Estimation target:
  - `skepticism_ij ~ Bernoulli(p_ij)`
  - `logit(p_ij) = beta0 + beta1*top_comment_skeptical_j + beta2*niche_j + beta3*log1p(view_count)_j + beta4*video_age_days_j + beta5*log1p(like_count)_ij + beta6*log1p(reply_count)_ij + FE(month_year_j) + u_channel + v_video`
  - `u_channel ~ N(0, sigma_channel^2), v_video ~ N(0, sigma_video^2)`
- Planned test:
  - H1: `beta1 > 0`

### Model M2 (H2): Cue-magnitude moderation
- Estimation target:
  - `skepticism_ij ~ Bernoulli(q_ij)`
  - `logit(q_ij) = gamma0 + gamma1*top_comment_skeptical_j + gamma2*top_comment_like_count_z_j + gamma3*(top_comment_skeptical_j * top_comment_like_count_z_j) + gamma4*niche_j + gamma5*log1p(view_count)_j + gamma6*video_age_days_j + gamma7*log1p(like_count)_ij + gamma8*log1p(reply_count)_ij + FE(month_year_j) + u_channel + v_video`
- Planned test:
  - H2: `gamma3 > 0`

### Model M3 (H3): Boundary-condition moderation
- Main model:
  - `logit(r_ij) = delta0 + delta1*top_comment_skeptical_j + delta2*niche_j + delta3*(top_comment_skeptical_j * niche_j) + delta4*log1p(view_count)_j + delta5*video_age_days_j + delta6*log1p(like_count)_ij + delta7*log1p(reply_count)_ij + FE(month_year_j) + u_channel + v_video`
- Robust alternatives:
  - add `top_comment_like_count_z` and `hours_since_top_comment_z` to the moderation specification.
  - estimate niche-specific marginal effects from the same interaction model.
- Planned test:
  - H3 main: `delta3 > 0` for higher authenticity-stakes niches relative to the reference baseline.

## 5) Ranking and Response Rules
- Ranking within each video:
  - sort by `like_count` descending, tie-break by `comment_timestamp` ascending.
- Cue:
  - `top_comment_skeptical` from rank 1.
- Response sample:
  - ranks 2-20 only.
- Report:
  - log-odds, OR, 95% CI, p-value (approx for VB mixed logit), ICC(channel), ICC(video).

## 6) Inclusion/Exclusion and Data Quality Rules
- Primary analysis excludes flagged rows:
  - `is_spam=1` OR `is_template=1` OR `is_duplicate=1`.
- Sensitivity runs:
  - include flagged rows (full sample).
  - restrict to videos with at least 5 / 10 / 15 response comments.
  - exclude channels with `coverage_shortfall=true`.
- Keep `comments_disabled` and `not_enough_comments` as explicit status covariates/descriptive strata.

## 7) Missing Data and Inference Conventions
- Transform heavy-tailed counts with `log1p`.
- If key outcome/predictor missing: drop row with count reported in flow table.
- Cluster-aware uncertainty is handled via random intercept structure.
- Multiplicity control for hypothesis family:
  - report raw p-values and FDR-adjusted q-values for main fixed-effect hypothesis tests.

## 8) Planned Output Tables (Manuscript)
- Table 1: Sample composition by niche, run, and status (`ok`, `not_enough_comments`, `comments_disabled`).
- Table 2: Attrition and cleaning counts (raw vs clean comments; spam/template/duplicate shares).
- Table 3: Descriptive statistics for key variables (comment and video level).
- Table 4: H1 mixed-logit results (core conformity-cascade association).
- Table 5: H2 moderation results (cue-magnitude interaction).
- Table 6: H3 moderation results (niche interaction and niche-specific marginal effects).
- Table 7: Robustness checks (timing, minimum-response thresholds, include/exclude flagged comments).
- Table 8: ICC and variance decomposition (channel/video/residual).
- Table 9: IRR results (Kappa/alpha) for 300-comment double coding.
- Table 10: NLP classifier benchmark vs adjudicated gold standard (Precision/Recall/F1 for baseline and advanced model).
- Table 11: Descriptive proof-demand and normalization summaries by niche and cue condition.

## 9) Planned Figures
- Figure 1: STROBE-style data flow diagram.
- Figure 2: Niche-wise data quality and attrition bars.
- Figure 3: Predicted skepticism probability by top-comment skepticism condition.
- Figure 4: Cue-magnitude moderation plot across the top-comment like-count range.
- Figure 5: Niche-specific conformity-cascade marginal effects.
- Figure 6: Distribution of response-comment skepticism by rank position (`2-20`).
- Figure 7: Conformity-cascade effect plot (OR with 95% CI across model specs).

## 10) Decision Lock for v1
- Keep primary cap at 20 clean comments per video.
- Add optional exploratory extension with 50-comment cap on a smaller balanced subset only.
- Do not switch confirmatory core to 50 until extension shows clear gain without niche bias.

## 11) Required Inputs Before Confirmatory Freeze
- Final niche framing lock:
  - either keep the confirmatory contrast within the current `Tech` / `Beauty` / `Lifestyle` frame, or introduce an explicit coded `Faceless Lifestyle` subgroup before confirmatory estimation.
- Completed adjudicated labels for pilot 300 comments.
- Final top-comment skepticism coding rule and response-comment skepticism labeling workflow.
- Final classifier choice (baseline + advanced model retained in reporting).
