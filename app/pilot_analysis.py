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

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False

try:
    from pilot_coding import _auto_check
    _AUTO_CHECK_AVAILABLE = True
except Exception:
    _AUTO_CHECK_AVAILABLE = False

try:
    from machine_audit import (
        run_gpt4o_audit,
        run_roberta_audit,
        compute_kappa_vs_gold,
        compute_f1_vs_gold,
        load_existing,
        GPT4O_CSV,
        ROBERTA_CSV,
    )
    _MACHINE_AUDIT_AVAILABLE = True
except Exception:
    _MACHINE_AUDIT_AVAILABLE = False

COMPLIANCE_DIR = Path("data/compliance")

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


def compute_per_code_irr(
    grouped: dict[int, dict[str, dict]],
    code_names: list[str],
    exclude_skip: bool = True,
) -> list[dict]:
    """Krippendorff's α and mean pairwise κ for each violation code (binary: applied yes/no)."""
    item_ids = sorted(grouped.keys())
    results = []
    for code in code_names:
        units = []
        for iid in item_ids:
            cm = grouped[iid]
            vals = []
            for c in CODERS:
                if c not in cm:
                    continue
                r = cm[c]
                if exclude_skip and r["decision"] == "skip":
                    continue
                codes_set = set(json.loads(r.get("violation_codes") or "[]"))
                vals.append(1 if code in codes_set else 0)
            units.append(vals)

        # Krippendorff's α (nominal, binary)
        value_counts: Counter = Counter()
        D_o_num = 0.0
        n_units_k = 0
        for vals in units:
            mu = len(vals)
            if mu < 2:
                continue
            n_units_k += 1
            disagree = sum(1 for i in range(mu) for j in range(i + 1, mu) if vals[i] != vals[j])
            D_o_num += disagree / (mu - 1)
            for v in vals:
                value_counts[v] += 1

        alpha = None
        if n_units_k > 0:
            D_o = D_o_num / n_units_k
            total = sum(value_counts.values())
            if total >= 2:
                D_e = sum(
                    value_counts[a] * value_counts[b]
                    for a in value_counts for b in value_counts if a != b
                ) / (total * (total - 1))
                alpha = 1.0 if D_e < 1e-10 else 1 - D_o / D_e

        # Mean pairwise κ
        pair_ks = []
        for ca, cb in combinations(CODERS, 2):
            ra, rb = [], []
            for iid in item_ids:
                if ca not in grouped[iid] or cb not in grouped[iid]:
                    continue
                if exclude_skip and (
                    grouped[iid][ca]["decision"] == "skip"
                    or grouped[iid][cb]["decision"] == "skip"
                ):
                    continue
                ca_codes = set(json.loads(grouped[iid][ca].get("violation_codes") or "[]"))
                cb_codes = set(json.loads(grouped[iid][cb].get("violation_codes") or "[]"))
                ra.append(1 if code in ca_codes else 0)
                rb.append(1 if code in cb_codes else 0)
            k, _ = cohen_kappa(ra, rb)
            if k is not None:
                pair_ks.append(k)
        mean_k = sum(pair_ks) / len(pair_ks) if pair_ks else None

        n_pos = sum(
            1 for iid in item_ids for c in CODERS
            if c in grouped[iid]
            and code in set(json.loads(grouped[iid][c].get("violation_codes") or "[]"))
        )
        total_ratings = sum(sum(1 for c in CODERS if c in grouped[iid]) for iid in item_ids)
        prev_pct = n_pos / total_ratings * 100 if total_ratings > 0 else 0.0

        results.append({
            "code": code, "alpha": alpha, "mean_k": mean_k,
            "prevalence_pct": prev_pct, "n_pos": n_pos,
        })

    results.sort(key=lambda x: (x["alpha"] is None, -(x["alpha"] or 0)))
    return results


def compute_item_consensus(
    grouped: dict[int, dict[str, dict]], exclude_skip: bool = True
) -> dict:
    """Unanimous-compliant, unanimous-non-compliant, split, ≥1-flagged counts."""
    uc = unc = split = at_least_one = 0
    for cm in grouped.values():
        decs = [r["decision"] for r in cm.values()
                if not exclude_skip or r["decision"] != "skip"]
        if not decs:
            continue
        unique = set(decs)
        if "non_compliant" in decs:
            at_least_one += 1
        if unique == {"compliant"}:
            uc += 1
        elif unique == {"non_compliant"}:
            unc += 1
        else:
            split += 1
    return {
        "unanimous_compliant": uc,
        "unanimous_non_compliant": unc,
        "split": split,
        "at_least_one_nc": at_least_one,
        "total": len(grouped),
    }


def compute_violation_freq(
    grouped: dict[int, dict[str, dict]],
    exclude_skip: bool = True,
    unanimous_only: bool = False,
) -> list[tuple[str, int]]:
    """Sorted (code, count) list from all annotations or unanimous-NC items only."""
    counts: Counter = Counter()
    for iid, cm in grouped.items():
        entries = [r for r in cm.values()
                   if not exclude_skip or r["decision"] != "skip"]
        if unanimous_only:
            if {r["decision"] for r in entries} != {"non_compliant"}:
                continue
        for r in entries:
            for code in json.loads(r.get("violation_codes") or "[]"):
                counts[code] += 1
    return counts.most_common()


# ── Tabs ──────────────────────────────────────────────────────────────────────

def tab_progress(reviews: list[dict], grouped: dict[int, dict[str, dict]], items: dict[int, dict]) -> None:
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

    # ── Item-level consensus ───────────────────────────────────────────────────
    st.divider()
    st.markdown("### Item-level consensus")
    consensus = compute_item_consensus(grouped)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("≥1 coder flagged NC", f"{consensus['at_least_one_nc']} / {consensus['total']}")
    m2.metric("Unanimous non-compliant", str(consensus["unanimous_non_compliant"]))
    m3.metric("Unanimous compliant", str(consensus["unanimous_compliant"]))
    m4.metric("Split (any disagreement)", str(consensus["split"]))
    st.caption(
        f"Only **{consensus['unanimous_compliant']}** items were unanimously judged compliant by all coders. "
        f"**{consensus['at_least_one_nc']}** items received at least one non-compliant flag."
    )

    # ── Violation frequency ────────────────────────────────────────────────────
    st.divider()
    st.markdown("### Violation code frequency")
    show_unc_only = st.checkbox(
        "Unanimous non-compliant items only (highest confidence)", value=False, key="vf_unc"
    )
    freq = compute_violation_freq(grouped, unanimous_only=show_unc_only)
    if not freq:
        st.info("No violation codes recorded yet.")
    else:
        total_ratings = sum(
            sum(1 for c in CODERS if c in grouped[iid]) for iid in grouped
        )
        h1, h2, h3 = st.columns([5, 2, 2])
        h1.markdown("**Code**"); h2.markdown("**Count**"); h3.markdown("**% of ratings**")
        for code, count in freq:
            c1, c2, c3 = st.columns([5, 2, 2])
            c1.write(code)
            c2.write(str(count))
            c3.write(f"{count / total_ratings * 100:.1f}%")


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

    # ── Per-code IRR ──────────────────────────────────────────────────────────
    st.divider()
    st.markdown("**Per-code IRR** _(binary: code applied yes/no)_")
    st.caption(
        "Each row shows how reliably coders agree on whether a specific violation code applies. "
        "α ≥ 0.67 is acceptable; negative α means agreement worse than chance (concept drift)."
    )
    code_names = load_code_names()
    per_code = compute_per_code_irr(grouped, code_names, exclude_skip=exclude_skip)

    # Filter out zero-prevalence codes (trivially perfect — nobody used them)
    per_code_active = [r for r in per_code if r["n_pos"] > 0]
    per_code_unused = [r for r in per_code if r["n_pos"] == 0]

    ph1, ph2, ph3, ph4, ph5 = st.columns([4, 2, 2, 2, 2])
    ph1.markdown("**Code**"); ph2.markdown("**α**"); ph3.markdown("**mean κ**")
    ph4.markdown("**usage**"); ph5.markdown("**n flags**")

    def _ac(val: float | None) -> str:
        if val is None: return "gray"
        return "green" if val >= 0.67 else ("orange" if val >= 0.4 else "red")

    for row in per_code_active:
        c1, c2, c3, c4, c5 = st.columns([4, 2, 2, 2, 2])
        c1.write(row["code"])
        if row["alpha"] is not None:
            c2.markdown(f":{_ac(row['alpha'])}[**{row['alpha']:+.3f}**]")
        else:
            c2.caption("—")
        if row["mean_k"] is not None:
            c3.markdown(f":{_ac(row['mean_k'])}[**{row['mean_k']:+.3f}**]")
        else:
            c3.caption("—")
        c4.write(f"{row['prevalence_pct']:.1f}%")
        c5.write(str(row["n_pos"]))

    if per_code_unused:
        with st.expander(f"{len(per_code_unused)} unused codes (α = 1.0 trivially — never applied)"):
            for row in per_code_unused:
                st.caption(f"• {row['code']}")


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

    # ── Fix Missing Codes ─────────────────────────────────────────────────────
    V_CODES = ["V1", "V2", "V3", "V4", "V5"]
    V_LABELS = {
        "V1": "V1 — Factual inaccuracy / hallucinated spec",
        "V2": "V2 — Missing required disclosure",
        "V3": "V3 — Unauthorized health or performance claim",
        "V4": "V4 — Fabricated testimonial / urgency cue",
        "V5": "V5 — Format / prompt artifact violation",
    }
    ghost_ids = sorted([
        iid for iid, g in gold.items()
        if g.get("decision") == "non_compliant"
        and not json.loads(g.get("violation_codes") or "[]")
    ])
    if ghost_ids:
        pending_ghosts = len(ghost_ids)
        with st.expander(
            f"⚠️ Fix Missing Violation Codes — {pending_ghosts} NC items have no codes recorded",
            expanded=pending_ghosts > 0,
        ):
            st.caption(
                "These items were adjudicated as NON_COMPLIANT but no violation codes were saved. "
                "Select V1–V5 codes and save each item. Uses the same unified codes as the machine auditors."
            )
            ghost_sel = st.selectbox(
                "Item",
                options=ghost_ids,
                format_func=lambda i: (
                    f"Item {i} | {items.get(i, {}).get('product_id', '')} | "
                    f"{items.get(i, {}).get('material_type', '')}"
                ),
                key="ghost_sel",
            )
            if ghost_sel is not None:
                g_item = items.get(ghost_sel, {})
                g_coder_map = grouped.get(ghost_sel, {})

                if g_item.get("output_text"):
                    st.text_area(
                        "Output",
                        value=g_item["output_text"].strip(),
                        height=180,
                        disabled=True,
                        key=f"ghost_txt_{ghost_sel}",
                    )

                # Show what coders originally said
                coders_here = [c for c in CODERS if c in g_coder_map]
                if coders_here:
                    cols = st.columns(len(coders_here))
                    for col, coder in zip(cols, coders_here):
                        r = g_coder_map[coder]
                        dec = r["decision"]
                        color = DECISION_COLORS.get(dec, "gray")
                        col.markdown(f"**{coder}**")
                        col.markdown(f":{color}[{DECISION_LABELS.get(dec, dec)}]")
                        old_codes = json.loads(r.get("violation_codes") or "[]")
                        if old_codes:
                            col.caption(", ".join(old_codes))

                ghost_codes = st.multiselect(
                    "Violation codes (V1–V5)",
                    options=V_CODES,
                    format_func=lambda v: V_LABELS.get(v, v),
                    key=f"ghost_codes_{ghost_sel}",
                )
                ghost_notes = st.text_input(
                    "Notes (optional)",
                    key=f"ghost_notes_{ghost_sel}",
                )
                if st.button("Save codes", type="primary", key=f"ghost_save_{ghost_sel}"):
                    if not ghost_codes:
                        st.warning("Select at least one violation code before saving.")
                    else:
                        save_gold(ghost_sel, "non_compliant", ghost_codes, ghost_notes, "Dorota")
                        st.success(f"Saved: Item {ghost_sel} → {', '.join(ghost_codes)}")
                        st.rerun()
        st.divider()

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

    # Unadjudicated items first so the selectbox always opens on something pending
    pending_ids = [i for i in ordered_ids if i not in gold]
    done_ids = [i for i in ordered_ids if i in gold]
    ordered_ids = pending_ids + done_ids

    pending_remaining = len(pending_ids)
    st.caption(f"{pending_remaining} pending · {len(done_ids)} done")

    # Apply staged advance before the widget renders
    if "_adj_sel_next" in st.session_state and st.session_state["_adj_sel_next"] in ordered_ids:
        st.session_state["adj_sel"] = st.session_state.pop("_adj_sel_next")

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

    # ── Auto-check note ───────────────────────────────────────────────────────
    if _AUTO_CHECK_AVAILABLE and item_info.get("output_text") and item_info.get("product_id"):
        spec = None
        if _YAML_AVAILABLE:
            spec_path = COMPLIANCE_DIR / f"{item_info['product_id']}.yaml"
            if spec_path.exists():
                with spec_path.open(encoding="utf-8") as _f:
                    spec = yaml.safe_load(_f)
        flags = _auto_check(item_info["output_text"], item_info["product_id"], spec)
        st.divider()
        st.markdown("**Auto-check** _(spec-based factual flags)_")
        if not flags:
            st.success("No spec violations detected automatically.")
        else:
            for flag in flags:
                lvl = flag.get("level", "amber")
                icon = "🔴" if lvl == "red" else "🟡"
                msg = flag.get("message", "")
                ev = flag.get("evidence", "")
                code = flag.get("code", "")
                st.markdown(
                    f"{icon} **{msg}**"
                    + (f"  \n&nbsp;&nbsp;&nbsp;&nbsp;`{code}`" if code else "")
                    + (f"  \n&nbsp;&nbsp;&nbsp;&nbsp;_{ev}_" if ev else "")
                )

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
        # Stage advance to next unadjudicated item (applied before widget renders on rerun)
        next_pending = [i for i in ordered_ids if i not in gold and i != item_id]
        if next_pending:
            st.session_state["_adj_sel_next"] = next_pending[0]
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


# ── Machine Audit ─────────────────────────────────────────────────────────────

def _audit_summary(results: list[dict], gold: dict[int, dict]) -> dict:
    """NC rate, κ, precision, recall, F1 vs gold."""
    if not _MACHINE_AUDIT_AVAILABLE:
        return {}
    n = len(results)
    nc = sum(1 for r in results if r.get("decision") == "NON_COMPLIANT")
    nc_rate = f"{nc / n * 100:.0f}%" if n else "—"
    kappa, n_pairs = compute_kappa_vs_gold(results, gold)
    precision, recall, f1 = compute_f1_vs_gold(results, gold)
    return {
        "nc_rate": nc_rate,
        "kappa": f"{kappa:.3f}" if kappa is not None else "—",
        "f1": f"{f1:.3f}" if f1 is not None else "—",
        "n": n,
        "n_pairs": n_pairs,
    }


def _show_audit_results(results: list[dict], gold: dict[int, dict], label: str) -> None:
    """Display results table and metrics for one auditor."""
    if not results:
        return

    summary = _audit_summary(results, gold)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Items audited", summary.get("n", "—"))
    m2.metric("NC rate", summary.get("nc_rate", "—"))
    m3.metric("κ vs gold", summary.get("kappa", "—"))
    m4.metric("F1 vs gold", summary.get("f1", "—"))

    if summary.get("n_pairs"):
        st.caption(f"κ computed on {summary['n_pairs']} items with gold standard.")

    errors = [r for r in results if r.get("decision") == "ERROR"]
    if errors:
        st.warning(f"{len(errors)} item(s) returned ERROR — check API key and quota.")

    with st.expander(f"Full results table — {label} ({len(results)} items)"):
        h = st.columns([1, 2, 2, 2, 1, 4])
        for col, hdr in zip(h, ["ID", "Product", "Decision", "Violations", "Conf.", "Rationale"]):
            col.markdown(f"**{hdr}**")
        for r in results:
            dec = r.get("decision", "")
            color = "green" if dec == "COMPLIANT" else ("red" if dec == "NON_COMPLIANT" else "gray")
            row = st.columns([1, 2, 2, 2, 1, 4])
            row[0].write(str(r.get("pilot_item_id", "")))
            row[1].write(r.get("product_id", "").replace("_", " "))
            row[2].markdown(f":{color}[{dec}]")
            row[3].write(r.get("violations", "") or "—")
            row[4].write(r.get("confidence", ""))
            row[5].caption(r.get("rationale", ""))


def tab_machine_audit(items: dict[int, dict], gold: dict[int, dict]) -> None:
    st.markdown("### Machine Audit — Round 2 Prompts")
    st.caption(
        "Re-runs GPT-4o and RoBERTa auditors with calibrated prompts and unified V1–V5 codes. "
        "Outputs saved to `outputs/compliance/round2_gpt4o.csv` and `round2_roberta.csv`. "
        "**`pilot_coding.db` is never modified.**"
    )

    if not _MACHINE_AUDIT_AVAILABLE:
        st.error(
            "`machine_audit.py` could not be imported. "
            "Ensure it is in the same directory as this app."
        )
        return

    if not os.environ.get("OPENAI_API_KEY"):
        st.warning("OPENAI_API_KEY environment variable not set — auditors will fail without it.")

    audit_items = [
        {
            "pilot_item_id": iid,
            "run_id": v.get("run_id", ""),
            "product_id": v.get("product_id", ""),
            "material_type": v.get("material_type", ""),
            "output_text": v.get("output_text", ""),
        }
        for iid, v in sorted(items.items())
        if v.get("output_text")
    ]

    if not audit_items:
        st.info("No items with output text found. Check PILOT_SAMPLE_CSV.")
        return

    st.caption(f"{len(audit_items)} items loaded for audit.")

    # ── GPT-4o Auditor ────────────────────────────────────────────────────────
    with st.expander("GPT-4o Auditor", expanded=True):
        run_btn = st.button("Run GPT-4o Auditor", key="run_gpt4o", type="primary")
        if GPT4O_CSV.exists():
            st.caption(f"Previous results: `{GPT4O_CSV.name}` exists")

        if run_btn:
            bar = st.progress(0.0, text="Starting GPT-4o Auditor…")
            def _gpt_cb(i: int, n: int) -> None:
                bar.progress((i + 1) / n, text=f"Item {i + 1}/{n}")
            with st.spinner("Running GPT-4o Auditor on 100 items (~2 min)…"):
                try:
                    res = run_gpt4o_audit(audit_items, progress_cb=_gpt_cb)
                    st.session_state["gpt4o_r2_results"] = res
                    bar.empty()
                    st.success(f"Done — {len(res)} items. Saved to `{GPT4O_CSV}`.")
                except Exception as e:
                    bar.empty()
                    st.error(f"Error: {e}")

        # Load from CSV if no session results yet
        if "gpt4o_r2_results" not in st.session_state:
            cached = load_existing(GPT4O_CSV)
            if cached:
                st.session_state["gpt4o_r2_results"] = cached

        gpt4o_res = st.session_state.get("gpt4o_r2_results")
        if gpt4o_res:
            _show_audit_results(gpt4o_res, gold, "GPT-4o Auditor")

    # ── RoBERTa Auditor ───────────────────────────────────────────────────────
    with st.expander("RoBERTa Auditor (GPT-4o-mini + BART-MNLI)"):
        st.caption(
            "Stage 1: GPT-4o-mini extracts 0–3 material claims per item.  "
            "Stage 2: BART-MNLI checks each claim against product brief.  "
            "⚠ First run downloads ~1.5 GB model from HuggingFace."
        )
        if st.button("Run RoBERTa Auditor", key="run_roberta", type="primary"):
            bar = st.progress(0.0, text="Starting RoBERTa Auditor…")
            def _rob_cb(i: int, n: int) -> None:
                bar.progress((i + 1) / n, text=f"Item {i + 1}/{n} (stage 1 + 2)…")
            with st.spinner("Running RoBERTa Auditor (~5–10 min including model load)…"):
                try:
                    res = run_roberta_audit(audit_items, progress_cb=_rob_cb)
                    st.session_state["roberta_r2_results"] = res
                    bar.empty()
                    st.success(f"Done — {len(res)} items. Saved to `{ROBERTA_CSV}`.")
                except Exception as e:
                    bar.empty()
                    st.error(f"Error: {e}")

        if "roberta_r2_results" not in st.session_state:
            cached = load_existing(ROBERTA_CSV)
            if cached:
                st.session_state["roberta_r2_results"] = cached

        roberta_res = st.session_state.get("roberta_r2_results")
        if roberta_res:
            _show_audit_results(roberta_res, gold, "RoBERTa Auditor")

    # ── Round 1 vs Round 2 comparison ────────────────────────────────────────
    gpt4o_res = st.session_state.get("gpt4o_r2_results")
    roberta_res = st.session_state.get("roberta_r2_results")
    if gpt4o_res or roberta_res:
        st.divider()
        st.markdown("### Round 1 vs Round 2 comparison")
        st.caption("Round 1 figures from IRR_FINDINGS_2026-07-14.md (gold n=100).")

        g2 = _audit_summary(gpt4o_res, gold) if gpt4o_res else {}
        r2 = _audit_summary(roberta_res, gold) if roberta_res else {}

        hdr = st.columns([3, 2, 2, 2, 2])
        for col, label in zip(hdr, ["Metric", "GPT-4o R1", "GPT-4o R2", "RoBERTa R1", "RoBERTa R2"]):
            col.markdown(f"**{label}**")

        rows = [
            ("NC rate",   "55%",   g2.get("nc_rate", "—"), "91%",   r2.get("nc_rate", "—")),
            ("κ vs gold", "0.213", g2.get("kappa", "—"),   "0.016", r2.get("kappa", "—")),
            ("F1 vs gold","0.726", g2.get("f1", "—"),      "0.854", r2.get("f1", "—")),
        ]
        for row in rows:
            cols = st.columns([3, 2, 2, 2, 2])
            for col, val in zip(cols, row):
                col.write(val)


# ── Export ────────────────────────────────────────────────────────────────────

def tab_export(
    reviews: list[dict],
    grouped: dict[int, dict[str, dict]],
    gold: dict[int, dict],
    items: dict[int, dict],
    code_names: list[str],
) -> None:
    import csv
    import io

    st.markdown("### Export")
    st.caption("Download CSVs for paper tables, supplementary material, or further analysis.")

    # ── Full annotations CSV ───────────────────────────────────────────────────
    st.markdown("**Full annotations** — one row per item, one column per coder + gold decision")
    buf = io.StringIO()
    fieldnames = (
        ["pilot_item_id", "product_id", "material_type"]
        + [f"{c}_decision" for c in CODERS]
        + [f"{c}_codes" for c in CODERS]
        + ["gold_decision", "gold_codes", "gold_adjudicator", "gold_notes"]
    )
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for iid in sorted(grouped.keys()):
        item_info = items.get(iid, {})
        row: dict = {
            "pilot_item_id": iid,
            "product_id": item_info.get("product_id", ""),
            "material_type": item_info.get("material_type", ""),
        }
        for c in CODERS:
            r = grouped[iid].get(c, {})
            row[f"{c}_decision"] = r.get("decision", "")
            codes = json.loads(r.get("violation_codes") or "[]")
            row[f"{c}_codes"] = "|".join(codes)
        g = gold.get(iid, {})
        row["gold_decision"] = g.get("decision", "")
        row["gold_codes"] = "|".join(json.loads(g.get("violation_codes") or "[]"))
        row["gold_adjudicator"] = g.get("adjudicator", "")
        row["gold_notes"] = g.get("notes", "")
        writer.writerow(row)
    st.download_button(
        "Download annotations.csv",
        data=buf.getvalue(),
        file_name="pilot_annotations.csv",
        mime="text/csv",
    )

    st.divider()

    # ── IRR summary CSV ────────────────────────────────────────────────────────
    st.markdown("**IRR summary** — Level 1 (decision) + Level 2 (per-code)")
    exclude_skip = st.checkbox("Exclude skipped items", value=True, key="export_excl")

    irr_buf = io.StringIO()
    irr_writer = csv.writer(irr_buf)

    # Level 1 header
    irr_writer.writerow(["# LEVEL 1 — Binary decision"])
    irr_writer.writerow(["pair_or_metric", "value", "n"])
    alpha_dec = krippendorff_alpha_nominal(grouped, exclude_skip=exclude_skip)
    irr_writer.writerow(["Krippendorff alpha (all raters)", f"{alpha_dec:.4f}" if alpha_dec is not None else "", ""])
    kappas = []
    for ca, cb in combinations(CODERS, 2):
        shared = [
            i for i in grouped
            if ca in grouped[i] and cb in grouped[i]
            and (not exclude_skip or (
                grouped[i][ca]["decision"] != "skip" and grouped[i][cb]["decision"] != "skip"
            ))
        ]
        ra = [grouped[i][ca]["decision"] for i in shared]
        rb = [grouped[i][cb]["decision"] for i in shared]
        k, n = cohen_kappa(ra, rb)
        kappas.append(k)
        irr_writer.writerow([f"Cohen kappa {ca}/{cb}", f"{k:.4f}" if k is not None else "", n])
    mean_k = sum(k for k in kappas if k is not None) / len([k for k in kappas if k is not None])
    irr_writer.writerow(["Mean pairwise kappa", f"{mean_k:.4f}", ""])

    # Level 2
    irr_writer.writerow([])
    irr_writer.writerow(["# LEVEL 2 — Per-code binary IRR"])
    irr_writer.writerow(["code", "alpha", "mean_kappa", "prevalence_pct", "n_flags"])
    per_code = compute_per_code_irr(grouped, code_names, exclude_skip=exclude_skip)
    for row in per_code:
        irr_writer.writerow([
            row["code"],
            f"{row['alpha']:.4f}" if row["alpha"] is not None else "",
            f"{row['mean_k']:.4f}" if row["mean_k"] is not None else "",
            f"{row['prevalence_pct']:.2f}",
            row["n_pos"],
        ])

    # Consensus
    irr_writer.writerow([])
    irr_writer.writerow(["# ITEM CONSENSUS"])
    consensus = compute_item_consensus(grouped, exclude_skip=exclude_skip)
    for k, v in consensus.items():
        irr_writer.writerow([k, v, ""])

    st.download_button(
        "Download irr_summary.csv",
        data=irr_buf.getvalue(),
        file_name="pilot_irr_summary.csv",
        mime="text/csv",
    )

    st.divider()

    # ── Violation frequency CSV ────────────────────────────────────────────────
    st.markdown("**Violation code frequency** — all annotations + unanimous-NC items")
    freq_buf = io.StringIO()
    freq_writer = csv.writer(freq_buf)
    freq_writer.writerow(["code", "count_all", "count_unanimous_nc"])
    freq_all = dict(compute_violation_freq(grouped, exclude_skip=exclude_skip))
    freq_unc = dict(compute_violation_freq(grouped, exclude_skip=exclude_skip, unanimous_only=True))
    all_codes_seen = sorted(set(freq_all) | set(freq_unc))
    for code in all_codes_seen:
        freq_writer.writerow([code, freq_all.get(code, 0), freq_unc.get(code, 0)])
    st.download_button(
        "Download violation_frequency.csv",
        data=freq_buf.getvalue(),
        file_name="pilot_violation_frequency.csv",
        mime="text/csv",
    )


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

    t0, t1, t2, t3, t4, t5, t6 = st.tabs(
        ["Setup", "Progress", "IRR", "Disagreements", "Adjudication", "Export", "Machine Audit"]
    )
    with t0:
        tab_setup()
    with t1:
        tab_progress(reviews, grouped, items)
    with t2:
        tab_irr(reviews, grouped, items)
    with t3:
        tab_disagreements(grouped, items, gold)
    with t4:
        tab_adjudication(grouped, items, gold, code_names)
    with t5:
        tab_export(reviews, grouped, gold, items, code_names)
    with t6:
        tab_machine_audit(items, gold)


if __name__ == "__main__":
    main()
