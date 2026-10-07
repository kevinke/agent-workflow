"""Workflow version selection and shared v2 policy helpers (SCOUT-002).

Pure functions only: this module never writes and never imports mutate or
validate (the common plan's dependency order). `version` decides whether a
ticket's State follows v1 semantics or the stricter v2 contracts;
`problems` reports shared v2 State-shape problems as strings so `validate`
can convert them into ERROR Findings.
"""

import os

import contracts

__all__ = ["version", "problems", "check_transition", "next_action",
           "readiness_problems", "counter_problems", "executable_task",
           "is_nonneg_int", "escalated_next_action", "ADOPTION_CONFIRMATIONS",
           "TRANSITIONS", "NEXT_ACTIONS", "ESCALATION_RESOLVERS",
           "SUPPORTED_VERSIONS"]

SUPPORTED_VERSIONS = (1, 2)

# The six adoption_checkpoint booleans; all must be true before a cheap
# executor may run on an adopted ticket (STATE_SCHEMA.md, MIGRATION.md).
ADOPTION_CONFIRMATIONS = (
    "repository_understood",
    "active_ticket_identified",
    "current_phase_identified",
    "remaining_work_identified",
    "critical_invariants_identified",
    "continuation_safe",
)

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

# Senior resolver for each escalated phase (spec decision 5). While a v2 ticket
# is escalated, next_action locks to the phase's resolver; the requirement phase
# (adoption/uncertainty) routes to workflow-bootstrap. Shared by `mutate` (to
# write the route) and `validate` (to detect route corruption).
ESCALATION_RESOLVERS = {
    "requirement": "workflow-bootstrap",
    "evidence_collection": "evidence-auditor",
    "evidence_audit": "evidence-auditor",
    "followup_evidence": "evidence-auditor",
    "technical_decision": "technical-decision",
    "planning": "technical-decision",
    "implementation": "technical-decision",
    "review": "technical-decision",
}

# The imperative written into next_action.action while a v2 ticket is escalated.
# Kept free of the restricted-YAML-reserved characters so it round-trips plainly.
ESCALATION_ACTION = ("resolve the escalation and clear it with "
                     "escalate --clear --resolution")


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
    In `implementation` the `task` key is the explicit executable task number
    (see `executable_task`); every other phase has no executable task.
    """
    if phase == "done":
        return {"role": None, "action": None, "task": None}
    if phase not in NEXT_ACTIONS:
        raise contracts.ContractError("no next action for phase %r" % phase)
    role, action = NEXT_ACTIONS[phase]
    task = None
    if phase == "implementation":
        task = executable_task((data or {}).get("implementation") or {})
    return {"role": role, "action": action, "task": task}


def escalated_next_action(phase):
    """The senior-resolver route written while a v2 ticket is escalated.

    Keys are always exactly role/action/task. The resolver is the phase's entry
    in `ESCALATION_RESOLVERS`; an unknown/terminal phase yields no role, which
    `validate` reports as an unresolvable escalation.
    """
    return {"role": ESCALATION_RESOLVERS.get(phase),
            "action": ESCALATION_ACTION if phase in ESCALATION_RESOLVERS else None,
            "task": None}


def is_nonneg_int(value):
    """True for a real integer >= 0; booleans are never integers here."""
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


def executable_task(implementation):
    """The explicit executable task number, or None when none remains.

    `current_task` is the completed count (both versions), so the executable
    task is `current_task + 1` while it is below `total_tasks`; once every task
    is complete there is no executable task. Malformed counters yield None.
    """
    if not isinstance(implementation, dict):
        return None
    current = implementation.get("current_task")
    total = implementation.get("total_tasks")
    current = 0 if current is None else current
    total = 0 if total is None else total
    if not is_nonneg_int(current) or not is_nonneg_int(total):
        return None
    return current + 1 if current < total else None


def counter_problems(implementation):
    """Coherence problems of the implementation counters; [] means coherent.

    Shared by `validate` and the mutator so the "task" counters have one rule:
    non-negative integers only (booleans are rejected), `completed_tasks` is
    exactly `[1..current_task]`, `current_task <= total_tasks`, and — when a
    registered Plan recorded them — the registered total matches the number of
    task hashes. The registered total stays authoritative.
    """
    problems = []
    current = implementation.get("current_task", 0)
    total = implementation.get("total_tasks", 0)
    current = 0 if current is None else current
    total = 0 if total is None else total

    if not is_nonneg_int(current):
        problems.append("implementation.current_task must be a non-negative "
                        "integer (got %r)" % (current,))
        current = None
    if not is_nonneg_int(total):
        problems.append("implementation.total_tasks must be a non-negative "
                        "integer (got %r)" % (total,))
        total = None

    completed = implementation.get("completed_tasks")
    if not isinstance(completed, list):
        problems.append("implementation.completed_tasks must be a list (got %r)"
                        % (completed,))
    elif not all(is_nonneg_int(c) for c in completed):
        problems.append("implementation.completed_tasks must contain only "
                        "non-negative integers (got %r)" % (completed,))
    elif current is not None and sorted(completed) != list(range(1, current + 1)):
        problems.append("implementation.completed_tasks %r does not match "
                        "current_task=%d (expected [1..%d])"
                        % (completed, current, current))
    elif total is not None and completed and completed[-1] > total:
        problems.append("implementation.completed_tasks contains task %d > "
                        "total_tasks (%d)" % (completed[-1], total))

    if current is not None and total is not None:
        if current > total:
            problems.append("implementation.current_task (%d) > total_tasks (%d)"
                            % (current, total))
        else:
            hashes = implementation.get("task_hashes")
            if isinstance(hashes, list) and len(hashes) != total:
                problems.append(
                    "implementation.total_tasks (%d) does not match the %d "
                    "registered task hashes" % (total, len(hashes)))
    return problems


def readiness_problems(root, ticket_id, data):
    """v2 execution-readiness problems; [] means a v2 executor may proceed.

    Read-only. Every condition here is v2-only, so a v1 Ticket always returns
    []. A v2 executor may not enter `implementation` or complete a task unless
    a registered Plan is present and unchanged (byte identity and task-hash
    identity), the counters cohere, the Status is `active`, and — for an adopted
    repo — the six-item `adoption_checkpoint` is fully confirmed. The fresh
    evidence binding is enforced separately by `mutate`/`validate` so the stale
    gate rule has a single source of truth.
    """
    if version(data) != 2:
        return []

    out = []
    implementation = data.get("implementation") or {}

    # 1-3: a registered Plan whose bytes and task contracts are unchanged.
    sources = data.get("source_artifacts") or {}
    plan_ref = sources.get("plan") or {}
    plan_path = plan_ref.get("path")
    plan_sha = plan_ref.get("sha256")
    if not plan_path or not plan_sha:
        out.append("no registered Plan (register one with `register-plan` in "
                   "planning before implementing)")
    else:
        full = os.path.join(root, plan_path)
        if not os.path.exists(full):
            out.append("registered Plan %r is missing on disk" % plan_path)
        else:
            try:
                current_sha = contracts.sha256_file(full)
            except OSError as exc:
                out.append("registered Plan %r cannot be read: %s"
                           % (plan_path, exc))
            else:
                if not isinstance(plan_sha, str) or current_sha != plan_sha:
                    out.append("registered Plan %r changed since registration "
                               "(drifted Plan: re-register it)" % plan_path)
                else:
                    try:
                        tasks = contracts.read_plan(full, ticket_id)
                    except contracts.ContractError as exc:
                        out.append("registered Plan %r is no longer a valid Plan: "
                                   "%s" % (plan_path, exc))
                    else:
                        recorded = implementation.get("task_hashes")
                        expected = [t["sha256"] for t in tasks]
                        if not isinstance(recorded, list) \
                                or [str(h) for h in recorded] != expected:
                            out.append("registered Plan task contracts changed "
                                       "since registration (task-hash drift)")

    # 4: counter coherence (the registered total is authoritative).
    out.extend(counter_problems(implementation))

    # 6: only an active ticket may execute.
    status = data.get("status")
    if status != "active":
        out.append("ticket status is %r; only an active ticket may be executed "
                   "(resolve the block or resume it first)" % status)

    # 7: an adopted repo needs a confirmed adoption checkpoint.
    migration = data.get("migration") or {}
    if migration.get("adopted_existing_repo"):
        checkpoint = data.get("adoption_checkpoint") or {}
        missing = [name for name in ADOPTION_CONFIRMATIONS
                   if checkpoint.get(name) is not True]
        if missing:
            out.append("adoption checkpoint is not confirmed (%s must all be "
                       "true before an executor proceeds)" % ", ".join(missing))
    return out
