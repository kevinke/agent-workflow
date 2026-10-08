"""Git code identity and review drift assessment (SCOUT-005, spec decision 6).

Read-only helpers that bind a Review verdict to the code it reviewed, for both
recorded verdicts. All Git access uses argument lists (never a shell) and
NUL-delimited output (never human-readable `git status` parsing), so repository
paths containing spaces or non-ASCII characters survive intact. Missing Git, an
unresolvable commit, or an unrelated history raise `contracts.ContractError`;
any other changed path is reported as a problem string so the caller can reject
the mutation. `resolve_commit` turns a literal hexadecimal object ID into the
full ancestral commit it names; `binding_problems` reports every way a recorded
verdict has stopped matching its immutable bindings (never raising, so
validators can surface stale State without a traceback).
"""

import os
import shutil
import subprocess
import tempfile

import contracts
import workflow_v2

__all__ = ["code_drift", "resolve_commit", "binding_problems",
           "TICKET_EXEMPT_FILES"]

# The only paths exempt from code review: this Ticket's own workflow records.
# Changing them does not stale the reviewed code (spec decision 6). Changing the
# bound Review artifact invalidates its hash separately in `set_review`.
TICKET_EXEMPT_FILES = ("state.yaml", "progress.md", "handoff.md", "review.md")

# Literal hexadecimal object IDs only (C1). The legal length range runs from a
# seven-character abbreviation to the repository's full object ID (git's
# `--show-object-format`: sha1 -> 40, sha256 -> 64 hex digits).
_OBJECT_FORMAT_LENGTHS = {"sha1": 40, "sha256": 64}
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_MIN_ABBREV_LEN = 7


def _run_git(root, args, env=None):
    """Run `git --no-optional-locks -C root <args>`; bytes out, no shell.

    `--no-optional-locks` stops `git status` from refreshing the stat cache, but
    on git 2.45 a worktree `git diff` rewrites `.git/index` anyway, so callers
    that run `diff` also pass a throwaway `GIT_INDEX_FILE` (see
    `_changed_paths`). Callers that only read (rev-parse, merge-base) need no
    redirect.
    """
    try:
        return subprocess.run(["git", "--no-optional-locks", "-C", root] + list(args),
                              capture_output=True, env=env)
    except OSError as exc:  # git binary missing
        raise contracts.ContractError("git is not available: %s" % exc)


def _require_work_tree(root):
    proc = _run_git(root, ["rev-parse", "--is-inside-work-tree"])
    if proc.returncode != 0 or proc.stdout.strip() != b"true":
        raise contracts.ContractError("not a Git work tree: %r" % (root,))


def _require_ancestor(root, reviewed_commit):
    """The reviewed commit must resolve AND be an ancestor of HEAD."""
    if not reviewed_commit or reviewed_commit.startswith("-"):
        raise contracts.ContractError(
            "reviewed_commit %r is missing or malformed" % (reviewed_commit,))
    proc = _run_git(root, ["rev-parse", "--verify", "--quiet",
                           reviewed_commit + "^{commit}"])
    if proc.returncode != 0:
        raise contracts.ContractError(
            "reviewed_commit %r does not resolve to a commit"
            % (reviewed_commit,))
    proc = _run_git(root, ["merge-base", "--is-ancestor",
                           reviewed_commit, "HEAD"])
    if proc.returncode != 0:
        raise contracts.ContractError(
            "reviewed_commit %r is not an ancestor of HEAD (unrelated history)"
            % (reviewed_commit,))


def _object_id_length(root):
    """The repository's full object ID length (40 for sha1, 64 for sha256)."""
    proc = _run_git(root, ["rev-parse", "--show-object-format"])
    if proc.returncode != 0:
        raise contracts.ContractError(
            "cannot read the repository object format: %s"
            % proc.stderr.decode("utf-8", "replace").strip())
    fmt = proc.stdout.decode("utf-8", "replace").strip()
    length = _OBJECT_FORMAT_LENGTHS.get(fmt)
    if length is None:
        raise contracts.ContractError("unsupported Git object format %r"
                                      % (fmt,))
    return length


def resolve_commit(root, revision):
    """Resolve a literal hexadecimal commit ID to the full commit it names.

    `revision` must be a literal hexadecimal object ID — the repository's full
    object ID or an unambiguous abbreviation of at least seven hex digits —
    that resolves to a commit and is an ancestor of HEAD. HEAD, branch and tag
    names are rejected even when they resolve: a recorded review must never
    follow a moving ref, and a historical symbolic binding is stale rather
    than re-authenticated by today's HEAD. The object database is the only
    authority (`git rev-parse --disambiguate`), so a ref named like a
    hexadecimal prefix never takes precedence over the object carrying it.

    Returns the full commit ID. Raises `contracts.ContractError` when Git is
    missing, `root` is not a work tree, the value is not a literal hex ID of
    legal length, it matches no object or several, the object is not a commit,
    or it is unrelated history. Read-only: no refs or objects are written.
    """
    _require_work_tree(root)
    if not isinstance(revision, str) or not revision \
            or revision.startswith("-") or not set(revision) <= _HEX_DIGITS:
        raise contracts.ContractError(
            "%r is not a literal hexadecimal commit ID (HEAD, branch and tag "
            "names are rejected; only a full or unambiguous abbreviated "
            "object ID resolves)" % (revision,))
    oid_length = _object_id_length(root)
    if not _MIN_ABBREV_LEN <= len(revision) <= oid_length:
        raise contracts.ContractError(
            "%r is not a valid object-ID length for this repository "
            "(expected %d..%d hexadecimal characters)"
            % (revision, _MIN_ABBREV_LEN, oid_length))

    proc = _run_git(root, ["rev-parse",
                           "--disambiguate=%s" % revision.lower()])
    if proc.returncode != 0:
        raise contracts.ContractError(
            "%r cannot be resolved against the object database: %s"
            % (revision, proc.stderr.decode("utf-8", "replace").strip()))
    candidates = proc.stdout.decode("utf-8", "replace").split()
    if not candidates:
        raise contracts.ContractError(
            "%r does not match any object in the repository" % (revision,))
    if len(candidates) > 1:
        raise contracts.ContractError(
            "%r is ambiguous (%d objects share this prefix)"
            % (revision, len(candidates)))

    # Peel by the FULL object ID only, so no ref named like the hex prefix can
    # stand in for the object; a tag peels to its commit, a blob/tree fails.
    full_oid = candidates[0]
    proc = _run_git(root, ["rev-parse", "--verify", "--quiet",
                           full_oid + "^{commit}"])
    if proc.returncode != 0:
        raise contracts.ContractError(
            "%r resolves to a non-commit object" % (revision,))
    commit = proc.stdout.decode("utf-8", "replace").strip()

    proc = _run_git(root, ["merge-base", "--is-ancestor", commit, "HEAD"])
    if proc.returncode != 0:
        raise contracts.ContractError(
            "%r is not an ancestor of HEAD (unrelated history)" % (revision,))
    return commit


def _rework_append_ok(root, ticket_id, data):
    """True for a registered appending rework Plan with an unchanged prefix.

    The narrow `changes_requested` rework exception of `binding_problems`:
    the registered Plan must strictly extend the completed work (an appended
    tail beyond the completed prefix) and the completed tasks' canonical
    contracts must be byte-identical to the registered Plan's prefix.
    """
    impl = data.get("implementation") or {}
    current = impl.get("current_task")
    total = impl.get("total_tasks")
    current = 0 if current is None else current
    total = 0 if total is None else total
    if not workflow_v2.is_nonneg_int(current) \
            or not workflow_v2.is_nonneg_int(total) \
            or current < 1 or current >= total:
        return False
    recorded = impl.get("task_hashes")
    if not isinstance(recorded, list) or len(recorded) != total:
        return False
    plan_ref = (data.get("source_artifacts") or {}).get("plan") or {}
    plan_path = plan_ref.get("path")
    if not plan_path:
        return False
    try:
        tasks = contracts.read_plan(os.path.join(root, plan_path), ticket_id)
    except contracts.ContractError:
        return False
    expected = [t["sha256"] for t in tasks[:current]]
    return [str(h) for h in recorded[:current]] == expected


def binding_problems(root, ticket_id, data, *, allow_rework=False):
    """Identity problems of the recorded Review verdict; [] means current.

    Read-only and never raises: every disagreement is returned as a problem
    string so validate, resume and the mutation guards report and reject the
    same stale bindings. Both recorded verdicts (`pass` and
    `changes_requested`) must still agree with what they were bound to:

    - a recorded verdict carries all three binding fields — a missing
      `artifact_sha256` or `plan_sha256` (hand-corrupted State) is a problem
      in itself, exactly as the pre-refactor unconditional comparisons
      rejected it;
    - the Review artifact's raw bytes (`review.artifact_sha256`);
    - the registered Plan's raw bytes (`review.plan_sha256`);
    - the reviewed commit (`review.reviewed_commit`): a literal hexadecimal
      object ID that still resolves to an ancestor of HEAD — a historical
      symbolic value is stale and needs a new review, never re-authenticated
      by resolving today's HEAD; and
    - the code at that commit (the `code_drift` rules).

    A `pending` verdict has no recorded binding and yields no problems here.

    `allow_rework` grants one narrow exception for a recorded
    `changes_requested`: when a strictly-appending rework Plan is registered
    and the completed task contracts are unchanged, only that Plan drift is
    excluded — the re-registration is the rework itself. Source-code drift,
    changed Review bytes, and a recorded `pass` never inherit the exception.
    """
    block = data.get("review") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return []
    verdict = block.get("verdict")
    if verdict not in ("pass", "changes_requested"):
        return []  # pending has no recorded binding to check

    problems = []
    rework = (allow_rework and verdict == "changes_requested"
              and _rework_append_ok(root, ticket_id, data))

    name = ((data.get("artifacts") or {}).get("review") or "review.md")
    review_path = os.path.join(root, ".ai", "work", ticket_id, name)
    expected_artifact = block.get("artifact_sha256")
    if not isinstance(expected_artifact, str):
        problems.append("review.artifact_sha256 is missing but a verdict is "
                        "recorded (stale binding: re-review and set-review "
                        "again)")
    elif not os.path.exists(review_path):
        problems.append("Review artifact %s is missing (stale binding: "
                        "re-review and set-review again)" % name)
    else:
        try:
            current_sha = contracts.sha256_file(review_path)
        except OSError as exc:
            problems.append("the Review artifact is unreadable: %s" % exc)
        else:
            if current_sha != expected_artifact:
                problems.append(
                    "Review artifact changed since the verdict was "
                    "recorded (stale binding: re-review and set-review "
                    "again)")

    sources = data.get("source_artifacts") or {}
    plan_ref = sources.get("plan") or {}
    plan_path = plan_ref.get("path")
    recorded_plan = block.get("plan_sha256")
    if not isinstance(recorded_plan, str):
        problems.append("review.plan_sha256 is missing but a verdict is "
                        "recorded (stale binding: re-review against the "
                        "current Plan)")
    elif recorded_plan != plan_ref.get("sha256") and not rework:
        problems.append(
            "review.plan_sha256 no longer matches the registered Plan "
            "(stale binding: re-review against the current Plan)")

    try:
        commit = resolve_commit(root, block.get("reviewed_commit"))
    except contracts.ContractError as exc:
        problems.append("review.reviewed_commit is stale: %s" % exc)
        return problems  # no immutable commit left to assess drift against

    try:
        drift = code_drift(root, ticket_id, commit, plan_path)
    except contracts.ContractError as exc:
        problems.append("cannot assess review code drift: %s" % exc)
        return problems
    if rework:
        plan_note = ("the registered Plan changed since the reviewed commit: %s"
                     % (plan_path or "").replace("\\", "/"))
        drift = [problem for problem in drift if problem != plan_note]
    problems.extend("review is stale: %s" % problem for problem in drift)
    return problems


def _names(root, args, env=None):
    """NUL-split the output of a `-z` Git command; [] when it is noise."""
    proc = _run_git(root, args, env)
    if proc.returncode != 0:
        raise contracts.ContractError(
            "git %s failed: %s"
            % (" ".join(args),
               proc.stderr.decode("utf-8", "replace").strip()))
    text = proc.stdout.decode("utf-8", "surrogateescape")
    return [p for p in text.split("\0") if p]


def _git_index_path(root):
    """Absolute path of this worktree's index, or None when unresolvable."""
    proc = _run_git(root, ["rev-parse", "--git-path", "index"])
    if proc.returncode != 0:
        return None
    path = proc.stdout.decode("utf-8", "surrogateescape").strip()
    if not path:
        return None
    if not os.path.isabs(path):
        path = os.path.join(root, path)
    return path


def _changed_paths(root, reviewed_commit):
    """Union of committed, staged, unstaged, and untracked paths (forward /).

    A worktree `git diff` rewrites `.git/index` even under `--no-optional-locks`
    (git 2.45), so the diff/ls-files probes run against a copy of the index via
    `GIT_INDEX_FILE`; any refresh lands in the copy, never the real index. The
    copy is stat-preserving (`shutil.copy2`): git re-checks by content every
    entry whose cached mtime is not older than the index file's own (racy-stat),
    so preserving the original mtime keeps that re-check engaged on the copy and
    an equal-size dirty edit whose file mtime collides with the cached stat is
    re-compared instead of being trusted clean. The copy has the same tree, so
    the reported paths are unchanged.
    """
    env = None
    tmpdir = None
    try:
        index = _git_index_path(root)
        if index is not None:
            tmpdir = tempfile.mkdtemp(prefix="ai-workflow-index-")
            env = dict(os.environ)
            env["GIT_INDEX_FILE"] = os.path.join(tmpdir, "index")
            if os.path.exists(index):
                try:
                    shutil.copy2(index, env["GIT_INDEX_FILE"])
                except OSError as exc:
                    raise contracts.ContractError(
                        "cannot read the Git index for a read-only drift "
                        "check: %s" % exc)

        paths = []
        for args in (
            ["diff", "--name-only", "-z", "--no-renames",
             "%s..HEAD" % reviewed_commit],
            ["diff", "--name-only", "-z", "--no-renames", "--cached"],
            ["diff", "--name-only", "-z", "--no-renames"],
            ["ls-files", "-z", "--others", "--exclude-standard"],
        ):
            for path in _names(root, args, env):
                path = path.replace("\\", "/")
                if path not in paths:
                    paths.append(path)
        return paths
    finally:
        if tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)


def code_drift(root, ticket_id, reviewed_commit, plan_path):
    """Repository-relative paths changed since the reviewed commit.

    Returns a list of problem strings; `[]` means the reviewed code is current.
    Raises `contracts.ContractError` when Git is missing, `root` is not a work
    tree, the reviewed commit does not resolve, or it is unrelated history.
    Read-only: it never writes.
    """
    _require_work_tree(root)
    _require_ancestor(root, reviewed_commit)

    exempt = {".ai/work/%s/%s" % (ticket_id, name)
              for name in TICKET_EXEMPT_FILES}
    plan_path = (plan_path or "").replace("\\", "/")

    problems = []
    for path in _changed_paths(root, reviewed_commit):
        if path in exempt:
            continue
        if path == plan_path:
            problems.append("the registered Plan changed since the reviewed "
                            "commit: %s" % path)
        else:
            problems.append("changed since the reviewed commit: %s" % path)
    return problems