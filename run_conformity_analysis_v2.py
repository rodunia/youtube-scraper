#!/usr/bin/env python3
"""
Run conformity cascade analysis with the new expanded evidence freeze
"""
import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, 'src')

import pandas as pd
from youtube_scraper.conformity_cascade import run_conformity_cascade

DB_PATH = Path("data/youtube_comments.db")
FREEZE_PATH = Path("data/evidence_base_freeze.json")
OUTPUT_DIR = Path("data/exports")

def main():
    print("=" * 80)
    print("CONFORMITY CASCADE ANALYSIS - EXPANDED EVIDENCE BASE v2")
    print("=" * 80)

    # Load freeze metadata
    print(f"\n📊 Loading evidence freeze: {FREEZE_PATH}")
    freeze = json.loads(FREEZE_PATH.read_text())
    print(f"   Generated: {freeze['generated_at']}")
    print(f"   Resolved comments: {freeze['snapshot_summary']['resolved_comments']}")
    print(f"   Skepticism positive: {freeze['snapshot_summary']['skepticism_positive']}")
    print(f"   Run IDs: {freeze['run_ids']}")

    # Load resolved consensus data from database
    print(f"\n📦 Loading resolved consensus data from database...")
    conn = sqlite3.connect(DB_PATH)

    query = """
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
            END as is_skeptical
        FROM annotations a
        GROUP BY a.comment_db_id
        HAVING COUNT(DISTINCT a.annotator_id) >= 2
           AND (MAX(a.is_adjudicated) = 1
                OR (MIN(a.skepticism_fake_callout) = MAX(a.skepticism_fake_callout)
                    AND MIN(a.proof_demand) = MAX(a.proof_demand)
                    AND MIN(a.normalization_defense) = MAX(a.normalization_defense)))
    )
    SELECT
        c.id as comment_id,
        v.video_id,
        ch.channel_id,
        ch.niche as channel_niche,
        c.cleaned_text as comment_text,
        c.like_count,
        c.published_at as comment_timestamp,
        rc.is_skeptical,
        c.comment_rank
    FROM resolved_comments rc
    JOIN comments c ON c.id = rc.comment_db_id
    JOIN videos v ON v.id = c.video_db_id
    JOIN channels ch ON ch.id = c.channel_db_id
    WHERE c.is_spam = 0
      AND c.is_template = 0
      AND c.is_duplicate = 0
      AND c.comment_rank BETWEEN 1 AND 20
    ORDER BY v.video_id, c.comment_rank
    """

    df = pd.read_sql_query(query, conn)
    conn.close()

    print(f"   Loaded {len(df)} comments")
    print(f"   Videos: {df['video_id'].nunique()}")
    print(f"   Channels: {df['channel_id'].nunique()}")
    print(f"   Niches: {df['channel_niche'].unique().tolist()}")

    # Check skeptical top comments
    top_skeptical = df[df['comment_rank'] == 1]['is_skeptical'].sum()
    print(f"   Skeptical top-ranked comments: {top_skeptical}")

    if top_skeptical == 0:
        print("\n❌ ERROR: No skeptical top-ranked comments found!")
        print("   Cannot run conformity cascade analysis without skeptical cues.")
        return 1

    # Run analysis
    print(f"\n🔬 Running conformity cascade analysis...")
    try:
        result = run_conformity_cascade(df)
    except Exception as e:
        print(f"\n❌ ERROR during analysis: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print(f"   ✅ Analysis complete!")

    # Display results
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)

    print(f"\n📊 Response Frame:")
    print(f"   Total response comments (rank 2-20): {len(result.response_df)}")
    print(f"   Videos with responses: {result.response_df['video_id'].nunique()}")
    print(f"   Skeptical top cue videos: {result.response_df['top_comment_skeptical'].sum()}")
    print(f"   Non-skeptical top cue videos: {(1 - result.response_df['top_comment_skeptical']).sum()}")

    # Cross-tab
    print(f"\n📋 Crosstab (Top Skeptical → Response Skeptical):")
    crosstab = pd.crosstab(
        result.response_df['top_comment_skeptical'],
        result.response_df['is_skeptical'],
        margins=True
    )
    print(crosstab)

    # Calculate simple rates
    top_0 = result.response_df[result.response_df['top_comment_skeptical'] == 0]
    top_1 = result.response_df[result.response_df['top_comment_skeptical'] == 1]

    rate_0 = top_0['is_skeptical'].mean() if len(top_0) > 0 else 0
    rate_1 = top_1['is_skeptical'].mean() if len(top_1) > 0 else 0

    print(f"\n📈 Skepticism Rates:")
    print(f"   Non-skeptical top cue (n={len(top_0)}): {rate_0:.1%}")
    print(f"   Skeptical top cue (n={len(top_1)}): {rate_1:.1%}")
    print(f"   Difference: {(rate_1 - rate_0):.1%}")

    # Model results
    print(f"\n🔍 H1 Model Results (Fixed Effects):")
    print(result.effects_df.to_string(index=False))

    # Extract H1 result
    h1_row = result.effects_df[result.effects_df['term'] == 'top_comment_skeptical']
    if not h1_row.empty:
        or_val = h1_row['odds_ratio'].iloc[0]
        ci_low = h1_row['or_ci_95_low'].iloc[0]
        ci_high = h1_row['or_ci_95_high'].iloc[0]
        p_val = h1_row['p_value_approx'].iloc[0]

        print(f"\n🎯 H1 Main Effect:")
        print(f"   OR = {or_val:.3f}, 95% CI [{ci_low:.3f}, {ci_high:.3f}], p ≈ {p_val:.4f}")

        if p_val < 0.05:
            print(f"   ✅ SIGNIFICANT at α=0.05")
        else:
            print(f"   ⚠️  NOT significant at α=0.05")

    # ICC
    print(f"\n📊 Variance Components (ICC):")
    print(result.icc_df.to_string(index=False))

    # Export results
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    effects_file = OUTPUT_DIR / f"conformity_v2_effects_{timestamp}.csv"
    icc_file = OUTPUT_DIR / f"conformity_v2_icc_{timestamp}.csv"
    response_file = OUTPUT_DIR / f"conformity_v2_response_frame_{timestamp}.csv"
    summary_file = OUTPUT_DIR / f"conformity_v2_summary_{timestamp}.json"

    result.effects_df.to_csv(effects_file, index=False)
    result.icc_df.to_csv(icc_file, index=False)
    result.response_df.to_csv(response_file, index=False)

    # Summary JSON
    summary = {
        "generated_at": timestamp,
        "freeze_date": freeze['generated_at'],
        "total_resolved_comments": freeze['snapshot_summary']['resolved_comments'],
        "skepticism_positive": freeze['snapshot_summary']['skepticism_positive'],
        "response_frame_n": len(result.response_df),
        "skeptical_top_cue_videos": int(result.response_df['top_comment_skeptical'].sum()),
        "h1_odds_ratio": float(or_val) if not h1_row.empty else None,
        "h1_ci_95_low": float(ci_low) if not h1_row.empty else None,
        "h1_ci_95_high": float(ci_high) if not h1_row.empty else None,
        "h1_p_value": float(p_val) if not h1_row.empty else None,
        "h1_significant": bool(p_val < 0.05) if not h1_row.empty else False,
        "skepticism_rate_non_skeptical_cue": float(rate_0),
        "skepticism_rate_skeptical_cue": float(rate_1),
    }

    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2)

    print(f"\n💾 Exported:")
    print(f"   {effects_file}")
    print(f"   {icc_file}")
    print(f"   {response_file}")
    print(f"   {summary_file}")

    print("\n" + "=" * 80)
    print("✅ ANALYSIS COMPLETE!")
    print("=" * 80)

    return 0

if __name__ == "__main__":
    sys.exit(main())
