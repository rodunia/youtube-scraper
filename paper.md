# Paper Kit

This file is a working manuscript kit for turning the current project into a research paper. It is not a final paper draft. It is a structured set of reusable texts, claims, cautions, and section-ready paragraphs based on the frozen resolved-consensus evidence base.

All counts and reusable claims below are aligned to the frozen evidence bundle saved on `2026-03-31` in `data/evidence_base_freeze.json` and `data/exports/final_analysis_bundle_20260331T205147Z.json`.

## Core Positioning

The strongest framing for this project is:

- Primary contribution: a web-based human-in-the-loop analytics system for scraping, coding, adjudicating, and analyzing verification signals around generative-AI content.
- Method angle: augmented intelligence through explainable screening, coding support, and integrated analytics workspaces.
- Empirical demonstration: applying that system to YouTube comments reveals measurable patterns of skepticism, normalization, and ranked-cue effects.

This is stronger than framing the project only as a YouTube comment study. The system is the methodological contribution; the YouTube findings show that the system produces meaningful research results.

## Session-Oriented Framing

For the target session, the paper aligns most clearly with:

- Generative Artificial Intelligence
- GenAI Web-based Systems
- Augmented Intelligence
- eXplainable Artificial Intelligence
- Data Analytics
- Data Science and Visualization Systems
- Human-centered Computing

That means the draft should consistently emphasize the system as:

- a smart web-based research console
- an augmented-intelligence workflow rather than a fully automated classifier
- an explainable analytics environment with human-readable signals and auditability
- a real-world implementation that combines tool design with empirical proof-of-use

## Working Title Options

1. A Human-in-the-Loop Analytics System for Studying Verification Signals Around Generative-AI Content: Evidence from YouTube Comments
2. Tracking Skepticism and Normalization Around Generative-AI Content with a Human-in-the-Loop Research Console
3. From Annotation to Hypothesis Testing: A Web-Based Research System for Analyzing Audience Responses to Generative-AI Content
4. Ranked Cues and Verification Signals in YouTube Comments: A Human-in-the-Loop System and Empirical Pilot

## One-Sentence Summary

We built a web-based human-in-the-loop analytics system for collecting, coding, adjudicating, and analyzing audience responses to generative-AI content, and used it to identify robust patterns of skepticism and normalization in YouTube comments.

## Short Abstract Draft

This paper presents a web-based human-in-the-loop analytics system for studying audience-side verification signals around generative-AI content. The system integrates scraping, annotation, adjudication, explainable weak labeling, model-assisted prioritization, multilingual and noise-aware text screening, interactive analytics views, and exportable hypothesis readouts within a single workflow designed to augment rather than replace human judgment. As an empirical demonstration, we apply the system to YouTube comments collected across multiple runs and niches. The main validated evidence base consists of 1,100 resolved comments that were double-coded and either adjudicated or fully agreed upon across coders. Within this evidence base, 114 comments were positive on at least one core label, including 42 skepticism comments, 4 proof-demand comments, and 68 normalization comments. A pooled ranked-cue analysis suggests that skeptical top-ranked comments are associated with substantially higher downstream skepticism in response comments, with response skepticism rising from 2.44% after non-skeptical top cues to 30.0% after skeptical top cues. The corresponding cue effect is statistically significant in the pooled model (OR approximately 8.62, `p ≈ 0.016`). In contrast, evidence for cue-magnitude moderation remains weak, and niche moderation should be interpreted cautiously. The paper contributes both a reusable augmented-intelligence analytics workflow and a validated empirical case showing how human-in-the-loop systems can support research on generative-AI content ecosystems.

## Extended Abstract Draft

The rapid diffusion of generative-AI content across online platforms has created a need for research tools that can capture how audiences interpret, contest, and normalize such content. Existing studies often separate data collection, coding, adjudication, visualization, and analysis into disconnected workflows, making it difficult to preserve reproducibility, maintain codebook quality, and clearly distinguish validated evidence from exploratory extension. To address this gap, this paper presents a web-based human-in-the-loop analytics system for studying verification signals around generative-AI content.

The system combines several components within a unified workflow: collection and run management, structured annotation and adjudication, explainable weak labeling, model-assisted coding prioritization, multilingual and low-information text screening, reproducibility bundles, interactive analytics views, and integrated hypothesis readouts. The platform is designed not simply as an annotation interface, but as a full research console that supports both validated evidence production and carefully separated exploratory extension.

We demonstrate the system through a case study of YouTube comments collected across multiple niches and runs. The frozen main evidence base comprises 1,100 resolved comments drawn from runs 11, 18, 20, 22, 23, and 24. Comments were included in the main analytical dataset only when they had been double-coded and either adjudicated or fully agreed upon across coders on the three core labels: skepticism, proof-demand, and normalization. Within this resolved set, 114 comments were positive on at least one core label, including 42 skepticism comments, 4 proof-demand comments, and 68 normalization comments.

Using the ranked-cue framework implemented in the system, we then evaluate whether skeptical top-ranked comments are associated with more skeptical downstream responses. In the pooled resolved-consensus analysis, the response frame contains 583 comments across 211 videos. Response skepticism rises from 2.44% after non-skeptical top cues to 30.0% after skeptical top cues, corresponding to a positive cue effect of 27.56 percentage points. In the pooled mixed-effects model, the top-cue skepticism term remains statistically significant, whereas the cue-magnitude interaction remains weak and non-significant. These findings suggest that skepticism and normalization are meaningfully present in the validated corpus, while proof-demand remains comparatively rare.

The contribution of the paper is therefore twofold. Methodologically, it introduces a human-in-the-loop research system tailored to the study of generative-AI content ecosystems. Empirically, it demonstrates that the system can recover interpretable and non-trivial patterns of audience skepticism and normalization in YouTube comments. The paper concludes by arguing that validated human-coded evidence and exploratory automated extension should be treated as complementary but analytically distinct layers in future studies of generative-AI reception.

## Contribution Statement

Use some version of the following:

This paper makes two contributions. First, it introduces a human-in-the-loop analytics system that integrates collection, annotation, adjudication, explainable weak labeling, multilingual/noise-aware screening, integrated analytics views, and reproducible hypothesis readouts for the study of generative-AI content ecosystems. Second, it demonstrates the value of this system through a validated empirical case study of YouTube comments, showing that skepticism and normalization toward generative-AI content can be identified reliably and linked to ranked social cues in audience discussion.

## Problem Framing

Possible introduction paragraph:

Generative-AI content is increasingly embedded in everyday platform ecosystems, yet audiences do not respond to it uniformly. Some users challenge authenticity, some request verification, and others normalize or defend AI-mediated production. Studying these reactions requires more than large-scale data collection alone: it requires a workflow that can move from raw platform data to validated labels, transparent screening, interpretable analytics, and reproducible hypothesis testing. This paper addresses that need by developing and demonstrating a human-in-the-loop analytics system designed for the analysis of audience-side verification signals around generative-AI content.

## Research Questions And Hypotheses

### Ready-to-use RQ text

The study asks whether and how audience-side verification signals appear in ranked YouTube comment spaces surrounding generative-AI content. More specifically, it examines whether skeptical top-ranked comments are associated with higher downstream skepticism, whether the strength of such an effect depends on the popularity of the top-ranked cue, and whether these dynamics vary across niches with different perceived authenticity stakes.

### Current hypothesis formulations

1. H1: Skeptical top-ranked cue.
   More downstream skepticism is expected after skeptical rank-1 comments.

2. H2: Stronger cue when top cue is liked more.
   The effect of a skeptical top-ranked comment is expected to strengthen when that top cue has higher social endorsement.

3. H3: Stronger in higher-stakes niches.
   The association between skeptical top-ranked cues and downstream skepticism is expected to be stronger in niches with higher authenticity stakes.

### Paper-ready wording

H1 predicts that response comments are more likely to express skepticism when the top-ranked comment in the thread is itself skeptical. H2 predicts that this association is stronger when the top-ranked skeptical cue has higher visible endorsement, operationalized through like-based cue magnitude. H3 predicts that the association is stronger in niches where authenticity carries higher interpretive stakes.

## System Description

### Short version

The system is a web-based research console that supports the full workflow from raw collection to validated analysis. It includes run management, annotation and adjudication interfaces, explainable weak-label screening, model-assisted prioritization for coding, multilingual and low-information text filters, codebook and reproducibility controls, integrated analytics views, and hypothesis readouts.

### Longer version

The platform was designed as a human-in-the-loop research system rather than a standalone annotation tool. It supports batch and profile-based collection management, manual coding of comments against a structured codebook, disagreement detection, adjudication workflows, explainable automation traces, interactive analytics workspaces, and exportable analysis bundles. Automated support in the system is deliberately assistive rather than substitutive: rule-based signals, lexical features, and prioritization scores are used to guide screening and exploration, while the main evidence base is reserved for resolved human-coded labels.

### System contribution paragraph

Methodologically, the system contributes a reproducible augmented-intelligence workflow for studying generative-AI reception in platform environments. It allows researchers to separate validated evidence from exploratory extension, preserve codebook decisions, inspect disagreement structure, trace automated suggestions back to explicit signal components, and move between annotation and analytics views within one environment. This distinction between validated human-coded evidence and broader machine-assisted exploration is central to the analytical design of the project.

## Data And Evidence Base

### Short methods paragraph

The broader corpus was collected through repeated YouTube scraping runs across multiple niches. The main analytical dataset, however, was intentionally narrower: only comments that had been double-coded and either adjudicated or fully agreed upon across coders were retained in the resolved-consensus evidence base. This procedure produced a frozen main dataset of 1,100 resolved comments drawn from runs 11, 18, 20, 22, 23, and 24.

### Evidence freeze paragraph

To establish a stable analytical dataset, we froze the main evidence base after completion of double-coding and adjudication. The final evidence base comprised 1,100 resolved YouTube comments drawn from runs 11, 18, 20, 22, 23, and 24. Comments were retained in the core dataset only when they had been double-coded and either adjudicated or fully agreed upon across coders on the three core labels: skepticism, proof-demand, and normalization. The freeze includes 148 disagreement cases and 0 unresolved disagreements. This freezing step separated the confirmatory evidence base from later exploratory analyses and ensured that subsequent results were not affected by ongoing coding decisions.

### Annotation paragraph

The coding framework focused on three core labels: skepticism, proof-demand, and normalization. In addition, coders could use auxiliary tags and an `Other` flag for analytically relevant but uncaptured cases. Disagreements were adjudicated within the research console, and the final main analysis relied on a resolved-consensus label source that prioritized adjudicated decisions where available and otherwise retained agreed double-coded labels.

### Human vs automated paragraph

The platform also supports automated screening through rules, lexical features, and priority heuristics, but these signals are not treated as equivalent to validated labels. Instead, they serve as exploratory and supportive layers around the core evidence base and are exposed through explainable analytics views rather than opaque end-to-end automation. This distinction is critical to the design of the present study and to the interpretation of the reported findings.

## Key Numbers To Cite

### Frozen evidence base

- Resolved comments: `1,100`
- Double-coded comments: `1,100`
- Disagreement comments: `148`
- Positive on at least one core label: `114`
- Skepticism: `42`
- Proof-demand: `4`
- Normalization: `68`
- Unresolved disagreements at freeze: `0`

### Useful percentages

- Any core positive: `114 / 1100 = 10.4%`
- Skepticism: `42 / 1100 = 3.8%`
- Proof-demand: `4 / 1100 = 0.4%`
- Normalization: `68 / 1100 = 6.2%`

### Ranked-cue pooled model

- Response comments in pooled resolved-consensus analysis: `583`
- Videos in pooled response frame: `211`
- Videos with skeptical top-ranked cue: `6`
- Response skepticism after skeptical top cue: `30.0%`
- Response skepticism after non-skeptical top cue: `2.44%`
- H1 delta: `+27.56` percentage points
- H1 model effect: odds ratio approximately `8.62`, `p ≈ 0.016`
- H2 interaction: not significant, `p ≈ 0.854`

## Results Text

### Descriptive findings paragraph

Within the frozen resolved-consensus evidence base, 114 of 1,100 comments were positive on at least one core label. Normalization was the most common core signal, followed by skepticism, while proof-demand remained comparatively rare. This suggests that audience responses to generative-AI content in the validated dataset more often took the form of either skeptical pushback or normalization than explicit requests for proof.

### More explicit descriptive version

The resolved-consensus evidence base contained 42 skepticism comments, 4 proof-demand comments, and 68 normalization comments. In proportional terms, 10.4% of resolved comments were positive on at least one core label. The most notable asymmetry in the coding results is the scarcity of proof-demand relative to both skepticism and normalization, indicating that audience reaction in this corpus was more often evaluative than explicitly evidentiary.

### Run/niche interpretation paragraph

The distribution of positive labels was not uniform across runs and niches. Signal concentration was strongest in runs 22 and 23, particularly in Lifestyle and Tech, whereas older pilot runs and much of run 24 were comparatively sparse. This pattern suggests that meaningful verification-related response is present but unevenly distributed, which reinforces the importance of separating validated evidence from simple corpus volume.

### H1 results paragraph

The pooled ranked-cue analysis provides support for H1. In the resolved-consensus response frame, downstream skepticism rose from 2.44% after non-skeptical top-ranked comments to 30.0% after skeptical top-ranked comments. The corresponding mixed-effects estimate for the top-cue skepticism term was positive and statistically significant, with an odds ratio of approximately 8.62. Substantively, this suggests that skeptical rank-1 cues are associated with substantially higher levels of skepticism in subsequent response comments.

### H2 results paragraph

Evidence for H2 was weak. Although the simple within-cue correlation between cue magnitude and response skepticism was positive, the interaction term between top-cue skepticism and top-comment like count was not statistically significant in the pooled model. Given the small number of skeptical top-cue videos in the final response frame, this result should be interpreted as inconclusive rather than as strong evidence against cue-magnitude moderation.

### H3 results paragraph

Evidence for H3 should be treated cautiously. Some niche interaction terms were suggestive, but the moderation pattern was not sufficiently stable, given the small number of skeptical-cue videos, to justify strong claims about niche-based amplification of the ranked-cue effect. Accordingly, niche differences are best interpreted as exploratory rather than confirmatory in the present study.

### Short results summary paragraph

Taken together, the final validated analysis supports the claim that skepticism and normalization are both meaningful audience responses to generative-AI content, and that skeptical top-ranked comments are associated with a marked increase in downstream skepticism. By contrast, proof-demand remains sparse, and stronger claims about cue magnitude or niche moderation require further evidence.

## Discussion Text

### Interpretation paragraph

The results suggest that audience-side verification around generative-AI content is not limited to explicit requests for evidence. Instead, it appears more commonly through skeptical interpretation and through normalization that downplays the relevance of AI mediation. This matters conceptually because it indicates that audience response may operate less as formal verification and more as rapid social positioning around authenticity, credibility, and acceptable use.

### System significance paragraph

The value of the system lies not only in enabling coding efficiency, but also in preserving the analytical distinction between validated findings and exploratory extension. In practice, this distinction allowed the project to stabilize a defensible main evidence base while still using explainable automation and integrated analytics views to survey the wider uncoded corpus. This is a useful design principle for research on generative-AI ecosystems, where full manual coding of all available data is often impractical.

### Stronger interpretation paragraph

The strongest empirical takeaway from the present study is that skeptical audience reaction appears socially patterned rather than randomly distributed. When skepticism is already visible in the highest-ranked comment position, downstream response comments are markedly more likely to express skepticism as well. While this does not by itself establish causal influence, it is consistent with a ranked-cue interpretation in which visible top comments help structure the tone of subsequent audience discussion.

## Limitations Text

### Core limitations paragraph

Several limitations should be acknowledged. First, the main evidence base is a curated human-labeled subset rather than a population-representative sample of all scraped comments. Second, proof-demand remained rare even in the resolved dataset, limiting the inferential depth of that construct. Third, the number of videos with skeptical top-ranked cues in the pooled resolved-consensus analysis remained small, which constrains the precision of higher-order interaction estimates. Fourth, broader automatic screening of uncoded comments is valuable for exploratory extension but should not be treated as equivalent to the validated human-coded evidence base.

### Short limitations version

The study should therefore be read as a validated case study with a strong methodological contribution and a credible empirical signal, rather than as a final population estimate of audience response to generative-AI content on YouTube.

## Separation Between Main Analysis And Extension

Use wording like this:

The analysis proceeded in two layers. The first was a validated main analysis based exclusively on the frozen resolved-consensus evidence base. The second was an exploratory extension layer based on automated screening of the remaining uncoded comments. This separation was intentional: the main claims of the paper rely only on resolved human-coded evidence, while the extension layer is used to map broader patterns, identify candidate examples, and motivate future work.

## Extension Analysis Text

### Methods paragraph for extension

After freezing the validated evidence base, the remaining uncoded comments were analyzed through the system’s exploratory extension workflow. This layer applies rule-based signals, AI-context detection, multilingual and low-information filters, and lexical screening to identify potentially relevant uncoded comments. These outputs are not treated as substitutes for human labels; rather, they serve as an exploratory map of the wider corpus and as a source of candidate comments for appendix examples or future targeted validation.

### Results paragraph for extension

The exploratory extension layer was used to survey the uncoded remainder of the scraped corpus and to identify candidate comments that resemble the validated patterns recovered in the main evidence base. This extension analysis does not change the main findings, but it provides contextual evidence about where similar signals may persist beyond the frozen labeled subset and helps identify promising material for future follow-up coding or qualitative interpretation.

## Why Not Analyze Everything As Main Evidence

Use some version of this:

Although the broader corpus is much larger than the frozen evidence base, the present paper does not merge automatically screened comments into the main confirmatory analysis. Doing so would blur the distinction between validated human-coded evidence and exploratory machine-assisted inference. The analytical strategy instead prioritizes methodological clarity: the main findings rely on resolved human labels, while broader automated analysis is retained as a secondary exploratory layer.

## Why Not Scrape More Videos Yet

Use some version of this:

At the current stage, additional scraping is not the highest-priority next step. The existing corpus is already larger than the validated coding base, meaning that the main bottleneck is interpretation rather than raw collection. Further scraping would be most useful in a subsequent extension wave designed to test new niches, time periods, or platforms, rather than as part of the frozen main evidence base reported in this paper.

## Suggested Paper Structure

1. Introduction
2. Related Work
3. System Design
4. Data Collection And Annotation Workflow
5. Frozen Evidence Base
6. Results
7. Exploratory Extension
8. Discussion
9. Limitations
10. Conclusion

## Section-by-Section Purpose

### Introduction

State the problem: audience responses to generative-AI content are important, but hard to study without an integrated workflow from collection to validated analysis.

### Related Work

Position the paper at the intersection of:

- generative-AI content studies
- human-in-the-loop annotation systems
- augmented intelligence and explainable AI
- social cue / ranked-comment effects
- platform analytics, visualization, and research tooling

### System Design

Describe the app as the main contribution:

- scraping and run management
- annotation and adjudication
- explainable automation
- integrated analytics and visualization
- multilingual/noise-aware screening
- reproducibility bundles
- evidence freeze and export workflow

### Data Collection And Annotation Workflow

Explain how the broader corpus was collected and how the main labeled subset was created.

### Frozen Evidence Base

This is where you justify the `1,100` as the primary analytical dataset.

### Results

Use:

- descriptive prevalence
- run/niche variation
- pooled ranked-cue model
- H1, H2, H3 readout

### Exploratory Extension

Describe the automatic analysis of uncoded comments as secondary and non-confirmatory.

### Discussion

Interpret skepticism, normalization, and the ranked-cue effect in substantive terms.

### Limitations

Be explicit about sampling, sparse proof-demand, and small skeptical-cue video counts.

### Conclusion

Reinforce the dual contribution: system plus validated empirical case.

## Mapping Exports To Paper Sections

- `data/evidence_base_freeze.json`
  Role: audit trail for the frozen main dataset

- `data/exports/final_prevalence_by_run_niche_*.csv`
  Role: descriptive results table

- `data/exports/final_model_effects_*.csv`
  Role: main hypothesis-test table

- `data/exports/final_icc_*.csv`
  Role: mixed-model / variance justification

- `data/exports/appendix_positive_comments_*.csv`
  Role: appendix examples and qualitative illustration

- `data/exports/appendix_extension_candidates_*.csv`
  Role: exploratory extension appendix

- `data/exports/final_analysis_bundle_*.json`
  Role: full reproducibility package for the paper

## Phrases Worth Reusing

- frozen resolved-consensus evidence base
- validated human-coded layer
- exploratory automated extension
- audience-side verification signals
- ranked-cue framework
- human-in-the-loop analytics system
- methodological separation between confirmatory evidence and exploratory screening
- skepticism and normalization as more prevalent than explicit proof-demand

## Strong One-Paragraph Conclusion

This paper introduced a human-in-the-loop analytics system for studying verification signals around generative-AI content and demonstrated its value through a validated YouTube comment case study. The frozen resolved-consensus evidence base showed that skepticism and normalization are both meaningful audience responses, while proof-demand remains comparatively rare. Most importantly, skeptical top-ranked comments were associated with substantially higher downstream skepticism in pooled analysis. These results support the value of combining validated human-coded evidence with clearly separated exploratory automation in the study of generative-AI platform ecosystems.

## What To Do Next

1. Use the frozen `1,100` as the only basis for your main claims.
2. Use the `final_prevalence_by_run_niche` and `final_model_effects` exports to draft the Results section.
3. Use the positive-comment appendix to select illustrative examples.
4. Mention the extension analysis, but keep it clearly separate from the validated main findings.
5. Treat any future scraping as a follow-up wave, not as part of the current frozen evidence base.
