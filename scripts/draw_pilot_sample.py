"""
Stratified random sample for the compliance coding pilot.

Draws 100 items from experiment_outputs_for_validation.csv using
equal allocation across product_id × material_type × model (36 cells,
3 per cell = 108, then 8 randomly removed to reach exactly 100).

Excludes rows with empty model. No machine judge signals used.
Seed is fixed for reproducibility.
"""
from __future__ import annotations

import csv
import json
import random
from collections import defaultdict
from pathlib import Path

SEED = 20260629
TARGET = 100
STRATA_COLS = ("product_id", "material_type", "model")
MODELS = {
    "gpt-4o-2024-08-06",
    "models/gemini-flash-latest",
    "mistral-large-latest",
    "mistral-large-veteran-2512",
}
INPUT = Path("data/compliance/experiment_outputs_for_validation.csv")
OUT_CSV = Path("outputs/compliance/pilot_sample_100.csv")
OUT_JSON = Path("outputs/compliance/pilot_sample_100_manifest.json")

KEEP_COLS = [
    "run_id",
    "product_id",
    "material_type",
    "model",
    "model_version",
    "temperature",
    "time_of_day_label",
    "repetition_id",
    "scheduled_day_of_week",
    "output_text",
    "prompt_id",
    "prompt_text_path",
    "output_path",
    "scheduled_datetime",
    "date_of_run",
    "status",
]


def main() -> None:
    rng = random.Random(SEED)

    with INPUT.open(newline="", encoding="utf-8") as f:
        all_rows = list(csv.DictReader(f))

    available_cols = list(all_rows[0].keys()) if all_rows else []
    keep = [c for c in KEEP_COLS if c in available_cols]

    cells: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    for row in all_rows:
        model = row.get("model", "").strip()
        if model not in MODELS:
            continue
        key = (
            row.get("product_id", "").strip(),
            row.get("material_type", "").strip(),
            model,
        )
        cells[key].append(row)

    per_cell = 3
    drawn: list[tuple[tuple[str, str, str], dict]] = []
    for key, bucket in sorted(cells.items()):
        rng.shuffle(bucket)
        for row in bucket[:per_cell]:
            drawn.append((key, row))

    # drawn = 108 (36 cells × 3); randomly drop 8 to reach TARGET
    overshoot = len(drawn) - TARGET
    if overshoot > 0:
        drop_indices = set(rng.sample(range(len(drawn)), overshoot))
        drawn = [item for i, item in enumerate(drawn) if i not in drop_indices]

    rng.shuffle(drawn)  # randomize presentation order

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    final_rows = []
    for item_num, (key, row) in enumerate(drawn, start=1):
        out = {c: row.get(c, "") for c in keep}
        out["pilot_item_id"] = item_num
        out["stratum"] = "__".join(key)
        final_rows.append(out)

    fieldnames = ["pilot_item_id", "stratum"] + keep
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(final_rows)

    cell_counts: dict[str, int] = defaultdict(int)
    for _, (key, _) in enumerate(drawn):
        cell_counts["__".join(key)] += 1

    manifest = {
        "seed": SEED,
        "source": str(INPUT),
        "total_source_rows": len(all_rows),
        "total_sampled": len(final_rows),
        "strata_cols": list(STRATA_COLS),
        "cell_counts": dict(sorted(cell_counts.items())),
        "output_csv": str(OUT_CSV),
    }
    with OUT_JSON.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"Drew {len(final_rows)} items from {len(cells)} cells.")
    print(f"CSV:      {OUT_CSV}")
    print(f"Manifest: {OUT_JSON}")
    print()
    print("Cell counts in sample:")
    for cell, n in sorted(cell_counts.items()):
        print(f"  {cell}: {n}")


if __name__ == "__main__":
    main()
