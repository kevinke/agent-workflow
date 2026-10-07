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
stays v1. See MIGRATION.md and STATE_SCHEMA.md for the reconstruction rules.

`upgrade` is idempotent: when the installed protocol is already current it is a
no-op. Returns `(updated_files, [])` — the pair shape is retained for
compatibility, and the second element is always empty.
"""

import os
import shutil

import contracts
import state
import validate
import workflow_v2

__all__ = ["upgrade", "upgrade_ticket", "UpgradeError",
           "kit_workflow_version", "installed_workflow_version"]

_WORK_DIR_REL = os.path.join(".ai", "work")

# Recorded reason/route for the reconstruction escalation created on conversion.
# Kept free of the restricted-YAML-reserved characters so it round-trips plainly.
_RECONSTRUCTION_REASON = ("workflow reconstruction required for this converted "
                          "v1 Ticket")


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


def _convert_v1_to_v2(data):
    """The one explicit v1 -> v2 conversion (mutates and returns `data`).

    Preserves the phase, source references, counters, ordered completed history,
    unknown maps, and the interrupted `next_action`. Records the reconstruction
    facts (`upgrade.from_version`/`previous_gate`/`requires_reconstruction`),
    resets the gate to insufficient and the review to pending, and creates an
    unresolved machine escalation routed to `workflow-bootstrap`. No audit, Plan
    or review pass is fabricated.
    """
    phase = data.get("phase")
    previous_action = data.get("next_action") or {}
    previous_gate = (data.get("evidence") or {}).get("gate")
    previous_status = data.get("status")

    data["workflow_version"] = 2
    data["upgrade"] = {
        "from_version": 1,
        "requires_reconstruction": True,
        "previous_gate": previous_gate,
    }

    evidence = dict(data.get("evidence") or {})
    evidence["gate"] = "insufficient"
    data["evidence"] = evidence

    # A scaffold default only: never a past passing verdict.
    review = dict(data.get("review") or {})
    review["verdict"] = "pending"
    data["review"] = review

    # The v2 Review filename default; no Review artifact is written here.
    artifacts = dict(data.get("artifacts") or {})
    if "review" not in artifacts:
        artifacts["review"] = "review.md"
    data["artifacts"] = artifacts

    escalation = dict(data.get("escalation") or {})
    escalation["required"] = True
    escalation["scope"] = "machine"
    escalation["reason"] = _RECONSTRUCTION_REASON
    escalation["previous_status"] = previous_status
    escalation["interrupted_action"] = {
        "role": previous_action.get("role"),
        "action": previous_action.get("action"),
        "task": previous_action.get("task"),
    }
    escalation["interrupted_phase"] = phase
    escalation["resolution"] = None
    data["escalation"] = escalation

    data["status"] = "escalation_required"
    data["next_action"] = {
        "role": workflow_v2.RECONSTRUCTION_ROLE,
        "action": workflow_v2.RECONSTRUCTION_ACTION,
        "task": None,
    }
    return data


def upgrade_ticket(root, ticket_id):
    """Explicitly convert one interpretable active v1 Ticket to workflow_version 2.

    Returns a confirmation line. An already-v2 Ticket is a byte-preserving
    no-op. A historical `done` v1 Ticket, an uninterpretable version
    (bool/zero/future), a state too malformed to reconstruct, or a missing
    ticket is rejected unchanged (raising UpgradeError).
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

    phase = data.get("phase")
    if phase == "done":
        raise UpgradeError(
            "cannot upgrade %s: a historical done Ticket stays workflow_version 1"
            % ticket_id)
    if phase not in validate.PHASES:
        raise UpgradeError(
            "cannot upgrade %s: state is too malformed to reconstruct (phase=%r)"
            % (ticket_id, phase))

    _convert_v1_to_v2(data)
    state.save_file(path, data)
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