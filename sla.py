"""
AIMS — SLA Follow-up & Escalation Chasing (Phase 2)
=============================================================
Bounded autonomy for open tickets: as a ticket ages, the system first *reminds*
the assignee, then *auto-escalates* up the chain if it's still unaddressed —
without a human kicking it off.

This module is the shared brain. It is used by:
  • aims_ui.py            — evaluated on every page load (catch-up)
  • sla_agent.py          — runnable standalone / on a schedule (proactive)

Design guarantees (the "bounded, auditable" part):
  • Idempotent — a reminder fires once per SLA window; no double-escalation.
  • Auditable — every autonomous change is written to the ticket's history,
    attributed to "SLA Agent (System)".
  • Human-gated — escalation only nudges a ticket UP the chain. It never closes
    a ticket or stops production; those stay human decisions.
"""

from datetime import datetime, timedelta, timezone

# Escalation chain — mirrors aims_ui.ESCALATION_PATH.
ESCALATION_PATH = {
    "QA Log":             "Supervisor",
    "Supervisor":         "QA Manager",
    "QA Manager":         "Production Manager",
    "Production Manager": None,
}

# Per-severity SLA policy, in minutes: (remind_after, escalate_after).
# Tighter for severe tickets, looser for minor ones.
SLA_POLICY = {
    "critical": {"remind": 30,   "escalate": 60},
    "high":     {"remind": 120,  "escalate": 240},
    "medium":   {"remind": 720,  "escalate": 1440},
    "low":      {"remind": 2160, "escalate": 4320},
}

ACTOR = "SLA Agent (System)"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str) -> datetime:
    """Parse an ISO timestamp into an aware UTC datetime."""
    dt = datetime.fromisoformat(ts)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _stamp(now: datetime) -> str:
    """History-friendly timestamp, matching the UI's format."""
    return now.strftime("%Y-%m-%d %H:%M UTC")


def _window_start(ticket: dict) -> str:
    """The ISO timestamp the current SLA window started (lazy-init for old tickets)."""
    return ticket.get("sla_window_started_at") or ticket.get("created_at")


def sla_status(ticket: dict, now: datetime | None = None) -> dict:
    """Read-only SLA view for one ticket: time remaining and urgency level.

    Returns {"label": str, "level": "ok"|"due"|"over"|"breached"|"closed"}.
    """
    now = now or utcnow()
    if ticket.get("status") == "Closed":
        return {"label": "—", "level": "closed"}
    if ticket.get("status") == "SLA Breached":
        return {"label": "SLA BREACHED", "level": "breached"}

    policy   = SLA_POLICY.get(ticket["severity"], SLA_POLICY["medium"])
    start    = _parse(_window_start(ticket))
    deadline = start + timedelta(minutes=policy["escalate"])
    remaining = deadline - now

    if remaining.total_seconds() <= 0:
        return {"label": "OVERDUE", "level": "over"}

    mins = int(remaining.total_seconds() // 60)
    label = f"due in {mins // 60}h {mins % 60}m" if mins >= 60 else f"due in {mins}m"
    # "due" once we're past the reminder threshold, else just "ok".
    reminder_deadline = start + timedelta(minutes=policy["remind"])
    level = "due" if now >= reminder_deadline else "ok"
    return {"label": label, "level": level}


def evaluate_slas(db: dict, now: datetime | None = None) -> list[dict]:
    """Apply SLA policy to every open ticket, mutating tickets in place.

    Returns a list of action dicts describing what changed, e.g.
      {"key": ..., "ticket_id": ..., "action": "reminded"|"escalated"|"breached",
       "detail": "..."}.
    No I/O and no notifications here — that keeps this testable. Callers persist
    the db and fire notifications based on the returned actions.
    """
    now = now or utcnow()
    actions: list[dict] = []

    for key, ticket in db.items():
        if ticket.get("status") == "Closed":
            continue

        policy = SLA_POLICY.get(ticket["severity"], SLA_POLICY["medium"])

        # Lazy-init SLA fields for tickets created before this feature existed.
        if not ticket.get("sla_window_started_at"):
            ticket["sla_window_started_at"] = ticket.get("created_at") or now.isoformat()
        ticket.setdefault("reminder_sent_at", None)
        ticket.setdefault("escalation_count", 0)

        start   = _parse(ticket["sla_window_started_at"])
        elapsed = now - start

        # ── Escalation takes priority over a reminder ───────────────────────────
        if elapsed >= timedelta(minutes=policy["escalate"]):
            next_role = ESCALATION_PATH.get(ticket["assigned_to"])
            if next_role:
                old = ticket["assigned_to"]
                ticket["assigned_to"]          = next_role
                ticket["status"]               = "Escalated"
                ticket["sla_window_started_at"] = now.isoformat()  # reset the clock
                ticket["reminder_sent_at"]     = None
                ticket["escalation_count"]    += 1
                detail = f"SLA breach: auto-escalated {old} → {next_role}"
                ticket.setdefault("history", []).append(
                    {"action": detail, "by": ACTOR, "at": _stamp(now)})
                actions.append({"key": key, "ticket_id": ticket["ticket_id"],
                                "action": "escalated", "detail": detail})
            elif ticket["status"] != "SLA Breached":
                # Top of the chain — can't escalate further. Flag it (once).
                ticket["status"] = "SLA Breached"
                detail = "SLA breach at top of chain — no further escalation possible"
                ticket.setdefault("history", []).append(
                    {"action": detail, "by": ACTOR, "at": _stamp(now)})
                actions.append({"key": key, "ticket_id": ticket["ticket_id"],
                                "action": "breached", "detail": detail})

        # ── Reminder (once per window) ──────────────────────────────────────────
        elif elapsed >= timedelta(minutes=policy["remind"]) and not ticket["reminder_sent_at"]:
            ticket["reminder_sent_at"] = now.isoformat()
            detail = f"SLA reminder sent to {ticket['assigned_to']}"
            ticket.setdefault("history", []).append(
                {"action": detail, "by": ACTOR, "at": _stamp(now)})
            actions.append({"key": key, "ticket_id": ticket["ticket_id"],
                            "action": "reminded", "detail": detail})

    return actions


def send_sla_notifications(db: dict, actions: list[dict]) -> None:
    """Best-effort email for each SLA action (gracefully skipped if unconfigured)."""
    try:
        from notifications import notify_ticket_escalated, notify_ticket_reminder
    except ImportError:
        return

    for a in actions:
        ticket = db.get(a["key"])
        if not ticket:
            continue
        if a["action"] == "escalated":
            notify_ticket_escalated(ticket, escalated_by=ACTOR)
        elif a["action"] == "reminded":
            notify_ticket_reminder(ticket)
