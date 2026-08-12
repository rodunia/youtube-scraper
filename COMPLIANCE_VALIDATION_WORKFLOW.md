# Compliance Validation Workflow

This is a separate workflow for validating LLM-generated marketing materials. It lives beside the YouTube workflow without changing it.

## Goal

Use existing machine-judge outputs to drive targeted human validation. Machine assessments are triage signals, not ground truth.

## Current Readiness Assumption

This scaffold is ready before the final dataset is attached. If the only canonical file is `results/experiments.csv` with pending rows, import that file first as the material registry and add machine-judge assessments later when checkpoint outputs are available. Pilot or historical judge outputs can still be imported as separate assessment approaches as long as their coverage is explicit.

## Validation Unit

- Material unit: one generated marketing material.
- Evidence unit: one claim or violation finding inside a material.
- Final material states: `compliant`, `non_compliant`, `inconclusive`, `error`.
- Finding states can capture unsupported claims, contradicted claims, missing required qualifiers, or other domain-specific violation categories.

Material-level rollup:

- `non_compliant` if any human-confirmed material finding is present.
- `inconclusive` if product truth or surrounding context is insufficient.
- `error` only for generation, import, or review failure.
- machine disagreement alone is not an `error`.

## Human-In-The-Loop Design

The workflow creates three main queues:

1. Calibration queue
   - Stratified sample across product, material type, generator model, and machine outcome.
   - Purpose: estimate machine judge behavior against human review.

2. High-risk queue
   - Includes high/critical machine findings, model disagreements, error/timeouts, and high violation counts.
   - Purpose: contain consequential risk first.

3. Negative audit queue
   - Samples all-machine-negative rows: at least one machine judge marked the material compliant, no machine judge flagged a violation, and no machine judge errored.
   - Purpose: estimate false negatives for the full triage stack.

Disagreements between humans, or between human review and high-confidence machine signals, should go to adjudication.

## Setup

Launch the separate compliance Streamlit app:

```bash
PYTHONPATH=src streamlit run app/compliance_app.py
```

Initialize the separate compliance database:

```bash
PYTHONPATH=src python -m compliance_validation.cli init-db
```

Inspect a dataset before mapping:

```bash
PYTHONPATH=src python -m compliance_validation.cli inspect-input \
  --input path/to/materials.csv
```

For a canonical experiment registry with pending rows and no full judge checkpoints yet, copy `src/compliance_validation/templates/material_registry_mapping_template.json`. For a file that already contains machine-judge outputs, copy `src/compliance_validation/templates/mapping_template.json`. Edit column names, then validate:

```bash
PYTHONPATH=src python -m compliance_validation.cli validate-mapping \
  --input path/to/materials.csv \
  --mapping src/compliance_validation/templates/mapping_template.json
```

Import:

```bash
PYTHONPATH=src python -m compliance_validation.cli import-dataset \
  --input path/to/materials.csv \
  --mapping src/compliance_validation/templates/mapping_template.json \
  --dataset-name llm-marketing-materials-v1
```

Build human review queues:

```bash
PYTHONPATH=src python -m compliance_validation.cli build-queues \
  --dataset-name llm-marketing-materials-v1 \
  --calibration-size 300 \
  --negative-audit-size 150 \
  --out-dir outputs/compliance
```

Create assignment packets in the Streamlit app after queues are built:

- `Assignments` creates reviewer packets from named queues.
- `Review` opens one packet at a time and shows the next pending item.
- Blind packets hide machine signals by default.
- Reviewers can save a final decision, defer an item, or skip it with a reason.

Import completed human review sheets:

```bash
PYTHONPATH=src python -m compliance_validation.cli import-human-reviews \
  --dataset-name llm-marketing-materials-v1 \
  --input outputs/compliance/completed_human_reviews.csv
```

Export a summary:

```bash
PYTHONPATH=src python -m compliance_validation.cli summary \
  --dataset-name llm-marketing-materials-v1 \
  --out-dir outputs/compliance
```

## Dataset Fields Needed

Required:

- stable material id
- run id
- output path
- product id
- material type
- engine
- model
- temperature
- time-of-day label
- repetition id
- scheduled day of week
- generated material text

Strongly recommended:

- prompt
- product ground truth
- Claude direct audit status and label
- Claude direct audit severity and violation count
- RoBERTa NLI flag count / status
- GPT-4o reassessment label where available
- GPT-4o conservative direct audit label where available

Optional but useful:

- raw judge JSON
- exact violation spans
- claim text
- product fact references
- API timeout/error markers
- prompt/run metadata

## Resolution Rule

The initial resolution rule should be conservative:

- human-confirmed violation -> validated violation
- human-rejected machine violation -> machine false positive
- human-found violation in machine-negative sample -> machine false negative pattern; expand similar review
- insufficient product truth -> `inconclusive`
- human disagreement -> adjudication

Claude direct audit can be the main machine triage signal, but it should not be called ground truth.
