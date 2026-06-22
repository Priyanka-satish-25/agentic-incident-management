# ProcedureGuard

🛡️ **Manufacturing compliance & incident management.**

A worker assembles a product on video, the build is checked against a Standard
Operating Procedure (SOP), and any deviation is turned into a tracked incident
ticket — severity-classified by an LLM and routed to the right role for triage.

This repository is **Layer 3 + the UI** of a larger pipeline (Layers 1 & 2 are
owned by teammates).

---

## Pipeline

```
Agent 1   →  extract SOP steps          →  *_steps_input.json
Agent 2   →  verify worker vs. SOP       →  *_verdicts.json   (Compliant / Deviation / Unable-to-verify)
Agent 3   →  classify deviations         →  *_incidents.json  ┐
Root-Cause Agent → diagnose the run      →  *_grouped.json    ┘ ← THIS REPO
UI        →  triage, comment, escalate   →  tickets_db.json
```

- **Agent 3** (`layer3/agent3/incident_management_agent.py`) reads a verdicts
  JSON, filters for `Deviation` verdicts, and calls an LLM per deviation to
  produce a structured incident record (severity, reason, summary, recommended
  action). Incidents are auto-assigned by severity:

  | Severity | Assigned to |
  |----------|-------------|
  | critical | Production Manager |
  | high     | QA Manager |
  | medium   | Supervisor |
  | low      | QA Log |

- **Root-Cause Agent** (`root_cause_agent.py`) reasons over *all* of a run's
  incidents together to separate independent **root causes** from their downstream
  **consequences** (e.g. a state-strip checkpoint failure that merely *reports*
  earlier component omissions). It runs automatically at the end of each Agent 3
  run, writing `*_grouped.json`. Bounded autonomy: read-only, guardrailed (every
  incident appears exactly once — nothing dropped or invented), and every causal
  link carries a written rationale.

- **UI** (`procedureguard_ui.py`) is a Streamlit app for role-based triage:
  view tickets, comment, close, and escalate up the chain
  (QA Log → Supervisor → QA Manager → Production Manager). A **Diagnoses** tab
  renders each run's causal tree, and grouped tickets show cause/effect links in
  their detail view.

- **Notifications** (`notifications.py`) sends email on ticket creation /
  escalation via the Resend API (optional — skipped gracefully if unconfigured).

---

## SOP dataset

The active SOP is the **STEMFIE construction-set vehicle assembly manual**
(open-source IndustReal dataset, doc IR-MAN-001 Rev B) — covering full-build
*Procedure A* (→ state 13) and the rear-chassis-upgrade *Procedure B*
(state 13 → 22). Sample verdicts (`RUN-102…105`) and their generated incidents
are derived from this manual, with deviations drawn from its Chapter 8
documented error modes (reversed pin, wrong braces, acorn-nut-for-screw,
omitted pulley / washer / wheel).

---

## Setup

Requires Python 3.10+.

```bash
# 1. Install Agent 3 dependencies
pip install -r layer3/agent3/requirements.txt

# 2. Install the UI dependency
pip install streamlit
```

### Configure the LLM backend

Agent 3 and the Root-Cause Agent use **Azure OpenAI**.
Copy the example env and add your Azure credentials:

```bash
cp layer3/agent3/.env.example layer3/agent3/.env
```

Edit `layer3/agent3/.env`:

```ini
AZURE_OPENAI_ENDPOINT=https://<your-resource>.openai.azure.com/
AZURE_OPENAI_API_KEY=<your Azure OpenAI key>
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini      # the deployment name you created
AZURE_OPENAI_API_VERSION=2024-10-21       # optional; this is the default
```

> Get the endpoint and key from your Azure OpenAI resource → **Keys and Endpoint**.
> `AZURE_OPENAI_DEPLOYMENT` must be the **deployment name** from Azure AI Studio
> (what you named the deployment), not the base model id.
> `.env` is gitignored — never commit it.

---

## Usage

### 1. Generate incidents from verdicts (Agent 3)

Run once per verdicts file. Each run writes `<run_id>_incidents.json` **and**
automatically produces the root-cause diagnosis `<run_id>_grouped.json`:

```bash
cd layer3/agent3
python3 incident_management_agent.py ../../sample_verdicts_input.json   # → RUN-102_incidents.json + RUN-102_grouped.json
python3 incident_management_agent.py ../../RUN-103_verdicts.json        # → RUN-103_*
python3 incident_management_agent.py ../../RUN-104_verdicts.json        # → RUN-104_*
python3 incident_management_agent.py ../../RUN-105_verdicts.json        # → RUN-105_*
```

To (re)generate only the diagnosis for an existing incidents file:

```bash
python3 root_cause_agent.py RUN-103_incidents.json   # → RUN-103_grouped.json (prints the causal tree)
```

### 2. View incidents in the terminal (optional)

```bash
python3 view_incidents.py RUN-103_incidents.json
```

### 3. Launch the triage UI

```bash
streamlit run procedureguard_ui.py
```

Opens at `http://localhost:8501`. On first launch it scans all
`*_incidents.json` files and builds `tickets_db.json`.

**Demo credentials:**

| User / pass   | Role               |
|---------------|--------------------|
| `alice` / `alice` | Production Manager |
| `bob`   / `bob`   | QA Manager         |
| `carol` / `carol` | Supervisor         |
| `dave`  / `dave`  | QA Log             |

> Deleting `*_incidents.json` does **not** clear the UI's store. To start clean,
> also delete `tickets_db.json` — it rebuilds from the incident files on next launch.

---

## Project layout

```
ProcedureGuard/
├── layer3/agent3/
│   ├── incident_management_agent.py   # Agent 3 — deviation → incident classifier
│   ├── requirements.txt
│   └── .env                           # LLM credentials (gitignored)
├── root_cause_agent.py                # Root-Cause Agent — per-run causal diagnosis
├── procedureguard_ui.py               # Streamlit triage UI (incl. Diagnoses tab)
├── notifications.py                   # Email notifications (Resend)
├── view_incidents.py                  # Terminal incident viewer
├── sample_verdicts_input.json         # RUN-102 verdicts (STEMFIE)
├── RUN-10x_verdicts.json              # Agent 2 output (input to Agent 3)
├── RUN-10x_incidents.json             # Agent 3 output (generated)
├── RUN-10x_grouped.json               # Root-Cause Agent output (generated)
└── tickets_db.json                    # UI state store (generated)
```

---

## Status & roadmap

**Now:** working demo. Flat-JSON persistence, demo logins, Azure OpenAI +
`gpt-4.1-mini`. Agent 3 classifies each deviation; the **Root-Cause Agent** then
reasons over the whole run to diagnose cause-vs-consequence (the first slice of
bounded, auditable agentic behavior — see Phase 2 below).

**Planned:**

- **Phase 1 — base Azure services:** ✅ Azure OpenAI (LLM, `gpt-4.1-mini`) now
  powers both agents. Remaining: Blob Storage (shared verdicts-in / incidents-out),
  Cosmos DB (replaces `tickets_db.json`), Key Vault, Azure Communication Services
  (email). Designed to keep local-file fallback so the demo still runs offline.
- **Phase 2 — bounded-agentic upgrades:** give the system real, auditable autonomy
  where it helps the workflow.
  - ✅ **Root-cause grouping** — diagnose each run as a whole (done).
  - ☐ **Unable-to-Verify handling** — re-request verification or flag for review
    instead of dropping these verdicts.
  - ☐ **SLA follow-up / escalation chasing** — remind, then auto-escalate on
    thresholds.
  - ☐ **Recurring-defect memory** — flag systemic issues across runs.
  - High-stakes actions (stop production, quarantine) stay human-gated.
