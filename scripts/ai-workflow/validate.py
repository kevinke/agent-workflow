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

import contracts
import parser
import state
import workflow_v2
from status import list_tickets

__all__ = ["validate_ticket", "validate_repo", "PHASES", "STATUSES", "GATES",
           "SCOPES", "ROLES", "DECISIONWARDS"]


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
# Public: shared with the `mutate` module so write-time checks use one rule.
DECISIONWARDS = {"technical_decision", "planning", "implementation", "review", "done"}

# Phases whose Evidence report must be a structurally valid concrete report
# on v2 Tickets (requirement/evidence_collection reports may still be
# pending scaffolds and are only WARNed about, per the common phase rules).
_V2_EVIDENCE_STRUCTURAL_PHASES = {
    "evidence_audit", "followup_evidence",
    "technical_decision", "planning", "implementation", "review", "done",
}
_V2_AUDIT_STRUCTURAL_PHASES = {
    "technical_decision", "planning", "implementation", "review", "done",
}
_V2_PENDING_PHASES = {"requirement", "evidence_collection"}


def _validate_v2_artifacts(work_dir, ticket, data, filenames, phase, bad, warn):
    """Structural artifact contracts for v2 Tickets; v1 semantics unchanged."""
    evidence_block = data.get("evidence") or {}
    gate = evidence_block.get("gate")
    round_no = evidence_block.get("round")

    ev_path = os.path.join(work_dir, filenames.get("evidence", "evidence.md"))
    audit_path = os.path.join(
        work_dir, filenames.get("evidence_audit", "evidence-audit.md"))

    if phase in _V2_PENDING_PHASES:
        # A scaffold is not a completed report: surface shape problems as
        # WARN so placeholders here are never structural failures.
        if os.path.exists(ev_path):
            try:
                report = contracts.read_artifact(ev_path, "evidence")
                problems = contracts.validate_evidence(report, ticket)
            except contracts.ContractError as exc:
                warn("evidence.md is not a structured report yet (%s)" % exc)
            else:
                for msg in problems:
                    warn("evidence.md pending scaffold: %s" % msg)
        return

    if phase in _V2_EVIDENCE_STRUCTURAL_PHASES and os.path.exists(ev_path):
        try:
            report = contracts.read_artifact(ev_path, "evidence")
            problems = contracts.validate_evidence(report, ticket)
        except contracts.ContractError as exc:
            bad("evidence.md violates the artifact grammar: %s" % exc)
        else:
            for msg in problems:
                bad("evidence.md: %s" % msg)

    if phase in _V2_AUDIT_STRUCTURAL_PHASES and os.path.exists(audit_path):
        try:
            report = contracts.read_artifact(audit_path, "evidence-audit")
            problems = contracts.validate_audit(report, ticket, gate, round_no)
        except contracts.ContractError as exc:
            bad("evidence-audit.md violates the artifact grammar: %s" % exc)
        else:
            for msg in problems:
                bad("evidence-audit.md: %s" % msg)

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

    # --- workflow version + shared v2 State problems ---------------------------
    version_problems = workflow_v2.problems(root, data)
    for msg in version_problems:
        bad(msg)
    ver = None
    if not version_problems:
        try:
            ver = workflow_v2.version(data)
        except contracts.ContractError:
            ver = None  # already reported above

    # --- schema scalar enums -------------------------------------------------
    phase = data.get("phase")
    if phase not in PHASES:
        bad("illegal phase %r (must be one of %s)" % (phase, ", ".join(sorted(PHASES))))
    status = data.get("status")
    if status not in STATUSES:
        bad("illegal status %r (must be one of %s)" % (status, ", ".join(sorted(STATUSES))))

    # Every save stamps updated_at; a missing value means hand-edited state.
    if not data.get("updated_at"):
        warn("missing updated_at (state was hand-edited, not saved via the kit)")

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
    # `done` clears next_action; an emptied block must not trip the role enum
    # check. Only validate the role when there is actually a next action.
    has_next = bool(next_action.get("action")) or bool(next_action.get("task")) \
        or bool(next_action.get("role"))
    if has_next:
        next_role = next_action.get("role")
        if next_role not in ROLES:
            bad("illegal next_action.role %r" % next_role)

    # --- gate-violating transition ------------------------------------------
    if phase in DECISIONWARDS and gate == "insufficient":
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

    completed = impl.get("completed_tasks")
    if cur >= 0 and tot >= 0 and "implementation" in data:
        if not isinstance(completed, list):
            bad("implementation.completed_tasks must be a list (got %r)" % (completed,))
        else:
            try:
                nums = sorted(int(c) for c in completed)
            except (TypeError, ValueError):
                bad("implementation.completed_tasks contains non-integer entries: %r"
                    % (completed,))
            else:
                if nums != list(range(1, cur + 1)):
                    bad("implementation.completed_tasks %r does not match "
                        "current_task=%d (expected [1..%d])"
                        % (completed, cur, cur))
                elif nums and tot > 0 and nums[-1] > tot:
                    bad("implementation.completed_tasks contains task %d > "
                        "total_tasks (%d)" % (nums[-1], tot))

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

    # --- v2 structured artifact contracts --------------------------------------
    if ver == 2:
        _validate_v2_artifacts(work_dir, ticket, data, filenames, phase,
                               bad, warn)

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