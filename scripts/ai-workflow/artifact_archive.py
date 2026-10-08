"""Verified export of a Ticket's raw work artifacts (HARDEN-006 Task 2).

`archive_ticket` turns a v2 Ticket whose bindings are CURRENT into a single
ZIP of exact raw bytes plus a `manifest.json` describing them. It is a
verification boundary, not a generic backup API: a v1 Ticket, a pending
Review, or any stale binding (Review bytes, registered Plan, gate hash,
reviewed code) is refused, so every exported archive re-verifies against the
recorded State hashes on arrival.

The manifest (format_version 1) is JSON:

    {
      "format_version": 1,
      "ticket_id": "<ticket>",
      "snapshot_head": "<Git commit the export was taken at>",
      "entries": [
        {"path": "<repository-relative path>",
         "sha256": "<SHA-256 of the member's raw bytes>",
         "bound_sha256": "<recorded State hash> | null"}
      ]
    }

`entries` is sorted by repository-relative path; `bound_sha256` is non-null
only for a member whose bytes a recorded State hash covers (the Evidence, its
Audit, the Review, the registered Plan at its ACTUAL source path). Supporting
files (state.yaml, decision.md, progress.md, handoff.md) carry a computed
`sha256` and a null `bound_sha256` — they were never previously bound, and
the archive must not pretend otherwise. Hashes are over RAW bytes; line
endings are never normalized before hashing.

`write_archive` is the publication primitive: it validates every member name
(normalized relative path, no traversal, no duplicates, `manifest.json`
reserved) and the output path BEFORE any write, then writes a temporary file
beside the output and publishes it with a NON-OVERWRITING atomic hard link
(`os.link` fails when the target exists — `os.replace` is never used), so a
pre-existing output keeps its exact bytes and a failed write never leaves a
partial archive. Filesystem inputs are collected only after symlink-resolved
containment inside the repository root; the output must not collide with a
collected input. Every error — contract, safety, or I/O — is an
`ArchiveError`.
"""

import hashlib
import json
import os
import subprocess
import tempfile
import zipfile

import phase_checks
import review as review_mod
import state
import workflow_v2

__all__ = ["ArchiveError", "archive_ticket", "write_archive"]

_MANIFEST_NAME = "manifest.json"
_FORMAT_VERSION = 1


class ArchiveError(Exception):
    """Raised when a verified archive cannot be produced or published."""


# ---------------------------------------------------------------------------
# Member path safety (before any write)
# ---------------------------------------------------------------------------

def _norm_member(raw):
    """Normalize one member name to a safe repository-relative path.

    Backslashes are treated as separators and normalized to `/`. Rejects
    (with ArchiveError) empty names, absolute paths, Windows drive prefixes,
    empty `.`/`..` path segments (traversal), NUL, and non-string values.
    Returns the normalized name.
    """
    if not isinstance(raw, str) or not raw:
        raise ArchiveError("member path must be a non-empty string: %r"
                           % (raw,))
    if "\x00" in raw:
        raise ArchiveError("member path contains NUL: %r" % (raw,))
    name = raw.replace("\\", "/")
    if name.startswith("/"):
        raise ArchiveError("member path must be relative, not absolute: %r"
                           % (raw,))
    if len(name) >= 2 and name[1] == ":":
        raise ArchiveError("member path must not carry a drive prefix: %r"
                           % (raw,))
    segments = name.split("/")
    for segment in segments:
        if segment in ("", ".", ".."):
            raise ArchiveError(
                "member path is not normalized (empty, '.' or '..' "
                "segment): %r" % (raw,))
    return name


def _within(root_real, path):
    """True when `path` symlink-resolves inside the real repository root."""
    real = os.path.realpath(path)
    return real == root_real or real.startswith(root_real + os.sep)


# ---------------------------------------------------------------------------
# Publication
# ---------------------------------------------------------------------------

def write_archive(output, *, ticket_id, snapshot_head, entries, bindings):
    """Write `entries` plus `manifest.json` into a new ZIP at `output`.

    `entries` maps member paths to raw bytes; `bindings` maps member paths to
    recorded SHA-256 hashes those bytes must still match (a binding for a
    member that is not in `entries`, or one the bytes no longer satisfy, is
    refused — a manifest is never allowed to lie). The manifest entries are
    sorted by normalized repository-relative path; members are written in
    that same order.

    Publication is atomic and non-overwriting: the ZIP is built in a
    temporary file beside `output`, then linked to `output` with `os.link`,
    which fails when the target exists — `os.replace` is never used and a
    pre-existing output keeps its exact bytes. The temporary file is always
    removed; when safe publication is unsupported (no hard links) the error
    is clean. Raises `ArchiveError` on every validation, safety, or I/O
    failure; the output path is returned on success.
    """
    if not isinstance(output, str) or not output:
        raise ArchiveError("output path must be a non-empty string")
    if not isinstance(ticket_id, str) or not ticket_id:
        raise ArchiveError("ticket_id must be a non-empty string")
    if not isinstance(snapshot_head, str) or not snapshot_head:
        raise ArchiveError("snapshot_head must be a non-empty string")
    if not isinstance(entries, dict) or not entries:
        raise ArchiveError("no entries to archive")
    if not isinstance(bindings, dict):
        raise ArchiveError("bindings must be a dict of member path to hash")

    members = {}  # normalized name -> raw bytes
    for raw, data in entries.items():
        if not isinstance(data, (bytes, bytearray)):
            raise ArchiveError("member %r must be bytes" % (raw,))
        name = _norm_member(raw)
        if name == _MANIFEST_NAME:
            raise ArchiveError("member name %r is reserved for the manifest"
                               % (raw,))
        if name in members:
            raise ArchiveError("duplicate member path after normalization: %r"
                               % (raw,))
        members[name] = bytes(data)

    bound_by_name = {}
    for raw, recorded in bindings.items():
        name = _norm_member(raw)
        if name not in members:
            raise ArchiveError("binding names a member that is not in the "
                               "archive: %r" % (raw,))
        if recorded is not None and not isinstance(recorded, str):
            raise ArchiveError("binding for %r must be a hash string or null"
                               % (raw,))
        bound_by_name[name] = recorded

    # The manifest is built from the collected bytes themselves: each entry's
    # sha256 is computed over the exact member bytes about to be written, and
    # a recorded binding that no longer matches the bytes refuses to publish.
    manifest_entries = []
    for name in sorted(members):
        digest = hashlib.sha256(members[name]).hexdigest()
        recorded = bound_by_name.get(name)
        if recorded is not None and recorded != digest:
            raise ArchiveError(
                "recorded binding for %s does not match the member bytes "
                "(collected %s, recorded %s)" % (name, digest, recorded))
        manifest_entries.append(
            {"path": name, "sha256": digest, "bound_sha256": recorded})
    manifest = {
        "format_version": _FORMAT_VERSION,
        "ticket_id": ticket_id,
        "snapshot_head": snapshot_head,
        "entries": manifest_entries,
    }
    manifest_bytes = (json.dumps(manifest, indent=2, sort_keys=True)
                      + "\n").encode("utf-8")

    out_abs = os.path.abspath(output)
    out_dir = os.path.dirname(out_abs) or "."
    if not os.path.isdir(out_dir):
        raise ArchiveError("output directory does not exist: %s" % out_dir)
    if os.path.lexists(out_abs):
        raise ArchiveError("output already exists (a verified archive is "
                           "never overwritten): %s" % output)

    ordered = sorted(members)
    fd, tmp = tempfile.mkstemp(dir=out_dir, suffix=".tmp",
                               prefix=os.path.basename(out_abs) + ".")
    fh = None
    try:
        fh = os.fdopen(fd, "wb")
        with zipfile.ZipFile(fh, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(_MANIFEST_NAME, manifest_bytes)
            for name in ordered:
                zf.writestr(name, members[name])
        fh.close()
        fh = None
        try:
            # Non-overwriting atomic publish: os.link fails when the target
            # exists, so a concurrent appearance of the output is an error,
            # never a silent replacement.
            os.link(tmp, out_abs)
        except OSError as exc:
            raise ArchiveError("cannot publish the archive safely (the "
                               "output is never overwritten): %s" % exc)
        return out_abs
    except OSError as exc:
        raise ArchiveError("cannot write the archive: %s" % exc)
    finally:
        if fh is not None:
            try:
                fh.close()
            except OSError:
                pass
        if os.path.lexists(tmp):
            try:
                os.unlink(tmp)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Whole-Ticket export
# ---------------------------------------------------------------------------

def _git_head(root):
    """The repository's current HEAD commit, or an ArchiveError."""
    try:
        proc = subprocess.run(
            ["git", "--no-optional-locks", "-C", root, "rev-parse", "HEAD"],
            capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ArchiveError("git is not available: %s" % exc)
    if proc.returncode != 0:
        raise ArchiveError("cannot read the Git HEAD: %s"
                           % proc.stderr.decode("utf-8", "replace").strip())
    head = proc.stdout.decode("utf-8", "replace").strip()
    if not head:
        raise ArchiveError("cannot read the Git HEAD (no commits?)")
    return head


def _load(root, ticket_id):
    """Load the State once; unknown ticket and parse failures are ArchiveError."""
    rel = os.path.join(".ai", "work", ticket_id, "state.yaml")
    path = os.path.join(root, rel)
    if not os.path.exists(path):
        raise ArchiveError("no ticket %s under .ai/work/ (run `start` or "
                           "`adopt` first)" % ticket_id)
    try:
        data = state.load_file(path)
    except state.StateError as exc:
        raise ArchiveError(str(exc))
    return path, data


def _require_str_hash(value, what):
    """A recorded binding that must exist when a verdict is recorded."""
    if not isinstance(value, str) or not value:
        raise ArchiveError("%s is missing but a Review verdict is recorded "
                           "(the archive would be unverifiable)" % what)
    return value


def archive_ticket(root, ticket_id, output):
    """Export a v2 Ticket's current, verified work artifacts to a ZIP.

    Collects the exact raw bytes of the State, Evidence, Audit, Decision,
    Progress, Handoff and Review artifacts plus the registered Plan at its
    ACTUAL registered source path, under safe unique repository-relative
    paths. The Review verdict must be recorded (both `pass` and
    `changes_requested` export; a pending Review, a v1 Ticket, or any stale
    Review/Plan/gate binding — assessed WITHOUT repair's rework exception —
    is refused), and every collected byte set is compared with all recorded
    hashes before publication. Supporting files carry computed hashes and a
    null `bound_sha256`. The output must not collide with a collected input
    or an existing file. Returns the published archive path; every refusal
    is an `ArchiveError` and nothing is written.
    """
    state_path, data = _load(root, ticket_id)
    if workflow_v2.version(data) != 2:
        raise ArchiveError(
            "archive-artifacts requires workflow_version 2 (this Ticket is "
            "v1; upgrade it explicitly first)")

    review_block = data.get("review") or {}
    verdict = review_block.get("verdict")
    if verdict not in ("pass", "changes_requested"):
        raise ArchiveError(
            "only a recorded Review verdict can be exported (this Ticket's "
            "review is pending; it is not a generic backup API)")

    # Current bindings, assessed WITHOUT the repair path's rework exception:
    # an appended rework Plan needs a new review before the Ticket may be
    # exported. Refuses stale Review bytes, Plan, commit and code drift.
    problems = review_mod.binding_problems(root, ticket_id, data,
                                           allow_rework=False)
    if problems:
        raise ArchiveError(
            "the recorded Review is not current (stale binding): %s"
            % "; ".join(problems))

    evidence = data.get("evidence") or {}
    names = phase_checks.artifact_names(data)
    # progress.md is not part of phase_checks' name table (it is fixed
    # there); honor a State override if one is recorded.
    progress_name = (data.get("artifacts") or {}).get("progress") \
        or "progress.md"
    work_rel = ".ai/work/%s" % ticket_id

    # (member path, on-disk path, recorded binding or None) — supporting
    # files (state, decision, progress, handoff) are unbound.
    plan_ref = (data.get("source_artifacts") or {}).get("plan") or {}
    plan_path = plan_ref.get("path")
    if not isinstance(plan_path, str) or not plan_path:
        raise ArchiveError("no registered Plan is recorded in State")
    spec = [
        ("%s/state.yaml" % work_rel, state_path, None),
        ("%s/%s" % (work_rel, names["evidence"]),
         os.path.join(root, work_rel, names["evidence"]),
         _require_str_hash(evidence.get("report_sha256"),
                           "evidence.report_sha256")),
        ("%s/%s" % (work_rel, names["evidence_audit"]),
         os.path.join(root, work_rel, names["evidence_audit"]),
         _require_str_hash(evidence.get("audit_sha256"),
                           "evidence.audit_sha256")),
        ("%s/%s" % (work_rel, names["decision"]),
         os.path.join(root, work_rel, names["decision"]), None),
        ("%s/%s" % (work_rel, progress_name),
         os.path.join(root, work_rel, progress_name), None),
        ("%s/%s" % (work_rel, names["handoff"]),
         os.path.join(root, work_rel, names["handoff"]), None),
        ("%s/%s" % (work_rel, names["review"]),
         os.path.join(root, work_rel, names["review"]),
         _require_str_hash(review_block.get("artifact_sha256"),
                           "review.artifact_sha256")),
        (plan_path, os.path.join(root, plan_path),
         _require_str_hash(review_block.get("plan_sha256"),
                           "review.plan_sha256")),
    ]

    root_real = os.path.realpath(root)
    entries = {}
    bindings = {}
    input_reals = []
    for member, full, bound in spec:
        name = _norm_member(member)
        if name in entries:
            raise ArchiveError("duplicate member path: %s" % member)
        if not os.path.exists(full):
            raise ArchiveError("archived artifact is missing on disk: %s"
                               % member)
        if not _within(root_real, full):
            raise ArchiveError("member path escapes the repository root "
                               "(symlink-resolved): %s" % member)
        try:
            with open(full, "rb") as fh:
                raw = fh.read()
        except OSError as exc:
            raise ArchiveError("cannot read archived artifact %s: %s"
                               % (member, exc))
        digest = hashlib.sha256(raw).hexdigest()
        if bound is not None and digest != bound:
            raise ArchiveError(
                "%s does not match its recorded hash (collected %s, "
                "recorded %s): re-audit/re-review before exporting"
                % (member, digest, bound))
        entries[name] = raw
        if bound is not None:
            bindings[name] = bound
        input_reals.append(os.path.realpath(full))

    # The registered Plan's own recorded hash must also match the collected
    # bytes (the Review hash comparison alone would not catch a State whose
    # `source_artifacts.plan.sha256` drifted from both).
    registered_plan_sha = _require_str_hash(
        plan_ref.get("sha256"), "source_artifacts.plan.sha256")
    plan_name = _norm_member(plan_path)
    plan_digest = hashlib.sha256(entries[plan_name]).hexdigest()
    if plan_digest != registered_plan_sha:
        raise ArchiveError(
            "the registered Plan %s does not match its recorded hash "
            "(collected %s, recorded %s): register-plan again before "
            "exporting" % (plan_path, plan_digest, registered_plan_sha))

    if not isinstance(output, str) or not output:
        raise ArchiveError("output path must be a non-empty string")
    out_abs = os.path.abspath(output)
    if os.path.realpath(out_abs) in input_reals:
        raise ArchiveError("the output path collides with a collected "
                           "artifact: %s" % output)
    out_dir = os.path.dirname(out_abs) or "."
    if not os.path.isdir(out_dir):
        raise ArchiveError("output directory does not exist: %s" % out_dir)
    if os.path.lexists(out_abs):
        raise ArchiveError("output already exists (a verified archive is "
                           "never overwritten): %s" % output)

    return write_archive(out_abs, ticket_id=ticket_id,
                         snapshot_head=_git_head(root),
                         entries=entries, bindings=bindings)
