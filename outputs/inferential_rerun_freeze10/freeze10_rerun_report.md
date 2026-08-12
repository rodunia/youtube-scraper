# Freeze-Scoped Inferential Rerun Report

## Freeze Anchor
- freeze_id: `10`
- freeze_uuid: `freeze-20260422T131415Z`
- freeze_name: `freeze-20-4a`
- run_ids: `[11, 12, 17, 18, 20, 21, 22, 23, 24, 25]`

## Data Handling
- Missing like_count values before ranking: `0` (handled as `0` for ranking and top-cue like predictor).
- Missing/unusable timestamps before response filtering: `2`.
- Elapsed hours computed as `(response_timestamp - top_timestamp)`; negative values clipped to `0`; rows missing either timestamp excluded.

## Exclusion Audit
- resolved_comments_before_screen: `1710`
- excluded_flagged_comments: `0`
- resolved_comments_after_screen: `1710`
- videos_after_screen: `621`
- videos_excluded_no_response_candidates_ranks_2_20: `270`
- videos_excluded_top_timestamp_missing: `2`
- videos_excluded_all_response_rows_invalid: `0`
- videos_in_final_response_frame: `351`
- response_rows_before_timestamp_and_label_filters: `1075`
- excluded_rows_missing_response_or_top_timestamp: `0`
- excluded_rows_missing_response_label: `0`
- final_response_rows: `1075`

## Required Counts
- rebuilt freeze-scoped response frame count: `1075`
- skeptical top-cue videos: `30`
- skeptical-cue response rows: `159`

## Old vs New Frame Baseline
- baseline response source: `data/conformity_response_17videos_2026-04-03.csv`
- baseline effects source: `data/conformity_effects_17videos_2026-04-03.csv`
- baseline response_rows: `933` | new: `1075`
- baseline skeptical_top_cue_videos: `17` | new: `30`

## Interaction Stability
- sparse_cue_structure_flag: `1`
- interpretation: H1 can be treated as the primary confirmatory effect if its main cue term remains in the expected direction; H3 (niche interactions) should be framed as fragile/secondary.

