"""
Round 2 Calibration — three-tab workflow for 4 coders.

Tab 1: Disagreement Review  — browse contested Round 1 items, set calibration anchors
Tab 2: Round 2 Coding       — re-code items with calibration notes as reference
Tab 3: Live IRR             — Krippendorff's α updating as coders submit
"""
from __future__ import annotations

import csv
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

DB_PATH = Path(os.environ.get("PILOT_DB_PATH", "outputs/compliance/pilot_coding.db"))
SAMPLE_CSV = Path(os.environ.get("PILOT_SAMPLE_CSV", "outputs/compliance/pilot_sample_100.csv"))

CODERS = ["Dorota", "Mohan", "Christian", "Edyta"]

V_CODES = ["V1", "V2", "V3", "V4", "V5"]
V_LABELS = {
    "V1": "V1 — Factual inaccuracy / hallucinated spec",
    "V2": "V2 — Missing required disclosure (EU / EFSA / MiCA)",
    "V3": "V3 — Unauthorized health or performance claim",
    "V4": "V4 — Fabricated testimonial / urgency cue",
    "V5": "V5 — Prompt artifact violation",
}

PRODUCT_BRIEFS = {
    "supplement_melatonin": (
        "Melatonin Tablets 3mg dietary supplement. Vegan, non-GMO, gluten-free, soy-free. "
        "Intended use: supports body's natural sleep-wake cycle. Adults 18+. "
        "REQUIRED (EFSA EC 1924/2006): 'Results may vary.' "
        "'Consult a physician before use if you have a medical condition.' "
        "'Not intended to diagnose, treat, cure, or prevent any disease.'"
    ),
    "smartphone_mid": (
        "Nova X5 5G mid-range Android smartphone. Processor: Tensor G4 + Titan M2 security chip. "
        "Display: 6.3\" OLED 120Hz. Camera: 50MP. Storage: 128/256/512GB. "
        "Software: pure Android, 7-year OS and security update guarantee. "
        "REQUIRED (UCPD 2005/29/EC): 'Performance and battery life may vary.' "
        "No specs beyond those listed above should be stated as fact."
    ),
    "cryptocurrency_corecoin": (
        "CoreCoin (CORE) decentralised Layer-1 digital asset (Proof-of-Stake). "
        "Max supply: 2,000,000,000 CORE. Features: P2P transfer, smart contracts, user key custody. "
        "REQUIRED (MiCA EU 2023/1114): 'Cryptocurrency investments involve risk and are highly volatile.' "
        "'Do not invest funds you cannot afford to lose.' "
        "'Past performance is not indicative of future results.' "
        "'CoreCoin is not backed by any government entity.'"
    ),
}


# ── Database ──────────────────────────────────────────────────────────────────

def _conn(readonly: bool = False) -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if readonly:
        con = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    else:
        con = sqlite3.connect(DB_PATH)
        con.execute("PRAGMA journal_mode=WAL")
    con.row_factory = sqlite3.Row
    return con


def ensure_tables() -> None:
    con = _conn()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS calibration_notes (
            pilot_item_id   INTEGER PRIMARY KEY,
            anchor_decision TEXT DEFAULT '',
            note            TEXT DEFAULT '',
            created_by      TEXT DEFAULT '',
            created_at      TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS round2_reviews (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            coder_id        TEXT NOT NULL,
            pilot_item_id   INTEGER NOT NULL,
            decision        TEXT NOT NULL,
            violation_codes TEXT DEFAULT '[]',
            notes           TEXT DEFAULT '',
            submitted_at    TEXT NOT NULL,
            UNIQUE(coder_id, pilot_item_id)
        );
    """)
    con.commit()
    con.close()


# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def load_sample() -> dict[int, dict]:
    items: dict[int, dict] = {}
    with SAMPLE_CSV.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            iid = int(row["pilot_item_id"])
            items[iid] = {
                "product_id": row["product_id"],
                "material_type": row["material_type"].replace(".j2", "").replace("_", " "),
                "output_text": row["output_text"],
            }
    return items


@st.cache_data(ttl=3600)
def load_round1() -> dict[int, dict[str, str]]:
    """Returns {item_id: {coder_id: decision}}. Read-only."""
    con = _conn(readonly=True)
    rows = con.execute(
        "SELECT pilot_item_id, coder_id, decision FROM pilot_reviews"
    ).fetchall()
    con.close()
    result: dict[int, dict[str, str]] = {}
    for r in rows:
        result.setdefault(int(r["pilot_item_id"]), {})[r["coder_id"]] = r["decision"]
    return result


def load_calibration_notes() -> dict[int, dict]:
    con = _conn(readonly=True)
    rows = con.execute("SELECT * FROM calibration_notes").fetchall()
    con.close()
    return {int(r["pilot_item_id"]): dict(r) for r in rows}


def load_round2() -> dict[int, dict[str, str]]:
    """Returns {item_id: {coder_id: decision}}."""
    con = _conn(readonly=True)
    rows = con.execute(
        "SELECT pilot_item_id, coder_id, decision FROM round2_reviews"
    ).fetchall()
    con.close()
    result: dict[int, dict[str, str]] = {}
    for r in rows:
        result.setdefault(int(r["pilot_item_id"]), {})[r["coder_id"]] = r["decision"]
    return result


def save_calibration_note(iid: int, anchor: str, note: str, created_by: str) -> None:
    con = _conn()
    con.execute(
        """INSERT INTO calibration_notes (pilot_item_id, anchor_decision, note, created_by, created_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(pilot_item_id) DO UPDATE SET
               anchor_decision = excluded.anchor_decision,
               note            = excluded.note,
               created_by      = excluded.created_by,
               created_at      = excluded.created_at""",
        (iid, anchor, note, created_by, datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()


def save_round2(coder_id: str, iid: int, decision: str,
                codes: list[str], notes: str) -> None:
    con = _conn()
    con.execute(
        """INSERT INTO round2_reviews
               (coder_id, pilot_item_id, decision, violation_codes, notes, submitted_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(coder_id, pilot_item_id) DO UPDATE SET
               decision        = excluded.decision,
               violation_codes = excluded.violation_codes,
               notes           = excluded.notes,
               submitted_at    = excluded.submitted_at""",
        (coder_id, iid, decision, json.dumps(codes), notes,
         datetime.now(timezone.utc).isoformat()),
    )
    con.commit()
    con.close()


# ── IRR ───────────────────────────────────────────────────────────────────────

def krippendorff_alpha(data: dict[int, dict[str, str]]) -> float | None:
    """
    Nominal Krippendorff's α.
    data: {item_id: {coder_id: value}}
    Uses all items with >= 2 coders present.
    """
    units = {iid: list(coders.values())
             for iid, coders in data.items() if len(coders) >= 2}
    if not units:
        return None

    all_vals = [v for vals in units.values() for v in vals]
    n = len(all_vals)
    if n == 0:
        return None

    cats = list(set(all_vals))

    # Coincidence matrix
    o: dict[tuple[str, str], float] = {(c1, c2): 0.0 for c1 in cats for c2 in cats}
    for vals in units.values():
        m = len(vals)
        if m < 2:
            continue
        for i in range(m):
            for j in range(m):
                if i != j:
                    o[(vals[i], vals[j])] += 1.0 / (m - 1)

    total = sum(o.values())
    if total == 0:
        return None

    D_o = sum(v for (c1, c2), v in o.items() if c1 != c2) / total
    n_c = {c: sum(o[(c, c2)] for c2 in cats) for c in cats}
    D_e = 1 - sum((n_c[c] / total) ** 2 for c in cats)

    if D_e < 1e-10:
        return 1.0
    return 1 - D_o / D_e


# ── Tab helpers ───────────────────────────────────────────────────────────────

def _item_card(iid: int, item: dict, cal_notes: dict) -> None:
    """Render product brief + output text side-by-side."""
    product_label = item["product_id"].replace("_", " ").title()
    st.markdown(f"**Item #{iid}** · {product_label} · {item['material_type']}")
    brief = PRODUCT_BRIEFS.get(item["product_id"], item["product_id"])
    with st.expander("Product brief (EU standards apply)"):
        st.text(brief)
    st.markdown("**Output to audit:**")
    st.markdown(item["output_text"])


# ── Tab 1: Disagreement Review ────────────────────────────────────────────────

def tab_disagreement(items: dict, round1: dict, cal_notes: dict) -> None:
    st.subheader("Round 1 Disagreement Review")
    st.caption(
        "Items ranked by disagreement. Set a calibration anchor and note for contested items — "
        "these become the living codebook that Round 2 coders see while coding."
    )

    # Compute stats per item
    stats = []
    for iid, coders in round1.items():
        if iid not in items:
            continue
        decisions = list(coders.values())
        n = len(decisions)
        nc = decisions.count("non_compliant")
        # disagreement = how far from unanimous (0 = full agreement, 0.5 = 50/50)
        disagree_frac = min(nc, n - nc) / n
        stats.append({
            "iid": iid,
            "n": n,
            "nc": nc,
            "c": n - nc,
            "disagree_frac": disagree_frac,
            "anchored": iid in cal_notes and bool(cal_notes[iid].get("note")),
        })
    stats.sort(key=lambda x: (-x["disagree_frac"], x["iid"]))

    col1, col2 = st.columns(2)
    show_unanchored = col1.checkbox("Show only items without calibration notes", value=False)
    min_coders = col2.number_input("Min coders in Round 1", 1, 6, 2)

    filtered = [s for s in stats
                if s["n"] >= min_coders
                and (not show_unanchored or not s["anchored"])]

    if not filtered:
        st.info("No items match the current filter.")
        return

    contested = sum(1 for s in filtered if s["disagree_frac"] > 0)
    anchored_count = sum(1 for s in filtered if s["anchored"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Items shown", len(filtered))
    c2.metric("Contested (any disagreement)", contested)
    c3.metric("Anchored", anchored_count)

    selected_idx = st.selectbox(
        "Select item",
        range(len(filtered)),
        format_func=lambda i: (
            f"#{filtered[i]['iid']} — "
            f"C:{filtered[i]['c']} NC:{filtered[i]['nc']} "
            f"({'✓ note' if filtered[i]['anchored'] else '○ no note'})"
        ),
    )

    stat = filtered[selected_idx]
    iid = stat["iid"]
    item = items[iid]
    coders = round1[iid]

    st.divider()
    col_item, col_anchor = st.columns([3, 2])

    with col_item:
        _item_card(iid, item, cal_notes)

    with col_anchor:
        st.markdown("**Round 1 decisions:**")
        for coder, dec in sorted(coders.items()):
            icon = "🔴" if dec == "non_compliant" else "🟢"
            st.markdown(f"{icon} `{coder}` — {dec.replace('_', ' ')}")

        st.divider()
        st.markdown("**Set calibration anchor:**")
        existing = cal_notes.get(iid, {})
        anchor_options = ["", "compliant", "non_compliant"]
        anchor = st.radio(
            "Consensus decision",
            anchor_options,
            index=anchor_options.index(existing.get("anchor_decision", "")),
            format_func=lambda x: "— not set —" if x == "" else x.replace("_", " ").upper(),
            key=f"anchor_{iid}",
        )
        note = st.text_area(
            "Calibration note (WHY — becomes codebook entry for Round 2 coders)",
            value=existing.get("note", ""),
            height=130,
            key=f"note_{iid}",
        )
        facilitator = st.selectbox(
            "Your name",
            [""] + CODERS,
            index=([""] + CODERS).index(existing.get("created_by", ""))
            if existing.get("created_by", "") in [""] + CODERS else 0,
            key=f"fac_{iid}",
        )
        if st.button("Save anchor & note", type="primary", key=f"save_{iid}"):
            if not facilitator:
                st.warning("Please select your name.")
            elif not note.strip():
                st.warning("Please add a calibration note before saving.")
            else:
                save_calibration_note(iid, anchor, note.strip(), facilitator)
                st.success("Saved.")
                st.rerun()


# ── Tab 2: Round 2 Coding ─────────────────────────────────────────────────────

def tab_coding(items: dict, cal_notes: dict, round2: dict) -> None:
    st.subheader("Round 2 Coding")
    st.caption(
        "Re-code each item using the calibration notes as your guide. "
        "Your Round 1 decisions are intentionally hidden to avoid anchoring bias."
    )

    coder_id = st.selectbox("Your name", [""] + CODERS, key="r2_coder")
    if not coder_id:
        st.info("Select your name to begin.")
        return

    done_ids = {iid for iid, coders in round2.items() if coder_id in coders}
    all_ids = sorted(items.keys())
    pending = [iid for iid in all_ids if iid not in done_ids]

    c1, c2, c3 = st.columns(3)
    c1.metric("Total items", len(all_ids))
    c2.metric("Completed", len(done_ids))
    c3.metric("Remaining", len(pending))

    if not pending:
        st.success(f"All done, {coder_id}! Thank you.")
        return

    # Navigation
    if "r2_idx" not in st.session_state:
        st.session_state.r2_idx = 0
    st.session_state.r2_idx = min(st.session_state.r2_idx, len(pending) - 1)

    nav1, nav2, nav3 = st.columns([1, 5, 1])
    with nav1:
        if st.button("← Prev", disabled=st.session_state.r2_idx == 0):
            st.session_state.r2_idx -= 1
            st.rerun()
    with nav2:
        st.progress(
            len(done_ids) / len(all_ids),
            text=f"{len(done_ids)} / {len(all_ids)} submitted",
        )
    with nav3:
        if st.button("Next →", disabled=st.session_state.r2_idx >= len(pending) - 1):
            st.session_state.r2_idx += 1
            st.rerun()

    iid = pending[st.session_state.r2_idx]
    item = items[iid]

    st.divider()
    col_item, col_form = st.columns([3, 2])

    with col_item:
        _item_card(iid, item, cal_notes)

    with col_form:
        # Show calibration note if available
        note_data = cal_notes.get(iid)
        if note_data and note_data.get("note"):
            st.markdown("**📋 Calibration note:**")
            if note_data.get("anchor_decision"):
                anchor_dec = note_data["anchor_decision"].replace("_", " ").upper()
                colour = "red" if "NON" in anchor_dec else "green"
                st.markdown(f"Anchor: :{colour}[**{anchor_dec}**]")
            st.info(note_data["note"])
        else:
            st.caption("No calibration note for this item — apply the codebook directly.")

        st.divider()
        st.markdown("**Your decision:**")
        decision = st.radio(
            "Compliance decision",
            ["compliant", "non_compliant"],
            format_func=lambda x: x.replace("_", " ").upper(),
            key=f"r2_dec_{iid}",
        )
        codes: list[str] = []
        if decision == "non_compliant":
            codes = st.multiselect(
                "Violation codes (select all that apply)",
                V_CODES,
                format_func=lambda c: V_LABELS[c],
                key=f"r2_codes_{iid}",
            )
        coder_note = st.text_input("Optional note", key=f"r2_note_{iid}")

        if st.button("Submit & continue →", type="primary", key=f"r2_submit_{iid}"):
            if decision == "non_compliant" and not codes:
                st.warning("Please select at least one violation code for non-compliant items.")
            else:
                save_round2(coder_id, iid, decision, codes, coder_note)
                st.session_state.r2_idx = min(
                    st.session_state.r2_idx, len(pending) - 2
                )
                st.rerun()


# ── Tab 3: Live IRR ───────────────────────────────────────────────────────────

def tab_irr(round1: dict, round2: dict) -> None:
    st.subheader("Live IRR — Round 2")

    r2_coders: set[str] = set()
    for coders in round2.values():
        r2_coders.update(coders.keys())

    if not r2_coders:
        st.info("No Round 2 submissions yet. Come back once coders have started.")
        return

    # Progress table
    all_ids = sorted(round1.keys())
    progress_rows = []
    for coder in sorted(r2_coders):
        done = sum(1 for iid in all_ids if iid in round2 and coder in round2[iid])
        progress_rows.append({
            "Coder": coder,
            "Completed": done,
            "Total": len(all_ids),
            "Progress": f"{done/len(all_ids):.0%}",
        })
    st.dataframe(pd.DataFrame(progress_rows).set_index("Coder"), use_container_width=True)

    # Items where ALL round2 coders have submitted
    complete = {
        iid: coders for iid, coders in round2.items()
        if all(c in coders for c in r2_coders)
    }

    st.metric("Items with all coders complete", len(complete))

    if len(complete) < 5:
        st.caption("Need at least 5 fully-coded items to compute α reliably.")
        return

    # α Round 2
    alpha_r2 = krippendorff_alpha(complete)

    # α Round 1 on same items for comparison
    round1_matched = {iid: round1[iid] for iid in complete if iid in round1}
    alpha_r1 = krippendorff_alpha(round1_matched) if round1_matched else None

    c1, c2, c3 = st.columns(3)
    if alpha_r1 is not None:
        c1.metric("Round 1 α (same items)", f"{alpha_r1:.3f}")
    c2.metric(
        "Round 2 α",
        f"{alpha_r2:.3f}" if alpha_r2 is not None else "—",
    )
    if alpha_r1 is not None and alpha_r2 is not None:
        c3.metric("Change", f"{alpha_r2 - alpha_r1:+.3f}")

    st.caption(
        f"α computed on {len(complete)} items fully coded by "
        f"{len(r2_coders)} coder(s): {', '.join(sorted(r2_coders))}."
    )

    # Per-coder agreement with majority vote
    if len(r2_coders) >= 2:
        st.divider()
        st.markdown("**Per-coder alignment with majority vote (Round 2):**")
        for coder in sorted(r2_coders):
            agree = total = 0
            for iid, coders in complete.items():
                vals = list(coders.values())
                majority = (
                    "non_compliant"
                    if vals.count("non_compliant") > len(vals) / 2
                    else "compliant"
                )
                if coder in coders:
                    total += 1
                    if coders[coder] == majority:
                        agree += 1
            if total > 0:
                pct = agree / total
                st.progress(pct, text=f"{coder}: {agree}/{total} agree with majority ({pct:.0%})")

    # NC rate per coder
    st.divider()
    st.markdown("**Non-compliant rate per coder (Round 2):**")
    nc_data = []
    for coder in sorted(r2_coders):
        coder_items = [(iid, coders[coder]) for iid, coders in round2.items() if coder in coders]
        if coder_items:
            nc_rate = sum(1 for _, d in coder_items if d == "non_compliant") / len(coder_items)
            nc_data.append({"Coder": coder, "NC rate": f"{nc_rate:.0%}", "n items": len(coder_items)})
    if nc_data:
        st.dataframe(pd.DataFrame(nc_data).set_index("Coder"), use_container_width=True)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    st.title("Calibration — Round 2")
    ensure_tables()

    items = load_sample()
    round1 = load_round1()
    cal_notes = load_calibration_notes()
    round2 = load_round2()

    tab1, tab2, tab3 = st.tabs([
        "① Disagreement Review",
        "② Round 2 Coding",
        "③ Live IRR",
    ])
    with tab1:
        tab_disagreement(items, round1, cal_notes)
    with tab2:
        tab_coding(items, cal_notes, round2)
    with tab3:
        tab_irr(round1, round2)


if __name__ == "__main__":
    main()
