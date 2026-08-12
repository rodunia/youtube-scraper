# IRR Findings — KES 2026 Compliance Pilot
**Date:** 2026-07-14 (updated 2026-07-20)
**Coders:** Christian, Dorota, Edyta, Mohan + GPT-4o + NLI/RoBERTa
**Items:** 100 LLM-generated marketing outputs
**DB:** `outputs/compliance/pilot_coding.db`

---

## Study context

RQ: *How reliable is automatic generation of marketing materials using LLMs?*

Human coders assessed 100 LLM-generated marketing outputs for compliance violations.
Each item was independently coded by all 4 human coders (400 total annotations).
Two automated systems (GPT-4o compliance judge, NLI/RoBERTa pipeline) were also
applied to the same 100 items, enabling a 6-coder comparison.
No skipped items.

---

## Level 1 — Binary decision (compliant / non-compliant)

### NC rates — all 6 coders
| Coder | Type | NC rate | n NC |
|-------|------|---------|------|
| NLI/RoBERTa | Machine | 91% | 91 |
| Edyta | Human | 89% | 89 |
| Christian | Human | 72% | 72 |
| Dorota | Human | 61% | 61 |
| GPT-4o | Machine | 55% | 55 |
| Mohan | Human | 52% | 52 |

Range across all 6: 91% − 52% = **39 percentage points**.

### Multi-rater agreement summary
| Metric | All 6 coders | 4 humans only | 2 machines only |
|--------|-------------|---------------|-----------------|
| Krippendorff's α | **+0.086** | **+0.050** | **+0.087** |
| Fleiss' κ | **+0.086** | **+0.050** | — |

> **Correction note:** An earlier version of this document reported α = −0.895 for
> 4 human coders. This was caused by a row/column transposition in the data passed
> to the library. The correct value is α = +0.050, consistent with Fleiss' κ = +0.050.
> The interpretation (slight, near-chance agreement) is unchanged.

### All 15 pairwise Cohen's κ
| Pair | Type | κ | 95% CI | p | PABAK | % agree |
|------|------|---|--------|---|-------|---------|
| Christian / Dorota | H–H | **+0.446** | [+0.258, +0.634] | **< .001 ***\*** | +0.500 | 75% |
| Dorota / GPT-4o | H–M | **+0.427** | [+0.247, +0.607] | **< .001 ***\*** | +0.440 | 72% |
| Christian / GPT-4o | H–M | **+0.393** | [+0.207, +0.579] | **< .001 ***\*** | +0.420 | 71% |
| GPT-4o / NLI | M–M | +0.216 | [+0.011, +0.421] | .039 * | +0.280 | 64% |
| Dorota / Edyta | H–H | +0.179 | [−0.045, +0.403] | .117 ns | +0.320 | 66% |
| Edyta / GPT-4o | H–M | +0.176 | [−0.031, +0.382] | .095 ns | +0.240 | 62% |
| Dorota / NLI | H–M | +0.122 | [−0.108, +0.351] | .300 ns | +0.280 | 64% |
| Christian / Edyta | H–H | +0.117 | [−0.154, +0.388] | .397 ns | +0.420 | 71% |
| Christian / NLI | H–M | +0.030 | [−0.254, +0.314] | .836 ns | +0.380 | 69% |
| Edyta / NLI | H–M | +0.001 | [−0.417, +0.419] | .996 ns | +0.640 | 82% |
| Edyta / Mohan | H–H | −0.053 | [−0.255, +0.149] | .609 ns | −0.020 | 49% |
| Mohan / NLI | H–M | −0.055 | [−0.257, +0.148] | .597 ns | −0.020 | 49% |
| Christian / Mohan | H–H | −0.059 | [−0.258, +0.141] | .564 ns | −0.040 | 48% |
| Dorota / Mohan | H–H | −0.110 | [−0.307, +0.087] | .274 ns | −0.100 | 45% |
| **Mohan / GPT-4o** | H–M | **−0.265** | [−0.455, −0.075] | **.006 **\*** | −0.260 | 37% |

*SE via Fleiss–Cohen approximation; two-tailed z-test; H=human, M=machine.*

### Agreement cluster summary
| Comparison type | Mean κ | n pairs |
|-----------------|--------|---------|
| Human – Human | +0.087 | 6 |
| Human – Machine | +0.104 | 8 |
| Machine – Machine | +0.216 | 1 |

**Key finding:** Only 3 of 15 pairs reach statistical significance:
- Christian/Dorota (H–H, κ=+0.446) — the strongest human pair
- Dorota/GPT-4o (H–M, κ=+0.427) and Christian/GPT-4o (H–M, κ=+0.393) — GPT-4o aligns with the two middle-threshold human coders
- Mohan/GPT-4o is the only *significantly negative* pair (κ=−0.265, p=.006) — Mohan is a systematic outlier relative to GPT-4o

### PABAK interpretation
Under PABAK (corrects for unequal base rates):
- Christian/Dorota: +0.500 (moderate) — most reliable human pair
- Christian/Edyta: +0.420 (moderate) — despite non-significant raw κ
- Dorota/GPT-4o: +0.440 (moderate) — GPT-4o most aligned with Dorota
- All Mohan pairs: ≤ −0.020 (near-zero or negative)
- Edyta/NLI: +0.640 (substantial) — both use a high-sensitivity threshold

### NLI/RoBERTa as a coder
The NLI pipeline (GPT-4o-mini claim extraction + RoBERTa NLI) shows:
- NC rate 91% — highest of all 6 coders
- κ vs gold standard: +0.016 (essentially random agreement)
- High recall (catches 91% of true NC items) but 90% false positive rate on compliant items
- Aligned with Edyta by PABAK (+0.640) — both use near-maximum sensitivity

This system is better understood as a *high-recall factual claim checker* than a
general compliance judge. It is useful for ruling items *in* as compliant (when it
says PASS, items are very likely clean) but not for ruling items *out*.

### Diagnosis
Overall agreement across all 6 coders is slight (α = +0.086, Fleiss' κ = +0.086).
The dominant patterns are:
1. **Threshold cluster:** Edyta + NLI cluster at high NC rates (89–91%); Christian +
   Dorota + GPT-4o cluster in the middle (55–72%); Mohan is the most lenient (52%)
2. **GPT-4o aligns with humans, not NLI:** GPT-4o's two strongest agreements are
   with Dorota (κ=+0.427) and Christian (κ=+0.393), not with the other machine (NLI κ=+0.216)
3. **Mohan is the sole significant outlier:** The only significantly negative κ in
   the full 15-pair table is Mohan/GPT-4o (κ=−0.265, p=.006)
4. **Calibration problem, not content disagreement:** the 39-point NC rate range
   across coders reflects threshold differences, not inability to identify problems

---

## Level 2 — Per-code binary agreement (code applied: yes/no)

Sorted by Krippendorff's α descending. Codes with 0 prevalence omitted.

| Code | α | mean κ | Usage (of 400 ratings) |
|------|---|--------|------------------------|
| `testimonial_misrepresentation` | **+0.394** | +0.691 | 10.8% (43) |
| `prompt_injection_artifact` | −0.041 | +0.462 | 20.5% (82) |
| `superlative_without_basis` | −0.477 | +0.292 | 6.5% (26) |
| `missing_mandatory_disclaimer` | −0.497 | +0.244 | 21.5% (86) |
| `unauthorized_health_claim` | −0.696 | +0.210 | 6.5% (26) |
| `off_spec_content` | −0.727 | +0.108 | 4.8% (19) |
| `false_authority_claim` | −0.751 | +0.231 | 1.2% (5) |
| `repetitious_information` | −0.803 | +0.222 | 2.8% (11) |
| `inadequate_financial_risk_warning` | −0.844 | +0.058 | 6.2% (25) |
| `misleading_efficacy_claim` | −0.852 | +0.077 | 21.5% (86) |
| `false_urgency_or_scarcity` | −0.890 | +0.043 | 2.2% (9) |
| `spec_accuracy_violation` | −0.920 | +0.028 | 4.2% (17) |
| `hallucinated_feature` | −0.958 | +0.048 | 10.8% (43) |

**Diagnosis:** Only `testimonial_misrepresentation` shows genuine agreement
(α = +0.394, mean κ = +0.691). Positive pairwise κ but negative α for most codes
indicates *concept drift* — coders use the same label but apply it to different items.

> **Note:** Per-code α values are unaffected by the Level 1 correction (they were
> computed independently using the same correct method).

---

## Level 3 — Code-set agreement (non-compliant items only)

| Metric | Value |
|--------|-------|
| Items where ≥2 coders said non-compliant | 90 / 100 |
| Exact code-set match (all agreeing coders) | **5 / 90 (5.6%)** |

### Mean Jaccard similarity on code sets
| Pair | Jaccard | n items |
|------|---------|---------|
| Christian / Dorota | 0.449 | 54 |
| Christian / Mohan | 0.396 | 36 |
| Christian / Edyta | 0.312 | 66 |
| Edyta / Mohan | 0.313 | 45 |
| Dorota / Mohan | 0.306 | 29 |
| Dorota / Edyta | 0.241 | 58 |

~30% overlap in code selection between coder pairs. Coders agree something is wrong
but assign different violation labels to it.

---

## Item-level consensus

| Category | n | % |
|----------|---|---|
| **Unanimous compliant** (all 4 human coders) | 2 | 2% |
| **Unanimous non-compliant** (all 4 human coders) | 26 | 26% |
| **Split** (any disagreement) | 72 | 72% |
| ≥1 coder flagged non-compliant | 98 | 98% |

---

## Most flagged violation codes (all coders combined)

| Code | Total flags | % of 400 ratings |
|------|-------------|------------------|
| `misleading_efficacy_claim` | 86 | 21.5% |
| `missing_mandatory_disclaimer` | 86 | 21.5% |
| `prompt_injection_artifact` | 82 | 20.5% |
| `hallucinated_feature` | 43 | 10.8% |
| `testimonial_misrepresentation` | 43 | 10.8% |
| `unauthorized_health_claim` | 26 | 6.5% |
| `superlative_without_basis` | 26 | 6.5% |
| `inadequate_financial_risk_warning` | 25 | 6.25% |
| `off_spec_content` | 19 | 4.75% |
| `spec_accuracy_violation` | 17 | 4.25% |

### Codes on unanimous non-compliant items (n=26, highest confidence)
| Code | Flags |
|------|-------|
| `prompt_injection_artifact` | 44 |
| `testimonial_misrepresentation` | 39 |
| `misleading_efficacy_claim` | 37 |
| `missing_mandatory_disclaimer` | 27 |
| `superlative_without_basis` | 16 |
| `unauthorized_health_claim` | 15 |
| `hallucinated_feature` | 12 |
| `off_spec_content` | 9 |

---

## Disagreement structure

| Split type | n items |
|------------|---------|
| 3v1 (majority resolvable) | 42 |
| 2v2 (genuine split) | 30 |
| **Total disagreements** | **72** |

---

## Gold standard (post-adjudication, n=100)

42 items auto-resolved by majority vote (3v1); 30 manually adjudicated by lead
researcher (Dorota). Final distribution:

| Decision | n | % |
|----------|---|---|
| Non-compliant | 80 | 80% |
| Compliant | 20 | 20% |

Top violation codes from gold NC items: misleading_efficacy_claim (37),
missing_mandatory_disclaimer (35), prompt_injection_artifact (32),
hallucinated_feature (21), unauthorized_health_claim (17).

---

## Machine judge validation against gold (n=100)

| System | NC rate | Accuracy | F1 | κ vs gold | FN rate | FP rate |
|--------|---------|----------|----|-----------|---------|---------|
| NLI/RoBERTa | 91% | 75% | 0.854 | 0.016 | 9% | 90% |
| GPT-4o compliance | 55% | 63% | 0.726 | 0.213 | 39% | 30% |
| Claude compliance | 51% | 59% | 0.687 | 0.170 | 44% | 30% |
| GPT-4o OR Claude | 72% | 72% | 0.816 | 0.239 | 23% | 50% |

No single machine system achieves acceptable agreement with the human gold standard
(κ < 0.25 for all). The best available machine ensemble (GPT-4o OR Claude) achieves
F1 = 0.816 but κ = 0.239 — "fair" agreement at best.

---

## Interpretation for paper

### Answer to RQ
LLM-generated marketing materials show systematic and pervasive compliance
violations: 98% of items received at least one non-compliant flag; only 2/100
were unanimously judged compliant by all four human coders. Even Mohan — the most
lenient coder — flagged 52% of items as non-compliant. Gold standard (post-adjudication)
rate: **80% non-compliant**.

### On the low IRR
Overall IRR is slight (α = +0.086, Fleiss' κ = +0.086 across 6 coders). The dominant
driver is threshold calibration differences — a 39-point NC rate gap between the most
and least strict coder — not disagreement about whether problems exist. Three of four
human coders form a coherent cluster (PABAK 0.32–0.50 among Christian, Dorota, Edyta);
Mohan is the systematic outlier (all Mohan κ values negative). This finding is
meaningful: compliance assessment is sufficiently subjective that uncalibrated coders
diverge significantly, motivating the need for automated and/or calibration-assisted tools.

### On the 6-coder comparison
Neither machines nor humans achieve reliable multi-rater agreement on this task
(mean H–H κ = +0.087; mean H–M κ = +0.104; M–M κ = +0.216). The slight advantage
of machine–machine agreement over human–human is misleading: both machines operate
at extreme NC rates (55% and 91%) with low mutual validity against gold. GPT-4o's
strongest alignments are with human coders (Dorota κ=+0.427, Christian κ=+0.393),
not with the other machine — suggesting GPT-4o captures similar judgment heuristics
to middle-threshold human coders.

### Key recommendation
Calibration session (joint review of gold standard) before additional annotation
rounds. Post-calibration IRR on a new 200-item set will test whether the threshold
gap is correctable through training. Expected improvement: κ ≥ 0.40 within the
human coder cluster.
