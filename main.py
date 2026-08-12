"""
Root launcher for the KES 2026 compliance pilot — multi-page app.

    streamlit run app/main.py

Pages (auto-discovered from app/pages/):
    1_Coding.py   — item-by-item annotation workbench
    2_Analysis.py — IRR, disagreements, adjudication
"""
import streamlit as st

st.set_page_config(
    page_title="KES 2026 · Compliance Pilot",
    layout="wide",
    initial_sidebar_state="auto",
)

st.title("Compliance Pilot")
st.markdown(
    "Use the sidebar to navigate:\n\n"
    "- **Coding** — annotate pilot items (Round 1)\n"
    "- **Analysis** — IRR, progress, disagreements, adjudication\n"
    "- **Calibration** — Round 2 coding with calibration anchors and live IRR"
)
