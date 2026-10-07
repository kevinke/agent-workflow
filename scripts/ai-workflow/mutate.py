"""`ai-workflow` semantic state mutations (spec §9 extension, TICKET-010).

The state machine and the restricted YAML subset are encoded here so a harness
never has to hand-write `state.yaml`: it declares intent (`advance`, `claim`,
`complete-task`, `set-gate`, `escalate`) and this module loads, checks, mutates,
and saves through the kit's own parser — rejecting illegal transitions and gate
violations at write time instead of relying on a later `validate` pass.
"""

import datetime
import os

import contracts
import state
import validate
import workflow_v2

__all__ = ["MutateError", "TRANSITIONS", "DEFAULT_NEXT",
           "advance", "claim", "complete_task", "set_gate", "escalate",
           "set_status", "release", "register_plan"]

_WORK_DIR_REL = os.path.join(".ai", "work")


class MutateError(Exception):
    """Raised when a state mutation would violate the protocol."""


# Allowed phase transitions and next_action routes come from the shared
# workflow_v2 tables so the mutator and validate cannot drift apart
# (dependency order: contracts -> workflow_v2 -> validate -> mutate).
# `requirement` is only ever a start phase, so it has no default next_action.
TRANSITIONS = workflow_v2.TRANSITIONS
DEFAULT_NEXT = {
    phase: route for phase, route in workflow_v2.NEXT_ACTIONS.items()
    if phase != "requirement"
}


def _ticket_path(root, ticket_id):
    return os.path.join(root, _WORK_DIR_REL, ticket_id, "state.yaml")


def _load(root, ticket_id):
    path = _ticket_path(root, ticket_id)
    if not os.path.exists(path):
        raise MutateError(
            "no ticket %s under .ai/work/ (run `start` or `adopt` first)" % ticket_id)
    try:
        data = state.load_file(path)
    except state.StateError as exc:
        raise MutateError(str(exc))
    try:
        workflow_v2.version(data)
    except contracts.ContractError as exc:
        raise MutateError(str(exc))
    return data


def _save(root, ticket_id, data):
    state.save_file(_ticket_path(root, ticket_id), data)


def _require_phase(phase):
    if phase not in validate.PHASES:
        raise MutateError("unknown phase %r (must be one of %s)"
                          % (phase, ", ".join(sorted(validate.PHASES))))


def _artifact_path(root, ticket_id, data, key, default):
    artifacts = data.get("artifacts") or {}
    return os.path.join(root, _WORK_DIR_REL, ticket_id,
                        artifacts.get(key, default))


def _set_gate_allowed(data, phase):
    """set-gate is an evidence_audit act, or a recorded senior reconstruction."""
    if phase == "evidence_audit":
        return True
    upgrade = data.get("upgrade") or {}
    return bool(upgrade.get("requires_reconstruction"))


def _require_fresh_binding(root, ticket_id, data):
    """v2: the recorded gate must still match the audited artifact bytes."""
    evidence = data.get("evidence") or {}
    expected_report = evidence.get("report_sha256")
    expected_audit = evidence.get("audit_sha256")
    if not expected_report or not expected_audit:
        raise MutateError(
            "evidence gate is not bound to audited artifacts "
            "(audit the evidence and `set-gate` first)")
    ev_path = _artifact_path(root, ticket_id, data, "evidence", "evidence.md")
    audit_path = _artifact_path(root, ticket_id, data, "evidence_audit",
                                "evidence-audit.md")
    try:
        report_sha = contracts.sha256_file(ev_path)
        audit_sha = contracts.sha256_file(audit_path)
    except OSError as exc:
        raise MutateError("cannot read the audited artifacts: %s" % exc)
    if report_sha != expected_report or audit_sha != expected_audit:
        raise MutateError(
            "stale evidence gate: the audited Evidence or its audit changed "
            "since the verdict was recorded (re-audit and `set-gate` again)")


def _bind_v2_gate(root, ticket_id, data, gate, round_no):
    """Validate the concrete reports, then return the v2 gate binding fields."""
    phase = data.get("phase")
    if not _set_gate_allowed(data, phase):
        raise MutateError(
            "set-gate is only allowed in evidence_audit (or a recorded senior "
            "escalation resolution); current phase=%r" % phase)

    ev_path = _artifact_path(root, ticket_id, data, "evidence", "evidence.md")
    audit_path = _artifact_path(root, ticket_id, data, "evidence_audit",
                                "evidence-audit.md")
    try:
        report = contracts.read_artifact(ev_path, "evidence")
    except contracts.ContractError as exc:
        raise MutateError("cannot bind gate: Evidence is not a structured "
                          "report (%s)" % exc)
    problems = contracts.validate_evidence(report, ticket_id)
    if problems:
        raise MutateError("cannot bind gate: Evidence is structurally invalid: %s"
                          % "; ".join(problems))
    evidence_round = (report.get("metadata") or {}).get("round")
    if isinstance(evidence_round, bool) or not isinstance(evidence_round, int) \
            or evidence_round <= 0:
        raise MutateError(
            "cannot bind gate: Evidence Metadata round %r is missing or illegal"
            % evidence_round)
    if round_no is None:
        round_no = evidence_round
    if round_no != evidence_round:
        raise MutateError(
            "cannot bind gate: round %r does not name the Evidence Metadata "
            "round %r" % (round_no, evidence_round))

    try:
        audit = contracts.read_artifact(audit_path, "evidence-audit")
    except contracts.ContractError as exc:
        raise MutateError("cannot bind gate: Audit is not a structured "
                          "report (%s)" % exc)
    audit_problems = contracts.validate_audit(audit, ticket_id, gate, round_no)
    if audit_problems:
        raise MutateError("cannot bind gate: Audit is structurally invalid: %s"
                          % "; ".join(audit_problems))

    report_sha256 = contracts.sha256_file(ev_path)
    audit_sha256 = contracts.sha256_file(audit_path)
    attested = (audit.get("metadata") or {}).get("evidence_sha256")
    if attested != report_sha256:
        raise MutateError(
            "cannot bind gate: the audit attests evidence_sha256 %s but the "
            "current Evidence hashes to %s" % (attested, report_sha256))
    return {"round": round_no, "report_sha256": report_sha256,
            "audit_sha256": audit_sha256}


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

    # v2 decisionward continuation: the sufficient gate must still be bound to
    # the audited artifacts; a changed report or audit makes the verdict stale.
    if workflow_v2.version(data) == 2 and to in validate.DECISIONWARDS:
        _require_fresh_binding(root, ticket_id, data)

    # v2 execution readiness: entering implementation needs a current registered
    # Plan, coherent counters, an active Status, and a safe adoption checkpoint.
    if workflow_v2.version(data) == 2 and to == "implementation":
        problems = workflow_v2.readiness_problems(root, ticket_id, data)
        if problems:
            raise MutateError(
                "cannot enter implementation: %s" % "; ".join(problems))

    data["phase"] = to
    data["next_action"] = workflow_v2.next_action(data, to)
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
    """Mark one implementation task complete (increment current_task).

    On a v2 Ticket the task must be a bounded, registered, current one: the
    phase is `implementation`, the registered Plan is present and unchanged,
    the counters cohere, the gate binding is fresh, and no `--total` may
    override the registered count. Counters are non-negative integers on both
    versions (booleans are never integers). On completion the explicit
    `next_action.task` is refreshed. Every rejection leaves State unchanged.
    """
    data = _load(root, ticket_id)
    ver = workflow_v2.version(data)
    phase = data.get("phase")
    impl = data.get("implementation") or {}

    if ver == 2:
        if phase != "implementation":
            raise MutateError(
                "cannot complete a task outside implementation (phase=%r)"
                % phase)
        problems = workflow_v2.readiness_problems(root, ticket_id, data)
        if problems:
            raise MutateError(
                "cannot complete a task: %s" % "; ".join(problems))
        _require_fresh_binding(root, ticket_id, data)

    current = impl.get("current_task", 0)
    total_tasks = impl.get("total_tasks", 0)
    current = 0 if current is None else current
    total_tasks = 0 if total_tasks is None else total_tasks
    if not workflow_v2.is_nonneg_int(current):
        raise MutateError(
            "implementation.current_task must be a non-negative integer "
            "(got %r); reconcile against `git log --grep ai-workflow(` and "
            "progress.md" % (current,))
    if not workflow_v2.is_nonneg_int(total_tasks):
        raise MutateError(
            "implementation.total_tasks must be a non-negative integer (got %r)"
            % (total_tasks,))
    completed = list(impl.get("completed_tasks") or [])
    if not all(workflow_v2.is_nonneg_int(c) for c in completed):
        raise MutateError(
            "implementation.completed_tasks contains non-integer entries; "
            "reconcile against `git log --grep ai-workflow(` and progress.md")
    if sorted(completed) != list(range(1, current + 1)):
        raise MutateError(
            "implementation counters out of sync: current_task=%d but "
            "completed_tasks=%s (expected [1..%d]); reconcile against "
            "`git log --grep ai-workflow(` and progress.md — do not "
            "hand-edit current_task" % (current, completed, current))

    if total is not None:
        if ver == 2:
            if not workflow_v2.is_nonneg_int(total) or int(total) != total_tasks:
                raise MutateError(
                    "cannot override the registered task count: --total %r "
                    "disagrees with implementation.total_tasks=%d (the "
                    "registered Plan is authoritative)" % (total, total_tasks))
        else:
            try:
                total_tasks = int(total)
            except (TypeError, ValueError):
                raise MutateError("--total must be a positive integer")

    if total_tasks <= 0:
        raise MutateError(
            "cannot complete a task: total_tasks=%s (set --total N first)" % total_tasks)
    if current >= total_tasks:
        raise MutateError("all %d tasks already complete" % total_tasks)
    current += 1
    if current not in completed:
        completed.append(current)
    impl["current_task"] = current
    impl["total_tasks"] = total_tasks
    impl["completed_tasks"] = completed
    data["implementation"] = impl
    if ver == 2:
        data["next_action"] = workflow_v2.next_action(data, phase)
    _save(root, ticket_id, data)
    return "%s: task %d/%d complete" % (ticket_id, current, total_tasks)


def _register_mode(data):
    """Why register-plan is allowed here (or None): the spec's three contexts."""
    if (data.get("upgrade") or {}).get("requires_reconstruction"):
        return "reconstruction"
    phase = data.get("phase")
    if phase == "planning":
        return "planning"
    if phase == "review" and (data.get("review") or {}).get("verdict") \
            == "changes_requested":
        return "review"
    return None


def register_plan(root, ticket_id, path, total):
    """Register a referenced execution Plan on a v2 Ticket (SCOUT-003).

    Loads and structurally validates the Plan, bounds its path to the repository,
    checks the declared task count, and records the reference, the Plan's byte
    hash and the ordered canonical task hashes without counting any task
    complete. Re-registration preserves the completed-task prefix and counter
    history and is allowed only in planning, a recorded senior reconstruction, or
    a strictly-appending changes_requested review. Every rejection leaves State
    unchanged.
    """
    data = _load(root, ticket_id)
    if workflow_v2.version(data) != 2:
        raise MutateError(
            "register-plan requires workflow_version 2 (this Ticket is v1; "
            "upgrade it explicitly first)")
    if not path:
        raise MutateError("--path <plan> is required")
    if os.path.isabs(path):
        raise MutateError(
            "plan path must be repository-relative, not absolute: %r" % path)
    full = os.path.join(root, path)
    if not os.path.exists(full):
        raise MutateError("plan file does not exist: %r" % path)
    real_root = os.path.realpath(root)
    real_full = os.path.realpath(full)
    if real_full != real_root and not real_full.startswith(real_root + os.sep):
        raise MutateError("plan path escapes the repository root: %r" % path)

    try:
        tasks = contracts.read_plan(full, ticket_id)
    except contracts.ContractError as exc:
        raise MutateError("cannot register the Plan: %s" % exc)

    if total is None:
        raise MutateError("--total N is required")
    try:
        total = int(total)
    except (TypeError, ValueError):
        raise MutateError("--total must be a positive integer")
    if total != len(tasks):
        raise MutateError(
            "declared total %d does not match the Plan's %d task sections"
            % (total, len(tasks)))

    mode = _register_mode(data)
    if mode is None:
        raise MutateError(
            "register-plan is allowed only in planning, a recorded senior "
            "escalation resolution, or changes_requested review append; "
            "current phase=%r" % data.get("phase"))

    impl = dict(data.get("implementation") or {})
    current = impl.get("current_task", 0) or 0
    if isinstance(current, bool) or not isinstance(current, int) or current < 0:
        raise MutateError("implementation.current_task is not a non-negative integer")
    old_hashes = impl.get("task_hashes") or []
    if not isinstance(old_hashes, list):
        raise MutateError("implementation.task_hashes must be a list")
    old_hashes = [str(h) for h in old_hashes]

    if len(tasks) < current:
        raise MutateError(
            "the new Plan has %d tasks but %d are already complete; a new total "
            "cannot be less than the completed count" % (len(tasks), current))
    if current and len(old_hashes) < current:
        raise MutateError(
            "implementation.task_hashes does not cover the %d completed tasks; "
            "reconcile the registered Plan before re-registering" % current)
    if current and [t["sha256"] for t in tasks[:current]] != old_hashes[:current]:
        raise MutateError(
            "cannot re-register: the contract of a completed task (1..%d) "
            "changed; completed tasks must stay unchanged" % current)
    if mode == "review" and len(tasks) <= len(old_hashes):
        raise MutateError(
            "changes_requested review rework must strictly append tasks "
            "(registered %d, new Plan has %d)"
            % (len(old_hashes), len(tasks)))

    sources = dict(data.get("source_artifacts") or {})
    plan_ref = dict(sources.get("plan") or {})
    plan_ref["path"] = path
    plan_ref["sha256"] = contracts.sha256_file(full)
    sources["plan"] = plan_ref
    data["source_artifacts"] = sources

    impl["total_tasks"] = len(tasks)
    impl["current_task"] = current
    impl["completed_tasks"] = list(impl.get("completed_tasks") or [])
    impl["task_hashes"] = [t["sha256"] for t in tasks]
    data["implementation"] = impl

    _save(root, ticket_id, data)
    return "%s: registered plan %s (%d tasks, %d complete)" % (
        ticket_id, path, len(tasks), current)


def set_gate(root, ticket_id, gate, round_no=None):
    """Record the auditor's evidence verdict.

    On a v2 Ticket the verdict is bound to the SHA-256 of the audited Evidence
    and its Audit artifact, and only concrete, metadata-consistent reports may
    be recorded (in evidence_audit, or a recorded senior reconstruction). v1
    keeps the loose, unbound behavior.
    """
    if gate not in validate.GATES:
        raise MutateError("unknown gate %r (must be sufficient or insufficient)" % gate)
    data = _load(root, ticket_id)
    evidence = data.get("evidence") or {}

    if workflow_v2.version(data) == 2:
        if round_no is not None:
            try:
                round_no = int(round_no)
            except (TypeError, ValueError):
                raise MutateError("round must be a positive integer")
            if round_no <= 0:
                raise MutateError("round must be a positive integer")
        bound = _bind_v2_gate(root, ticket_id, data, gate, round_no)
        evidence["round"] = bound["round"]
        evidence["gate"] = gate
        evidence["report_sha256"] = bound["report_sha256"]
        evidence["audit_sha256"] = bound["audit_sha256"]
    else:
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


def set_status(root, ticket_id, status):
    """Set the lateral status (orthogonal to phase)."""
    if status not in validate.STATUSES:
        raise MutateError("unknown status %r (must be one of %s)"
                          % (status, ", ".join(sorted(validate.STATUSES))))
    data = _load(root, ticket_id)
    data["status"] = status
    _save(root, ticket_id, data)
    return "%s: status=%s" % (ticket_id, status)


def release(root, ticket_id):
    """Clear the soft claim; provenance is kept for the audit trail."""
    data = _load(root, ticket_id)
    data["claim"] = {"harness": None, "model": None, "claimed_at": None}
    _save(root, ticket_id, data)
    return "%s: claim released" % ticket_id
