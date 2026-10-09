"""Tests for the enforced local process boundary and supervisor receipts
(HARDEN-011 Task 2).

Three named tests, exactly as the plan freezes them:

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

Host execution legs are conditional: if the boundary reports itself
unavailable the executing legs skip with a message naming the blocker, which
is never read as support. The fail-closed legs never skip.
"""

import errno
import hashlib
import json
import os
import shutil
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


class ReviewBoundaryTest(V2CLITestCase):
    # -- fixture helpers -----------------------------------------------------

    def setUp(self):
        super().setUp()
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

    def _patch(self, name, value):
        original = getattr(review_boundary, name)
        setattr(review_boundary, name, value)
        self.addCleanup(setattr, review_boundary, name, original)
        return original

    # -- host-conditionality -------------------------------------------------

    def _unavailable(self, action):
        """Run a host leg; on an unavailable boundary skip naming the blocker.

        A skip records that this host could not run the boundary. It is never
        treated as support, and no fail-closed leg goes through here.
        """
        try:
            return action()
        except contracts.ContractError as exc:
            self.skipTest("linux-bwrap-v1 boundary is unavailable on this host, "
                          "no support is claimed by this skip: %s" % exc)

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
            self._patch("_extra_bind_specs",
                        lambda cp: [("--bind", "/etc", "/elsewhere")])
            with self.assertRaises(contracts.ContractError) as ctx:
                review_boundary.run(output, "probe", ["true"])
            self.assertIn(review_boundary.UNAPPROVED_MOUNT_ROOT,
                          str(ctx.exception))
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
        # reused, and the refused command is the reviewer's, verbatim, after
        # the literal `--`.
        self.assertTrue(any("--" in command
                            and command[command.index("--") + 1:] == refused_argv
                            for command in refused_calls), refused_calls)
        self.assertEqual(self._receipt_files(output), receipts_before,
                         "a launch-time boundary failure wrote a receipt")
        self.assertEqual(sorted(os.listdir(runs_dir)), files_before,
                         "a launch-time boundary failure left capture files")

        # -- (9) nothing escaped to the live tree ----------------------------
        self.assertEqual(records_before, self._record_bytes())
        self._assert_live_untouched(live)
        self.assertEqual(self._context_json_bytes(output), context_bytes_before)

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


if __name__ == "__main__":
    unittest.main()
