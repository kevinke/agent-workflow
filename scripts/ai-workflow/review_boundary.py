"""Enforced local process boundary and supervised execution receipts
(HARDEN-011 Task 2).

The reviewer's verification commands are launched *inside* one tested host
boundary, profile ``linux-bwrap-v1``, and every launch leaves a supervisor-
owned receipt the reviewer cannot forge or rewrite.

What the boundary is
--------------------
`bwrap` (bubblewrap) with ``--unshare-all --new-session --die-with-parent
--clearenv``, a fresh ``--tmpfs /`` root, private ``/proc`` and ``/dev``, a
read-only ``/usr`` plus the four merged-usr symlinks, a temporary ``/tmp`` that
is also ``HOME``, and exactly two writable scopes: the snapshot clone at
``/snapshot`` (the process cwd) and the verifier output area at ``/scratch``.
Nothing else from the host is mounted, so host sockets, credentials, ``/run``,
the live working tree and WSL interoperability are unreachable, and there is no
network. The child is spawned from an argument list — never a shell — with
``close_fds=True`` and ``stdin=subprocess.DEVNULL``.

The live tree is never mounted for a run
---------------------------------------
``run`` deliberately mounts **no** live path at all: that is how "live Git and
WSL interop unavailable" holds, because there is nothing to reach. The plan's
"read-only declared inputs" is satisfied differently in this profile — Task 1
already copied every declared input (the registered Plan and the configured
verification artifacts) into the snapshot clone by raw bytes, so the read-only
copy *is* ``repo/``'s content; the inputs stay pinned by identity in the
supervisor manifest, and drift away from that pinned identity is detected and
refuses a further baseline run. A reviewer may therefore edit the snapshot
(``/snapshot`` is writable by design) but cannot reach the live repository, the
live ``.git``, or the supervisor's own ``meta/`` records.

Receipts are built from supervisor-side SHA-256 of raw bytes
-----------------------------------------------------------
A clone prepared by Windows Git with ``core.autocrlf`` reads as ``M code.py``
to Linux Git inside the sandbox: the two hosts disagree about line endings
without any real change. Every identity, hash and residual-change record here is
therefore computed by the supervisor from raw bytes on the host side, never from
``git status`` inside the sandbox (see ``review_snapshot`` Task 1, same rule).

One explicit host path translator
---------------------------------
``linux_path`` is the only path translation in this module: a Windows
``C:\\Users\\...\\Temp\\x`` becomes ``/mnt/c/Users/.../Temp/x`` for the bind
source. MSYS/Git-Bash mangling is never relied on — it is a shell concern, and
this module never uses a shell. Note that ``wsl.exe -- <argv>`` re-parses argv
through the default Linux shell; this module uses ``wsl.exe --exec`` so the
argv list reaches ``bwrap`` verbatim and no reviewer-supplied word can be
reinterpreted by a shell.

What is proven, and what is not
------------------------------
``preflight`` proves the profile with its own disposable protected sentinel
(a source file, a test file, a fixture, a config file and a fake ``.git/index``)
mounted read-only at ``/live``, and removes it again; it never probes real live
files. A blocker — missing ``bwrap``, denied namespace creation, unsupported
runtime layout, unrepresentable context layout, unapproved mount root, shared
writable Git metadata — always raises ``contracts.ContractError` and produces
**no receipt at all** and no fallback launch. A nonzero command exit is recorded
as that command's own status, never as a boundary success or failure.

This proves a *local command* boundary on the hosts it actually ran on (recorded
in every receipt as ``host`` plus ``boundary.sandbox_host``). It claims nothing
about a Windows-native sandbox, Codex Desktop or any model/Harness adapter:
those stay unsupported until their own host write restriction is demonstrated
through this same entry point.

Python 3 stdlib only; no shell, no new permission service, no model launcher.
"""

import datetime
import errno
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid

import contracts
import review_snapshot

__all__ = ["preflight", "run", "PROFILE", "KINDS", "launch", "linux_path",
           "supervisor_host"]

FORMAT_VERSION = 1
PROFILE = "linux-bwrap-v1"
KINDS = ("baseline", "probe")

# The frozen in-sandbox layout.
SANDBOX_ROOT = "/"
SANDBOX_SNAPSHOT = "/snapshot"
SANDBOX_SCRATCH = "/scratch"
SANDBOX_LIVE = "/live"
SANDBOX_TMP = "/tmp"
SANDBOX_CWD = SANDBOX_SNAPSHOT

# Context layout written by Task 1 (`review_snapshot`); private names repeated
# here so this module never has to reach into another module's internals.
_REPO_DIR = "repo"
_SCRATCH_DIR = "scratch"
_META_DIR = "meta"
_RUNS_DIR = "runs"
_CONTEXT_FILE = "context.json"
_PREFLIGHT_FILE = "preflight.json"
_BASELINE_FILE = "baseline.json"

# The disposable protected sentinel preflight builds for itself, under the
# supervisor-owned meta area. It is created, probed and removed by preflight
# alone; no real live file is ever used as a probe target.
SENTINEL_DIR = "preflight-sentinel"
SENTINEL_FILES = ("source.py", "test_source.py", "fixture.json", "config.toml",
                  ".git/index")
_SENTINEL_CONTENT = {
    "source.py": b"def sentinel():\n    return 42\n",
    "test_source.py": b"def test_sentinel():\n    assert sentinel() == 42\n",
    "fixture.json": b'{\n  "sentinel": true,\n  "value": 42\n}\n',
    "config.toml": b"[sentinel]\nenabled = true\n",
    ".git/index": b"DIRC\x00\x00\x00\x02fake index for the boundary probe\n",
}

# A write denied with one of these errnos is a denial of the *privilege*. Any
# other failure (ENOENT above all) means the path was not there to be denied,
# which is not evidence of a boundary, so it fails closed too.
# The verifier command is not started by a shell, so `run` cannot otherwise tell
# "the boundary refused to set up" from "the verifier ran and failed quietly":
# both can leave a nonzero status and empty output. The sandbox therefore writes
# this marker itself, from inside, immediately before `exec`ing the reviewer's
# command; `run` clears it first, so a stale one cannot mask a non-start.
_START_MARKER = ".boundary-started"
_START_SCRIPT = 't="$1"; shift; : > "$t"; exec "$@"'

DENIAL_ERRNOS = frozenset({errno.EACCES, errno.EPERM, errno.EROFS})
# A rename or a hard link that leaves one mount for another must be refused
# across the mount boundary; anything else would be an escape out of `/live`.
# EXDEV is the correct denial signature for a cross-mount escape, so both
# syscalls are judged against it rather than against the privilege errnos.
CROSS_MOUNT_RENAME_ERRNOS = frozenset({errno.EXDEV})
CROSS_MOUNT_SYSCALLS = frozenset({"rename", "link"})

# The scopes the profile promises are writable. A report that cannot prove all
# of them is not a boundary, it is a sandbox that cannot do the reviewer's work.
WRITABLE_SCOPES = ("/snapshot", "/scratch", "/tmp", "$HOME")

# Linux errno numbers as the sandbox reports them, written out because the
# supervisor may be Windows Python reaching `bwrap` through `wsl.exe`: there
# `errno.ENETUNREACH` is 10051, which would never match the 101 a Linux sandbox
# actually reports, and a denial would be refused as "not proof". The write
# errnos above happen to carry the same value on both platforms; the network
# ones do not, so they are stated as Linux values and never as host constants.
LINUX_NETWORK_ERRNOS = {"ENETUNREACH": 101, "EHOSTUNREACH": 113,
                        "ECONNREFUSED": 111, "ECONNRESET": 104,
                        "ETIMEDOUT": 110}

# A network *denial* is only proven by an errno that means "there is no network
# to reach": `--unshare-all` leaves the namespace with no interface at all, so
# `connect()` answers ENETUNREACH, and a permission filter answers EPERM/EACCES.
# Every other failure is refused as evidence, because each of them is also what
# a boundary *with* network produces:
#   * a timeout carries no errno at all, and is exactly what a shared network
#     namespace reports for a firewalled destination (measured on this host);
#   * ECONNREFUSED / ECONNRESET mean something on the other end answered;
#   * EHOSTUNREACH means a live route existed and a router rejected the packet,
#     which is what an iptables `REJECT --reject-with icmp-host-unreachable`
#     rule on a *connected* host looks like — deliberately not accepted;
#   * `EAI_*` name-resolution codes are negative pseudo-errnos that also occur
#     when a resolver is present but broken.
NO_NETWORK_ERRNOS = frozenset((errno.EPERM, errno.EACCES,
                               LINUX_NETWORK_ERRNOS["ENETUNREACH"]))
# The attempts the probe must make: name resolution *and* an outbound connect.
# Both are required, because a report that skipped one proves nothing about it,
# and only the connect's own errno can prove the network is absent (a resolver
# failure is ambiguous: glibc answers with a negative `EAI_*` pseudo-errno both
# when there is no network and when there is a network and a broken resolver).
NETWORK_ATTEMPTS = ("dns", "connect")
# The attempt whose failure alone can prove the network is gone: it needs no
# resolver and no name service, so it is the only unambiguous observation.
NETWORK_PROOF_ATTEMPT = "connect"

# The only environment the sandboxed process may see. `--clearenv` removes
# everything inherited; `LC_CTYPE` and `PWD` are set by bwrap itself, and no
# `GIT_*` override may survive into the verifier (the plan's "clear inherited
# environment, Git overrides and descriptors").
ALLOWED_ENV_KEYS = frozenset({"HOME", "LC_CTYPE", "PATH", "PWD"})

# ---------------------------------------------------------------------------
# Named blockers. Each one is greppable and appears in the raised message.
# ---------------------------------------------------------------------------
BWRAP_EXECUTABLE_NOT_FOUND = "bwrap-executable-not-found"
NAMESPACE_CREATION_DENIED = "namespace-creation-denied"
UNSUPPORTED_RUNTIME_LAYOUT = "unsupported-runtime-layout"
CONTEXT_LAYOUT_NOT_REPRESENTABLE = "context-layout-not-representable"
UNAPPROVED_MOUNT_ROOT = "unapproved-mount-root"
SHARED_WRITABLE_GIT_METADATA = "shared-writable-git-metadata"
SENTINEL_ROOT_NOT_ISOLATED = "protected-sentinel-not-supervisor-owned"
BASELINE_IDENTITY_DRIFT = "baseline-identity-drift"
PREPARATION_BASELINE_ALTERED = "preparation-baseline-altered"
LIVE_WRITE_ALLOWED = "boundary-permits-live-writes"
DENIAL_UNVERIFIED = "boundary-denial-unverified"
SENTINEL_CHANGED = "protected-sentinel-changed"
WRITABLE_SCOPE_UNAVAILABLE = "declared-writable-scope-unavailable"
HOST_SCOPE_REACHABLE = "host-scope-reachable-inside-boundary"
NETWORK_PERMITTED = "boundary-permits-network"
ENVIRONMENT_NOT_SANITIZED = "inherited-environment-not-cleared"
PROBE_REPORT_UNREADABLE = "boundary-probe-report-unreadable"
BOUNDARY_SETUP_FAILED = "boundary-setup-failed"
BOUNDARY_NEVER_STARTED = "boundary-never-started"

_BWRAP = "bwrap"
_GLOBAL_FLAGS = ("--unshare-all", "--new-session", "--die-with-parent",
                 "--clearenv")
_RUNTIME_RO_BINDS = ("/usr",)
_RUNTIME_SYMLINKS = (("usr/bin", "/bin"), ("usr/lib", "/lib"),
                     ("usr/lib64", "/lib64"), ("usr/sbin", "/sbin"))
_RUNTIME_TMPFS = (SANDBOX_ROOT, SANDBOX_TMP)
_RUNTIME_DEVICE_DIRS = ("/dev", "/proc")
_SANDBOX_ENV = (("HOME", SANDBOX_TMP), ("PATH", "/usr/bin:/bin"))
# Every destination the profile is allowed to have mounted, and the only
# non-context sources it may mount. Anything else is an unapproved mount root.
_ALLOWED_DESTINATIONS = frozenset(
    (_RUNTIME_TMPFS + _RUNTIME_DEVICE_DIRS + _RUNTIME_RO_BINDS
     + tuple(link for _, link in _RUNTIME_SYMLINKS)
     + (SANDBOX_SNAPSHOT, SANDBOX_SCRATCH, SANDBOX_LIVE)))
_RUNTIME_SOURCES = frozenset(_RUNTIME_RO_BINDS
                            + tuple(target for target, _ in _RUNTIME_SYMLINKS))
_MOUNT_OPTIONS = ("--bind", "--ro-bind", "--dev-bind", "--symlink")


# ---------------------------------------------------------------------------
# Host adapters: one argv list, never a shell
# ---------------------------------------------------------------------------

def supervisor_host():
    """The coordinator's own platform, recorded plainly on every receipt."""
    return "%s %s (%s)" % (platform.system(), platform.release(),
                           platform.machine())


def linux_path(path):
    """Translate one host path into the Linux sandbox's view of it.

    This is the module's only path translation, used for every bind source.
    Windows `C:\\Users\\...\\Temp\\x` is `/mnt/c/Users/.../Temp/x` for
    `wsl.exe`; a POSIX supervisor path is already correct. Nothing here relies
    on MSYS or Git-Bash path mangling, which is a shell concern — this module
    never goes through a shell. A path that cannot be expressed (a UNC share)
    is refused rather than passed through untranslated.
    """
    absolute = os.path.abspath(path)
    if os.name != "nt":
        return absolute
    normalized = absolute.replace("\\", "/")
    if len(normalized) >= 3 and normalized[1] == ":" \
            and normalized[0].isalpha() and normalized[2] == "/":
        return "/mnt/%s%s" % (normalized[0].lower(), normalized[2:])
    if normalized.startswith("//"):
        raise contracts.ContractError(
            "%s: the review context path %r is on a UNC share, which profile "
            "%s cannot express as a bind source"
            % (CONTEXT_LAYOUT_NOT_REPRESENTABLE, absolute, PROFILE))
    raise contracts.ContractError(
        "%s: cannot translate the host path %r into a Linux bind source for "
        "profile %s" % (CONTEXT_LAYOUT_NOT_REPRESENTABLE, absolute, PROFILE))


def _wsl_distro():
    """Optional distro override; the WSL default is used when it is unset."""
    return os.environ.get("AI_WORKFLOW_BWRAP_DISTRO") or None


def launcher_prefix():
    """The argv head that reaches `bwrap` on this supervisor host.

    `--exec` (not `--`) matters: `wsl.exe -- <argv>` hands the joined command
    line to the default Linux shell, which would re-split and reinterpret the
    reviewer's argv. `wsl.exe --exec` starts the binary directly from the
    argument list.
    """
    if os.name == "nt":
        distro = _wsl_distro()
        if distro:
            return ["wsl.exe", "-d", distro, "--exec"]
        return ["wsl.exe", "--exec"]
    if sys.platform.startswith("linux"):
        return []
    raise contracts.ContractError(
        "%s: profile %s needs a Linux sandbox host; this supervisor is %s and "
        "no boundary was demonstrated for it" % (UNSUPPORTED_RUNTIME_LAYOUT,
                                                 PROFILE, supervisor_host()))


def _launcher_label():
    prefix = launcher_prefix()
    return " ".join(prefix + [_BWRAP]) if prefix else "%s (same host)" % _BWRAP


def _boundary_argv(bwrap_args, inner_argv=None):
    """Assemble the single argv list that starts the boundary.

    `inner_argv` follows a literal `--`, so a reviewer argument is never parsed
    as a bwrap option.
    """
    command = launcher_prefix() + [_BWRAP] + list(bwrap_args)
    if inner_argv is not None:
        command += ["--"] + list(inner_argv)
    return command


def launch(command, stdout_path=None, stderr_path=None):
    """Start `command` as an argument list and return its exit status.

    This is the module's launcher seam: the focused tests replace it to
    simulate a missing executable or a denied namespace without touching any
    host setting. There is no shell anywhere, sibling descriptors are not
    inherited, stdin is not interactive, and the captured streams are written
    straight into the destination file descriptors.
    """
    out_fd = None
    err_fd = None
    try:
        if stdout_path is None:
            out_fd = subprocess.DEVNULL
        else:
            out_fd = os.open(stdout_path,
                             os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        if stderr_path is None:
            err_fd = subprocess.DEVNULL
        else:
            err_fd = os.open(stderr_path,
                             os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        proc = subprocess.Popen(list(command), stdout=out_fd, stderr=err_fd,
                                stdin=subprocess.DEVNULL, close_fds=True)
    except OSError as exc:
        # `wsl.exe` itself, or `bwrap` inside the distro, is not reachable.
        raise _LaunchUnavailable(exc)
    finally:
        for fd in (out_fd, err_fd):
            if fd not in (None, subprocess.DEVNULL):
                try:
                    os.close(fd)
                except OSError:
                    pass
    return proc.wait()


class _LaunchUnavailable(OSError):
    """The launcher could not start the boundary binary at all."""


def classify_boundary_failure(returncode, stdout_bytes, stderr_text):
    """Name a boundary-level launch failure, or `None` if the command ran.

    Only bwrap's own setup marker counts: a nonzero status with *every* stderr
    line owned by bwrap and nothing at all captured from the inner process. A
    verifier that merely fails is not a boundary failure — its exit status is
    recorded as-is, which is exactly what `test_receipts_preserve_failures...`
    depends on.
    """
    if returncode == 0 or stdout_bytes:
        return None
    lines = [line for line in (stderr_text or "").splitlines() if line.strip()]
    if not lines or not all(line.startswith("bwrap:") for line in lines):
        return None
    text = "\n".join(lines).lower()
    denied = ("uid map" in text or "unshare" in text or "permission denied"
              in text or "operation not permitted" in text
              or "no user namespaces" in text)
    if denied:
        return NAMESPACE_CREATION_DENIED
    if "source path" in text or "no such file" in text or "tmpfs" in text \
            or "can't create" in text or "mount" in text:
        return UNSUPPORTED_RUNTIME_LAYOUT
    return BOUNDARY_SETUP_FAILED


def _unavailable_marker_failure(stderr_text):
    """A launcher that could not even exec `bwrap` inside the host."""
    text = (stderr_text or "").lower()
    if "execvpe(" in text or "command not found" in text \
            or "no such file or directory" in text:
        return BWRAP_EXECUTABLE_NOT_FOUND
    return None


def _blocker(named, detail):
    """A named blocker: `ContractError`, never a weakened continuation."""
    return contracts.ContractError(
        "%s: profile %s cannot enforce the boundary here — %s"
        % (named, PROFILE, detail))


def _require(named, condition, detail):
    if not condition:
        raise _blocker(named, detail)


# ---------------------------------------------------------------------------
# Context layout and mount roots
# ---------------------------------------------------------------------------

def _comparable(path):
    """A path in a form containment can be compared on this platform.

    `os.path.realpath` on Windows yields backslash separators, while a `gitdir:`
    pointer or a translated bind source may use forward slashes; on POSIX a
    backslash is an ordinary filename character and is left alone.
    """
    normalized = path.replace("\\", "/") if os.name == "nt" else path
    return normalized.rstrip("/") or "/"


def _within(child, parent):
    """True when `child` is `parent` or below it (both already resolved)."""
    child = _comparable(child)
    parent = _comparable(parent)
    return child == parent or child.startswith(parent + "/")


def _meta_dir(context_path):
    return os.path.join(context_path, _META_DIR)


def _sentinel_root(context_path):
    """Where preflight builds its own disposable protected sentinel.

    Always inside the supervisor-owned meta area, never inside a real tree.
    """
    return os.path.join(_meta_dir(context_path), SENTINEL_DIR)


def _mount_roots(context_path):
    """Canonical (realpath) roots for `repo`, `scratch` and `meta`.

    Both sides are resolved: a context whose root or layout directory is a
    symlink, or whose directory resolves outside `context_path`, is not
    representable as the frozen mount set and is refused.
    """
    if not context_path:
        raise _blocker(CONTEXT_LAYOUT_NOT_REPRESENTABLE,
                       "no review context path was given")
    if os.path.islink(context_path):
        raise _blocker(CONTEXT_LAYOUT_NOT_REPRESENTABLE,
                       "the review context root %r is a symlink" % context_path)
    if not os.path.isdir(context_path):
        raise _blocker(CONTEXT_LAYOUT_NOT_REPRESENTABLE,
                       "the review context directory %r does not exist"
                       % context_path)
    real = os.path.realpath(os.path.abspath(context_path))
    roots = {}
    for name in (_REPO_DIR, _SCRATCH_DIR, _META_DIR):
        full = os.path.join(real, name)
        if os.path.islink(full):
            raise _blocker(
                CONTEXT_LAYOUT_NOT_REPRESENTABLE,
                "%s/%s is a symlink; a linked or escaping directory is not "
                "isolation, so it is never followed as a mount root"
                % (context_path, name))
        if not os.path.isdir(full):
            raise _blocker(
                CONTEXT_LAYOUT_NOT_REPRESENTABLE,
                "%s/%s is missing; the review context layout must hold %s, "
                "%s and %s" % (context_path, name, _REPO_DIR, _SCRATCH_DIR,
                               _META_DIR))
        resolved = os.path.realpath(full)
        if not _within(resolved, real):
            raise _blocker(
                CONTEXT_LAYOUT_NOT_REPRESENTABLE,
                "%s/%s resolves to %r, outside the review context %r"
                % (context_path, name, resolved, real))
        roots[name] = {"host": resolved,
                       "sandbox_source": linux_path(resolved)}
    return real, roots


def _require_independent_git(roots):
    """Refuse a snapshot whose Git metadata reaches outside the snapshot.

    A copy that shares live object storage, a `gitdir:` pointer to the live
    repository, a linked worktree or a symlinked `.git` is writable shared
    state, not isolation: a `git` run inside the sandbox would move live
    metadata. This re-checks at execution time what Task 1 established at
    preparation, because the context on disk can be replaced in between.
    """
    repo = roots[_REPO_DIR]["host"]
    git_path = os.path.join(repo, ".git")
    if os.path.islink(git_path):
        raise _blocker(
            SHARED_WRITABLE_GIT_METADATA,
            "the snapshot's `.git` is a symlink to %r; a linked or shared Git "
            "directory is writable by the sandbox and is not isolation"
            % os.readlink(git_path))
    if os.path.isdir(git_path):
        git_dir = os.path.realpath(git_path)
    elif os.path.isfile(git_path):
        with open(git_path, "rb") as fh:
            raw = fh.read().decode("utf-8", "replace").strip()
        pointer = raw.split("gitdir:", 1)[1].strip() if "gitdir:" in raw else ""
        if not pointer:
            raise _blocker(
                CONTEXT_LAYOUT_NOT_REPRESENTABLE,
                "the snapshot's `.git` is neither a repository directory nor "
                "a readable `gitdir:` pointer")
        # A pointer is host-absolute when it names a root or a drive, and it is
        # only resolvable when this supervisor can actually read that form. A
        # Windows-style pointer under a Linux supervisor (or the reverse) would
        # otherwise resolve to a path inside the snapshot and look independent,
        # so it is refused rather than guessed at.
        host_absolute = (pointer.startswith(("/", "\\\\", "//"))
                         or (len(pointer) >= 2 and pointer[0].isalpha()
                             and pointer[1] == ":"))
        if host_absolute and not os.path.isabs(pointer):
            raise _blocker(
                SHARED_WRITABLE_GIT_METADATA,
                "the snapshot's `gitdir:` pointer %r names an absolute path in "
                "a form this supervisor cannot resolve; the snapshot's Git "
                "directory cannot be shown to be independent" % pointer)
        candidate = pointer if host_absolute else os.path.join(repo, pointer)
        git_dir = os.path.realpath(candidate)
    else:
        raise _blocker(
            CONTEXT_LAYOUT_NOT_REPRESENTABLE,
            "the snapshot clone has no Git metadata at %s" % git_path)
    if not _within(git_dir, repo):
        raise _blocker(
            SHARED_WRITABLE_GIT_METADATA,
            "the snapshot's Git directory resolves to %r, outside the snapshot "
            "root %r; live Git metadata would be writable from inside the "
            "boundary" % (git_dir, repo))
    alternates = os.path.join(git_dir, "objects", "info", "alternates")
    if os.path.exists(alternates):
        raise _blocker(
            SHARED_WRITABLE_GIT_METADATA,
            "the snapshot clone shares object storage (%s exists); a clone "
            "with alternates is not independent" % alternates)
    return git_dir


def _extra_bind_specs(context_path):
    """Hook for the profile's mount set. It adds nothing.

    Frozen: every bind the boundary may make is derived from the context and
    the runtime allowlist below. The focused tests inject a foreign bind here
    to prove the mount allowlist rejects it instead of launching it.
    """
    return []


def _bind_specs(roots, context_path, live_source=None):
    """The frozen mount list as structured (option, source, destination).

    `meta` is never a mount: the supervisor's manifest, receipts and baseline
    record stay out of the verifier's reach entirely. `live_source` is mounted
    read-only by `preflight` only, and only ever as its own sentinel.
    """
    specs = [("--tmpfs", None, SANDBOX_ROOT)]
    specs += [("--dev", None, "/dev"), ("--proc", None, "/proc")]
    specs += [("--ro-bind", source, source) for source in _RUNTIME_RO_BINDS]
    specs += [("--symlink", target, link) for target, link in _RUNTIME_SYMLINKS]
    specs += [("--tmpfs", None, SANDBOX_TMP)]
    specs += [("--bind", roots[_REPO_DIR]["sandbox_source"], SANDBOX_SNAPSHOT),
              ("--bind", roots[_SCRATCH_DIR]["sandbox_source"],
               SANDBOX_SCRATCH)]
    if live_source is not None:
        specs.append(("--ro-bind", live_source, SANDBOX_LIVE))
    specs += [tuple(spec) for spec in _extra_bind_specs(context_path)]
    return specs


def _verify_bind_specs(specs, roots, live_source=None):
    """Every mount destination and source must be on the profile allowlist."""
    approved = set(_RUNTIME_SOURCES)
    approved.add(roots[_REPO_DIR]["sandbox_source"])
    approved.add(roots[_SCRATCH_DIR]["sandbox_source"])
    if live_source is not None:
        approved.add(live_source)
    for option, source, destination in specs:
        if destination not in _ALLOWED_DESTINATIONS:
            raise _blocker(
                UNAPPROVED_MOUNT_ROOT,
                "the mount set asks for destination %r, which profile %s does "
                "not permit" % (destination, PROFILE))
        if option not in _MOUNT_OPTIONS:
            continue
        if source is None:
            raise _blocker(UNAPPROVED_MOUNT_ROOT,
                           "%s was requested without a source" % option)
        if option == "--dev-bind" and destination != "/dev":
            raise _blocker(UNAPPROVED_MOUNT_ROOT,
                           "--dev-bind is only allowed for /dev")
        if source not in approved:
            raise _blocker(
                UNAPPROVED_MOUNT_ROOT,
                "%s asks to mount %r at %r; only the review context roots and "
                "the runtime paths %s may be mounted under profile %s"
                % (option, source, destination,
                   ", ".join(sorted(_RUNTIME_SOURCES)), PROFILE))


def _mount_args(specs):
    """Flatten structured specs back into bwrap argv."""
    args = []
    for option, source, destination in specs:
        if source is None:
            args += [option, destination]
        else:
            args += [option, source, destination]
    return args


def _runtime_args():
    args = list(_GLOBAL_FLAGS)
    for key, value in _SANDBOX_ENV:
        args += ["--setenv", key, value]
    args += ["--chdir", SANDBOX_CWD]
    return args


def _boundary_command(roots, context_path, inner_argv, live_source=None,
                      start_marker=False):
    specs = _bind_specs(roots, context_path, live_source=live_source)
    _verify_bind_specs(specs, roots, live_source=live_source)
    argv = list(inner_argv)
    if start_marker:
        # `sh -c` here takes the reviewer's command positionally: `$1` is the
        # marker path, and after `shift` `"$@"` is the reviewer's own argv, so
        # no reviewer content is ever re-parsed as shell syntax. `exec` keeps
        # the verifier's exit status and signal death as the reported status.
        argv = ["sh", "-c", _START_SCRIPT, "review-boundary",
                "%s/%s" % (SANDBOX_SCRATCH, _START_MARKER)] + argv
    return _boundary_argv(_runtime_args() + _mount_args(specs), argv)


# ---------------------------------------------------------------------------
# Supervisor-side identity, residual change and JSON helpers
# ---------------------------------------------------------------------------

def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _read_json(path):
    with open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def _write_json(path, payload):
    raw = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as fh:
            fh.write(raw)
        os.replace(tmp, path)
    except OSError as exc:
        raise contracts.ContractError("cannot persist %r: %s" % (path, exc))


def _sha_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _read_context(context_path):
    path = os.path.join(_meta_dir(context_path), _CONTEXT_FILE)
    context = _read_json(path)
    if not isinstance(context, dict) \
            or context.get("format_version") != review_snapshot.FORMAT_VERSION:
        raise contracts.ContractError(
            "%s is not a format_version %d review context manifest"
            % (path, review_snapshot.FORMAT_VERSION))
    for key in ("ticket_id", "live_root", "scope", "live_manifest",
                "snapshot_manifest", "inputs"):
        if key not in context:
            raise contracts.ContractError(
                "review context %s is missing %r" % (path, key))
    return context


def _pinned_paths(context):
    """The pinned scope: Task 1's fixed scope plus the declared input paths.

    Pinned on purpose: a reviewer creating files under `scratch/` must not be
    able to move a baseline identity, and a reviewer editing tracked snapshot
    code or a captured verification input must not be able to slip past one.
    """
    scope = context.get("scope") or {}
    paths = set(scope.get("paths") or {})
    paths.update(context.get("inputs") or {})
    plan_path = (context.get("plan") or {}).get("path")
    if plan_path:
        paths.add(plan_path)
    return sorted(paths)


def _scope_identity(entries, context):
    """The code-scope part of a pinned identity, comparable to Task 1's capture.

    The pinned set is deliberately wider than Task 1's scope (it also covers the
    captured verification inputs), so the preparation baseline can only be
    compared over the paths `prepare` itself hashed.
    """
    names = set(((context.get("scope") or {}).get("paths")) or {})
    return review_snapshot._canonical_sha(
        {path: entry for path, entry in entries.items() if path in names})


def _pinned_identity(root, context):
    """(entries, canonical-JSON SHA-256) over the pinned scope, raw bytes."""
    paths = _pinned_paths(context)
    entries = review_snapshot._manifest(root, paths)
    return entries, review_snapshot._canonical_sha(entries)


def _entry_changes(before, after):
    """Pinned paths whose content, kind or mode differs."""
    return sorted(path for path in set(before) & set(after)
                  if before[path] != after[path])


def _enumerate_tree(repo):
    """Repository-relative forward-slash paths present under the snapshot.

    `.git` is excluded: transient snapshot Git state is the reviewer's own
    working area and is not a residual *source* change. Symlinked directories
    are recorded as paths, never followed.
    """
    found = set()
    for dirpath, dirnames, filenames in os.walk(repo, followlinks=False):
        relative = os.path.relpath(dirpath, repo).replace("\\", "/")
        if relative == ".git" or relative.startswith(".git/"):
            dirnames[:] = []
            continue
        keep = []
        for name in dirnames:
            full = os.path.join(dirpath, name)
            rel = os.path.join(relative, name).replace("\\", "/") \
                if relative != "." else name
            if os.path.islink(full):
                found.add(rel)
            else:
                keep.append(name)
        dirnames[:] = keep
        for name in filenames:
            rel = os.path.join(relative, name).replace("\\", "/") \
                if relative != "." else name
            found.add(rel)
    return found


# ---------------------------------------------------------------------------
# bwrap availability and version
# ---------------------------------------------------------------------------

def _probe_captured(command):
    """Run a boundary probe with output captured to supervisor temp files."""
    with tempfile.TemporaryDirectory(prefix="ai-workflow-boundary-") as tmp:
        out = os.path.join(tmp, "stdout")
        err = os.path.join(tmp, "stderr")
        try:
            returncode = launch(command, out, err)
        except _LaunchUnavailable as exc:
            raise _blocker(BWRAP_EXECUTABLE_NOT_FOUND,
                           "the host could not start the boundary binary: %s"
                           % exc)
        except OSError as exc:
            raise _blocker(BWRAP_EXECUTABLE_NOT_FOUND,
                           "the host could not start the boundary binary: %s"
                           % exc)
        stdout_bytes = _read_or_empty(out)
        stderr_text = _read_or_empty(err).decode("utf-8", "replace")
    return returncode, stdout_bytes, stderr_text


def _read_or_empty(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return b""


def _bwrap_version():
    """`bwrap --version` through the launcher seam, or a named blocker.

    Failing closed here is what keeps "absent binary" from ever reading as
    support: no caller may proceed to a launch without a version string.
    """
    returncode, stdout_bytes, stderr_text = _probe_captured(
        launcher_prefix() + [_BWRAP, "--version"])
    named = classify_boundary_failure(returncode, stdout_bytes, stderr_text) \
        or _unavailable_marker_failure(stderr_text)
    if named:
        raise _blocker(named, stderr_text.strip() or "bwrap --version failed")
    if returncode != 0:
        raise _blocker(UNSUPPORTED_RUNTIME_LAYOUT,
                       "bwrap --version exited %d: %s"
                       % (returncode, stderr_text.strip()))
    text = stdout_bytes.decode("utf-8", "replace").strip()
    if not text:
        raise _blocker(UNSUPPORTED_RUNTIME_LAYOUT,
                       "bwrap --version reported nothing")
    return text


def _probe_argv(proof_prefix, absent_paths):
    """The sandboxed probe program as an argv tail (no shell, one `-c`)."""
    return ["/usr/bin/env", "python3", "-c",
            _probe_script(proof_prefix, absent_paths)]


# ---------------------------------------------------------------------------
# The in-sandbox boundary probe
# ---------------------------------------------------------------------------

# Written to the sandboxed interpreter as a `-c` program: it attempts every
# forbidden operation against the read-only sentinel mounted at `/live` from
# inside the same process, proves each declared writable scope is genuinely
# writable, and reports what it observed as one JSON line. The supervisor does
# not trust the report on its own: it re-enumerates the sentinel afterwards, so
# a sandbox that claims denial while having written would still be caught.
_PROBE_TEMPLATE = r'''
import json, os, socket, sys, platform

config = json.loads(__CONFIG__)
LIVE = config["live"]
SENTINELS = config["sentinels"]
PROOF = config["proof_prefix"]

def attempt(name, syscall, path, call):
    try:
        call()
        return {"name": name, "syscall": syscall, "path": path,
                "allowed": True, "errno": None}
    except OSError as exc:
        return {"name": name, "syscall": syscall, "path": path,
                "allowed": False, "errno": exc.errno}

def as_write(path):
    def run():
        with open(path, "wb") as fh:
            fh.write(b"overwritten by the verifier\n")
    return run

def as_append(path):
    def run():
        with open(path, "ab") as fh:
            fh.write(b"appended by the verifier\n")
    return run

def as_truncate(path):
    def run():
        with open(path, "r+b") as fh:
            fh.truncate(0)
    return run

def as_unlink(path):
    return lambda: os.unlink(path)

def as_rename(src, dst):
    return lambda: os.rename(src, dst)

attempts = []
for rel in SENTINELS:
    path = LIVE + "/" + rel
    slug = rel.replace("/", ".").replace(".", "_")
    attempts.append(attempt("overwrite-" + slug, "open-write", path,
                            as_write(path)))
for rel in SENTINELS:
    path = LIVE + "/" + rel
    slug = rel.replace("/", ".").replace(".", "_")
    attempts.append(attempt("append-" + slug, "open-append", path,
                            as_append(path)))
for rel in SENTINELS:
    path = LIVE + "/" + rel
    slug = rel.replace("/", ".").replace(".", "_")
    attempts.append(attempt("truncate-" + slug, "open-truncate", path,
                            as_truncate(path)))
attempts.append(attempt("create-new-file", "open-write",
                        LIVE + "/injected-source.py",
                        as_write(LIVE + "/injected-source.py")))
attempts.append(attempt("mkdir-live", "mkdir", LIVE + "/injected-dir",
                        lambda: os.mkdir(LIVE + "/injected-dir")))
attempts.append(attempt("makedirs-live", "mkdir",
                        LIVE + "/injected-dir/deep",
                        lambda: os.makedirs(LIVE + "/injected-dir/deep")))
attempts.append(attempt("chmod-sentinel", "chmod", LIVE + "/" + SENTINELS[0],
                        lambda: os.chmod(LIVE + "/" + SENTINELS[0], 0o777)))
attempts.append(attempt("symlink-into-snapshot", "symlink", LIVE + "/escape",
                        lambda: os.symlink("/snapshot", LIVE + "/escape")))
attempts.append(attempt("hardlink-into-scratch", "link",
                        LIVE + "/" + SENTINELS[0],
                        lambda: os.link(LIVE + "/" + SENTINELS[0],
                                        "/scratch/hardlinked")))
attempts.append(attempt("rename-into-snapshot", "rename",
                        LIVE + "/" + SENTINELS[0],
                        as_rename(LIVE + "/" + SENTINELS[0],
                                  "/snapshot/stolen-by-rename")))
attempts.append(attempt("rename-into-scratch", "rename",
                        LIVE + "/" + SENTINELS[1],
                        as_rename(LIVE + "/" + SENTINELS[1],
                                  "/scratch/stolen-by-rename")))
attempts.append(attempt("rename-into-tmp", "rename",
                        LIVE + "/" + SENTINELS[2],
                        as_rename(LIVE + "/" + SENTINELS[2],
                                  "/tmp/stolen-by-rename")))
for rel in SENTINELS:
    path = LIVE + "/" + rel
    slug = rel.replace("/", ".").replace(".", "_")
    attempts.append(attempt("unlink-" + slug, "unlink", path,
                            as_unlink(path)))

writable = {}
for label, base in (("/snapshot", "/snapshot"), ("/scratch", "/scratch"),
                    ("/tmp", "/tmp"),
                    ("$HOME", os.environ.get("HOME") or "/tmp")):
    target = base + "/" + PROOF
    try:
        with open(target, "w") as fh:
            fh.write("writable scope proof\n")
        with open(target) as fh:
            writable[label] = fh.read().startswith("writable scope proof")
    except OSError:
        writable[label] = False

not_visible = {}
for path in config["must_be_absent"]:
    not_visible[path] = not os.path.exists(path)

network = []
def network_attempt(name, call):
    # The probe only reports what it observed. Deciding whether that
    # observation *means* "no network" is the supervisor's job: a report that
    # graded itself would be a report whose denial claim could never be checked.
    try:
        call()
    except OSError as exc:
        return {"name": name, "allowed": False,
                "errno": exc.errno if isinstance(exc.errno, int) else None,
                "error": type(exc).__name__ + ": " + str(exc)}
    except Exception as exc:
        return {"name": name, "allowed": False, "errno": None,
                "error": type(exc).__name__ + ": " + str(exc)}
    return {"name": name, "allowed": True, "errno": None, "error": "succeeded"}

def open_connect():
    handle = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        handle.settimeout(3)
        handle.connect(("1.1.1.1", 443))
    finally:
        handle.close()

network.append(network_attempt("dns",
                               lambda: socket.getaddrinfo("example.com", 80)))
network.append(network_attempt("connect", open_connect))

sys.stdout.write(json.dumps({
    "attempts": attempts,
    "writable": writable,
    "not_visible": not_visible,
    "network": network,
    "cwd": os.getcwd(),
    "env_keys": sorted(os.environ),
    "git_env_keys": sorted(k for k in os.environ if k.startswith("GIT_")),
    "sandbox_host": platform.system() + " " + platform.release(),
    "sandbox_uid": os.getuid(),
}, sort_keys=True) + "\n")
'''


def _probe_script(proof_prefix, absent_paths):
    """Render the sandboxed probe program for this context.

    The config is embedded as a JSON *string literal* (`json.dumps` twice), so
    the in-sandbox program decodes exactly what the supervisor wrote instead of
    re-parsing a source-level object.
    """
    config = {"live": SANDBOX_LIVE, "sentinels": list(SENTINEL_FILES),
              "proof_prefix": proof_prefix,
              "must_be_absent": list(absent_paths)}
    return _PROBE_TEMPLATE.replace("__CONFIG__",
                                   json.dumps(json.dumps(config)))


# ---------------------------------------------------------------------------
# The disposable protected sentinel
# ---------------------------------------------------------------------------

def _require_supervisor_owned_sentinel(sentinel_root, meta_root, context_root):
    """Preflight may only ever build its sentinel inside the context meta area.

    This is what keeps "controlled protected-sentinel tests use disposable
    repositories; they never attempt a write to real source" structural: a
    sentinel root outside the supervisor-owned meta directory — or inside the
      live worktree at all — is refused before anything is created or launched.
    """
    resolved = os.path.realpath(os.path.abspath(sentinel_root))
    meta = os.path.realpath(os.path.abspath(meta_root))
    if not _within(resolved, meta) or resolved == meta:
        raise _blocker(
            SENTINEL_ROOT_NOT_ISOLATED,
            "the protected sentinel would be built at %r, which is not inside "
            "the supervisor-owned review meta directory %r; preflight never "
            "probes a real live tree" % (resolved, meta))
    live = os.path.realpath(os.path.abspath(context_root))
    if _within(live, resolved):
        raise _blocker(
            SENTINEL_ROOT_NOT_ISOLATED,
            "the protected sentinel at %r would contain the review context "
            "root %r" % (resolved, live))
    return resolved


def _create_sentinel(sentinel_root):
    """Write the disposable protected files the sandbox must not touch."""
    if os.path.exists(sentinel_root):
        shutil.rmtree(sentinel_root)
    for rel in SENTINEL_FILES:
        full = os.path.join(sentinel_root, rel)
        parent = os.path.dirname(full)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        with open(full, "wb") as fh:
            fh.write(_SENTINEL_CONTENT[rel])


def _enumerate_sentinel(sentinel_root):
    """(paths, per-path byte identity) of the protected tree, host-side.

    Both halves of each record start equal; `_seal_sentinel_after` refreshes
    the `*_after` half once the sandboxed attempts have finished, so the
    comparison is a host-side re-observation, not the sandbox's own claim.
    """
    paths = []
    records = {}
    for rel in sorted(SENTINEL_FILES):
        full = os.path.join(sentinel_root, rel)
        if not os.path.lexists(full):
            records[rel] = {"sha256_before": None, "sha256_after": None,
                            "size_before": None, "size_after": None,
                            "mode_before": None, "mode_after": None}
            continue
        with open(full, "rb") as fh:
            raw = fh.read()
        digest = hashlib.sha256(raw).hexdigest()
        mode = stat.S_IMODE(os.lstat(full).st_mode)
        records[rel] = {"sha256_before": digest, "sha256_after": digest,
                        "size_before": len(raw), "size_after": len(raw),
                        "mode_before": mode, "mode_after": mode}
    for dirpath, dirnames, filenames in os.walk(sentinel_root,
                                                followlinks=False):
        relative = os.path.relpath(dirpath, sentinel_root).replace("\\", "/")
        for name in filenames:
            paths.append(os.path.join(relative, name).replace("\\", "/")
                         if relative != "." else name)
        for name in dirnames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                paths.append("%s/%s" % (relative, name)
                             if relative != "." else name)
    return sorted(paths), records


def _seal_sentinel_after(records, sentinel_root):
    """Refresh the *after* half of each sentinel record."""
    for rel in records:
        full = os.path.join(sentinel_root, rel)
        record = records[rel]
        if not os.path.lexists(full):
            record["sha256_after"] = None
            record["size_after"] = None
            record["mode_after"] = None
            continue
        with open(full, "rb") as fh:
            raw = fh.read()
        record["sha256_after"] = hashlib.sha256(raw).hexdigest()
        record["size_after"] = len(raw)
        record["mode_after"] = stat.S_IMODE(os.lstat(full).st_mode)
    return records


# ---------------------------------------------------------------------------
# Evidence evaluation
# ---------------------------------------------------------------------------

def _absent_probe_paths(context, context_root, meta_root, roots):
    """(paths that must be unreachable, the live-repository subset of them).

    The generic set is what the profile masks with its fresh root; the live
    subset is what proves the live repository and its Git metadata stayed
    unreachable. Both are probed from inside the sandbox, so a claim of
    isolation is checked against the sandbox's own view, not assumed.
    """
    generic = ["/meta", "/mnt", "/mnt/c", "/run", "/home", "/init",
               "/tmp/.X11-unix"]
    host_side = [roots[_META_DIR]["sandbox_source"], linux_path(context_root),
                 linux_path(meta_root)]
    live = []
    live_root = (context or {}).get("live_root")
    if live_root:
        live = [linux_path(live_root), linux_path(os.path.join(live_root,
                                                               ".git"))]
    paths = []
    for path in generic + host_side + live:
        if path not in paths:
            paths.append(path)
    return paths, generic + host_side + live


def _evaluate_probe_report(report):
    """Turn the sandbox's own report into accepted/denied evidence."""
    if not isinstance(report, dict):
        raise _blocker(PROBE_REPORT_UNREADABLE,
                       "the boundary probe reported %s, not a report object"
                       % type(report).__name__)
    attempts = report.get("attempts")
    if not isinstance(attempts, list) or not attempts:
        raise _blocker(PROBE_REPORT_UNREADABLE,
                       "the boundary probe reported no write attempts")
    if not all(isinstance(attempt, dict) for attempt in attempts):
        raise _blocker(PROBE_REPORT_UNREADABLE,
                       "the boundary probe reported an attempt that is not an "
                       "attempt object: %r" % (attempts,))
    denials = {}
    permitted = []
    unverified = []
    rename_errno = None
    for attempt in attempts:
        name = attempt.get("name")
        syscall = attempt.get("syscall")
        code = attempt.get("errno")
        if attempt.get("allowed"):
            permitted.append("%s (%s -> %s)" % (name, syscall, code))
        if syscall in CROSS_MOUNT_SYSCALLS:
            if code is not None and rename_errno is None:
                rename_errno = code
            allowed = CROSS_MOUNT_RENAME_ERRNOS
        else:
            allowed = DENIAL_ERRNOS
        if code is not None and code not in allowed:
            unverified.append("%s (%s -> errno %s)" % (name, syscall, code))
        elif code is None and not attempt.get("allowed"):
            # A failure that reports no errno at all cannot be matched against
            # the denial set, so it proves nothing either way.
            unverified.append("%s (%s -> failed with no errno reported)"
                              % (name, syscall))
        denials[name] = {"syscall": syscall, "path": attempt.get("path"),
                         "allowed": bool(attempt.get("allowed")),
                         "errno": code}
    if permitted:
        raise _blocker(LIVE_WRITE_ALLOWED,
                       "the sandboxed process was allowed to modify the "
                       "protected sentinel: %s" % "; ".join(permitted))
    if unverified:
        raise _blocker(
            DENIAL_UNVERIFIED,
            "an attempt failed for a reason that is not a privilege denial "
            "(the path was not there to be denied): %s" % "; ".join(unverified))
    _require(UNSUPPORTED_RUNTIME_LAYOUT, rename_errno is not None,
             "the probe performed no cross-mount rename or hard link, so the "
             "escape out of the read-only scope was never exercised")
    return denials, rename_errno


def _judge_probe_report(report, absent_paths, observed):
    """The whole preflight verdict, as a pure function of the evidence.

    `report` is the sandbox's own claim about what it was allowed to do; it is
    never trusted, only tested. `observed` is the supervisor's own record of the
    protected sentinel it built for this pass: where it was created, the file
    set before and after the sandbox ran, and the per-file hashes/modes.

    Splitting the verdict out of `_preflight_pass` is what makes it testable
    against *lying* reports: a report that records an allowed write, an ENOENT
    dressed up as a denial, a missing cross-mount escape attempt, a writable
    scope it never proved or a network that merely timed out can all be fed
    straight to the judge without configuring a host or launching a sandbox.
    Every leg names its own blocker; nothing here is allowed to raise a generic
    error, and nothing here accepts a claim the supervisor did not verify.

    Returns `(denials, rename_errno, env_keys, network_denial_errno)`.
    """
    if not isinstance(observed, dict):
        raise _blocker(SENTINEL_CHANGED,
                       "preflight recorded no supervisor-side sentinel "
                       "observation, so the report has nothing to be checked "
                       "against")
    # Structural first: a sentinel outside the supervisor-owned meta area means
    # preflight was about to probe somebody else's files. Nothing about the
    # report can rescue that.
    for key in ("sentinel_root", "meta_root", "context_root"):
        if not observed.get(key):
            raise _blocker(
                SENTINEL_ROOT_NOT_ISOLATED,
                "preflight reported no %r, so the protected sentinel's owner "
                "cannot be established" % key)
    _require_supervisor_owned_sentinel(observed.get("sentinel_root"),
                                       observed.get("meta_root"),
                                       observed.get("context_root"))

    denials, rename_errno = _evaluate_probe_report(report)

    writable = report.get("writable")
    writable = writable if isinstance(writable, dict) else {}
    _require(WRITABLE_SCOPE_UNAVAILABLE,
             all(writable.get(scope) is True for scope in WRITABLE_SCOPES),
             "a declared writable scope is not proven writable: %r"
             % (writable,))

    not_visible = report.get("not_visible")
    not_visible = (not_visible if isinstance(not_visible, dict) else {})
    reachable = [path for path in absent_paths if not not_visible.get(path)]
    _require(HOST_SCOPE_REACHABLE, not reachable,
             "paths profile %s must not reach are visible inside the boundary: "
             "%s" % (PROFILE, ", ".join(reachable)))

    network = _network_attempts(report)
    reported = set(item.get("name") for item in network
                   if isinstance(item.get("name"), str))
    unreported = sorted(set(NETWORK_ATTEMPTS) - reported)
    unknown = sorted(reported - set(NETWORK_ATTEMPTS))
    _require(NETWORK_PERMITTED, not unreported and not unknown,
             "profile %s proves its no-network restriction from a %s attempt "
             "and a %s attempt: this report attempted %s and not %s%s: %r"
             % (PROFILE, NETWORK_ATTEMPTS[0], NETWORK_ATTEMPTS[1],
                ", ".join(sorted(reported)) or "nothing at all",
                ", ".join(unreported) or "nothing",
                ", besides the unrecognized %s" % ", ".join(unknown)
                if unknown else "", network))
    reached = [item for item in network if item.get("allowed")]
    _require(NETWORK_PERMITTED, not reached,
             "the sandboxed process reached the network: %s"
             % "; ".join("%s succeeded (%s)" % (item.get("name"),
                                                item.get("error"))
                         for item in reached))
    proofs = [item for item in network
              if item.get("name") == NETWORK_PROOF_ATTEMPT]
    unproven = [item for item in proofs
                if item.get("errno") not in NO_NETWORK_ERRNOS]
    _require(NETWORK_PERMITTED, not unproven,
             "the sandbox reached for the network and was not refused by the "
             "absence of one: %s is not a no-network errno (only %s are); a "
             "timeout, an EAI_* name-resolution failure, a refused or reset "
             "connection and an ICMP-style unreachable all happen on hosts "
             "that DO have network: %r"
             % ("; ".join("%r" % (item.get("error"),) for item in unproven),
                ", ".join(str(code) for code in sorted(NO_NETWORK_ERRNOS)),
                network))
    network_denial_errno = proofs[0].get("errno") if proofs else None

    env_keys = sorted(report.get("env_keys") or [])
    _require(ENVIRONMENT_NOT_SANITIZED,
             set(env_keys) <= set(ALLOWED_ENV_KEYS),
             "the sandboxed process inherited environment keys %s; profile %s "
             "clears the environment and permits only %s"
             % (", ".join(env_keys), PROFILE,
                ", ".join(sorted(ALLOWED_ENV_KEYS))))
    git_env_keys = list(report.get("git_env_keys") or [])
    _require(ENVIRONMENT_NOT_SANITIZED, not git_env_keys,
             "GIT_* overrides survived into the sandbox: %s"
             % ", ".join(git_env_keys))
    _require(UNSUPPORTED_RUNTIME_LAYOUT, report.get("cwd") == SANDBOX_CWD,
             "the verifier cwd is %r, not the pinned %r"
             % (report.get("cwd"), SANDBOX_CWD))

    # The supervisor's own re-enumeration is the actual proof: the sandbox could
    # have reported whatever it liked about its own attempts, so its bytes and
    # file set are checked against what was recorded before the launch.
    files = observed.get("files")
    files = files if isinstance(files, dict) else {}
    unprotected = sorted(set(SENTINEL_FILES) - set(files))
    _require(SENTINEL_CHANGED, not unprotected,
             "preflight protected no record for sentinel file(s): %s"
             % ", ".join(unprotected))
    paths_before = list(observed.get("paths_before") or [])
    paths_after = list(observed.get("paths_after") or [])
    _require(SENTINEL_CHANGED, paths_before and paths_before == paths_after,
             "the protected sentinel's file set changed: %s"
             % _describe_difference(paths_before, paths_after))
    changed = sorted(rel for rel, record in files.items()
                     if not isinstance(record, dict)
                     or record.get("sha256_before")
                     != record.get("sha256_after")
                     or record.get("mode_before") != record.get("mode_after")
                     or record.get("size_before") != record.get("size_after"))
    _require(SENTINEL_CHANGED, not changed,
             "protected bytes or metadata changed for: %s" % ", ".join(changed))
    return denials, rename_errno, env_keys, network_denial_errno


def _network_attempts(report):
    """The report's network attempts, shaped, or empty — never a crash."""
    raw = report.get("network")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]



# ---------------------------------------------------------------------------
# Public: preflight
# ---------------------------------------------------------------------------

def preflight(context_path):
    """Prove profile `linux-bwrap-v1` against this host and record the result.

    Builds preflight's own disposable protected sentinel (a source file, a test
    file, a fixture, a config file and a fake `.git/index`) inside the
    supervisor-owned meta area, mounts it read-only at `/live`, and from inside
    one sandboxed process attempts overwrite, append, truncate, unlink, mkdir,
    chmod, symlink, hard link, cross-mount rename and new-file creation against
    it, then proves `/snapshot`, `/scratch`, `/tmp` and `$HOME` are writable.
    Every attempt must be denied as a privilege denial (EACCES/EPERM/EROFS, or
    EXDEV for the renames) *and* the sentinel must be byte-for-byte unchanged
    when re-enumerated from the host side; anything else is a named blocker.
    The network must be refused because there is no network to refuse —
    ENETUNREACH, EPERM or EACCES — never because a connection timed out on a
    host that has one. The verdict is `_judge_probe_report`, a pure function of
    the sandbox's report and the supervisor's own sentinel record, which is what
    lets the focused tests feed it reports that lie.
    The sentinel is always removed again.

    Returns the restriction evidence and persists it as `meta/preflight.json`.
    Raises `contracts.ContractError` with the blocker named in the message on
    every failure, including host-unavailable; a failed preflight persists
    evidence that says `enforced: false` and never a passing claim.
    """
    try:
        evidence = _preflight_pass(context_path)
    except contracts.ContractError as exc:
        _persist_failed_preflight(context_path, str(exc))
        raise
    _write_json(os.path.join(_meta_dir(context_path), _PREFLIGHT_FILE),
                evidence)
    return evidence


def _persist_failed_preflight(context_path, message):
    """Record a refused proof: `enforced: false` plus the named blocker.

    The record can never authorize a run (`_evidence_is_current` requires
    `enforced` true), but it keeps the refusal auditable instead of silent.
    A context whose layout is unrepresentable gets no record at all, because
    there is no safe directory to write it into.
    """
    try:
        _context_root, roots = _mount_roots(context_path)
    except contracts.ContractError:
        return
    named = message.split(":", 1)[0].strip()
    evidence = {
        "format_version": FORMAT_VERSION,
        "profile": PROFILE,
        "enforced": False,
        "blocker": named,
        "created_at": _now(),
        "detail": message,
        "supervisor_host": supervisor_host(),
        "sandbox_host": None,
        "cwd": SANDBOX_CWD,
        "mount_roots": {name: dict(roots[name])
                        for name in (_REPO_DIR, _SCRATCH_DIR, _META_DIR)},
        "meta_mounted": False,
        "denials": {},
        "writable": {},
        "not_visible": {},
        "sentinel": {"files": {}, "paths_before": [], "paths_after": [],
                     "removed": True},
    }
    _write_json(os.path.join(_meta_dir(context_path), _PREFLIGHT_FILE),
                evidence)


def _preflight_pass(context_path):
    """The one sandboxed pass that proves the profile, or names a blocker."""
    context_root, roots = _mount_roots(context_path)
    meta_root = roots[_META_DIR]["host"]
    sentinel_root = _require_supervisor_owned_sentinel(
        _sentinel_root(context_path), meta_root, context_root)
    version = _bwrap_version()
    try:
        context = _read_context(context_path)
    except contracts.ContractError:
        context = None
    absent_paths, live_paths = _absent_probe_paths(context, context_root,
                                                   meta_root, roots)

    proof_prefix = ".bwrap-preflight-" + uuid.uuid4().hex[:12]
    live_source = linux_path(sentinel_root)
    command = _boundary_command(
        roots, context_path, _probe_argv(proof_prefix, absent_paths),
        live_source=live_source)
    _create_sentinel(sentinel_root)
    paths_before, records = _enumerate_sentinel(sentinel_root)
    try:
        returncode, stdout_bytes, stderr_text = _probe_captured(command)
        named = classify_boundary_failure(returncode, stdout_bytes, stderr_text)
        if named:
            raise _blocker(named, stderr_text.strip()
                           or "bwrap exited %d" % returncode)
        if returncode != 0 and not stdout_bytes.strip():
            raise _blocker(UNSUPPORTED_RUNTIME_LAYOUT,
                           "the boundary probe exited %d without a report: %s"
                           % (returncode, stderr_text.strip()))
        try:
            report = json.loads(
                stdout_bytes.decode("utf-8").strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise _blocker(PROBE_REPORT_UNREADABLE,
                           "the boundary probe reported no parseable evidence "
                           "(stderr: %s)" % (stderr_text.strip() or "empty"))
        # The supervisor's own re-enumeration is the actual proof: the sandbox
        # could have reported whatever it liked about its own attempts. Both
        # halves are handed to the judge, which is a pure function of the report
        # plus this observation, so the focused tests can feed it reports that
        # lie without configuring a host or launching a sandbox.
        paths_after, _ = _enumerate_sentinel(sentinel_root)
        _seal_sentinel_after(records, sentinel_root)
        denials, rename_errno, env_keys, network_denial_errno = (
            _judge_probe_report(
                report, absent_paths,
                {"sentinel_root": sentinel_root, "meta_root": meta_root,
                 "context_root": context_root, "paths_before": paths_before,
                 "paths_after": paths_after, "files": records}))

        evidence = {
            "format_version": FORMAT_VERSION,
            "profile": PROFILE,
            "enforced": True,
            "blocker": None,
            "created_at": _now(),
            "bwrap_version": version,
            "supervisor_host": supervisor_host(),
            "sandbox_host": report["sandbox_host"],
            "sandbox_uid": report.get("sandbox_uid"),
            "launcher": _launcher_label(),
            "launcher_prefix": launcher_prefix(),
            "distro": _wsl_distro(),
            "cwd": report["cwd"],
            "env_keys": env_keys,
            "mount_roots": {name: dict(roots[name])
                            for name in (_REPO_DIR, _SCRATCH_DIR, _META_DIR)},
            "meta_mounted": False,
            "denials": denials,
            "rename_errno": rename_errno,
            "writable": report["writable"],
            "not_visible": report["not_visible"],
            "network": report["network"],
            "network_denied": True,
            "network_denial_errno": network_denial_errno,
            "live_git_unavailable": all(report["not_visible"].get(path)
                                        for path in live_paths),
            "absent_probe_paths": absent_paths,
            "sentinel": {
                "root": sentinel_root,
                "files": records,
                "paths_before": paths_before,
                "paths_after": paths_after,
                "removed": True,
            },
            "live_root": (context or {}).get("live_root"),
        }
        return evidence
    finally:
        _remove_sentinel(sentinel_root, roots, proof_prefix)


def _describe_difference(before, after):
    missing = sorted(set(before) - set(after))
    extra = sorted(set(after) - set(before))
    parts = []
    if missing:
        parts.append("removed: %s" % ", ".join(missing))
    if extra:
        parts.append("created: %s" % ", ".join(extra))
    return "; ".join(parts) or "no difference"


def _remove_sentinel(sentinel_root, roots, proof_prefix):
    """Remove the sentinel and every writable-scope proof file it created."""
    if os.path.exists(sentinel_root):
        shutil.rmtree(sentinel_root, ignore_errors=True)
    for name in (_REPO_DIR, _SCRATCH_DIR):
        candidate = os.path.join(roots[name]["host"], proof_prefix)
        try:
            if os.path.lexists(candidate):
                os.remove(candidate)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Evidence acceptance for a run
# ---------------------------------------------------------------------------

def _evidence_is_current(evidence, roots, version):
    """Only evidence for exactly this host, profile and mount set may pass."""
    if not isinstance(evidence, dict):
        return False
    checks = (
        evidence.get("format_version") == FORMAT_VERSION,
        evidence.get("profile") == PROFILE,
        evidence.get("enforced") is True,
        evidence.get("blocker") is None,
        evidence.get("meta_mounted") is False,
        evidence.get("cwd") == SANDBOX_CWD,
        bool(evidence.get("denials")),
        all(not attempt.get("allowed")
            for attempt in (evidence.get("denials") or {}).values()),
        all(bool(evidence.get("writable", {}).get(scope))
            for scope in WRITABLE_SCOPES),
        evidence.get("network_denied") is True,
        evidence.get("network_denial_errno") in NO_NETWORK_ERRNOS,
        evidence.get("bwrap_version") == version,
        evidence.get("supervisor_host") == supervisor_host(),
        evidence.get("launcher") == _launcher_label(),
        evidence.get("sandbox_host"),
        evidence.get("sentinel", {}).get("removed") is True,
    )
    if not all(bool(check) for check in checks):
        return False
    persisted = evidence.get("mount_roots") or {}
    for name in (_REPO_DIR, _SCRATCH_DIR, _META_DIR):
        recorded = persisted.get(name) or {}
        expected = roots[name]
        if recorded.get("host") != expected["host"] \
                or recorded.get("sandbox_source") != expected["sandbox_source"]:
            return False
    return True


def _boundary_evidence(context_path, roots):
    """Accepted boundary evidence for this context on this host.

    Persisted evidence is reused only when it matches this host, this bwrap
    version and these exact canonical mount roots; otherwise the same
    `preflight` entry point re-derives it. That is not a fallback to a weaker
    boundary: the identical restrictions are re-proved.
    """
    version = _bwrap_version()
    path = os.path.join(_meta_dir(context_path), _PREFLIGHT_FILE)
    if os.path.isfile(path):
        try:
            persisted = _read_json(path)
        except (ValueError, OSError, contracts.ContractError):
            persisted = None
        if persisted is not None and _evidence_is_current(persisted, roots,
                                                         version):
            return persisted
    evidence = preflight(context_path)
    _require(UNSUPPORTED_RUNTIME_LAYOUT,
             _evidence_is_current(evidence, roots, version),
             "preflight produced evidence that does not describe this host "
             "and these mount roots")
    return evidence


# ---------------------------------------------------------------------------
# Currentness, baseline pinning and receipts
# ---------------------------------------------------------------------------

def _require_current_context(context_path, context, stage):
    """Re-validate the supervisor manifest against the live repository.

    Task 1's `assert_current` compares the Ticket, the live root, the reviewed
    commit, the live manifest identity, every captured raw input hash and the
    HARDEN-010 drift. It runs before the launch, and again after it: a run
    whose preparation baseline moved underneath it is refused, not recorded.
    """
    live_root = context.get("live_root") or ""
    if not live_root or not os.path.isdir(live_root):
        raise _blocker(PREPARATION_BASELINE_ALTERED,
                       "the review context's live root %r is not a directory, "
                       "so %s cannot be re-checked" % (live_root, stage))
    try:
        review_snapshot.assert_current(live_root, context.get("ticket_id"),
                                       context_path)
    except contracts.ContractError as exc:
        message = str(exc)
        if stage != "before the run":
            raise _blocker(PREPARATION_BASELINE_ALTERED,
                           "the verification consumed an altered preparation "
                           "baseline (%s): %s" % (stage, message))
        raise contracts.ContractError(
            "the review context is no longer current %s: %s" % (stage, message))


def _baseline_path(context_path):
    return os.path.join(_meta_dir(context_path), _BASELINE_FILE)


def _require_baseline_accepted(context_path, identity):
    """The first baseline pins the snapshot identity; later ones must match.

    A tracked snapshot code or verification-input change since the pinned
    baseline is refused. Restoring the snapshot to the pinned identity lets
    another explicitly recorded baseline run. Probe runs are never blocked by
    this pin — a probe is expected to modify the snapshot.
    """
    path = _baseline_path(context_path)
    if not os.path.exists(path):
        return None
    try:
        record = _read_json(path)
    except (ValueError, OSError) as exc:
        raise contracts.ContractError(
            "cannot read the baseline record %s: %s" % (path, exc))
    pinned = record.get("snapshot_identity")
    if pinned != identity:
        raise _blocker(
            BASELINE_IDENTITY_DRIFT,
            "the snapshot no longer matches the baseline recorded by run %s "
            "(pinned identity %r, current %r); restore it, or record another "
            "explicit baseline run" % (record.get("run_id"), pinned, identity))
    return record


def _record_baseline(context_path, identity, run_id):
    """Record the baseline identity this run accepted, as an audit step."""
    previous = None
    path = _baseline_path(context_path)
    if os.path.exists(path):
        try:
            previous = _read_json(path).get("run_id")
        except (ValueError, OSError):
            previous = None
    _write_json(path, {
        "format_version": FORMAT_VERSION,
        "kind": "baseline",
        "profile": PROFILE,
        "snapshot_identity": identity,
        "run_id": run_id,
        "previous_run_id": previous,
        "recorded_at": _now(),
    })


def _require_argv(argv):
    """`argv` must be a real top-level command list, never a shell fragment."""
    if isinstance(argv, str) or argv is None \
            or not isinstance(argv, (list, tuple)):
        raise contracts.ContractError(
            "argv must be a list of command arguments, got %r" % (argv,))
    items = list(argv)
    if not items:
        raise contracts.ContractError("argv must name the command to run")
    for item in items:
        if not isinstance(item, str) or not item:
            raise contracts.ContractError(
                "argv entries must be non-empty strings, got %r" % (item,))
        if "\0" in item:
            raise contracts.ContractError("argv entries may not contain NUL")
    if items[0].startswith("-"):
        raise contracts.ContractError(
            "argv[0] must be the program to run, not an option: %r" % items[0])
    return items


# ---------------------------------------------------------------------------
# Public: run
# ---------------------------------------------------------------------------

def run(context_path, kind, argv):
    """Run one verifier command under the enforced boundary; return a receipt.

    `kind` is `"baseline"` or `"probe"`; anything else is a `ContractError`.
    The command starts from the frozen argument list built for this context:
    the snapshot clone writable at `/snapshot` (its cwd), `/scratch` writable,
    the runtime read-only mounts, a cleared environment, no network, no host
    sockets, no live tree and no supervisor `meta/`. `argv` is passed verbatim
    after a literal `--`, so it is never interpreted by a shell or as bwrap
    options.

    stdout and stderr are captured to `meta/runs/<run_id>.stdout`/`.stderr` and
    are collected for failing commands too; the exit status is recorded as the
    command's own. Before accepting the receipt the supervisor re-checks the
    live identities, that `meta/context.json` is still the exact byte sequence
    it read before the launch, that the layout roots are still canonical and
    still independent, and that nothing else reached the supervisor's records;
    any disagreement refuses the receipt. A blocked attempt never leaves a
    receipt behind, in this module or any other.

    Returns the persisted receipt dict.
    """
    if kind not in KINDS:
        raise contracts.ContractError(
            "run kind must be one of %s, got %r" % (" or ".join(KINDS), kind))
    command_argv = _require_argv(argv)
    context_root, roots = _mount_roots(context_path)
    _require_independent_git(roots)
    # Build and verify the mount set before anything is launched: an
    # unapproved bind source must never reach the host launcher.
    marker_host = os.path.join(roots[_SCRATCH_DIR]["host"], _START_MARKER)
    # Cleared before the launch so a marker left by an earlier run can never
    # stand in for a boundary that did not start this time.
    try:
        if os.path.lexists(marker_host):
            os.remove(marker_host)
    except OSError as exc:
        raise _blocker(WRITABLE_SCOPE_UNAVAILABLE,
                       "cannot clear the boundary start marker: %s" % exc)
    command = _boundary_command(roots, context_path, command_argv,
                                start_marker=True)
    evidence = _boundary_evidence(context_path, roots)
    context = _read_context(context_path)
    context_bytes_before = _read_bytes_or_none(
        os.path.join(_meta_dir(context_path), _CONTEXT_FILE))
    _require_current_context(context_path, context, "before the run")

    repo = roots[_REPO_DIR]["host"]
    before_entries, before_identity = _pinned_identity(repo, context)
    before_tree = _enumerate_tree(repo)
    if kind == "baseline":
        pinned = _require_baseline_accepted(context_path, before_identity)
        if pinned is None:
            # The first baseline is the preparation baseline. Tying it to Task
            # 1's captured snapshot identity is what stops a probe-modified
            # snapshot from promoting its own edits into "the" baseline.
            prepared = context.get("snapshot_manifest")
            current = _scope_identity(before_entries, context)
            if current != prepared:
                raise _blocker(
                    BASELINE_IDENTITY_DRIFT,
                    "the first baseline run must start from the prepared "
                    "snapshot (prepared %r, snapshot now %r); restore it or "
                    "prepare a fresh review context" % (prepared, current))

    run_id = uuid.uuid4().hex
    runs_dir = os.path.join(_meta_dir(context_path), _RUNS_DIR)
    if not os.path.isdir(runs_dir):
        try:
            os.makedirs(runs_dir)
        except OSError as exc:
            raise contracts.ContractError(
                "cannot create the receipt directory %s: %s" % (runs_dir, exc))
    stdout_path = os.path.join(runs_dir, "%s.stdout" % run_id)
    stderr_path = os.path.join(runs_dir, "%s.stderr" % run_id)
    started_at = _now()
    try:
        returncode = launch(command, stdout_path, stderr_path)
    except (_LaunchUnavailable, OSError) as exc:
        for stray in (stdout_path, stderr_path):
            try:
                if os.path.lexists(stray):
                    os.remove(stray)
            except OSError:
                pass
        raise _blocker(BWRAP_EXECUTABLE_NOT_FOUND,
                       "the host could not start the boundary for this run: %s"
                       % exc)
    finished_at = _now()

    captured_out = _read_or_empty(stdout_path)
    captured_err = _read_or_empty(stderr_path).decode("utf-8", "replace")
    named = classify_boundary_failure(returncode, captured_out, captured_err)
    if named:
        # bwrap itself refused: the command never ran under the boundary, so
        # there is nothing to record and no fallback to try. The half-written
        # capture files go too, so a refused attempt leaves no receipt-shaped
        # trail for a later phase to mistake for a run.
        for stray in (stdout_path, stderr_path):
            try:
                if os.path.lexists(stray):
                    os.remove(stray)
            except OSError:
                pass
        raise _blocker(named,
                       "the boundary refused to start the verifier command: %s"
                       % captured_err.strip())

    if not os.path.isfile(marker_host):
        # Nothing inside the sandbox reached its start step, so this cannot be
        # recorded as an enforced run however the status reads. A launcher that
        # could not exec at all (wsl.exe or bwrap unreachable) leaves a nonzero
        # status whose stderr is not bwrap's own marker, and would otherwise be
        # filed as an ordinary verifier failure with `enforced: true`.
        for stray in (stdout_path, stderr_path):
            try:
                if os.path.lexists(stray):
                    os.remove(stray)
            except OSError:
                pass
        raise _blocker(
            BOUNDARY_NEVER_STARTED,
            "the boundary never reached its in-sandbox start step, so the "
            "verifier command did not run under profile %s (exit %r: %s)"
            % (PROFILE, returncode, captured_err.strip()))

    after_entries, after_identity = _pinned_identity(repo, context)
    after_tree = _enumerate_tree(repo)

    # Accept the receipt only after re-checking the supervisor's own records.
    if _read_bytes_or_none(os.path.join(_meta_dir(context_path),
                                        _CONTEXT_FILE)) != context_bytes_before:
        raise _blocker(PREPARATION_BASELINE_ALTERED,
                       "meta/context.json changed during the run; the "
                       "preparation baseline is not the one this run started "
                       "from")
    _require_current_context(context_path, context, "after the run")
    persisted_evidence = None
    try:
        persisted_evidence = _read_json(
            os.path.join(_meta_dir(context_path), _PREFLIGHT_FILE))
    except (OSError, ValueError, contracts.ContractError):
        persisted_evidence = None
    _require(PREPARATION_BASELINE_ALTERED,
             isinstance(persisted_evidence, dict)
             and persisted_evidence.get("enforced") is True,
             "the persisted boundary evidence is missing, unreadable or no "
             "longer claims enforcement")
    rechecked_root, rechecked_roots = _mount_roots(context_path)
    _require(PREPARATION_BASELINE_ALTERED, rechecked_root == context_root
             and rechecked_roots == roots,
             "the review context layout roots moved during the run")
    _require_independent_git(rechecked_roots)

    receipt = {
        "run_id": run_id,
        "kind": kind,
        "argv": command_argv,
        "cwd": SANDBOX_CWD,
        "exit_code": int(returncode),
        "stdout_path": "%s/%s/%s.stdout" % (_META_DIR, _RUNS_DIR, run_id),
        "stdout_sha256": _sha_file(stdout_path),
        "stderr_path": "%s/%s/%s.stderr" % (_META_DIR, _RUNS_DIR, run_id),
        "stderr_sha256": _sha_file(stderr_path),
        "snapshot_before": before_identity,
        "snapshot_after": after_identity,
        "changed_paths": _entry_changes(before_entries, after_entries),
        "added_paths": sorted(after_tree - before_tree),
        "removed_paths": sorted(before_tree - after_tree),
        "boundary": _receipt_boundary(context_path, evidence),
        "profile": PROFILE,
        "host": supervisor_host(),
        "started_at": started_at,
        "finished_at": finished_at,
        "blocker": None,
    }
    _write_json(os.path.join(runs_dir, "%s.json" % run_id), receipt)
    if kind == "baseline":
        _record_baseline(context_path, before_identity, run_id)
    return receipt


def _read_bytes_or_none(path):
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


def _receipt_boundary(context_path, evidence):
    """Reference plus summary of the accepted preflight evidence.

    The receipt points at the durable evidence instead of duplicating it, and
    carries enough of a summary that a consumer can see what was actually
    proved — including which host proved it.
    """
    path = os.path.join(_meta_dir(context_path), _PREFLIGHT_FILE)
    return {
        "profile": PROFILE,
        "enforced": bool(evidence.get("enforced")),
        "blocker": evidence.get("blocker"),
        "preflight": "%s/%s" % (_META_DIR, _PREFLIGHT_FILE),
        "preflight_sha256": _sha_file(path),
        "bwrap_version": evidence.get("bwrap_version"),
        "supervisor_host": evidence.get("supervisor_host"),
        "sandbox_host": evidence.get("sandbox_host"),
        "launcher": evidence.get("launcher"),
        "distro": evidence.get("distro"),
        "mount_roots": evidence.get("mount_roots"),
        "denials_attempted": len(evidence.get("denials") or {}),
        "denial_errnos": sorted({attempt["errno"]
                                 for attempt in (evidence.get("denials") or {})
                                 .values()
                                 if attempt.get("errno") is not None}),
        "rename_errno": evidence.get("rename_errno"),
        "writable": evidence.get("writable"),
        "not_visible": evidence.get("not_visible"),
        "network_denied": evidence.get("network_denied"),
        "network_denial_errno": evidence.get("network_denial_errno"),
        "live_git_unavailable": evidence.get("live_git_unavailable"),
        "env_keys": evidence.get("env_keys"),
        "sentinel_removed": bool((evidence.get("sentinel") or {})
                                 .get("removed")),
    }
