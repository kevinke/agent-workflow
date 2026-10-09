"""Tests for the enforced local process boundary and supervisor receipts
(HARDEN-011 Task 2).

The plan's three named tests, then the refusal legs an independent review
required (see ``.superpowers/sdd/2026-10-09-harden-11/``):

``test_boundary_denies_live_and_allows_snapshot``
    ``preflight`` really does deny every write to a disposable protected
    sentinel from inside the same sandboxed process, and really does allow
    ``/snapshot`` and ``/scratch`` writes. The proof is supervisor-side: the
    sentinel's file set, bytes and modes are compared before and after the
    sandboxed attempts, so a sandbox that lies about denial cannot pass.

``test_unavailable_boundary_is_closed``
    every unavailable or misconfigured boundary fails closed with a *named*
    blocker and produces no receipt: bwrap missing, namespace creation denied,
    an unapproved mount root, shared writable Git metadata, an unrepresentable
    context layout. These legs run unconditionally on every host and are driven
    through the injectable launcher seam (``review_boundary.launch``), so no
    host setting is touched.

``test_receipts_preserve_failures_and_scope``
    a failing baseline command and a successful probe command each leave their
    own receipt carrying the command's real exit status, argv verbatim and
    hashes over the bytes actually captured; residual snapshot changes are
    recorded; the supervisor's ``meta/`` is unreachable from inside the sandbox;
    and a snapshot that drifted from its recorded baseline refuses further
    baseline runs until it is restored.

``test_denial_judge_refuses_lying_probe_reports``
    the denial judge itself, driven with reports no sandbox produced. The real
    legs can only ever hand it honest evidence, so a judge that accepted an
    allowed write, an ENOENT posing as a denial, a missing cross-mount rename, a
    self-graded network claim or a mutated sentinel would stay invisible to
    them. Each leg names the blocker it expects, and one leg confirms an honest
    report is still accepted — a judge that refused everything would otherwise
    look identical to a judge that refuses nothing.

Host execution legs are conditional: if the boundary reports itself
unavailable the executing legs skip with a message naming the blocker, which
is never read as support. The fail-closed legs never skip.
"""

import errno
import hashlib
import json
import os
import shutil
from contextlib import contextmanager
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contracts  # noqa: E402
import review_boundary  # noqa: E402
import review_snapshot  # noqa: E402
from v2_support import V2CLITestCase  # noqa: E402

# Verifier commands run *inside* the sandbox, so they name the sandbox's own
# interpreter and POSIX paths: `/snapshot` is the snapshot clone (the cwd),
# `/scratch` the verifier output area, `/live` the disposable sentinel preflight
# mounts read-only, and `/meta` is deliberately never mounted at all.

FAILING_COMMAND_SCRIPT = (
    "import os, sys\n"
    "sys.stdout.write('failing-stdout\\n')\n"
    "sys.stdout.write('cwd ' + os.getcwd() + '\\n')\n"
    "sys.stderr.write('failing-stderr\\n')\n"
    "sys.stderr.flush()\n"
    "sys.exit(3)\n"
)

PROBE_EDIT_SCRIPT = (
    "import json, os\n"
    "res = {'cwd': os.getcwd()}\n"
    "orig = open('src/feature.py', 'rb').read()\n"
    "open('src/feature.py', 'wb').write(orig + b'# probe edit\\n')\n"
    "open('probe_added.py', 'w').write('reviewer scratch source\\n')\n"
    "os.remove('src/app.py')\n"
    "open('/scratch/probe-note.txt', 'w').write('scratch write ok\\n')\n"
    "for name in ('context.json', 'preflight.json'):\n"
    "    try:\n"
    "        with open('/meta/' + name, 'a') as fh:\n"
    "            fh.write('tamper\\n')\n"
    "        res['write_' + name] = 'ALLOWED'\n"
    "    except OSError as exc:\n"
    "        res['write_' + name] = 'denied ' + str(exc.errno)\n"
    "res['meta_visible'] = os.path.exists('/meta')\n"
    "print(json.dumps(res, sort_keys=True))\n"
)

UNCHANGED_COMMAND_SCRIPT = (
    "import json, os\n"
    "print(json.dumps({'cwd': os.getcwd()}, sort_keys=True))\n"
)

DENIED_META_WRITE_ERRNOS = {"denied %d" % code for code in
                            (errno.ENOENT, errno.EACCES, errno.EPERM,
                             errno.EROFS)}


def _slug(rel):
    """The probe template's own attempt-name transform, kept in one place.

    Deriving the names here instead of typing them means a report built by
    these tests names the same attempts the sandboxed probe really reports.
    """
    return rel.replace("/", ".").replace(".", "_")


# "the judge's `observed` argument was not supplied" — a plain None cannot carry
# that meaning here, because a missing observation is itself one of the lies.
_NO_OBSERVED = object()

# Linux errno numbers, hardcoded independently of the module: the sandbox is
# Linux while the supervisor may be Windows Python driving `wsl.exe`, and on
# Windows `errno.ENETUNREACH` is 10051. Reading the profile's own table would
# hide a wrong table behind the same wrong arithmetic.
LINUX = {"EPERM": 1, "EACCES": 13, "EROFS": 30, "EXDEV": 18, "ENOENT": 2,
         "ENETUNREACH": 101, "EHOSTUNREACH": 113, "ECONNREFUSED": 111,
         "ECONNRESET": 104, "ETIMEDOUT": 110}


class ReviewBoundaryTest(V2CLITestCase):
    # -- fixture helpers -----------------------------------------------------

    # Every module-level seam a leg may stub. A stub that survives the leg that
    # installed it silently changes what later legs exercise — a leaked
    # `_probe_captured` in particular would replace the real sandbox with a
    # canned report, which is the opposite of this file's purpose. `setUp`
    # refuses to start a test on top of a leak.
    _SEAM_NAMES = ("launch", "_probe_captured", "_extra_bind_specs",
                   "_sentinel_root", "_bwrap_version")
    _pristine_seams = dict((name, getattr(review_boundary, name))
                           for name in _SEAM_NAMES)

    def setUp(self):
        super().setUp()
        for name in self._SEAM_NAMES:
            current = getattr(review_boundary, name)
            self.assertIs(current, self._pristine_seams[name],
                          "seam %s leaked from an earlier test" % name)
        # Review contexts live OUTSIDE the live worktree (Task 1 enforces that).
        self._out_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._out_tmp.cleanup)

    def _record_bytes(self):
        """Configured live State/Review/Handoff bytes, read without mutation."""
        out = {}
        data = self.read_state()
        artifacts = data.get("artifacts") or {}
        for key in ("state", "review", "handoff"):
            if key == "state":
                rel = os.path.join(".ai", "work", self.TICKET, "state.yaml")
            else:
                rel = os.path.join(".ai", "work", self.TICKET,
                                   artifacts.get(key, "%s.md" % key))
            full = os.path.join(self.root, rel)
            out[rel] = self._read_bytes(full) if os.path.exists(full) else None
        return out

    def _live_untouched(self):
        """Fingerprint of everything a boundary run must not move."""
        index_path = os.path.join(self.root, ".git", "index")
        return {
            "index": self._read_bytes(index_path),
            "index_mtime": os.stat(index_path).st_mtime_ns,
            "flags": self._git("ls-files", "-v", "-z").stdout,
            "gitdir": sorted(os.listdir(os.path.join(self.root, ".git"))),
            "files": self.capture_files(),
        }

    def _assert_live_untouched(self, snap):
        index_path = os.path.join(self.root, ".git", "index")
        self.assertEqual(self._read_bytes(index_path), snap["index"],
                         ".git/index bytes changed")
        self.assertEqual(os.stat(index_path).st_mtime_ns, snap["index_mtime"],
                         ".git/index mtime changed")
        self.assertEqual(self._git("ls-files", "-v", "-z").stdout, snap["flags"],
                         "index hint flags changed")
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, ".git"))),
                         snap["gitdir"],
                         "a file was created or removed under .git")
        self.assertEqual(self.capture_files(), snap["files"],
                         "live working-tree bytes changed")

    def _new_output(self, name="context"):
        path = os.path.join(self._out_tmp.name, name)
        self.assertFalse(os.path.exists(path))
        return path

    def _prepare(self, output=None):
        """Prepare a real Task 1 snapshot; return (context, output)."""
        output = output or self._new_output()
        reviewed = self._git("rev-parse", "HEAD").stdout.strip()
        context = review_snapshot.prepare(self.root, self.TICKET, reviewed,
                                          output)
        return context, output

    def _meta(self, output, *parts):
        return os.path.join(output, "meta", *parts)

    def _read_bytes(self, path):
        with open(path, "rb") as fh:
            return fh.read()

    def _sha(self, path):
        return hashlib.sha256(self._read_bytes(path)).hexdigest()

    def _context_json_bytes(self, output):
        return self._read_bytes(self._meta(output, "context.json"))

    def _receipt_files(self, output):
        runs = self._meta(output, "runs")
        if not os.path.isdir(runs):
            return []
        return sorted(name for name in os.listdir(runs)
                      if name.endswith(".json"))

    def _write_bytes(self, path, data, mode=None):
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        raw = data.encode("utf-8") if isinstance(data, str) else data
        with open(path, "wb") as fh:
            fh.write(raw)
        if mode is not None:
            try:
                os.chmod(path, mode)
            except OSError:
                pass  # Windows reports a uniform mode; chmod is advisory there

    def _assert_no_enforced_receipt(self, output):
        """No receipt at all, and so certainly none claiming enforced success.

        A blocked attempt must leave nothing behind that a later phase could
        read as a run that happened under an enforced boundary — not a receipt,
        not a baseline pin, not even an unmatched capture file.
        """
        self.assertEqual(self._receipt_files(output), [],
                         "a blocked boundary attempt still wrote a receipt")
        runs = self._meta(output, "runs")
        if os.path.isdir(runs):
            self.assertEqual(sorted(os.listdir(runs)), [],
                             "a blocked attempt left capture files behind")
        self.assertFalse(os.path.exists(self._meta(output, "baseline.json")),
                         "a blocked attempt recorded a baseline")
        evidence = self._meta(output, "preflight.json")
        if os.path.exists(evidence):
            persisted = json.loads(self._read_bytes(evidence).decode("utf-8"))
            self.assertIsNot(persisted.get("enforced"), True,
                             "a blocked attempt persisted an enforced=True "
                             "evidence record")
            self.assertTrue(persisted.get("blocker"),
                            "a blocked attempt persisted no named blocker")

    # -- receipt/output accessors (paths in the receipt are context-relative) --

    def _receipt_output_abs(self, output, receipt, stream):
        return os.path.join(output,
                            *receipt["%s_path" % stream].split("/"))

    def _assert_captured(self, output, receipt, stream, needle):
        path = self._receipt_output_abs(output, receipt, stream)
        self.assertEqual(os.path.realpath(path),
                         os.path.realpath(self._meta(
                             output, "runs",
                             "%s.%s" % (receipt["run_id"], stream))))
        raw = self._read_bytes(path)
        self.assertEqual(receipt["%s_sha256" % stream],
                         hashlib.sha256(raw).hexdigest(),
                         "%s hash does not cover the captured bytes" % stream)
        self.assertEqual(receipt["%s_path" % stream],
                         "meta/runs/%s.%s" % (receipt["run_id"], stream))
        if needle is not None:
            self.assertIn(needle, raw)

    # -- launcher seam -------------------------------------------------------

    def _seam(self, behavior):
        """Replace the module-level launcher seam; record every launch call.

        Every fail-closed leg below goes through this seam, so the host is
        never reconfigured to prove a refusal.
        """
        calls = []

        def wrapper(command, stdout_path=None, stderr_path=None):
            calls.append(list(command))
            return behavior(command, stdout_path, stderr_path)

        original = review_boundary.launch
        review_boundary.launch = wrapper
        self.addCleanup(setattr, review_boundary, "launch", original)
        return calls

    @staticmethod
    def _denied_namespace(command, stdout_path, stderr_path):
        """What a denied uid map looks like: bwrap's own marker, nothing ran.

        `bwrap --version` still answers, because that is the real shape of this
        blocker: the binary is present but namespace creation is refused.
        """
        if "--version" in command:
            if stdout_path:
                with open(stdout_path, "wb") as fh:
                    fh.write(b"bubblewrap 0.0.0-simulated\n")
            if stderr_path:
                with open(stderr_path, "wb") as fh:
                    fh.write(b"")
            return 0
        if stderr_path:
            with open(stderr_path, "wb") as fh:
                fh.write(b"bwrap: setting up uid map: Permission denied\n")
        if stdout_path:
            with open(stdout_path, "wb") as fh:
                fh.write(b"")
        return 1

    @staticmethod
    def _missing_executable(command, stdout_path, stderr_path):
        raise FileNotFoundError(2, "No such file or directory", None,
                                "bwrap")

    @staticmethod
    def _never_launches(command, stdout_path, stderr_path):
        raise AssertionError("the boundary must not launch: %s" % (command,))

    @contextmanager
    def _scoped(self, name, value):
        """Patch a module attribute for ONE subtest.

        `_patch` unwinds only when the whole test method ends, so a patch applied
        inside a subTest leaks into every later subTest and silently changes what
        they exercise: the injected foreign bind here made a downstream argv leg
        fail for the wrong reason, so removing its guard kept the suite green.
        """
        original = getattr(review_boundary, name)
        setattr(review_boundary, name, value)
        try:
            yield
        finally:
            setattr(review_boundary, name, original)

    def _patch(self, name, value):
        original = getattr(review_boundary, name)
        setattr(review_boundary, name, value)
        self.addCleanup(setattr, review_boundary, name, original)
        return original

    # -- host-conditionality -------------------------------------------------

    def _unavailable(self, action):
        """Run a host leg; skip only if this host cannot run the boundary AT ALL.

        A skip may only mean "no bwrap here" or "namespaces are refused here".
        Every other refusal is a real block or our own misconfiguration and must
        fail: with the previous blanket handling, a mutation that dropped
        `--unshare-all` or broke the baseline tie turned the leg into a skip, so
        a green run never proved the boundary had been exercised.
        """
        try:
            return action()
        except contracts.ContractError as exc:
            blocker = str(exc).split(":", 1)[0].strip()
            if blocker not in self._SKIP_BLOCKERS:
                raise
            self.skipTest(
                "linux-bwrap-v1 boundary is unavailable on this host, no "
                "support is claimed by this skip: %s" % exc)

    # Only these two blockers describe a host that cannot provide the boundary.
    _SKIP_BLOCKERS = (review_boundary.BWRAP_EXECUTABLE_NOT_FOUND,
                      review_boundary.NAMESPACE_CREATION_DENIED)

    def _preflight_or_skip(self, output):
        return self._unavailable(lambda: review_boundary.preflight(output))

    def _run_or_skip(self, output, kind, argv):
        return self._unavailable(lambda: review_boundary.run(output, kind, argv))

    # ========================================================================
    # 1. The boundary actually denies live writes and allows snapshot writes.
    # ========================================================================

    def test_boundary_denies_live_and_allows_snapshot(self):
        self.prepare_v2_review()
        context, output = self._prepare()
        records_before = self._record_bytes()
        live = self._live_untouched()
        receipts_before = self._receipt_files(output)

        evidence = self._preflight_or_skip(output)

        # -- what profile and what host actually proved this -----------------
        self.assertEqual(evidence["profile"], review_boundary.PROFILE)
        self.assertEqual(evidence["format_version"], 1)
        self.assertIs(evidence["enforced"], True)
        self.assertIsNone(evidence["blocker"])
        self.assertTrue(evidence["bwrap_version"])
        self.assertRegex(evidence["bwrap_version"].lower(), r"bubble ?wrap")
        # Stated plainly so no reader can mistake this for adapter support: the
        # supervisor host and the host that enforced the boundary are both
        # recorded, and neither is a Windows or Codex sandbox claim.
        self.assertEqual(evidence["supervisor_host"],
                         review_boundary.supervisor_host())
        self.assertIn("Linux", evidence["sandbox_host"])
        self.assertTrue(evidence["launcher"])

        # -- the protected sentinel: denied, and provably unchanged ----------
        denials = evidence["denials"]
        self.assertTrue(denials, "preflight attempted no live write at all")
        rename_errno = evidence["rename_errno"]
        for name, attempt in sorted(denials.items()):
            self.assertIs(attempt["allowed"], False,
                          "attempt %s was not denied" % name)
            # A cross-mount escape (rename or hard link) is refused with EXDEV
            # because the two paths are on different mounts; that refusal is
            # the boundary property itself, not a privilege error.
            allowed_errnos = (review_boundary.CROSS_MOUNT_RENAME_ERRNOS
                              if attempt["syscall"]
                              in review_boundary.CROSS_MOUNT_SYSCALLS
                              else review_boundary.DENIAL_ERRNOS)
            self.assertIn(attempt["errno"], allowed_errnos,
                          "attempt %s denied with errno %r" % (name,
                                                               attempt["errno"]))
        self.assertIn(rename_errno, review_boundary.CROSS_MOUNT_RENAME_ERRNOS)
        covered = {attempt["syscall"] for attempt in denials.values()}
        for syscall in ("open-write", "open-append", "open-truncate", "unlink",
                        "mkdir", "rename", "link"):
            self.assertIn(syscall, covered)
        self.assertTrue(any(attempt["path"].startswith("/live/.git")
                            for attempt in denials.values()),
                        "the fake Git index was never probed for denial")

        sentinel = evidence["sentinel"]
        self.assertEqual(set(sentinel["files"]),
                         set(review_boundary.SENTINEL_FILES),
                         "preflight did not protect every sentinel kind")
        for rel, record in sorted(sentinel["files"].items()):
            self.assertEqual(record["sha256_before"], record["sha256_after"],
                             "sentinel %s bytes changed" % rel)
            self.assertEqual(record["mode_before"], record["mode_after"],
                             "sentinel %s metadata (mode) changed" % rel)
            self.assertEqual(record["size_before"], record["size_after"],
                             "sentinel %s size changed" % rel)
        # The protected file SET is re-enumerated supervisor-side too: a
        # successful create/mkdir/unlink would show here even if the sandboxed
        # process reported every single attempt as denied.
        self.assertEqual(sentinel["paths_before"], sentinel["paths_after"])
        self.assertGreaterEqual(len(sentinel["paths_before"]), 5)
        self.assertIn(".git/index", sentinel["paths_before"])
        self.assertTrue(sentinel["removed"])
        self.assertFalse(os.path.exists(
            self._meta(output, review_boundary.SENTINEL_DIR)),
            "preflight left its protected sentinel behind")

        # -- the declared scopes really are writable --------------------------
        self.assertEqual(evidence["writable"],
                         {"/snapshot": True, "/scratch": True, "/tmp": True,
                          "$HOME": True})
        self.assertEqual(evidence["cwd"], "/snapshot")

        # -- nothing outside the declared scopes is reachable -----------------
        for path in ("/meta", "/mnt", "/mnt/c", "/run", "/home", "/init",
                     "/tmp/.X11-unix"):
            self.assertIs(evidence["not_visible"][path], True,
                          "%s is reachable inside the boundary" % path)
        self.assertIs(evidence["network_denied"], True)
        # Network denial has to be proven by an errno that means "there is no
        # network at all", not by "the call failed": on a host that DOES have
        # network a firewalled destination merely times out and reports no
        # errno, which the old check scored as a denial. `--unshare-all` leaves
        # the namespace with no interface, so the real answer is ENETUNREACH.
        names = [item["name"] for item in evidence["network"]]
        self.assertEqual(names, ["dns", "connect"])
        self.assertEqual([item["name"] for item in evidence["network"]
                          if item["allowed"] is True], [],
                         "the sandboxed process reached the network")
        proof = [item for item in evidence["network"]
                 if item["name"] == review_boundary.NETWORK_PROOF_ATTEMPT]
        self.assertEqual(len(proof), 1)
        self.assertIn(proof[0]["errno"], review_boundary.NO_NETWORK_ERRNOS,
                      "the network attempt failed with %r, which does not "
                      "prove the absence of a network" % (proof[0]["errno"],))
        self.assertEqual(evidence["network_denial_errno"], proof[0]["errno"])
        self.assertIs(evidence["live_git_unavailable"], True)
        self.assertEqual(evidence["env_keys"],
                         ["HOME", "LC_CTYPE", "PATH", "PWD"])

        # -- mount roots are canonical and translated ------------------------
        roots = evidence["mount_roots"]
        for name in ("repo", "scratch", "meta"):
            self.assertIn(name, roots)
            host_path = os.path.realpath(os.path.join(output, name))
            self.assertEqual(roots[name]["host"], host_path)
            self.assertFalse(os.path.islink(os.path.join(output, name)))
            source = roots[name]["sandbox_source"]
            self.assertTrue(source.startswith("/"), source)
            self.assertNotIn("\\", source)
            self.assertNotIn(":", source[1:],
                             "untranslated drive letter in %r" % source)
            if os.name == "nt":
                self.assertTrue(source.startswith("/mnt/"), source)
        # `meta` is a verified root but never a mount: the supervisor's own
        # records stay outside the verifier's reach entirely.
        self.assertIs(evidence["meta_mounted"], False)

        # -- persisted evidence is exactly the returned evidence --------------
        with open(self._meta(output, "preflight.json"), "rb") as fh:
            self.assertEqual(json.loads(fh.read().decode("utf-8")), evidence)

        # -- preflight leaves the snapshot and the live tree pristine ---------
        self.assertEqual(self._receipt_files(output), receipts_before)
        self._assert_snapshot_pristine(output)
        self.assertEqual(records_before, self._record_bytes())
        self._assert_live_untouched(live)

    def _assert_snapshot_pristine(self, output):
        """No preflight proof file may survive inside the snapshot."""
        for base in (os.path.join(output, "repo"),
                     os.path.join(output, "scratch")):
            for dirpath, dirnames, filenames in os.walk(base):
                dirnames[:] = [d for d in dirnames if d != ".git"]
                for name in filenames:
                    self.assertNotIn("preflight", name,
                                     "preflight left %s in %s" % (name, base))

    # ========================================================================
    # 1b. The denial judge on its own: a *lying* report must be refused by name.
    # ========================================================================
    #
    # `preflight` proves enforcement by running an in-sandbox probe that reports
    # what it was allowed to do, and then judging that report against the
    # supervisor's own record of the protected sentinel. The real-sandbox legs
    # can only ever feed the judge honest reports — on this host writes genuinely
    # are denied — so a judge that accepted an allowed write, an ENOENT posing as
    # a denial, a missing cross-mount rename, a self-graded "network_denied":
    # true or a mutated sentinel would stay invisible to them. These legs drive
    # the judge with reports no sandbox produced, and each leg names the blocker
    # it expects.

    # The paths a report has to claim are unreachable. The pure legs use this
    # fixed set; the entry-point legs derive the context's real set.
    _ABSENT_PATHS = ("/meta", "/mnt", "/mnt/c", "/run", "/home", "/init",
                     "/tmp/.X11-unix")

    @staticmethod
    def _attempt(name, syscall, path, code):
        """One attempt, in the shape the probe template writes it."""
        return {"name": name, "syscall": syscall, "path": path,
                "allowed": code is None, "errno": code}

    def _attempts(self):
        """Every attempt the sandboxed probe makes, in its own order.

        Mirrored straight from `_PROBE_TEMPLATE` — same names, same syscall
        labels, same `/live` paths — so nothing here invents a report shape.
        """
        live = review_boundary.SANDBOX_LIVE
        files = list(review_boundary.SENTINEL_FILES)
        attempts = []
        for verb, syscall, code in (("overwrite", "open-write", errno.EROFS),
                                    ("append", "open-append", errno.EROFS),
                                    ("truncate", "open-truncate", errno.EACCES)):
            for rel in files:
                attempts.append(self._attempt("%s-%s" % (verb, _slug(rel)),
                                              syscall, "%s/%s" % (live, rel),
                                              code))
        attempts.append(self._attempt("create-new-file", "open-write",
                                      "%s/injected-source.py" % live,
                                      errno.EROFS))
        attempts.append(self._attempt("mkdir-live", "mkdir",
                                      "%s/injected-dir" % live, errno.EROFS))
        attempts.append(self._attempt("makedirs-live", "mkdir",
                                      "%s/injected-dir/deep" % live,
                                      errno.EROFS))
        attempts.append(self._attempt("chmod-sentinel", "chmod",
                                      "%s/%s" % (live, files[0]), errno.EPERM))
        attempts.append(self._attempt("symlink-into-snapshot", "symlink",
                                      "%s/escape" % live, errno.EROFS))
        attempts.append(self._attempt("hardlink-into-scratch", "link",
                                      "%s/%s" % (live, files[0]), errno.EXDEV))
        for label, index in (("rename-into-snapshot", 0),
                             ("rename-into-scratch", 1),
                             ("rename-into-tmp", 2)):
            attempts.append(self._attempt(label, "rename",
                                          "%s/%s" % (live, files[index]),
                                          errno.EXDEV))
        for rel in files:
            attempts.append(self._attempt("unlink-%s" % _slug(rel), "unlink",
                                          "%s/%s" % (live, rel), errno.EPERM))
        return attempts

    @staticmethod
    def _network():
        """What the real sandbox answers: DNS unresolvable, no route at all."""
        return [{"name": "dns", "allowed": False, "errno": -3,
                 "error": "gaierror: [Errno -3] Temporary failure in name "
                          "resolution"},
                {"name": "connect", "allowed": False,
                 "errno": LINUX["ENETUNREACH"],
                 "error": "OSError: [Errno %d] Network is unreachable"
                          % LINUX["ENETUNREACH"]}]

    def _report(self, **changes):
        """An honest probe report; then lie about exactly one part."""
        report = {
            "attempts": self._attempts(),
            "writable": dict((scope, True)
                             for scope in review_boundary.WRITABLE_SCOPES),
            "not_visible": dict((path, True) for path in self._ABSENT_PATHS),
            "network": self._network(),
            "cwd": review_boundary.SANDBOX_CWD,
            "env_keys": sorted(review_boundary.ALLOWED_ENV_KEYS),
            "git_env_keys": [],
            "sandbox_host": "Linux 6.6.0-synthetic (x86_64)",
            "sandbox_uid": 1000,
        }
        report.update(changes)
        return report

    def _observed(self, **changes):
        """The supervisor's own record of the sentinel it built for this pass."""
        context_root = os.path.join(self._out_tmp.name, "observed", "context")
        meta_root = os.path.join(context_root, "meta")
        digest = hashlib.sha256(b"protected sentinel bytes").hexdigest()
        paths = sorted(review_boundary.SENTINEL_FILES)
        observed = {
            "sentinel_root": os.path.join(meta_root,
                                          review_boundary.SENTINEL_DIR),
            "meta_root": meta_root,
            "context_root": context_root,
            "paths_before": paths,
            "paths_after": list(paths),
            "files": dict((rel, {"sha256_before": digest,
                                 "sha256_after": digest,
                                 "size_before": 24, "size_after": 24,
                                 "mode_before": 0o644, "mode_after": 0o644})
                           for rel in review_boundary.SENTINEL_FILES),
            }
        observed.update(changes)
        return observed

    def _judge(self, report, observed=_NO_OBSERVED):
        if observed is _NO_OBSERVED:
            observed = self._observed()
        return review_boundary._judge_probe_report(report,
                                                   list(self._ABSENT_PATHS),
                                                   observed)

    @staticmethod
    def _lie_file(observed, rel, **fields):
        """Move one sentinel record's after-half: bytes, mode or size changed."""
        files = dict(observed["files"])
        files[rel] = dict(files[rel], **fields)
        return dict(observed, files=files)

    @staticmethod
    def _lie_record(observed, rel, value):
        """Replace (`value`) or drop (`None`) one sentinel protection record."""
        files = dict(observed["files"])
        if value is None:
            files.pop(rel, None)
        else:
            files[rel] = value
        return dict(observed, files=files)

    @staticmethod
    def _lie_paths(observed, before=_NO_OBSERVED, after=_NO_OBSERVED):
        """Distort the supervisor's before/after enumeration of the sentinel."""
        observed = dict(observed)
        if before is not _NO_OBSERVED:
            observed["paths_before"] = before
        if after is not _NO_OBSERVED:
            observed["paths_after"] = after
        return observed

    def _assert_refused(self, report, blocker, observed=_NO_OBSERVED):
        """The judge must refuse this evidence, and name the reason."""
        with self.assertRaises(contracts.ContractError) as ctx:
            self._judge(report, observed)
        message = str(ctx.exception)
        self.assertEqual(message.split(":", 1)[0].strip(), blocker,
                          "expected blocker %s, got: %s" % (blocker, message))
        self.assertIn("profile %s cannot enforce the boundary"
                      % review_boundary.PROFILE, message)
        return message

    def _lie_attempts(self, report, names, **fields):
        """Rewrite named attempts; an unknown name is a broken leg."""
        remaining = set(names)
        for item in report["attempts"]:
            if item["name"] in remaining:
                item.update(fields)
                remaining.discard(item["name"])
        if remaining:
            raise AssertionError("no such probe attempt: %s"
                                 % ", ".join(sorted(remaining)))
        return report

    def _canned_probe(self, report):
        """Replace the sandboxed probe with a report of the test's choosing.

        Only the in-sandbox probe is replaced: the supervisor still builds its
        own protected sentinel, still re-enumerates it and still judges the
        report, so `preflight` itself is what these legs exercise.
        """
        payload = json.dumps(report, sort_keys=True).encode("utf-8") + b"\n"

        def captured(command):
            if "--version" in command:
                return 0, b"bubblewrap 0.9.0-synthetic\n", b""
            return 0, payload, b""
        return captured

    def _report_for_context(self, output, **changes):
        """An honest report whose reachability claims cover this real context."""
        context_root, roots = review_boundary._mount_roots(output)
        meta_root = roots[review_boundary._META_DIR]["host"]
        context = review_boundary._read_context(output)
        absent, _live = review_boundary._absent_probe_paths(context,
                                                            context_root,
                                                            meta_root, roots)
        report = self._report(not_visible=dict((path, True) for path in absent))
        report.update(changes)
        return report

    _EVIDENCE_VERSION = "bubblewrap 0.9.0-synthetic"

    def _evidence(self, **changes):
        """Accepted preflight evidence, shaped as `run()` reads it back."""
        roots = dict((name, {"host": "/synthetic/%s/host" % name,
                             "sandbox_source": "/synthetic/%s" % name})
                     for name in ("repo", "scratch", "meta"))
        evidence = {
            "format_version": review_boundary.FORMAT_VERSION,
            "profile": review_boundary.PROFILE,
            "enforced": True,
            "blocker": None,
            "meta_mounted": False,
            "cwd": review_boundary.SANDBOX_CWD,
            "denials": dict((item["name"], {"allowed": item["allowed"],
                                             "syscall": item["syscall"],
                                             "errno": item["errno"]})
                            for item in self._attempts()),
            "writable": dict((scope, True)
                             for scope in review_boundary.WRITABLE_SCOPES),
            "network_denied": True,
            "network_denial_errno": LINUX["ENETUNREACH"],
            "bwrap_version": self._EVIDENCE_VERSION,
            "supervisor_host": review_boundary.supervisor_host(),
            "launcher": review_boundary._launcher_label(),
            "sandbox_host": "Linux 6.6.0-synthetic (x86_64)",
            "sentinel": {"removed": True},
            "mount_roots": dict((name, dict(roots[name])) for name in roots),
            }
        evidence.update(changes)
        return evidence, roots

    def _assert_evidence_current(self, evidence, roots, expected):
        """Persisted evidence authorizes later runs, so it must split too."""
        self.assertIs(review_boundary._evidence_is_current(
            evidence, roots, self._EVIDENCE_VERSION), expected)

    def test_denial_judge_refuses_lying_probe_reports(self):
        # -- the control: an honest report is accepted, for the right reasons --
        # Without this leg, "the judge now refuses everything" and "the judge is
        # a no-op" both look like a passing test suite.
        denials, rename_errno, env_keys, network_errno = self._judge(
            self._report())
        self.assertEqual(set(denials),
                         set(item["name"] for item in self._attempts()),
                         "the judge did not record every attempted write")
        self.assertEqual([name for name, item in sorted(denials.items())
                          if item["allowed"]], [])
        self.assertEqual(rename_errno, LINUX["EXDEV"])
        self.assertEqual(env_keys, sorted(review_boundary.ALLOWED_ENV_KEYS))
        self.assertEqual(network_errno, LINUX["ENETUNREACH"])
        # The denial sets must be the numbers a LINUX sandbox reports, not this
        # host's: Windows shares Linux's EACCES/EPERM/EROFS/EXDEV/ENOENT but not
        # its network errnos, and a table read from the host would silently make
        # every real denial "not proof" (or, worse, accept 10051 as one).
        self.assertEqual(review_boundary.DENIAL_ERRNOS,
                         frozenset((LINUX["EACCES"], LINUX["EPERM"],
                                    LINUX["EROFS"])))
        self.assertEqual(review_boundary.CROSS_MOUNT_RENAME_ERRNOS,
                         frozenset((LINUX["EXDEV"],)))
        self.assertEqual(review_boundary.NO_NETWORK_ERRNOS,
                         frozenset((LINUX["EPERM"], LINUX["EACCES"],
                                    LINUX["ENETUNREACH"])))
        for code in (LINUX["EHOSTUNREACH"], LINUX["ECONNREFUSED"],
                     LINUX["ECONNRESET"], LINUX["ETIMEDOUT"],
                     LINUX["ENOENT"]):
            self.assertNotIn(code, review_boundary.NO_NETWORK_ERRNOS)

        report_legs = (
            # A write the sandbox was *allowed* to make is the plan's "a sandbox
            # that launches but permits live writes is unsupported" case.
            ("an overwrite the sandbox reported as allowed",
             lambda r: self._lie_attempts(
                 r, {"overwrite-%s" % _slug(review_boundary.SENTINEL_FILES[0])},
                 allowed=True, errno=None),
             review_boundary.LIVE_WRITE_ALLOWED),
            ("a cross-mount rename the sandbox reported as allowed",
             lambda r: self._lie_attempts(r, {"rename-into-snapshot"},
                                          allowed=True, errno=None),
             review_boundary.LIVE_WRITE_ALLOWED),
            ("a hard link into /scratch the sandbox reported as allowed",
             lambda r: self._lie_attempts(r, {"hardlink-into-scratch"},
                                          allowed=True, errno=None),
             review_boundary.LIVE_WRITE_ALLOWED),
            ("a create-new-file the sandbox reported as allowed",
             lambda r: self._lie_attempts(r, {"create-new-file"},
                                          allowed=True, errno=None),
             review_boundary.LIVE_WRITE_ALLOWED),
            # ENOENT means the file was never there to be protected, which is
            # not a boundary — the sentinel would simply have been missing.
            ("a denial reported as ENOENT",
             lambda r: self._lie_attempts(
                 r,
                 {"unlink-%s" % _slug(".git/index")}, allowed=False,
                 errno=errno.ENOENT),
             review_boundary.DENIAL_UNVERIFIED),
            ("a denial reported as ENOTDIR",
             lambda r: self._lie_attempts(
                 r, {"append-%s" % _slug("config.toml")}, allowed=False,
                 errno=errno.ENOTDIR),
             review_boundary.DENIAL_UNVERIFIED),
            ("an attempt that failed reporting no errno at all",
             lambda r: self._lie_attempts(
                 r, {"truncate-%s" % _slug("fixture.json")}, allowed=False,
                 errno=None),
             review_boundary.DENIAL_UNVERIFIED),
            # EXDEV is the escape-refusal signature; a privilege error there is
            # not evidence that the mount boundary held.
            ("a cross-mount rename denied with EACCES instead of EXDEV",
             lambda r: self._lie_attempts(r, {"rename-into-scratch"},
                                          allowed=False, errno=errno.EACCES),
             review_boundary.DENIAL_UNVERIFIED),
            ("a report that never exercised the cross-mount escape",
             lambda r: dict(r, attempts=[
                 item for item in r["attempts"]
                 if item["syscall"] not in
                 review_boundary.CROSS_MOUNT_SYSCALLS]),
             review_boundary.UNSUPPORTED_RUNTIME_LAYOUT),
            ("a report with no write attempts at all",
             lambda r: dict(r, attempts=[]),
             review_boundary.PROBE_REPORT_UNREADABLE),
            ("a report whose attempts are not attempt objects",
             lambda r: dict(r, attempts=["everything was denied"]),
             review_boundary.PROBE_REPORT_UNREADABLE),
            ("a report that is not a report",
             lambda r: [],
             review_boundary.PROBE_REPORT_UNREADABLE),
            # -- declared writable scope ------------------------------------
            ("a writable-scope claim that omits /snapshot",
             lambda r: dict(r, writable={
                 scope: True for scope in review_boundary.WRITABLE_SCOPES
                 if scope != "/snapshot"}),
             review_boundary.WRITABLE_SCOPE_UNAVAILABLE),
            ("a writable-scope claim that omits /scratch",
             lambda r: dict(r, writable={
                 scope: True for scope in review_boundary.WRITABLE_SCOPES
                 if scope != "/scratch"}),
             review_boundary.WRITABLE_SCOPE_UNAVAILABLE),
            ("a writable scope that is merely truthy, not proven",
             lambda r: dict(r, writable=dict(
                 r["writable"], **{"/tmp": 1})),
             review_boundary.WRITABLE_SCOPE_UNAVAILABLE),
            ("a writable scope that reported failure",
             lambda r: dict(r, writable=dict(
                 r["writable"], **{"$HOME": False})),
             review_boundary.WRITABLE_SCOPE_UNAVAILABLE),
            ("a report with no writable-scope evidence at all",
             lambda r: dict(r, writable=None),
             review_boundary.WRITABLE_SCOPE_UNAVAILABLE),
            # -- reachability ------------------------------------------------
            ("a host path the sandbox could still see",
             lambda r: dict(r, not_visible=dict(
                 r["not_visible"], **{"/meta": False})),
             review_boundary.HOST_SCOPE_REACHABLE),
            ("a report with no reachability evidence at all",
             lambda r: dict(r, not_visible=None),
             review_boundary.HOST_SCOPE_REACHABLE),
            # -- network: only "there is no network" counts as a denial ------
            # A resolvable name IS network, even where one raw connect happens to
            # be refused. This is the only leg that refuses it: the connect half
            # of the same report is a textbook ENETUNREACH, so the errno rule
            # alone would wave it through.
            ("a report whose name resolution succeeded while connect was "
             "refused",
             lambda r: dict(r, network=[
                 {"name": "dns", "allowed": True, "errno": None,
                  "error": "succeeded"}, r["network"][1]]),
             review_boundary.NETWORK_PERMITTED),
            ("a report whose connect succeeded",
             lambda r: dict(r, network=[
                 r["network"][0],
                 {"name": "connect", "allowed": True, "errno": None,
                  "error": "succeeded"}]),
             review_boundary.NETWORK_PERMITTED),
            # The reviewer's measurement: on a *shared* network namespace this
            # connect times out with no errno at all, and the old check filed
            # that as a denial.
            ("a connect that merely timed out, carrying no errno",
             lambda r: dict(r, network=[
                 r["network"][0],
                 {"name": "connect", "allowed": False, "errno": None,
                  "error": "TimeoutError: timed out"}]),
             review_boundary.NETWORK_PERMITTED),
            ("a connect refused by something that answered",
             lambda r: dict(r, network=[
                 r["network"][0],
                 {"name": "connect", "allowed": False,
                  "errno": LINUX["ECONNREFUSED"],
                  "error": "ConnectionRefusedError: [Errno 111] Connection "
                           "refused"}]),
             review_boundary.NETWORK_PERMITTED),
            ("a connect reset mid-session",
             lambda r: dict(r, network=[
                 r["network"][0],
                 {"name": "connect", "allowed": False,
                  "errno": LINUX["ECONNRESET"],
                  "error": "ConnectionResetError: [Errno 104] Connection reset "
                           "by peer"}]),
             review_boundary.NETWORK_PERMITTED),
            # EHOSTUNREACH needs a live route to produce: it is what a rejecting
            # firewall on a networked host answers, never what an absent network
            # answers, so it cannot prove the boundary has no network.
            ("a connect rejected as host-unreachable",
             lambda r: dict(r, network=[
                 r["network"][0],
                 {"name": "connect", "allowed": False,
                  "errno": LINUX["EHOSTUNREACH"],
                  "error": "OSError: [Errno 113] No route to host"}]),
             review_boundary.NETWORK_PERMITTED),
            ("a connect that timed out carrying ETIMEDOUT",
             lambda r: dict(r, network=[
                 r["network"][0],
                 {"name": "connect", "allowed": False,
                  "errno": LINUX["ETIMEDOUT"],
                  "error": "OSError: [Errno 110] Connection timed out"}]),
             review_boundary.NETWORK_PERMITTED),
            # The report may not grade itself: `network_denied: true` was the
            # old self-reported flag, and it means nothing next to a timeout.
            ("a network denial the report graded for itself",
             lambda r: dict(r, network=[
                 r["network"][0],
                 {"name": "connect", "allowed": False, "errno": None,
                  "error": "TimeoutError: timed out"}],
                 network_denied=True),
             review_boundary.NETWORK_PERMITTED),
            # Coverage: the judge scores both attempts or none of them.
            ("a report that attempted no network call at all",
             lambda r: dict(r, network=[]),
             review_boundary.NETWORK_PERMITTED),
            ("a report that never attempted an outbound connect",
             lambda r: dict(r, network=[r["network"][0]]),
             review_boundary.NETWORK_PERMITTED),
            ("a report that never attempted a name resolution",
             lambda r: dict(r, network=[r["network"][1]]),
             review_boundary.NETWORK_PERMITTED),
            ("a report carrying an attempt profile %s does not know"
             % review_boundary.PROFILE,
             lambda r: dict(r, network=list(r["network"]) + [
                 {"name": "udp", "allowed": False,
                  "errno": LINUX["ENETUNREACH"], "error": "OSError"}]),
             review_boundary.NETWORK_PERMITTED),
            ("a report whose network evidence is not shaped",
             lambda r: dict(r, network={"connect": "denied"}),
             review_boundary.NETWORK_PERMITTED),
            ("a report whose network attempts have no names",
             lambda r: dict(r, network=[{"allowed": False, "errno": None},
                                        {"allowed": False,
                                         "errno": LINUX["ENETUNREACH"]}]),
             review_boundary.NETWORK_PERMITTED),
            # -- environment and cwd ----------------------------------------
            ("an inherited environment key that survived into the sandbox",
             lambda r: dict(r, env_keys=sorted(
                 list(review_boundary.ALLOWED_ENV_KEYS) + ["SSH_AUTH_SOCK"])),
             review_boundary.ENVIRONMENT_NOT_SANITIZED),
            ("a GIT_* override that survived into the sandbox",
             lambda r: dict(r, git_env_keys=["GIT_DIR", "GIT_WORK_TREE"]),
             review_boundary.ENVIRONMENT_NOT_SANITIZED),
            ("a report from the wrong cwd",
             lambda r: dict(r, cwd="/live"),
             review_boundary.UNSUPPORTED_RUNTIME_LAYOUT),
            ("a report from the snapshot root instead of the pinned cwd",
             lambda r: dict(r, cwd="/"),
             review_boundary.UNSUPPORTED_RUNTIME_LAYOUT),
        )

        for label, lie, blocker in report_legs:
            with self.subTest(label):
                self._assert_refused(lie(self._report()), blocker)

        observation_legs = (
            ("sentinel bytes changed while the report claimed denial",
             lambda o: self._lie_file(o, "source.py",
                                      sha256_after=hashlib.sha256(
                                          b"overwritten by the verifier").
                                          hexdigest()),
             review_boundary.SENTINEL_CHANGED),
            ("sentinel mode changed",
             lambda o: self._lie_file(o, "config.toml", mode_after=0o777),
             review_boundary.SENTINEL_CHANGED),
            ("sentinel size changed",
             lambda o: self._lie_file(o, "fixture.json", size_after=9999),
             review_boundary.SENTINEL_CHANGED),
            ("a sentinel record that is not a record",
             lambda o: self._lie_record(o, "test_source.py", "unreadable"),
             review_boundary.SENTINEL_CHANGED),
            ("the sentinel grew a file the sandbox created",
             lambda o: self._lie_paths(o, after=list(o["paths_after"])
                                       + ["injected-source.py"]),
             review_boundary.SENTINEL_CHANGED),
            ("the sentinel lost a file the sandbox unlinked",
             lambda o: self._lie_paths(
                 o, after=[path for path in o["paths_after"]
                           if path != ".git/index"]),
             review_boundary.SENTINEL_CHANGED),
            ("the sentinel was never enumerated at all",
             lambda o: self._lie_paths(o, before=[], after=[]),
             review_boundary.SENTINEL_CHANGED),
            ("one sentinel kind carries no protection record",
             lambda o: self._lie_record(o, "fixture.json", None),
             review_boundary.SENTINEL_CHANGED),
            ("the supervisor recorded no observation for the report",
             lambda o: None,
             review_boundary.SENTINEL_CHANGED),
            ("the sentinel is not supervisor-owned",
             lambda o: dict(o, sentinel_root=os.path.join(self.root, ".git")),
             review_boundary.SENTINEL_ROOT_NOT_ISOLATED),
            ("the sentinel root is the meta directory itself",
             lambda o: dict(o, sentinel_root=o["meta_root"]),
             review_boundary.SENTINEL_ROOT_NOT_ISOLATED),
            ("the sentinel root is not inside the meta directory",
             lambda o: dict(o, sentinel_root=os.path.join(
                 o["context_root"], review_boundary.SENTINEL_DIR)),
             review_boundary.SENTINEL_ROOT_NOT_ISOLATED),
            ("the sentinel would contain the review context root",
             lambda o: dict(
                 o,
                 meta_root=os.path.join(self._out_tmp.name, "nested", "meta"),
                 sentinel_root=os.path.join(self._out_tmp.name, "nested",
                                            "meta",
                                            review_boundary.SENTINEL_DIR),
                 context_root=os.path.join(self._out_tmp.name, "nested", "meta",
                                           review_boundary.SENTINEL_DIR,
                                           "context")),
             review_boundary.SENTINEL_ROOT_NOT_ISOLATED),
            ("the supervisor recorded no sentinel root at all",
             lambda o: dict(o, sentinel_root=None),
             review_boundary.SENTINEL_ROOT_NOT_ISOLATED),
        )
        for label, distort, blocker in observation_legs:
            with self.subTest(label):
                self._assert_refused(self._report(), blocker,
                                     observed=distort(self._observed()))

        # -- what `run()` will accept as proof when it reads it back ----------
        # The judge is only half the story: a persisted preflight record is what
        # authorizes every later run, so the acceptance check has to
        # discriminate on the same evidence and must not be satisfied by a claim.
        evidence, roots = self._evidence()
        self._assert_evidence_current(evidence, roots, True)

        def without(item, key):
            return dict((name, value) for name, value in item.items()
                        if name != key)

        def allowed_denial(item):
            name = "overwrite-%s" % _slug(review_boundary.SENTINEL_FILES[0])
            denials = dict(item["denials"])
            denials[name] = dict(denials[name], allowed=True, errno=None)
            return dict(item, denials=denials)

        def missing_scope(item, scope):
            return dict(item, writable=without(item["writable"], scope))

        evidence_legs = (
            ("evidence carrying no network denial errno",
             lambda e: without(e, "network_denial_errno")),
            ("evidence whose network failure proves nothing (EHOSTUNREACH)",
             lambda e: dict(e, network_denial_errno=LINUX["EHOSTUNREACH"])),
            ("evidence whose network failure was a timeout",
             lambda e: dict(e, network_denial_errno=None)),
            ("evidence that merely claims the network was denied",
             lambda e: dict(e, network_denied=False)),
            ("evidence recording a write the sandbox was allowed to make",
             allowed_denial),
            ("evidence that never proved /snapshot writable",
             lambda e: missing_scope(e, "/snapshot")),
            ("evidence that never proved /scratch writable",
             lambda e: missing_scope(e, "/scratch")),
            ("evidence with an unremoved protected sentinel",
             lambda e: dict(e, sentinel={"removed": False})),
        )
        for label, distort in evidence_legs:
            with self.subTest(label):
                self._assert_evidence_current(distort(evidence), roots, False)

        # -- the judge is on preflight's real path ---------------------------
        # The same reports, delivered through the public entry point instead of
        # called directly: a refusal must name its blocker, must launch nothing,
        # and must leave behind `enforced: false` evidence rather than a passing
        # claim. The honest case is here too, because it is what proves the
        # canned report really reached the judge — without it every refusing leg
        # above could be passing for the wrong reason.
        self.prepare_v2_review()
        timeout_report = lambda r: dict(r, network=[  # noqa: E731
            r["network"][0],
            {"name": "connect", "allowed": False, "errno": None,
             "error": "TimeoutError: timed out"}])
        cases = (
            ("an honest report, judged through preflight", lambda r: r, None),
            ("an allowed live write",
             lambda r: self._lie_attempts(
                 r, {"overwrite-%s" % _slug(review_boundary.SENTINEL_FILES[0])},
                 allowed=True, errno=None),
             review_boundary.LIVE_WRITE_ALLOWED),
            ("a network timeout", timeout_report,
             review_boundary.NETWORK_PERMITTED),
        )
        for index, (label, lie, blocker) in enumerate(cases):
            with self.subTest("preflight entry point: %s" % label):
                _context, output = self._prepare(
                    output=self._new_output("lying-%d" % index))
                report = lie(self._report_for_context(output))
                calls = self._seam(self._never_launches)
                with self._scoped("_probe_captured", self._canned_probe(report)):
                    if blocker is None:
                        evidence = review_boundary.preflight(output)
                    else:
                        with self.assertRaises(contracts.ContractError) as ctx:
                            review_boundary.preflight(output)
                        evidence = None
                self.assertEqual(calls, [],
                                 "a canned report reached the judge by "
                                 "launching a real sandbox")
                self.assertFalse(os.path.exists(
                    self._meta(output, review_boundary.SENTINEL_DIR)),
                    "preflight left its protected sentinel behind")
                persisted = json.loads(self._read_bytes(
                    self._meta(output, "preflight.json")).decode("utf-8"))
                if blocker is None:
                    self.assertIs(evidence["enforced"], True)
                    self.assertIsNone(evidence["blocker"])
                    self.assertEqual(persisted, evidence)
                    self.assertEqual(
                        evidence["network_denial_errno"],
                        LINUX["ENETUNREACH"])
                    self.assertEqual(sorted(evidence["sentinel"]
                                             ["paths_before"]),
                                     sorted(review_boundary.SENTINEL_FILES))
                else:
                    message = str(ctx.exception)
                    self.assertEqual(message.split(":", 1)[0].strip(), blocker,
                                     message)
                    self.assertIs(persisted["enforced"], False)
                    self.assertEqual(persisted["blocker"], blocker)
                    self._assert_no_enforced_receipt(output)

    # ========================================================================
    # 2. Every unavailable or misconfigured boundary fails closed, by name.
    # ========================================================================

    def test_unavailable_boundary_is_closed(self):
        self.prepare_v2_review()

        # (a) The bwrap executable is not available at all.
        with self.subTest("bwrap executable missing"):
            _context, output = self._prepare(output=self._new_output("missing"))
            calls = self._seam(self._missing_executable)
            with self.assertRaises(contracts.ContractError) as ctx:
                review_boundary.run(output, "probe", ["true"])
            self.assertIn(review_boundary.BWRAP_EXECUTABLE_NOT_FOUND,
                          str(ctx.exception))
            self.assertTrue(calls, "the launcher was never consulted, so the "
                                   "unavailable host was never actually probed")
            self._assert_no_enforced_receipt(output)
            # Preflight reports the same blocker rather than an unspecified
            # failure, so an unavailable host is named, never guessed at.
            with self.assertRaises(contracts.ContractError) as ctx:
                review_boundary.preflight(output)
            self.assertIn(review_boundary.BWRAP_EXECUTABLE_NOT_FOUND,
                          str(ctx.exception))
            self._assert_no_enforced_receipt(output)

        # (b) Namespace creation is denied: bwrap itself refuses to start.
        with self.subTest("namespace creation denied"):
            _context, output = self._prepare(output=self._new_output("denied"))
            calls = self._seam(self._denied_namespace)
            with self.assertRaises(contracts.ContractError) as ctx:
                review_boundary.preflight(output)
            self.assertIn(review_boundary.NAMESPACE_CREATION_DENIED,
                          str(ctx.exception))
            self.assertTrue(calls, "the boundary was never attempted")
            # The frozen launch shape: no shell in front of it, bwrap itself,
            # and every real launch separated from the inner command by `--`.
            for command in calls:
                self.assertNotIn(command[0], ("sh", "bash", "cmd", "/bin/sh",
                                              "cmd.exe"),
                                 "the boundary was started through a shell")
            self.assertTrue(any("bwrap" in command for command in calls), calls)
            launched = [command for command in calls if "--version"
                        not in command]
            self.assertTrue(launched, "no boundary launch was attempted")
            for command in launched:
                self.assertIn("--", command,
                              "no argument separator: the inner command could "
                              "be parsed as bwrap options")
            self._assert_no_enforced_receipt(output)

            # A run must not fall back to an unconstrained launch either.
            run_calls = self._seam(self._denied_namespace)
            with self.assertRaises(contracts.ContractError) as ctx:
                review_boundary.run(output, "probe", ["true"])
            self.assertIn(review_boundary.NAMESPACE_CREATION_DENIED,
                          str(ctx.exception))
            self.assertTrue(run_calls)
            for command in run_calls:
                self.assertNotIn(command[0], ("sh", "bash", "cmd", "/bin/sh",
                                              "cmd.exe"),
                                 "the boundary was started through a shell")
                if "--version" not in command:
                    self.assertIn("--", command,
                                  "no argument separator: the inner command "
                                  "could be parsed as bwrap options")
            self._assert_no_enforced_receipt(output)

            # The classifier is pinned directly: only bwrap's own setup marker,
            # with nothing captured from the inner process, is a boundary
            # failure. A verifier that merely exits nonzero is not.
            classify = review_boundary.classify_boundary_failure
            marker = "bwrap: setting up uid map: Permission denied\n"
            self.assertEqual(classify(1, b"", marker),
                             review_boundary.NAMESPACE_CREATION_DENIED)
            self.assertIsNone(
                classify(1, b"", "bwrap: setting up uid map: Permission denied\n"
                                 "verifier said something\n"),
                "a verifier's own output must not read as a boundary failure")
            self.assertIsNone(classify(1, b"ran\n", "bwrap: nope\n"))
            self.assertIsNone(classify(3, b"", "assertion failed\n"))
            self.assertIsNone(classify(0, b"", ""))

        # (c) An unapproved mount root: a bind source outside the context.
        with self.subTest("unapproved mount root"):
            _context, output = self._prepare(
                output=self._new_output("unapproved"))
            calls = self._seam(self._never_launches)
            with self._scoped("_extra_bind_specs",
                              lambda cp: [("--bind", "/etc", "/elsewhere")]):
                with self.assertRaises(contracts.ContractError) as ctx:
                    review_boundary.run(output, "probe", ["true"])
            self.assertIn(review_boundary.UNAPPROVED_MOUNT_ROOT,
                          str(ctx.exception))
            self.assertIs(review_boundary._extra_bind_specs,
                          self._pristine_seams["_extra_bind_specs"],
                          "the injected foreign bind outlived its subtest")
            self.assertEqual(calls, [], "an unapproved mount root was launched")
            self._assert_no_enforced_receipt(output)

        # (d) Shared writable Git metadata behind the snapshot: a copy or a
        #     symlink that reaches live Git is not isolation.
        for label, tamper in (
                ("gitdir-pointer", "_tamper_gitdir_pointer"),
                ("alternates", "_tamper_alternates"),
                ("git-symlink", "_tamper_git_symlink")):
            with self.subTest("shared writable Git: %s" % label):
                _context, output = self._prepare(
                    output=self._new_output("git-%s" % label))
                getattr(self, tamper)(output)
                calls = self._seam(self._never_launches)
                with self.assertRaises(contracts.ContractError) as ctx:
                    review_boundary.run(output, "probe", ["true"])
                self.assertIn(review_boundary.SHARED_WRITABLE_GIT_METADATA,
                              str(ctx.exception))
                self.assertEqual(calls, [],
                                 "shared writable Git was launched anyway")
                self._assert_no_enforced_receipt(output)

        # (e) A context layout that cannot be represented as the frozen mounts.
        for label, present, missing in (
                ("missing repo", ("scratch", "meta"), "repo"),
                ("missing scratch", ("repo", "meta"), "scratch"),
                ("missing meta", ("repo", "scratch"), "meta")):
            with self.subTest("context layout: %s" % label):
                output = self._new_output("layout-%s" % label.split()[-1])
                for part in present:
                    os.makedirs(os.path.join(output, part))
                calls = self._seam(self._never_launches)
                with self.assertRaises(contracts.ContractError) as ctx:
                    review_boundary.run(output, "probe", ["true"])
                self.assertIn(review_boundary.CONTEXT_LAYOUT_NOT_REPRESENTABLE,
                              str(ctx.exception))
                self.assertEqual(calls, [])

        # (f) A layout root that is not a real directory under the context —
        #     a symlink reaching elsewhere, or nothing at all — is refused,
        #     never followed. Windows may not grant symlink privilege, in which
        #     case the same "not a real directory inside the context" refusal is
        #     exercised without the link.
        with self.subTest("layout root is never followed"):
            output = self._new_output("escaping")
            elsewhere = self._new_output("elsewhere-repo")
            os.makedirs(elsewhere)
            os.makedirs(os.path.join(output, "scratch"))
            os.makedirs(os.path.join(output, "meta"))
            link = os.path.join(output, "repo")
            try:
                os.symlink(elsewhere, link)
                linked = True
            except (OSError, NotImplementedError):
                linked = False
            calls = self._seam(self._never_launches)
            with self.assertRaises(contracts.ContractError) as ctx:
                review_boundary.run(output, "probe", ["true"])
            self.assertIn(review_boundary.CONTEXT_LAYOUT_NOT_REPRESENTABLE,
                          str(ctx.exception))
            self.assertEqual(calls, [], "an escaping root was launched anyway")
            if linked:
                # Prove the refusal is about the link, not the missing directory:
                # the target exists and is a real directory.
                self.assertTrue(os.path.isdir(elsewhere))

        # (g) `kind` is a closed set and argv must be a real command.
        with self.subTest("closed kind set and argv"):
            _context, output = self._prepare(output=self._new_output("kind"))
            calls = self._seam(self._never_launches)
            for bad_kind in ("acceptance", "", "BASELINE", None, 1, "baseline "):
                with self.assertRaises(contracts.ContractError):
                    review_boundary.run(output, bad_kind, ["true"])
            for bad_argv in ([], [""], None, "true", ["python3", ""],
                             ["--bind", "/"], ["python3", "-c", "x", "\0"]):
                with self.assertRaises(contracts.ContractError):
                    review_boundary.run(output, "probe", bad_argv)
            self.assertEqual(calls, [],
                             "invalid usage still reached the launcher")

        # (h) Preflight never probes a real live tree: its sentinel must be
        #     created inside the supervisor-owned meta area, nowhere else.
        with self.subTest("preflight sentinel stays supervisor-owned"):
            _context, output = self._prepare(output=self._new_output("sentinel"))
            live_git = os.path.join(self.root, ".git")
            sentinel_files_before = sorted(os.listdir(live_git))
            calls = self._seam(self._never_launches)
            self._patch("_sentinel_root", lambda cp: live_git)
            with self.assertRaises(contracts.ContractError) as ctx:
                review_boundary.preflight(output)
            self.assertIn(review_boundary.SENTINEL_ROOT_NOT_ISOLATED,
                          str(ctx.exception))
            self.assertEqual(calls, [], "preflight launched before checking")
            self.assertEqual(sorted(os.listdir(live_git)), sentinel_files_before,
                             "preflight wrote inside the live Git directory")
            self.assertFalse(os.path.exists(
                os.path.join(live_git, review_boundary.SENTINEL_DIR)))

        # (i) The public CLI: bad usage exits 2, a boundary blocker exits 1, and
        #     neither produces a receipt or any claim of enforcement.
        with self.subTest("run-review usage and blocker exit codes"):
            _context, output = self._prepare(
                output=self._new_output("cli-usage"))
            proc = self.cli("run-review", self.TICKET, "--review-context",
                            output, "--kind", "probe")
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            proc = self.cli("run-review", self.TICKET, "--review-context",
                            output, "--kind", "verifier", "--", "true")
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            proc = self.cli("run-review", self.TICKET, "--review-context",
                            output, "--kind", "probe", "--")
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            proc = self.cli("run-review", self.TICKET, "--kind", "probe",
                            "--", "true")
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            proc = self.cli("run-review", self.TICKET, "--review-context",
                            output, "--", "true")
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)

            # A context whose currentness cannot be re-verified is refused (1),
            # not launched and not recorded.
            broken = self._new_output("broken-cli")
            os.makedirs(os.path.join(broken, "repo"))
            proc = self.cli("run-review", self.TICKET, "--review-context",
                            broken, "--kind", "probe", "--", "true")
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertEqual(self._receipt_files(broken), [])

            # A context whose layout cannot be mounted fails closed with a
            # named blocker (1) and no receipt. The manifest is still current,
            # so this is the boundary refusing, not a stale-baseline refusal.
            _unused, partial = self._prepare(
                output=self._new_output("no-scratch"))
            shutil.rmtree(os.path.join(partial, "scratch"))
            proc = self.cli("run-review", self.TICKET, "--review-context",
                            partial, "--kind", "probe", "--", "true")
            self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
            self.assertNotIn("Traceback", proc.stderr)
            self.assertIn(review_boundary.CONTEXT_LAYOUT_NOT_REPRESENTABLE,
                          proc.stderr)
            self.assertEqual(self._receipt_files(partial), [])

    def _tamper_gitdir_pointer(self, output):
        """Replace the snapshot's own Git dir with a pointer to a foreign one."""
        repo = os.path.join(output, "repo")
        git_dir = os.path.join(repo, ".git")
        elsewhere = os.path.join(self._out_tmp.name, "shared-git-dir")
        os.makedirs(elsewhere, exist_ok=True)
        os.rename(git_dir, git_dir + ".real")
        self._write_bytes(git_dir, "gitdir: %s\n" % elsewhere)

    def _tamper_alternates(self, output):
        """Give the snapshot shared object storage pointing at the live repo."""
        info = os.path.join(output, "repo", ".git", "objects", "info")
        os.makedirs(info, exist_ok=True)
        live_objects = os.path.join(self.root, ".git", "objects")
        self._write_bytes(os.path.join(info, "alternates"),
                          "%s\n" % live_objects)

    def _tamper_git_symlink(self, output):
        """Point the snapshot's `.git` at another directory through a link."""
        repo = os.path.join(output, "repo")
        git_dir = os.path.join(repo, ".git")
        elsewhere = os.path.join(self._out_tmp.name, "symlinked-git-dir")
        os.makedirs(elsewhere, exist_ok=True)
        os.rename(git_dir, git_dir + ".real")
        try:
            os.symlink(elsewhere, git_dir)
        except (OSError, NotImplementedError):
            # No symlink privilege here: an absolute `gitdir:` pointer expresses
            # the same unapproved reach and keeps this leg running everywhere.
            self._write_bytes(git_dir, "gitdir: %s\n" % elsewhere)

    # ========================================================================
    # 3. Receipts keep failures honest and the scope pinned.
    # ========================================================================

    def test_receipts_preserve_failures_and_scope(self):
        self.prepare_v2_review()
        _context, output = self._prepare()
        repo = os.path.join(output, "repo")
        context_bytes_before = self._context_json_bytes(output)
        records_before = self._record_bytes()
        live = self._live_untouched()

        evidence = self._preflight_or_skip(output)
        self.assertEqual(self._receipt_files(output), [])

        orig_feature = self._read_bytes(os.path.join(repo, "src", "feature.py"))
        orig_app = self._read_bytes(os.path.join(repo, "src", "app.py"))
        app_mode = os.stat(os.path.join(repo, "src", "app.py")).st_mode & 0o7777

        # -- (1) a failing run is recorded with its own exit status -----------
        failing_argv = ["python3", "-c", FAILING_COMMAND_SCRIPT]
        first = self._run_or_skip(output, "baseline", failing_argv)
        self._check_receipt_shape(output, first, "baseline", failing_argv,
                                  evidence)
        self.assertEqual(first["exit_code"], 3,
                         "a failing verifier's exit code was not preserved")
        self.assertIsNone(first["blocker"])
        self.assertIs(first["boundary"]["enforced"], True)
        self.assertEqual(first["snapshot_before"], first["snapshot_after"])
        self.assertEqual(first["changed_paths"], [])
        self.assertEqual(first["added_paths"], [])
        self.assertEqual(first["removed_paths"], [])
        self._assert_captured(output, first, "stdout", b"failing-stdout")
        self.assertIn(b"cwd /snapshot",
                      self._read_bytes(self._receipt_output_abs(
                          output, first, "stdout")))
        self._assert_captured(output, first, "stderr", b"failing-stderr")
        self.assertEqual(len(self._receipt_files(output)), 1)

        # The first baseline pins the snapshot identity it accepted.
        with open(self._meta(output, "baseline.json"), "rb") as fh:
            baseline = json.loads(fh.read().decode("utf-8"))
        self.assertEqual(baseline["snapshot_identity"], first["snapshot_before"])
        self.assertEqual(baseline["run_id"], first["run_id"])
        self.assertEqual(baseline["kind"], "baseline")

        # -- (2) a successful probe records its residual changes --------------
        probe_argv = ["python3", "-c", PROBE_EDIT_SCRIPT]
        probe = self._run_or_skip(output, "probe", probe_argv)
        self._check_receipt_shape(output, probe, "probe", probe_argv, evidence)
        self.assertEqual(probe["exit_code"], 0)
        self.assertNotEqual(probe["run_id"], first["run_id"])
        self.assertEqual(probe["changed_paths"], ["src/feature.py"])
        self.assertEqual(probe["added_paths"], ["probe_added.py"])
        self.assertEqual(probe["removed_paths"], ["src/app.py"])
        self.assertNotEqual(probe["snapshot_before"], probe["snapshot_after"])
        self.assertEqual(probe["snapshot_before"], first["snapshot_after"])

        # The supervisor's meta was unreachable, and the probe's own account of
        # that agrees with the bytes still on disk.
        captured = self._read_bytes(
            self._receipt_output_abs(output, probe, "stdout")).decode("utf-8")
        reported = json.loads(captured.strip().splitlines()[-1])
        self.assertEqual(reported["cwd"], "/snapshot")
        self.assertIs(reported["meta_visible"], False)
        for key in ("write_context.json", "write_preflight.json"):
            self.assertNotEqual(reported[key], "ALLOWED",
                                "%s was writable from inside the sandbox" % key)
            self.assertIn(reported[key], DENIED_META_WRITE_ERRNOS)
        self.assertEqual(self._context_json_bytes(output), context_bytes_before)
        self.assertTrue(os.path.exists(os.path.join(output, "scratch",
                                                    "probe-note.txt")),
                        "the declared writable scratch scope was not usable")
        self.assertEqual(len(self._receipt_files(output)), 2)
        # A probe never re-pins the baseline.
        with open(self._meta(output, "baseline.json"), "rb") as fh:
            self.assertEqual(json.loads(fh.read().decode("utf-8"))["run_id"],
                             first["run_id"])

        # -- (3) a drifted snapshot refuses further baseline runs -------------
        refused_argv = ["python3", "-c", UNCHANGED_COMMAND_SCRIPT]
        with self.assertRaises(contracts.ContractError) as ctx:
            review_boundary.run(output, "baseline", refused_argv)
        self.assertIn(review_boundary.BASELINE_IDENTITY_DRIFT,
                      str(ctx.exception))
        self.assertEqual(len(self._receipt_files(output)), 2,
                         "a refused baseline wrote a receipt")

        # A probe is never blocked by the baseline pin.
        second_probe = self._run_or_skip(output, "probe", refused_argv)
        self._check_receipt_shape(output, second_probe, "probe", refused_argv,
                                  evidence)
        self.assertEqual(second_probe["exit_code"], 0)
        self.assertEqual(second_probe["changed_paths"], [])
        self.assertEqual(second_probe["added_paths"], [])
        self.assertEqual(second_probe["removed_paths"], [])
        self.assertEqual(len(self._receipt_files(output)), 3)

        # -- (4) restoring the snapshot allows another recorded baseline -----
        self._write_bytes(os.path.join(repo, "src", "feature.py"), orig_feature)
        self._write_bytes(os.path.join(repo, "src", "app.py"), orig_app,
                          app_mode)
        os.remove(os.path.join(repo, "probe_added.py"))
        restored = self._run_or_skip(output, "baseline", refused_argv)
        self._check_receipt_shape(output, restored, "baseline", refused_argv,
                                  evidence)
        self.assertEqual(restored["exit_code"], 0)
        self.assertEqual(restored["snapshot_before"], first["snapshot_before"])
        self.assertEqual(restored["changed_paths"], [])
        self.assertEqual(restored["added_paths"], [])
        self.assertEqual(restored["removed_paths"], [])
        with open(self._meta(output, "baseline.json"), "rb") as fh:
            re_pinned = json.loads(fh.read().decode("utf-8"))
        self.assertEqual(re_pinned["run_id"], restored["run_id"])
        self.assertEqual(re_pinned["snapshot_identity"],
                         restored["snapshot_before"])
        self.assertEqual(len(self._receipt_files(output)), 4)

        # -- (5) receipts round-trip through disk exactly -------------------
        stored = {}
        for name in self._receipt_files(output):
            with open(self._meta(output, "runs", name), "rb") as fh:
                stored[name] = json.loads(fh.read().decode("utf-8"))
        self.assertEqual(len(stored), 4)
        seen_ids = set()
        for receipt in (first, probe, second_probe, restored):
            self.assertEqual(stored["%s.json" % receipt["run_id"]], receipt)
            seen_ids.add(receipt["run_id"])
        self.assertEqual(len(seen_ids), 4, "run ids are not unique")

        # -- (6) the CLI preserves the command's own exit status -------------
        proc = self.cli("run-review", self.TICKET, "--review-context", output,
                        "--kind", "probe", "--", "python3", "-c",
                        FAILING_COMMAND_SCRIPT)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("run-review", proc.stderr)
        self.assertIn("receipt", proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(len(self._receipt_files(output)), 5)

        proc = self.cli("run-review", self.TICKET, "--review-context", output,
                        "--kind", "probe", "--", "python3", "-c",
                        UNCHANGED_COMMAND_SCRIPT)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("receipt", proc.stdout)
        self.assertEqual(len(self._receipt_files(output)), 6)

        # Each CLI invocation recorded the argv it was actually handed: the
        # script is identifiable by the exit status the receipt preserved.
        cli_receipts = sorted(set(self._receipt_files(output)) - set(stored))
        self.assertEqual(len(cli_receipts), 2)
        by_exit = {}
        for name in cli_receipts:
            with open(self._meta(output, "runs", name), "rb") as fh:
                receipt = json.loads(fh.read().decode("utf-8"))
            self.assertEqual(receipt["kind"], "probe")
            self.assertEqual(receipt["argv"][0], "python3")
            by_exit[receipt["exit_code"]] = receipt
        self.assertEqual(by_exit[3]["argv"],
                         ["python3", "-c", FAILING_COMMAND_SCRIPT])
        self.assertEqual(by_exit[0]["argv"],
                         ["python3", "-c", UNCHANGED_COMMAND_SCRIPT])

        # -- (7) no reviewer argument is ever reinterpreted by a shell --------
        # Every payload below would create or append a host file if any part of
        # the launch went through a shell (`wsl.exe -- <argv>` does; this module
        # uses `wsl.exe --exec`). The supervisor's own manifest must stay
        # byte-identical, and the argv must come back verbatim.
        meta_json = review_boundary.linux_path(
            os.path.join(output, "meta", "context.json"))
        hostile_argv = ["python3", "-c", UNCHANGED_COMMAND_SCRIPT,
                        "a;b", "$(echo PWNED >> %s)" % meta_json,
                        ";echo PWNED >> %s" % meta_json,
                        "`echo PWNED >> %s`" % meta_json,
                        "|touch %s" % meta_json, "&touch %s" % meta_json,
                        "*?[]", "quote'd\"word"]
        hostile = self._run_or_skip(output, "probe", hostile_argv)
        self._check_receipt_shape(output, hostile, "probe", hostile_argv,
                                  evidence)
        self.assertEqual(hostile["exit_code"], 0)
        self.assertEqual(hostile["argv"], hostile_argv)
        self.assertEqual(self._context_json_bytes(output),
                         context_bytes_before,
                         "a reviewer argument was reinterpreted outside the "
                         "boundary")
        self.assertEqual(hostile["changed_paths"], [])
        self.assertEqual(hostile["added_paths"], [])
        self.assertEqual(hostile["removed_paths"], [])
        self.assertEqual(len(self._receipt_files(output)), 7)

        # -- (8) a boundary lost at launch time still refuses, after a good proof
        # The accepted preflight evidence for this very context is on disk and
        # still describes this host, so the run reaches its own launch and the
        # launch is what fails (as a revoked namespace would): the run is
        # refused, no receipt is written and no capture file is left behind.
        def revoked_namespace(command, stdout_path, stderr_path):
            if "--version" in command:
                # Answer exactly as this host's real bwrap did during preflight,
                # so the accepted evidence stays current and is reused.
                with open(stdout_path, "wb") as fh:
                    fh.write((evidence["bwrap_version"] + "\n").encode("utf-8"))
                with open(stderr_path, "wb") as fh:
                    fh.write(b"")
                return 0
            return self._denied_namespace(command, stdout_path, stderr_path)

        runs_dir = self._meta(output, "runs")
        files_before = sorted(os.listdir(runs_dir))
        receipts_before = self._receipt_files(output)
        refused_calls = self._seam(revoked_namespace)
        refused_argv = ["python3", "-c", UNCHANGED_COMMAND_SCRIPT]
        with self.assertRaises(contracts.ContractError) as ctx:
            review_boundary.run(output, "probe", refused_argv)
        self.assertIn(review_boundary.NAMESPACE_CREATION_DENIED,
                      str(ctx.exception))
        # The run really did reach its own launch: the accepted evidence was
        # reused, and the refused command is the reviewer's own, passed
        # positionally after the literal `--`.
        launched = [command for command in refused_calls if "--" in command]
        self.assertTrue(launched, refused_calls)
        self._assert_inner_command(launched[-1], refused_argv)
        self.assertEqual(self._receipt_files(output), receipts_before,
                         "a launch-time boundary failure wrote a receipt")
        self.assertEqual(sorted(os.listdir(runs_dir)), files_before,
                         "a launch-time boundary failure left capture files")

        # -- (9) nothing escaped to the live tree ----------------------------
        self.assertEqual(records_before, self._record_bytes())
        self._assert_live_untouched(live)
        self.assertEqual(self._context_json_bytes(output), context_bytes_before)

    def test_boundary_that_never_started_writes_no_enforced_receipt(self):
        """A launcher failure must not be filed as an enforced verifier run.

        An unreachable `wsl.exe`/`bwrap` leaves a nonzero status whose stderr is
        not bwrap's own marker and which captured nothing — indistinguishable
        from a verifier that failed quietly. Before this pin the run was recorded
        with `boundary.enforced: true` and pinned a baseline although nothing had
        started, which is the exact "no receipt claiming enforced success" the
        plan forbids.
        """
        self.prepare_v2_review()
        _context, output = self._prepare(output=self._new_output("nostart"))
        self._preflight_or_skip(output)
        receipts_before = self._receipt_files(output)

        def launcher_failed(command, stdout_path, stderr_path):
            # `run` re-probes the boundary through the same seam, so fail ONLY
            # the verifier launch — identified by the start-marker wrapper that
            # only `run` puts around the reviewer's argv. Letting the probe and
            # version calls through keeps this leg testing the marker gate
            # rather than one of the earlier layers that also closes.
            if "review-boundary" not in command:
                return real_launch(command, stdout_path, stderr_path)
            with open(stderr_path, "wb") as fh:
                fh.write(b"Wsl: the system cannot find the path specified.\n")
            with open(stdout_path, "wb") as fh:
                fh.write(b"")
            return 4294967295

        real_launch = review_boundary.launch

        self._seam(launcher_failed)
        with self.assertRaises(contracts.ContractError) as ctx:
            review_boundary.run(output, "baseline",
                                ["python3", "-c", UNCHANGED_COMMAND_SCRIPT])
        self.assertIn(review_boundary.BOUNDARY_NEVER_STARTED,
                      str(ctx.exception))
        # `preflight` recorded genuine enforcement at the top of this test, so
        # the claim under test is specifically that the refused run wrote no
        # receipt and pinned no baseline.
        self.assertEqual(self._receipt_files(output), receipts_before,
                         "a run that never started still wrote a receipt")
        self.assertFalse(os.path.exists(self._meta(output, "baseline.json")),
                         "a run that never started pinned a baseline")

    def test_first_baseline_must_start_from_the_prepared_snapshot(self):
        """Probe edits cannot promote themselves into the acceptance baseline.

        The first baseline used to pin whatever identity it happened to observe,
        so a probe that edited snapshot source and then ran a `baseline` command
        made the edited tree the new baseline and a second edited run passed.
        The first baseline is now required to equal Task 1's captured snapshot
        identity; a later baseline still compares against the recorded one.
        """
        self.prepare_v2_review()
        _context, output = self._prepare(output=self._new_output("basepin"))
        self._preflight_or_skip(output)
        target = os.path.join(output, "repo", "src", "feature.py")
        with open(target, "rb") as fh:
            original = fh.read()
        argv = ["python3", "-c", UNCHANGED_COMMAND_SCRIPT]

        with open(target, "wb") as fh:
            fh.write(original + b"\n# probe edit, never restored\n")
        with self.assertRaises(contracts.ContractError) as ctx:
            review_boundary.run(output, "baseline", argv)
        self.assertIn(review_boundary.BASELINE_IDENTITY_DRIFT,
                      str(ctx.exception))
        # `preflight` legitimately recorded enforcement above, so the check here
        # is that the refused attempt wrote neither a receipt nor a baseline.
        self.assertEqual(self._receipt_files(output), [],
                         "a refused baseline still wrote a receipt")
        self.assertFalse(os.path.exists(self._meta(output, "baseline.json")),
                         "a refused baseline pinned itself")

        with open(target, "wb") as fh:
            fh.write(original)
        receipt = self._run_or_skip(output, "baseline", argv)
        self.assertIs(receipt["boundary"]["enforced"], True)
        self.assertTrue(os.path.exists(self._meta(output, "baseline.json")))

    def _assert_inner_command(self, command, expected_argv):
        """The reviewer's argv must be executed as discrete positional elements.

        `run` prefixes the command with a two-statement in-sandbox wrapper so
        the supervisor can prove the boundary actually started. The wrapper
        receives everything positionally, so this pins both the command that
        really runs and, more importantly, that no reviewer content was ever
        joined into the `-c` script text.
        """
        self.assertIn("--", command, command)
        inner = command[command.index("--") + 1:]
        self.assertEqual(inner[0], "sh")
        self.assertEqual(inner[1], "-c")
        self.assertEqual(inner[3], "review-boundary")
        self.assertEqual(inner[4], "/scratch/.boundary-started")
        for element in expected_argv:
            self.assertNotIn(element, inner[2],
                             "reviewer content reached the wrapper script")
        self.assertEqual(inner[5:], list(expected_argv),
                         "the reviewer's argv was not passed verbatim and "
                         "positionally after the start-marker wrapper")

    def _check_receipt_shape(self, output, receipt, kind, argv, evidence):
        """Every frozen key present, nothing invented, nothing weakened."""
        self.assertEqual(
            set(receipt),
            {"run_id", "kind", "argv", "cwd", "exit_code", "stdout_path",
             "stdout_sha256", "stderr_path", "stderr_sha256", "snapshot_before",
             "snapshot_after", "changed_paths", "added_paths", "removed_paths",
             "boundary", "profile", "host", "started_at", "finished_at",
             "blocker"})
        self.assertEqual(receipt["kind"], kind)
        self.assertEqual(receipt["argv"], argv,
                         "argv was not recorded verbatim")
        self.assertEqual(receipt["cwd"], "/snapshot")
        self.assertEqual(receipt["profile"], review_boundary.PROFILE)
        self.assertEqual(receipt["host"], review_boundary.supervisor_host())
        self.assertRegex(receipt["run_id"], r"^[0-9a-f]{32}$")
        self.assertEqual(receipt["stdout_path"],
                         "meta/runs/%s.stdout" % receipt["run_id"])
        self.assertEqual(receipt["stderr_path"],
                         "meta/runs/%s.stderr" % receipt["run_id"])
        for key in ("stdout_sha256", "stderr_sha256", "snapshot_before",
                    "snapshot_after"):
            self.assertRegex(receipt[key], r"^[0-9a-f]{64}$")
        self.assertLessEqual(receipt["started_at"], receipt["finished_at"])
        self.assertIsInstance(receipt["exit_code"], int)
        for key in ("changed_paths", "added_paths", "removed_paths"):
            self.assertIsInstance(receipt[key], list)

        boundary = receipt["boundary"]
        self.assertEqual(boundary["profile"], review_boundary.PROFILE)
        self.assertIs(boundary["enforced"], True)
        self.assertEqual(boundary["bwrap_version"], evidence["bwrap_version"])
        self.assertEqual(boundary["sandbox_host"], evidence["sandbox_host"])
        self.assertEqual(boundary["supervisor_host"],
                         evidence["supervisor_host"])
        self.assertEqual(boundary["preflight"], "meta/preflight.json")
        self.assertEqual(boundary["preflight_sha256"],
                         self._sha(self._meta(output, "preflight.json")))
        self.assertEqual(boundary["denials_attempted"],
                         len(evidence["denials"]))
        self.assertEqual(boundary["writable"], evidence["writable"])
        # The receipt carries the *proof* of the network denial, not just the
        # claim: a run whose boundary had network must not be able to record a
        # bare `network_denied: true`.
        self.assertIs(boundary["network_denied"], True)
        self.assertIn(boundary["network_denial_errno"],
                      review_boundary.NO_NETWORK_ERRNOS,
                      "the receipt records no no-network errno")
        self.assertEqual(boundary["network_denial_errno"],
                         evidence["network_denial_errno"])


if __name__ == "__main__":
    unittest.main()
