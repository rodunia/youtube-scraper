"""
Analysis and adjudication workbench for the compliance coding pilot.

Run alongside the coding app:
    streamlit run app/pilot_analysis.py

Reads from the same DB and CSV as pilot_coding.py (same env vars):
    PILOT_DB_PATH     — default: outputs/compliance/pilot_coding.db
    PILOT_SAMPLE_CSV  — default: outputs/compliance/pilot_sample_100.csv
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

import streamlit as st

DB_PATH = Path(os.environ.get("PILOT_DB_PATH", "outputs/compliance/pilot_coding.db"))
SAMPLE_CSV = Path(os.environ.get("PILOT_SAMPLE_CSV", "outputs/compliance/pilot_sample_100.csv"))

CODERS = ["Dorota", "Mohan", "Christian", "Edyta"]

# Full 15-code codebook v1 — loaded from JSON seed file
_CODEBOOK_SEED_PATH = Path("data/compliance/codebook_v1_seed.json")

def _load_starter_codes() -> list[dict]:
    if _CODEBOOK_SEED_PATH.exists():
        with _CODEBOOK_SEED_PATH.open(encoding="utf-8") as _f:
            return json.load(_f)
    # Minimal fallback if file is missing
    return [
        {"name": "misleading_efficacy_claim", "definition": "Overstates the product's effect or benefit without adequate qualification."},
        {"name": "unverified_statistic", "definition": "Numerical claim presented without a citable source."},
        {"name": "omission_of_material_risk", "definition": "A side effect or limitation that a reasonable consumer would want to know is absent."},
        {"name": "superlative_without_basis", "definition": "Absolute language ('best', '#1', 'only') that cannot be substantiated."},
        {"name": "false_urgency_or_scarcity", "definition": "Pressure language implying fabricated time or quantity limits."},
        {"name": "testimonial_misrepresentation", "definition": "Implied or explicit endorsement that is vague, unattributed, or contradicted by context."},
    ]

STARTER_CODES = _load_starter_codes()

DECISION_LABELS = {
    "compliant": "✓ Compliant",
    "non_compliant": "✗ Non-compliant",
    "skip": "⊘ Skip",
}
DECISION_COLORS = {
    "compliant": "green",
    "non_compliant": "red",
    "skip": "gray",
}


# ── DB ────────────────────────────────────────────────────────────────────────

def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_gold_table() -> None:
    con = _conn()
    con.execute("""
        CREATE TABLE IF NOT EXISTS gold_decisions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            pilot_item_id   INTEGER UNIQUE NOT NULL,
            decision        TEXT NOT NULL,
            violation_codes TEXT DEFAULT '[]',
            notes           TEXT DEFAULT '',
            adjudicator     TEXT DEFAULT '',
            adjudicated_at  TEXT NOT NULL
        )
    """)
    con.commit()
    con.close()


def load_all_reviews() -> list[dict]:
    con = _conn()
    rows = con.execute("""
        SELECT coder_id, pilot_item_id, run_id, decision,
               violation_codes, notes, skip_reason, submitted_at
        FROM pilot_reviews
        ORDER BY pilot_item_id, coder_id
    """).fetchall()
    con.close()
    return [dict(r) for r in rows]


def load_gold() -> dict[int, dict]:
    con = _conn()
    try:
        rows = con.execute(
            "SELECT * FROM gold_decisions ORDER BY pilot_item_id"
        ).fetchall()
        return {r["pilot_item_id"]: dict(r) for r in rows}
    except Exception:
        return {}
    finally:
        con.close()


def save_gold(
    pilot_item_id: int,
    decision: str,
    violation_codes: list[str],
    notes: str,
    adjudicator: str,
) -> None:
    con = _conn()
    con.execute(
        """INSERT INTO gold_decisions
           (pilot_item_id, decision, violation_codes, notes, adjudicator, adjudicated_at)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(pilot_item_id) DO UPDATE SET
             decision        = excluded.decision,
             violation_codes = excluded.violation_codes,
             notes           = excluded.notes,
             adjudicator     = excluded.adjudicator,
             adjudicated_at  = excluded.adjudicated_at
        """,
        (pilot_item_id, decision, json.dumps(violation_codes), notes.strip(), adjudicator, _now()),
    )
    con.commit()
    con.close()


def load_code_names() -> list[str]:
    con = _conn()
    rows = con.execute("SELECT name FROM violation_codes ORDER BY name").fetchall()
    con.close()
    return [r[0] for r in rows]


def load_all_codes_full() -> list[dict]:
    con = _conn()
    rows = con.execute(
        "SELECT name, definition, created_by FROM violation_codes ORDER BY name"
    ).fetchall()
    con.close()
    return [{"name": r[0], "definition": r[1], "created_by": r[2]} for r in rows]


def seed_codes(codes: list[dict], created_by: str = "setup") -> tuple[int, int]:
    """Insert starter codes; skip any that already exist. Returns (added, skipped)."""
    con = _conn()
    added = skipped = 0
    for c in codes:
        try:
            con.execute(
                "INSERT INTO violation_codes (name, definition, created_by, created_at) VALUES (?,?,?,?)",
                (c["name"], c.get("definition", ""), created_by, _now()),
            )
            added += 1
        except sqlite3.IntegrityError:
            skipped += 1
    con.commit()
    con.close()
    return added, skipped


def delete_code(name: str) -> None:
    con = _conn()
    con.execute("DELETE FROM violation_codes WHERE name = ?", (name,))
    con.commit()
    con.close()


# ── Data helpers ───────────────────────────────────────────────────────────────

@st.cache_data
def load_items() -> dict[int, dict]:
    if not SAMPLE_CSV.exists():
        return {}
    with SAMPLE_CSV.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return {int(r["pilot_item_id"]): r for r in rows}


def group_by_item(reviews: list[dict]) -> dict[int, dict[str, dict]]:
    """Returns {item_id: {coder_id: review_dict}}."""
    grouped: dict[int, dict[str, dict]] = defaultdict(dict)
    for r in reviews:
        grouped[r["pilot_item_id"]][r["coder_id"]] = r
    return dict(grouped)


def find_disagreements(
    grouped: dict[int, dict[str, dict]],
    exclude_skip: bool = True,
) -> list[int]:
    """Item ids where ≥2 non-skip coders hold different decisions."""
    result = []
    for item_id, coder_map in sorted(grouped.items()):
        decisions = {
            c: r["decision"]
            for c, r in coder_map.items()
            if not exclude_skip or r["decision"] != "skip"
        }
        if len(decisions) >= 2 and len(set(decisions.values())) > 1:
            result.append(item_id)
    return result


def classify_split(coder_map: dict[str, dict], exclude_skip: bool = True) -> str:
    """Returns '3v1', '2v2', 'Xv0' (unanimous), or 'other'."""
    decisions = [
        r["decision"] for r in coder_map.values()
        if not exclude_skip or r["decision"] != "skip"
    ]
    if len(decisions) < 2:
        return "other"
    counts = Counter(decisions)
    top = counts.most_common()
    if len(top) == 1:
        return f"{top[0][1]}v0"
    if top[0][1] == 3 and top[1][1] == 1:
        return "3v1"
    if top[0][1] == 2 and top[1][1] == 2:
        return "2v2"
    return "other"


def find_code_conflicts(
    grouped: dict[int, dict[str, dict]],
    exclude_skip: bool = True,
) -> list[int]:
    """Items where all non-skip coders agree on non_compliant but use different code sets."""
    result = []
    for item_id, coder_map in sorted(grouped.items()):
        entries = [
            r for r in coder_map.values()
            if not exclude_skip or r["decision"] != "skip"
        ]
        if len(entries) < 2:
            continue
        if {r["decision"] for r in entries} != {"non_compliant"}:
            continue
        code_sets = [frozenset(json.loads(r.get("violation_codes") or "[]")) for r in entries]
        if len(set(code_sets)) > 1:
            result.append(item_id)
    return result


def _irr_subset(
    grouped: dict[int, dict[str, dict]],
    item_ids: set[int],
    exclude_skip: bool,
) -> tuple[float | None, float | None, int]:
    """Mean pairwise κ and Krippendorff's α for an item subset."""
    sub = {i: grouped[i] for i in item_ids if i in grouped}
    if not sub:
        return None, None, 0
    kappas = []
    for ca, cb in combinations(CODERS, 2):
        shared = [
            i for i, cm in sub.items()
            if ca in cm and cb in cm
            and (not exclude_skip or (
                cm[ca]["decision"] != "skip" and cm[cb]["decision"] != "skip"
            ))
        ]
        if not shared:
            continue
        ra = [sub[i][ca]["decision"] for i in shared]
        rb = [sub[i][cb]["decision"] for i in shared]
        k, _ = cohen_kappa(ra, rb)
        if k is not None:
            kappas.append(k)
    mean_k = sum(kappas) / len(kappas) if kappas else None
    alpha = krippendorff_alpha_nominal(sub, exclude_skip=exclude_skip)
    return mean_k, alpha, len(sub)


# ── IRR ───────────────────────────────────────────────────────────────────────

def cohen_kappa(ratings_a: list[str], ratings_b: list[str]) -> tuple[float | None, int]:
    """Pairwise Cohen's kappa. Returns (kappa, n_pairs)."""
    n = len(ratings_a)
    if n == 0:
        return None, 0
    po = sum(a == b for a, b in zip(ratings_a, ratings_b)) / n
    cats = set(ratings_a) | set(ratings_b)
    pe = sum((ratings_a.count(c) / n) * (ratings_b.count(c) / n) for c in cats)
    if 1 - pe < 1e-10:
        return 1.0, n
    return (po - pe) / (1 - pe), n


def krippendorff_alpha_nominal(
    grouped: dict[int, dict[str, dict]],
    exclude_skip: bool = True,
) -> float | None:
    """Krippendorff's alpha (nominal) across all raters and items."""
    value_counts: Counter = Counter()
    D_o_num = 0.0
    n_units = 0

    for coder_map in grouped.values():
        vals = [
            r["decision"] for r in coder_map.values()
            if not exclude_skip or r["decision"] != "skip"
        ]
        mu = len(vals)
        if mu < 2:
            continue
        n_units += 1
        disagree_pairs = sum(
            1 for i in range(mu) for j in range(i + 1, mu) if vals[i] != vals[j]
        )
        D_o_num += disagree_pairs / (mu - 1)
        for v in vals:
            value_counts[v] += 1

    if n_units == 0:
        return None

    D_o = D_o_num / n_units
    total = sum(value_counts.values())
    if total < 2:
        return None

    D_e = sum(
        value_counts[a] * value_counts[b]
        for a in value_counts
        for b in value_counts
        if a != b
    ) / (total * (total - 1))

    if D_e < 1e-10:
        return 1.0
    return 1 - D_o / D_e


# ── Tabs ──────────────────────────────────────────────────────────────────────

def tab_progress(reviews: list[dict], items: dict[int, dict]) -> None:
    st.markdown("### Team progress")
    total = len(items)
    if not total:
        st.info("Sample CSV not found.")
        return
    if not reviews:
        st.info("No coding done yet.")
        return

    counts_by_coder: dict[str, Counter] = defaultdict(Counter)
    for r in reviews:
        counts_by_coder[r["coder_id"]][r["decision"]] += 1

    for coder in CODERS:
        counts = counts_by_coder.get(coder, Counter())
        done = sum(counts.values())
        c1, c2, c3, c4, c5 = st.columns([2, 5, 1, 1, 1])
        c1.write(f"**{coder}**")
        c2.progress(done / total if total else 0)
        c3.caption(f"{done}/{total}")
        c4.caption(f"✓ {counts.get('compliant', 0)}")
        c5.caption(f"✗ {counts.get('non_compliant', 0)}")

    st.divider()
    total_done = len(reviews)
    max_possible = len(CODERS) * total
    col1, col2 = st.columns(2)
    col1.metric("Total annotations", f"{total_done} / {max_possible}")
    active_coders = len(set(r["coder_id"] for r in reviews))
    col2.metric("Coders active", f"{active_coders} / {len(CODERS)}")


def tab_irr(
    reviews: list[dict],
    grouped: dict[int, dict[str, dict]],
    items: dict[int, dict],
) -> None:
    st.markdown("### Inter-rater reliability")

    if not reviews:
        st.info("No coding data yet.")
        return

    exclude_skip = st.checkbox("Exclude skipped items from IRR", value=True)

    # Pairwise kappa for each coder pair
    pairs = list(combinations(CODERS, 2))
    results = []
    for ca, cb in pairs:
        shared = [
            iid for iid, cmap in grouped.items()
            if ca in cmap and cb in cmap
            and (not exclude_skip or (
                cmap[ca]["decision"] != "skip" and cmap[cb]["decision"] != "skip"
            ))
        ]
        if not shared:
            results.append({"pair": f"{ca} / {cb}", "kappa": None, "po": None, "n": 0})
            continue
        ra = [grouped[i][ca]["decision"] for i in shared]
        rb = [grouped[i][cb]["decision"] for i in shared]
        kappa, n = cohen_kappa(ra, rb)
        po = sum(a == b for a, b in zip(ra, rb)) / n if n else None
        results.append({"pair": f"{ca} / {cb}", "kappa": kappa, "po": po, "n": n})

    st.markdown("**Pairwise Cohen's κ**")
    h1, h2, h3, h4 = st.columns([3, 2, 2, 2])
    h1.markdown("**Pair**"); h2.markdown("**κ**"); h3.markdown("**% agree**"); h4.markdown("**n**")

    for r in results:
        c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
        c1.write(r["pair"])
        if r["kappa"] is None:
            c2.caption("—"); c3.caption("—")
        else:
            k = r["kappa"]
            color = "green" if k >= 0.6 else ("orange" if k >= 0.4 else "red")
            c2.markdown(f":{color}[**{k:.3f}**]")
            c3.write(f"{r['po'] * 100:.1f}%")
        c4.write(str(r["n"]))

    st.divider()
    alpha = krippendorff_alpha_nominal(grouped, exclude_skip=exclude_skip)
    if alpha is not None:
        color = "green" if alpha >= 0.8 else ("orange" if alpha >= 0.67 else "red")
        st.markdown(
            f"**Krippendorff's α** (nominal, all raters): :{color}[**{alpha:.3f}**]"
        )
        st.caption("α ≥ 0.80 good · 0.67–0.80 tentative · < 0.67 problematic  _(Krippendorff 2004)_")
    else:
        st.info("Not enough overlapping ratings to compute α.")

    st.divider()
    st.markdown("**Decision distribution per coder**")
    for coder in CODERS:
        coder_reviews = [r for r in reviews if r["coder_id"] == coder]
        if not coder_reviews:
            continue
        counts = Counter(r["decision"] for r in coder_reviews)
        n = len(coder_reviews)
        st.caption(
            f"**{coder}** ({n}):  "
            + "  ·  ".join(
                f"{DECISION_LABELS.get(d, d)} {cnt} ({cnt / n * 100:.0f}%)"
                for d, cnt in sorted(counts.items())
            )
        )

    # ── Breakdown by product ───────────────────────────────────────────────────
    if items:
        st.divider()
        st.markdown("**IRR breakdown by product**")

        def _kappa_color(k: float | None) -> str:
            if k is None: return "gray"
            return "green" if k >= 0.6 else ("orange" if k >= 0.4 else "red")

        products = sorted({v["product_id"] for v in items.values() if v.get("product_id")})
        hc = st.columns([3, 2, 2, 2])
        hc[0].markdown("**Product**"); hc[1].markdown("**mean κ**")
        hc[2].markdown("**α**"); hc[3].markdown("**n items**")
        for product in products:
            ids = {i for i, v in items.items() if v.get("product_id") == product}
            mk, alpha, n = _irr_subset(grouped, ids, exclude_skip)
            rc = st.columns([3, 2, 2, 2])
            rc[0].write(product.replace("_", " ").title())
            if mk is not None:
                rc[1].markdown(f":{_kappa_color(mk)}[**{mk:.3f}**]")
            else:
                rc[1].caption("—")
            if alpha is not None:
                rc[2].markdown(f":{_kappa_color(alpha)}[**{alpha:.3f}**]")
            else:
                rc[2].caption("—")
            rc[3].write(str(n))

        # ── Breakdown by material type ─────────────────────────────────────────
        st.divider()
        st.markdown("**IRR breakdown by material type**")
        materials = sorted({v["material_type"] for v in items.values() if v.get("material_type")})
        hm = st.columns([3, 2, 2, 2])
        hm[0].markdown("**Material**"); hm[1].markdown("**mean κ**")
        hm[2].markdown("**α**"); hm[3].markdown("**n items**")
        for mat in materials:
            ids = {i for i, v in items.items() if v.get("material_type") == mat}
            mk, alpha, n = _irr_subset(grouped, ids, exclude_skip)
            rm = st.columns([3, 2, 2, 2])
            label = mat.replace(".j2", "").replace("_", " ").title()
            rm[0].write(label)
            if mk is not None:
                rm[1].markdown(f":{_kappa_color(mk)}[**{mk:.3f}**]")
            else:
                rm[1].caption("—")
            if alpha is not None:
                rm[2].markdown(f":{_kappa_color(alpha)}[**{alpha:.3f}**]")
            else:
                rm[2].caption("—")
            rm[3].write(str(n))


def tab_disagreements(
    grouped: dict[int, dict[str, dict]],
    items: dict[int, dict],
    gold: dict[int, dict],
) -> None:
    st.markdown("### Disagreements")

    if not grouped:
        st.info("No coding data yet.")
        return

    exclude_skip = st.checkbox("Exclude skipped items", value=True, key="disag_excl")
    disag_ids = find_disagreements(grouped, exclude_skip=exclude_skip)

    if not disag_ids:
        st.success("No disagreements — all coders agree on all coded items.")
        return

    adjudicated = sum(1 for i in disag_ids if i in gold)
    st.caption(f"{len(disag_ids)} items with ≥1 disagreement · {adjudicated} adjudicated")

    for item_id in disag_ids:
        coder_map = grouped[item_id]
        item_info = items.get(item_id, {})
        gold_entry = gold.get(item_id)

        split = classify_split(coder_map, exclude_skip=exclude_skip)
        split_badge = {"3v1": " · 🟡 3v1", "2v2": " · 🔴 2v2"}.get(split, "")

        header = f"Item {item_id}{split_badge}"
        if item_info.get("product_id"):
            header += f"  ·  {item_info['product_id']}"
        if gold_entry:
            lbl = DECISION_LABELS.get(gold_entry["decision"], gold_entry["decision"])
            header += f"  ·  Gold: {lbl} ✓"

        with st.expander(header):
            if item_info.get("output_text"):
                st.text_area(
                    "output",
                    value=item_info["output_text"].strip(),
                    height=160,
                    disabled=True,
                    label_visibility="collapsed",
                    key=f"dt_{item_id}",
                )

            coders_here = [c for c in CODERS if c in coder_map]
            cols = st.columns(len(coders_here)) if coders_here else []
            for col, coder in zip(cols, coders_here):
                r = coder_map[coder]
                dec = r["decision"]
                color = DECISION_COLORS.get(dec, "gray")
                col.markdown(f"**{coder}**")
                col.markdown(f":{color}[{DECISION_LABELS.get(dec, dec)}]")
                codes = json.loads(r.get("violation_codes") or "[]")
                if codes:
                    col.caption("Codes: " + ", ".join(codes))
                if r.get("notes"):
                    col.caption(f'Notes: "{r["notes"]}"')
                if r.get("skip_reason"):
                    col.caption(f'Skip: "{r["skip_reason"]}"')

            if gold_entry:
                st.divider()
                gc = gold_entry["decision"]
                gcol = DECISION_COLORS.get(gc, "gray")
                gcodes = json.loads(gold_entry.get("violation_codes") or "[]")
                st.markdown(
                    f"**Gold ({gold_entry['adjudicator']}):** "
                    f":{gcol}[{DECISION_LABELS.get(gc, gc)}]"
                    + (f"  ·  {', '.join(gcodes)}" if gcodes else "")
                )
                if gold_entry.get("notes"):
                    st.caption(f'Gold notes: "{gold_entry["notes"]}"')


    # ── Code conflicts (unanimous non-compliant, different codes) ─────────────
    st.divider()
    st.markdown("### Code conflicts — unanimous verdict, different codes")
    st.caption("All coders agree the item is non-compliant but assign different violation codes.")

    conflict_ids = find_code_conflicts(grouped, exclude_skip=exclude_skip)
    if not conflict_ids:
        st.success("No code conflicts — coders agree on codes wherever they agree on verdict.")
    else:
        st.caption(f"{len(conflict_ids)} item(s) with code disagreement")
        for item_id in conflict_ids:
            coder_map = grouped[item_id]
            item_info = items.get(item_id, {})
            with st.expander(f"Item {item_id}  ·  {item_info.get('product_id', '')}"):
                coders_here = [c for c in CODERS if c in coder_map]
                cols = st.columns(len(coders_here)) if coders_here else []
                all_code_sets = []
                for col, coder in zip(cols, coders_here):
                    r = coder_map[coder]
                    codes = json.loads(r.get("violation_codes") or "[]")
                    all_code_sets.append(set(codes))
                    col.markdown(f"**{coder}**")
                    for code in codes:
                        col.caption(f"• {code}")
                    if not codes:
                        col.caption("_(no codes)_")
                    if r.get("notes"):
                        col.caption(f'Notes: "{r["notes"]}"')
                # Show union and intersection
                if all_code_sets:
                    union = set.union(*all_code_sets)
                    intersection = set.intersection(*all_code_sets)
                    st.divider()
                    c1, c2 = st.columns(2)
                    c1.markdown("**All codes used (union)**")
                    for code in sorted(union):
                        c1.caption(f"• {code}")
                    c2.markdown("**Codes all coders agree on (intersection)**")
                    if intersection:
                        for code in sorted(intersection):
                            c2.caption(f"• {code}")
                    else:
                        c2.caption("_(none — full disagreement on codes)_")


def tab_adjudication(
    grouped: dict[int, dict[str, dict]],
    items: dict[int, dict],
    gold: dict[int, dict],
    code_names: list[str],
) -> None:
    st.markdown("### Adjudication")
    st.caption("Set a gold-standard decision for disagreed items — saved to the DB for export.")

    if not grouped:
        st.info("No coding data yet.")
        return

    exclude_skip = st.checkbox("Exclude skipped items", value=True, key="adj_excl")
    disag_ids = find_disagreements(grouped, exclude_skip=exclude_skip)

    if not disag_ids:
        st.success("No disagreements to adjudicate.")
        return

    # Classify splits
    splits = {i: classify_split(grouped[i], exclude_skip=exclude_skip) for i in disag_ids}
    ids_3v1 = [i for i in disag_ids if splits[i] == "3v1"]
    ids_2v2 = [i for i in disag_ids if splits[i] == "2v2"]
    done_count = sum(1 for i in disag_ids if i in gold)

    # Summary metrics
    mc1, mc2, mc3 = st.columns(3)
    mc1.metric("Total disagreements", len(disag_ids))
    mc2.metric("🟡 3v1 — auto-resolvable", len(ids_3v1))
    mc3.metric("🔴 2v2 — needs review", len(ids_2v2))
    st.caption(f"{done_count}/{len(disag_ids)} adjudicated")

    # Auto-resolve 3v1 items
    pending_3v1 = [i for i in ids_3v1 if i not in gold]
    if pending_3v1:
        st.divider()
        st.markdown("**Auto-resolve 3v1 items**")
        st.caption(
            f"{len(pending_3v1)} items where 3 coders agree — majority vote is applied automatically. "
            "Codes are the union of all majority coders' code sets. You can still override individually below."
        )
        if st.button(f"Auto-resolve all {len(pending_3v1)} pending 3v1 items", key="auto_3v1"):
            for iid in pending_3v1:
                cmap = grouped[iid]
                entries = [
                    r for r in cmap.values()
                    if not exclude_skip or r["decision"] != "skip"
                ]
                decisions = [r["decision"] for r in entries]
                majority_dec = Counter(decisions).most_common(1)[0][0]
                majority_entries = [r for r in entries if r["decision"] == majority_dec]
                union_codes = sorted(set(
                    c for r in majority_entries
                    for c in json.loads(r.get("violation_codes") or "[]")
                ))
                save_gold(iid, majority_dec, union_codes, "Auto-resolved: 3v1 majority vote.", "auto_majority")
            st.success(f"Auto-resolved {len(pending_3v1)} items.")
            st.rerun()

    st.divider()
    st.markdown("**Manual adjudication**")
    show_all = st.checkbox("Show all disagreements (default: 2v2 first)", value=False, key="adj_show_all")
    if show_all:
        ordered_ids = ids_2v2 + ids_3v1 + [i for i in disag_ids if splits[i] not in ("2v2", "3v1")]
    else:
        ordered_ids = ids_2v2 if ids_2v2 else disag_ids

    if not ordered_ids:
        st.info("No items to show for current filter.")
        return

    item_id = st.selectbox(
        "Item to adjudicate",
        options=ordered_ids,
        format_func=lambda i: f"Item {i}  [{splits.get(i, '')}]" + (" ✓" if i in gold else ""),
        key="adj_sel",
    )
    if item_id is None:
        return

    coder_map = grouped.get(item_id, {})
    item_info = items.get(item_id, {})
    gold_entry = gold.get(item_id)

    if item_info.get("output_text"):
        st.text_area(
            "output",
            value=item_info["output_text"].strip(),
            height=200,
            disabled=True,
            label_visibility="collapsed",
            key=f"adj_txt_{item_id}",
        )

    coders_here = [c for c in CODERS if c in coder_map]
    if coders_here:
        cols = st.columns(len(coders_here))
        for col, coder in zip(cols, coders_here):
            r = coder_map[coder]
            dec = r["decision"]
            color = DECISION_COLORS.get(dec, "gray")
            col.markdown(f"**{coder}**")
            col.markdown(f":{color}[{DECISION_LABELS.get(dec, dec)}]")
            codes = json.loads(r.get("violation_codes") or "[]")
            if codes:
                col.caption(", ".join(codes))
            if r.get("notes"):
                col.caption(f'"{r["notes"]}"')

    st.divider()
    st.markdown("**Gold decision**")

    adjudicator = st.selectbox("Adjudicator", options=CODERS, key=f"adj_who_{item_id}")

    dec_opts = {"compliant": "✓ Compliant", "non_compliant": "✗ Non-compliant"}
    current_dec = gold_entry["decision"] if gold_entry and gold_entry["decision"] in dec_opts else "compliant"
    g_decision = st.radio(
        "Decision",
        options=list(dec_opts.keys()),
        format_func=lambda x: dec_opts[x],
        index=list(dec_opts.keys()).index(current_dec),
        horizontal=True,
        key=f"adj_dec_{item_id}",
    )

    current_codes = json.loads(gold_entry.get("violation_codes") or "[]") if gold_entry else []
    g_codes = st.multiselect(
        "Violation codes",
        options=code_names,
        default=[c for c in current_codes if c in code_names],
        key=f"adj_codes_{item_id}",
    )

    g_notes = st.text_area(
        "Notes",
        value=gold_entry.get("notes", "") if gold_entry else "",
        height=80,
        key=f"adj_notes_{item_id}",
    )

    if st.button("Save gold decision", type="primary", key=f"adj_save_{item_id}"):
        save_gold(item_id, g_decision, g_codes, g_notes, adjudicator)
        st.success(f"Gold decision saved for item {item_id}.")
        st.rerun()


# ── Setup tab ─────────────────────────────────────────────────────────────────

def tab_setup() -> None:
    st.markdown("### Codebook setup")
    st.caption(
        "Choose how to start the codebook before coders begin. "
        "You can mix both options — add the starter set first, then edit freely."
    )

    existing = load_all_codes_full()
    n_existing = len(existing)

    # ── Option A: clean slate ─────────────────────────────────────────────────
    with st.expander(
        f"**Option A — Clean slate** _(start with 0 codes; coders build the codebook as they go)_",
        expanded=(n_existing == 0),
    ):
        st.markdown(
            "Coders encounter items cold and add codes inline whenever they spot a new violation type. "
            "Best when you want to discover categories bottom-up without anchoring on pre-defined labels."
        )
        if n_existing == 0:
            st.success("Codebook is currently empty — Option A is active.")
        else:
            st.info(f"Codebook has **{n_existing} code(s)** already. Delete them below if you want a clean slate.")
        if n_existing > 0:
            if st.button("⚠️ Clear entire codebook", key="clear_all", type="secondary"):
                if st.session_state.get("_confirm_clear"):
                    for c in existing:
                        delete_code(c["name"])
                    st.session_state._confirm_clear = False
                    st.success("Codebook cleared.")
                    st.rerun()
                else:
                    st.session_state._confirm_clear = True
                    st.warning("Click again to confirm — this deletes all codes from the DB.")

    # ── Option B: pre-seeded starter set ──────────────────────────────────────
    with st.expander(
        f"**Option B — Pre-seeded starter codebook** _(load {len(STARTER_CODES)} violation codes — codebook v1)_",
        expanded=(n_existing == 0),
    ):
        st.markdown(
            "Load a curated set of 6 violation types derived from regulatory literature "
            "and the test coding session. Coders still add/edit codes during coding. "
            "Best when you want anchoring labels to reduce early-session drift."
        )
        st.markdown("**Proposed starter codes:**")
        for c in STARTER_CODES:
            already = any(e["name"] == c["name"] for e in existing)
            badge = " ✓ _already in DB_" if already else ""
            st.markdown(f"- **`{c['name']}`**{badge}  \n  {c['definition']}")

        seeder = st.selectbox(
            "Add as (your name)",
            options=CODERS,
            key="seed_as",
        )
        if st.button("Load starter codebook", type="primary", key="seed_btn"):
            added, skipped = seed_codes(STARTER_CODES, created_by=seeder)
            if added:
                st.success(f"Added {added} code(s). {skipped} already existed — skipped.")
            else:
                st.info("All starter codes already in the codebook.")
            st.rerun()

    # ── Current codebook ──────────────────────────────────────────────────────
    st.divider()
    existing = load_all_codes_full()  # reload after any changes
    st.markdown(f"**Current codebook — {len(existing)} code(s)**")
    if not existing:
        st.caption("Empty. Coders will build it from scratch.")
    else:
        for c in existing:
            row_l, row_r = st.columns([10, 1])
            author = f" _(by {c['created_by']})_" if c["created_by"] else ""
            row_l.markdown(f"**`{c['name']}`**{author}")
            if c["definition"]:
                row_l.caption(c["definition"])
            if row_r.button("×", key=f"setup_del_{c['name']}", help=f"Remove {c['name']}"):
                delete_code(c["name"])
                st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="Pilot Analysis",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    if not DB_PATH.exists():
        st.error(f"DB not found: `{DB_PATH}`. Run the coding app first to create it.")
        return

    init_gold_table()

    reviews = load_all_reviews()
    items = load_items()
    grouped = group_by_item(reviews)
    gold = load_gold()
    code_names = load_code_names()

    if "test" in SAMPLE_CSV.stem:
        st.warning(f"TEST MODE — {SAMPLE_CSV.name} / {DB_PATH.name}")

    n_coders = len(set(r["coder_id"] for r in reviews))
    st.title("📊 Pilot Analysis")
    st.caption(
        f"DB: `{DB_PATH}`  ·  {len(reviews)} annotations  ·  "
        f"{n_coders}/{len(CODERS)} coders active  ·  {len(items)} items"
    )

    t0, t1, t2, t3, t4 = st.tabs(["Setup", "Progress", "IRR", "Disagreements", "Adjudication"])
    with t0:
        tab_setup()
    with t1:
        tab_progress(reviews, items)
    with t2:
        tab_irr(reviews, grouped, items)
    with t3:
        tab_disagreements(grouped, items, gold)
    with t4:
        tab_adjudication(grouped, items, gold, code_names)


if __name__ == "__main__":
    main()
