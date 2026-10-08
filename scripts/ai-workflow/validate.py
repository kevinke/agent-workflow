"""`ai-workflow validate` — validate the workflow itself (not the code).

Two severities (CONTEXT.md "Validate Severity"):

- ERROR  — illegal schema, gate-violating transition, missing required artifact,
           DONE-with-next_action, handoff missing, or restricted-YAML violation.
           Must be fixed before handoff; causes a non-zero exit.
- WARN   — proceed allowed, must be recorded in handoff (e.g. uncommitted work,
           missing handoff fields, missing protocol dir).

Read-only: never writes state.yaml.
"""

import copy
import os
import subprocess

import contracts
import parser
import phase_checks
import state
import workflow_v2
from status import list_tickets

__all__ = ["validate_ticket", "validate_repo", "reconstruction_problems",
           "PHASES", "STATUSES", "GATES", "SCOPES", "ROLES", "DECISIONWARDS"]


# The phase/artifact maps live in `phase_checks` (shared with the recovery
# checks); these names are retained for the mutator and other consumers.
PHASES = phase_checks.PHASES
DECISIONWARDS = phase_checks.DECISIONWARD_PHASES

STATUSES = {"active", "blocked", "escalation_required", "paused", "abandoned"}
GATES = {"sufficient", "insufficient"}
SCOPES = {"machine", "human"}
ROLES = {
    "scout", "evidence-auditor", "technical-decision", "executor-plan",
    "ticket-executor", "checkpoint-handoff", "workflow-bootstrap", "reviewer",
}


def _validate_v2_review(root, work_dir, ticket, data, filenames, bad):
    """v2 Review binding agreement with command-time completion guards.

    Read-only and crash-safe: it never calls Git in a way that could raise, and
    missing/malformed fields are reported as ERRORs rather than tracebacks.
    - phase `done` with a verdict other than `pass` is an ERROR;
    - a recorded verdict in `review`/`done` must carry its binding fields
      and still agree with what it was bound to (the shared both-verdict
      `phase_checks.recorded_review_problems` check, with the narrow
      appended-rework exception for a recorded `changes_requested`).
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
    for problem in phase_checks.recorded_review_problems(root, ticket, data):
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
        # A late-phase v2 start/adopt scaffold (HARDEN-003) carries the same
        # reconstruction-style carve-out: its recovery marker routes the
        # unresolved escalation to the workflow-bootstrap senior resolver, so
        # the coherent bootstrap route is not route corruption.
        bootstrapping = isinstance(data.get("recovery"), dict) \
            and data["recovery"].get("kind") == "bootstrap"
        if reconstructing or bootstrapping:
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
    execution_phase = ver == 2 and phase in phase_checks.EXECUTION_PHASES
    if "implementation" in data and not execution_phase:
        for msg in workflow_v2.counter_problems(data.get("implementation") or {}):
            bad(msg)

    # --- DONE must clear next_action ----------------------------------------
    if phase == "done" and has_next:
        bad("phase=done but next_action is still set")

    # --- missing artifacts per required phase --------------------------------
    filenames = phase_checks.artifact_names(data)
    for key in phase_checks.required_artifacts(phase):
        if not os.path.exists(os.path.join(work_dir, filenames[key])):
            bad("missing artifact %s for phase=%s" % (filenames[key], phase))

    # --- v2 structured artifact contracts --------------------------------------
    if ver == 2:
        # Early scaffolds keep their WARN behavior: pending-phase shape
        # problems come back as notices and never become ERRORs.
        problems, notices = phase_checks.artifact_contract_problems(
            work_dir, ticket, data, filenames, phase)
        for msg in problems:
            bad(msg)
        for msg in notices:
            warn(msg)
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

    Compatibility wrapper: it prepares the proposed cleared State — the
    unresolved escalation and the reconstruction flag provisionally cleared,
    the recorded previous Status restored (falling back to `active` when it
    is not a valid Status) — and delegates to the shared
    `phase_checks.continuation_problems`. Read-only: nothing is written and
    the caller's `data` is never mutated, so this judges only whether the
    *retained phase's current contracts* are genuinely satisfied. The
    active-Status execution requirement is excluded only for paused/blocked
    recovery, so a reconstructed paused/blocked Ticket is not silently made
    executable.
    """
    proposed = copy.deepcopy(data)
    esc = dict(proposed.get("escalation") or {})
    previous = esc.get("previous_status")
    if previous == "escalation_required" or previous not in STATUSES:
        previous = "active"
    esc["required"] = False
    proposed["escalation"] = esc
    proposed["status"] = previous
    upgrade_block = proposed.get("upgrade")
    if isinstance(upgrade_block, dict) \
            and upgrade_block.get("requires_reconstruction"):
        cleared_upgrade = dict(upgrade_block)
        cleared_upgrade["requires_reconstruction"] = False
        proposed["upgrade"] = cleared_upgrade
    require_active = previous not in ("paused", "blocked")
    return phase_checks.continuation_problems(
        root, ticket, proposed, require_active=require_active)


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