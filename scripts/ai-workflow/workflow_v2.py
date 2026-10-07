"""Workflow version selection and shared v2 policy helpers (SCOUT-002).

Pure functions only: this module never writes and never imports mutate or
validate (the common plan's dependency order). `version` decides whether a
ticket's State follows v1 semantics or the stricter v2 contracts;
`problems` reports shared v2 State-shape problems as strings so `validate`
can convert them into ERROR Findings.
"""

import contracts

__all__ = ["version", "problems", "check_transition", "next_action",
           "TRANSITIONS", "NEXT_ACTIONS", "SUPPORTED_VERSIONS"]

SUPPORTED_VERSIONS = (1, 2)

# Allowed phase transitions, a literal encoding of STATE_SCHEMA.md. This is
# the pure table shared by `mutate` and `validate`; the v2 gate/route checks
# are layered on top by the callers.
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

# Route written into next_action when a ticket enters a phase. `done` clears
# the block entirely. Kept here so both the mutator and validate share it.
NEXT_ACTIONS = {
    "requirement": ("workflow-bootstrap",
                    "advance phase from requirement to evidence_collection"),
    "evidence_collection": ("scout", "collect evidence into evidence.md"),
    "evidence_audit": ("evidence-auditor", "audit evidence sufficiency"),
    "followup_evidence": ("scout", "collect the missing evidence"),
    "technical_decision": ("technical-decision", "write decision.md"),
    "planning": ("executor-plan", "write the implementation plan"),
    "implementation": ("ticket-executor", "implement current task"),
    "review": ("checkpoint-handoff", "review and hand off"),
}


def version(data):
    """Return the ticket's workflow version: missing means 1.

    Only integer 1/2 are accepted; bools, zero, strings, and future versions
    raise ContractError so unsupported versions fail clearly instead of
    silently falling back to v1 rules.
    """
    if not isinstance(data, dict):
        raise contracts.ContractError("state root must be a map")
    ver = data.get("workflow_version", 1)
    if ver is None:
        ver = 1
    if isinstance(ver, bool) or not isinstance(ver, int) or ver not in SUPPORTED_VERSIONS:
        raise contracts.ContractError(
            "unsupported workflow_version %r (must be one of %s)"
            % (ver, ", ".join(str(v) for v in SUPPORTED_VERSIONS)))
    return ver


def _is_int(value):
    return not isinstance(value, bool) and isinstance(value, int)


def problems(root, data):
    """Shared v2 State-shape problems; [] means the State shape is fine.

    Read-only by contract. Version violations are reported as a problem
    string here (not raised) so `validate` can surface them as Findings
    without crashing the rest of the validation pass.
    """
    try:
        ver = version(data)
    except contracts.ContractError as exc:
        return [str(exc)]

    out = []
    if ver != 2:
        return out

    evidence = data.get("evidence") or {}
    for key in ("report_sha256", "audit_sha256"):
        if key in evidence and evidence[key] is not None \
                and not isinstance(evidence[key], str):
            out.append("evidence.%s must be a string or null" % key)

    implementation = data.get("implementation") or {}
    if "task_hashes" in implementation \
            and not isinstance(implementation["task_hashes"], list):
        out.append("implementation.task_hashes must be a list")
    if "current_task" in implementation and implementation["current_task"] is not None \
            and not _is_int(implementation["current_task"]):
        out.append("implementation.current_task must be an integer")

    review = data.get("review") or {}
    if "verdict" in review and review["verdict"] is not None \
            and review["verdict"] not in ("pending", "pass", "changes_requested"):
        out.append("review.verdict must be pending|pass|changes_requested")

    upgrade = data.get("upgrade") or {}
    if "from_version" in upgrade and upgrade["from_version"] is not None \
            and not _is_int(upgrade["from_version"]):
        out.append("upgrade.from_version must be an integer")

    return out


def check_transition(root, data, to):
    """Validate a transition precondition; raise ContractError if illegal.

    Shares the TRANSITIONS table with `validate`, so the v1 edges plus the v2
    repair edge are checked the same way everywhere. `root` is part of the
    planned interface but read-only checks need no repository access.
    """
    current = (data or {}).get("phase")
    if current not in TRANSITIONS:
        raise contracts.ContractError(
            "cannot advance from phase %r (terminal or unknown)" % current)
    if to not in TRANSITIONS[current]:
        raise contracts.ContractError(
            "illegal transition %s -> %s (allowed: %s)"
            % (current, to, ", ".join(sorted(TRANSITIONS[current]))))


def next_action(data, phase):
    """The next_action block written when a ticket enters `phase`.

    Always carries exactly the keys role/action/task; entering `done` clears the
    block. Shared by the mutator and available to validate for route checks.
    """
    if phase == "done":
        return {"role": None, "action": None, "task": None}
    if phase not in NEXT_ACTIONS:
        raise contracts.ContractError("no next action for phase %r" % phase)
    role, action = NEXT_ACTIONS[phase]
    return {"role": role, "action": action, "task": None}
