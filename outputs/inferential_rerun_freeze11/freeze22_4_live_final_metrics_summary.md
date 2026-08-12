# Freeze Metrics Summary: freeze-22-4-live-final

## Freeze identity
- freeze_id: `11`
- freeze_uuid: `freeze-20260422T131415Z`
- freeze_name: `freeze-22-4-live-final`
- created_by: `annotator_a`
- created_at: `2026-04-22T14:00:58.423110+00:00`
- run_ids: `[11, 12, 17, 18, 20, 22, 23, 24]`

## Frozen validated layer summary
- resolved_comments: `1708`
- double_coded_comments: `1708`
- disagreement_comments: `439`
- unresolved_disagreements: `0`
- any_core_positive: `359`
- skepticism_positive: `208`
- proof_positive: `4`
- normalization_positive: `147`
- channels: `77`
- videos: `619`

## Response-frame rebuild (inferential rerun)
- resolved_comments_before_screen: `1708`
- resolved_comments_after_screen: `1708`
- videos_after_screen: `619`
- videos_excluded_no_response_candidates_ranks_2_20: `268`
- videos_excluded_top_timestamp_missing: `0`
- final videos in response frame: `351`
- final response rows (ranks 2-20): `1075`
- skeptical top-cue videos: `30`
- skeptical-cue response rows: `159`

## Data handling
- missing like_count before fill: `0` (filled with 0)
- missing/unusable timestamps before response filtering: `0`
- elapsed hours = (response_timestamp - top_timestamp) / 3600, clipped at 0; no silent imputation for missing timestamps

## Descriptive cue contrast
- skeptical top cue: skepticism_rate=`0.440252` (70/159), videos=`30`
- non-skeptical top cue: skepticism_rate=`0.066594` (61/916), videos=`321`

## Model metrics (BinomialBayesMixedGLM fit_vb)
- H1 main predictor `top_comment_skeptical`: OR=`5.289126`, 95% CI [`3.494488`, `8.005424`], p≈`3.35792e-15`
- Niche interaction terms:
  - `top_comment_skeptical:C(channel_niche, Treatment(reference='Lifestyle'))[T.Beauty]`: OR=`40.781755`, 95% CI [`22.036950`, `75.471039`], p≈`3.53886e-32`
  - `top_comment_skeptical:C(channel_niche, Treatment(reference='Lifestyle'))[T.Tech]`: OR=`0.265558`, 95% CI [`0.124274`, `0.567461`], p≈`0.000620574`

## Old-vs-new baseline comparison (manuscript-era baseline files)
- Response rows: baseline=`933.0`, rerun=`1075.0`, delta=`142.0`
- Videos in response frame: baseline=`272.0`, rerun=`351.0`, delta=`79.0`
- Skeptical top-cue videos: baseline=`17.0`, rerun=`30.0`, delta=`13.0`
- Skeptical-cue response rows: baseline=`161.0`, rerun=`159.0`, delta=`-2.0`
- Downstream skepticism rate | skeptical cue: baseline=`0.3788819875776397`, rerun=`0.440251572327044`, delta=`0.0613695847494042`
- Downstream skepticism rate | non-skeptical cue: baseline=`0.0310880829015544`, rerun=`0.0665938864628821`, delta=`0.0355058035613276`
- Top-cue main effect OR: baseline=`7.927484424924973`, rerun=`5.2891262478050125`, delta=`-2.6383581771199607`

## Generated artifacts
- `outputs/inferential_rerun_freeze11/freeze10_analytic_response_frame.csv`
- `outputs/inferential_rerun_freeze11/freeze10_cue_rate_crosstab.csv`
- `outputs/inferential_rerun_freeze11/freeze10_exclusion_audit.csv`
- `outputs/inferential_rerun_freeze11/freeze10_forest_plot.png`
- `outputs/inferential_rerun_freeze11/freeze10_handling_summary.csv`
- `outputs/inferential_rerun_freeze11/freeze10_model_effects.csv`
- `outputs/inferential_rerun_freeze11/freeze10_model_formula.txt`
- `outputs/inferential_rerun_freeze11/freeze10_model_summary.txt`
- `outputs/inferential_rerun_freeze11/freeze10_old_vs_new_comparison.csv`
- `outputs/inferential_rerun_freeze11/freeze10_ranked_resolved_comments.csv`
- `outputs/inferential_rerun_freeze11/freeze10_rerun_manifest.json`
- `outputs/inferential_rerun_freeze11/freeze10_rerun_report.md`
- Note: filenames use `freeze10_*` prefix for historical script naming, but this bundle was run on freeze_id 11.
