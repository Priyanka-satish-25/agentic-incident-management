"""
AIMS — Email Notification Module (Resend API)

Sends emails when tickets are raised or escalated.

Setup:
  1. Sign up free at https://resend.com
  2. Create an API key (Dashboard → API Keys)
  3. Add to AIMS/.env:

Required .env variables:
    RESEND_API_KEY      your Resend API key (re_xxxxxxxxxxxx)
    NOTIFY_FROM         sender address — use 'onboarding@resend.dev' for testing
                        or a verified domain address for production

Optional role email mappings (all default to NOTIFY_FROM if not set):
    EMAIL_PRODUCTION_MANAGER
    EMAIL_QA_MANAGER
    EMAIL_SUPERVISOR
    EMAIL_QA_LOG
"""

import os

from dotenv import load_dotenv

from aims.config import ENV_FILE

load_dotenv(ENV_FILE)

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
NOTIFY_FROM    = os.environ.get("NOTIFY_FROM", "onboarding@resend.dev")

ROLE_EMAILS = {
    "Production Manager": os.environ.get("EMAIL_PRODUCTION_MANAGER", NOTIFY_FROM),
    "QA Manager":         os.environ.get("EMAIL_QA_MANAGER",         NOTIFY_FROM),
    "Supervisor":         os.environ.get("EMAIL_SUPERVISOR",          NOTIFY_FROM),
    "QA Log":             os.environ.get("EMAIL_QA_LOG",              NOTIFY_FROM),
}

SEVERITY_EMOJI = {
    "critical": "🔴",
    "high":     "🟠",
    "medium":   "🟡",
    "low":      "🟢",
}

SEVERITY_COLOR = {
    "critical": "#c0392b",
    "high":     "#e67e22",
    "medium":   "#f0a500",
    "low":      "#27ae60",
}


def _send(to: str, subject: str, html: str) -> bool:
    """Send an email via Resend API. Returns True on success."""
    if not RESEND_API_KEY:
        print("[Notifications] RESEND_API_KEY not set — skipping email.")
        return False

    try:
        import resend
        resend.api_key = RESEND_API_KEY
        resend.Emails.send({
            "from":    NOTIFY_FROM,
            "to":      [to],
            "subject": subject,
            "html":    html,
        })
        print(f"[Notifications] ✓ Email sent to {to}")
        return True
    except Exception as e:
        print(f"[Notifications] ✗ Failed to send email: {e}")
        return False


def _ticket_table(ticket: dict) -> str:
    sev   = ticket["severity"]
    color = SEVERITY_COLOR.get(sev, "#888")
    emoji = SEVERITY_EMOJI.get(sev, "")
    badge = (f"<span style='background:{color};color:white;"
             f"padding:2px 10px;border-radius:4px;font-weight:bold'>"
             f"{emoji} {sev.upper()}</span>")
    rows = [
        ("Ticket ID",   ticket["ticket_id"]),
        ("Run",         ticket["run_id"]),
        ("Severity",    badge),
        ("Assigned To", ticket["assigned_to"]),
        ("SOP Step",    ticket["sop_step"]),
        ("Timestamp",   ticket["timestamp"]),
        ("Confidence",  f"{ticket['confidence']}%"),
        ("Status",      ticket["status"]),
    ]
    cells = "".join(
        f"<tr>"
        f"<td style='padding:8px 12px;background:#f0f4f8;font-weight:bold;width:150px'>{k}</td>"
        f"<td style='padding:8px 12px;border:1px solid #ddd'>{v}</td>"
        f"</tr>"
        for k, v in rows
    )
    return f"<table style='width:100%;border-collapse:collapse;margin-bottom:20px'>{cells}</table>"


def _base_layout(header_color: str, title: str, body_html: str) -> str:
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:640px;margin:0 auto">
      <div style="background:{header_color};padding:20px;border-radius:8px 8px 0 0">
        <h2 style="color:white;margin:0">🛡️ AIMS — {title}</h2>
      </div>
      <div style="border:1px solid #ddd;border-top:none;padding:24px;border-radius:0 0 8px 8px">
        {body_html}
        <p style="color:#888;font-size:0.8rem;margin-top:24px">
          Automated notification from AIMS. Do not reply to this email.
        </p>
      </div>
    </div>
    """


def notify_ticket_created(ticket: dict) -> bool:
    """Notify the assigned role when Agent 3 raises a new incident ticket."""
    role  = ticket["assigned_to"]
    to    = ROLE_EMAILS.get(role, NOTIFY_FROM)
    sev   = ticket["severity"]
    emoji = SEVERITY_EMOJI.get(sev, "")

    subject = f"[AIMS] {emoji} NEW TICKET {ticket['ticket_id']} — {sev.upper()} — {ticket['run_id']}"

    body = f"""
      {_ticket_table(ticket)}
      <h3 style="color:#1F4E79">Summary</h3>
      <p style="color:#333">{ticket['incident_summary']}</p>
      <h3 style="color:#1F4E79">Why {sev.upper()}?</h3>
      <p style="color:#333">{ticket['severity_reason']}</p>
      <h3 style="color:#1F4E79">Recommended Action</h3>
      <p style="color:#333">{ticket['recommended_action']}</p>
      <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;padding:12px;margin-top:20px">
        <strong>⚠️ Action required:</strong> Log in to the AIMS dashboard
        at <code>http://localhost:8501</code> to review this ticket.
      </div>
    """
    return _send(to, subject, _base_layout("#1F4E79", "New Incident Ticket", body))


def notify_ticket_reminder(ticket: dict) -> bool:
    """Nudge the current assignee that an open ticket is approaching its SLA deadline."""
    role  = ticket["assigned_to"]
    to    = ROLE_EMAILS.get(role, NOTIFY_FROM)
    sev   = ticket["severity"]
    emoji = SEVERITY_EMOJI.get(sev, "")

    subject = f"[AIMS] ⏰ REMINDER — {ticket['ticket_id']} — {sev.upper()} — awaiting your action"

    body = f"""
      <p style="color:#333">
        This ticket is assigned to <strong>{role}</strong> and is approaching its
        SLA deadline. Please review it before it auto-escalates.
      </p>
      {_ticket_table(ticket)}
      <h3 style="color:#b8860b">Recommended Action</h3>
      <p style="color:#333">{ticket['recommended_action']}</p>
      <div style="background:#fff3cd;border:1px solid #ffc107;border-radius:4px;padding:12px;margin-top:20px">
        <strong>⏰ Action required:</strong> Log in to the AIMS dashboard
        at <code>http://localhost:8501</code> to act on this ticket before it escalates.
      </div>
    """
    return _send(to, subject, _base_layout("#b8860b", "SLA Reminder", body))


def notify_ticket_escalated(ticket: dict, escalated_by: str) -> bool:
    """Notify the new assignee when a ticket is escalated."""
    role  = ticket["assigned_to"]
    to    = ROLE_EMAILS.get(role, NOTIFY_FROM)
    sev   = ticket["severity"]
    emoji = SEVERITY_EMOJI.get(sev, "")

    subject = f"[AIMS] {emoji} ESCALATED TO YOU — {ticket['ticket_id']} — {sev.upper()}"

    body = f"""
      <p style="color:#333">
        <strong>{escalated_by}</strong> has escalated the following ticket to <strong>{role}</strong>:
      </p>
      {_ticket_table(ticket)}
      <h3 style="color:#6a0dad">Summary</h3>
      <p style="color:#333">{ticket['incident_summary']}</p>
      <h3 style="color:#6a0dad">Recommended Action</h3>
      <p style="color:#333">{ticket['recommended_action']}</p>
      <div style="background:#f3e5f5;border:1px solid #9c27b0;border-radius:4px;padding:12px;margin-top:20px">
        <strong>⚠️ This ticket requires your attention.</strong> Log in to the
        AIMS dashboard at <code>http://localhost:8501</code> to review it.
      </div>
    """
    return _send(to, subject, _base_layout("#6a0dad", "Ticket Escalated To You", body))
