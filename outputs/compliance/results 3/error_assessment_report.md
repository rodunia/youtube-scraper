# Error Assessment Report

Generated: 2026-02-11 18:18:18

---

## Executive Summary

- **Glass Box Audit**: 95 violations detected in 137 runs
- **Golden Dataset**: 500 labeled samples (Contradiction: 31, Entailment: 196, Neutral: 273)
- **Claim Extraction**: 1,520 claims extracted (No Match: 1,393, Partial: 115, Exact: 12)

---

## Key Findings

### 1. Glass Box Audit Violations

**Major Issue**: High false positive rate due to disclaimers
- Disclaimers (e.g., 'may vary', 'depends on') are flagged as contradictions
- NLI model interprets hedging language as contradiction
- **Recommendation**: Separate disclaimer analysis from core claims

### 2. Golden Dataset Quality

**Status**: Label distribution appears reasonable

### 3. Claim Extraction Quality

**Major Issue**: Very high no-match rate (91.6%)
- LLMs generating creative claims beyond YAML definitions
- **Recommendation**: Expand YAML authorized_claims or improve matching


---

## Detailed Statistics

### Glass Box Audit

- Total runs audited: 137
- Violations detected: 95
- Average confidence: 0.9743

### Golden Dataset

- Label 0: 31 (6.2%)
- Label 1: 196 (39.2%)
- Label 2: 273 (54.6%)

### Claim Extraction

- None: 1,393 (91.6%)
- Partial: 115 (7.6%)
- Exact: 12 (0.8%)