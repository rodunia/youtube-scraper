# Workflow Evaluation Notes

- Freeze: `KES-final` (id=8, uuid=freeze-20260408T142800Z)
- Run scope: `11, 18, 20, 22, 23, 24`
- Random baseline seed: `20260420`
- Random simulations: `5000`

## Methods paragraph (paper-ready)

Workflow evaluation used freeze-scoped resolved labels only and did not treat assistive outputs as ground truth. We selected comments that had recorded annotation priority scores, kept the earliest priority-scored touch per comment, and compared top-priority versus remainder yield on the resolved any-core-positive outcome. As a practical review-effort proxy, we computed how many reviews are needed to recover 80% of positives under priority order and under random ordering using a fixed-seed Monte Carlo simulation.

## Results paragraph (paper-ready)

In the instrumented subset (n=222, positives=95), the top-priority slice (n=56) had a positive rate of 0.8929 versus 0.2711 in the remainder (lift=3.2937), capturing 0.5263 of all positives in this subset. To recover 80% of positives, priority ordering required 86 reviews versus a random-order mean of 176.6358 (5th-95th percentile 164.0000 to 188.0000), implying a review-burden reduction of 0.5131.

## Limitation sentence (paper-ready)

This metric is limited to comments with recorded priority traces and should be interpreted as an instrumented-subset workflow signal rather than a full-corpus benchmark.

## Interpretation guardrail

Use this as a practical workflow-value signal for the instrumented queueing subset only. Do not interpret it as classifier accuracy or as evidence that assistive labels replace human validation.
