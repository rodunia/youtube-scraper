# Research Hypothesis Tests - 54 LLM-Generated Files

**Date**: 2026-03-22
**Dataset**: 54 completed LLM-generated marketing files
**Analysis**: Glass Box audit with ground truth YAMLs

---

## H1: People-Pleasing Bias

**Overall mean violations**: 4.78 ± 4.79

**t-test against H0 (mean=0)**: t=7.261, p=0.000000

**✅ CONCLUSION**: STRONG evidence for people-pleasing bias (p < 0.001)

### Engine Comparison

| Engine | Mean Violations | SD | Files with Violations |
|--------|-----------------|----|-----------------------|
| openai | 6.17 | 5.09 | 16/18 (88.9%) |
| google | 3.17 | 3.15 | 16/18 (88.9%) |
| mistral | 5.00 | 5.33 | 17/18 (94.4%) |

**ANOVA**: F=1.815, p=0.173262

---

## H2: Induced Errors and Hallucinations

### Product Comparison

| Product | Mean Violations | Median | SD |
|---------|-----------------|--------|----|  
| cryptocurrency_corecoin | 3.22 | 2.5 | 3.07 |
| smartphone_mid | 7.56 | 3.5 | 6.30 |
| supplement_melatonin | 3.56 | 3.0 | 2.85 |

**ANOVA**: F=5.183, p=0.008934

**✅ CONCLUSION**: Products differ significantly in violation rates

### Material Type Comparison

| Material | Mean Violations | Median | SD |
|----------|-----------------|--------|----|  
| digital_ad | 1.70 | 2.0 | 1.18 |
| faq | 7.85 | 7.0 | 5.06 |

**t-test (FAQ vs Digital Ad)**: t=6.033, p=0.000000

**✅ CONCLUSION**: FAQs have significantly MORE violations than Digital Ads

---

## H3: Temperature Effect

**⚠️ INSUFFICIENT DATA**: All 54 files use temperature=0.6

Cannot test hypothesis without files at temp=0.2 and temp=1.0

