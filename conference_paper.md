# Conference Paper Draft Kit

This file is a conference-focused version of the manuscript materials. It is intentionally shorter, tighter, and more presentation-oriented than `paper.md`.

All counts and reusable claims below are aligned to the frozen evidence bundle saved on `2026-03-31` in `data/evidence_base_freeze.json` and `data/exports/final_analysis_bundle_20260331T205147Z.json`.

## Best-Fit Positioning

For a conference paper, the strongest framing is:

- primary contribution: a web-based human-in-the-loop analytics system for studying verification signals around generative-AI content
- method angle: augmented intelligence through explainable screening, coding support, and integrated analytics workspaces
- empirical demonstration: a validated YouTube comment case showing skepticism, normalization, and ranked-cue effects

This means the paper should not read like a broad social-media content paper with an app attached. It should read like a methods-and-system paper with a clear empirical proof-of-use.

## Session Fit

The clearest session alignment is with:

- Generative Artificial Intelligence
- GenAI Web-based Systems
- Augmented Intelligence
- eXplainable Artificial Intelligence
- Data Analytics
- Data Science and Visualization Systems
- Human-centered Computing

The submission should therefore emphasize:

- the research console as a smart web-based system
- human-centered augmentation rather than full automation
- explainable weak labeling and transparent decision support
- integrated analysis and visualization workflows
- the YouTube study as a real-world validation case rather than the sole contribution

## Title Options

1. A Human-in-the-Loop Analytics System for Studying Verification Signals Around Generative-AI Content
2. An Explainable Web-Based Analytics Console for Generative-AI Content Research
3. From Annotation to Cue Analysis: An Augmented-Intelligence System for Generative-AI Content Research
4. Tracking Skepticism and Normalization Around Generative-AI Content with a Web-Based Research Console

## Recommended Title

A Human-in-the-Loop Analytics System for Studying Verification Signals Around Generative-AI Content

Subtitle if needed:
Evidence from a Validated YouTube Comment Case Study

## Conference Abstract

This paper presents a web-based human-in-the-loop analytics system for studying audience-side verification signals around generative-AI content. The system integrates collection management, annotation, adjudication, explainable weak labeling, multilingual and low-information text screening, model-assisted coding prioritization, and exportable analytics readouts within a single workflow designed to augment rather than replace human judgment. As an empirical demonstration, we apply the system to YouTube comments collected across multiple runs and niches. The final validated evidence base consists of 1,100 resolved comments that were double-coded and either adjudicated or fully agreed upon across coders on three core labels: skepticism, proof-demand, and normalization. Within this evidence base, 114 comments were positive on at least one core label, including 42 skepticism comments, 4 proof-demand comments, and 68 normalization comments. A pooled ranked-cue analysis shows that response skepticism rises from 2.44% after non-skeptical top-ranked comments to 30.0% after skeptical top-ranked comments, with a statistically significant top-cue skepticism effect in the pooled model (OR approximately 8.62, `p ≈ 0.016`). Evidence for cue-magnitude moderation remains weak, and niche moderation is best treated as exploratory. The paper contributes both a reusable augmented-intelligence research console and a validated empirical case for studying how audiences interpret generative-AI content in platform environments.

## 100-Word Abstract Version

We present a web-based human-in-the-loop analytics system for studying audience-side verification signals around generative-AI content. The platform combines scraping, annotation, adjudication, explainable weak labeling, multilingual/noise-aware screening, and integrated analytics readouts that augment human interpretation. We demonstrate the system on YouTube comments, using a validated evidence base of 1,100 resolved comments, including 42 skepticism labels, 4 proof-demand labels, and 68 normalization labels. In pooled ranked-cue analysis, response skepticism increased from 2.44% after non-skeptical top-ranked comments to 30.0% after skeptical top-ranked comments. The paper contributes both a reusable augmented-intelligence workflow and an empirical case showing how ranked comment cues structure discussion around generative-AI content.

## Three-Bullet Contribution Version

Use this when a CFP or submission system asks for concise contributions:

1. We introduce a web-based human-in-the-loop analytics system for collecting, coding, adjudicating, screening, and analyzing audience responses to generative-AI content.
2. We show how the system augments human judgment through explainable weak labeling, coding prioritization, and integrated analysis workspaces while preserving a clear boundary between validated evidence and exploratory automation.
3. We demonstrate the system on YouTube comments and recover a significant association between skeptical top-ranked comments and downstream skepticism.

## Recommended Paper Structure

Keep the conference paper compact:

1. Introduction
2. System and Workflow
3. Case Study Design
4. Results
5. Discussion and Limitations
6. Conclusion

## Section Plan

### 1. Introduction

Goal:
- establish the research problem
- explain why integrated workflows are needed
- preview the system and the empirical case

Suggested opening paragraph:

Generative-AI content is increasingly embedded in platform ecosystems, yet audience reactions remain difficult to study with methodological clarity. Users may challenge authenticity, request evidence, or normalize AI-mediated production, but these signals are hard to move from raw platform data into validated, reproducible analysis. Existing workflows often separate collection, coding, visualization, and inference into disconnected stages. This paper addresses that gap by presenting a web-based human-in-the-loop analytics system for studying audience-side verification signals around generative-AI content.

Suggested second paragraph:

The paper makes two contributions. First, it introduces a web-based research console that integrates scraping, annotation, adjudication, explainable weak labeling, multilingual and low-information text screening, interactive analytics views, and exportable hypothesis readouts. Second, it demonstrates the value of this augmented-intelligence system through a validated YouTube comment case study, showing that skepticism and normalization toward generative-AI content can be identified reliably and linked to ranked social cues in comment threads.

### 2. System and Workflow

Goal:
- show that the system is the primary contribution
- keep description concrete, not bloated

Suggested paragraph:

The platform was designed as a full human-in-the-loop research workflow rather than as a standalone annotation interface. It supports run management, structured annotation and adjudication, explainable rule-based screening, model-assisted prioritization for coding, multilingual and low-information comment filtering, reproducibility bundles, interactive analytics views, and integrated hypothesis workspaces. Automated signals are deliberately assistive rather than substitutive: they are used to guide screening and exploratory extension, while the main analytical layer is reserved for resolved human-coded labels.

Suggested short feature list:

- collection and run management
- manual coding and disagreement adjudication
- explainable weak-label screening
- model-assisted coding prioritization
- multilingual and noise-aware text filters
- integrated analytics and visualization views
- reproducibility and export workflow

### 3. Case Study Design

Goal:
- explain the YouTube case clearly
- make the evidence-freeze logic explicit

Suggested paragraph:

We demonstrate the system through a YouTube comment case study spanning multiple runs and niches. Although the broader corpus is larger, the main analytical dataset was intentionally narrower. Comments were included in the resolved-consensus evidence base only when they had been double-coded and either adjudicated or fully agreed upon across coders on three core labels: skepticism, proof-demand, and normalization. This procedure yielded a frozen evidence base of 1,100 resolved comments drawn from runs 11, 18, 20, 22, 23, and 24, with 148 disagreement cases fully resolved by the freeze point.

Suggested follow-up paragraph:

This design separates validated evidence from exploratory extension. The main claims of the paper rely only on the frozen resolved-consensus dataset, while automated analysis of uncoded comments is treated as a secondary exploratory layer rather than as equivalent evidence.

### 4. Results

Use this section in three parts.

#### 4.1 Descriptive Results

Suggested paragraph:

Within the frozen evidence base, 114 of 1,100 comments were positive on at least one core label. The dataset contained 42 skepticism comments, 4 proof-demand comments, and 68 normalization comments. Thus, skepticism and normalization were both substantially more common than explicit proof-demand. This indicates that audience-side verification around generative-AI content in the validated corpus appeared more often through evaluative skepticism and normalization than through explicit evidentiary requests.

#### 4.2 Ranked-Cue Results

Suggested paragraph:

The pooled ranked-cue analysis supports H1. In the resolved-consensus response frame, skepticism in downstream response comments rose from 2.44% after non-skeptical top-ranked comments to 30.0% after skeptical top-ranked comments. The corresponding mixed-effects model estimated a positive and statistically significant top-cue skepticism effect, with an odds ratio of approximately 8.62. This suggests that skeptical rank-1 cues are associated with substantially higher downstream skepticism in subsequent comments.

#### 4.3 Weak And Exploratory Results

Suggested paragraph:

Evidence for H2 was weak. Although a simple within-cue correlation was positive, the cue-magnitude interaction was not statistically significant in the pooled model. H3 should also be interpreted cautiously: some niche interaction terms were suggestive, but the overall moderation pattern was not stable enough, given the small number of skeptical-cue videos, to justify strong claims. These results indicate that the clearest empirical finding in the present study concerns H1.

### 5. Discussion and Limitations

Goal:
- interpret the main finding
- emphasize the methodological value of the system
- keep limitations honest and short

Suggested discussion paragraph:

The strongest takeaway is that skeptical audience reaction appears socially patterned rather than randomly distributed. When skepticism is already visible at the top of a comment thread, subsequent response comments are markedly more likely to express skepticism as well. While this does not by itself establish causal influence, it is consistent with a ranked-cue interpretation in which visible top comments help structure the tone of later audience discussion.

Suggested system-value paragraph:

The methodological value of the system lies in preserving the distinction between validated evidence and exploratory automation while still augmenting analyst judgment. In practice, this allowed the project to stabilize a defensible resolved-consensus dataset while using explainable screening, prioritization, and integrated analytics views to inspect the broader uncoded corpus. This separation is especially useful in generative-AI research settings where complete manual coding of all collected material is impractical.

Suggested limitations paragraph:

The study has several limitations. The frozen evidence base is a curated human-labeled subset rather than a population estimate of all scraped comments. Proof-demand remained rare, limiting the depth of inference for that construct. In addition, the number of videos with skeptical top-ranked cues remained small, which constrains the precision of higher-order interaction estimates. Accordingly, the present paper should be read as a validated conference-scale case with a strong methodological contribution and a credible empirical signal, rather than as a definitive platform-wide estimate.

### 6. Conclusion

Suggested paragraph:

This paper introduced a web-based human-in-the-loop analytics system for studying verification signals around generative-AI content and demonstrated its value through a validated YouTube comment case study. The resolved-consensus evidence base showed that skepticism and normalization are both meaningful audience responses, while proof-demand remains comparatively rare. Most importantly, skeptical top-ranked comments were associated with substantially higher downstream skepticism in pooled analysis. Together, these results show how explainable augmented-intelligence workflows can support rigorous research on generative-AI content ecosystems.

## Hypotheses

Use these exact formulations if you want consistency with the app:

1. H1: skeptical top-ranked cue
2. H2: stronger cue when top cue is liked more
3. H3: stronger in higher-stakes niches

Paper-ready versions:

- H1 predicts that response comments are more likely to express skepticism when the top-ranked comment in the thread is itself skeptical.
- H2 predicts that this association becomes stronger when the top-ranked skeptical cue has higher visible endorsement.
- H3 predicts that the association is stronger in niches where authenticity carries higher interpretive stakes.

## Key Numbers To Reuse

- resolved comments: `1,100`
- double-coded comments: `1,100`
- disagreement comments: `148`
- unresolved disagreements: `0`
- positive on at least one core label: `114`
- skepticism: `42`
- proof-demand: `4`
- normalization: `68`
- response comments in pooled ranked-cue frame: `583`
- videos in pooled response frame: `211`
- skeptical top-cue videos: `6`
- response skepticism after skeptical top cue: `30.0%`
- response skepticism after non-skeptical top cue: `2.44%`
- H1 delta: `+27.56` percentage points
- top-cue skepticism odds ratio: `~8.62`
- top-cue skepticism p-value: `~0.016`

## Recommended Figure/Table Set

For a conference paper, do not overload.

Use:

1. One system figure
   Show workflow from scraping -> coding -> adjudication -> analytics workspace -> resolved evidence -> exploratory extension.

2. One descriptive table
   Label prevalence overall and by run/niche.

3. One hypothesis table
   Main pooled model effects, with H1 highlighted.

4. Optional appendix/example table
   A few representative positive comments.

## What To Leave Out

To stay conference-sized, avoid:

- a long app walkthrough
- too many screenshots
- a huge appendix inside the main text
- too much emphasis on weak-label heuristics
- treating exploratory extension as main evidence

## How To Talk About Extension Analysis

Recommended wording:

Beyond the frozen validated evidence base, the system also supports exploratory automated screening of the remaining uncoded corpus. In this paper, that extension layer is used only to contextualize the broader corpus and to identify candidate examples for future follow-up, not to expand the main confirmatory evidence base.

## Good Final Claim

If you want one compact final claim to orient the paper, use this:

The paper shows that a human-in-the-loop analytics system can support both rigorous evidence production and broader exploratory mapping in studies of generative-AI content, and that skeptical ranked cues in YouTube comment threads are associated with materially higher downstream skepticism in a validated case-study setting.

## Submission Strategy

For conference submission, prioritize:

1. clarity over completeness
2. system contribution plus one clear empirical result
3. disciplined separation of validated evidence and exploratory extension
4. a short, sharp results section centered on H1

## Best Next Move

Turn this into a true draft by writing:

1. final conference abstract
2. 5-6 page main text using the section plan above
3. one system figure
4. one results table from the exported CSVs
