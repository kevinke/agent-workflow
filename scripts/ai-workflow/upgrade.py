"""`ai-workflow upgrade` — explicit protocol upgrade (spec §9, TICKET-008/007).

Reads the kit's bundled `workflow_version` (single source of truth: the shipped
`templates/state.yaml`) and the version installed in the target repo. When the
installed protocol is older, `upgrade` overwrites the target's `.ai/workflow/`
docs and templates with the bundled ones — the one place an explicit upgrade
overwrites, where `init` never does. It never rewrites a Ticket's State: Ticket
versions are handled only by the explicit `upgrade-ticket` command.

`upgrade-ticket` converts one interpretable *active* v1 Ticket to
`workflow_version: 2` once, keeping its phase and history, recording
`upgrade.previous_gate` and `upgrade.requires_reconstruction`, resetting the gate
to insufficient and the review to pending, and creating an unresolved machine
escalation whose resolver is `workflow-bootstrap` (preserving the interrupted
action). It fabricates no past audit, Plan, or review pass; a `done` v1 Ticket
stays v1. The owned shapes are preflighted (`conversion_problems`) before any
write, and the owned keys are merged into the existing nested maps, so unknown
extension fields survive conversion untouched. See MIGRATION.md and
STATE_SCHEMA.md for the reconstruction rules.

`upgrade` is idempotent: when the installed protocol is already current it is a
no-op. Returns `(updated_files, [])` — the pair shape is retained for
compatibility, and the second element is always empty.
"""

import copy
import os
import shutil

import contracts
import state
import validate
import workflow_v2

__all__ = ["upgrade", "upgrade_ticket", "conversion_problems", "UpgradeError",
           "kit_workflow_version", "installed_workflow_version"]

_WORK_DIR_REL = os.path.join(".ai", "work")

# The only v1 Statuses the explicit conversion accepts. `active`, `paused` and
# `blocked` are live, reconstructible work; a ticket that has already escalated
# must have that block resolved first, and an `abandoned` ticket has no routine
# work to reconstruct.
_CONVERTIBLE_STATUSES = frozenset({"active", "paused", "blocked"})

# Recorded reason/route for the reconstruction escalation created on conversion.
# Kept free of the restricted-YAML-reserved characters so it round-trips plainly.
_RECONSTRUCTION_REASON = ("workflow reconstruction required for this converted "
                          "v1 Ticket")

# The nested maps the explicit conversion reads or writes. Each is optional:
# when present it must be a map (a null counts as absent), or the State is
# malformed input rather than convertible work.
_OWNED_MAPS = ("artifacts", "evidence", "escalation", "implementation",
               "next_action", "review", "source_artifacts", "upgrade")

# The known source-reference children of `source_artifacts` (STATE_SCHEMA.md).
_SOURCE_REFERENCES = ("spec", "ticket", "plan")


class UpgradeError(Exception):
    """Raised when there is no installed protocol, or a Ticket cannot be
    explicitly upgraded (unknown/malformed/done/historical)."""


def _kit_root():
    # this file: scripts/ai-workflow/upgrade.py
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _kit_workflow_dir():
    return os.path.join(_kit_root(), ".ai", "workflow")


def _installed_workflow_dir(root):
    return os.path.join(root, ".ai", "workflow")


def _ticket_state_path(root, ticket_id):
    return os.path.join(root, _WORK_DIR_REL, ticket_id, "state.yaml")


def _read_workflow_version(directory):
    tmpl = os.path.join(directory, "templates", "state.yaml")
    if not os.path.isfile(tmpl):
        return None
    try:
        data = state.load_file(tmpl)
    except state.StateError:
        return None
    version = data.get("workflow_version")
    return version if isinstance(version, int) else None


def kit_workflow_version():
    """The workflow_version bundled with this kit (its own template)."""
    return _read_workflow_version(_kit_workflow_dir())


def installed_workflow_version(root):
    """The workflow_version installed in the target repo, or None."""
    return _read_workflow_version(_installed_workflow_dir(root))


def _overwrite_tree(src, dst, updated):
    """Copy src into dst, overwriting everything (the explicit-upgrade case)."""
    for dirpath, _dirs, files in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        dest_dir = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(dest_dir, exist_ok=True)
        for fname in files:
            src_path = os.path.join(dirpath, fname)
            dest_path = os.path.join(dest_dir, fname)
            shutil.copy2(src_path, dest_path)
            updated.append(dest_path)


def conversion_problems(data):
    """Preflight one candidate State for the explicit v1 -> v2 conversion.

    Returns every owned-shape problem as an actionable string; [] means the
    State may be converted. Read-only, and it must run before any nested
    `.get`/dict conversion touches the State. Malformed input (a scalar or
    list where an owned map belongs, a malformed nested source reference,
    boolean or negative counters, a non-ordered completed history) is
    reported as `malformed input`; an ineligible Ticket (uninterpretable
    version, historical done phase, an already-escalated or abandoned
    Status) as `unsupported conversion`. Unknown fields — including unknown
    children of the owned maps — are never checked and never reported, so
    validation never coerces or rejects extension data.
    """
    problems = []
    try:
        ver = workflow_v2.version(data)
    except contracts.ContractError as exc:
        problems.append("unsupported conversion: %s" % exc)
    else:
        if ver == 2:
            problems.append("unsupported conversion: the Ticket is already "
                            "workflow_version 2")

    phase = data.get("phase")
    if phase == "done":
        problems.append("unsupported conversion: a historical done Ticket "
                        "stays workflow_version 1")
    elif not isinstance(phase, str) or phase not in validate.PHASES:
        problems.append("malformed input: phase %r is not a workflow phase; "
                        "fix the State before converting" % (phase,))

    status = data.get("status")
    if not isinstance(status, str) or status not in _CONVERTIBLE_STATUSES:
        problems.append(
            "unsupported conversion: only an active, paused, or blocked v1 "
            "Ticket may be converted (status=%r); resolve an existing "
            "escalation with `escalate --clear --resolution` first, or leave "
            "an abandoned Ticket as workflow_version 1" % (status,))

    for key in _OWNED_MAPS:
        value = data.get(key)
        if value is not None and not isinstance(value, dict):
            problems.append("malformed input: %s must be a map (got %s); fix "
                            "the State before converting"
                            % (key, type(value).__name__))

    sources = data.get("source_artifacts")
    if isinstance(sources, dict):
        for ref in _SOURCE_REFERENCES:
            value = sources.get(ref)
            if value is not None and not isinstance(value, dict):
                problems.append(
                    "malformed input: source_artifacts.%s must be a map (got "
                    "%s); fix the State before converting"
                    % (ref, type(value).__name__))

    implementation = data.get("implementation")
    if isinstance(implementation, dict):
        problems.extend("malformed input: %s" % problem for problem
                        in workflow_v2.counter_problems(implementation))

    return problems


def _convert_v1_to_v2(data):
    """The one explicit v1 -> v2 conversion (returns a converted deep copy).

    Works on a deep copy of the parsed State and merges the owned keys into
    the existing nested maps, so every unknown child — including unknown
    children of `upgrade`, `evidence`, `review`, `escalation`,
    `source_artifacts.plan`, `implementation` and nested custom maps — is
    preserved rather than dropped or coerced. Preserves the phase, source
    references, counters and ordered completed history, records the
    reconstruction facts (`upgrade.from_version`/`previous_gate`/
    `requires_reconstruction`), resets the gate to insufficient and the
    review to pending without carrying over an old verdict, and creates an
    unresolved machine escalation routed to `workflow-bootstrap` whose
    `interrupted_action` snapshots the whole old `next_action` — unknown
    children survive in both the snapshot and the reconstruction route. No
    audit, Plan or review pass is fabricated. Callers preflight the owned
    shapes with `conversion_problems` first; this function never validates.
    """
    converted = copy.deepcopy(data)

    phase = converted.get("phase")
    previous_action = converted.get("next_action")
    if not isinstance(previous_action, dict):
        previous_action = {}
    previous_gate = (converted.get("evidence") or {}).get("gate")
    previous_status = converted.get("status")

    converted["workflow_version"] = 2

    upgrade_block = converted.get("upgrade")
    if not isinstance(upgrade_block, dict):
        upgrade_block = {}
    upgrade_block["from_version"] = 1
    upgrade_block["requires_reconstruction"] = True
    upgrade_block["previous_gate"] = previous_gate
    converted["upgrade"] = upgrade_block

    evidence = converted.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
    evidence["gate"] = "insufficient"
    converted["evidence"] = evidence

    # A scaffold default only: never a past passing verdict.
    review = converted.get("review")
    if not isinstance(review, dict):
        review = {}
    review["verdict"] = "pending"
    converted["review"] = review

    # The v2 Review filename default; no Review artifact is written here.
    artifacts = converted.get("artifacts")
    if not isinstance(artifacts, dict):
        artifacts = {}
    if "review" not in artifacts:
        artifacts["review"] = "review.md"
    converted["artifacts"] = artifacts

    escalation = converted.get("escalation")
    if not isinstance(escalation, dict):
        escalation = {}
    escalation["required"] = True
    escalation["scope"] = "machine"
    escalation["reason"] = _RECONSTRUCTION_REASON
    escalation["previous_status"] = previous_status
    # The interrupted action is snapshotted whole: unknown children of the old
    # `next_action` and of any pre-existing `interrupted_action` survive next
    # to the three owned keys, which always stay present.
    previous_interrupted = escalation.get("interrupted_action")
    interrupted = (copy.deepcopy(previous_interrupted)
                   if isinstance(previous_interrupted, dict) else {})
    interrupted.update(copy.deepcopy(previous_action))
    interrupted["role"] = previous_action.get("role")
    interrupted["action"] = previous_action.get("action")
    interrupted["task"] = previous_action.get("task")
    escalation["interrupted_action"] = interrupted
    escalation["interrupted_phase"] = phase
    escalation["resolution"] = None
    converted["escalation"] = escalation

    converted["status"] = "escalation_required"
    # The reconstruction route keeps the old action's unknown children and
    # overwrites only the three owned keys.
    next_action = copy.deepcopy(previous_action)
    next_action["role"] = workflow_v2.RECONSTRUCTION_ROLE
    next_action["action"] = workflow_v2.RECONSTRUCTION_ACTION
    next_action["task"] = None
    converted["next_action"] = next_action
    return converted


def upgrade_ticket(root, ticket_id):
    """Explicitly convert one interpretable active v1 Ticket to workflow_version 2.

    Returns a confirmation line. An already-v2 Ticket is a byte-preserving
    no-op. The owned shapes are preflighted with `conversion_problems` before
    anything is written, so a historical `done` v1 Ticket, an uninterpretable
    version (bool/zero/future), a Status that is not active/paused/blocked (an
    already escalated or abandoned Ticket), a malformed owned map or counter,
    a state too malformed to reconstruct, or a missing ticket is rejected
    with an actionable UpgradeError and unchanged State bytes. The conversion
    itself merges its owned keys into the existing nested maps, so unknown
    extension fields survive.
    """
    path = _ticket_state_path(root, ticket_id)
    if not os.path.isfile(path):
        raise UpgradeError(
            "no ticket %s under .ai/work/ (run `start` or `adopt` first)" % ticket_id)
    try:
        data = state.load_file(path)
    except state.StateError as exc:
        raise UpgradeError("cannot upgrade %s: %s" % (ticket_id, exc))
    try:
        ver = workflow_v2.version(data)
    except contracts.ContractError as exc:
        raise UpgradeError("cannot upgrade %s: %s" % (ticket_id, exc))
    if ver == 2:
        return "%s: already workflow_version 2 (no change)" % ticket_id

    problems = conversion_problems(data)
    if problems:
        raise UpgradeError("cannot upgrade %s: %s"
                           % (ticket_id, "; ".join(problems)))

    state.save_file(path, _convert_v1_to_v2(data))
    return ("%s: converted to workflow_version 2 "
            "(senior reconstruction required)" % ticket_id)


def upgrade(root):
    """Upgrade the installed protocol to the kit's bundled version.

    Returns (updated_files, []); ([], []) when already current. Ticket State is
    never written here. Raises UpgradeError when no protocol is installed in the
    target.
    """
    kit_version = kit_workflow_version()
    installed_version = installed_workflow_version(root)
    if kit_version is None or installed_version is None:
        raise UpgradeError(
            "no installed protocol in %s (run `ai-workflow init` first), "
            "or the kit template is unreadable." % root
        )
    if installed_version >= kit_version:
        return [], []
    updated = []
    _overwrite_tree(_kit_workflow_dir(), _installed_workflow_dir(root), updated)
    return updated, []