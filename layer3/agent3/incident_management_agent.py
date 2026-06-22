"""
Agent 3 — Incident Management Agent
=====================================
Reads compliance verdicts from Agent 2, identifies deviations,
classifies severity, generates incident records, and prints a report.

Flow:
  1. Load verdicts JSON
  2. Filter for "Deviation" verdicts
  3. Call Gemini per deviation → severity classification + incident summary
  4. Save all incidents to a local JSON file
  5. Print incident report to terminal (highlights High/Critical)

Run:
  python3 incident_management_agent.py ../../sample_verdicts_input.json
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI

load_dotenv()

# Notifications (optional — gracefully skipped if .env not configured)
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
try:
    from notifications import notify_ticket_created
    _NOTIFY = True
except ImportError:
    _NOTIFY = False

# ── Azure OpenAI client ───────────────────────────────────────────────────────
client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
)
# On Azure, `model` is the *deployment name* you created (not the base model id).
MODEL = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")

# ── Ticket ID counter (in production this would come from a DB sequence) ───────
_ticket_counter = 2044


def _next_ticket_id() -> str:
    global _ticket_counter
    _ticket_counter += 1
    return f"INC-{_ticket_counter}"


# ── Prompts ────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an incident classification engine for a manufacturing compliance system.

A worker has deviated from a Standard Operating Procedure (SOP) during production.
Your job: assess the business impact of the deviation and produce a structured incident record.

Severity levels:
  "critical" → immediate safety risk or structural failure. Production must stop.
  "high"     → functional failure likely if not corrected. QA manager must review.
  "medium"   → quality degradation possible. Supervisor should be notified.
  "low"      → cosmetic or minor impact. Log only.

Return ONLY a JSON object with these exact fields — no markdown, no explanation:
{
  "severity": "<critical|high|medium|low>",
  "severity_reason": "<one sentence explaining the severity rating>",
  "incident_summary": "<2-3 sentences describing what happened, what was missed, and why it matters>",
  "recommended_action": "<one sentence on what should be done next>"
}\
"""


def _build_user_prompt(deviation: dict) -> str:
    duration_context = ""
    if deviation["check_type"] == "duration":
        expected = deviation.get("expected_duration_seconds")
        actual   = deviation.get("actual_duration_seconds")
        duration_context = f"\nExpected duration: {expected}s | Actual duration: {actual}s"

    return f"""\
Classify this SOP deviation and generate an incident record.

SOP Step:            {deviation['description']}
Compliance Criterion:{deviation['compliance_criterion']}
Agent 2 Verdict:     {deviation['reasoning']}{duration_context}
Timestamp in video:  {deviation['timestamp']}
Detection confidence:{deviation['confidence']}%

Return the JSON incident record.\
"""


# ── Core logic ─────────────────────────────────────────────────────────────────

def classify_deviation(deviation: dict) -> dict:
    """Call Gemini to classify one deviation and generate an incident record."""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": _build_user_prompt(deviation)},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    return json.loads(response.choices[0].message.content)


def build_incident(deviation: dict, classification: dict, ticket_id: str) -> dict:
    """Combine verdict data + Gemini classification into a full incident record."""
    return {
        "ticket_id":          ticket_id,
        "run_id":             None,           # filled in by run()
        "step_id":            deviation["step_id"],
        "sequence_position":  deviation["sequence_position"],
        "section":            deviation["section"],
        "sop_step":           deviation["description"],
        "verdict":            "Deviation",
        "timestamp":          deviation["timestamp"],
        "confidence":         deviation["confidence"],
        "severity":           classification["severity"],
        "severity_reason":    classification["severity_reason"],
        "incident_summary":   classification["incident_summary"],
        "recommended_action": classification["recommended_action"],
        "status":             "Open",
        "assigned_to":        _assign_to(classification["severity"]),
        "created_at":         datetime.now(timezone.utc).isoformat(),
    }


def _assign_to(severity: str) -> str:
    return {
        "critical": "Production Manager",
        "high":     "QA Manager",
        "medium":   "Supervisor",
        "low":      "QA Log",
    }.get(severity, "QA Manager")


def _save_incidents(run_id: str, incidents: list[dict], output_dir: Path) -> Path:
    output = {
        "run_id":        run_id,
        "generated_at":  datetime.now(timezone.utc).isoformat(),
        "total_incidents": len(incidents),
        "incidents":     incidents,
    }
    out_path = output_dir / f"{run_id}_incidents.json"
    out_path.write_text(json.dumps(output, indent=2))
    return out_path


def _print_report(run_id: str, incidents: list[dict]) -> None:
    """Print a formatted incident report to the terminal."""
    SEVERITY_ICON = {
        "critical": "🔴 CRITICAL",
        "high":     "🟠 HIGH",
        "medium":   "🟡 MEDIUM",
        "low":      "🟢 LOW",
    }

    print("\n" + "=" * 60)
    print(f"  INCIDENT REPORT — {run_id}")
    print("=" * 60)
    print(f"  Total incidents: {len(incidents)}")

    counts = {}
    for inc in incidents:
        counts[inc["severity"]] = counts.get(inc["severity"], 0) + 1
    for sev in ["critical", "high", "medium", "low"]:
        if sev in counts:
            print(f"  {SEVERITY_ICON[sev]}: {counts[sev]}")

    print("=" * 60)

    for inc in incidents:
        sev   = inc["severity"]
        icon  = SEVERITY_ICON[sev]
        print(f"\n  [{icon}] {inc['ticket_id']} — {inc['sop_step']}")
        print(f"  Timestamp:  {inc['timestamp']}  |  Confidence: {inc['confidence']}%")
        print(f"  Summary:    {inc['incident_summary']}")
        print(f"  Action:     {inc['recommended_action']}")
        print(f"  Assigned:   {inc['assigned_to']}  |  Status: {inc['status']}")

        if sev in ("critical", "high"):
            print(f"  ⚠  ESCALATION REQUIRED — notifying {inc['assigned_to']}")

    print("\n" + "=" * 60 + "\n")


# ── Entry point ────────────────────────────────────────────────────────────────

def run(verdicts_json_path: str) -> dict:
    path = Path(verdicts_json_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Verdicts JSON not found: {path}")

    print(f"\n[Agent 3] Loading: {path.name}")
    data   = json.loads(path.read_text())
    run_id = data["run_id"]
    all_verdicts = data["verdicts"]

    deviations = [v for v in all_verdicts if v["verdict"] == "Deviation"]
    print(f"[Agent 3] run_id={run_id} | deviations={len(deviations)} of {len(all_verdicts)} steps")

    if not deviations:
        print("[Agent 3] No deviations found — nothing to process.")
        return {"run_id": run_id, "incident_count": 0}

    incidents = []
    for dev in deviations:
        print(f"[Agent 3] Classifying {dev['step_id']} ({dev['timestamp']})...")
        classification = classify_deviation(dev)
        ticket_id      = _next_ticket_id()
        incident       = build_incident(dev, classification, ticket_id)
        incident["run_id"] = run_id
        incidents.append(incident)
        print(f"  → {ticket_id} | severity={classification['severity'].upper()}")

        if _NOTIFY:
            notify_ticket_created(incident)

    out_path = _save_incidents(run_id, incidents, path.parent)
    print(f"\n[Agent 3] Incidents saved → {out_path.name}")

    _print_report(run_id, incidents)

    result = {
        "run_id":         run_id,
        "incident_count": len(incidents),
        "incidents_path": str(out_path),
    }

    # ── Root-cause analysis (Phase 2) ──────────────────────────────────────────
    # Reason over the whole run to separate root causes from their consequences.
    # Best-effort: a failure here must not invalidate the incidents already saved.
    try:
        from root_cause_agent import analyze_and_save
        grouped = analyze_and_save(run_id, incidents, path.parent, quiet=True)
        grouped_path = path.parent / f"{run_id}_grouped.json"
        result["grouped_path"] = str(grouped_path)
        print(f"[Agent 3] Root-cause diagnosis → {grouped_path.name} "
              f"({grouped['root_cause_count']} root cause(s) in {grouped['group_count']} group(s))")
    except Exception as e:
        print(f"[Agent 3] Root-cause analysis skipped ({e.__class__.__name__}: {e})")

    return result


if __name__ == "__main__":
    input_path = sys.argv[1] if len(sys.argv) > 1 else "../../sample_verdicts_input.json"
    result = run(input_path)
    print(json.dumps(result, indent=2))
