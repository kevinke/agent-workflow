"""`ai-workflow start` — scaffold a new (greenfield) ticket (spec §9, TICKET-008).

The greenfield counterpart to `adopt` (which handles legacy repos): creates
`.ai/work/<ticket-id>/` from the bundled templates, writes a fresh `state.yaml`
at the `requirement` phase (or `--phase` when a senior starts a ticket at a later
phase), and records `source_artifacts` pointers by reference — never a copy.

Idempotent and non-destructive: never deletes and never overwrites an existing
ticket (a second run on an already-started ticket is a no-op). `decision.md` is
senior-only and is not faked here; `evidence-audit.md` comes when evidence is
audited. On a v2 install, a start directly at `implementation`/`review` enters
explicit bootstrap recovery: the scaffold records an unresolved machine
escalation routed to the workflow-bootstrap senior resolver, and only the public
recovery sequence plus a referenced `escalate --clear` make it ready
(MIGRATION.md, STATE_SCHEMA.md).
"""

import os
import subprocess

import init
import parser
import state
import validate
import workflow_v2

__all__ = ["start"]

_WORK_DIR_REL = os.path.join(".ai", "work")

# The v2 phases whose direct entry is a senior bootstrap act: the retained
# phase's contracts (Evidence, Plan, Decision) do not exist yet, so the
# scaffold must never present itself as executor-ready. Earlier phases keep
# the ordinary entry-point scaffolds.
_BOOTSTRAP_PHASES = ("implementation", "review")


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


def _template_state(root, ticket_id, title, phase, base_commit, branch,
                    spec_path, ticket_path, plan_path):
    """Build the ticket's state.yaml from the resolved template (single source
    of truth): parse the template, then fill in the real ticket identity.

    The template is resolved from the installed target when it has one, else the
    bundled kit, so an unupgraded v1 install keeps scaffolding v1 Tickets."""
    tmpl = os.path.join(init.templates_dir(root), "state.yaml")
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
        # A later-phase v2 Ticket keeps the template's workflow-bootstrap role
        # (senior reconstruction), never an executor's; it has no current
        # evidence/Plan contracts yet.
        data["next_action"]["action"] = "continue work from %s" % ph
        if data.get("workflow_version") == 2 and ph in _BOOTSTRAP_PHASES:
            # Late-phase v2 start enters explicit bootstrap recovery
            # (HARDEN-003): the requested phase has none of its contracts yet,
            # so the scaffold must never present itself as executor-ready.
            # Record the interrupted ordinary continuation and the previous
            # Status, raise an unresolved machine escalation routed to the
            # workflow-bootstrap senior resolver, and mark the bounded
            # recovery additively (the template's unknown keys survive). Only
            # the public recovery sequence plus a referenced
            # `escalate --clear --resolution` leaves it; existing half-ready
            # states keep entering Task 1 recovery through ordinary
            # `escalate` instead.
            previous_status = data.get("status", "active")
            interrupted = workflow_v2.next_action(data, ph)
            esc = dict(data.get("escalation") or {})
            esc.update({
                "required": True,
                "scope": "machine",
                "reason": "late-phase start at %s (senior bootstrap recovery)"
                          % ph,
                "previous_status": previous_status,
                "interrupted_action": interrupted,
                "interrupted_phase": ph,
                "resolution": None,
            })
            data["escalation"] = esc
            data["recovery"] = {"kind": "bootstrap"}
            data["status"] = "escalation_required"
            data["next_action"] = {
                "role": "workflow-bootstrap",
                "action": "continue work from %s" % ph,
                "task": None,
            }
    return data


def _scaffold_template(root, dst_path, name, created, ticket_id=None):
    """Copy a resolved template into dst_path if absent (idempotent)."""
    if os.path.exists(dst_path):
        return
    src = os.path.join(init.templates_dir(root), name)
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
    On a v2 install a `--phase implementation`/`--phase review` start enters
    explicit bootstrap recovery instead of a half-ready active State.
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
        root, ticket_id, title, phase, base_commit, branch,
        spec_path, ticket_path, plan_path,
    )
    state.save_file(state_path, data)
    created.append(state_path)

    _scaffold_template(root, os.path.join(work_dir, "evidence.md"), "evidence.md", created, ticket_id)
    _scaffold_template(root, os.path.join(work_dir, "handoff.md"), "handoff.md", created, ticket_id)
    _scaffold_template(root, os.path.join(work_dir, "progress.md"), "progress.md", created, ticket_id)

    return created
