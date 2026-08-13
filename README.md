# KES 2026 — Compliance Pilot Study

Multi-page Streamlit app for human coding, machine auditing, and calibration of AI-generated marketing compliance.

---

## Setup

**Requirements:** Python 3.10+

```bash
git clone https://github.com/rodunia/youtube-scraper.git
cd youtube-scraper

python -m venv .venv
source .venv/bin/activate        # Mac/Linux
# .venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

---

## File you must copy manually

The coding database is excluded from git (it contains research data). You need to copy it from Dorota's machine:

```
outputs/compliance/pilot_coding.db
```

Copy it to the same path on the new machine. Without this file the app will start but all coding data, gold decisions, and calibration notes will be missing.

Everything else (pilot sample CSV, machine audit results, recoded outputs) is already in the repo.

---

## Running the app

```bash
streamlit run main.py
```

Pages available in the sidebar:

| Page | Purpose |
|---|---|
| Coding | Round 1 item-by-item annotation (do not re-code here after Round 1 is complete) |
| Analysis | IRR, disagreements, adjudication, machine audit |
| Calibration | Round 2 coding with calibration anchors and live Krippendorff's α |

---

## Machine auditor (GPT-4o)

To run the machine audit you need an OpenAI API key:

```bash
export OPENAI_API_KEY=sk-proj-...
```

Then launch the app and use the Machine Audit tab in the Analysis page.

---

## Project structure

```
main.py                          # App launcher
pages/                           # Streamlit pages (auto-discovered)
  1_Coding.py
  2_Analysis.py
  3_Calibration.py
app/
  pilot_coding.py                # Round 1 coding logic
  pilot_analysis.py              # IRR, adjudication, machine audit
  pilot_calibration.py           # Round 2 calibration workflow
  machine_audit.py               # GPT-4o auditor
  prompts_v2.py                  # Audit prompts (EU jurisdiction, V1-V5)
scripts/
  recode_round1.py               # Recode Round 1 codes → V1-V5
outputs/compliance/
  pilot_coding.db                # NOT in git — copy manually
  pilot_sample_100.csv           # 100-item pilot sample
  round1_recoded.csv             # Round 1 codes mapped to V1-V5
  round2_gpt4o.csv               # Machine audit results
  prompt_versions/               # Archived prompt versions
```
