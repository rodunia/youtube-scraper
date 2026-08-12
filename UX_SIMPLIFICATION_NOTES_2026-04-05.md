# UX Simplification Notes

Date: 2026-04-05
Branch context: `conference-paper-prep-2026-04-05`

Purpose:
Create a lightweight working note for simplifying the current app UX without adding new product surface area.

## Keep

- Keep the `Run Lab` name.
- Keep the current high-level workflow centered on evidence preparation, analysis, and export.
- Keep exploratory tools available, but make them feel secondary.

## Core Direction

The next UX pass should focus on subtraction, clearer naming, and explicit actions.

That means:

- fewer visible controls at once
- fewer automatic reruns triggered by checkboxes/selects
- clearer distinction between paper-safe outputs and exploratory outputs
- simpler names for tabs, controls, and exports
- more "summary first, details second"

## Main Problems To Fix

### 1. Too many decisions on screen at once

Current risk:
- users are asked to interpret too many options before they know what matters

Simplification:
- show only the core path first
- move advanced options into collapsed sections
- reduce repeated banners, metrics, and diagnostics

### 2. Actions happen on tick/change

Current risk:
- changing a checkbox or select can feel like it already "did something"
- the user loses a sense of control over when analysis is actually rerun

Simplification:
- checkbox/select controls should only set state
- expensive actions should happen only after pressing a clear button
- use grouped forms where possible:
  - `Apply filters`
  - `Run analysis`
  - `Export`

### 3. Naming is more technical than it needs to be

Current risk:
- labels are accurate but cognitively heavy
- paper-facing and exploratory actions are not always obvious at a glance

Simplification:
- prefer plain-language labels
- reserve technical wording for expanders/help text
- make paper-safe vs exploratory language explicit in names

## Rename Candidates

Keep:
- `Run Lab`

Change:
- `Conformity Cascade` -> `Main Analysis`
- `Combined Hypotheses` -> `Cross-Run Analysis`
- `Comment label source` -> `Evidence Source`
- `Build final analysis pack` -> `Export Paper Files`
- `Build uncoded extension analysis` -> `Explore Uncoded (Not for Paper)`
- `Include flagged` -> `Include filtered-out rows`
- `Model Effects` -> `Model Results`
- `Combined Model Effects` -> `Cross-Run Model Results`

## Tab-by-Tab Simplification

### Run Lab

Goal:
- keep as the home for research workflow

Simplify:
- keep `Step 1 / Step 2 / Step 3`
- show only one compact status summary at the top
- collapse explanatory panels by default
- reduce visible export buttons to the most important paper outputs first
- move secondary reproducibility/diagnostic tables lower on the page

### Main Analysis

Goal:
- make this the clearest "run the model, read the result" page

Simplify:
- put controls in one compact filter row
- add explicit `Run analysis` behavior instead of passive reruns
- show headline results first:
  - H1
  - H2
  - H3
  - sample size
- put full effect table, ICC, and response frame below

### Cross-Run Analysis

Goal:
- make pooled analysis feel like an advanced but understandable extension

Simplify:
- reduce visible options
- keep only essential pooled summary metrics up top
- collapse raw response frame by default
- emphasize why/when to use this tab

### Annotation

Goal:
- reduce friction and accidental state confusion

Simplify:
- keep the coding surface visible
- reduce explanatory clutter around it
- keep label guide in an expander
- avoid making every toggle feel like a major action
- keep save actions highly explicit

### Auto Analysis / Exploratory Areas

Goal:
- preserve value without competing with the validated workflow

Simplify:
- clearly mark as exploratory
- collapse by default where possible
- cut visible metrics to only those needed for triage/follow-up

## Priority Order

### First pass

- keep `Run Lab`
- rename the most confusing tabs and controls
- stop checkbox-driven action patterns where possible
- reduce default-on detail panels

### Second pass

- simplify export areas
- compress repeated metric strips
- improve summary-first layout on analysis pages

### Later

- annotation keyboard ergonomics
- stronger visual distinctions between validated and exploratory layers
- deeper layout cleanup

## Guardrails

- do not add new features unless a simplification depends on them
- prefer removing or hiding controls over introducing new ones
- preserve current analytical behavior unless explicitly changing it
- keep paper-safe workflow obvious

## Working Decision

For the next UX branch:

- keep `Run Lab`
- simplify names elsewhere
- reduce passive checkbox-triggered behavior
- optimize for clarity over completeness on first load
