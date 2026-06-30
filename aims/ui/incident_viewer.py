"""
Incident Viewer — simple Streamlit UI for incidents JSON

Run:
  streamlit run aims/ui/incident_viewer.py
"""

import json
import sys
from pathlib import Path

# `streamlit run` executes this as a loose script; add the repo root so the
# `aims` package imports with or without `pip install -e .`. (parents[2] = root.)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import streamlit as st

from aims.config import INCIDENTS_DIR

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AIMS — Incidents",
    page_icon="🔍",
    layout="wide",
)

SEVERITY_COLOUR = {
    "critical": "#c0392b",
    "high":     "#e67e22",
    "medium":   "#f1c40f",
    "low":      "#27ae60",
}

SEVERITY_EMOJI = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🟢",
}

# ── Sidebar — file picker ──────────────────────────────────────────────────────
st.sidebar.title("AIMS")
st.sidebar.markdown("### Load incidents file")

json_files = sorted(INCIDENTS_DIR.glob("*_incidents.json"))
by_name    = {f.name: f for f in json_files}

if not by_name:
    st.sidebar.warning(f"No *_incidents.json files found in {INCIDENTS_DIR}.")
    st.stop()

selected = st.sidebar.selectbox("File", list(by_name))
data     = json.loads(by_name[selected].read_text())

run_id     = data["run_id"]
incidents  = data["incidents"]
generated  = data["generated_at"][:19].replace("T", " ")

# ── Severity filter ────────────────────────────────────────────────────────────
all_severities = ["critical", "high", "medium", "low"]
present        = [s for s in all_severities if any(i["severity"] == s for i in incidents)]
selected_sevs  = st.sidebar.multiselect("Filter by severity", present, default=present)

filtered = [i for i in incidents if i["severity"] in selected_sevs]

# ── Header ─────────────────────────────────────────────────────────────────────
st.title(f"🔍 Incident Report — {run_id}")
st.caption(f"Generated {generated} UTC  ·  Source: `{selected}`")

# ── Summary row ────────────────────────────────────────────────────────────────
counts = {s: sum(1 for i in incidents if i["severity"] == s) for s in all_severities}
cols   = st.columns(4)
labels = ["Critical", "High", "Medium", "Low"]
keys   = ["critical", "high", "medium", "low"]

for col, label, key in zip(cols, labels, keys):
    col.metric(f"{SEVERITY_EMOJI[key]} {label}", counts[key])

st.divider()

# ── Incident cards ─────────────────────────────────────────────────────────────
if not filtered:
    st.info("No incidents match the selected filters.")
else:
    st.markdown(f"Showing **{len(filtered)}** of **{len(incidents)}** incidents")
    st.write("")

    for inc in filtered:
        sev   = inc["severity"]
        color = SEVERITY_COLOUR[sev]
        emoji = SEVERITY_EMOJI[sev]

        with st.container(border=True):
            # Title row
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(
                    f"<span style='background:{color};color:white;padding:2px 10px;"
                    f"border-radius:4px;font-weight:bold;font-size:0.8rem'>"
                    f"{emoji} {sev.upper()}</span> &nbsp;"
                    f"<strong>{inc['ticket_id']}</strong> · "
                    f"Step {inc['sequence_position']} ({inc['step_id']})",
                    unsafe_allow_html=True,
                )
            with col2:
                status_color = "red" if inc["status"] == "Open" else "green"
                st.markdown(
                    f"<div style='text-align:right'>"
                    f"<span style='color:{status_color};font-weight:bold'>{inc['status']}</span>"
                    f" · {inc['assigned_to']}</div>",
                    unsafe_allow_html=True,
                )

            st.write("")

            # Details
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**Section:** {inc['section']}")
            c2.markdown(f"**Timestamp:** `{inc['timestamp']}`")
            c3.markdown(f"**Confidence:** {inc['confidence']}%")

            st.markdown(f"**SOP Step:** {inc['sop_step']}")
            st.markdown(f"**Why {sev}:** {inc['severity_reason']}")

            with st.expander("Full summary & recommended action"):
                st.markdown(f"**Summary:** {inc['incident_summary']}")
                st.markdown(f"**Action:** {inc['recommended_action']}")
                st.caption(f"Created: {inc['created_at'][:19].replace('T', ' ')} UTC")
