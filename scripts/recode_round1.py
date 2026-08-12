"""
Recode Round 1 pilot_reviews from 13+ original codes → V1-V5.

Reads ONLY from pilot_coding.db (never writes).
Writes: outputs/compliance/round1_recoded.csv
        outputs/compliance/round1_recoded_gold.csv  (gold_decisions recoded)

Run: python scripts/recode_round1.py
"""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

DB_PATH = Path("outputs/compliance/pilot_coding.db")
OUT_DIR = Path("outputs/compliance")
REVIEWS_CSV = OUT_DIR / "round1_recoded.csv"
GOLD_CSV = OUT_DIR / "round1_recoded_gold.csv"

# Deterministic mapping: old code → V1-V5
# Unmapped / ambiguous codes go to V5 (catch-all format/other violation)
CODE_MAP: dict[str, str] = {
    # V1 — factual inaccuracy
    "misleading_efficacy_claim":    "V1",
    "hallucinated_feature":         "V1",
    "false_authority_claim":        "V1",
    "spec_accuracy_violation":      "V1",
    "unverified_statistic":         "V1",
    # V2 — missing disclosure
    "missing_mandatory_disclaimer": "V2",
    "inadequate_financial_risk_warning": "V2",
    "missing_info":                 "V2",
    "missing_information":          "V2",
    "omission_of_material_risk":    "V2",
    # V3 — unauthorized claim
    "unauthorized_health_claim":    "V3",
    "superlative_without_basis":    "V3",
    "fear_appeal_without_basis":    "V3",
    "harmful_advice":               "V3",
    # V4 — testimonial / urgency misuse
    "testimonial_misrepresentation": "V4",
    "false_urgency_or_scarcity":    "V4",
    # V5 — format / structural violation
    "off_spec_content":             "V5",
    "prompt_injection_artifact":    "V5",
    "repetitious_information":      "V5",
    "bad_marketing":                "V5",
    "typo":                         "V5",
}

UNMAPPED_DEFAULT = "V5"


def recode(old_codes: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for c in old_codes:
        v = CODE_MAP.get(c, UNMAPPED_DEFAULT)
        if v not in seen:
            seen.add(v)
            out.append(v)
    return sorted(out)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    # ── pilot_reviews ────────────────────────────────────────────────────────
    rows = conn.execute(
        "SELECT coder_id, pilot_item_id, run_id, decision, violation_codes "
        "FROM pilot_reviews ORDER BY pilot_item_id, coder_id"
    ).fetchall()

    review_out: list[dict] = []
    unmapped_seen: set[str] = set()

    for r in rows:
        old_codes: list[str] = json.loads(r["violation_codes"] or "[]")
        # track any codes we haven't explicitly mapped
        for c in old_codes:
            if c not in CODE_MAP:
                unmapped_seen.add(c)
        new_codes = recode(old_codes)
        review_out.append({
            "coder_id":      r["coder_id"],
            "pilot_item_id": r["pilot_item_id"],
            "run_id":        r["run_id"],
            "decision":      r["decision"],
            "old_codes":     "|".join(old_codes),
            "new_codes":     "|".join(new_codes),
        })

    with REVIEWS_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["coder_id", "pilot_item_id", "run_id", "decision", "old_codes", "new_codes"],
        )
        writer.writeheader()
        writer.writerows(review_out)

    # ── gold_decisions ───────────────────────────────────────────────────────
    gold_rows = conn.execute(
        "SELECT pilot_item_id, decision, violation_codes, adjudicator "
        "FROM gold_decisions ORDER BY pilot_item_id"
    ).fetchall()

    gold_out: list[dict] = []
    for g in gold_rows:
        old_codes = json.loads(g["violation_codes"] or "[]")
        new_codes = recode(old_codes)
        gold_out.append({
            "pilot_item_id": g["pilot_item_id"],
            "decision":      g["decision"],
            "old_codes":     "|".join(old_codes),
            "new_codes":     "|".join(new_codes),
            "adjudicator":   g["adjudicator"],
        })

    with GOLD_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["pilot_item_id", "decision", "old_codes", "new_codes", "adjudicator"],
        )
        writer.writeheader()
        writer.writerows(gold_out)

    conn.close()

    print(f"pilot_reviews recoded:  {len(review_out)} rows → {REVIEWS_CSV}")
    print(f"gold_decisions recoded: {len(gold_out)} rows → {GOLD_CSV}")
    if unmapped_seen:
        print(f"WARNING — codes not in map (defaulted to V5): {sorted(unmapped_seen)}")
    else:
        print("All codes mapped cleanly.")


if __name__ == "__main__":
    main()
