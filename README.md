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
Agent 1  →  extract SOP steps          →  *_steps_input.json
Agent 2  →  verify worker vs. SOP       →  *_verdicts.json   (Compliant / Deviation / Unable-to-verify)
Agent 3  →  classify deviations         →  *_incidents.json  ← THIS REPO
UI       →  triage, comment, escalate   →  tickets_db.json
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

- **UI** (`procedureguard_ui.py`) is a Streamlit app for role-based triage:
  view tickets, comment, close, and escalate up the chain
  (QA Log → Supervisor → QA Manager → Production Manager).

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

Agent 3 currently uses **GitHub Marketplace Models** (free, rate-limited).
Copy the example env and add a token:

```bash
cp layer3/agent3/.env.example layer3/agent3/.env
```

Edit `layer3/agent3/.env`:

```ini
GITHUB_TOKEN=<your GitHub PAT with "Models: Read-only" permission>
GITHUB_MODEL=gpt-4o-mini
```

> Get a token at https://github.com/settings/personal-access-tokens
> (fine-grained → Account permissions → **Models: Read-only**).
> `.env` is gitignored — never commit it.

---

## Usage

### 1. Generate incidents from verdicts (Agent 3)

Run once per verdicts file. Output is written next to the input as
`<run_id>_incidents.json`:

```bash
cd layer3/agent3
python3 incident_management_agent.py ../../sample_verdicts_input.json   # → RUN-102_incidents.json
python3 incident_management_agent.py ../../RUN-103_verdicts.json        # → RUN-103_incidents.json
python3 incident_management_agent.py ../../RUN-104_verdicts.json        # → RUN-104_incidents.json
python3 incident_management_agent.py ../../RUN-105_verdicts.json        # → RUN-105_incidents.json
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
├── procedureguard_ui.py               # Streamlit triage UI
├── notifications.py                   # Email notifications (Resend)
├── view_incidents.py                  # Terminal incident viewer
├── sample_verdicts_input.json         # RUN-102 verdicts (STEMFIE)
├── RUN-10x_verdicts.json              # Agent 2 output (input to Agent 3)
├── RUN-10x_incidents.json             # Agent 3 output (generated)
└── tickets_db.json                    # UI state store (generated)
```

---

## Status & roadmap

**Now:** working demo. Flat-JSON persistence, demo logins, GitHub Models +
`gpt-4o-mini`. Not yet agentic — Agent 3 is a single fixed-prompt classification
call per deviation.

**Planned:**

- **Phase 1 — base Azure services:** Azure OpenAI (LLM), Blob Storage (shared
  verdicts-in / incidents-out), Cosmos DB (replaces `tickets_db.json`), Key Vault,
  Azure Communication Services (email). Designed to keep local-file fallback so
  the demo still runs offline. *Currently parked.*
- **Phase 2 — agentic Agent 3:** rebuild as a tool-calling agent (context lookups,
  autonomous routing / escalation) using Azure OpenAI function calling or Azure AI
  Foundry Agent Service — only if real decision-making is wanted beyond fixed
  classification.
