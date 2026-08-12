"""
Export pilot coding data to JSONL for LLM training/validation.

Usage:
    python scripts/export_pilot_jsonl.py              # all individual annotations
    python scripts/export_pilot_jsonl.py --gold-only  # only adjudicated gold items
    python scripts/export_pilot_jsonl.py --majority   # majority vote (gold takes precedence)

    # Point at test DB:
    PILOT_DB_PATH=outputs/compliance/test_coding.db \\
    PILOT_SAMPLE_CSV=outputs/compliance/test_sample_10.csv \\
    python scripts/export_pilot_jsonl.py

Output: outputs/compliance/pilot_export_<mode>_<YYYYMMDD>.jsonl
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("PILOT_DB_PATH", "outputs/compliance/pilot_coding.db"))
SAMPLE_CSV = Path(os.environ.get("PILOT_SAMPLE_CSV", "outputs/compliance/pilot_sample_100.csv"))
OUT_DIR = Path("outputs/compliance")


def _conn(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def load_items(csv_path: Path) -> dict[int, dict]:
    with csv_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {int(r["pilot_item_id"]): r for r in rows}


def load_reviews(con: sqlite3.Connection) -> list[dict]:
    rows = con.execute("""
        SELECT coder_id, pilot_item_id, run_id, decision,
               violation_codes, notes, skip_reason, submitted_at
        FROM pilot_reviews
        ORDER BY pilot_item_id, coder_id
    """).fetchall()
    return [dict(r) for r in rows]


def load_gold(con: sqlite3.Connection) -> dict[int, dict]:
    try:
        rows = con.execute(
            "SELECT * FROM gold_decisions ORDER BY pilot_item_id"
        ).fetchall()
        return {r["pilot_item_id"]: dict(r) for r in rows}
    except Exception:
        return {}


def _item_meta(item: dict) -> dict:
    return {
        "run_id": item.get("run_id", ""),
        "output_text": item.get("output_text", ""),
        "product_id": item.get("product_id", ""),
        "material_type": item.get("material_type", ""),
        "model": item.get("model", ""),
    }


def export_all(
    reviews: list[dict],
    items: dict[int, dict],
    out_path: Path,
) -> int:
    """One record per (coder, item) — skip decisions excluded."""
    n = 0
    with out_path.open("w", encoding="utf-8") as f:
        for r in reviews:
            if r["decision"] == "skip":
                continue
            item = items.get(r["pilot_item_id"], {})
            record = {
                **_item_meta(item),
                "pilot_item_id": r["pilot_item_id"],
                "label": r["decision"],
                "violation_codes": json.loads(r.get("violation_codes") or "[]"),
                "notes": r.get("notes", ""),
                "coder": r["coder_id"],
                "submitted_at": r.get("submitted_at", ""),
                "source": "human_pilot",
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1
    return n


def export_gold(
    gold: dict[int, dict],
    items: dict[int, dict],
    out_path: Path,
) -> int:
    """One record per adjudicated item."""
    n = 0
    with out_path.open("w", encoding="utf-8") as f:
        for item_id, g in sorted(gold.items()):
            item = items.get(item_id, {})
            record = {
                **_item_meta(item),
                "pilot_item_id": item_id,
                "label": g["decision"],
                "violation_codes": json.loads(g.get("violation_codes") or "[]"),
                "notes": g.get("notes", ""),
                "adjudicator": g.get("adjudicator", ""),
                "adjudicated_at": g.get("adjudicated_at", ""),
                "source": "human_gold",
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1
    return n


def export_majority(
    reviews: list[dict],
    items: dict[int, dict],
    gold: dict[int, dict],
    out_path: Path,
) -> int:
    """One record per item — gold if adjudicated, else majority vote. Tied items omitted."""
    by_item: dict[int, list[dict]] = defaultdict(list)
    for r in reviews:
        by_item[r["pilot_item_id"]].append(r)

    n = 0
    with out_path.open("w", encoding="utf-8") as f:
        for item_id, item_reviews in sorted(by_item.items()):
            item = items.get(item_id, {})

            if item_id in gold:
                g = gold[item_id]
                decision = g["decision"]
                codes = json.loads(g.get("violation_codes") or "[]")
                notes = g.get("notes", "")
                extra = {"adjudicator": g.get("adjudicator", ""), "source": "human_gold"}
            else:
                non_skip = [r["decision"] for r in item_reviews if r["decision"] != "skip"]
                if not non_skip:
                    continue
                counts = Counter(non_skip)
                top = counts.most_common(2)
                if len(top) > 1 and top[0][1] == top[1][1]:
                    continue  # tie — skip
                decision = top[0][0]
                codes = sorted({
                    c
                    for r in item_reviews
                    if r["decision"] == decision
                    for c in json.loads(r.get("violation_codes") or "[]")
                })
                notes = ""
                extra = {"n_coders_agree": top[0][1], "source": "majority_vote"}

            record = {
                **_item_meta(item),
                "pilot_item_id": item_id,
                "label": decision,
                "violation_codes": codes,
                "notes": notes,
                "n_annotations": len(item_reviews),
                **extra,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            n += 1
    return n


def main() -> None:
    parser = argparse.ArgumentParser(description="Export pilot coding data to JSONL.")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    parser.add_argument("--csv", type=Path, default=SAMPLE_CSV)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--gold-only", action="store_true", help="Only gold-adjudicated items")
    group.add_argument("--majority", action="store_true", help="Majority vote per item (gold takes precedence)")
    args = parser.parse_args()

    if not args.db.exists():
        print(f"ERROR: DB not found: {args.db}")
        raise SystemExit(1)
    if not args.csv.exists():
        print(f"ERROR: CSV not found: {args.csv}")
        raise SystemExit(1)

    mode = "gold" if args.gold_only else ("majority" if args.majority else "all")
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"pilot_export_{mode}_{date_str}.jsonl"

    con = _conn(args.db)
    reviews = load_reviews(con)
    gold = load_gold(con)
    con.close()
    items = load_items(args.csv)

    if args.gold_only:
        n = export_gold(gold, items, out_path)
    elif args.majority:
        n = export_majority(reviews, items, gold, out_path)
    else:
        n = export_all(reviews, items, out_path)

    print(f"Exported {n} records → {out_path}")


if __name__ == "__main__":
    main()
