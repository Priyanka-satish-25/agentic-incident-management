"""
ProcedureGuard — SLA Agent (standalone runner)
===============================================
Scans the ticket store, applies SLA policy (reminders + auto-escalation), saves,
and sends notifications. Runs once and exits — register it on a schedule (cron,
or the /schedule skill) so it acts even when nobody has the UI open.

Usage:
  python3 sla_agent.py                      # evaluate against the real clock
  python3 sla_agent.py --fast-forward 300   # DEMO: pretend 300 min have passed
  python3 sla_agent.py --quiet              # only print a one-line summary
"""

import argparse
import json
from datetime import timedelta
from pathlib import Path

import sla

DB_PATH = Path(__file__).parent / "tickets_db.json"


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


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="ProcedureGuard SLA follow-up agent.")
    p.add_argument("--fast-forward", type=int, default=0, metavar="MIN",
                   help="Simulate MIN minutes elapsed (for demos).")
    p.add_argument("--quiet", action="store_true", help="Print only a summary line.")
    args = p.parse_args()
    run(fast_forward=args.fast_forward, quiet=args.quiet)
