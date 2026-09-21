"""`ai-workflow start` — scaffold a new (greenfield) ticket (spec §9, TICKET-008).

The greenfield counterpart to `adopt` (which handles legacy repos): creates
`.ai/work/<ticket-id>/` from the bundled templates, writes a fresh `state.yaml`
at the `requirement` phase (or `--phase` when a senior starts a ticket at a later
phase), and records `source_artifacts` pointers by reference — never a copy.

Idempotent and non-destructive: never deletes and never overwrites an existing
ticket (a second run on an already-started ticket is a no-op). `decision.md` is
senior-only and is not faked here; `evidence-audit.md` comes when evidence is
audited.
"""

import os
import subprocess

import parser
import state
import validate

__all__ = ["start"]

_WORK_DIR_REL = os.path.join(".ai", "work")


def _kit_root():
    # this file: scripts/ai-workflow/start.py
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _template_dir():
    return os.path.join(_kit_root(), ".ai", "workflow", "templates")


def _git(root, *args):
    try:
        out = subprocess.run(
            ["git", "-C", root, *args], capture_output=True, text=True, timeout=10
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _template_state(ticket_id, title, phase, base_commit, branch,
                    spec_path, ticket_path, plan_path):
    """Build the ticket's state.yaml from the shipped template (single source
    of truth): parse the template, then fill in the real ticket identity."""
    tmpl = os.path.join(_template_dir(), "state.yaml")
    with open(tmpl, encoding="utf-8") as fh:
        data = parser.parse(fh.read())
    ph = phase if phase in validate.PHASES else "requirement"
    data["ticket"] = {"id": ticket_id, "title": title or ""}
    data["phase"] = ph
    data["status"] = "active"
    data["repository"] = {"base_commit": base_commit, "branch": branch}
    data["source_artifacts"] = {
        "spec": {"path": spec_path},
        "ticket": {"path": ticket_path},
        "plan": {"path": plan_path},
    }
    if ph != "requirement":
        # The template's canned action only fits the requirement entry point.
        data["next_action"]["action"] = "continue work from %s" % ph
    return data


def _scaffold_template(dst_path, name, created, ticket_id=None):
    """Copy a bundled template into dst_path if absent (idempotent)."""
    if os.path.exists(dst_path):
        return
    src = os.path.join(_template_dir(), name)
    try:
        with open(src, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        text = "# %s\n" % name
    text = text.replace("<ticket-id>", ticket_id or "<ticket-id>")
    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    created.append(dst_path)


def start(root, ticket_id, title=None, phase=None,
          spec_path=None, ticket_path=None, plan_path=None,
          base_commit=None, branch=None):
    """Start a new (greenfield) ticket from the bundled templates.

    Creates `.ai/work/<ticket-id>/` (state.yaml + evidence/handoff/progress
    scaffolds). Returns created paths; a no-op if the ticket already exists.
    """
    work_dir = os.path.join(root, _WORK_DIR_REL, ticket_id)
    state_path = os.path.join(work_dir, "state.yaml")
    if os.path.exists(state_path):
        return []  # already started; idempotent no-op

    created = []
    os.makedirs(work_dir, exist_ok=True)

    base_commit = base_commit or _git(root, "rev-parse", "HEAD")
    branch = branch or _git(root, "rev-parse", "--abbrev-ref", "HEAD")

    data = _template_state(
        ticket_id, title, phase, base_commit, branch,
        spec_path, ticket_path, plan_path,
    )
    state.save_file(state_path, data)
    created.append(state_path)

    _scaffold_template(os.path.join(work_dir, "evidence.md"), "evidence.md", created, ticket_id)
    _scaffold_template(os.path.join(work_dir, "handoff.md"), "handoff.md", created, ticket_id)
    _scaffold_template(os.path.join(work_dir, "progress.md"), "progress.md", created, ticket_id)

    return created
