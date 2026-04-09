# Conference Paper Draft Kit

This file is the conference-oriented manuscript kit for the current project. It is intentionally shorter and more submission-focused than `paper.md`.

All reusable claims below are aligned to the named freeze `KES-final` (`freeze_id=8`, `freeze_uuid=freeze-20260408T142800Z`, timestamp `2026-04-08T14:28:00Z`) covering runs `11, 18, 20, 22, 23, 24`.

## Main Contribution

Use this sentence as the backbone of the paper:

A human-in-the-loop, explainable analytics system can create a defensible validated evidence layer for studying verification signals around generative-AI content, and a YouTube case demonstrates one clear downstream cue effect within that workflow.

## Best-Fit Positioning

For KES-style submission, the strongest framing is:

- primary contribution: a web-based human-in-the-loop analytics system
- novelty claim: an explicit validated-evidence / exploratory-extension split inside one explainable, reproducible research environment
- empirical role: a validated YouTube case used to demonstrate the workflow, not to support broad platform-wide theory

This means the paper should read as a system-and-methods paper with one bounded empirical validation case.

## Safer Session Fit Language

In the paper itself, use broad fit language rather than speculative session labels:

- intelligent information systems
- explainable and augmented intelligence
- human-centered analytics
- knowledge discovery and data analysis
- generative-AI applications

## Title Options

1. A Human-in-the-Loop Analytics System for Studying Verification Signals Around Generative-AI Content
2. Validated Evidence and Exploratory Extension in a Human-in-the-Loop Analytics System for Generative-AI Content Research
3. An Explainable Research Console for Studying Verification Signals Around Generative-AI Content
4. From Coding to Cue Analysis: A Human-in-the-Loop System for Generative-AI Content Research

## Recommended Title

A Human-in-the-Loop Analytics System for Studying Verification Signals Around Generative-AI Content

Subtitle if needed:

A Validated YouTube Case Study

## Conference Abstract

This paper presents a web-based human-in-the-loop analytics system for studying audience-side verification signals around generative-AI content. The core contribution is not a standalone dashboard or classifier, but an explainable research environment that preserves a strict boundary between validated human-coded evidence and broader exploratory automation. The system integrates collection management, coding, disagreement detection, adjudication, explainable screening, coding prioritization, and exportable analytics within one reproducible workflow. We demonstrate the system through a validated YouTube comment case. The frozen evidence base contains 1,322 resolved comments from runs 11, 18, 20, 22, 23, and 24; all comments were double-coded, 224 involved disagreement, and 0 remained unresolved at freeze. Within this validated layer, 209 comments were positive on at least one core label, including 106 skepticism comments, 4 proof-demand comments, and 99 normalization comments. The main empirical result demonstrates a robust conformity cascade: skeptical top-ranked comments strongly predict downstream skepticism (OR = 17.26, 95% CI [10.87, 27.40], p < 1e-30), with clear niche moderation (skeptical × Beauty OR = 21.72, p < 1e-19; skeptical × Tech OR = 0.205, p = 0.00018). Cue-magnitude and elapsed-time interactions are not significant in the current freeze-scoped model. The paper therefore contributes an explainable augmented-intelligence workflow plus one robustly validated empirical demonstration of its analytical value.

## 100-Word Version

We present a web-based human-in-the-loop analytics system for studying verification signals around generative-AI content. Its main novelty is an explicit split between a frozen validated evidence layer and a broader exploratory extension layer inside one explainable workflow. The system combines collection, coding, adjudication, assistive screening, prioritization, and integrated analytics. We validate it on YouTube comments using a frozen evidence base of 1,322 resolved double-coded comments, including 224 disagreement cases and 0 unresolved disagreements. Skeptical top-ranked comments strongly predict downstream skepticism (OR = 17.26, 95% CI [10.87, 27.40], p < 1e-30), with significant niche interactions (Beauty amplification and Tech attenuation), while skeptical × like-count and skeptical × time interactions are not significant in the current freeze-scoped model.

## Three-Bullet Contribution Version

1. We introduce an explainable human-in-the-loop analytics system that separates validated evidence production from exploratory extension inside one reproducible research environment.
2. We make that boundary operational through double-coding, disagreement detection, adjudication, and evidence freezing rather than treating automation as equivalent to human validation.
3. We validate the system on YouTube comments and demonstrate a robust conformity cascade: skeptical top-ranked comments strongly predict downstream skepticism (OR = 17.26, p < 1e-30) with significant niche interactions, while cue-magnitude and temporal interactions are not significant in the current freeze-scoped model.

## Recommended Paper Structure

1. Introduction
2. System Design
3. Validation Workflow
4. YouTube Validation Case
5. Results
6. Discussion, Ethics, and Limitations
7. Conclusion

## Section Plan

### 1. Introduction

Goal:

- define the workflow problem
- make the system the paper’s main object
- position the YouTube analysis as validation, not the whole paper

Suggested opening paragraph:

Generative-AI content is increasingly visible in platform ecosystems, but audience-side verification signals are methodologically difficult to study. Researchers must move from raw platform data to validated labels, disagreement handling, transparent screening, and reproducible analysis, yet these steps are often split across disconnected tools. This paper addresses that workflow problem by introducing a human-in-the-loop analytics system for studying verification signals around generative-AI content.

Suggested second paragraph:

The system’s main novelty is not generic integration alone. Rather, it is the explicit separation of a validated evidence layer from a broader exploratory extension layer inside one explainable and reproducible environment. Human coding and adjudication determine the confirmatory dataset; automated signals remain assistive and are used for prioritization, screening, and exploratory mapping.

Suggested third paragraph:

We validate the system through a YouTube comment case study spanning 1,322 double-coded comments. The empirical contribution demonstrates robust conformity cascades while revealing theoretically meaningful moderation by channel niche. The paper supports three main findings: (1) a strong ranked-cue effect showing skeptical top comments predict downstream skepticism, (2) significant niche interactions (Beauty amplification and Tech attenuation), and (3) non-significant skeptical-cue interactions for cue-like magnitude and elapsed time in the current freeze-scoped model.

### 2. System Design

Goal:

- establish the system as the primary contribution
- define novelty more precisely than “dashboard + annotation”

Suggested paragraph:

The platform was designed as a full research environment rather than as a single annotation interface. It supports collection and run management, manual coding, disagreement detection, adjudication, explainable rule-based screening, coding prioritization, multilingual and low-information text diagnostics, integrated analytics views, and exportable reproducibility bundles. Its central design principle is epistemic separation: validated claims rely only on resolved human-coded evidence, whereas automation is visible, explainable, and analytically useful but does not enter the main confirmatory layer by default.

Short novelty statement to reuse:

The system contributes an explainable, evidence-preserving workflow in which validated human-coded evidence and exploratory automation are intentionally connected but never conflated.

### 3. Validation Workflow

Goal:

- replace vague claims of “validated” with procedure

Suggested validation subsection:

The core codebook contained three substantive labels: skepticism, proof-demand, and normalization. Skepticism captured comments that challenged authenticity or explicitly called AI-mediated content fake or misleading. Proof-demand captured comments that requested evidence, demonstration, or disclosure proof. Normalization captured comments that defended, accepted, or downplayed AI involvement as ordinary or acceptable. Coders worked inside the research console with comment text, thread context, and visible automation hints, but those hints were assistive rather than binding. Comments entered the main evidence base only after two independent coding passes. Disagreements were flagged automatically and resolved through adjudication in the same environment. A comment counted as resolved if it was either fully agreed upon across coders or explicitly adjudicated. The evidence layer was then locked as a named freeze, preventing later exploratory work from altering the main confirmatory layer.

Suggested reproducibility paragraph:

Paper-facing analyses are anchored to freeze `KES-final` (`freeze_id=8`, `freeze_uuid=freeze-20260408T142800Z`, timestamp `2026-04-08T14:28:00Z`). This freeze includes runs `11, 18, 20, 22, 23, 24` with `1,322` resolved comments (`1,322` double-coded; `224` disagreement cases; `0` unresolved disagreements). The freeze record stores deterministic logic metadata used by the workflow (`rules_version=deterministic-rules-v1.1.0`, `scoring_version=assistive-scoring-v1.1.0`, `preprocessing_profile=clean_top20_v1`, plus preprocessing/signal-detection/triage/priority sub-version registry). Re-running exports from the same freeze reproduced identical freeze identity and summary tables; model effects were numerically stable with only negligible floating-point variation (maximum absolute difference `< 6e-05`), leaving substantive interpretation unchanged.

Suggested label-definition table:

| Label | Operational definition | Used in main analysis |
| --- | --- | --- |
| Skepticism | Challenges authenticity, calls content fake, or questions truthfulness | Yes |
| Proof-demand | Requests evidence, proof, or verifiable disclosure | Yes |
| Normalization | Accepts, defends, or downplays AI use as normal | Yes |
| Extra tags / Other | Auxiliary coding for context and edge cases | No, descriptive only |

Suggested validation numbers paragraph:

Across the frozen runs, the validated layer contains 1,322 resolved double-coded comments. Of these, 224 involved disagreement and 0 remained unresolved at freeze. Put differently, 16.9% of double-coded comments required disagreement handling, while the remaining cases entered the evidence layer through coder agreement. This makes the main dataset procedurally auditable rather than merely convenient.

Optional agreement sentence if space allows:

At the label level, raw disagreement before adjudication was concentrated in skepticism and normalization, while proof-demand disagreement remained rare, consistent with the scarcity of proof-demand in the corpus (0.4% prevalence).

Suggested reliability paragraph:

Inter-rater reliability was assessed on the subset of 242 double-coded comment pairs for which both original coder records were still available prior to adjudication. On this subset, agreement was perfect for the skepticism label (Cohen's kappa = 1.00; Krippendorff's alpha = 1.00). Proof-demand and normalization also showed 100% agreement, with Krippendorff's alpha = 1.00 in both cases, while Cohen's kappa was undefined because no positive cases appeared in that subset. Reliability cannot be computed on the full validated dataset because the current adjudication workflow does not preserve pre-adjudication label histories for all adjudicated rows. Accordingly, the paper should report the subset IRR transparently and treat full-dataset consensus as an adjudication outcome rather than as a full-dataset reliability estimate.

Short metric line to reuse:

- IRR subset: `n = 242` double-coded pairs; skepticism `kappa = 1.00`, `alpha = 1.00`; proof-demand `alpha = 1.00` (kappa undefined); normalization `alpha = 1.00` (kappa undefined)

### 4. YouTube Validation Case

Goal:

- keep the empirical case bounded
- make YouTube a proof-of-use

Suggested paragraph:

We demonstrate the system through a YouTube comment case spanning runs 11, 18, 20, 22, 23, and 24. The broader database currently contains 27 runs, 205 channels, 3,463 videos, and 33,467 comments, but the paper’s main claims rely only on the frozen resolved-consensus subset. This separation is intentional. The YouTube case is used to show that the workflow can move from raw collection to validated analysis while preserving a clear distinction between confirmatory evidence and exploratory extension.

### 4.1 Model Specification

Suggested one-page subsection:

The main conformity analysis was estimated on response comments ranked 2-20 within each video thread. For every video, comments were first ordered by descending like count, with earlier timestamps used as the tie-breaker. The highest-ranked comment was treated as the visible cue, and the remaining ranked comments in positions 2-20 were treated as downstream responses. The dependent variable was a binary skepticism label on each response comment. The primary predictor was whether the top-ranked cue comment in that thread was itself skeptical. To test contextual moderation, the model included channel niche, the z-standardized like count of the top-ranked cue, the z-standardized number of hours elapsed between the top-ranked cue and each response comment, and interactions between skeptical cue status and each of those moderators.

Formally, the fixed-effects portion of the model can be written as:

`logit(P(response_skepticism_ij = 1)) = beta_0 + beta_1 skeptical_top_cue_j + beta_2 niche_j + beta_3 skeptical_top_cue_j x niche_j + beta_4 top_like_z_j + beta_5 skeptical_top_cue_j x top_like_z_j + beta_6 hours_since_top_z_ij + beta_7 skeptical_top_cue_j x hours_since_top_z_ij`

where `i` indexes response comments and `j` indexes videos. Lifestyle served as the reference niche when available. Because responses were nested within both channels and videos, the model was estimated as a mixed-effects logistic regression with random intercepts for channel and video. In implementation, the paper’s analysis used a binomial Bayesian mixed-effects model with variance components for `channel_id` and `video_id`, and fixed-effect uncertainty was summarized through approximate z-statistics, two-sided p-values, and 95% confidence intervals transformed into odds ratios. The headline H1 estimate therefore represents the multiplicative change in the odds that a downstream response comment is skeptical when the top-ranked cue is skeptical, holding the included moderators constant. H2 was evaluated through the skeptical-cue by top-like-count interaction, H3 through skeptical-cue by niche interactions, and temporal decay through the skeptical-cue by elapsed-time interaction.

Short methods version:

- unit of analysis: response comments ranked `2-20`
- cue definition: rank-1 comment within each video, sorted by like count and timestamp
- outcome: binary skepticism label on the response comment
- model family: mixed-effects logistic regression
- random intercepts: `channel_id`, `video_id`
- moderators: `channel_niche`, `top_comment_like_count_z`, `hours_since_top_comment_z`
- key interactions: skeptical cue x niche, skeptical cue x like count, skeptical cue x elapsed time

### 5. Results

Use this section asymmetrically.

#### 5.1 Descriptive Results

Suggested paragraph:

Within the frozen evidence base, 209 of 1,322 comments were positive on at least one core label (15.8%). The validated dataset contained 106 skepticism comments (8.0%), 4 proof-demand comments (0.3%), and 99 normalization comments (7.5%). Proof-demand remains too sparse to sustain hypothesis testing on its own. The descriptive picture shows substantial skepticism and normalization signals in the validated layer, motivating the conformity cascade analysis focused on skepticism as the primary verification signal.

#### 5.2 Main Supported Result

Suggested paragraph:

The main supported result demonstrates robust conformity cascades (H1). In the current freeze-scoped model, skeptical top-ranked comments strongly predict downstream skepticism (OR = 17.26, 95% CI [10.87, 27.40], p < 1e-30). Niche moderation is significant: the skeptical-cue interaction is strongly positive in Beauty (OR = 21.72, 95% CI [11.24, 41.97], p < 1e-19) and strongly negative in Tech (OR = 0.205, 95% CI [0.090, 0.470], p = 0.00018), relative to Lifestyle. By contrast, skeptical × like-count and skeptical × elapsed-time interactions are not significant in this freeze-scoped specification. These findings demonstrate that the validated workflow recovers robust main effects and interpretable cross-niche structure from platform comment data.

#### 5.3 Secondary And Exploratory Checks

Suggested paragraph:

Originally planned H2 (cue-magnitude moderation via skeptical × like-count interaction) is not supported in the current freeze-scoped model (OR = 0.885, p = 0.897). Temporal moderation is also not supported (skeptical × time OR = 1.57, p = 0.594). Originally planned H3 (niche heterogeneity) is supported through significant skeptical-cue interactions in Beauty and Tech.

Short version:

The empirical section supports three main findings: (1) a robust conformity cascade main effect, (2) significant niche moderation, and (3) non-significant skeptical-cue interactions for cue-like magnitude and elapsed time in the current freeze-scoped model.

### 6. Discussion, Ethics, and Limitations

Suggested methodological significance paragraph:

The main value of the system is not that it automates content analysis end to end, but that it preserves the distinction between validated evidence production and broader exploratory mapping. In this project, that design made it possible to stabilize a defensible confirmatory dataset while still using explainable automation to inspect the wider uncoded corpus. This is especially useful in generative-AI research settings where the total corpus is much larger than what can be coded manually with high confidence.

Suggested empirical interpretation paragraph:

Substantively, the findings reveal three theoretically meaningful patterns. First, skeptical audience reactions exhibit robust conformity cascades: when skepticism is visible at the top of a thread, downstream responses are much more likely to be skeptical (OR = 17.26). Second, this process differs across niches in the current freeze-scoped model, with strong amplification in Beauty and attenuation in Tech relative to Lifestyle. Third, skeptical-cue interactions with cue-like magnitude and elapsed time are not significant in the same specification. The paper does not claim broad causal identification or platform-wide generalization; it instead uses these results as a bounded validation case showing that the workflow can recover robust main effects and interpretable moderation patterns from platform comment data.

Suggested ethics and reproducibility paragraph:

The study relies on public platform comments, but the workflow is designed to minimize unnecessary exposure of personal information. Analytical tables use internal database identifiers and hashed commenter fields rather than public-facing account names, and the paper should report aggregate statistics plus carefully selected excerpts only where analytically necessary. Reproducibility is supported through named evidence freezes with explicit IDs/UUIDs, versioned assistive logic metadata, exportable analysis bundles, and strict separation between the validated evidence layer and the exploratory extension layer.

Suggested limitations paragraph:

The paper should be read as a validated conference-scale case rather than as a population estimate of audience behavior on YouTube. The frozen evidence base is a curated human-labeled subset spanning 1,322 comments, with proof-demand remaining too rare (0.3%) for independent analysis. Inter-rater reliability is computable only on the 242 double-coded comment pairs for which pre-adjudication coder records were preserved; the current workflow does not retain full label history for all previously adjudicated rows. These constraints are acceptable for a systems paper with robust empirical validation, but the findings should be interpreted as demonstrating the workflow's analytical capacity rather than as definitive platform-wide behavioral claims.

### 7. Conclusion

Suggested paragraph:

This paper introduces a human-in-the-loop analytics system for studying verification signals around generative-AI content and validates it through a YouTube comment case spanning 1,322 double-coded comments. The main contribution is an explainable, reproducible workflow that preserves a strict boundary between frozen validated evidence and exploratory extension. Within that framework, we demonstrate robust conformity cascades where skeptical top-ranked comments strongly predict downstream skepticism (OR = 17.26, p < 1e-30), with significant niche interactions and non-significant skeptical-cue interactions for cue-like magnitude and elapsed time in the current freeze-scoped model. This makes the paper strongest as a system-and-methods contribution with conservative, defensible empirical validation.

## H1 / H2 / H3 Status

Use this wording consistently:

- H1: **robustly supported** and headline-worthy (OR = 17.26, p < 1e-30)
- H2 (like count × skeptical cue interaction): **not supported** (OR = 0.885, p = 0.897)
- H3 (niche moderation): **supported** (Beauty interaction OR = 21.72, p < 1e-19; Tech interaction OR = 0.205, p = 0.00018)
- Temporal moderation (skeptical × time): **not supported** (OR = 1.57, p = 0.594)

Paper-ready wording:

- H1 predicts that downstream response comments are more likely to express skepticism when the top-ranked comment is itself skeptical. **Strongly supported** (OR = 17.26, 95% CI [10.87, 27.40], p < 1e-30).
- H2 cue-magnitude moderation is not supported in this freeze-scoped model (skeptical × like count OR = 0.885, p = 0.897).
- H3 niche moderation is supported: Beauty shows amplification (OR = 21.72, p < 1e-19) and Tech shows attenuation (OR = 0.205, p = 0.00018) relative to Lifestyle.
- Temporal moderation is not supported (skeptical × time OR = 1.57, p = 0.594).

## Key Numbers To Reuse

- runs in frozen evidence layer: `11, 18, 20, 22, 23, 24`
- freeze name: `KES-final`
- freeze id: `8`
- freeze uuid: `freeze-20260408T142800Z`
- freeze timestamp: `2026-04-08T14:28:00Z`
- rules_version: `deterministic-rules-v1.1.0`
- scoring_version: `assistive-scoring-v1.1.0`
- preprocessing_profile: `clean_top20_v1`
- preprocessing_rules_version: `preprocessing-v1.0.0`
- signal_detection_rules_version: `signal-detection-v1.0.0`
- triage_scoring_version: `triage-v1.0.0`
- priority_scoring_version: `priority-v1.0.0`
- resolved comments: `1,322`
- double-coded comments: `1,322`
- disagreement comments: `224`
- unresolved disagreements: `0`
- disagreement rate: `16.9%`
- any core positive: `209` (15.8%)
- skepticism: `106` (8.0%)
- proof-demand: `4` (0.3%)
- normalization: `99` (7.5%)
- skeptical top-cue videos (model summary): `10`
- response comments in model frame: `787`
- channels: `57`
- videos (total): `374`

**H1 Main Effect:**
- H1 odds ratio: `17.26`
- H1 95% CI: `[10.87, 27.40]`
- H1 p-value: `< 1e-30`
- H1 coefficient: `2.848` (SE = 0.236)

**Niche Moderation (H3 - supported):**
- Beauty interaction OR: `21.72`, 95% CI `[11.24, 41.97]`, p `< 1e-19`
- Tech interaction OR: `0.205`, 95% CI `[0.090, 0.470]`, p `= 0.00018`

**Cue Interaction (H2 - not supported):**
- Skeptical × like count OR: `0.885`, 95% CI `[0.140, 5.610]`, p `= 0.897`

**Temporal Interaction (not supported):**
- Skeptical × time OR: `1.572`, 95% CI `[0.298, 8.306]`, p `= 0.594`

- current broader database: `27` runs, `205` channels, `3,463` videos, `33,467` comments

## Recommended Figure/Table Set

Use a small, defensible set.

1. Boundary figure
   Show: raw corpus -> screened corpus -> coded corpus -> adjudicated/resolved corpus -> frozen validated evidence -> exploratory extension.

2. Validation table
   Include: double-coded comments, disagreement cases, unresolved disagreements, freeze date, and resolved evidence size.

3. Systems table
   Include rows like:
   - broader collected corpus: `33,467` comments, assistive collection layer
   - labeled comments in frozen runs: ~2,500, mixed human/assistive workflow
   - frozen resolved evidence: `1,322`, human-validated main analysis layer
   - disagreement cases: `224`, human adjudication layer
   - unresolved disagreements: `0`, frozen state
   - exploratory remainder: corpus outside frozen validated layer, assistive screening only

4. Main results table
   Highlight supported findings:
   - H1 main effect: OR = 17.26, p < 1e-30
   - H3 niche moderation: Beauty amplification and Tech attenuation (both significant)
   - Skeptical × like count interaction: not significant
   - Skeptical × time interaction: not significant

## What To Leave Out

- broad claims about "how audiences interpret GenAI content" in general
- long feature catalogs
- causal language implying platform-wide behavioral mechanisms
- attempts to make proof-demand a major result (still only 4 comments, 0.3%)
- language implying that automated screening expands the confirmatory evidence base
- claims that non-significant interactions are meaningful moderators

## Good Final Claim

The paper shows that a human-in-the-loop analytics system can produce a defensible validated evidence layer while retaining a broader exploratory extension layer, and that this workflow recovers a strong conformity cascade with clear cross-niche structure in a bounded YouTube validation case.

## Current Freeze Snapshot (KES-final)

- freeze anchor: `KES-final` (`freeze_id=8`, `freeze_uuid=freeze-20260408T142800Z`)
- resolved comments: `1,322`
- disagreement cases: `224`
- unresolved disagreements: `0`
- main effect: skeptical top cue OR `17.26` (p < `1e-30`)
- significant niche interactions: Beauty amplification, Tech attenuation
- skeptical × like-count interaction: not significant
- skeptical × elapsed-time interaction: not significant
