"""Shared retained-phase contract checks (HARDEN-003).

One home for the phase/artifact maps and the contracts a v2 Ticket's
*retained* phase must currently satisfy, so `validate` and the recovery-clear
path judge the same State with one rule set instead of drifting copies. Pure
and read-only: this module never writes and never imports `validate` or
`mutate` (dependency order: contracts -> workflow_v2 -> review ->
phase_checks -> validate -> mutate).

For a recovery clear the caller supplies the *proposed* cleared State (the
recovery/escalation flags already provisionally cleared and the previous
Status restored), so a rejected clear never touches the real State bytes.
"""

import os

import contracts
import review
import workflow_v2

__all__ = ["PHASES", "DECISIONWARD_PHASES", "EXECUTION_PHASES", "PENDING_PHASES",
           "EVIDENCE_STRUCTURAL_PHASES", "AUDIT_STRUCTURAL_PHASES",
           "HANDOFF_BOUNDARY_PHASES",
           "DEFAULT_ARTIFACT_NAMES", "artifact_names", "required_artifacts",
           "artifact_contract_problems", "handoff_readiness_problems",
           "recorded_review_problems", "continuation_problems"]

PHASES = {
    "requirement", "evidence_collection", "evidence_audit", "followup_evidence",
    "technical_decision", "planning", "implementation", "review", "done",
}

# Phases that require a sufficient evidence gate before they may be entered or
# restored into. Public: shared with the `mutate` module (validate.DECISIONWARDS)
# so write-time checks and validation use one rule.
DECISIONWARD_PHASES = {"technical_decision", "planning", "implementation",
                       "review", "done"}

# Phases whose Evidence report may still be a pending scaffold: shape problems
# there are warnings (never continuation blockers), per the common phase rules.
PENDING_PHASES = {"requirement", "evidence_collection"}

# Phases where a present Evidence report must be a structurally valid report.
EVIDENCE_STRUCTURAL_PHASES = {
    "evidence_audit", "followup_evidence",
    "technical_decision", "planning", "implementation", "review", "done",
}

# Phases where a present Audit must be structurally valid.
AUDIT_STRUCTURAL_PHASES = {
    "technical_decision", "planning", "implementation", "review", "done",
}

# Phases where the v2 execution-readiness gate (registered Plan, coherent
# counters, active Status, adoption checkpoint) applies.
EXECUTION_PHASES = {"implementation", "review", "done"}

# Phases whose retained Handoff must be concrete (HARDEN-007): the transfer
# boundaries `review` and `done`. An implementation retained phase gates only
# on the recovery-clear boundary, where the caller passes `require_handoff`.
HANDOFF_BOUNDARY_PHASES = {"review", "done"}

# The default artifact filenames; an `artifacts.<key>` entry in the State
# overrides the default.
DEFAULT_ARTIFACT_NAMES = {
    "evidence": "evidence.md",
    "evidence_audit": "evidence-audit.md",
    "decision": "decision.md",
    "handoff": "handoff.md",
    "review": "review.md",
}

# Required artifact keys per phase, in report order (the retained-phase file
# requirements; no new phases). review.md is never required: a pending Review
# has no artifact yet.
_REQUIRED_ARTIFACTS = {
    "requirement": ("handoff",),
    "evidence_collection": ("handoff",),
    "evidence_audit": ("handoff", "evidence"),
    "followup_evidence": ("handoff", "evidence"),
    "technical_decision": ("handoff", "evidence", "evidence_audit"),
    "planning": ("handoff", "evidence", "evidence_audit", "decision"),
    "implementation": ("handoff", "evidence", "evidence_audit", "decision"),
    "review": ("handoff", "evidence", "evidence_audit", "decision"),
    "done": ("handoff", "evidence", "evidence_audit", "decision"),
}


def artifact_names(data):
    """The artifact filenames: defaults plus the State's configured overrides."""
    artifacts = (data or {}).get("artifacts") or {}
    names = dict(DEFAULT_ARTIFACT_NAMES)
    for key, default in DEFAULT_ARTIFACT_NAMES.items():
        names[key] = artifacts.get(key, default)
    return names


def required_artifacts(phase):
    """The artifact keys `phase` requires, in report order; () when none."""
    return _REQUIRED_ARTIFACTS.get(phase, ())


def artifact_contract_problems(work_dir, ticket_id, data, names, phase):
    """Structural v2 artifact contracts; returns (problems, scaffold_notices).

    Extracted from the former `validate._validate_v2_artifacts` so validation
    and the recovery checks share it. A sufficient gate whose bound Evidence
    or audit bytes have since changed is a problem (the stale-binding
    blocker), and the structured grammars hold from their phases onward. In
    the early `requirement`/`evidence_collection` phases the Evidence may
    still be a pending scaffold: its shape problems come back as
    `scaffold_notices` (validate reports them as WARN), so a scaffold is
    never a structural failure.
    """
    problems = []
    notices = []
    evidence_block = data.get("evidence") or {}
    gate = evidence_block.get("gate")
    round_no = evidence_block.get("round")

    ev_path = os.path.join(work_dir, names.get("evidence", "evidence.md"))
    audit_path = os.path.join(
        work_dir, names.get("evidence_audit", "evidence-audit.md"))

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
                    problems.append("%s changed since the evidence gate was "
                                    "recorded (stale binding: re-audit and "
                                    "set-gate again)" % label)

    if phase in PENDING_PHASES:
        # A scaffold is not a completed report: surface shape problems as
        # notices so placeholders here are never structural failures.
        if os.path.exists(ev_path):
            try:
                report = contracts.read_artifact(ev_path, "evidence")
                shape = contracts.validate_evidence(report, ticket_id)
            except contracts.ContractError as exc:
                notices.append("evidence.md is not a structured report yet (%s)"
                               % exc)
            else:
                for msg in shape:
                    notices.append("evidence.md pending scaffold: %s" % msg)
        return problems, notices

    if phase in EVIDENCE_STRUCTURAL_PHASES and os.path.exists(ev_path):
        try:
            report = contracts.read_artifact(ev_path, "evidence")
            shape = contracts.validate_evidence(report, ticket_id)
        except contracts.ContractError as exc:
            problems.append("evidence.md violates the artifact grammar: %s" % exc)
        else:
            for msg in shape:
                problems.append("evidence.md: %s" % msg)

    if phase in AUDIT_STRUCTURAL_PHASES and os.path.exists(audit_path):
        try:
            report = contracts.read_artifact(audit_path, "evidence-audit")
            shape = contracts.validate_audit(report, ticket_id, gate, round_no)
        except contracts.ContractError as exc:
            problems.append("evidence-audit.md violates the artifact grammar: %s"
                            % exc)
        else:
            for msg in shape:
                problems.append("evidence-audit.md: %s" % msg)

    return problems, notices


def handoff_readiness_problems(root, ticket_id, data):
    """Readiness syntax problems of the Ticket's current handoff; [] = ready.

    The shared HARDEN-007 gate body: a read-only `contracts.validate_handoff`
    pass over the configured handoff artifact. A missing file is NOT reported
    here — the per-phase required-artifact checks already own that problem,
    so this check never masks (or duplicates) it.
    """
    names = artifact_names(data)
    path = os.path.join(root, ".ai", "work", ticket_id,
                        names.get("handoff", "handoff.md"))
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return ["handoff.md exists but could not be read"]
    return contracts.validate_handoff(text)


def recorded_review_problems(root, ticket_id, data):
    """Binding problems of a recorded verdict; [] for pending or absent.

    The shared both-verdict check (01): a recorded `pass` or
    `changes_requested` in `review`/`done` must still agree with its immutable
    bindings — the Review artifact bytes, the registered Plan, the literal
    immutable reviewed commit, and the reviewed code. A recorded
    `changes_requested` inherits the one narrow appended-rework exception (a
    strictly-appending rework Plan with an unchanged completed prefix); a
    recorded `pass` never does. `pending` has no recorded binding.
    """
    block = data.get("review") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return []
    verdict = block.get("verdict")
    if verdict not in ("pass", "changes_requested"):
        return []
    if data.get("phase") not in ("review", "done"):
        return []
    return review.binding_problems(
        root, ticket_id, data, allow_rework=(verdict == "changes_requested"))


def _review_completion_problems(root, ticket_id, data):
    """`review` continuation needs every registered task complete.

    The one exception is the valid recorded rework intermediate state: a
    recorded `changes_requested` whose strictly-appending rework Plan is
    registered with the completed task contracts unchanged (01's narrow
    rework exception) may continue with the appended tasks still open — that
    is exactly the repair path a recovery clear must restore.
    """
    impl = data.get("implementation") or {}
    if workflow_v2.executable_task(impl) is None:
        return []
    block = data.get("review") or {}
    verdict = block.get("verdict") if isinstance(block, dict) else None
    if verdict == "changes_requested" \
            and review._rework_append_ok(root, ticket_id, data):
        return []
    return ["phase=review requires every registered task complete "
            "(current_task=%r of total_tasks=%r)"
            % (impl.get("current_task"), impl.get("total_tasks"))]


def continuation_problems(root, ticket_id, data, *, require_active=True,
                          require_handoff=False):
    """Problems blocking a continuation of the retained phase; [] means none.

    Read-only. `data` is the State to judge — for a recovery clear the
    *proposed* cleared State prepared by the caller, so a rejected clear
    leaves the real State bytes untouched. The retained phase's current
    contracts:

    - the phase's required artifacts are present on disk;
    - a decisionward phase has a current sufficient gate, freshly bound to
      the audited Evidence and its audit;
    - the v2 structured artifact contracts hold (early scaffolds are
      warnings here, never blockers);
    - an execution phase has a current registered Plan, coherent counters and
      a confirmed adoption checkpoint (`require_active` keeps the
      active-Status execution gate; a paused/blocked recovery clear turns it
      off so the restored Ticket stays reconstructed, not silently
      executable);
    - the retained Handoff is concrete at the transfer boundaries: always in
      `review`/`done`, and in an implementation recovery clear via
      `require_handoff` (ordinary implementation drafting never gates —
      `contracts.validate_handoff` stays syntax-only and the early drafts
      keep their WARN notices elsewhere);
    - a recorded verdict still agrees with its immutable bindings; and
    - `review` continues only with every registered task complete — except
      the valid recorded rework intermediate state.
    """
    phase = data.get("phase")
    if phase not in PHASES:
        return ["retained phase %r is not a valid phase" % phase]

    problems = []
    work_dir = os.path.join(root, ".ai", "work", ticket_id)
    names = artifact_names(data)

    for key in required_artifacts(phase):
        if not os.path.exists(os.path.join(work_dir, names[key])):
            problems.append("missing artifact %s for phase=%s"
                            % (names[key], phase))

    gate = (data.get("evidence") or {}).get("gate")
    if phase in DECISIONWARD_PHASES and gate != "sufficient":
        problems.append("phase=%s requires a current sufficient evidence gate "
                        "(evidence.gate=%r)" % (phase, gate))

    structural, _notices = artifact_contract_problems(
        work_dir, ticket_id, data, names, phase)
    problems.extend(structural)

    # The transfer-boundary handoff gate: always at `review`/`done`, and for
    # an implementation retained phase only where the caller marks the
    # boundary (the recovery clear) — an ordinary implementation continuation
    # keeps its draft-with-notices behavior.
    if phase in HANDOFF_BOUNDARY_PHASES or (require_handoff
                                            and phase == "implementation"):
        for problem in handoff_readiness_problems(root, ticket_id, data):
            problems.append("handoff.md is not ready for the transfer "
                            "boundary: %s" % problem)

    # The registered-Plan / counter / adoption contracts apply only to the
    # execution phases (as in `validate_ticket`); an earlier retained phase
    # has no Plan to register yet.
    if phase in EXECUTION_PHASES:
        problems.extend(workflow_v2.readiness_problems(
            root, ticket_id, data, require_active=require_active))
        if phase == "review":
            problems.extend(_review_completion_problems(root, ticket_id, data))
        problems.extend(recorded_review_problems(root, ticket_id, data))
    elif "implementation" in data:
        problems.extend(
            workflow_v2.counter_problems(data.get("implementation") or {}))
    return problems
