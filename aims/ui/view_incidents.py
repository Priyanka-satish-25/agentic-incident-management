"""
view_incidents.py — pretty-print an incidents JSON file in the terminal

Run:
  python3 -m aims.ui.view_incidents data/incidents/RUN-102_incidents.json
"""

import json
import sys
from pathlib import Path

SEVERITY_BADGE = {
    "critical": "\033[41m\033[97m CRITICAL \033[0m",
    "high":     "\033[43m\033[30m   HIGH   \033[0m",
    "medium":   "\033[33m\033[1m  MEDIUM  \033[0m",
    "low":      "\033[32m\033[1m   LOW    \033[0m",
}

STATUS_COLOUR = {
    "Open":     "\033[31mOpen\033[0m",
    "Resolved": "\033[32mResolved\033[0m",
    "Closed":   "\033[90mClosed\033[0m",
}

W = 70  # terminal width


def bar(char="─", width=W):
    print(char * width)


def wrap(text, width=W - 14, prefix=""):
    """Simple word-wrap for long strings."""
    words, lines, line = text.split(), [], ""
    for w in words:
        if len(line) + len(w) + 1 > width:
            lines.append(prefix + line.strip())
            line = w + " "
        else:
            line += w + " "
    if line.strip():
        lines.append(prefix + line.strip())
    return "\n".join(lines)


def print_report(path: str):
    data = json.loads(Path(path).read_text())
    run_id    = data["run_id"]
    incidents = data["incidents"]
    total     = data["total_incidents"]
    generated = data["generated_at"][:19].replace("T", " ")

    counts = {}
    for inc in incidents:
        counts[inc["severity"]] = counts.get(inc["severity"], 0) + 1

    # ── Header ────────────────────────────────────────────────────────────────
    print()
    bar("═")
    print(f"  INCIDENT REPORT   run={run_id}   generated={generated} UTC")
    bar("═")
    print(f"  Total incidents: {total}   ", end="")
    for sev in ["critical", "high", "medium", "low"]:
        if sev in counts:
            print(f"{SEVERITY_BADGE[sev]} ×{counts[sev]}  ", end="")
    print("\n")

    # ── Each incident ─────────────────────────────────────────────────────────
    for i, inc in enumerate(incidents, 1):
        sev    = inc["severity"]
        badge  = SEVERITY_BADGE.get(sev, sev.upper())
        status = STATUS_COLOUR.get(inc["status"], inc["status"])

        bar()
        print(f"  {badge}  {inc['ticket_id']}  ·  Step {inc['sequence_position']} — {inc['step_id']}")
        bar()
        print(f"  Section   : {inc['section']}")
        print(f"  SOP step  : {inc['sop_step']}")
        print()
        print(f"  Timestamp : {inc['timestamp']}   Confidence: {inc['confidence']}%")
        print(f"  Status    : {status}   Assigned: {inc['assigned_to']}")
        print()
        print(f"  Why       : {inc['severity_reason']}")
        print()
        print("  Summary   :")
        print(wrap(inc["incident_summary"], prefix="    "))
        print()
        print("  Action    :")
        print(wrap(inc["recommended_action"], prefix="    "))
        print()

    bar("═")
    print(f"  End of report — {total} incident(s) for {run_id}")
    bar("═")
    print()


def _cli() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "data/incidents/RUN-102_incidents.json"
    print_report(path)


if __name__ == "__main__":
    _cli()
