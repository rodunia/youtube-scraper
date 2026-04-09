# Paper Figure Pack Runbook (2026-04-09)

This runbook generates a deterministic figure bundle anchored to a named evidence freeze.

## Command

```bash
PYTHONPATH=src python -m youtube_scraper.cli paper-figure-pack \
  --freeze-name KES-final \
  --out-dir exports/paper_figures/kes_final
```

Optional:

- `--freeze-id 8` to lock by numeric freeze ID.
- `--include-flagged` only for sensitivity checks (not recommended for paper-safe defaults).

## Core Outputs

- `figure_01_workflow_boundary.mmd`
  - Workflow boundary diagram spec (validated vs exploratory split).
- `figure_02_evidence_funnel.csv`
  - Stage counts for raw -> screened -> coded -> resolved -> frozen -> exploratory extension.
- `figure_02_evidence_funnel.html`
  - Interactive bar chart for the evidence funnel.
- `figure_03_freeze_metadata.csv`
  - Freeze identity and versioning panel (ID/UUID, runs, counts, versions).
- `figure_03_reproducibility_term_diffs.csv`
  - Run1 vs run2 coefficient differences from same freeze-scoped model input.
- `figure_03_reproducibility_summary.json`
  - Pass/fail summary with tolerances and max deltas.
- `figure_04_model_forest_effects.csv`
  - OR/CI/p table for forest plot.
- `figure_04_model_forest_plot.html`
  - Forest plot (log-scale OR, 95% CI).
- `figure_05_predicted_probabilities.csv`
  - Model-implied probabilities by niche and top-cue condition (z-moderators fixed at 0).
- `figure_05_predicted_probabilities.html`
  - Grouped bar chart for predicted probabilities.
- `figure_appendix_prevalence_by_run_niche.csv`
  - Freeze prevalence table by run and niche.
- `figure_appendix_prevalence_heatmap.html`
  - Optional appendix heatmap.
- `paper_figure_pack_manifest.json`
  - Single-file manifest with freeze anchor, headline H1 metrics, reproducibility status, and file inventory.

## Paper Integration (suggested mapping)

- Figure 1: workflow boundary (`figure_01_workflow_boundary.mmd` rendered).
- Figure 2: evidence funnel (`figure_02_evidence_funnel.html` screenshot/export).
- Figure 3: freeze metadata + reproducibility (`figure_03_*`).
- Figure 4: model forest plot (`figure_04_model_forest_plot.html`).
- Figure 5: predicted probabilities by niche (`figure_05_predicted_probabilities.html`).

## Notes

- The command reads freeze scope from `evidence_freezes` and computes model outputs from resolved-consensus labels only.
- This keeps paper-facing visuals aligned with the validated layer, while exploratory outputs remain separate by design.
