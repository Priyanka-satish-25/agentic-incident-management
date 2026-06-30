"""
AIMS — SLA Agent (standalone runner)
===============================================
Scans the ticket store, applies SLA policy (reminders + auto-escalation), saves,
and sends notifications. Runs once and exits — register it on a schedule (cron,
or the /schedule skill) so it acts even when nobody has the UI open.

Usage:
  python3 -m aims.agents.sla_runner                      # evaluate against the real clock
  python3 -m aims.agents.sla_runner --fast-forward 300   # DEMO: pretend 300 min have passed
  python3 -m aims.agents.sla_runner --quiet              # only print a one-line summary
  python3 -m aims.agents.sla_runner --reset              # undo all SLA actions (keeps triage)
  aims-sla                                               # console script (after `pip install -e .`)
  aims-sla --reset                                       # same, as a console command
"""

import argparse
import json
from datetime import datetime, timedelta, timezone

from aims.agents import sla
from aims.config import TICKETS_DB, INCIDENTS_DIR

DB_PATH = TICKETS_DB


def run(fast_forward: int = 0, quiet: bool = False) -> dict:
    if not DB_PATH.exists():
        print(f"[SLA Agent] No ticket store at {DB_PATH.name} — launch the UI first.")
        return {"reminded": 0, "escalated": 0, "breached": 0}

    db  = json.loads(DB_PATH.read_text())
    now = sla.utcnow() + timedelta(minutes=fast_forward)

    if fast_forward and not quiet:
        print(f"[SLA Agent] ⏩ Fast-forward: evaluating as if {fast_forward} min from now "
              f"({now.strftime('%Y-%m-%d %H:%M UTC')}).")

    actions = sla.evaluate_slas(db, now)

    if actions:
        DB_PATH.write_text(json.dumps(db, indent=2))
        sla.send_sla_notifications(db, actions)

    counts = {"reminded": 0, "escalated": 0, "breached": 0}
    for a in actions:
        counts[a["action"]] = counts.get(a["action"], 0) + 1
        if not quiet:
            icon = {"reminded": "🔔", "escalated": "⬆️", "breached": "⛔"}[a["action"]]
            print(f"  {icon} {a['ticket_id']}: {a['detail']}")

    if not quiet:
        open_tickets = sum(1 for t in db.values() if t.get("status") != "Closed")
        print(f"\n[SLA Agent] {open_tickets} open ticket(s) checked → "
              f"{counts['reminded']} reminded, {counts['escalated']} escalated, "
              f"{counts['breached']} breached.")
    else:
        print(f"[SLA Agent] {counts['reminded']} reminded, "
              f"{counts['escalated']} escalated, {counts['breached']} breached.")

    return counts


def reset_sla(quiet: bool = False) -> dict:
    """Undo every SLA action, returning tickets to their post-Agent-3 state.

    Surgical (not a wipe): human triage — comments and non-SLA history — is kept.
    For each ticket it clears the SLA tracking fields, restarts the SLA clock
    from now (so nothing instantly re-fires), drops the "SLA Agent (System)"
    history rows, and restores the original status/assignee from the Agent 3
    incident files. Tickets not found in those files keep their current status.
    """
    if not DB_PATH.exists():
        print(f"[SLA Agent] No ticket store at {DB_PATH.name} — nothing to reset.")
        return {"reset": 0}

    # Authoritative original status/assignee, straight from Agent 3 output.
    original = {}
    for f in INCIDENTS_DIR.glob("*_incidents.json"):
        for inc in json.loads(f.read_text()).get("incidents", []):
            original[f'{inc["run_id"]}__{inc["ticket_id"]}'] = (inc["status"], inc["assigned_to"])

    now = datetime.now(timezone.utc).isoformat()
    db = json.loads(DB_PATH.read_text())
    restored = 0
    for key, t in db.items():
        t["sla_window_started_at"] = now      # restart the clock from now
        t["reminder_sent_at"] = None
        t["escalation_count"] = 0
        t["history"] = [h for h in t.get("history", []) if h.get("by") != sla.ACTOR]
        if key in original:                   # undo SLA-driven status/assignee changes
            t["status"], t["assigned_to"] = original[key]
            restored += 1

    DB_PATH.write_text(json.dumps(db, indent=2))
    if not quiet:
        print(f"[SLA Agent] Reset SLA state on {len(db)} ticket(s) "
              f"({restored} restored from incident files). Comments kept.")
    return {"reset": len(db), "restored": restored}


def _cli() -> None:
    p = argparse.ArgumentParser(description="AIMS SLA follow-up agent.")
    p.add_argument("--fast-forward", type=int, default=0, metavar="MIN",
                   help="Simulate MIN minutes elapsed (for demos).")
    p.add_argument("--reset", action="store_true",
                   help="Undo all SLA actions (reminders/escalations), keeping triage.")
    p.add_argument("--quiet", action="store_true", help="Print only a summary line.")
    args = p.parse_args()
    if args.reset:
        reset_sla(quiet=args.quiet)
        return
    run(fast_forward=args.fast_forward, quiet=args.quiet)


if __name__ == "__main__":
    _cli()
