"""
Root-Cause Analysis Agent  (Phase 2, slice #1)
==============================================
Reads an incidents file produced by Agent 3 and reasons over ALL of a run's
incidents at once to produce a causal diagnosis — distinguishing independent
root causes from their downstream consequences (e.g. a state-strip checkpoint
failure that is merely *reporting* the component omissions upstream of it).

This is bounded, auditable autonomy:
  • READ-ONLY  — it groups and links; it never deletes, downgrades or invents.
  • GUARDRAIL  — every input incident must appear exactly once in the output;
                 anything the model drops is fault-tolerantly re-added as its
                 own root cause (never silently lost).
  • AUDITABLE  — every link carries a written rationale, saved to the output.

It does NOT modify the original incidents file. It writes <run_id>_grouped.json.

Run:
  python3 -m aims.agents.root_cause data/incidents/RUN-103_incidents.json
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AzureOpenAI

from aims.config import INCIDENTS_DIR, DIAGNOSES_DIR, ENV_FILE

load_dotenv(ENV_FILE)

# ── Azure OpenAI client ──────────────────────────────────────────────────────
client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21"),
)
# On Azure, `model` is the *deployment name* you created (not the base model id).
MODEL = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini")


SYSTEM_PROMPT = """\
You are a root-cause analysis engine for a manufacturing compliance system.

You are given ALL of the incidents detected in a single production run. Each
incident is one deviation from a Standard Operating Procedure (SOP). Your job is
to reason across them together and organize them into causal groups.

Key principle: a verification, checkpoint, audit, or "state-strip" step does not
introduce a new defect — it REPORTS the state of components handled in earlier
steps. So when such a step fails, it is almost always a CONSEQUENCE (a symptom)
of the specific component-level deviations it is reporting, not an independent
root cause. Link it to those underlying deviations.

Classify every incident into one of three roles within its group:
  "root_cause"  — an independent defect with its own corrective action.
  "consequence" — a symptom/detection of one or more root causes (give caused_by).
  "contributing"— a deviation that worsens or enables another, but isn't the root.

Group incidents that share a root cause together. Independent, unrelated defects
each form their own single-member group.

Return ONLY this JSON object — no markdown, no commentary:
{
  "diagnosis": "<2-3 sentences: how many distinct root causes this run has and the headline finding>",
  "groups": [
    {
      "label": "<short human label for the underlying problem>",
      "root_cause_tickets": ["<ticket_id>", ...],
      "members": [
        {
          "ticket_id": "<ticket_id>",
          "role": "root_cause|consequence|contributing",
          "caused_by": ["<ticket_id>", ...],   // [] unless role is consequence/contributing
          "reason": "<one sentence explaining this ticket's role and any linkage>"
        }
      ]
    }
  ]
}

Every ticket_id given to you must appear exactly once across all members.\
"""


def _incident_digest(inc: dict) -> dict:
    """The minimal view the agent needs to reason about one incident."""
    return {
        "ticket_id":         inc["ticket_id"],
        "step_id":           inc["step_id"],
        "sequence_position": inc["sequence_position"],
        "section":           inc["section"],
        "sop_step":          inc["sop_step"],
        "severity":          inc["severity"],
        "severity_reason":   inc["severity_reason"],
        "incident_summary":  inc["incident_summary"],
    }


def analyze(run_id: str, incidents: list[dict]) -> dict:
    digests = [_incident_digest(i) for i in incidents]
    user_prompt = (
        f"Production run: {run_id}\n"
        f"Incidents in this run ({len(digests)}):\n\n"
        f"{json.dumps(digests, indent=2)}\n\n"
        "Produce the causal grouping JSON."
    )
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
    )
    return json.loads(response.choices[0].message.content)


def enforce_guardrail(run_id: str, incidents: list[dict], result: dict) -> dict:
    """Every incident must appear exactly once. Repair, never lose data."""
    expected = {i["ticket_id"] for i in incidents}
    seen, deduped_groups = set(), []

    for group in result.get("groups", []):
        members = []
        for m in group.get("members", []):
            tid = m.get("ticket_id")
            if tid in expected and tid not in seen:
                seen.add(tid)
                members.append(m)
            # drop duplicates / hallucinated ids silently from the structure
        if members:
            group["members"] = members
            deduped_groups.append(group)

    # Any incident the model failed to place becomes its own root-cause group.
    missing = expected - seen
    by_id = {i["ticket_id"]: i for i in incidents}
    for tid in sorted(missing):
        deduped_groups.append({
            "label": by_id[tid]["sop_step"][:60],
            "root_cause_tickets": [tid],
            "members": [{
                "ticket_id": tid, "role": "root_cause", "caused_by": [],
                "reason": "Not grouped by the agent; retained as an independent root cause (guardrail).",
            }],
            "_guardrail_added": True,
        })

    return {
        "run_id": run_id,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "model": MODEL,
        "total_incidents": len(incidents),
        "root_cause_count": sum(len(g.get("root_cause_tickets", [])) for g in deduped_groups),
        "group_count": len(deduped_groups),
        "diagnosis": result.get("diagnosis", ""),
        "groups": deduped_groups,
    }


SEV_ICON = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
ROLE_TAG = {"root_cause": "ROOT CAUSE", "consequence": "└─ consequence", "contributing": "├─ contributing"}


def print_tree(out: dict, incidents: list[dict]) -> None:
    by_id = {i["ticket_id"]: i for i in incidents}
    print("\n" + "=" * 68)
    print(f"  ROOT-CAUSE DIAGNOSIS — {out['run_id']}")
    print("=" * 68)
    print(f"  {out['total_incidents']} incidents  →  {out['root_cause_count']} root cause(s)"
          f" in {out['group_count']} group(s)\n")
    print(f"  {out['diagnosis']}\n")

    for n, g in enumerate(out["groups"], 1):
        flag = "  (guardrail)" if g.get("_guardrail_added") else ""
        print("-" * 68)
        print(f"  GROUP {n}: {g['label']}{flag}")
        # root causes first, then consequences/contributing
        order = {"root_cause": 0, "contributing": 1, "consequence": 2}
        for m in sorted(g["members"], key=lambda x: order.get(x["role"], 9)):
            inc = by_id.get(m["ticket_id"], {})
            sev = inc.get("severity", "?")
            icon = SEV_ICON.get(sev, " ")
            tag = ROLE_TAG.get(m["role"], m["role"])
            cb = f"  ⟵ caused by {', '.join(m['caused_by'])}" if m.get("caused_by") else ""
            print(f"    {icon} {m['ticket_id']}  [{tag}]  {sev.upper()}{cb}")
            print(f"        {inc.get('sop_step','')[:62]}")
            print(f"        ↳ {m['reason']}")
        print()
    print("=" * 68 + "\n")


def analyze_and_save(run_id: str, incidents: list[dict], output_dir, quiet: bool = False) -> dict:
    """Analyze a run's incidents, apply the guardrail, write <run_id>_grouped.json.

    Reusable entry point — called both by this script's CLI and by Agent 3's
    pipeline. Pass quiet=True to suppress the terminal tree (pipeline use).
    """
    if not quiet:
        print(f"[Root-Cause Agent] {run_id} | analyzing {len(incidents)} incident(s) with {MODEL}...")
    raw = analyze(run_id, incidents)
    out = enforce_guardrail(run_id, incidents, raw)

    out_path = Path(output_dir) / f"{run_id}_grouped.json"
    out_path.write_text(json.dumps(out, indent=2))

    if not quiet:
        print(f"[Root-Cause Agent] Diagnosis saved → {out_path.name}")
        print_tree(out, incidents)
    return out


def run(incidents_path: str) -> dict:
    path = Path(incidents_path).resolve()
    data = json.loads(path.read_text())
    DIAGNOSES_DIR.mkdir(parents=True, exist_ok=True)
    return analyze_and_save(data["run_id"], data["incidents"], DIAGNOSES_DIR)


def _cli() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else str(INCIDENTS_DIR / "RUN-103_incidents.json")
    run(target)


if __name__ == "__main__":
    _cli()
