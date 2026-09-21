"""`ai-workflow validate` — validate the workflow itself (not the code).

Two severities (CONTEXT.md "Validate Severity"):

- ERROR  — illegal schema, gate-violating transition, missing required artifact,
           DONE-with-next_action, handoff missing, or restricted-YAML violation.
           Must be fixed before handoff; causes a non-zero exit.
- WARN   — proceed allowed, must be recorded in handoff (e.g. uncommitted work,
           missing handoff fields, missing protocol dir).

Read-only: never writes state.yaml.
"""

import os
import subprocess

import parser
import state
from status import list_tickets

__all__ = ["validate_ticket", "validate_repo", "PHASES", "STATUSES", "GATES", "SCOPES"]


PHASES = {
    "requirement", "evidence_collection", "evidence_audit", "followup_evidence",
    "technical_decision", "planning", "implementation", "review", "done",
}
STATUSES = {"active", "blocked", "escalation_required", "paused", "abandoned"}
GATES = {"sufficient", "insufficient"}
SCOPES = {"machine", "human"}
ROLES = {
    "scout", "evidence-auditor", "technical-decision", "executor-plan",
    "ticket-executor", "checkpoint-handoff", "workflow-bootstrap",
}

# Phases that require a sufficient evidence gate before they may be entered.
_DECISIONWARDS = {"technical_decision", "planning", "implementation", "review", "done"}

_HANDOFF_SECTIONS = [
    "What was done",
    "What remains",
    "Important discoveries",
    "Current failure",
    "Do not repeat",
    "Next recommended action",
    "Repository State",
]


class Finding(object):
    def __init__(self, severity, message):
        self.severity = severity  # ERROR | WARN
        self.message = message

    def __repr__(self):
        return "%s: %s" % (self.severity, self.message)


def _git_dirty(root):
    try:
        out = subprocess.run(
            ["git", "-C", root, "status", "--porcelain"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode != 0:
            return None  # not a git repo
        return out.stdout.strip() != ""
    except (OSError, subprocess.SubprocessError):
        return None


def _read_handoff(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return None


def validate_ticket(root, ticket, findings):
    """Validate one ticket's state.yaml + artifacts. Appends Findings."""
    work_dir = os.path.join(root, ".ai", "work", ticket)
    state_path = os.path.join(work_dir, "state.yaml")

    if not os.path.exists(state_path):
        findings.append(Finding("ERROR", "[%s] missing state.yaml" % ticket))
        return

    try:
        data = state.load_file(state_path)
    except state.StateError as exc:
        findings.append(Finding("ERROR", "[%s] %s" % (ticket, exc)))
        return

    bad = lambda msg: findings.append(Finding("ERROR", "[%s] %s" % (ticket, msg)))
    warn = lambda msg: findings.append(Finding("WARN", "[%s] %s" % (ticket, msg)))

    # --- schema scalar enums -------------------------------------------------
    phase = data.get("phase")
    if phase not in PHASES:
        bad("illegal phase %r (must be one of %s)" % (phase, ", ".join(sorted(PHASES))))
    status = data.get("status")
    if status not in STATUSES:
        bad("illegal status %r (must be one of %s)" % (status, ", ".join(sorted(STATUSES))))

    evidence = data.get("evidence") or {}
    gate = evidence.get("gate")
    if gate not in GATES:
        bad("illegal evidence.gate %r" % gate)

    esc = data.get("escalation") or {}
    if esc.get("required"):
        scope = esc.get("scope")
        if scope not in SCOPES:
            bad("illegal escalation.scope %r (machine|human)" % scope)

    next_action = data.get("next_action") or {}
    next_role = next_action.get("role")
    if next_role not in ROLES:
        bad("illegal next_action.role %r" % next_role)
    has_next = bool(next_action.get("action")) or bool(next_action.get("task")) or bool(next_role)

    # --- gate-violating transition ------------------------------------------
    if phase in _DECISIONWARDS and gate == "insufficient":
        bad("gate-violating transition: phase=%s but evidence.gate=insufficient" % phase)

    # --- implementation counters --------------------------------------------
    impl = data.get("implementation") or {}
    try:
        cur = int(impl.get("current_task", 0) or 0)
        tot = int(impl.get("total_tasks", 0) or 0)
    except (TypeError, ValueError):
        cur = tot = -1
    if cur > tot >= 0:
        bad("implementation.current_task (%d) > total_tasks (%d)" % (cur, tot))

    # --- DONE must clear next_action ----------------------------------------
    if phase == "done" and has_next:
        bad("phase=done but next_action is still set")

    # --- missing artifacts per required phase --------------------------------
    artifacts = data.get("artifacts") or {}
    filenames = {
        "evidence": artifacts.get("evidence", "evidence.md"),
        "evidence_audit": artifacts.get("evidence_audit", "evidence-audit.md"),
        "decision": artifacts.get("decision", "decision.md"),
        "handoff": artifacts.get("handoff", "handoff.md"),
    }

    def artifact_exists(key):
        return os.path.exists(os.path.join(work_dir, filenames[key]))

    # handoff is required whenever the ticket is in progress or done.
    if phase in PHASES and not artifact_exists("handoff"):
        bad("missing artifact handoff.md for phase=%s" % phase)
    if phase in {"evidence_audit", "followup_evidence", "technical_decision",
                 "planning", "implementation", "review", "done"} \
            and not artifact_exists("evidence"):
        bad("missing artifact evidence.md for phase=%s" % phase)
    if phase in {"technical_decision", "planning", "implementation", "review", "done"} \
            and not artifact_exists("evidence_audit"):
        bad("missing artifact evidence-audit.md for phase=%s" % phase)
    if phase in {"planning", "implementation", "review", "done"} \
            and not artifact_exists("decision"):
        bad("missing artifact decision.md for phase=%s" % phase)

    # --- handoff field completeness -----------------------------------------
    handoff_path = os.path.join(work_dir, filenames["handoff"])
    if os.path.exists(handoff_path):
        handoff_text = _read_handoff(handoff_path)
        if handoff_text is None:
            warn("handoff.md exists but could not be read")
        else:
            for section in _HANDOFF_SECTIONS:
                if section not in handoff_text:
                    warn("handoff.md missing section %r" % section)

    # --- uncommitted work (WARN) ---------------------------------------------
    dirty = _git_dirty(root)
    if dirty:
        warn("uncommitted work in repository")


def validate_repo(root):
    """Validate the workflow installation + every ticket. Returns findings list."""
    findings = []

    # Protocol presence at repo level is a WARN (workflow self-check), not a
    # per-ticket schema error.
    if not os.path.exists(os.path.join(root, ".ai", "workflow", "STATE_SCHEMA.md")):
        findings.append(Finding("WARN", "repo has no .ai/workflow/ protocol installed"))

    ticket_ids = list_tickets(root)
    if not ticket_ids:
        findings.append(Finding("WARN", "no tickets found under .ai/work/"))
    for tid in ticket_ids:
        validate_ticket(root, tid, findings)
    return findings


def has_errors(findings):
    return any(f.severity == "ERROR" for f in findings)