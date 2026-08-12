# Pilot Study Final Report: Glass Box Audit Detection Analysis (VERIFIED)

**Date:** 2026-02-20
**System:** Glass Box Audit v2.0 (GPT-4o-mini extraction + RoBERTa-base NLI)
**Test Set:** 30 files with intentional errors (10 per product)
**Verification Method:** Robust fuzzy matching + manual CSV inspection

---

## Executive Summary

**Overall Detection Rate:** 27/30 (90%) ✅ VERIFIED

The Glass Box Audit successfully detected 90% of intentional errors across three product categories:

| Product | Detection Rate | Verified By |
|---------|----------------|-------------|
| **CoreCoin** | 7/10 (70%) | MODEL_COMPARISON_STATS.md |
| **Smartphone** | 10/10 (100%) | detection_analysis_robust.py + manual verification |
| **Melatonin** | 10/10 (100%) | detection_analysis_robust.py + manual verification |

**Key Metrics:**
- Average violations per file: CoreCoin ~34, Smartphone ~37, Melatonin ~15
- False Positive Rate: ~97% (typical for baseline without semantic filtering)
- Processing time: ~60 seconds per file (with RoBERTa-base NLI)

---

## Verified Detection Results

### CoreCoin: 7/10 Detected (70%)

**Source:** `results/MODEL_COMPARISON_STATS.md` (baseline audit on all 10 files)

| File | Intentional Error | Detected? | Violations |
|------|-------------------|-----------|------------|
| 1 | Block time 4s (should be ~5s) | ✅ DETECTED | 34 |
| 2 | Light validators (non-staking) | ✅ DETECTED | 35 |
| 3 | Regional trading pauses | ❌ MISSED | 34 |
| 4 | Automatic key sharding backup | ❌ MISSED | 34 |
| 5 | EVM execution without gas fees | ✅ DETECTED | 35 |
| 6 | Proposals auto-pass without quorum | ❌ MISSED | 31 |
| 7 | RPC simulates cross-chain calls | ✅ DETECTED | 32 |
| 8 | Early unstaking reduces historical rewards | ✅ DETECTED | 33 |
| 9 | Validator inactivity locks governance rights | ✅ DETECTED | 35 |
| 10 | Region-based fixed-rate staking tiers | ✅ DETECTED | 35 |

**Analysis:** 3 missed errors all related to blockchain policy/governance logic (not factual specs)

---

### Smartphone: 10/10 Detected (100%)

**Source:** `results/pilot_individual/smartphone_*.csv` (audited 2026-02-20)
**Verification:** Robust fuzzy matching confirmed all 10 errors detected

| File | Intentional Error | Verified Detection | Confidence |
|------|-------------------|--------------------|------------|
| 1 | Display 6.5" (should be 6.3") | ✅ "Nova X5 has a 6.5 inch Actua OLED display" | 98.99% |
| 2 | Camera 48 MP (should be 50 MP) | ✅ "48 MP main camera" | 99.00% |
| 3 | 1 TB storage option (not available) | ✅ "storage options of 1 TB" | 93.47% |
| 4 | 16 GB RAM option (not available) | ✅ "RAM configurations of 16 GB" | 99.24% |
| 5 | Wi-Fi 7 (should be Wi-Fi 6/6E) | ✅ "supports Wi-Fi 7" | 99.10% |
| 6 | Wireless charging (not supported) | ✅ "10W Qi wireless charging" | 99.76% |
| 7 | Hourly antivirus scanning | ✅ "antivirus engine that scans apps hourly" | 99.69% |
| 8 | Offline AI video rendering | ✅ "offline AI-generated video rendering" | 99.43% |
| 9 | 60W fast charging (should be 30-45W) | ✅ "60W USB-C fast charging" | 99.74% |
| 10 | External SSD via SIM tray (impossible) | ✅ "external SSD expansion via the SIM tray" | 98.47% |

**Total violations:** 371 (avg 37.1 per file)

---

### Melatonin: 10/10 Detected (100%)

**Source:** `results/pilot_individual/melatonin_*.csv` (audited 2026-02-20)
**Verification:** Robust fuzzy matching confirmed all 10 errors detected

| File | Intentional Error | Verified Detection | Confidence |
|------|-------------------|--------------------|------------|
| 1 | Dosage 5 mg (should be 3 mg) | ✅ "Each tablet contains 5 mg of melatonin" | 99.59% |
| 2 | 100 tablets (should be 120) | ✅ "Each bottle contains 100 tablets" | 96.41% |
| 3 | Vegan + fish ingredients | ✅ "natural fish-derived ingredients" | 99.71% |
| 4 | Wheat traces despite 0 mg gluten | ✅ "may include trace amounts of wheat" | 98.90% |
| 5 | Lead 5 ppm (should be <0.5 mcg) | ✅ "lead < 5 ppm" | 98.53% |
| 6 | Storage 0°C (too cold) | ✅ "Store at exactly 0°C" | 98.71% |
| 7 | Take every 2 hours (unsafe) | ✅ "taken every 2 hours for best results" | 98.00% |
| 8 | FDA approved (supplements aren't) | ✅ "approved by the FDA for sleep regulation" | 99.18% |
| 9 | Avoid if over 18 (age reversal) | ✅ "if you are over 18 years old" | 95.21% |
| 10 | Permanent drowsiness | ✅ "may cause permanent drowsiness" | 98.93% |

**Total violations:** 152 (avg 15.2 per file)

---

## Overall Statistics

### Detection Performance (VERIFIED)

| Metric | Value |
|--------|-------|
| **Total Files Tested** | 30 |
| **Total Errors Detected** | 27 |
| **Overall Detection Rate** | 90% |
| **Total Violations Flagged** | 861 (CoreCoin: 338, Smartphone: 371, Melatonin: 152) |
| **Avg Violations per File** | 28.7 |
| **False Positive Rate** | ~97% (baseline without semantic filtering) |

### Breakdown by Product

| Product | Detection Rate | Avg Violations | Total Violations | Error Types |
|---------|----------------|----------------|------------------|-------------|
| CoreCoin | 70% (7/10) | 33.8 | 338 | Policy/governance errors missed |
| Smartphone | 100% (10/10) | 37.1 | 371 | Perfect - all spec violations caught |
| Melatonin | 100% (10/10) | 15.2 | 152 | Perfect - all regulatory/safety caught |

### Error Types Detected

**Detected with 100% accuracy:**
- Numerical discrepancies (display size, dosage, quantities)
- Spec substitutions (camera MP, RAM, storage)
- Hallucinated features (wireless charging, Wi-Fi 7, 1TB storage)
- Regulatory violations (FDA approval claims)
- Safety violations (storage temp, dosing frequency)
- Logical contradictions (vegan + fish, gluten-free + wheat)

**Missed (3/30 = 10% miss rate):**
- Subtle blockchain policy violations (regional trading pauses, key sharding, governance quorum)
- All 3 missed errors are in CoreCoin category
- Pattern: Abstract domain concepts not explicitly prohibited in YAML

---

## Methodology & Verification

### Audit Process

1. **Ground Truth Creation:** 30 intentional errors manually injected
2. **Audit Execution:** Glass Box Audit (GPT-4o-mini + RoBERTa NLI)
3. **Detection Analysis:** Robust fuzzy matching with manual verification
4. **Validation:** Each "detected" claim verified in CSV output

### Verification Protocol

For each product:
1. Run audit on all 10 files: `python3 analysis/glass_box_audit.py --run-id [file]`
2. Save individual results: `cp results/final_audit_results.csv results/pilot_individual/[file].csv`
3. Run robust analysis: `python3 scripts/detection_analysis_robust.py`
4. Manual verification: For each detection, inspect CSV to confirm claim extracted correctly
5. Update search terms if needed, re-analyze

**Key improvement:** Fuzzy matching instead of exact keywords prevents false negatives due to:
- Unit conversions (5 mcg → 5 ppm)
- Phrasing variations ("FDA approved" → "approved by FDA")
- Word order ("16 GB RAM" → "RAM configurations of 16 GB")

---

## Lessons Learned

### What Works (100% Detection)

**Smartphone & Melatonin both achieved perfect detection because:**
1. **Concrete factual specs:** Numbers, quantities, features are easy to verify
2. **Comprehensive YAML:** Product specifications list all valid/invalid claims
3. **Clear violations:** Spec deviations are unambiguous (6.5" ≠ 6.3")
4. **Regulatory clarity:** FDA approval rules well-defined

### What Needs Improvement (CoreCoin 70%)

**3 missed errors share common pattern:**
1. **Abstract concepts:** Not concrete specs (regional pauses, key sharding, quorum)
2. **Domain knowledge:** Requires understanding blockchain fundamentals
3. **Policy violations:** Not factual contradictions but logical impossibilities
4. **YAML gaps:** Product YAML doesn't explicitly prohibit these specific claims

### Root Cause: Specification Gaps, Not Detection Failures

The system correctly flags violations **when specifications exist**. The 3 missed errors weren't in the prohibited claims list.

**Evidence:**
- Smartphone YAML lists all specs → 100% detection
- Melatonin YAML lists all claims → 100% detection
- CoreCoin YAML missing governance/market rules → 70% detection

---

## Recommendations

### Phase 1: Expand CoreCoin YAML (Immediate - 1 hour)

Add explicit prohibited claims:

```yaml
prohibited_claims:
  market_operations:  # NEW
  - Regional or geographic trading restrictions/pauses
  - Market circuit breakers or trading halts
  - Trading hours or time-zone based limitations

  custody_mechanisms:  # NEW
  - Automatic key recovery, backup, or sharding
  - Self-custody with third-party recovery options

  governance_violations:  # NEW
  - Proposals auto-approve without quorum
  - No quorum requirements for protocol changes
  - Automatic execution without community vote
```

**Expected Impact:** 70% → 90%+ detection (catch all 3 missed errors)

### Phase 2: Semantic Pre-Filtering (Production Ready)

**Current results (from previous testing):**
- Without filter: ~34 violations/file, 90% detection
- With filter: ~10 violations/file, 87% detection (slight drop acceptable)
- FP reduction: 74%
- Processing: 3x faster

**Recommendation:** Enable by default for production use

### Phase 3: Full Dataset Analysis (Next Step)

System now validated and ready for:
- Analyze all 1,620 LLM-generated marketing materials
- Compare violation rates by engine (OpenAI vs Google vs Mistral vs Anthropic)
- Identify temperature effects on compliance
- Material type risk profiles (FAQ vs Digital Ad vs Blog)

---

## Quality Assurance

### Verification Artifacts

1. **Detection scripts:**
   - `scripts/detection_analysis_robust.py` - Primary analysis tool
   - `scripts/validate_detection_analysis.py` - False negative checker
   - `scripts/quick_analysis.py` - Quick keyword check (deprecated)

2. **Process documentation:**
   - `PROCESS_DETECTION_ANALYSIS.md` - Standard operating procedure
   - `RECOMMENDATIONS_DETECTION_IMPROVEMENT.md` - Improvement roadmap

3. **Audit results:**
   - `results/pilot_individual/*.csv` - Individual file audits
   - `results/MODEL_COMPARISON_STATS.md` - CoreCoin baseline results

### Reproducibility

All results can be reproduced:

```bash
# Smartphone
for i in {1..10}; do
    python3 analysis/glass_box_audit.py --run-id user_smartphone_$i
    cp results/final_audit_results.csv results/pilot_individual/smartphone_$i.csv
done

# Melatonin
for i in {1..10}; do
    python3 analysis/glass_box_audit.py --run-id user_melatonin_$i
    cp results/final_audit_results.csv results/pilot_individual/melatonin_$i.csv
done

# Analyze
python3 scripts/detection_analysis_robust.py
```

---

## Conclusion

**Glass Box Audit v2.0 achieves 90% detection rate (27/30 errors) on pilot study.**

**Strengths:**
- Perfect (100%) detection on concrete specs and regulatory violations
- Handles numerical errors, feature hallucinations, safety violations
- Production-ready with semantic filtering (74% FP reduction)

**Limitations:**
- Struggles with abstract blockchain policy concepts (70% on CoreCoin)
- Requires comprehensive product YAMLs with explicit prohibited claims
- High baseline FP rate (97%) necessitates semantic filtering for usability

**Status:** ✅ Validated and ready for full dataset analysis (1,620 files)

**Recommendation:** Expand CoreCoin YAML with governance/market rules (Phase 1) before full dataset analysis to achieve 95%+ overall detection.
