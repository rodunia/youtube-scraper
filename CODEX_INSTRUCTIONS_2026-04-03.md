# Instructions for Re-running Conformity Analysis (17 Videos)

**Date**: 2026-04-03
**Task**: Remove duplicate video and re-run conformity cascade analysis

---

## 🎯 Problem

Video `2w-iOmZigmI` appears TWICE in database:
- `video_db_id = 1939` (run 22) ✅ KEEP THIS
- `video_db_id = 2713` (run 23) ❌ EXCLUDE THIS

This inflated Beauty videos from 3 → 5, but actually only 4 unique videos exist.

---

## 📋 Step-by-Step Instructions

### **Step 1: Generate Revised Evidence Freeze CSV**

In Streamlit "Evidence Freeze" tab:
1. Open existing freeze: `evidence_base_freeze.json` (2026-04-03T19:03:58)
2. **Add filter**: Exclude `video_db_id = 2713`
3. Export to CSV for conformity analysis

**OR** run this SQL query to generate CSV directly:

```sql
-- Export conformity dataset excluding duplicate video 2713
.mode csv
.headers on
.output data/conformity_input_17videos_2026-04-03.csv

WITH resolved_comments AS (
    SELECT
        a.comment_db_id,
        CASE
            WHEN MAX(a.is_adjudicated) = 1 THEN (
                SELECT skepticism_fake_callout
                FROM annotations
                WHERE comment_db_id = a.comment_db_id AND is_adjudicated = 1
                LIMIT 1
            )
            WHEN COUNT(DISTINCT a.annotator_id) >= 2
             AND MIN(a.skepticism_fake_callout) = MAX(a.skepticism_fake_callout)
            THEN MIN(a.skepticism_fake_callout)
        END as resolved_skepticism
    FROM annotations a
    GROUP BY a.comment_db_id
    HAVING COUNT(DISTINCT a.annotator_id) >= 2
       AND (MAX(a.is_adjudicated) = 1
            OR (MIN(a.skepticism_fake_callout) = MAX(a.skepticism_fake_callout)
                AND MIN(a.proof_demand) = MAX(a.proof_demand)
                AND MIN(a.normalization_defense) = MAX(a.normalization_defense)))
)
SELECT
    v.video_id,
    ch.channel_id,
    ch.niche as channel_niche,
    c.cleaned_text as comment_text,
    c.like_count,
    c.published_at as comment_timestamp,
    rc.resolved_skepticism as is_skeptical
FROM resolved_comments rc
JOIN comments c ON c.id = rc.comment_db_id
JOIN videos v ON v.id = c.video_db_id
JOIN channels ch ON ch.id = c.channel_db_id
WHERE c.run_id IN (11, 18, 20, 22, 23, 24)
  AND c.comment_rank BETWEEN 1 AND 20
  AND c.is_spam = 0
  AND c.is_template = 0
  AND c.is_duplicate = 0
  AND v.id != 2713  -- ← EXCLUDE DUPLICATE
ORDER BY v.video_id, c.like_count DESC, c.published_at ASC;

.output stdout
```

**Expected result**: CSV with ~1,308 comments (down from ~1,322)

---

### **Step 2: Run Conformity Cascade Analysis**

**Option A: In Streamlit**
1. Go to "Conformity Cascade" tab
2. Load CSV: `conformity_input_17videos_2026-04-03.csv`
3. Click "Run Analysis"
4. Export results to `conformity_results_17videos_2026-04-03.csv`

**Option B: Via Python Script**

```python
from pathlib import Path
from youtube_scraper.conformity_cascade import run_from_csv

result = run_from_csv(
    input_csv=Path("data/conformity_input_17videos_2026-04-03.csv"),
    output_effects_csv=Path("data/conformity_effects_17videos.csv"),
    output_icc_csv=Path("data/conformity_icc_17videos.csv"),
    output_response_csv=Path("data/conformity_response_17videos.csv"),
)

print("\n=== Fixed Effects ===")
print(result.effects_df.to_string())

print("\n=== ICC ===")
print(result.icc_df.to_string())
```

---

### **Step 3: Compare Results**

**Key metrics to check:**

| Metric | 16 videos | 18 videos | 17 videos (target) |
|--------|-----------|-----------|-------------------|
| **Total videos** | 16 | 18 | 17 |
| **Beauty videos** | 3 | 5 | 4 |
| **H1 Main Effect OR** | 17.73 | 2.55 | ? |
| **H1 p-value** | <0.001 | <0.001 | ? |
| **Beauty Interaction OR** | 38.0 | 1.06 | ? |
| **Beauty p-value** | <0.001 | 0.908 | ? |
| **Tech Interaction OR** | 0.18 | 0.86 | ? |
| **Tech p-value** | <0.001 | 0.628 | ? |
| **Like Count × Skeptical OR** | (not tested) | 0.18 | ? |
| **Time × Skeptical OR** | (not tested) | 0.056 | ? |

**Expected outcome:**
- H1 main effect: OR should be between 2.55 and 17.73 (likely ~5-10 range)
- Beauty interaction: OR might recover to 10-25 range (but probably still not 38)
- Tech interaction: OR might recover to 0.3-0.5 range (but probably not 0.18)
- Like count and time interactions: Should remain significant

---

## 🔍 Verification Queries

### **Check skeptical-cue video count:**

```sql
WITH resolved_comments AS (
    SELECT
        a.comment_db_id,
        CASE
            WHEN MAX(a.is_adjudicated) = 1 THEN (SELECT skepticism_fake_callout FROM annotations WHERE comment_db_id = a.comment_db_id AND is_adjudicated = 1 LIMIT 1)
            WHEN COUNT(DISTINCT a.annotator_id) >= 2 AND MIN(a.skepticism_fake_callout) = MAX(a.skepticism_fake_callout) THEN MIN(a.skepticism_fake_callout)
        END as resolved_skepticism
    FROM annotations a
    GROUP BY a.comment_db_id
    HAVING COUNT(DISTINCT a.annotator_id) >= 2
       AND (MAX(a.is_adjudicated) = 1 OR (MIN(a.skepticism_fake_callout) = MAX(a.skepticism_fake_callout) AND MIN(a.proof_demand) = MAX(a.proof_demand) AND MIN(a.normalization_defense) = MAX(a.normalization_defense)))
)
SELECT
    ch.niche,
    COUNT(DISTINCT c.video_db_id) as skeptical_cue_videos
FROM resolved_comments rc
JOIN comments c ON c.id = rc.comment_db_id
JOIN channels ch ON ch.id = c.channel_db_id
WHERE c.video_db_id IN (
    SELECT DISTINCT c2.video_db_id
    FROM resolved_comments rc2
    JOIN comments c2 ON c2.id = rc2.comment_db_id
    WHERE c2.comment_rank = 1 AND rc2.resolved_skepticism = 1
)
AND c.run_id IN (11, 18, 20, 22, 23, 24)
AND c.video_db_id != 2713  -- Exclude duplicate
GROUP BY ch.niche
ORDER BY skeptical_cue_videos DESC;
```

**Expected result:**
```
Tech     | 10
Beauty   | 4
Lifestyle| 3
```

---

## 📊 Interpretation Guidelines

### **If Beauty OR recovers to 15-30 range (p < 0.05):**
✅ **Report as moderate amplification**
- Frame: "Beauty content shows moderate amplification (OR ≈ 20-30)"
- Note: More conservative than initial 16-video estimate (OR=38)

### **If Beauty OR stays weak (OR < 5, p > 0.05):**
⚠️ **Accept non-replication**
- Frame: "Niche moderation did not replicate with expanded validation"
- Focus on: Main effect + quality/time moderators

### **If H1 main effect stabilizes around OR = 3-5:**
✅ **Report as robust finding**
- Frame: "Conformity cascades are real but moderate (OR ≈ 3-5)"
- More defensible than OR=17.73 (likely overfitted)

---

## 🚨 Common Issues

### **Issue 1: "video_id not found" error**
- **Cause**: CSV missing required columns
- **Fix**: Ensure CSV has: `video_id`, `channel_id`, `channel_niche`, `comment_text`, `like_count`, `comment_timestamp`, `is_skeptical`

### **Issue 2: "No variation in dependent variable"**
- **Cause**: Filtered dataset has only 0s or only 1s for `is_skeptical`
- **Fix**: Check that you have both skeptical-cue videos AND non-skeptical videos

### **Issue 3: Model convergence warning**
- **Cause**: Small sample size or multicollinearity
- **Fix**: Try simplifying model (remove interactions if needed)

---

## 📝 Files to Generate

1. ✅ `conformity_input_17videos_2026-04-03.csv` — Input data (excluding video 2713)
2. ✅ `conformity_effects_17videos.csv` — Fixed effects table
3. ✅ `conformity_icc_17videos.csv` — ICC table
4. ✅ `RESULTS_17VIDEOS_COMPARISON_2026-04-03.md` — Comparison document

---

## 🎯 Success Criteria

**Minimum acceptable outcome:**
- H1 main effect: p < 0.001, OR > 2.0
- At least ONE new moderator significant (quality OR time)
- Clear documentation of what changed vs 18-video analysis

**Best-case outcome:**
- H1: OR ≈ 5-10, p < 0.001
- Beauty: OR ≈ 15-25, p < 0.05
- Tech: OR ≈ 0.3-0.5, p < 0.05
- Quality and time moderators remain significant

---

**Generated**: 2026-04-03 21:35
**Status**: Ready to execute
**Next**: Run SQL query → Generate CSV → Run conformity analysis → Compare results
