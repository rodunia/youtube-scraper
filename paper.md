# Paper Kit

This file is the long-form manuscript kit for turning the project into a submission-ready paper. It is not a final draft; it is a structured set of claims, cautions, reusable paragraphs, and section-ready materials aligned to the frozen resolved-consensus evidence base.

All reusable numbers below are aligned to the frozen bundle saved on `2026-03-31` in `data/evidence_base_freeze.json` and `data/exports/final_analysis_bundle_20260331T205147Z.json`.

## Core Positioning

The strongest version of this paper is:

- primary contribution: a web-based human-in-the-loop analytics system
- novelty claim: an explicit validated-evidence / exploratory-extension split inside one explainable, reproducible research environment
- empirical role: a bounded YouTube validation case showing one clear ranked-cue effect

This is stronger than framing the project as a broad empirical paper about platform behavior. The system is the main contribution; the YouTube case demonstrates that the workflow can produce defensible evidence and recover one interpretable signal.

## One-Sentence Summary

We built a human-in-the-loop analytics system that separates frozen validated evidence from exploratory automation inside one explainable workflow, and used a YouTube case to show one clear association between skeptical top-ranked comments and downstream skepticism.

## Working Title Options

1. A Human-in-the-Loop Analytics System for Studying Verification Signals Around Generative-AI Content
2. Validated Evidence and Exploratory Extension in a Human-in-the-Loop Analytics System for Generative-AI Content Research
3. An Explainable Research Console for Studying Verification Signals Around Generative-AI Content
4. From Annotation to Ranked-Cue Analysis: A Human-in-the-Loop System for Generative-AI Content Research

## Short Abstract Draft

This paper presents a web-based human-in-the-loop analytics system for studying audience-side verification signals around generative-AI content. The core contribution is an explainable and reproducible workflow that preserves a strict boundary between validated human-coded evidence and broader exploratory automation. The system integrates collection management, annotation, disagreement detection, adjudication, explainable screening, coding prioritization, and exportable analytics readouts inside one environment designed to augment rather than replace human judgment. We validate the workflow through a YouTube comment case using a frozen evidence base of 1,100 resolved double-coded comments from runs 11, 18, 20, 22, 23, and 24. Within this validated layer, 114 comments were positive on at least one core label, including 42 skepticism comments, 4 proof-demand comments, and 68 normalization comments. The main empirical result is a pooled ranked-cue effect: downstream skepticism rises from 2.44% after non-skeptical top-ranked comments to 30.0% after skeptical top-ranked comments, with an odds ratio of approximately 8.62 (`p ≈ 0.016`). Cue-magnitude moderation is not supported, and niche heterogeneity is treated only as exploratory. The paper therefore contributes both an augmented-intelligence research system and one validated empirical demonstration of its analytical value.

## Extended Abstract Draft

Generative-AI content is increasingly embedded in online platform ecosystems, but audience responses remain methodologically difficult to study. Researchers must move from raw platform data to validated labels, disagreement handling, transparent screening, and reproducible analysis, yet these stages are often distributed across disconnected tools. This paper addresses that workflow problem by introducing a web-based human-in-the-loop analytics system for studying verification signals around generative-AI content.

The system’s main novelty is not generic integration alone. Rather, it is the explicit separation of a validated evidence layer from a broader exploratory extension layer inside one explainable, reproducible environment. The platform combines collection management, annotation, disagreement detection, adjudication, explainable rule-based screening, coding prioritization, multilingual and low-information text diagnostics, integrated analytics views, and exportable bundles. Automated signals remain assistive rather than substitutive: they help analysts prioritize, screen, and map the broader corpus, but the paper’s confirmatory claims rely only on resolved human-coded evidence.

We validate the workflow through a YouTube comment case spanning runs 11, 18, 20, 22, 23, and 24. The broader database currently contains 27 runs, 205 channels, 3,463 videos, and 33,467 comments, but the main analytical dataset is intentionally narrower. The frozen evidence base contains 1,100 resolved double-coded comments. A comment entered this layer only when it had received two independent coding passes and was either fully agreed upon or explicitly adjudicated on the three core labels: skepticism, proof-demand, and normalization. At freeze, the validated layer included 148 disagreement cases and 0 unresolved disagreements.

Within the frozen evidence base, 114 comments were positive on at least one core label, including 42 skepticism comments, 4 proof-demand comments, and 68 normalization comments. Using the ranked-cue workflow implemented in the system, we then evaluated whether skeptical top-ranked comments are associated with more skeptical downstream responses. In the pooled resolved-consensus response frame, downstream skepticism rises from 2.44% after non-skeptical top comments to 30.0% after skeptical top comments. The corresponding mixed-effects estimate is statistically significant, with an odds ratio of approximately 8.62 (`p ≈ 0.016`). By contrast, cue-magnitude moderation is not supported, and niche heterogeneity remains exploratory because the number of skeptical-cue videos is small.

The paper is therefore strongest as a system-and-methods contribution with one bounded empirical validation case. Its main argument is that rigorous research on generative-AI content benefits from an evidence-preserving workflow in which validated human-coded inference and broader exploratory automation are intentionally connected but never conflated.

## Contribution Statement

Use some version of the following:

This paper makes two contributions. First, it introduces a human-in-the-loop analytics system that supports collection, coding, adjudication, explainable screening, prioritization, and integrated analysis while preserving a strict distinction between validated evidence and exploratory extension. Second, it validates that workflow through a YouTube comment case and recovers one clear ranked-cue association between skeptical top-ranked comments and downstream skepticism.

## Problem Framing

Possible opening paragraph:

Generative-AI content is now deeply embedded in platform ecosystems, but audience-side verification signals are difficult to study without a workflow that moves cleanly from raw collection to validated evidence. Users may challenge authenticity, request proof, or normalize AI-mediated production, yet these signals are sparse, noisy, and easily conflated with broader exploratory automation. This paper addresses that methodological problem by presenting a human-in-the-loop analytics system designed to create a defensible validated evidence layer while retaining a separate exploratory view of the wider corpus.

## Research Questions And Claim Structure

### Better framing for the paper

The paper should be organized around one primary empirical claim and two secondary checks:

1. H1 as the main supported claim.
   Skeptical top-ranked comments are associated with substantially higher downstream skepticism.

2. H2 as a secondary null moderation check.
   Does visible cue endorsement strengthen the H1 association?
   Current answer: not supported in the pooled data.

3. H3 as an exploratory heterogeneity scan.
   Does the H1 association vary across niches?
   Current answer: exploratory and inconclusive.

### Paper-ready wording

H1 predicts that downstream response comments are more likely to express skepticism when the top-ranked comment in the thread is itself skeptical. H2 tests whether that association becomes stronger when the top-ranked cue has higher visible endorsement. H3 probes whether the H1 association varies across niches with different perceived authenticity stakes. In the present paper, H1 is the only supported headline finding; H2 is not supported, and H3 remains exploratory.

## System Description

### Short version

The system is a web-based research console that supports the full workflow from raw collection to validated analysis. It includes run management, annotation and adjudication interfaces, explainable weak-label screening, coding prioritization, multilingual and low-information text diagnostics, evidence freezing, reproducibility bundles, and integrated analytics views.

### Longer version

The platform was designed as a human-in-the-loop research environment rather than as a standalone annotation tool. It supports collection management, manual coding of comments against a structured codebook, disagreement detection, adjudication workflows, explainable automation traces, integrated analytics workspaces, and exportable analysis bundles. Automated support is deliberately assistive rather than substitutive: rule-based signals, lexical features, and priority heuristics are used to guide screening and exploration, while the main evidence base is reserved for resolved human-coded labels.

### System contribution paragraph

The methodological contribution is not merely that several steps were put into one application. The main novelty is the explicit validated-evidence / exploratory-extension split embedded inside one explainable workflow. The system allows researchers to preserve codebook decisions, inspect disagreements, adjudicate contested cases, freeze a stable evidence layer, and then continue broader exploratory mapping without contaminating the main confirmatory dataset.

## Validation Workflow

### Procedural trust paragraph

The codebook centered three substantive labels: skepticism, proof-demand, and normalization. Skepticism captured comments that challenged authenticity or explicitly called content fake or misleading. Proof-demand captured requests for evidence, demonstration, or proof of disclosure. Normalization captured comments that defended, accepted, or downplayed AI involvement as ordinary or acceptable. Coders worked inside the research console with comment text, thread context, and visible automation hints, but those hints were assistive rather than binding. A comment entered the main evidence layer only after two independent coding passes. Disagreements were flagged automatically and resolved through adjudication in the same environment. A comment counted as resolved if it was either fully agreed upon or explicitly adjudicated on the core labels.

### Evidence freeze paragraph

To establish a stable confirmatory dataset, we froze the main evidence base on `2026-03-31`. The freeze covered runs 11, 18, 20, 22, 23, and 24. At that point, the validated layer contained 1,100 resolved double-coded comments, 148 disagreement cases, and 0 unresolved disagreements. This step locked the confirmatory layer before subsequent exploratory extension analysis and made later analytics reproducible against a fixed evidence snapshot.

### Label-definition table

| Label | Operational definition | Used in main analysis |
| --- | --- | --- |
| Skepticism | Challenges authenticity, calls content fake, or questions truthfulness | Yes |
| Proof-demand | Requests evidence, proof, or verifiable disclosure | Yes |
| Normalization | Accepts, defends, or downplays AI use as normal | Yes |
| Extra tags / Other | Auxiliary coding for contextual or edge-case content | No, descriptive only |

### Agreement/adjudication paragraph

The validation layer is procedurally auditable rather than rhetorically “validated.” All 1,100 comments in the frozen evidence base were double-coded. Of those, 148 cases involved disagreement and were brought into the resolved layer through adjudication; 0 remained unresolved at freeze. At the label level, raw disagreement before adjudication was concentrated in normalization (`55` comments) and skepticism (`42` comments), while proof-demand disagreement remained rare (`7` comments), which is consistent with the scarcity of proof-demand in the corpus.

## Data And Evidence Base

### Short methods paragraph

The broader corpus was collected through repeated YouTube scraping runs across multiple niches. The current database contains 27 runs, 205 channels, 3,463 videos, and 33,467 comments. The paper’s confirmatory analysis is intentionally narrower: only comments in the frozen resolved-consensus evidence layer are used for the main claims.

### Human vs automated paragraph

The platform also supports automated screening through rules, lexical features, and priority heuristics, but these signals are not treated as equivalent to validated labels. Instead, they serve as assistive and exploratory layers around the core evidence base. This distinction is central to the design of the paper and should be repeated wherever the results are interpreted.

## Key Numbers To Cite

### Frozen evidence base

- resolved comments: `1,100`
- double-coded comments: `1,100`
- disagreement comments: `148`
- unresolved disagreements: `0`
- any core positive: `114`
- skepticism: `42`
- proof-demand: `4`
- normalization: `68`

### Useful percentages

- any core positive: `114 / 1100 = 10.4%`
- skepticism: `42 / 1100 = 3.8%`
- proof-demand: `4 / 1100 = 0.4%`
- normalization: `68 / 1100 = 6.2%`
- disagreement share in double-coded set: `148 / 1100 = 13.5%`

### Ranked-cue pooled model

- response comments in pooled resolved-consensus analysis: `583`
- videos in pooled response frame: `211`
- videos with skeptical top-ranked cue: `6`
- response skepticism after skeptical top cue: `30.0%`
- response skepticism after non-skeptical top cue: `2.44%`
- H1 delta: `+27.56` percentage points
- H1 model effect: odds ratio approximately `8.62`, `p ≈ 0.016`
- H2 interaction: not significant, `p ≈ 0.854`

### Broader corpus / system context

- total runs currently in DB: `27`
- channels: `205`
- videos: `3,463`
- comments: `33,467`
- total annotations currently in DB: `3,163`
- labeled comments across frozen runs: `2,043`

## Results Text

### Descriptive findings paragraph

Within the frozen resolved-consensus evidence base, 114 of 1,100 comments were positive on at least one core label. The validated dataset contained 42 skepticism comments, 4 proof-demand comments, and 68 normalization comments. This means the main descriptive contribution of the labeled layer is not broad prevalence estimation, but a clear demonstration of which verification-related signals were recoverable with robust coding discipline.

### More explicit descriptive version

The most notable asymmetry in the coding results is the scarcity of proof-demand relative to both skepticism and normalization. In other words, audience-side verification in this corpus appeared more often as evaluative skepticism or normalization than as explicit evidentiary requests. That descriptive imbalance is useful context, but it is too thin to support a major proof-demand result.

### H1 results paragraph

The pooled ranked-cue analysis supports H1 and should be treated as the paper’s headline empirical result. In the resolved-consensus response frame, downstream skepticism rose from 2.44% after non-skeptical top-ranked comments to 30.0% after skeptical top-ranked comments. The corresponding mixed-effects estimate for the top-cue skepticism term was positive and statistically significant, with an odds ratio of approximately 8.62. In the present paper, this result matters primarily because it shows that the validated workflow can recover a non-trivial and interpretable ranked-cue pattern.

### H2 results paragraph

H2 should be presented only as a secondary moderation check and reported honestly as not supported in the current data. Although simple descriptive association between cue endorsement and downstream skepticism was positive, the pooled interaction between top-cue skepticism and top-comment like count was not statistically significant. Given the small number of skeptical top-cue videos, this result is better described as a non-supported secondary test than as a major theoretical takeaway.

### H3 results paragraph

H3 should be treated as exploratory rather than confirmatory. Some niche terms were suggestive, but the moderation pattern was not stable enough to justify strong claims about niche-based amplification of the ranked-cue effect. In the current paper, niche variation is best used as exploratory context and as motivation for future targeted data collection rather than as a headline result.

### Short results summary paragraph

Taken together, the validated analysis supports one main association claim: skeptical top-ranked comments are associated with markedly higher downstream skepticism. Proof-demand remains sparse, cue-magnitude moderation is not supported, and niche heterogeneity remains exploratory.

## Discussion Text

### System significance paragraph

The value of the system lies not only in supporting coding efficiency, but in making the epistemic boundary between validated evidence and exploratory extension operational. In practice, this design allowed the project to stabilize a defensible confirmatory layer while still using explainable automation to inspect the wider uncoded corpus. That separation is particularly useful in research on generative-AI content, where the total amount of material typically exceeds what can be coded manually with high confidence.

### Stronger interpretation paragraph

The strongest empirical takeaway is that skeptical audience reaction appears socially patterned rather than randomly distributed. When skepticism is already visible in the highest-ranked comment position, downstream response comments are much more likely to express skepticism as well. The paper does not claim broad causal identification or platform-wide generalization; instead, it uses this result as a bounded validation case for the analytical workflow.

### Methodological implication paragraph

More broadly, the paper argues for a methodological principle: automation should help researchers surface, prioritize, and inspect candidate material, but it should not silently expand the confirmatory evidence base. The system is strongest where it makes that distinction visible and enforceable.

## Ethics And Reproducibility

Use wording like this:

The study relies on public platform comments, but the workflow is designed to minimize unnecessary exposure of personal information. Analytical tables use internal database identifiers and hashed commenter fields rather than public-facing account names, and the paper should rely primarily on aggregate statistics plus carefully selected excerpts where analytically necessary. Reproducibility is supported through frozen evidence snapshots, exportable analysis bundles, and explicit separation between the validated evidence layer and the exploratory extension layer.

## Limitations Text

### Core limitations paragraph

Several limitations should be acknowledged. First, the main evidence base is a curated human-labeled subset rather than a population-representative sample of all scraped comments. Second, proof-demand remained rare even in the resolved dataset, limiting the inferential depth of that construct. Third, only six videos in the pooled resolved-consensus response frame contained skeptical top-ranked cues, which constrains the precision of higher-order interaction estimates. Fourth, broader automated screening of uncoded comments is analytically useful but should not be treated as equivalent to the validated human-coded evidence base.

### Short limitations version

The study should therefore be read as a validated case study with a strong methodological contribution and one credible empirical signal, rather than as a final platform-wide estimate of audience behavior.

## Separation Between Main Analysis And Extension

Use wording like this:

The analysis proceeded in two layers. The first was a validated main analysis based exclusively on the frozen resolved-consensus evidence base. The second was an exploratory extension layer based on automated screening of the remaining corpus. This separation was intentional: the main claims of the paper rely only on resolved human-coded evidence, while the extension layer is used to map broader patterns, identify candidate examples, and motivate future work.

## Why Not Scrape More Yet

Use some version of this:

At the current stage, additional scraping is not the highest-priority next step for this paper. The broader corpus is already much larger than the validated coding base, meaning that the main bottleneck is methodological packaging and interpretation rather than raw collection. Further scraping would be more useful in a later extension wave designed to test new platforms, niches, or time periods.

## Suggested Paper Structure

1. Introduction
2. Related Work
3. System Design
4. Validation Workflow
5. YouTube Validation Case
6. Results
7. Discussion
8. Ethics and Reproducibility
9. Limitations
10. Conclusion

## Section-by-Section Purpose

### Introduction

State the workflow problem, make the system the primary object of the paper, and preview the YouTube analysis as a validation case.

### Related Work

Distinguish the paper from:

- annotation platforms
- social media analytics dashboards
- active-learning / weak-supervision pipelines
- explainable or augmented-intelligence content-analysis tools

### System Design

Describe the system’s novelty as the validated-evidence / exploratory-extension split inside one explainable workflow.

### Validation Workflow

Explain the codebook, double-coding rule, disagreement handling, adjudication process, freeze rule, and why “resolved” is trustworthy.

### YouTube Validation Case

Describe the broader corpus briefly, then justify why the frozen 1,100-comment evidence layer is the paper’s main analytical dataset.

### Results

Give H1 the space. Report H2 honestly as non-supported. Keep H3 exploratory.

### Discussion

Interpret the results mainly as evidence that the workflow can recover a meaningful ranked-cue signal while preserving methodological discipline.

### Ethics and Reproducibility

Show that the workflow includes practical safeguards around identifiers, exports, and frozen evidence management.

### Limitations

Be explicit about sparse proof-demand, few skeptical-cue videos, and the case-study status of the evidence layer.

### Conclusion

Reinforce the main message: system first, validated case second.

## Figure And Table Plan

### Boundary figure

Show this explicitly:

raw corpus -> screened corpus -> coded corpus -> adjudicated/resolved corpus -> frozen validated evidence -> exploratory extension

This figure is important because it makes the epistemic boundary reviewer-proof.

### Validation table

Include:

- frozen runs
- resolved comments
- double-coded comments
- disagreement cases
- unresolved disagreements
- freeze date

### System evaluation table

Use a compact table like this:

| Layer | Size / status | Human vs assistive role | Analytical use |
| --- | --- | --- | --- |
| Broader collected corpus | `33,467` comments | collection + assistive diagnostics | context only |
| Labeled comments in frozen runs | `2,043` | human coding with assistive context | candidate evidence layer |
| Frozen resolved evidence | `1,100` | human validated | main confirmatory analysis |
| Disagreement cases | `148` | human adjudication | quality control |
| Unresolved disagreements at freeze | `0` | n/a | frozen state |
| Exploratory extension layer | remainder outside frozen evidence | assistive screening only | contextual mapping, future follow-up |

If you need one measurable workflow benefit, the safest defensible claim is not “time saved,” but “the system preserves a narrow validated evidence layer while still retaining the much larger corpus for exploratory extension instead of forcing a false choice between full manual coding and opaque automation.”

## What To Cut Or Soften

- broad claims about general audience behavior on platforms
- language implying strong theory support beyond H1
- attempts to enlarge proof-demand into a major result
- confident discussion of niche effects
- long feature catalogs
- any phrasing that blurs validated evidence with automated screening

## Good Final Claim

The paper shows that a human-in-the-loop analytics system can produce a defensible validated evidence layer while retaining a separate exploratory extension layer, and that this workflow recovers one clear ranked-cue effect in a bounded YouTube validation case.

