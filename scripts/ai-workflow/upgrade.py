"""`ai-workflow upgrade` — explicit protocol upgrade (spec §9, TICKET-008).

Reads the kit's bundled `workflow_version` (single source of truth: the shipped
`templates/state.yaml`) and the version installed in the target repo. When the
installed protocol is older, `upgrade` overwrites the target's `.ai/workflow/`
docs and templates with the bundled ones — the one place an explicit upgrade
overwrites, where `init` never does — and bumps `workflow_version` in every
ticket state.yaml that is older, preserving all other fields.

Idempotent: when the installed protocol is already current, it is a no-op.
Returns `(updated_files, bumped_tickets)`.
"""

import os
import shutil

import state

__all__ = ["upgrade", "UpgradeError", "kit_workflow_version",
           "installed_workflow_version"]


class UpgradeError(Exception):
    """Raised when there is no installed protocol to upgrade."""


def _kit_root():
    # this file: scripts/ai-workflow/upgrade.py
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _kit_workflow_dir():
    return os.path.join(_kit_root(), ".ai", "workflow")


def _installed_workflow_dir(root):
    return os.path.join(root, ".ai", "workflow")


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


def _bump_tickets(root, kit_version):
    """Bump workflow_version in tickets older than the kit's, preserving all
    other fields. Returns the list of bumped ticket ids."""
    bumped = []
    work_dir = os.path.join(root, ".ai", "work")
    if not os.path.isdir(work_dir):
        return bumped
    for name in sorted(os.listdir(work_dir)):
        state_path = os.path.join(work_dir, name, "state.yaml")
        if not os.path.isfile(state_path):
            continue
        try:
            data = state.load_file(state_path)
        except state.StateError:
            continue  # leave unparseable tickets alone; validate will flag them
        current = data.get("workflow_version")
        if not isinstance(current, int) or current >= kit_version:
            continue
        data["workflow_version"] = kit_version
        state.save_file(state_path, data)
        bumped.append(name)
    return bumped


def upgrade(root):
    """Upgrade the installed protocol to the kit's bundled version.

    Returns (updated_files, bumped_tickets); ([], []) when already current.
    Raises UpgradeError when no protocol is installed in the target.
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
    bumped = _bump_tickets(root, kit_version)
    return updated, bumped
