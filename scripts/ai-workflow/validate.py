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
import review
import state
import workflow_v2
from status import list_tickets

__all__ = ["validate_ticket", "validate_repo", "reconstruction_problems",
           "PHASES", "STATUSES", "GATES", "SCOPES", "ROLES", "DECISIONWARDS"]


PHASES = {
    "requirement", "evidence_collection", "evidence_audit", "followup_evidence",
    "technical_decision", "planning", "implementation", "review", "done",
}
STATUSES = {"active", "blocked", "escalation_required", "paused", "abandoned"}
GATES = {"sufficient", "insufficient"}
SCOPES = {"machine", "human"}
ROLES = {
    "scout", "evidence-auditor", "technical-decision", "executor-plan",
    "ticket-executor", "checkpoint-handoff", "workflow-bootstrap", "reviewer",
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

# Phases where a v2 executor may run: the execution-readiness gate and its
# problems (registered Plan, coherence, active Status, adoption checkpoint)
# apply here, and the shared counter rule is reported through it.
_V2_EXECUTION_PHASES = {"implementation", "review", "done"}


def _validate_v2_artifacts(work_dir, ticket, data, filenames, phase, bad, warn):
    """Structural artifact contracts for v2 Tickets; v1 semantics unchanged."""
    evidence_block = data.get("evidence") or {}
    gate = evidence_block.get("gate")
    round_no = evidence_block.get("round")

    ev_path = os.path.join(work_dir, filenames.get("evidence", "evidence.md"))
    audit_path = os.path.join(
        work_dir, filenames.get("evidence_audit", "evidence-audit.md"))

    # A sufficient verdict binds it to the audited artifact bytes; if either
    # changed the binding is stale -- the same blocker decisionward advances hit.
    # An insufficient verdict is meant to be superseded by the follow-up round,
    # so its (necessarily aging) binding is not reported here.
    if gate == "sufficient":
        recorded = (
            ("evidence.md", ev_path, evidence_block.get("report_sha256")),
            ("evidence-audit.md", audit_path, evidence_block.get("audit_sha256")),
        )
        for label, path, expected in recorded:
            if expected and os.path.exists(path):
                if contracts.sha256_file(path) != expected:
                    bad("%s changed since the evidence gate was recorded (stale "
                        "binding: re-audit and set-gate again)" % label)

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

def _validate_v2_review(root, work_dir, ticket, data, filenames, bad):
    """v2 Review binding agreement with command-time completion guards.

    Read-only and crash-safe: it never calls Git in a way that could raise, and
    missing/malformed fields are reported as ERRORs rather than tracebacks.
    - phase `done` with a verdict other than `pass` is an ERROR;
    - a recorded verdict in `review`/`done` must carry its binding fields
      (reported by the shared check like every other binding disagreement);
    - a recorded `pass` OR `changes_requested` whose Review artifact, registered
      Plan, literal immutable reviewed commit, or reviewed code no longer
      matches is an ERROR (the same blocker `advance` reports, via the shared
      `review.binding_problems` check).
    The intermediate states stay valid here: a `pending` verdict has no recorded
    binding, and a coherent `changes_requested` append (registered rework Plan,
    unchanged completed contracts) permits only that Plan drift.
    """
    phase = data.get("phase")
    block = data.get("review")
    if block is None:
        block = {}
    elif not isinstance(block, dict):
        return  # a malformed review block is already reported by workflow_v2
    verdict = block.get("verdict")

    if phase == "done" and verdict != "pass":
        bad("phase=done but review.verdict is %r (a current `pass` is required "
            "to complete)" % (verdict,))
    if verdict in ("pass", "changes_requested") \
            and phase in ("review", "done"):
        for problem in review.binding_problems(
                root, ticket, data,
                allow_rework=(verdict == "changes_requested")):
            bad(problem)


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


def _validate_escalation(data, bad):
    """v2 escalation/Status/route divergence (spec decision 5). Read-only.

    An unresolved escalation must be internally consistent: Status locked to
    `escalation_required`, the route pointing at the phase's senior resolver,
    and the recorded continuation well-formed. Missing fields never crash; a
    field is only checked when `required` is true or the field is present.
    """
    esc = data.get("escalation") or {}
    if not isinstance(esc, dict):
        bad("escalation must be a map")
        return
    required = esc.get("required") is True
    status = data.get("status")
    phase = data.get("phase")

    if required and status != "escalation_required":
        bad("escalation.required is true but status is %r (must be "
            "escalation_required)" % status)
    if status == "escalation_required" and not required:
        bad("status is escalation_required but escalation.required is not true "
            "(record the escalation or restore a valid status)")

    if required:
        reconstructing = (data.get("upgrade") or {}).get("requires_reconstruction")
        if reconstructing:
            expected = workflow_v2.RECONSTRUCTION_ROLE
        else:
            expected = workflow_v2.ESCALATION_RESOLVERS.get(phase)
        if expected is None:
            bad("escalation.required is true in phase %r, which has no senior "
                "resolver" % phase)
        else:
            role = (data.get("next_action") or {}).get("role")
            if role != expected:
                bad("escalation route corruption: escalation.required is true "
                    "but next_action.role is %r (phase %r requires the %s "
                    "resolver)" % (role, phase, expected))

    if required or "previous_status" in esc:
        previous = esc.get("previous_status")
        if previous is not None and previous not in STATUSES:
            bad("escalation.previous_status %r is not a valid status" % previous)
    if required or "interrupted_phase" in esc:
        interrupted = esc.get("interrupted_phase")
        if interrupted is not None and interrupted not in PHASES:
            bad("escalation.interrupted_phase %r is not a valid phase" % interrupted)
    if required or "interrupted_action" in esc:
        action = esc.get("interrupted_action")
        if action is not None and (not isinstance(action, dict)
                                   or set(action.keys()) != {"role", "action", "task"}):
            bad("escalation.interrupted_action must be a map with role/action/task")
    if required or "resolution" in esc:
        resolution = esc.get("resolution")
        if resolution is not None and not isinstance(resolution, str):
            bad("escalation.resolution must be a string or null")


def _git_dirty(root):
    try:
        # `--no-optional-locks` keeps this strictly read-only: a plain
        # `git status` opportunistically refreshes the stat cache and rewrites
        # `.git/index`, which would break `resume`'s read-only guarantee.
        out = subprocess.run(
            ["git", "--no-optional-locks", "-C", root, "status", "--porcelain"],
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

    # --- v2 escalation/Status/route divergence -------------------------------
    if ver == 2:
        _validate_escalation(data, bad)
        # A converted v1 Ticket is not valid until a senior reconstructs the
        # retained phase and clears the flag; the mutation-time clear check
        # excludes exactly this one blocker.
        if (data.get("upgrade") or {}).get("requires_reconstruction"):
            bad("workflow reconstruction is required for this converted v1 "
                "Ticket: a senior resolver must reconstruct the retained phase "
                "and clear it with `escalate --clear --resolution`")

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
    # The shared counter rule (non-negative integers, completed == [1..current],
    # current <= total, registered total == task-hash count) lives in
    # workflow_v2 so `validate` and `mutate` cannot drift. On a ready v2
    # execution phase it is reported through `readiness_problems` below.
    execution_phase = ver == 2 and phase in _V2_EXECUTION_PHASES
    if "implementation" in data and not execution_phase:
        for msg in workflow_v2.counter_problems(data.get("implementation") or {}):
            bad(msg)

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
        "review": artifacts.get("review", "review.md"),
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
        _validate_v2_review(root, work_dir, ticket, data, filenames, bad)

    # --- v2 execution readiness ------------------------------------------------
    # In an execution phase a v2 Ticket must be genuinely ready: a current
    # registered Plan, coherent counters, an active Status, and (adopted repos)
    # a confirmed adoption checkpoint. v1 Tickets skip this entirely.
    if execution_phase:
        for msg in workflow_v2.readiness_problems(root, ticket, data):
            bad(msg)

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


def reconstruction_problems(root, ticket, data):
    """Problems that block clearing a v1->v2 reconstruction; [] means clearable.

    Read-only. The reconstruction flag's own blocker and the unresolved
    escalation are provisionally cleared here, so this judges only whether the
    *retained phase's current contracts* are genuinely satisfied:

    - the phase's required artifacts are present on disk;
    - a decisionward phase has a current sufficient gate, freshly bound to the
      audited Evidence and its audit;
    - the v2 structured artifact contracts hold (see `_validate_v2_artifacts`);
    - an execution phase has a current registered Plan, coherent counters and a
      confirmed adoption checkpoint.

    The active-Status execution requirement is deliberately excluded: a
    reconstructed paused/blocked Ticket is not silently made executable. Review
    is not checked here — a pending Review is acceptable, and the current
    `pass`/`done` rules apply only once a verdict is recorded or `done` is
    entered (which a `done` v1 Ticket never is).
    """
    work_dir = os.path.join(root, ".ai", "work", ticket)
    phase = data.get("phase")
    problems = []
    if phase not in PHASES:
        return ["retained phase %r is not a valid phase" % phase]

    evidence = data.get("evidence") or {}
    gate = evidence.get("gate")
    artifacts = data.get("artifacts") or {}
    filenames = {
        "evidence": artifacts.get("evidence", "evidence.md"),
        "evidence_audit": artifacts.get("evidence_audit", "evidence-audit.md"),
        "decision": artifacts.get("decision", "decision.md"),
        "handoff": artifacts.get("handoff", "handoff.md"),
        "review": artifacts.get("review", "review.md"),
    }

    def missing(key):
        return not os.path.exists(os.path.join(work_dir, filenames[key]))

    if missing("handoff"):
        problems.append("missing artifact %s for phase=%s"
                        % (filenames["handoff"], phase))
    if phase in {"evidence_audit", "followup_evidence", "technical_decision",
                 "planning", "implementation", "review", "done"} \
            and missing("evidence"):
        problems.append("missing artifact %s for phase=%s"
                        % (filenames["evidence"], phase))
    if phase in {"technical_decision", "planning", "implementation", "review",
                 "done"} and missing("evidence_audit"):
        problems.append("missing artifact %s for phase=%s"
                        % (filenames["evidence_audit"], phase))
    if phase in {"planning", "implementation", "review", "done"} \
            and missing("decision"):
        problems.append("missing artifact %s for phase=%s"
                        % (filenames["decision"], phase))

    if phase in DECISIONWARDS and gate != "sufficient":
        problems.append("phase=%s requires a current sufficient evidence gate "
                        "(evidence.gate=%r)" % (phase, gate))

    _validate_v2_artifacts(work_dir, ticket, data, filenames, phase,
                           problems.append, lambda _msg: None)
    # The registered-Plan / counter / adoption contracts apply only to the
    # execution phases (as in `validate_ticket`); an earlier retained phase has
    # no Plan to register yet. The active-Status requirement is excluded so a
    # reconstructed paused/blocked Ticket stays reconstructed, not executable.
    if phase in _V2_EXECUTION_PHASES:
        problems.extend(workflow_v2.readiness_problems(
            root, ticket, data, require_active=False))
        if phase == "review":
            impl = data.get("implementation") or {}
            if workflow_v2.executable_task(impl) is not None:
                problems.append(
                    "phase=review requires every registered task complete "
                    "(current_task=%r of total_tasks=%r)"
                    % (impl.get("current_task"), impl.get("total_tasks")))
    elif "implementation" in data:
        problems.extend(
            workflow_v2.counter_problems(data.get("implementation") or {}))
    return problems


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