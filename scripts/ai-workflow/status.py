"""`ai-workflow status` — a one-screen, LLM/human-readable summary of a ticket.

Reads `.ai/work/<ticket>/state.yaml` and prints: ticket, phase, status, task N/M,
evidence gate, escalation, and next role/action.
"""

import glob
import os

import state
import workflow_v2

__all__ = ["status_for_ticket", "list_tickets", "ticket_state_path",
           "WORK_DIR_REL"]


WORK_DIR_REL = os.path.join(".ai", "work")


def ticket_state_path(root, ticket):
    """The path to a ticket's state.yaml under `.ai/work/` (single source)."""
    return os.path.join(root, WORK_DIR_REL, ticket, "state.yaml")


def list_tickets(root):
    """Return sorted ticket ids that have a state.yaml under `.ai/work/`."""
    pattern = os.path.join(root, WORK_DIR_REL, "*", "state.yaml")
    paths = glob.glob(pattern)
    ids = []
    for p in paths:
        ticket = os.path.basename(os.path.dirname(p))
        if ticket != ".ai" and ticket != "work":
            ids.append(ticket)
    return sorted(ids)


def _fmt_task(data):
    """The completed count over the total, plus the explicit executable task.

    `current_task`/`total_tasks` keep their meaning (completed / registered);
    the executable task is the same `current_task + 1` the State records in
    `next_action.task`, shown without changing the completed count.
    """
    impl = data.get("implementation") or {}
    try:
        cur = int(impl.get("current_task", 0) or 0)
        tot = int(impl.get("total_tasks", 0) or 0)
    except (TypeError, ValueError):
        cur, tot = 0, 0
    text = "%d/%d" % (cur, tot)
    executable = workflow_v2.executable_task(impl)
    if executable is not None:
        text += " (next %d)" % executable
    return text


def status_for_ticket(root, ticket):
    path = ticket_state_path(root, ticket)
    try:
        data = state.load_file(path)
    except state.StateError as exc:
        return "error: %s" % exc

    ticket_id = (data.get("ticket") or {}).get("id") or ticket
    title = (data.get("ticket") or {}).get("title") or ""
    phase = data.get("phase")
    status = data.get("status")
    evidence = data.get("evidence") or {}
    escalation = data.get("escalation") or {}
    next_action = data.get("next_action") or {}

    lines = []
    lines.append("Ticket  : %s%s" % (ticket_id, (" — " + title) if title else ""))
    lines.append("Phase   : %s (%s)" % (phase, status))
    lines.append("Task    : %s" % _fmt_task(data))
    lines.append("Evidence: gate=%s round=%s" % (evidence.get("gate"), evidence.get("round")))
    if escalation.get("required"):
        scope = escalation.get("scope")
        reason = escalation.get("reason")
        lines.append("Escalate: %s%s" % (scope, (" — " + reason) if reason else ""))
    else:
        lines.append("Escalate: none")
    role = next_action.get("role")
    action = next_action.get("action")
    lines.append("Next    : [%s] %s" % (role, action))
    return "\n".join(lines)