"""Git code identity and review drift assessment (SCOUT-005, spec decision 6).

Read-only helpers that bind a Review verdict to the code it reviewed. All Git
access uses argument lists (never a shell) and NUL-delimited output (never
human-readable `git status` parsing), so repository paths containing spaces or
non-ASCII characters survive intact. Missing Git, an unresolvable commit, or an
unrelated history raise `contracts.ContractError`; any other changed path is
reported as a problem string so the caller can reject the mutation.
"""

import os
import shutil
import subprocess
import tempfile

import contracts

__all__ = ["code_drift", "TICKET_EXEMPT_FILES"]

# The only paths exempt from code review: this Ticket's own workflow records.
# Changing them does not stale the reviewed code (spec decision 6). Changing the
# bound Review artifact invalidates its hash separately in `set_review`.
TICKET_EXEMPT_FILES = ("state.yaml", "progress.md", "handoff.md", "review.md")


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
    (git 2.45), so the diff/ls-files probes run against a byte-identical copy of
    the index via `GIT_INDEX_FILE`; any refresh lands in the copy, never the real
    index. The copy has the same tree, so the reported paths are unchanged.
    """
    env = None
    tmpdir = None
    index = _git_index_path(root)
    if index is not None:
        tmpdir = tempfile.mkdtemp(prefix="ai-workflow-index-")
        env = dict(os.environ)
        env["GIT_INDEX_FILE"] = os.path.join(tmpdir, "index")
        if os.path.exists(index):
            shutil.copyfile(index, env["GIT_INDEX_FILE"])

    try:
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