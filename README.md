# AIMS — Agentic Incident Management System

**Manufacturing compliance & incident management.**

A worker assembles a product on video, the build is checked against a Standard
Operating Procedure (SOP), and any deviation is turned into a tracked incident
ticket — severity-classified by an LLM and routed to the right role for triage.

This repository is **Layer 3 + the UI** of a larger pipeline (Layers 1 & 2 are
owned by teammates).

---

## Pipeline

```
Agent 1   →  extract SOP steps          →  data/checklists/*_steps.json
Agent 2   →  verify worker vs. SOP       →  data/verdicts/*_verdicts.json   (Compliant / Deviation / Unable-to-verify)
Agent 3   →  classify deviations         →  data/incidents/*_incidents.json  ┐
Root-Cause Agent → diagnose the run      →  data/diagnoses/*_grouped.json    ┘ ← THIS REPO
UI        →  triage, comment, escalate   →  data/tickets_db.json
```

All pipeline artifacts live under `data/` (see **Project layout**). The on-disk
locations are defined once in [`aims/config.py`](aims/config.py) — every module
imports the directory constants from there rather than hard-coding paths.

- **Agent 3** (`aims/agents/incident_management.py`) reads a verdicts
  JSON and calls an LLM per `Deviation` to produce a structured incident record
  (severity, reason, summary, recommended action). It also handles
  `Unable to Verify` verdicts (see below) instead of dropping them. Incidents are
  auto-assigned by severity:

  | Severity | Assigned to |
  |----------|-------------|
  | critical | Production Manager |
  | high     | QA Manager |
  | medium   | Supervisor |
  | low      | QA Log |

- **Root-Cause Agent** (`aims/agents/root_cause.py`) reasons over *all* of a run's
  incidents together to separate independent **root causes** from their downstream
  **consequences** (e.g. a state-strip checkpoint failure that merely *reports*
  earlier component omissions). It runs automatically at the end of each Agent 3
  run, writing `*_grouped.json`. Bounded autonomy: read-only, guardrailed (every
  incident appears exactly once — nothing dropped or invented), and every causal
  link carries a written rationale.

- **Unable-to-Verify handling** — when Agent 2 couldn't confirm a step (occlusion,
  low confidence), Agent 3 no longer drops it. It asks the LLM to rate the *risk of
  leaving the step unverified* (with a written rationale). **Low risk** is
  auto-closed by the system (logged to QA Log); **medium or higher** is flagged
  `Needs Review` and routed to a human — the system never guesses compliance when
  evidence is missing. These records live in the same `*_incidents.json` (marked
  `verdict: "Unable to Verify"`) and are excluded from the root-cause causal tree.

- **UI** (`aims/ui/app.py`) is a Streamlit app for role-based triage:
  view tickets, comment, close, and escalate up the chain
  (QA Log → Supervisor → QA Manager → Production Manager). A **Diagnoses** tab
  renders each run's causal tree, and grouped tickets show cause/effect links in
  their detail view. A **Needs Review** tab lists unverifiable steps awaiting a
  human call — *Mark Compliant* or *Promote to Incident*.

- **SLA Agent** (`aims/agents/sla.py` + `aims/agents/sla_runner.py`) chases open tickets as they age.
  Per-severity thresholds (critical 30m/1h → low 36h/72h) drive a two-stage
  policy: first a **reminder** to the assignee, then **auto-escalation** up the
  chain if still unaddressed. It runs on every UI load *and* as a standalone
  agent you can schedule (cron / `/schedule`), so escalation happens even with
  nobody watching. Bounded: escalation only nudges a ticket upward (never closes
  it or stops production), every action is logged as "SLA Agent (System)", and it
  is idempotent. `python3 -m aims.agents.sla_runner --fast-forward <min>` simulates elapsed
  time for demos.

- **Notifications** (`aims/agents/notifications.py`) sends email on ticket creation,
  escalation, and SLA reminders via the Resend API (optional — skipped gracefully
  if unconfigured).

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

Install the project as an editable package — this pulls in all dependencies
(`openai`, `python-dotenv`, `resend`, `streamlit`) and registers the `aims-*`
console commands:

```bash
pip install -e .
# add the optional UI-test extra (Playwright) with:  pip install -e ".[test]"
```

### Configure the LLM backend

Agent 3 and the Root-Cause Agent use **Azure OpenAI**.
Copy the example env (at the repo root) and add your Azure credentials:

```bash
cp .env.example .env
```

Edit `.env`:

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

Reads from `data/verdicts/`; writes incidents to `data/incidents/` and the
diagnosis to `data/diagnoses/`. Run everything from the **repo root**:

```bash
# console script (after `pip install -e .`) …            … or the module form:
aims-incident data/verdicts/RUN-102_verdicts.json   # python3 -m aims.agents.incident_management data/verdicts/RUN-102_verdicts.json
aims-incident data/verdicts/RUN-103_verdicts.json   # → RUN-103_* (incidents + grouped)
aims-incident data/verdicts/RUN-104_verdicts.json   # → RUN-104_*
aims-incident data/verdicts/RUN-105_verdicts.json   # → RUN-105_*
```

To (re)generate only the diagnosis for an existing incidents file:

```bash
aims-root-cause data/incidents/RUN-103_incidents.json   # → data/diagnoses/RUN-103_grouped.json (prints the causal tree)
```

### 2. View incidents in the terminal (optional)

```bash
aims-view data/incidents/RUN-103_incidents.json         # or: python3 -m aims.ui.view_incidents <file>
```

### 3. Launch the triage UI

```bash
streamlit run aims/ui/app.py
```

Opens at `http://localhost:8501`. On first launch it scans
`data/incidents/*_incidents.json` and builds `data/tickets_db.json`.

**Demo credentials:**

| User / pass   | Role               |
|---------------|--------------------|
| `alice` / `alice` | Production Manager |
| `bob`   / `bob`   | QA Manager         |
| `carol` / `carol` | Supervisor         |
| `dave`  / `dave`  | QA Log             |

> Deleting `data/incidents/*_incidents.json` does **not** clear the UI's store. To
> start clean, also delete `data/tickets_db.json` — it rebuilds from the incident
> files on next launch.

### 4. Run the SLA agent (optional)

The UI applies SLA policy on every load, but you can also run the agent on its
own so tickets are chased while the UI is closed:

```bash
aims-sla                      # evaluate against the real clock
aims-sla --fast-forward 300   # demo: simulate 300 min elapsed
aims-sla --reset              # undo all SLA actions (re-demo from a clean slate)
#  (module form: python3 -m aims.agents.sla_runner [--fast-forward 300 | --reset])
```

Schedule it (e.g. every 15 min via cron or `/schedule`) for hands-off escalation.

`--reset` is surgical: it clears each ticket's SLA fields, restarts the SLA clock
from now, removes the `SLA Agent (System)` history rows, and restores the original
status/assignee from `data/incidents/` — **keeping your comments and triage**. Use
it to rewind after a `--fast-forward` demo.

---

## Project layout

```
agentic-incident-management/
├── pyproject.toml                     # deps + console scripts (aims-incident, aims-sla, …)
├── .env.example                       # copy to .env (LLM + email creds; gitignored)
├── aims/                              # the importable package
│   ├── config.py                      # single source of truth for paths + .env location
│   ├── agents/
│   │   ├── incident_management.py     # Agent 3 — deviation → incident classifier
│   │   ├── root_cause.py              # Root-Cause Agent — per-run causal diagnosis
│   │   ├── sla.py                     # SLA policy engine (reminders + escalation)
│   │   ├── sla_runner.py              # SLA Agent — standalone/schedulable runner
│   │   └── notifications.py           # Email notifications (Resend)
│   └── ui/
│       ├── app.py                     # Streamlit triage UI (incl. Diagnoses tab)
│       ├── incident_viewer.py         # Streamlit single-file incident viewer
│       └── view_incidents.py          # Terminal incident viewer
├── tests/
│   └── test_ui.py                     # Playwright UI smoke test
└── data/                              # all pipeline artifacts (keyed by run_id)
    ├── checklists/   RUN-10x_steps.json, RUN-10x_compliance_checklist.json  # Agent 1
    ├── verdicts/     RUN-10x_verdicts.json     # Agent 2 output  → Agent 3 input
    ├── incidents/    RUN-10x_incidents.json    # Agent 3 output (generated)
    ├── diagnoses/    RUN-10x_grouped.json       # Root-Cause output (generated)
    └── tickets_db.json                          # UI state store (generated, gitignored)
```

---

## Status & roadmap

**Now:** working demo. Flat-JSON persistence, demo logins, Azure OpenAI +
`gpt-4.1-mini`. Agent 3 classifies each deviation; the **Root-Cause Agent** then
reasons over the whole run to diagnose cause-vs-consequence (the first slice of
bounded, auditable agentic behavior — see Phase 2 below).

**Planned:**

- **Phase 1 — base Azure services:** Azure OpenAI (LLM, `gpt-4.1-mini`) now
  powers both agents. Remaining: Blob Storage (shared verdicts-in / incidents-out),
  Cosmos DB (replaces `tickets_db.json`), Key Vault, Azure Communication Services
  (email). Designed to keep local-file fallback so the demo still runs offline.
- **Phase 2 — bounded-agentic upgrades:** give the system real, auditable autonomy
  where it helps the workflow.
  - **Root-cause grouping** — diagnose each run as a whole (done).
  - **Unable-to-Verify handling** — risk-rate unverifiable steps; auto-close
    low-risk, flag the rest for human review instead of dropping them (done).
  - **SLA follow-up / escalation chasing** — remind, then auto-escalate on
    per-severity thresholds; runs on UI load and as a schedulable agent (done).
  - High-stakes actions (stop production, quarantine) stay human-gated.
