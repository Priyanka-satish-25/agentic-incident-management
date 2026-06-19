"""
ProcedureGuard — Role-Based Incident Management UI

Run:
  streamlit run procedureguard_ui.py

Demo credentials:
  alice / alice  →  Production Manager
  bob   / bob    →  QA Manager
  carol / carol  →  Supervisor
  dave  / dave   →  QA Log
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

try:
    from notifications import notify_ticket_escalated
    _NOTIFY = True
except ImportError:
    _NOTIFY = False

# ── Config ─────────────────────────────────────────────────────────────────────
st.set_page_config(page_title="ProcedureGuard", page_icon="🛡️", layout="wide")

SCRIPT_DIR = Path(__file__).parent
DB_PATH = SCRIPT_DIR / "tickets_db.json"

USERS = {
    "alice": {"password": "alice", "role": "Production Manager", "name": "Alice"},
    "bob":   {"password": "bob",   "role": "QA Manager",         "name": "Bob"},
    "carol": {"password": "carol", "role": "Supervisor",         "name": "Carol"},
    "dave":  {"password": "dave",  "role": "QA Log",             "name": "Dave"},
}

ESCALATION_PATH = {
    "QA Log":             "Supervisor",
    "Supervisor":         "QA Manager",
    "QA Manager":         "Production Manager",
    "Production Manager": None,
}

ROLE_RANK = {"QA Log": 1, "Supervisor": 2, "QA Manager": 3, "Production Manager": 4}

SEVERITY_COLOR  = {"critical": "#c0392b", "high": "#e67e22", "medium": "#f1c40f", "low": "#27ae60"}
SEVERITY_EMOJI  = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
STATUS_COLOR    = {"Open": "red", "In Review": "orange", "Escalated": "purple", "Closed": "green"}


# ── Tickets DB (JSON file as persistent store) ─────────────────────────────────

def load_db() -> dict:
    if DB_PATH.exists():
        return json.loads(DB_PATH.read_text())
    return {}


def save_db(db: dict) -> None:
    st.session_state.db = db
    DB_PATH.write_text(json.dumps(db, indent=2))


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def db_key(run_id: str, ticket_id: str) -> str:
    return f"{run_id}__{ticket_id}"


def init_db_from_incidents(db: dict) -> dict:
    """Scan for *_incidents.json files and add any new tickets to the DB."""
    for path in sorted(SCRIPT_DIR.glob("*_incidents.json")):
        data = json.loads(path.read_text())
        for inc in data.get("incidents", []):
            key = db_key(inc["run_id"], inc["ticket_id"])
            if key not in db:
                db[key] = {
                    **inc,
                    "comments": [],
                    "history": [
                        {"action": "Ticket created by system", "by": "System", "at": inc.get("created_at", now())[:16].replace("T", " ")}
                    ],
                }
    save_db(db)
    return db


# ── Helpers ────────────────────────────────────────────────────────────────────

def severity_badge(sev: str) -> str:
    c = SEVERITY_COLOR.get(sev, "#888")
    e = SEVERITY_EMOJI.get(sev, "")
    return (f"<span style='background:{c};color:white;padding:2px 10px;"
            f"border-radius:4px;font-weight:bold;font-size:0.75rem'>"
            f"{e} {sev.upper()}</span>")


def status_badge(status: str) -> str:
    c = STATUS_COLOR.get(status, "grey")
    return f"<span style='color:{c};font-weight:bold'>{status}</span>"


def user_can_act(user_role: str, ticket: dict) -> bool:
    """User can act on tickets assigned to their role or below."""
    return ROLE_RANK.get(user_role, 0) >= ROLE_RANK.get(ticket["assigned_to"], 0)


# ── Login ──────────────────────────────────────────────────────────────────────

def login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("## 🛡️ ProcedureGuard")
        st.markdown("##### Manufacturing Compliance & Incident Management")
        st.divider()

        username = st.text_input("Username")
        password = st.text_input("Password", type="password")

        if st.button("Login", use_container_width=True, type="primary"):
            user = USERS.get(username)
            if user and user["password"] == password:
                st.session_state.logged_in   = True
                st.session_state.username    = username
                st.session_state.user        = user
                st.session_state.selected    = None
                st.rerun()
            else:
                st.error("Invalid credentials.")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("**Demo credentials:**")
        for uname, u in USERS.items():
            st.caption(f"`{uname}` / `{uname}` → {u['role']}")


# ── Ticket detail view ─────────────────────────────────────────────────────────

def ticket_detail(key: str, db: dict, user: dict):
    ticket = db[key]
    sev    = ticket["severity"]
    role   = user["role"]

    if st.button("← Back to list"):
        st.session_state.selected = None
        st.rerun()

    st.markdown(f"### {severity_badge(sev)} &nbsp; {ticket['ticket_id']} — {ticket['sop_step']}",
                unsafe_allow_html=True)
    st.caption(f"Run: **{ticket['run_id']}** · Step {ticket['sequence_position']} ({ticket['step_id']}) · Section: {ticket['section']}")

    st.divider()

    # ── Incident info ──────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Severity",   sev.upper())
    c2.metric("Confidence", f"{ticket['confidence']}%")
    c3.metric("Timestamp",  ticket["timestamp"])
    c4.metric("Status",     ticket["status"])

    st.markdown(f"**Assigned to:** {ticket['assigned_to']}")
    st.markdown(f"**Why {sev}:** {ticket['severity_reason']}")
    st.markdown(f"**Summary:** {ticket['incident_summary']}")
    st.markdown(f"**Recommended action:** {ticket['recommended_action']}")

    st.divider()

    # ── Comments ───────────────────────────────────────────────────────────────
    st.markdown("#### 💬 Comments")
    if ticket["comments"]:
        for c in ticket["comments"]:
            with st.container(border=True):
                st.markdown(f"**{c['author']}** · {c['at']}")
                st.write(c["text"])
    else:
        st.caption("No comments yet.")

    if ticket["status"] != "Closed":
        comment_text = st.text_area("Add a comment", key=f"comment_{key}", placeholder="Write your comment here...")
        if st.button("Post comment", key=f"post_{key}"):
            if comment_text.strip():
                ticket["comments"].append({"author": user["name"], "at": now(), "text": comment_text.strip()})
                ticket["history"].append({"action": f"Comment added", "by": user["name"], "at": now()})
                if ticket["status"] == "Open":
                    ticket["status"] = "In Review"
                    ticket["history"].append({"action": "Status → In Review", "by": user["name"], "at": now()})
                save_db(db)
                st.success("Comment posted.")
                st.rerun()

    st.divider()

    # ── Actions ────────────────────────────────────────────────────────────────
    st.markdown("#### ⚙️ Actions")

    if ticket["status"] == "Closed":
        st.info("This ticket is closed.")
    elif not user_can_act(role, ticket):
        st.warning(f"This ticket is assigned to **{ticket['assigned_to']}**. You don't have permission to act on it.")
    else:
        col_close, col_escalate = st.columns(2)

        with col_close:
            if st.button("✅ Close ticket", key=f"close_{key}", use_container_width=True):
                # Save any pending comment before closing
                pending = st.session_state.get(f"comment_{key}", "").strip()
                if pending:
                    ticket["comments"].append({"author": user["name"], "at": now(), "text": pending})
                    ticket["history"].append({"action": "Comment added", "by": user["name"], "at": now()})
                ticket["status"] = "Closed"
                ticket["history"].append({"action": "Ticket closed", "by": user["name"], "at": now()})
                save_db(db)
                st.success("Ticket closed.")
                st.rerun()

        with col_escalate:
            next_role = ESCALATION_PATH.get(ticket["assigned_to"])
            if next_role:
                if st.button(f"⬆️ Escalate to {next_role}", key=f"esc_{key}", use_container_width=True):
                    # Save any pending comment before escalating
                    pending = st.session_state.get(f"comment_{key}", "").strip()
                    if pending:
                        ticket["comments"].append({"author": user["name"], "at": now(), "text": pending})
                        ticket["history"].append({"action": "Comment added", "by": user["name"], "at": now()})
                    old = ticket["assigned_to"]
                    ticket["assigned_to"] = next_role
                    ticket["status"]      = "Escalated"
                    ticket["history"].append({"action": f"Escalated: {old} → {next_role}", "by": user["name"], "at": now()})
                    save_db(db)
                    if _NOTIFY:
                        notify_ticket_escalated(ticket, escalated_by=user["name"])
                    st.success(f"Ticket escalated to {next_role}.")
                    st.rerun()
            else:
                st.caption("Already at highest escalation level.")

    st.divider()

    # ── History ────────────────────────────────────────────────────────────────
    st.markdown("#### 📋 Ticket History")
    for h in reversed(ticket["history"]):
        st.caption(f"**{h['at']}** — {h['action']} *(by {h['by']})*")


# ── Ticket list ────────────────────────────────────────────────────────────────

def ticket_list(tickets: list, db: dict, label: str, tab_prefix: str = ""):
    if not tickets:
        st.info(f"No {label.lower()} tickets.")
        return

    for key, ticket in tickets:
        sev    = ticket["severity"]
        status = ticket["status"]

        with st.container(border=True):
            col1, col2 = st.columns([5, 1])
            with col1:
                st.markdown(
                    f"{severity_badge(sev)} &nbsp; **{ticket['ticket_id']}** · {ticket['run_id']} "
                    f"· Step {ticket['sequence_position']}",
                    unsafe_allow_html=True,
                )
                st.caption(ticket["sop_step"])
                st.markdown(
                    f"🕐 `{ticket['timestamp']}` &nbsp;|&nbsp; "
                    f"Confidence: {ticket['confidence']}% &nbsp;|&nbsp; "
                    f"Assigned: **{ticket['assigned_to']}** &nbsp;|&nbsp; "
                    f"Status: {status_badge(status)}",
                    unsafe_allow_html=True,
                )
            with col2:
                if st.button("View", key=f"view_{tab_prefix}_{key}", use_container_width=True):
                    st.session_state.selected = key
                    st.rerun()


# ── Main app ───────────────────────────────────────────────────────────────────

def main_app(db: dict, user: dict):
    role = user["role"]

    # Sidebar
    with st.sidebar:
        st.markdown(f"## 🛡️ ProcedureGuard")
        st.divider()
        st.markdown(f"**{user['name']}**")
        st.markdown(f"Role: `{role}`")
        st.divider()

        # Summary counts
        all_tickets = list(db.values())
        open_count  = sum(1 for t in all_tickets if t["status"] != "Closed")
        mine_count  = sum(1 for t in all_tickets if t["assigned_to"] == role and t["status"] != "Closed")
        st.metric("Open tickets",      open_count)
        st.metric("Assigned to me",    mine_count)

        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            for key in ["logged_in", "username", "user", "selected"]:
                st.session_state.pop(key, None)
            st.rerun()

    # If a ticket is selected, show detail view
    if st.session_state.get("selected"):
        key = st.session_state.selected
        if key in db:
            ticket_detail(key, db, user)
        else:
            st.session_state.selected = None
            st.rerun()
        return

    # Main tabs
    tab_mine, tab_all, tab_history = st.tabs(["📋 My Tickets", "🗂️ All Tickets", "🕓 History"])

    all_items     = [(k, t) for k, t in db.items()]
    mine_open     = [(k, t) for k, t in all_items if t["assigned_to"] == role and t["status"] != "Closed"]
    all_open      = [(k, t) for k, t in all_items if t["status"] != "Closed"]
    history_items = [(k, t) for k, t in all_items if t["status"] == "Closed"]

    with tab_mine:
        st.markdown(f"### Tickets assigned to you ({len(mine_open)} open)")
        if mine_open:
            # Severity filter
            sevs = list({t["severity"] for _, t in mine_open})
            sel  = st.multiselect("Filter by severity", sevs, default=sevs, key="mine_filter")
            filtered = [(k, t) for k, t in mine_open if t["severity"] in sel]
            ticket_list(filtered, db, "My", tab_prefix="mine")
        else:
            st.success("✅ No open tickets assigned to you.")

    with tab_all:
        st.markdown(f"### All open tickets ({len(all_open)})")
        sev_opts = list({t["severity"] for _, t in all_open})
        rol_opts = list({t["assigned_to"] for _, t in all_open})
        c1, c2   = st.columns(2)
        sel_sev  = c1.multiselect("Severity", sev_opts, default=sev_opts, key="all_sev")
        sel_rol  = c2.multiselect("Assigned to", rol_opts, default=rol_opts, key="all_rol")
        filtered = [(k, t) for k, t in all_open if t["severity"] in sel_sev and t["assigned_to"] in sel_rol]
        ticket_list(filtered, db, "open", tab_prefix="all")

    with tab_history:
        st.markdown(f"### Closed tickets ({len(history_items)})")
        if history_items:
            ticket_list(history_items, db, "closed", tab_prefix="hist")
        else:
            st.info("No closed tickets yet.")


# ── Entry point ────────────────────────────────────────────────────────────────

# Load db once into session state; subsequent reruns reuse the in-memory copy
if "db" not in st.session_state:
    _db = load_db()
    _db = init_db_from_incidents(_db)
    st.session_state.db = _db

db = st.session_state.db

if not st.session_state.get("logged_in"):
    login_page()
else:
    main_app(db, st.session_state.user)
