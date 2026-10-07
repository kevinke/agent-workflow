"""`ai-workflow` semantic state mutations (spec §9 extension, TICKET-010).

The state machine and the restricted YAML subset are encoded here so a harness
never has to hand-write `state.yaml`: it declares intent (`advance`, `claim`,
`complete-task`, `set-gate`, `escalate`) and this module loads, checks, mutates,
and saves through the kit's own parser — rejecting illegal transitions and gate
violations at write time instead of relying on a later `validate` pass.
"""

import datetime
import os
import re

import contracts
import review
import state
import validate
import workflow_v2

__all__ = ["MutateError", "TRANSITIONS", "DEFAULT_NEXT",
           "advance", "claim", "complete_task", "set_gate", "escalate",
           "set_status", "release", "register_plan", "set_review"]

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


def _escalation_required(data):
    """True when a recorded escalation is still unresolved."""
    return bool((data.get("escalation") or {}).get("required"))


def _escalation_block(action):
    """The MutateError message for a routine command blocked by escalation."""
    return MutateError(
        "cannot %s while an escalation is required: a senior must resolve the "
        "underlying issue and record it with `escalate --clear --resolution ...` "
        "first" % action)


# A resolution must carry a supporting reference and may not be bare prose.
_DOC_ID_RE = re.compile(r"\b(?:F|DQ)-[0-9]+\b")
_REF_PATH_RE = re.compile(r"[A-Za-z0-9_./-]*\.[A-Za-z]{2,6}\b")
_COMMIT_RE = re.compile(r"\b[0-9a-f]{7,40}\b")
_USER_RE = re.compile(r"\buser", re.IGNORECASE)


def _resolution_has_reference(text):
    """A minimal, documented rule: at least one supporting reference token.

    Accepts a document id (`F-<n>`/`DQ-<n>`), a repository-relative path (a
    dotted extension such as `decision.md` or `.ai/work/.../handoff.md`), or a
    commit hash. This declares the resolution; it does not authenticate it.
    """
    return bool(_DOC_ID_RE.search(text) or _REF_PATH_RE.search(text)
                or _COMMIT_RE.search(text))


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


_REVIEW_ENTRY_ARTIFACTS = (
    ("evidence", "evidence.md"),
    ("evidence_audit", "evidence-audit.md"),
    ("decision", "decision.md"),
    ("handoff", "handoff.md"),
)


def _require_review_entry(root, ticket_id, data):
    """v2: entering `review` needs a ready, finished implementation.

    Requires the execution-readiness conditions (a current registered Plan,
    coherent counters, an active Status), every registered task complete, and
    the required artifacts present (evidence, evidence-audit, decision,
    handoff). Every failure is actionable and leaves State unchanged.
    """
    problems = workflow_v2.readiness_problems(root, ticket_id, data)
    if problems:
        raise MutateError("cannot enter review: %s" % "; ".join(problems))
    impl = data.get("implementation") or {}
    if workflow_v2.executable_task(impl) is not None:
        raise MutateError(
            "cannot enter review: not all registered tasks are complete "
            "(implementation.current_task=%r of total_tasks=%r)"
            % (impl.get("current_task"), impl.get("total_tasks")))
    missing = [default for key, default in _REVIEW_ENTRY_ARTIFACTS
               if not os.path.exists(
                   _artifact_path(root, ticket_id, data, key, default))]
    if missing:
        raise MutateError(
            "cannot enter review: missing required artifact(s) %s"
            % ", ".join(missing))


def _require_current_pass(root, ticket_id, data):
    """v2: `review -> done` needs a CURRENT passing review.

    Requires `review.verdict == "pass"`, the bound Review-artifact hash still
    matching `review.md`, the bound `plan_sha256` still matching the registered
    Plan, and empty code drift since the reviewed commit. A missing verdict,
    `changes_requested`, a stale binding, or a moved reviewed commit rejects the
    transition and leaves State unchanged. Missing Git or a non-ancestor commit
    is reported as a MutateError, not a traceback.
    """
    block = data.get("review")
    if not isinstance(block, dict):
        block = {}
    verdict = block.get("verdict")
    if verdict != "pass":
        raise MutateError(
            "cannot complete: phase=done requires a current `pass` review "
            "(review.verdict=%r)" % (verdict,))

    review_path = _artifact_path(root, ticket_id, data, "review", "review.md")
    try:
        current_sha = contracts.sha256_file(review_path)
    except OSError as exc:
        raise MutateError(
            "cannot complete: the Review artifact is unreadable: %s" % exc)
    if current_sha != block.get("artifact_sha256"):
        raise MutateError(
            "cannot complete: the Review artifact changed since the verdict was "
            "recorded (stale binding: re-review and `set-review` again)")

    sources = data.get("source_artifacts") or {}
    plan_ref = sources.get("plan") or {}
    if block.get("plan_sha256") != plan_ref.get("sha256"):
        raise MutateError(
            "cannot complete: the Review binds a different Plan than the "
            "registered one (stale binding: re-review against the current Plan)")
    try:
        drift = review.code_drift(root, ticket_id, block.get("reviewed_commit"),
                                  plan_ref.get("path"))
    except contracts.ContractError as exc:
        raise MutateError("cannot complete: %s" % exc)
    if drift:
        raise MutateError(
            "cannot complete: the reviewed code changed since %s: %s"
            % (block.get("reviewed_commit"), "; ".join(drift)))


def _require_repair(root, ticket_id, data):
    """v2: the append-only `review -> implementation` repair precondition.

    Requires a recorded `changes_requested` verdict whose Review artifact is
    unchanged (a stale failed Review is rejected), code identity unchanged since
    the reviewed commit, and a registered Plan with tasks appended beyond the
    completed prefix whose completed prefix is unchanged. The appended Plan is
    the rework itself, so a plan-only change is expected and is not drift; only
    the append/prefix consistency is checked. An unresolved escalation is
    blocked earlier in `advance`.
    """
    block = data.get("review")
    verdict = block.get("verdict") if isinstance(block, dict) else None
    if verdict != "changes_requested":
        raise MutateError(
            "cannot repair: review -> implementation requires a recorded "
            "changes_requested verdict (review.verdict=%r)" % (verdict,))

    review_path = _artifact_path(root, ticket_id, data, "review", "review.md")
    try:
        current_sha = contracts.sha256_file(review_path)
    except OSError as exc:
        raise MutateError(
            "cannot repair: the Review artifact is unreadable: %s" % exc)
    if current_sha != block.get("artifact_sha256"):
        raise MutateError(
            "cannot repair: the recorded Review artifact changed since the "
            "verdict was recorded (stale failed Review: re-record it)")

    sources = data.get("source_artifacts") or {}
    plan_ref = sources.get("plan") or {}
    plan_path = plan_ref.get("path")
    try:
        drift = review.code_drift(root, ticket_id, block.get("reviewed_commit"),
                                  plan_path)
    except contracts.ContractError as exc:
        raise MutateError("cannot repair: %s" % exc)
    plan_note = ("the registered Plan changed since the reviewed commit: %s"
                 % (plan_path or "").replace("\\", "/"))
    drift = [problem for problem in drift if problem != plan_note]
    if drift:
        raise MutateError(
            "cannot repair: the reviewed code changed since %s: %s"
            % (block.get("reviewed_commit"), "; ".join(drift)))

    impl = data.get("implementation") or {}
    current = impl.get("current_task", 0)
    total = impl.get("total_tasks", 0)
    current = 0 if current is None else current
    total = 0 if total is None else total
    if not workflow_v2.is_nonneg_int(current) \
            or not workflow_v2.is_nonneg_int(total) or current >= total:
        raise MutateError(
            "cannot repair: the registered Plan has no appended task beyond the "
            "completed prefix (current_task=%r, total_tasks=%r); register an "
            "appending rework Plan first"
            % (impl.get("current_task"), impl.get("total_tasks")))

    if current:
        if not plan_path:
            raise MutateError(
                "cannot repair: no registered Plan to check the completed "
                "prefix against")
        try:
            tasks = contracts.read_plan(os.path.join(root, plan_path), ticket_id)
        except contracts.ContractError as exc:
            raise MutateError(
                "cannot repair: the registered Plan is invalid: %s" % exc)
        recorded = [str(h) for h in (impl.get("task_hashes") or [])]
        expected = [t["sha256"] for t in tasks[:current]]
        if recorded[:current] != expected:
            raise MutateError(
                "cannot repair: the completed prefix task contracts changed; "
                "completed tasks must stay unchanged")


def advance(root, ticket_id, to):
    """Move a ticket to phase `to` along the state machine.

    Enforces the transition table (including the v2-only repair edge), the
    evidence gate on decisionward targets, and the gate-branched exit from
    evidence_audit. On a v2 Ticket it additionally gates completion: entering
    `review` needs a finished, ready implementation; `done` needs a current
    passing Review; and `review -> implementation` is the append-only repair.
    Returns a confirmation line.
    """
    _require_phase(to)
    data = _load(root, ticket_id)
    ver = workflow_v2.version(data)
    if ver == 2 and _escalation_required(data):
        raise _escalation_block("advance")
    current = data.get("phase")
    if current not in TRANSITIONS:
        raise MutateError("cannot advance from phase %r (terminal or unknown)" % current)
    if to == current:
        raise MutateError("already in phase %r" % current)
    try:
        workflow_v2.check_transition(root, data, to)
    except contracts.ContractError as exc:
        raise MutateError(str(exc))

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
    if ver == 2 and to in validate.DECISIONWARDS:
        _require_fresh_binding(root, ticket_id, data)

    # v2 execution readiness: entering implementation needs a current registered
    # Plan, coherent counters, an active Status, and a safe adoption checkpoint.
    # From `review` this is the append-only repair, which clears the failed
    # verdict (in the same save) and routes to the first appended task.
    if ver == 2 and to == "implementation":
        problems = workflow_v2.readiness_problems(root, ticket_id, data)
        if problems:
            raise MutateError(
                "cannot enter implementation: %s" % "; ".join(problems))
        if current == "review":
            _require_repair(root, ticket_id, data)
            review_block = dict(data.get("review") or {})
            review_block["verdict"] = "pending"
            data["review"] = review_block

    # v2 completion guards: a finished implementation to review, a current pass
    # to done.
    if ver == 2 and to == "review":
        _require_review_entry(root, ticket_id, data)
    if ver == 2 and to == "done":
        _require_current_pass(root, ticket_id, data)

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

    if ver == 2 and _escalation_required(data):
        raise _escalation_block("complete a task")

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


def set_review(root, ticket_id, verdict):
    """Record the Reviewer's verdict on a v2 Ticket (SCOUT-005).

    Requires the review phase, no unresolved escalation, a ready execution state
    (current registered Plan, coherent counters, active Status), every registered
    task complete, a structurally valid Review artifact whose Metadata `verdict`
    equals the CLI value and whose `plan_sha256` equals the registered Plan hash,
    and clean reviewed code (no drift since the reviewed commit). On success it
    binds the verdict to the Review artifact's raw-byte hash, the reviewed commit
    and the Plan hash in a single save. Every rejection leaves State unchanged.
    """
    data = _load(root, ticket_id)
    if workflow_v2.version(data) != 2:
        raise MutateError(
            "set-review requires workflow_version 2 (this Ticket is v1; "
            "upgrade it explicitly first)")
    if verdict not in ("pass", "changes_requested"):
        raise MutateError(
            "unknown verdict %r (must be pass or changes_requested)" % verdict)
    if data.get("phase") != "review":
        raise MutateError(
            "set-review is only allowed in the review phase (current phase=%r)"
            % data.get("phase"))
    if _escalation_required(data):
        raise _escalation_block("record a review")

    problems = workflow_v2.readiness_problems(root, ticket_id, data)
    if problems:
        raise MutateError("cannot record a review: %s" % "; ".join(problems))

    impl = data.get("implementation") or {}
    total_tasks = impl.get("total_tasks")
    if not workflow_v2.is_nonneg_int(total_tasks) or total_tasks <= 0:
        raise MutateError(
            "cannot record a review: no registered task count "
            "(implementation.total_tasks=%r)" % (total_tasks,))
    if workflow_v2.executable_task(impl) is not None:
        raise MutateError(
            "cannot record a review: not all registered tasks are complete "
            "(implementation.current_task=%r of total_tasks=%r)"
            % (impl.get("current_task"), total_tasks))

    artifact_path = _artifact_path(root, ticket_id, data, "review", "review.md")
    try:
        report = contracts.read_artifact(artifact_path, "review")
    except contracts.ContractError as exc:
        raise MutateError("cannot record a review: the Review artifact is not a "
                          "structured report (%s)" % exc)
    review_problems = contracts.validate_review(report, ticket_id, verdict)
    if review_problems:
        raise MutateError("cannot record a review: the Review artifact is "
                          "structurally invalid: %s" % "; ".join(review_problems))

    md = report.get("metadata") or {}
    sources = data.get("source_artifacts") or {}
    plan_ref = sources.get("plan") or {}
    registered_plan_sha = plan_ref.get("sha256")
    if md.get("plan_sha256") != registered_plan_sha:
        raise MutateError(
            "cannot record a review: the Review binds a different Plan than the "
            "registered one (artifact plan_sha256=%r, registered=%r)"
            % (md.get("plan_sha256"), registered_plan_sha))

    reviewed_commit = md.get("reviewed_commit")
    try:
        drift = review.code_drift(root, ticket_id, reviewed_commit,
                                  plan_ref.get("path"))
    except contracts.ContractError as exc:
        raise MutateError("cannot record a review: %s" % exc)
    if drift:
        raise MutateError(
            "cannot record a review: the reviewed code changed since %s: %s"
            % (reviewed_commit, "; ".join(drift)))

    try:
        artifact_sha = contracts.sha256_file(artifact_path)
    except OSError as exc:
        raise MutateError("cannot read the Review artifact: %s" % exc)

    data["review"] = {
        "verdict": verdict,
        "artifact_sha256": artifact_sha,
        "reviewed_commit": reviewed_commit,
        "plan_sha256": md.get("plan_sha256"),
    }
    artifacts = dict(data.get("artifacts") or {})
    if "review" not in artifacts:
        artifacts["review"] = "review.md"
    data["artifacts"] = artifacts

    _save(root, ticket_id, data)
    return "%s: review verdict=%s (commit %s)" % (
        ticket_id, verdict, reviewed_commit)


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


def escalate(root, ticket_id, scope=None, reason=None, clear=False,
             resolution=None):
    """Set or clear the escalation block.

    On a v1 Ticket this is the original loose behavior (write the `escalation`
    block only). On a v2 Ticket escalation is atomic: it records the interrupted
    continuation, sets `status=escalation_required` and routes `next_action` to
    the phase's senior resolver, while routine advances/completion and a raw
    Status overwrite are rejected. Clearing requires a documented `--resolution`
    (with supporting references, and the user's answer for a human scope) and
    restores the previous Status and a recomputed phase-appropriate action.
    Every rejection leaves State unchanged.
    """
    data = _load(root, ticket_id)

    if workflow_v2.version(data) != 2:
        # v1 semantics are byte-compatible with the original implementation.
        if clear:
            data["escalation"] = {"required": False, "scope": "machine",
                                  "reason": None}
            _save(root, ticket_id, data)
            return "%s: escalation cleared" % ticket_id
        if scope not in validate.SCOPES:
            raise MutateError("unknown escalation scope %r (machine|human)" % scope)
        data["escalation"] = {"required": True, "scope": scope, "reason": reason}
        _save(root, ticket_id, data)
        return "%s: escalation required (scope=%s)" % (ticket_id, scope)

    esc = data.get("escalation") or {}
    if not isinstance(esc, dict):
        esc = {}

    if clear:
        current_scope = scope if scope in validate.SCOPES else esc.get("scope")
        text = resolution.strip() if isinstance(resolution, str) else ""
        if not text:
            raise MutateError(
                "cannot clear a v2 escalation without --resolution: record the "
                "senior resolution and the artifacts that support it")
        if not _resolution_has_reference(text):
            raise MutateError(
                "the escalation --resolution must reference supporting evidence: "
                "a document id (F-<n>/DQ-<n>), a repository-relative path with a "
                "dotted extension, or a commit hash")
        if current_scope == "human" and not _USER_RE.search(text):
            raise MutateError(
                "a human escalation must record the user's answer: mention the "
                "user and the answer in --resolution")

        previous = esc.get("previous_status")
        if previous == "escalation_required":
            raise MutateError(
                "cannot restore escalation_required as the previous Status: the "
                "recorded continuation is inconsistent")
        if previous not in validate.STATUSES:
            previous = "active"

        esc["required"] = False
        if current_scope in validate.SCOPES:
            esc["scope"] = current_scope
        esc["reason"] = None
        esc["resolution"] = text
        data["escalation"] = esc
        data["status"] = previous
        data["next_action"] = workflow_v2.next_action(data, data.get("phase"))
        _save(root, ticket_id, data)
        return "%s: escalation cleared (status=%s)" % (ticket_id, previous)

    if scope not in validate.SCOPES:
        raise MutateError("unknown escalation scope %r (machine|human)" % scope)
    if data.get("phase") == "done" or data.get("status") == "abandoned":
        raise MutateError(
            "cannot escalate a %s ticket: there is no routine work to interrupt"
            % ("done" if data.get("phase") == "done" else "abandoned"))

    if not esc.get("required"):
        # First escalation: record the continuation this interrupts.
        next_action = data.get("next_action") or {}
        esc["previous_status"] = data.get("status")
        esc["interrupted_action"] = {
            "role": next_action.get("role"),
            "action": next_action.get("action"),
            "task": next_action.get("task"),
        }
        esc["interrupted_phase"] = data.get("phase")
    # Repeated escalation keeps the stored continuation (store on the first only).
    esc["required"] = True
    esc["scope"] = scope
    esc["reason"] = reason
    if "resolution" not in esc:
        esc["resolution"] = None
    data["escalation"] = esc
    data["status"] = "escalation_required"
    data["next_action"] = workflow_v2.escalated_next_action(data.get("phase"))
    _save(root, ticket_id, data)
    return "%s: escalation required (scope=%s)" % (ticket_id, scope)


def set_status(root, ticket_id, status):
    """Set the lateral status (orthogonal to phase).

    On a v2 Ticket an unresolved escalation locks the Status to
    `escalation_required`: any other target is rejected and State is unchanged,
    so a bare `set-status active` cannot bypass escalation.
    """
    if status not in validate.STATUSES:
        raise MutateError("unknown status %r (must be one of %s)"
                          % (status, ", ".join(sorted(validate.STATUSES))))
    data = _load(root, ticket_id)
    if workflow_v2.version(data) == 2 and _escalation_required(data) \
            and status != "escalation_required":
        raise MutateError(
            "cannot set status %r while an escalation is required: it stays "
            "escalation_required until `escalate --clear --resolution ...` "
            "resolves it" % status)
    data["status"] = status
    _save(root, ticket_id, data)
    return "%s: status=%s" % (ticket_id, status)


def release(root, ticket_id):
    """Clear the soft claim; provenance is kept for the audit trail."""
    data = _load(root, ticket_id)
    data["claim"] = {"harness": None, "model": None, "claimed_at": None}
    _save(root, ticket_id, data)
    return "%s: claim released" % ticket_id
