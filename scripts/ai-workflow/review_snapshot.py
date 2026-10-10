"""Identified independent review snapshot preparation (HARDEN-011 Task 1).

The trusted coordinator prepares a disposable, fully independent repository
snapshot for the reviewer: an independent Git clone (``--no-local
--no-checkout``, no reference/alternates) checked out at the reviewed commit,
plus raw-byte copies of the registered Plan and the configured verification
inputs (except the Review artifact) at identical repository-relative paths.
Supervisor-owned identities live in ``meta/context.json`` outside the
verifier's write scope; ``scratch/`` holds verifier outputs and ``repo/`` the
snapshot checkout.

Preparation is transactional: the HARDEN-010 ``review.code_drift`` assessment
runs before AND after capture, the literal reviewed commit is resolved once,
and any failure raises ``contracts.ContractError`` and removes the whole
context directory — live source, workflow records, Git index and Git metadata
are never modified. ``assert_current`` re-validates the persisted context
against the live repository before a later phase may rely on it.

All Git access uses argument lists (never a shell) and NUL-delimited output,
mirroring ``review.py``; every manifest identity is the SHA-256 of the UTF-8
canonical JSON of the manifest map (``sort_keys=True``,
``separators=(",", ":")``).
"""

import contextlib
import hashlib
import json
import os
import shutil
import stat
import subprocess

import contracts
import host_runtime
import review
import state
import workflow_v2

__all__ = ["prepare", "assert_current"]

FORMAT_VERSION = 1

# Context layout (frozen): the independent clone, verifier outputs and the
# supervisor-only manifest. Nothing is installed under the live `.ai/work/`.
_REPO_DIR = "repo"
_SCRATCH_DIR = "scratch"
_META_DIR = "meta"
_CONTEXT_FILE = "context.json"

# The configured artifact keys captured as verification inputs. The Review
# artifact is deliberately excluded: it is the verdict carrier, not an input.
_INPUT_KEYS = ("evidence", "evidence_audit", "decision", "progress", "handoff")

# Canonical JSON for manifest identities.
_JSON_SEPARATORS = (",", ":")

# Tracked index modes: a gitlink cannot be hashed as ordinary content, and a
# 120000 blob is a symlink rather than a directory even when its target is one.
_MODE_GITLINK = "160000"
_MODE_SYMLINK = "120000"


@contextlib.contextmanager
def _io_contract(action):
    """Translate an OSError raised inside `action` into the module contract.

    `prepare` and `assert_current` promise `contracts.ContractError` for every
    failure; a raw OSError would reach the CLI as a traceback instead of exit 1
    and, inside `prepare`, would escape before the rollback ran.
    """
    try:
        yield
    except OSError as exc:
        raise contracts.ContractError(
            "%s: %s" % (action, exc))


def _remove_tree(path):
    """Delete a whole context tree, then prove it is gone.

    `git clone --no-local` writes pack objects with mode 0444, and Windows
    refuses to delete a read-only file. `shutil.rmtree(..., ignore_errors=True)`
    swallows that and silently leaves a full clone of the live repository
    behind, so the read-only bits are cleared first and the removal is checked.
    """
    if not os.path.lexists(path):
        return
    for dirpath, dirnames, filenames in os.walk(path):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            try:
                # `os.access`/`os.chmod` follow a link to its target. Safe here:
                # a context is built from a scope pass that already refused any
                # link escaping the repository, and this only ever widens the
                # writable bit on a tree that is about to be deleted.
                if not os.access(full, os.W_OK):
                    os.chmod(full, stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass  # rmtree below reports anything genuinely undeletable
    try:
        shutil.rmtree(path)
    except OSError as exc:
        raise contracts.ContractError(
            "cannot remove the failed review snapshot directory %r; it may "
            "still hold a clone of the live repository: %s" % (path, exc))
    if os.path.lexists(path):
        raise contracts.ContractError(
            "the failed review snapshot directory %r still exists after "
            "removal; it may still hold a clone of the live repository" % path)


def _run_git(root, args, env=None):
    """Run `git --no-optional-locks -C root <args>`; bytes out, no shell."""
    try:
        return subprocess.run(["git", "--no-optional-locks", "-C", root]
                              + list(args), capture_output=True, env=env)
    except OSError as exc:  # git binary missing
        raise contracts.ContractError("git is not available: %s" % exc)


def _git_out(root, args, env=None):
    """NUL-split output of a `-z` Git command; ContractError on failure."""
    proc = _run_git(root, args, env)
    if proc.returncode != 0:
        raise contracts.ContractError(
            "git %s failed: %s"
            % (" ".join(args), proc.stderr.decode("utf-8", "replace").strip()))
    return proc.stdout.decode("utf-8", "surrogateescape")


def _input_sha(full, rel):
    """SHA-256 of a captured file, naming it if the file cannot be read."""
    try:
        return contracts.sha256_file(full)
    except OSError as exc:
        raise contracts.ContractError(
            "cannot hash verification input %r: %s" % (rel, exc))


def _manifest_delta(entries, scope_paths):
    """Attribute a live-manifest mismatch as far as the persisted scope allows.

    Only the manifest identity is persisted, not a hash per path, so a content
    change is reported as an identity move; paths that vanished are nameable
    because the persisted scope lists them.
    """
    gone = sorted(set(scope_paths) - set(entries))
    if not gone:
        return "in-scope content or modes changed"
    shown = ", ".join(gone[:5])
    if len(gone) > 5:
        shown += " (+%d more)" % (len(gone) - 5)
    return "in-scope path(s) no longer hashable: %s" % shown


def _canonical_sha(mapping):
    """SHA-256 of the UTF-8 canonical JSON of a manifest map."""
    raw = json.dumps(mapping, sort_keys=True,
                     separators=_JSON_SEPARATORS).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _load_state(root, ticket_id):
    path = os.path.join(root, ".ai", "work", ticket_id, "state.yaml")
    if not os.path.exists(path):
        raise contracts.ContractError(
            "no ticket %s under .ai/work/ (run `start` or `adopt` first)"
            % ticket_id)
    try:
        data = state.load_file(path)
    except (state.StateError, OSError) as exc:
        raise contracts.ContractError(str(exc))
    try:
        workflow_v2.version(data)
    except contracts.ContractError as exc:
        raise contracts.ContractError(str(exc))
    return data


def _require_ready(root, ticket_id, data):
    """v2 Review readiness with every registered task complete."""
    if workflow_v2.version(data) != 2:
        raise contracts.ContractError(
            "prepare-review requires workflow_version 2 (this Ticket is v1; "
            "upgrade it explicitly first)")
    problems = workflow_v2.readiness_problems(root, ticket_id, data)
    if problems:
        raise contracts.ContractError(
            "cannot prepare a review snapshot: %s" % "; ".join(problems))
    impl = data.get("implementation") or {}
    if workflow_v2.executable_task(impl) is not None:
        raise contracts.ContractError(
            "cannot prepare a review snapshot: not all registered tasks are "
            "complete (implementation.current_task=%r of total_tasks=%r)"
            % (impl.get("current_task"), impl.get("total_tasks")))


def _require_clean_drift(root, ticket_id, full_oid, plan_path):
    """Run the HARDEN-010 assessment; reject any reported drift."""
    drift = review.code_drift(root, ticket_id, full_oid, plan_path)
    if drift:
        raise contracts.ContractError(
            "cannot prepare a review snapshot: the reviewed code changed "
            "since %s: %s" % (full_oid, "; ".join(drift)))


def _check_output_path(root, output):
    """The context directory must be new and outside the live repository."""
    if not output:
        raise contracts.ContractError("--output <new-directory> is required")
    if os.path.exists(output):
        raise contracts.ContractError(
            "the output directory already exists: %r (prepare-review needs a "
            "previously-absent directory)" % output)
    real_root = os.path.realpath(root)
    real_out = os.path.realpath(os.path.abspath(output))
    inside = real_out == real_root or real_out.startswith(real_root + os.sep)
    if not inside:
        # A sibling path is fine, but the live Git metadata must not contain
        # it either (it cannot exist yet, so only the containment direction
        # that can occur is output as an ancestor of root — refused above by
        # the existence check; still, keep the Git-dir guard explicit).
        for git_dir in _git_dirs(root):
            if real_out == git_dir or real_out.startswith(git_dir + os.sep):
                inside = True
                break
    if inside:
        raise contracts.ContractError(
            "the output directory must be outside the live worktree and Git "
            "metadata: %r" % output)


def _git_dirs(root):
    """Absolute paths of the worktree Git dir and the common Git dir."""
    dirs = []
    for key in ("--git-dir", "--git-common-dir"):
        proc = _run_git(root, ["rev-parse", key])
        if proc.returncode != 0:
            raise contracts.ContractError(
                "cannot resolve the Git directory: %s"
                % proc.stderr.decode("utf-8", "replace").strip())
        path = proc.stdout.decode("utf-8", "surrogateescape").strip()
        if not os.path.isabs(path):
            path = os.path.join(root, path)
        dirs.append(os.path.realpath(path))
    return dirs


def _record_paths(ticket_id):
    """The four exact code-drift record paths of this Ticket."""
    return {".ai/work/%s/%s" % (ticket_id, name)
            for name in review.TICKET_EXEMPT_FILES}


def _scope_paths(root, ticket_id):
    """(paths, kinds, ignore_rules): tracked + nonignored untracked minus records.

    `paths` is the sorted repository-relative path list in scope; `kinds` maps
    each to "file" or "symlink"; `ignore_rules` persists the exclude sources
    the standard untracked scan consulted. Submodules are rejected outright:
    their gitlink entries cannot be hashed as ordinary content.
    """
    records = _record_paths(ticket_id)
    paths = []
    kinds = {}
    for entry in _git_out(root, ["ls-files", "-s", "-z"]).split("\0"):
        if not entry:
            continue
        header, _, path = entry.partition("\t")
        if not path or path in records:
            continue
        if header.split(" ")[0] == _MODE_GITLINK:
            raise contracts.ContractError(
                "cannot prepare a review snapshot: submodule %r is in scope; "
                "submodules are not supported in this profile" % path)
        full = os.path.join(root, path)
        kinds[path] = _worktree_kind(root, full, path)
        paths.append(path)
    for path in _git_out(
            root, ["ls-files", "-z", "--others",
                   "--exclude-standard"]).split("\0"):
        if not path or path in records or path in kinds:
            continue
        full = os.path.join(root, path)
        if _is_plain_directory(full):
            continue  # untracked directories are reported through their contents
        kinds[path] = _worktree_kind(root, full, path)
        paths.append(path)
    ignore_rules = _ignore_rules(root)
    return sorted(paths), kinds, ignore_rules


def _is_plain_directory(full):
    """True for a real directory; False for a symlink that points at one."""
    try:
        return stat.S_ISDIR(os.lstat(full).st_mode)
    except OSError:
        return False


def _worktree_kind(root, full, rel):
    """Classify an in-scope path from its own lstat; reject odd shapes.

    Classification must not follow the link: `os.path.isdir` reports a symlink to
    a directory as a directory, which would both mislabel an in-repo directory
    symlink as a submodule and silently drop an out-repo one from scope, so an
    escaping link would be omitted rather than refused.
    """
    st = os.lstat(full)
    if stat.S_ISLNK(st.st_mode):
        _check_symlink(root, full, rel)
        return "symlink"
    if stat.S_ISDIR(st.st_mode):
        raise contracts.ContractError(
            "cannot prepare a review snapshot: %r is a directory at a tracked "
            "path that is not a gitlink" % rel)
    if stat.S_ISREG(st.st_mode):
        return "file"
    raise contracts.ContractError(
        "cannot prepare a review snapshot: %r is neither a regular file nor a "
        "symlink" % rel)


def _ignore_rules(root):
    """The exclude sources the standard untracked scan consulted."""
    rules = ["git:core.excludesFile", "git:.git/info/exclude"]
    proc = _run_git(root, ["rev-parse", "--show-toplevel"])
    if proc.returncode == 0:
        top = proc.stdout.decode("utf-8", "surrogateescape").strip()
        ignore = os.path.join(top, ".gitignore")
        if os.path.exists(ignore):
            rules.append(".gitignore")
    return rules


def _check_symlink(root, full, rel):
    """Reject a symlink whose target escapes the repository root."""
    if not os.path.islink(full):
        return
    target = os.readlink(full)
    if os.path.isabs(target):
        raise contracts.ContractError(
            "cannot prepare a review snapshot: symlink %r has an absolute "
            "target outside the repository" % rel)
    resolved = os.path.realpath(full)
    real_root = os.path.realpath(root)
    if resolved != real_root and not resolved.startswith(real_root + os.sep):
        raise contracts.ContractError(
            "cannot prepare a review snapshot: symlink %r escapes the "
            "repository root" % rel)


def _manifest(root, paths):
    """{path: {kind, sha256, mode}} for the in-scope paths present under root.

    File hashes cover raw bytes; symlink hashes cover the link-target bytes.
    """
    entries = {}
    for path in paths:
        full = os.path.join(root, path)
        if not os.path.lexists(full):
            continue
        st = os.lstat(full)
        mode = stat.S_IMODE(st.st_mode)
        if stat.S_ISLNK(st.st_mode):
            kind = "symlink"
            digest = hashlib.sha256(os.readlink(full).encode(
                "utf-8", "surrogateescape")).hexdigest()
        elif stat.S_ISREG(st.st_mode):
            kind = "file"
            digest = contracts.sha256_file(full)
        else:
            continue
        entries[path] = {"kind": kind, "sha256": digest, "mode": mode}
    return entries


def _configured_inputs(root, ticket_id, data):
    """{(repo-relative path, on-disk full path)} of raw-byte capture inputs.

    The registered Plan plus the configured existing artifacts except Review,
    resolved against the Ticket work directory. Escaping or absolute paths are
    refused rather than silently rewritten.
    """
    work_rel = os.path.join(".ai", "work", ticket_id)
    work_dir = os.path.join(root, work_rel)
    targets = []
    plan_ref = (data.get("source_artifacts") or {}).get("plan") or {}
    plan_path = plan_ref.get("path")
    if plan_path:
        _bounded_input(root, plan_path)
        targets.append(plan_path.replace("\\", "/"))
    artifacts = data.get("artifacts") or {}
    for key in _INPUT_KEYS:
        name = artifacts.get(key)
        if not name:
            continue
        targets.append(_artifact_rel(root, ticket_id, name))
    state_rel = os.path.join(work_rel, "state.yaml").replace("\\", "/")
    seen = set()
    out = []
    for rel in targets + [state_rel]:
        if rel in seen:
            continue
        seen.add(rel)
        full = os.path.join(root, rel)
        if os.path.exists(full):
            out.append((rel, full))
    return out


def _bounded_input(root, rel):
    """Refuse an input path that is absolute or escapes the repository."""
    if os.path.isabs(rel):
        raise contracts.ContractError(
            "cannot prepare a review snapshot: input path %r is absolute, "
            "not repository-relative" % rel)
    real_root = os.path.realpath(root)
    real_full = os.path.realpath(os.path.join(root, rel))
    if real_full != real_root and not real_full.startswith(real_root + os.sep):
        raise contracts.ContractError(
            "cannot prepare a review snapshot: input path %r escapes the "
            "repository root" % rel)


def _artifact_rel(root, ticket_id, name):
    """The repo-relative path of a configured artifact; escapes are refused.

    A configured artifact value names a file inside the Ticket work directory
    (`mutate._artifact_path` joins it the same way). An absolute value, or one
    whose normalised path leaves that directory — a `..` component, a drive or
    UNC prefix — is refused rather than silently rewritten to a different file:
    the raw-byte capture must hash the artifact the Ticket actually names.
    """
    if os.path.isabs(name):
        raise contracts.ContractError(
            "cannot prepare a review snapshot: configured input %r is an "
            "absolute path, not a file inside the Ticket work directory"
            % name)
    rel = os.path.join(".ai", "work", ticket_id, name).replace("\\", "/")
    work_real = os.path.realpath(os.path.join(root, ".ai", "work", ticket_id))
    real = os.path.realpath(os.path.join(root, rel))
    if real == work_real or not real.startswith(work_real + os.sep):
        raise contracts.ContractError(
            "cannot prepare a review snapshot: configured input %r escapes "
            "the Ticket work directory" % name)
    return rel


def _copy_raw_inputs(root, clone_root, inputs):
    """Copy live input bytes to identical relative paths inside the clone."""
    for rel, full in inputs:
        dest = os.path.join(clone_root, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.islink(dest):
            os.unlink(dest)
        try:
            with open(full, "rb") as fh:
                raw = fh.read()
            with open(dest, "wb") as fh:
                fh.write(raw)
        except OSError as exc:
            raise contracts.ContractError(
                "cannot copy verification input %r into the snapshot: %s"
                % (rel, exc))


def _clone(root, clone_root, full_oid):
    """Independent clone (`--no-local --no-checkout`) checked out at the OID."""
    # No OSError handler here: `prepare` already shields the whole capture pass,
    # so a local translation would only pre-empt the pass's message. (This is
    # not a nesting hazard — `ContractError` is not an `OSError`.) Git is
    # reached by the drift and scope passes before this runs.
    proc = subprocess.run(
        ["git", "clone", "--no-local", "--no-checkout", "--", root,
         clone_root], capture_output=True)
    if proc.returncode != 0:
        raise contracts.ContractError(
            "cannot clone the repository for the snapshot: %s"
            % proc.stderr.decode("utf-8", "replace").strip())
    proc = _run_git(clone_root, ["checkout", "--detach", "--quiet", full_oid])
    if proc.returncode != 0:
        raise contracts.ContractError(
            "cannot check out the reviewed commit in the snapshot: %s"
            % proc.stderr.decode("utf-8", "replace").strip())
    # Independence is structural: no alternates file may exist.
    alternates = os.path.join(clone_root, ".git", "objects", "info",
                              "alternates")
    if os.path.exists(alternates):
        raise contracts.ContractError(
            "the snapshot clone shares object storage (alternates file "
            "present); refusing a non-independent clone")


def _write_context(output, manifest):
    """Persist meta/context.json exclusively from the supervisor."""
    meta_dir = os.path.join(output, _META_DIR)
    path = os.path.join(meta_dir, _CONTEXT_FILE)
    raw = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    tmp = path + ".tmp"
    try:
        # Inside the try, not before it: `exist_ok=True` still raises when
        # `meta` exists as a file, and an OSError escaping here would roll the
        # context back and then re-raise raw, reaching the CLI as a traceback.
        os.makedirs(meta_dir, exist_ok=True)
        with open(tmp, "wb") as fh:
            fh.write(raw)
        os.replace(tmp, path)
    except OSError as exc:
        raise contracts.ContractError(
            "cannot persist the snapshot manifest: %s" % exc)


def prepare(root, ticket_id, reviewed_commit, output):
    """Prepare an identified independent review snapshot; return the manifest.

    Creates the previously-absent `output` directory (outside the live
    worktree and Git metadata) holding `repo/` (independent clone checked out
    at the reviewed commit), `scratch/` (verifier outputs) and `meta/` with
    the persisted context manifest. Raises `contracts.ContractError`; any
    failure removes the whole context directory and never changes live files.
    """
    host_runtime.validate_host_path(root)
    host_runtime.validate_host_path(output)
    root = os.path.abspath(root)
    data = _load_state(root, ticket_id)
    _require_ready(root, ticket_id, data)
    _check_output_path(root, output)
    # Resolve the literal commit exactly once; the same OID drives the drift
    # checks, the checkout and the persisted identity.
    full_oid = review.resolve_commit(root, reviewed_commit)
    plan_ref = (data.get("source_artifacts") or {}).get("plan") or {}
    plan_path = (plan_ref.get("path") or "").replace("\\", "/")
    _require_clean_drift(root, ticket_id, full_oid, plan_path)

    execution_host = host_runtime.prepare_paths(root, output)

    with _io_contract(
            "cannot prepare a review snapshot: cannot read the in-scope "
            "repository content"):
        paths, kinds, ignore_rules = _scope_paths(root, ticket_id)
        live_entries = _manifest(root, paths)
        inputs = _configured_inputs(root, ticket_id, data)

    try:
        os.makedirs(output)
    except OSError as exc:
        raise contracts.ContractError(
            "cannot create the review snapshot output directory %r: %s"
            % (output, exc))
    try:
        with _io_contract(
                "cannot prepare a review snapshot: cannot capture the "
                "snapshot content"):
            clone_root = os.path.join(output, _REPO_DIR)
            _clone(root, clone_root, full_oid)
            _copy_raw_inputs(root, clone_root, inputs)
            os.makedirs(os.path.join(output, _SCRATCH_DIR), exist_ok=True)
            snapshot_entries = _manifest(clone_root, paths)
            # The post-capture drift check proves capture itself changed
            # nothing; it runs against the live repository, not the snapshot.
            _require_clean_drift(root, ticket_id, full_oid, plan_path)

        state_rel = os.path.join(".ai", "work", ticket_id,
                                 "state.yaml").replace("\\", "/")
        input_hashes = {}
        for rel, full in inputs:
            input_hashes[rel] = _input_sha(full, rel)
        plan_full = os.path.join(root, plan_path)
        manifest = {
            "format_version": FORMAT_VERSION,
            "ticket_id": ticket_id,
            "live_root": os.path.realpath(root),
            "execution_host": execution_host,
            "reviewed_commit": full_oid,
            "plan": {"path": plan_path,
                     "sha256": _input_sha(plan_full, plan_path)},
            "inputs": input_hashes,
            "state_sha256": input_hashes.get(state_rel),
            "scope": {
                "paths": {path: kinds[path] for path in paths},
                "excluded_records": sorted(_record_paths(ticket_id)),
                "ignore_rules": ignore_rules,
                "generated_exclusions": [],
            },
            "live_manifest": _canonical_sha(live_entries),
            "snapshot_manifest": _canonical_sha(snapshot_entries),
        }
        _write_context(output, manifest)
    except BaseException:
        # Any failure removes the whole context. Raising inside the handler
        # chains the original cause, so a rollback that itself fails reports
        # both rather than silently leaving a clone of the live repository.
        _remove_tree(output)
        raise
    return manifest


def assert_current(root, ticket_id, context_path):
    """Re-validate a persisted context against the live repository.

    Compares the Ticket, the live root, the reviewed commit, the live
    manifest identity, every captured input hash (including the live State
    hash) and the HARDEN-010 drift since the reviewed commit. Returns the
    persisted manifest; any disagreement raises `contracts.ContractError`.
    """
    root = os.path.abspath(root)
    path = os.path.join(context_path, _META_DIR, _CONTEXT_FILE)
    try:
        with open(path, "rb") as fh:
            manifest = json.loads(fh.read().decode("utf-8"))
    except (OSError, ValueError) as exc:
        raise contracts.ContractError(
            "cannot read the review context manifest %r: %s" % (path, exc))
    if not isinstance(manifest, dict) \
            or manifest.get("format_version") != FORMAT_VERSION:
        raise contracts.ContractError(
            "review context %r is not a format_version %d manifest"
            % (context_path, FORMAT_VERSION))
    if manifest.get("ticket_id") != ticket_id:
        raise contracts.ContractError(
            "review context belongs to ticket %r, not %r"
            % (manifest.get("ticket_id"), ticket_id))
    if "execution_host" in manifest \
            and manifest["execution_host"] != host_runtime.review_runtime():
        raise contracts.ContractError(
            "review-context-runtime-mismatch: prepared for %r, current %r; "
            "use the original coordinator/distro or prepare a fresh context" %
            (manifest["execution_host"], host_runtime.review_runtime()))
    if manifest.get("live_root") != os.path.realpath(root):
        raise contracts.ContractError(
            "review context live_root %r does not match %r"
            % (manifest.get("live_root"), os.path.realpath(root)))

    full_oid = review.resolve_commit(root, manifest.get("reviewed_commit"))
    scope = manifest.get("scope") or {}
    kinds = scope.get("paths") or {}
    scope_paths = sorted(kinds.keys())
    with _io_contract("cannot re-validate the review context"):
        live_entries = _manifest(root, scope_paths)
        if _canonical_sha(live_entries) != manifest.get("live_manifest"):
            raise contracts.ContractError(
                "the live repository no longer matches the captured review "
                "context baseline (live manifest changed; %s)"
                % _manifest_delta(live_entries, scope_paths))

        inputs = manifest.get("inputs") or {}
        for rel, expected in inputs.items():
            full = os.path.join(root, rel)
            if not os.path.exists(full):
                raise contracts.ContractError(
                    "captured verification input %r is missing from the live "
                    "repository" % rel)
            if _input_sha(full, rel) != expected:
                raise contracts.ContractError(
                    "captured verification input %r changed since the review "
                    "context was prepared" % rel)

        plan_path = ((manifest.get("plan") or {}).get("path") or "")
        _require_clean_drift(root, ticket_id, full_oid, plan_path)
    return manifest
