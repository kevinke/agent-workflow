"""Read-only continuation brief (SCOUT-006 Task 1, spec decision 7).

A *receiving* Agent reads `ai-workflow resume <ticket-id>` to identify its exact
next task, the referenced artifacts and their digests, and the continuation
checks -- without the departing Agent's chat history. It points at reports
rather than pasting their contents.

Strictly read-only: this module never writes `updated_at`, never claims the
ticket, and never mutates a file. Every Git observation uses
`--no-optional-locks`, so `status` does not refresh its index. Version 1 Tickets
get explicit notices for the newer contracts instead of invented gates or a
migration claim. Bound artifacts and the registered Plan also carry raw
transport notices (HARDEN-006): an effective `text` attribute other than
`-text` can rewrite bound bytes on a clone/checkout — the notice is visible
only, never a new execution gate.
"""

import os
import re
import subprocess

import contracts
import review
import state
import status
import transport
import validate
import workflow_v2

__all__ = ["resume_for_ticket", "continuation_blocked", "ResumeError",
           "HEADINGS"]

# The frozen section labels, in order.
HEADINGS = ("Ticket", "State", "Next action", "Repository", "Artifacts",
            "Checks")

_CODE_ANCHOR_RE = re.compile(r"code:\s*(\S+)")
_BLOCKING_STATUSES = ("paused", "blocked", "abandoned")
_PLACEHOLDER = "\u2014"  # em dash: "no value"
_ARTIFACT_KEYS = (
    ("evidence", "evidence", "evidence.md"),
    ("evidence-audit", "evidence_audit", "evidence-audit.md"),
    ("decision", "decision", "decision.md"),
    ("handoff", "handoff", "handoff.md"),
    ("review", "review", "review.md"),
)


class ResumeError(Exception):
    """Raised when the ticket's state.yaml cannot be read."""


def resume_for_ticket(root, ticket_id):
    """Render the read-only continuation brief for `ticket_id`.

    Raises `ResumeError` when state.yaml cannot be read; otherwise returns the
    brief text. The rendering never mutates the repository.
    """
    text, _blocked = _evaluate(root, ticket_id)
    return text


def continuation_blocked(root, ticket_id):
    """True when the brief carries ERROR blockers or a continuation blocker.

    Intended for the CLI's exit selection (`0` valid brief, `1` blocked).
    """
    _text, blocked = _evaluate(root, ticket_id)
    return blocked


# ---------------------------------------------------------------------------
# Read-only Git observations (--no-optional-locks: never refresh the index)
# ---------------------------------------------------------------------------

def _git(root, args):
    try:
        return subprocess.run(
            ["git", "--no-optional-locks", "-C", root] + list(args),
            capture_output=True)
    except OSError as exc:  # git binary missing
        raise contracts.ContractError("git is not available: %s" % exc)


def _decode(proc):
    return proc.stdout.decode("utf-8", "surrogateescape")


def _head(root):
    try:
        proc = _git(root, ["rev-parse", "HEAD"])
    except contracts.ContractError:
        return None
    if proc.returncode != 0:
        return None
    return _decode(proc).strip() or None


def _branch(root):
    try:
        proc = _git(root, ["rev-parse", "--abbrev-ref", "HEAD"])
    except contracts.ContractError:
        return None
    if proc.returncode != 0:
        return None
    return _decode(proc).strip() or None


def _dirty_paths(root):
    """Working-tree paths with uncommitted changes, or None outside a work tree."""
    try:
        proc = _git(root, ["status", "--porcelain", "-z"])
    except contracts.ContractError:
        return None
    if proc.returncode != 0:
        return None
    paths = []
    for entry in _decode(proc).split("\0"):
        if not entry:
            continue
        path = (entry[3:] if len(entry) > 3 else entry).replace("\\", "/")
        if path and path not in paths:
            paths.append(path)
    return paths


def _changed_since(root, base):
    """Committed paths changed since `base`, or None when it cannot resolve."""
    if not base:
        return None
    try:
        proc = _git(root, ["diff", "--name-only", "-z", "--no-renames",
                           "%s..HEAD" % base])
    except contracts.ContractError:
        return None
    if proc.returncode != 0:
        return None
    return [p.replace("\\", "/") for p in _decode(proc).split("\0") if p]


def _short(commit):
    return commit[:12] if isinstance(commit, str) and commit else _PLACEHOLDER


def _digest(path):
    try:
        return contracts.sha256_file(path)
    except OSError:
        return None


def _version(data):
    """(version, error): the ticket's workflow version, or the failure string."""
    try:
        return workflow_v2.version(data), None
    except contracts.ContractError as exc:
        return None, str(exc)


def _evidence_metadata(path):
    try:
        report = contracts.read_artifact(path, "evidence")
    except contracts.ContractError:
        return None
    return report.get("metadata") or {}


def _evidence_anchors(evidence_path):
    """(fact id, anchor token, file path) for code anchors in the report."""
    try:
        report = contracts.read_artifact(evidence_path, "evidence")
    except contracts.ContractError:
        return []
    anchors = []
    for rec in report.get("records") or []:
        if rec.get("kind") != "finding":
            continue
        fields = rec.get("fields") or {}
        for line in (fields.get("Sources") or "").splitlines():
            match = _CODE_ANCHOR_RE.search(line)
            if not match:
                continue
            token = match.group(1)
            path = token.rsplit(":", 1)[0] if ":" in token else token
            anchors.append((rec.get("id"), token, path))
    return anchors


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _evaluate(root, ticket_id):
    """Return (brief_text, blocked). Raises ResumeError on unreadable State."""
    state_path = status.ticket_state_path(root, ticket_id)
    work_dir = os.path.dirname(state_path)
    try:
        data = state.load_file(state_path)
    except state.StateError as exc:
        raise ResumeError(str(exc))

    findings = []
    validate.validate_ticket(root, ticket_id, findings)
    errors = [f for f in findings if f.severity == "ERROR"]

    blockers = _continuation_blockers(data)

    lines = []
    _render_ticket(lines, data, ticket_id)
    _render_state(lines, data)
    _render_next_action(lines, data)
    _render_repository(lines, root)
    _render_artifacts(lines, root, work_dir, ticket_id, data)
    _render_checks(lines, findings, blockers)

    return "\n".join(lines), bool(errors) or bool(blockers)


def _continuation_blockers(data):
    """Explicit continuation blockers that are not malformed-State Findings."""
    blockers = []
    esc = data.get("escalation")
    if isinstance(esc, dict) and esc.get("required") is True:
        reason = esc.get("reason")
        blockers.append("unresolved escalation (scope=%s)%s"
                        % (esc.get("scope"),
                           (": " + str(reason)) if reason else ""))
    status_name = data.get("status")
    if status_name in _BLOCKING_STATUSES:
        blockers.append("status=%s: no routine execution (resolve the block or "
                        "escalate)" % status_name)
    return blockers


def _render_ticket(lines, data, ticket_id):
    ticket = data.get("ticket") or {}
    lines.append("## Ticket")
    lines.append("  id    : %s" % (ticket.get("id") or ticket_id))
    title = ticket.get("title")
    if title:
        lines.append("  title : %s" % title)


def _render_state(lines, data):
    lines.append("## State")
    lines.append("  phase      : %s" % data.get("phase"))
    lines.append("  status     : %s" % data.get("status"))
    evidence = data.get("evidence") or {}
    lines.append("  gate       : %s (round %s)"
                 % (evidence.get("gate"), evidence.get("round")))

    esc = data.get("escalation")
    if isinstance(esc, dict) and esc.get("required") is True:
        lines.append("  escalation : required (scope=%s)" % esc.get("scope"))
        if esc.get("reason"):
            lines.append("  reason     : %s" % esc["reason"])
        interrupted = esc.get("interrupted_action")
        if isinstance(interrupted, dict):
            lines.append(
                "  interrupted: [%s] %s task=%s (previous_status=%s, phase=%s)"
                % (interrupted.get("role"), interrupted.get("action"),
                   interrupted.get("task"), esc.get("previous_status"),
                   esc.get("interrupted_phase")))
    else:
        lines.append("  escalation : none")
    if isinstance(esc, dict) and esc.get("resolution"):
        lines.append("  resolution : %s" % esc["resolution"])

    ver, ver_err = _version(data)
    if ver_err is not None:
        lines.append("  workflow   : unreadable (%s)" % ver_err)
    elif ver == 2:
        lines.append("  workflow   : v2 (strict contracts: registered Plan, "
                     "Review verdict, bound Evidence)")
    else:
        lines.append(
            "  workflow   : v1 \u2014 newer v2 contracts are not enabled (no "
            "registered Plan, no Review verdict, no Evidence binding); Ticket "
            "migration is explicit, never automatic")


def _render_next_action(lines, data):
    next_action = data.get("next_action") or {}
    lines.append("## Next action")
    lines.append("  role    : %s" % (next_action.get("role") or _PLACEHOLDER))
    lines.append("  action  : %s" % (next_action.get("action") or _PLACEHOLDER))
    task = next_action.get("task")
    if task is None:
        lines.append("  task    : %s (no executable task)" % _PLACEHOLDER)
    else:
        lines.append("  task    : %s (executable task)" % task)
    lines.append("  reminder: record handoff.md before stopping (the "
                 "checkpoint-handoff role owns the handoff discipline)")


def _render_repository(lines, root):
    lines.append("## Repository")
    head = _head(root)
    dirty = _dirty_paths(root)
    lines.append("  branch : %s" % (_branch(root) or _PLACEHOLDER))
    lines.append("  head   : %s" % (_short(head) if head else _PLACEHOLDER))
    if dirty is None:
        lines.append("  dirty  : unknown (not a Git work tree)")
    elif not dirty:
        lines.append("  dirty  : none")
    else:
        lines.append("  dirty  : %d path(s)" % len(dirty))
        for path in dirty:
            lines.append("    %s" % path)


def _render_artifacts(lines, root, work_dir, ticket_id, data):
    lines.append("## Artifacts")
    artifacts = data.get("artifacts") or {}
    evidence_name = artifacts.get("evidence", "evidence.md")

    meta = _evidence_metadata(os.path.join(work_dir, evidence_name))
    evidence_note = None
    if meta is not None:
        evidence_note = "observed_commit=%s round=%s" % (
            _short(str(meta.get("observed_commit") or "")), meta.get("round"))

    for label, key, default in _ARTIFACT_KEYS:
        name = artifacts.get(key, default)
        digest = _digest(os.path.join(work_dir, name))
        if digest is None:
            lines.append("  %-18s (missing)" % name)
        elif evidence_note and key == "evidence":
            lines.append("  %-18s sha256=%s  (%s)" % (name, digest, evidence_note))
        else:
            lines.append("  %-18s sha256=%s" % (name, digest))

    _render_plan(lines, root, data)
    _render_evidence_freshness(lines, root, work_dir, evidence_name)
    _render_review_freshness(lines, root, ticket_id, data)
    _render_transport_notices(lines, root, work_dir, data)


def _render_plan(lines, root, data):
    ver, _ = _version(data)
    plan_ref = (data.get("source_artifacts") or {}).get("plan") or {}
    path = plan_ref.get("path")
    sha = plan_ref.get("sha256")
    if not path:
        if ver == 2:
            lines.append("  %-18s (no registered Plan; register one with "
                         "register-plan)" % "plan")
        else:
            lines.append("  %-18s (v1: no registered Plan; registration is a "
                         "v2 contract)" % "plan")
        return
    digest = _digest(os.path.join(root, path))
    if digest is None:
        lines.append("  %-18s %s (recorded but missing on disk)"
                     % ("plan", path))
    else:
        note = "registered"
        if sha and digest != sha:
            note = "registered hash mismatch (re-register)"
        lines.append("  %-18s %s sha256=%s (%s)"
                     % ("plan", path, digest, note))


def _render_evidence_freshness(lines, root, work_dir, evidence_name):
    meta = _evidence_metadata(os.path.join(work_dir, evidence_name))
    if meta is None:
        return
    observed = meta.get("observed_commit")
    head = _head(root)
    if not (isinstance(observed, str) and observed and head and observed != head):
        return

    lines.append(
        "  evidence           observed_commit %s differs from HEAD %s; anchor "
        "relevance assessment required (recorded facts are not automatically "
        "discarded)" % (_short(observed), _short(head)))
    changed = _changed_since(root, observed)
    if changed:
        lines.append("  evidence           changed since the observed commit: "
                     "%s" % ", ".join(changed))
    changed_set = set(changed or [])
    for fact_id, token, path in _evidence_anchors(
            os.path.join(work_dir, evidence_name)):
        if path in changed_set:
            lines.append("  evidence           %s anchor %s changed; assess "
                         "whether this pivotal anchor still supports the "
                         "recorded fact" % (fact_id, token))


def _render_review_freshness(lines, root, ticket_id, data):
    """Freshness of a recorded verdict, for `pass` and `changes_requested`.

    The same shared binding check the validators and mutation guards run
    (`review.binding_problems`): a `pass` must stay current to complete, and a
    recorded `changes_requested` must keep its Review bytes, immutable commit,
    registered Plan and code identity (a coherent appended-rework Plan is the
    one permitted Plan drift). `pending` has no recorded binding to report.
    """
    block = data.get("review")
    if not isinstance(block, dict):
        return
    verdict = block.get("verdict")
    if verdict not in ("pass", "changes_requested"):
        return
    problems = review.binding_problems(
        root, ticket_id, data,
        allow_rework=(verdict == "changes_requested"))
    for problem in problems:
        lines.append("  review             %s" % problem)


def _render_transport_notices(lines, root, work_dir, data):
    """Raw-transport notices for bound artifacts and the registered Plan.

    The same shared path set `validate_ticket` warns about (its WARN findings
    also reach the Checks section): an effective `text` attribute other than
    `-text` can rewrite bound bytes on a clone/checkout and invalidate every
    SHA-256 binding. Contextual and read-only — never a blocker; pinning a
    path with `-text` stays the user's explicit decision.
    """
    ver, _ = _version(data)
    if ver != 2:
        return
    for problem in transport.attribute_problems(
            root, validate.bound_artifact_paths(root, work_dir, data)):
        lines.append("  %-18s %s" % ("transport", problem))


def _render_checks(lines, findings, blockers):
    lines.append("## Checks")
    if not findings and not blockers:
        lines.append("  (no findings)")
        return
    for finding in sorted(findings, key=lambda f: (f.severity != "ERROR",
                                                   f.message)):
        lines.append("  %-5s %s" % (finding.severity, finding.message))
    for blocker in blockers:
        lines.append("  blocker: %s" % blocker)