"""
Small test sample for trying out the pilot coding app before the real run.

Draws 10 items at random from experiment_outputs_for_validation.csv,
excluding anything already in the 100-item pilot sample, so testing
doesn't touch the real pilot data.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

SEED = 999
TEST_SIZE = 10
SOURCE = Path("data/compliance/experiment_outputs_for_validation.csv")
PILOT_SAMPLE = Path("outputs/compliance/pilot_sample_100.csv")
OUT_CSV = Path("outputs/compliance/test_sample_10.csv")

KEEP_COLS = [
    "run_id", "product_id", "material_type", "model", "model_version",
    "temperature", "time_of_day_label", "repetition_id",
    "scheduled_day_of_week", "output_text", "prompt_id", "prompt_text_path",
    "output_path", "scheduled_datetime", "date_of_run", "status",
]


def main() -> None:
    rng = random.Random(SEED)

    with SOURCE.open(newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))

    pilot_run_ids: set[str] = set()
    if PILOT_SAMPLE.exists():
        with PILOT_SAMPLE.open(newline="", encoding="utf-8") as f:
            pilot_run_ids = {r["run_id"] for r in csv.DictReader(f)}

    candidates = [
        r for r in all_rows
        if r.get("run_id", "").strip() not in pilot_run_ids
        and r.get("model", "").strip()
        and r.get("output_text", "").strip()
    ]
    rng.shuffle(candidates)
    drawn = candidates[:TEST_SIZE]

    keep = [c for c in KEEP_COLS if c in drawn[0].keys()] if drawn else KEEP_COLS

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["pilot_item_id"] + keep
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for i, row in enumerate(drawn, start=1):
            out = {c: row.get(c, "") for c in keep}
            out["pilot_item_id"] = i
            writer.writerow(out)

    print(f"Wrote {len(drawn)} test items to {OUT_CSV}")


if __name__ == "__main__":
    main()
