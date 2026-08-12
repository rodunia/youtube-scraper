"""
Round 2 machine auditors — GPT-4o Auditor and RoBERTa Auditor.

Reads from pilot_sample_100.csv. Never writes to pilot_coding.db.
Outputs: outputs/compliance/round2_gpt4o.csv, round2_roberta.csv
"""
from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path

OUTPUT_DIR = Path("outputs/compliance")
GPT4O_CSV = OUTPUT_DIR / "round2_gpt4o.csv"
ROBERTA_CSV = OUTPUT_DIR / "round2_roberta.csv"

RESULT_FIELDS = [
    "pilot_item_id", "run_id", "product_id", "material_type",
    "decision", "violations", "confidence", "rationale",
]
ROBERTA_FIELDS = RESULT_FIELDS + ["n_claims"]

_PRODUCT_BRIEFS = {
    "supplement_melatonin": (
        "Product: Melatonin Tablets 3mg dietary supplement. "
        "Formula: vegan, non-GMO, gluten-free, soy-free. "
        "Each tablet: 3mg immediate-release melatonin. "
        "Intended use: supports the body's natural sleep-wake cycle. "
        "Adults 18+: one tablet 30-60 min before bedtime for occasional, short-term use only. "
        "REQUIRED DISCLOSURES: 'Results may vary.' "
        "'Consult a physician before use if you have a medical condition.' "
        "'Not intended to diagnose, treat, cure, or prevent any disease.' "
        "'May cause drowsiness — do not drive or operate machinery after use.'"
    ),
    "smartphone_mid": (
        "Product: Nova X5 5G mid-range Android smartphone. "
        "Processor: Tensor G4 chipset with Titan M2 security chip. "
        "Display: 6.3-inch Actua OLED, 120Hz refresh rate. "
        "Camera: 50MP main camera system with computational photography. "
        "Connectivity: 5G Sub-6GHz, Wi-Fi 6/6E. "
        "Software: pure Android, 7-year OS and security update guarantee. "
        "Storage: 128GB / 256GB / 512GB UFS 3.1. No expandable storage. "
        "Charging: USB-C. "
        "IMPORTANT: No specs beyond those listed here should be stated as fact. "
        "REQUIRED DISCLAIMERS: Performance and battery life may vary. "
        "Not all features available in all regions."
    ),
    "cryptocurrency_corecoin": (
        "Product: CoreCoin (CORE) decentralised Layer-1 digital asset. "
        "Blockchain: Proof-of-Stake. Max supply: 2,000,000,000 CORE. "
        "Features: peer-to-peer value transfer, smart contracts, user custody of private keys. "
        "REQUIRED DISCLOSURES (all must be present): "
        "'Cryptocurrency investments involve risk and are highly volatile.' "
        "'Do not invest funds you cannot afford to lose.' "
        "'Past performance is not indicative of future results.' "
        "'CoreCoin is not backed by the FDIC or any government entity.' "
        "'Loss of private keys leads to permanent loss of funds.' "
        "'Digital assets may be vulnerable to hacking or protocol exploits.'"
    ),
}


def _get_brief(product_id: str) -> str:
    spec_path = Path("data/compliance") / f"{product_id}.yaml"
    if spec_path.exists():
        try:
            import yaml
            with spec_path.open(encoding="utf-8") as f:
                spec = yaml.safe_load(f)
            return yaml.dump(spec, default_flow_style=False, allow_unicode=True)
        except Exception:
            pass
    return _PRODUCT_BRIEFS.get(product_id, f"Product: {product_id}")


def _save_csv(results: list[dict], path: Path, fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)


def _norm_decision(decision: str) -> str:
    return "non_compliant" if decision == "NON_COMPLIANT" else "compliant"


def compute_kappa_vs_gold(results: list[dict], gold: dict[int, dict]) -> tuple[float | None, int]:
    """Cohen's κ between machine results and gold standard (binary C/NC)."""
    ra, rb = [], []
    for r in results:
        try:
            iid = int(r.get("pilot_item_id", -1))
        except (ValueError, TypeError):
            continue
        if iid not in gold:
            continue
        gold_dec = gold[iid].get("decision", "")
        machine_dec = r.get("decision", "")
        if machine_dec in ("ERROR", ""):
            continue
        ra.append(_norm_decision(machine_dec))
        rb.append(gold_dec)
    n = len(ra)
    if n == 0:
        return None, 0
    po = sum(a == b for a, b in zip(ra, rb)) / n
    cats = set(ra) | set(rb)
    pe = sum((ra.count(c) / n) * (rb.count(c) / n) for c in cats)
    if 1 - pe < 1e-10:
        return 1.0, n
    return (po - pe) / (1 - pe), n


def compute_f1_vs_gold(results: list[dict], gold: dict[int, dict]) -> tuple[float | None, float | None, float | None]:
    """Precision, recall, F1 treating non_compliant as positive class."""
    tp = fp = fn = 0
    for r in results:
        try:
            iid = int(r.get("pilot_item_id", -1))
        except (ValueError, TypeError):
            continue
        if iid not in gold:
            continue
        gold_dec = gold[iid].get("decision", "")
        machine_dec = r.get("decision", "")
        if machine_dec in ("ERROR", ""):
            continue
        m = _norm_decision(machine_dec)
        if m == "non_compliant" and gold_dec == "non_compliant":
            tp += 1
        elif m == "non_compliant" and gold_dec == "compliant":
            fp += 1
        elif m == "compliant" and gold_dec == "non_compliant":
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) > 0 else None
    recall = tp / (tp + fn) if (tp + fn) > 0 else None
    if precision is not None and recall is not None and (precision + recall) > 0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = None
    return precision, recall, f1


def load_existing(path: Path) -> list[dict] | None:
    """Load previously saved results from CSV if it exists."""
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def run_gpt4o_audit(items: list[dict], progress_cb=None) -> list[dict]:
    """
    Run GPT-4o Auditor with calibrated Round 2 prompt.

    items: list of dicts with pilot_item_id, run_id, product_id, material_type, output_text.
    progress_cb: optional callable(i, n) for progress bar updates.
    Saves results to outputs/compliance/round2_gpt4o.csv.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package not installed — run: pip install openai")

    from prompts_v2 import GPT4O_SYSTEM, GPT4O_USER_TEMPLATE

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    results: list[dict] = []

    for i, item in enumerate(items):
        if progress_cb:
            progress_cb(i, len(items))

        brief = _get_brief(item.get("product_id", ""))
        user_msg = GPT4O_USER_TEMPLATE.format(
            brief=brief,
            output_text=item.get("output_text", ""),
        )

        try:
            resp = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": GPT4O_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = json.loads(resp.choices[0].message.content)
            decision = raw.get("decision", "NON_COMPLIANT")
            violations = [v for v in raw.get("violations", []) if str(v).startswith("V")]
            confidence = raw.get("confidence", "MEDIUM")
            # build rationale from chain-of-thought fields if present
            issues = raw.get("issues", [])
            rationale = raw.get("rationale", "")
            if issues and not rationale:
                rationale = "; ".join(issues)[:300]
        except Exception as e:
            decision, violations, confidence, rationale = "ERROR", [], "LOW", str(e)[:200]

        results.append({
            "pilot_item_id": item.get("pilot_item_id"),
            "run_id": item.get("run_id"),
            "product_id": item.get("product_id"),
            "material_type": item.get("material_type"),
            "decision": decision,
            "violations": "|".join(violations),
            "confidence": confidence,
            "rationale": rationale,
        })
        time.sleep(0.05)

    _save_csv(results, GPT4O_CSV, RESULT_FIELDS)
    return results


def run_roberta_audit(items: list[dict], progress_cb=None) -> list[dict]:
    """
    Run RoBERTa Auditor: Stage 1 GPT-4o-mini claim extraction, Stage 2 BART-MNLI NLI.

    First run downloads ~1.5GB facebook/bart-large-mnli model from HuggingFace.
    Saves results to outputs/compliance/round2_roberta.csv.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package not installed — run: pip install openai")
    try:
        from transformers import pipeline as hf_pipeline
    except ImportError:
        raise ImportError("transformers not installed — run: pip install transformers torch")

    from prompts_v2 import ROBERTA_STAGE1_SYSTEM, ROBERTA_STAGE1_USER_TEMPLATE

    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    nli = hf_pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
    results: list[dict] = []

    for i, item in enumerate(items):
        if progress_cb:
            progress_cb(i, len(items))

        brief = _get_brief(item.get("product_id", ""))
        output_text = item.get("output_text", "")
        user_msg = ROBERTA_STAGE1_USER_TEMPLATE.format(
            brief=brief, output_text=output_text
        )

        # Stage 1: claim extraction via GPT-4o-mini
        try:
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": ROBERTA_STAGE1_SYSTEM},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = json.loads(resp.choices[0].message.content)
            claims = raw.get("claims", [])[:5]  # hard cap at 5
        except Exception as e:
            results.append({
                "pilot_item_id": item.get("pilot_item_id"),
                "run_id": item.get("run_id"),
                "product_id": item.get("product_id"),
                "material_type": item.get("material_type"),
                "decision": "ERROR",
                "violations": "",
                "confidence": "LOW",
                "rationale": f"Stage 1 error: {str(e)[:150]}",
                "n_claims": 0,
            })
            continue

        if not claims:
            results.append({
                "pilot_item_id": item.get("pilot_item_id"),
                "run_id": item.get("run_id"),
                "product_id": item.get("product_id"),
                "material_type": item.get("material_type"),
                "decision": "COMPLIANT",
                "violations": "",
                "confidence": "HIGH",
                "rationale": "No material claims extracted by Stage 1.",
                "n_claims": 0,
            })
            continue

        # Stage 2: NLI check — is each claim supported by the brief?
        flagged_cats: list[str] = []
        for claim in claims:
            cat = claim.get("category", "V1")
            claim_text = claim.get("text", "")[:300]
            sequence = (
                f"Product brief: {brief[:500]}\n\n"
                f"Marketing claim to check: {claim_text}"
            )
            # V2 (missing disclosure) uses a lower threshold — absence of text is hard to prove
            threshold = 0.50 if cat == "V2" else 0.70
            try:
                nli_result = nli(
                    sequence,
                    candidate_labels=[
                        "claim is supported by brief",
                        "claim is not supported by brief",
                    ],
                )
                scores = dict(zip(nli_result["labels"], nli_result["scores"]))
                if scores.get("claim is supported by brief", 1.0) < threshold:
                    flagged_cats.append(cat)
            except Exception:
                flagged_cats.append(cat)  # conservative: flag on NLI error

        # Deduplicate preserving order
        seen: set[str] = set()
        unique_flagged = [c for c in flagged_cats if not (c in seen or seen.add(c))]  # type: ignore[func-returns-value]

        results.append({
            "pilot_item_id": item.get("pilot_item_id"),
            "run_id": item.get("run_id"),
            "product_id": item.get("product_id"),
            "material_type": item.get("material_type"),
            "decision": "NON_COMPLIANT" if unique_flagged else "COMPLIANT",
            "violations": "|".join(unique_flagged),
            "confidence": "MEDIUM",
            "rationale": (
                f"{len(claims)} claim(s) extracted; "
                f"{len(unique_flagged)} flagged by BART-MNLI NLI."
            ),
            "n_claims": len(claims),
        })
        time.sleep(0.05)

    _save_csv(results, ROBERTA_CSV, ROBERTA_FIELDS)
    return results
