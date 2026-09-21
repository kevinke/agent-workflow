"""`ai-workflow` semantic state mutations (spec §9 extension, TICKET-010).

The state machine and the restricted YAML subset are encoded here so a harness
never has to hand-write `state.yaml`: it declares intent (`advance`, `claim`,
`complete-task`, `set-gate`, `escalate`) and this module loads, checks, mutates,
and saves through the kit's own parser — rejecting illegal transitions and gate
violations at write time instead of relying on a later `validate` pass.
"""

import datetime
import os

import state
import validate

__all__ = ["MutateError", "TRANSITIONS", "DEFAULT_NEXT",
           "advance", "claim", "complete_task", "set_gate", "escalate"]

_WORK_DIR_REL = os.path.join(".ai", "work")


class MutateError(Exception):
    """Raised when a state mutation would violate the protocol."""


# Allowed phase transitions, a literal encoding of STATE_SCHEMA.md. Gate
# constraints on entering decisionward phases are enforced in advance().
TRANSITIONS = {
    "requirement": {"evidence_collection"},
    "evidence_collection": {"evidence_audit"},
    "evidence_audit": {"technical_decision", "followup_evidence"},
    "followup_evidence": {"evidence_audit"},
    "technical_decision": {"planning"},
    "planning": {"implementation"},
    "implementation": {"review"},
    "review": {"done"},
}

# Default next_action written when a ticket is advanced into a phase. `done`
# clears next_action entirely.
DEFAULT_NEXT = {
    "evidence_collection": ("scout", "collect evidence into evidence.md"),
    "evidence_audit": ("evidence-auditor", "audit evidence sufficiency"),
    "followup_evidence": ("scout", "collect the missing evidence"),
    "technical_decision": ("technical-decision", "write decision.md"),
    "planning": ("executor-plan", "write the implementation plan"),
    "implementation": ("ticket-executor", "implement current task"),
    "review": ("checkpoint-handoff", "review and hand off"),
}


def _ticket_path(root, ticket_id):
    return os.path.join(root, _WORK_DIR_REL, ticket_id, "state.yaml")


def _load(root, ticket_id):
    path = _ticket_path(root, ticket_id)
    if not os.path.exists(path):
        raise MutateError(
            "no ticket %s under .ai/work/ (run `start` or `adopt` first)" % ticket_id)
    try:
        return state.load_file(path)
    except state.StateError as exc:
        raise MutateError(str(exc))


def _save(root, ticket_id, data):
    state.save_file(_ticket_path(root, ticket_id), data)


def _require_phase(phase):
    if phase not in validate.PHASES:
        raise MutateError("unknown phase %r (must be one of %s)"
                          % (phase, ", ".join(sorted(validate.PHASES))))


def advance(root, ticket_id, to):
    """Move a ticket to phase `to` along the state machine.

    Enforces the transition table, the evidence gate on decisionward targets,
    and the gate-branched exit from evidence_audit. Returns a confirmation line.
    """
    _require_phase(to)
    data = _load(root, ticket_id)
    current = data.get("phase")
    if current not in TRANSITIONS:
        raise MutateError("cannot advance from phase %r (terminal or unknown)" % current)
    if to == current:
        raise MutateError("already in phase %r" % current)
    if to not in TRANSITIONS[current]:
        raise MutateError("illegal transition %s -> %s (allowed: %s)"
                          % (current, to, ", ".join(sorted(TRANSITIONS[current]))))

    gate = (data.get("evidence") or {}).get("gate")
    if to in validate.DECISIONWARDS and gate != "sufficient":
        raise MutateError(
            "cannot advance to %s: evidence.gate=%s but a sufficient gate is required "
            "(audit the evidence and `set-gate --gate sufficient` first)" % (to, gate))
    if current == "evidence_audit":
        expected = "technical_decision" if gate == "sufficient" else "followup_evidence"
        if to != expected:
            raise MutateError(
                "evidence_audit with gate=%s must advance to %s, not %s"
                % (gate, expected, to))

    data["phase"] = to
    if to == "done":
        data["next_action"] = {"role": None, "action": None, "task": None}
    else:
        role, action = DEFAULT_NEXT[to]
        data["next_action"] = {"role": role, "action": action, "task": None}
    _save(root, ticket_id, data)
    return "%s: %s -> %s" % (ticket_id, current, to)


def claim(root, ticket_id, harness=None, model=None):
    """Record the soft claim (and provenance) of the working session."""
    data = _load(root, ticket_id)
    claimed_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    data["claim"] = {"harness": harness, "model": model, "claimed_at": claimed_at}
    data["provenance"] = {"last_harness": harness, "last_model": model}
    _save(root, ticket_id, data)
    who = ("%s / %s" % (harness, model)) if (harness or model) else "unknown"
    return "%s claimed by %s at %s" % (ticket_id, who, claimed_at)


def complete_task(root, ticket_id, total=None):
    """Mark one implementation task complete (increment current_task)."""
    data = _load(root, ticket_id)
    impl = data.get("implementation") or {}
    try:
        current = int(impl.get("current_task", 0) or 0)
        total_tasks = int(impl.get("total_tasks", 0) or 0)
    except (TypeError, ValueError):
        raise MutateError("implementation counters are not integers")
    if total is not None:
        total_tasks = int(total)
    if total_tasks <= 0:
        raise MutateError(
            "cannot complete a task: total_tasks=%s (set --total N first)" % total_tasks)
    if current >= total_tasks:
        raise MutateError("all %d tasks already complete" % total_tasks)
    current += 1
    completed = list(impl.get("completed_tasks") or [])
    if current not in completed:
        completed.append(current)
    impl["current_task"] = current
    impl["total_tasks"] = total_tasks
    impl["completed_tasks"] = completed
    data["implementation"] = impl
    _save(root, ticket_id, data)
    return "%s: task %d/%d complete" % (ticket_id, current, total_tasks)


def set_gate(root, ticket_id, gate, round_no=None):
    """Record the auditor's evidence verdict."""
    if gate not in validate.GATES:
        raise MutateError("unknown gate %r (must be sufficient or insufficient)" % gate)
    data = _load(root, ticket_id)
    evidence = data.get("evidence") or {}
    if round_no is not None:
        evidence["round"] = int(round_no)
    evidence["gate"] = gate
    data["evidence"] = evidence
    _save(root, ticket_id, data)
    return "%s: evidence.gate=%s round=%s" % (ticket_id, gate, evidence.get("round"))


def escalate(root, ticket_id, scope=None, reason=None, clear=False):
    """Set or clear the escalation block."""
    data = _load(root, ticket_id)
    if clear:
        data["escalation"] = {"required": False, "scope": "machine", "reason": None}
        _save(root, ticket_id, data)
        return "%s: escalation cleared" % ticket_id
    if scope not in validate.SCOPES:
        raise MutateError("unknown escalation scope %r (machine|human)" % scope)
    data["escalation"] = {"required": True, "scope": scope, "reason": reason}
    _save(root, ticket_id, data)
    return "%s: escalation required (scope=%s)" % (ticket_id, scope)
