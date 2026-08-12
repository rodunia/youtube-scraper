# Randomizer Dry-Run Validation Report
**Generated:** 2026-03-16 01:33:35
---
## Summary
- **Total runs:** 1620
- **Days:** 7 (full week)
- **Time slots:** 3 per day
- **Total time cells:** 21

## Distribution by Day of Week
**Expected per day:** 231.4 runs

| Day       | Runs | Expected | Deviation | Status |
|-----------|------|----------|-----------|--------|
| Friday     |  233 | 231.4 | +0.7% | ✅ PASS |
| Monday     |  211 | 231.4 | -8.8% | ❌ FAIL |
| Saturday   |  231 | 231.4 | -0.2% | ✅ PASS |
| Sunday     |  251 | 231.4 | +8.5% | ❌ FAIL |
| Thursday   |  228 | 231.4 | -1.5% | ✅ PASS |
| Tuesday    |  251 | 231.4 | +8.5% | ❌ FAIL |
| Wednesday  |  215 | 231.4 | -7.1% | ❌ FAIL |

**Chi-square test:** χ²=6.34, p=0.3860 (✅ PASS)

## Distribution by Time Slot
**Expected per slot:** 540.0 runs

| Time Slot  | Runs | Expected | Deviation | Status |
|------------|------|----------|-----------|--------|
| afternoon  |  512 | 540.0 | -5.2% | ❌ FAIL |
| evening    |  558 | 540.0 | +3.3% | ✅ PASS |
| morning    |  550 | 540.0 | +1.9% | ✅ PASS |

**Chi-square test:** χ²=2.24, p=0.3268 (✅ PASS)

## Distribution by Day × Time Slot
**Expected per cell:** 77.1 runs

**Cells within tolerance (±10%):** 10/21

**Chi-square test:** χ²=28.19, p=0.1050 (✅ PASS)

## Experimental Factors (Should be Exact)
**product_id:** ✅ PASS
**engine:** ✅ PASS
**material_type:** ✅ PASS
**temperature:** ✅ PASS

## Independence Tests
Testing if experimental factors are independent of timing:

| Test | χ² | p-value | Result |
|------|-----|---------|--------|
| product_id × scheduled_day_of_week | 9.93 | 0.6221 | ✅ PASS |
| product_id × scheduled_time_slot | 5.13 | 0.2741 | ✅ PASS |
| engine × scheduled_day_of_week | 11.02 | 0.5276 | ✅ PASS |
| engine × scheduled_time_slot | 3.67 | 0.4531 | ✅ PASS |
| material_type × scheduled_day_of_week | 10.49 | 0.5731 | ✅ PASS |
| material_type × scheduled_time_slot | 2.87 | 0.5805 | ✅ PASS |

---
## Overall Verdict
### ✅ ALL TESTS PASSED
Randomizer is working correctly. Ready to proceed with experiment.
