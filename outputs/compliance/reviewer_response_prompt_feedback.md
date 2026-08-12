# Response to Reviewer Comment on GPT-4o Auditor Prompt
*Draft for co-author review — 2026-07-23*

---

Thank you for these important methodological observations. We address each point below.

**1. Jurisdiction specificity**

You are correct that disclosure requirements are jurisdiction-dependent and that a
jurisdiction-neutral prompt produces legally ambiguous compliance criteria. We have
revised the auditor prompt to specify EU compliance standards:

- Supplement/health claims → EFSA Regulation EC 1924/2006
- Digital asset marketing → MiCA (Regulation EU 2023/1114)
- General advertising → UCPD (Directive 2005/29/EC)

We acknowledge this as a scope limitation in the paper and note that audit outcomes
may differ under alternative frameworks (e.g. US FTC/FDA/SEC). Future work could
replicate the study under US jurisdiction for cross-framework comparison.

**2. Directional bias in the prompt ("Default toward NON-COMPLIANT")**

We agree. The instruction to default toward non-compliant, together with the
assertion that "80% of outputs contain at least one violation," introduces a
systematic prior that cannot be defended when the human inter-rater reliability
on the same corpus is Krippendorff's α = 0.086 — barely above chance. Claiming
this as a "validated" base rate overstates the quality of the gold standard.

We have removed the directional instruction entirely. The six calibration examples
(three compliant, three non-compliant) now guide the model's calibration without
imposing a directional bias. We will report this revision in the Methods section
and note it as a design decision driven by methodological integrity.

**3. Subjective codes in V5**

Agreed. The following codes have been removed from V5:
- *repetitious_information* — editorial judgement, not a compliance standard
- *bad_marketing* — entirely subjective, no regulatory basis
- *typo* — not a compliance issue

*off_spec_content* (content stating facts not present in the brief) has been
reclassified under V1 (Factual Inaccuracy), where it belongs substantively —
if a claim goes beyond what the brief authorises, it is a factual accuracy
violation.

V5 is now narrowly defined as **prompt artifact violations**: output that contains
verbatim system-prompt text, role labels, JSON schema fragments, or other
generation artefacts visible in the consumer-facing output. This is mechanically
verifiable and does not require subjective editorial judgement.

---

## Summary of prompt changes

| What changed | Before | After |
|---|---|---|
| Jurisdiction | None specified | EU (EFSA / MiCA / UCPD) |
| NC prior | "Default toward NON-COMPLIANT; 80% base rate" | Removed |
| V1 scope | Factual inaccuracy + hallucinated specs | Now also covers off-spec content |
| V5 scope | Prompt artifacts + repetition + bad marketing + typo | Prompt artifacts only (concrete definition) |

Backup of original prompt: `outputs/compliance/prompt_versions/prompts_v2_pre_review_2026-07-23.py`
