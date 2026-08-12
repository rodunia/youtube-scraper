# Randomizer ANOVA Validation Report
**Generated:** 2026-03-21 11:26:15
---

## Purpose
Statistical validation that experimental factors (engine, temperature, material, product) are truly independent of timing factors (day of week, time of day) using Analysis of Variance (ANOVA).

**Key Question:** Does the randomizer create a truly random distribution, or are there systematic patterns that would confound temporal analysis?

---

## Test 1: Day of Week Effect
**Test:** One-Way ANOVA (7 groups)

**H₀:** Mean calls per hour is equal across all days

**Results:**
- F-statistic: nan
- p-value: nan
- Significant at α=0.05: NO ✅

**Interpretation:** NOT SIGNIFICANT (p=nan): Day of week does NOT significantly affect call volume. ✅ Randomization working as expected.

---

## Test 2: Time of Day Effect
**Test:** One-Way ANOVA (3 groups) with Tukey HSD post-hoc

**H₀:** Mean calls per hour is equal across all time slots

**Results:**
- F-statistic: 4.3997
- p-value: 0.0125
- Significant at α=0.05: YES ⚠️

**Tukey HSD Post-Hoc Results:**
```
  Multiple Comparison of Means - Tukey HSD, FWER=0.05  
=======================================================
  group1   group2 meandiff p-adj   lower  upper  reject
-------------------------------------------------------
afternoon evening   0.0292 0.4812 -0.0301 0.0885  False
afternoon morning   0.0765 0.0093  0.0155 0.1374   True
  evening morning   0.0473 0.1528 -0.0126 0.1072  False
-------------------------------------------------------
```

**Interpretation:** SIGNIFICANT (p=0.0125): Time of day DOES affect call volume. See Tukey HSD results for pairwise differences.

---

## Test 3: LLM Engine Effect
**Test:** One-Way ANOVA (3 groups, perfectly balanced)

**H₀:** Mean calls per hour is equal across all engines

**Results:**
- F-statistic: 13.3203
- p-value: 0.0000
- Significant at α=0.05: YES ⚠️

**Interpretation:** SIGNIFICANT (p=0.0000): Engine DOES affect call volume. This suggests non-random assignment of engines to time slots.

---

## Test 4: Temperature Setting Effect
**Test:** One-Way ANOVA (3 groups, perfectly balanced) with Tukey HSD post-hoc

**H₀:** Mean calls per hour is equal across all temperature settings

**Results:**
- F-statistic: 201.4660
- p-value: 0.0000
- Significant at α=0.05: YES ⚠️

**Tukey HSD Post-Hoc Results:**
```
Multiple Comparison of Means - Tukey HSD, FWER=0.05 
====================================================
group1 group2 meandiff p-adj   lower   upper  reject
----------------------------------------------------
   0.2    0.3    1.961    0.0  1.1293  2.7927   True
   0.2    0.4    0.961    0.0   0.847   1.075   True
   0.2    0.5    1.961    0.0  1.6443  2.2776   True
   0.2    0.6   0.0947    0.0  0.0382  0.1513   True
   0.2    0.7    1.961    0.0  1.4796  2.4423   True
   0.2    0.8    0.961    0.0  0.8039  1.1181   True
   0.2    0.9    1.961    0.0  1.1293  2.7927   True
   0.2    1.0   0.0235  0.939 -0.0338  0.0808  False
   0.3    0.4     -1.0 0.0067 -1.8375 -0.1625   True
   0.3    0.5      0.0    1.0 -0.8881  0.8881  False
   0.3    0.6  -1.8662    0.0 -2.6978 -1.0346   True
   0.3    0.7      0.0    1.0 -0.9592  0.9592  False
   0.3    0.8     -1.0 0.0075 -1.8444 -0.1556   True
   0.3    0.9      0.0    1.0 -1.1748  1.1748  False
   0.3    1.0  -1.9375    0.0 -2.7692 -1.1058   True
   0.4    0.5      1.0    0.0  0.6685  1.3315   True
   0.4    0.6  -0.8662    0.0 -0.9795  -0.753   True
   0.4    0.7      1.0    0.0  0.5087  1.4913   True
   0.4    0.8      0.0    1.0 -0.1852  0.1852  False
   0.4    0.9      1.0 0.0067  0.1625  1.8375   True
   0.4    1.0  -0.9375    0.0 -1.0511 -0.8239   True
   0.5    0.6  -1.8662    0.0 -2.1826 -1.5499   True
   0.5    0.7      0.0    1.0 -0.5732  0.5732  False
   0.5    0.8     -1.0    0.0 -1.3487 -0.6513   True
   0.5    0.9      0.0    1.0 -0.8881  0.8881  False
   0.5    1.0  -1.9375    0.0  -2.254  -1.621   True
   0.6    0.7   1.8662    0.0   1.385  2.3474   True
   0.6    0.8   0.8662    0.0  0.7097  1.0228   True
   0.6    0.9   1.8662    0.0  1.0346  2.6978   True
   0.6    1.0  -0.0713 0.0024  -0.127 -0.0155   True
   0.7    0.8     -1.0    0.0  -1.503  -0.497   True
   0.7    0.9      0.0    1.0 -0.9592  0.9592  False
   0.7    1.0  -1.9375    0.0 -2.4188 -1.4562   True
   0.8    0.9      1.0 0.0075  0.1556  1.8444   True
   0.8    1.0  -0.9375    0.0 -1.0943 -0.7807   True
   0.9    1.0  -1.9375    0.0 -2.7692 -1.1058   True
----------------------------------------------------
```

**Interpretation:** SIGNIFICANT (p=0.0000): Temperature DOES affect call volume. See Tukey HSD results for pairwise differences.

---

## Test 5: Two-Way ANOVA - Day × Time Interaction
**Test:** Two-Way ANOVA (7 × 3 = 21 cells)

**H₀ (Interaction):** The effect of time of day is consistent across all days

**Results:**

| Effect | F | p-value | Significant |
|--------|---|---------|-------------|
| Day (main) | 1.1748 | 0.3201 | NO ✅ |
| Time (main) | 0.0129 | 0.9097 | NO ✅ |
| Day × Time (interaction) | 0.9411 | 0.4940 | NO ✅ |

**Interpretation:**
✅ Main effect of DAY is NOT significant (p=0.3201)
✅ Main effect of TIME is NOT significant (p=0.9097)
✅ INTERACTION is NOT significant (p=0.4940)
This means the time-of-day pattern is consistent across days.

---

## Overall Verdict

### ⚠️  POTENTIAL ISSUES DETECTED

One or more ANOVA tests were significant, suggesting:
- Non-random patterns may exist
- Review significant effects above
- Consider re-running randomization with different seed

**Recommendation:** Investigate significant effects before proceeding.
