"""Tests for the identified independent review snapshot (HARDEN-011 Task 1).

Covers `review_snapshot.prepare` / `review_snapshot.assert_current` and the
`ai-workflow prepare-review` CLI. The fixture drives the public v2 lifecycle
into a clean `review` tree (via `v2_support.V2CLITestCase.prepare_v2_review`),
then prepares a snapshot in a previously-absent directory OUTSIDE the live
worktree. The snapshot clone must have fully independent object storage (no
alternates/reference), capture separate live/snapshot content identities, copy
the registered Plan and configured verification inputs by raw bytes, refuse
unsafe scopes, and run the HARDEN-010 drift assessment before AND after
capture — every rejection leaves the live source, artifacts, Git index and
State untouched and creates no partial context.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contracts  # noqa: E402
import review  # noqa: E402
import review_snapshot  # noqa: E402
from v2_support import V2CLITestCase  # noqa: E402


class ReviewSnapshotTest(V2CLITestCase):
    # -- fixture helpers -----------------------------------------------------

    def setUp(self):
        super().setUp()
        # Snapshot outputs must live OUTSIDE the live worktree, so they get
        # their own disposable directory (a sibling of the repo temp dir).
        self._out_tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._out_tmp.cleanup()
        super().tearDown()

    def _record_bytes(self):
        """Read configured live State/Review/Handoff paths without mutation.

        None for an absent file. Captured before and compared after every
        preparation/rejection so a probe that rewrote a workflow record is
        caught even when the probe's own output claims success.
        """
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
            if os.path.exists(full):
                with open(full, "rb") as fh:
                    out[rel] = fh.read()
            else:
                out[rel] = None
        return out

    def _index_snapshot(self):
        """Live index bytes/mtime/flags a read-only preparation must not move."""
        index_path = os.path.join(self.root, ".git", "index")
        with open(index_path, "rb") as fh:
            index_bytes = fh.read()
        return {
            "index": index_bytes,
            "index_mtime": os.stat(index_path).st_mtime_ns,
            "flags": self._git("ls-files", "-v", "-z").stdout,
            "gitdir": sorted(os.listdir(os.path.join(self.root, ".git"))),
        }

    def _assert_index_unchanged(self, snap):
        index_path = os.path.join(self.root, ".git", "index")
        with open(index_path, "rb") as fh:
            self.assertEqual(fh.read(), snap["index"], ".git/index bytes changed")
        self.assertEqual(os.stat(index_path).st_mtime_ns, snap["index_mtime"],
                         ".git/index mtime changed")
        self.assertEqual(self._git("ls-files", "-v", "-z").stdout, snap["flags"],
                         "index hint flags changed")
        self.assertEqual(sorted(os.listdir(os.path.join(self.root, ".git"))),
                         snap["gitdir"],
                         "a file was created or removed under .git")

    def _abs_git(self, base, *args):
        """Resolve a `rev-parse` path against its own repository, absolutely.

        `--git-dir` values are relative to the invoking process's cwd, so two
        different repositories must each be joined to their own root before
        comparison; comparing `abspath` of both would make any two repos look
        identical.
        """
        proc = subprocess.run(["git", "-C", base, "rev-parse", *args],
                              capture_output=True, text=True, env=self._env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        value = proc.stdout.strip()
        if not os.path.isabs(value):
            value = os.path.join(base, value)
        return os.path.realpath(value)

    def _new_output(self, name="context"):
        """A previously-absent output directory outside the live worktree."""
        path = os.path.join(self._out_tmp.name, name)
        self.assertFalse(os.path.exists(path))
        return path

    def _symlink_or_skip(self, target, link):
        """Create a symlink, or report the leg as not run on a hostile host.

        Unprivileged Windows refuses `os.symlink`; skipping loudly is honest,
        while silently continuing would let a guard look tested when it was not.
        """
        try:
            os.symlink(target, link)
        except (OSError, NotImplementedError) as exc:
            self.skipTest("host cannot create symlinks: %s" % exc)

    def _write_bytes(self, path, raw):
        with open(path, "wb") as fh:
            fh.write(raw)

    def _prepare(self, output=None, commit=None):
        """Prepare a snapshot via the public API; return (context, output)."""
        output = output or self._new_output()
        commit = commit or self._git("rev-parse", "HEAD").stdout.strip()
        context = review_snapshot.prepare(self.root, self.TICKET, commit,
                                          output)
        return context, output

    def _assert_context_layout(self, output):
        self.assertTrue(os.path.isdir(os.path.join(output, "repo")))
        self.assertTrue(os.path.isdir(os.path.join(output, "scratch")))
        self.assertTrue(os.path.isfile(os.path.join(output, "meta",
                                                    "context.json")))

    # -- scope and metadata ---------------------------------------------------

    def test_snapshot_scope_and_metadata(self):
        """The clone is independent; unsafe scopes reject; records preserved."""
        reviewed = self.prepare_v2_review()
        records_before = self._record_bytes()
        snap = self._index_snapshot()
        output = self._new_output()

        context = review_snapshot.prepare(self.root, self.TICKET, reviewed,
                                          output)

        # Manifest schema (frozen keys).
        self.assertEqual(context["format_version"], 1)
        self.assertEqual(context["ticket_id"], self.TICKET)
        self.assertEqual(context["reviewed_commit"], reviewed)
        plan_ref = context["plan"]
        self.assertEqual(plan_ref["path"],
                         ".ai/work/%s/plan.md" % self.TICKET)
        live_plan = os.path.join(self.root, plan_ref["path"])
        self.assertEqual(plan_ref["sha256"],
                         contracts.sha256_file(live_plan))
        self.assertIsInstance(context["inputs"], dict)
        self.assertIsInstance(context["state_sha256"], str)
        self.assertEqual(context["state_sha256"],
                         contracts.sha256_file(os.path.join(
                             self.work, "state.yaml")))
        self.assertIsInstance(context["scope"], dict)
        self.assertIsInstance(context["live_manifest"], str)
        self.assertIsInstance(context["snapshot_manifest"], str)

        # The context layout exists and the manifest round-trips.
        self._assert_context_layout(output)
        with open(os.path.join(output, "meta", "context.json"), "rb") as fh:
            persisted = json.loads(fh.read().decode("utf-8"))
        self.assertEqual(persisted, context)

        # Independent clone: distinct Git dir and common dir, no alternates.
        # `rev-parse` prints a path relative to the *invoking* process's cwd, so
        # each value must be joined to its own root before comparing — plain
        # `abspath` would resolve both against the test runner's cwd and make
        # any two repositories look identical.
        clone_root = os.path.join(output, "repo")

        live_git = self._abs_git(self.root, "--git-dir")
        live_common = self._abs_git(self.root, "--git-common-dir")
        clone_git = self._abs_git(clone_root, "--git-dir")
        clone_common = self._abs_git(clone_root, "--git-common-dir")
        self.assertNotEqual(clone_git, live_git,
                            "the snapshot clone shares the live Git directory")
        self.assertNotEqual(clone_common, live_common,
                            "the snapshot clone shares the live Git common "
                            "directory")
        # No object alternates: the clone's objects/info/alternates is absent.
        clone_objects = os.path.join(clone_root, ".git", "objects")
        self.assertFalse(
            os.path.exists(os.path.join(clone_objects, "info", "alternates")),
            "the snapshot clone must not share object storage")

        # The clone checked out the reviewed commit.
        proc = subprocess.run(
            ["git", "-C", clone_root, "rev-parse", "HEAD"],
            capture_output=True, text=True, env=self._env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), reviewed)

        # The scope excludes exactly the four code-drift record paths, and
        # nothing else silently: every tracked + nonignored untracked path
        # outside them appears in the scope listing.
        scope_paths = context["scope"]["paths"]
        self.assertEqual(context["scope"]["excluded_records"],
                         sorted(".ai/work/%s/%s" % (self.TICKET, name)
                                for name in review.TICKET_EXEMPT_FILES))
        records = {".ai/work/%s/%s" % (self.TICKET, name)
                   for name in review.TICKET_EXEMPT_FILES}
        for path in records:
            self.assertNotIn(path, scope_paths)
        proc = self._git("ls-files", "-z")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for path in proc.stdout.split("\0"):
            if path and path not in records:
                self.assertIn(path, scope_paths)

        # Live records, index and Git metadata are untouched.
        self.assertEqual(records_before, self._record_bytes())
        self._assert_index_unchanged(snap)

    def test_prepare_rejects_dirty_flagged_code(self):
        """HARDEN-010 flagged dirty code rejects preparation with no output."""
        reviewed = self.prepare_v2_review()
        # An index hint hides an equal-size edit from a plain `git diff`, but
        # HARDEN-010 neutralizes hints: preparation must still reject.
        self._flagged_edit("both", "src/feature.py")
        records_before = self._record_bytes()
        snap = self._index_snapshot()
        output = self._new_output()

        with self.assertRaises(contracts.ContractError) as ctx:
            review_snapshot.prepare(self.root, self.TICKET, reviewed, output)
        self.assertIn("src/feature.py", str(ctx.exception))

        # No partial context, no live change.
        self.assertFalse(os.path.exists(output))
        self.assertEqual(records_before, self._record_bytes())
        self._assert_index_unchanged(snap)
        self._unhint_and_rewind("src/feature.py")

    def test_distinct_eol_manifests_and_raw_inputs(self):
        """Checkout conversion must not move the captured raw input bytes."""
        reviewed = self.prepare_v2_review()
        # Force the conversion from version-controlled attributes rather than
        # from whatever `core.autocrlf` the host happens to carry. The live
        # worktree keeps the LF bytes it was written with, while any checkout of
        # the reviewed commit yields CRLF for the declared artifacts. The file
        # sits beside the artifacts because `.ai/work/.gitattributes` installs
        # `** -text`, and the closest .gitattributes wins.
        attrs = Path(self.root, ".ai", "work", self.TICKET, ".gitattributes")
        attrs.write_text("handoff.md text eol=crlf\n"
                         "progress.md text eol=crlf\n", encoding="utf-8")
        converted = self.commit_all("fixture: convert artifacts on checkout")

        handoff_rel = ".ai/work/%s/handoff.md" % self.TICKET
        live_handoff = Path(self.root, ".ai", "work", self.TICKET, "handoff.md")
        live_raw = live_handoff.read_bytes()
        self.assertNotIn(b"\r\n", live_raw,
                         "the fixture must leave the live bytes unconverted")

        # Control: prove a plain checkout of the reviewed commit really does
        # convert the artifact. Without this, the equality assertion below could
        # pass while raw-byte capture was doing nothing at all.
        control = os.path.join(self._out_tmp.name, "control-clone")
        proc = subprocess.run(["git", "clone", "--no-local", "--quiet", "--",
                               self.root, control], capture_output=True,
                              env=self._env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        control_raw = Path(control, ".ai", "work", self.TICKET,
                           "handoff.md").read_bytes()
        self.assertIn(b"\r\n", control_raw,
                      "the fixture did not force checkout conversion, so the "
                      "raw-byte pin below proves nothing")

        plan_rel = ".ai/work/%s/plan.md" % self.TICKET
        live_plan = Path(self.root, ".ai", "work", self.TICKET, "plan.md")
        registered_plan_sha = contracts.sha256_file(str(live_plan))
        records_before = self._record_bytes()

        context, output = self._prepare(commit=converted)

        # The snapshot copy is the live bytes, not the converted checkout.
        snapshot_handoff = Path(output, "repo", ".ai", "work", self.TICKET,
                                "handoff.md")
        self.assertEqual(snapshot_handoff.read_bytes(), live_raw)
        self.assertNotEqual(snapshot_handoff.read_bytes(), control_raw)
        self.assertEqual(context["inputs"][handoff_rel],
                         hashlib.sha256(live_raw).hexdigest())

        # The registered Plan stays exactly the hash it was registered under.
        self.assertEqual(Path(output, "repo", ".ai", "work", self.TICKET,
                              "plan.md").read_bytes(), live_plan.read_bytes())
        self.assertEqual(context["plan"]["sha256"], registered_plan_sha)
        self.assertEqual(records_before, self._record_bytes())

        # Both identities are captured; a clean tree may legitimately match.
        self.assertIsInstance(context["live_manifest"], str)
        self.assertIsInstance(context["snapshot_manifest"], str)

    # -- rejection and preservation cases -------------------------------------

    def test_rejections_preserve_live_state_index_and_lock(self):
        """Every rejection path leaves live bytes, index and lock untouched."""
        reviewed = self.prepare_v2_review()
        index_path = Path(self.root, ".git", "index")
        lock_path = Path(self.root, ".git", "index.lock")
        with open(lock_path, "wb") as fh:
            fh.write(b"stale lock from a crashed git\n")

        records_before = self._record_bytes()
        before_index = index_path.read_bytes()
        before_index_mtime = index_path.stat().st_mtime_ns
        before_lock = lock_path.read_bytes()
        before_lock_mtime = lock_path.stat().st_mtime_ns

        # (a) An output inside the live worktree is refused.
        inside = os.path.join(self.root, "context-inside")
        with self.assertRaises(contracts.ContractError):
            review_snapshot.prepare(self.root, self.TICKET, reviewed, inside)
        self.assertFalse(os.path.exists(inside))

        # (b) An output that already exists is refused.
        taken = self._new_output("taken")
        os.makedirs(taken)
        with self.assertRaises(contracts.ContractError):
            review_snapshot.prepare(self.root, self.TICKET, reviewed, taken)
        self.assertEqual(os.listdir(taken), [])

        # (c) An unresolvable commit is refused.
        output = self._new_output()
        with self.assertRaises(contracts.ContractError):
            review_snapshot.prepare(self.root, self.TICKET, "0000000", output)
        self.assertFalse(os.path.exists(output))

        # Legs (a)-(c) reject without touching the live records.
        self.assertEqual(records_before, self._record_bytes())

        # (d) A v1 Ticket is refused. Seeding v1 rewrites the live State on
        # purpose, so a fresh baseline is captured *after* the seed and used
        # for the final comparison — otherwise the seed itself would be read
        # as the rejection having changed the records.
        self.seed_v1("review")
        records_v1 = self._record_bytes()
        output = self._new_output("v1-out")
        with self.assertRaises(contracts.ContractError):
            review_snapshot.prepare(self.root, self.TICKET, reviewed, output)
        self.assertFalse(os.path.exists(output))
        self.assertEqual(records_v1, self._record_bytes())

        self.assertEqual(index_path.read_bytes(), before_index)
        self.assertEqual(index_path.stat().st_mtime_ns, before_index_mtime)
        self.assertEqual(lock_path.read_bytes(), before_lock)
        self.assertEqual(lock_path.stat().st_mtime_ns, before_lock_mtime)

    def test_uncreatable_output_is_a_contract_error(self):
        """An output that cannot be created refuses cleanly, leaving nothing."""
        reviewed = self.prepare_v2_review()
        # The parent of the output path is a regular file, so `makedirs` cannot
        # succeed. The refusal must be a clean contract error rather than a raw
        # OSError escaping `prepare` (which the CLI would surface as a
        # traceback instead of exit 1).
        blocker = os.path.join(self._out_tmp.name, "blocker-file")
        with open(blocker, "w", encoding="utf-8") as fh:
            fh.write("not a directory\n")
        blocked = os.path.join(blocker, "ctx")
        with self.assertRaises(contracts.ContractError):
            review_snapshot.prepare(self.root, self.TICKET, reviewed, blocked)
        self.assertFalse(os.path.exists(blocked))
        # The live records are untouched by the refusal.
        before = self._record_bytes()
        with self.assertRaises(contracts.ContractError):
            review_snapshot.prepare(self.root, self.TICKET, reviewed, blocked)
        self.assertEqual(before, self._record_bytes())

    def test_capture_damage_refuses_and_rolls_back_a_packed_context(self):
        """Capture that changes live code is refused and the context is gone."""
        reviewed = self.prepare_v2_review()
        # Pack the live objects so the clone inherits Git's read-only (0444)
        # pack files. Windows refuses to delete those, and the rollback that
        # used `shutil.rmtree(..., ignore_errors=True)` swallowed the resulting
        # PermissionError and silently left a whole clone of the live repository
        # on disk. Every other rejection leg in this file fails BEFORE the
        # clone, so nothing else reached that path.
        repack = self._git("-c", "gc.auto=0", "repack", "-a", "-d")
        self.assertEqual(repack.returncode, 0, repack.stderr)
        pack_dir = os.path.join(self.root, ".git", "objects", "pack")
        self.assertTrue([f for f in os.listdir(pack_dir)
                         if f.endswith(".pack")],
                        "repack produced no pack; this leg would prove nothing")

        output = self._new_output("damage-out")
        source = os.path.join(self.root, "src", "feature.py")
        with open(source, "rb") as fh:
            original = fh.read()

        real_copy = review_snapshot._copy_raw_inputs

        def copy_then_damage(*args):
            real_copy(*args)
            # Simulate a capture step that damages live source. Only the
            # post-capture drift check stands between this and a persisted
            # context that misrepresents the reviewed code.
            self._write_bytes(source, original + b"# injected during capture\n")

        def restore():
            review_snapshot._copy_raw_inputs = real_copy
            self._write_bytes(source, original)

        try:
            review_snapshot._copy_raw_inputs = copy_then_damage
            with self.assertRaises(contracts.ContractError) as ctx:
                review_snapshot.prepare(self.root, self.TICKET, reviewed, output)
            self.assertIn("changed since", str(ctx.exception))
            self.assertFalse(os.path.exists(output))
        finally:
            # Restored here rather than with addCleanup: unittest runs cleanups
            # after tearDown, which has already deleted the fixture repository.
            restore()

    def test_capture_oserror_is_a_contract_error_not_a_traceback(self):
        """An OSError anywhere in capture is the module's stated failure."""
        reviewed = self.prepare_v2_review()
        real_clone = review_snapshot._clone

        def clone_boom(*args):
            raise OSError("simulated capture failure")

        review_snapshot._clone = clone_boom
        output = self._new_output("clone-oserror")
        try:
            with self.assertRaises(contracts.ContractError) as ctx:
                review_snapshot.prepare(self.root, self.TICKET, reviewed, output)
        finally:
            review_snapshot._clone = real_clone
        self.assertIn("simulated capture failure", str(ctx.exception))
        self.assertFalse(os.path.exists(output))

        # The pre-capture pass carries the same contract, and a refusal there
        # must not create the output directory at all.
        real_scope = review_snapshot._scope_paths

        def scope_boom(*args):
            raise OSError("simulated scope failure")

        review_snapshot._scope_paths = scope_boom
        output = self._new_output("scope-oserror")
        try:
            with self.assertRaises(contracts.ContractError) as ctx:
                review_snapshot.prepare(self.root, self.TICKET, reviewed, output)
        finally:
            review_snapshot._scope_paths = real_scope
        self.assertIn("simulated scope failure", str(ctx.exception))
        self.assertFalse(os.path.exists(output))

    def test_assert_current_oserror_is_a_contract_error(self):
        """Re-validating against an unreadable live tree fails as contracted."""
        reviewed = self.prepare_v2_review()
        context, output = self._prepare(commit=reviewed)
        real_manifest = review_snapshot._manifest

        def manifest_boom(*args):
            raise OSError("simulated live read failure")

        review_snapshot._manifest = manifest_boom
        try:
            with self.assertRaises(contracts.ContractError) as ctx:
                review_snapshot.assert_current(self.root, self.TICKET, output)
        finally:
            review_snapshot._manifest = real_manifest
        self.assertIn("simulated live read failure", str(ctx.exception))

    def test_unsafe_input_scopes_reject(self):
        """External/escaping inputs, external links and submodules refuse."""
        reviewed = self.prepare_v2_review()
        original_artifacts = dict(self.read_state().get("artifacts") or {})

        # An escaping configured input (../ outside the ticket dir).
        data = self.read_state()
        artifacts = dict(data.get("artifacts") or {})
        artifacts["evidence"] = "../evidence.md"
        data["artifacts"] = artifacts
        self.write_state(data)
        output = self._new_output("escape-out")
        with self.assertRaises(contracts.ContractError) as ctx:
            review_snapshot.prepare(self.root, self.TICKET, reviewed, output)
        self.assertIn("escapes", str(ctx.exception))
        self.assertFalse(os.path.exists(output))

        # An absolute configured input.
        data = self.read_state()
        artifacts = dict(data.get("artifacts") or {})
        artifacts["evidence"] = "/tmp/evidence.md"
        data["artifacts"] = artifacts
        self.write_state(data)
        output = self._new_output("abs-out")
        with self.assertRaises(contracts.ContractError):
            review_snapshot.prepare(self.root, self.TICKET, reviewed, output)
        self.assertFalse(os.path.exists(output))

        # Restore the configured artifacts so the remaining legs do not
        # inherit this leg's State mutation.
        data = self.read_state()
        data["artifacts"] = original_artifacts
        self.write_state(data)

        # A submodule committed into the reviewed tree is an unsupported
        # repository shape: `_scope_paths` cannot hash a gitlink as ordinary
        # content. It must be part of the reviewed commit — otherwise the
        # drift check rejects the uncommitted tree first and the shape check is
        # never reached, which would leave the unsupported-shape path untested.
        # The submodule source lives OUTSIDE the live repo so it cannot appear
        # as untracked drift of its own. This leg runs before the symlink leg:
        # `_scope_paths` reports the first offending path in sorted order, and
        # a committed `src/...` symlink would otherwise mask `vendor/sub`.
        sub_src = os.path.join(self._out_tmp.name, "submod-src")
        os.makedirs(sub_src)
        proc = subprocess.run(["git", "init", "-q", sub_src],
                              capture_output=True, env=self._env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        proc = subprocess.run(
            ["git", "-C", sub_src, "-c", "user.name=v2-fixture",
             "-c", "user.email=v2-fixture@local", "commit", "-q", "--allow-empty",
             "-m", "submodule seed"], capture_output=True, env=self._env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # Git blocks the `file` transport by default; the fixture clones from a
        # local path, so allow it for this command only.
        proc = self._git("-c", "protocol.file.allow=always",
                         "submodule", "add", sub_src, "vendor/sub")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        sub_reviewed = self.commit_all("fixture: add submodule")
        output = self._new_output("submodule-out")
        with self.assertRaises(contracts.ContractError) as ctx:
            review_snapshot.prepare(self.root, self.TICKET, sub_reviewed,
                                    output)
        self.assertIn("submodule", str(ctx.exception))
        self.assertFalse(os.path.exists(output))

        # A symlink inside the repo pointing outside it. Creating a symlink
        # needs a privilege Windows does not grant by default (the same
        # limitation the suite's two pre-existing archive/plan symlink cases
        # skip on), so the leg is reported as skipped rather than passing
        # without having run.
        link = os.path.join(self.root, "src", "external_link.py")
        self._symlink_or_skip(
            os.path.join(self._out_tmp.name, "outside.txt"), link)
        # Commit the link so it belongs to the reviewed tree: an
        # uncommitted one would be rejected as drift before the symlink
        # shape check ran.
        link_reviewed = self.commit_all("fixture: add escaping symlink")
        output = self._new_output("link-out")
        with self.assertRaises(contracts.ContractError) as ctx:
            review_snapshot.prepare(self.root, self.TICKET, link_reviewed,
                                    output)
        self.assertIn("symlink", str(ctx.exception))
        self.assertFalse(os.path.exists(output))

    def test_directory_symlinks_are_classified_not_followed(self):
        """A link to a directory is a symlink: in-repo kept, out-repo refused."""
        reviewed = self.prepare_v2_review()
        pkg = os.path.join(self.root, "pkg")
        os.makedirs(pkg, exist_ok=True)
        with open(os.path.join(pkg, "real.txt"), "w", encoding="utf-8") as fh:
            fh.write("x\n")
        self.commit_all("fixture: add a package directory")

        # A tracked symlink to an IN-REPO directory is an ordinary symlink.
        # `os.path.isdir` follows the link, so the tracked pass read it as a
        # gitlink and refused the whole preparation as a submodule.
        inside_link = os.path.join(self.root, "link_dir")
        self._symlink_or_skip("pkg", inside_link)
        link_reviewed = self.commit_all("fixture: track a directory symlink")
        context, output = self._prepare(commit=link_reviewed)
        self.assertEqual(context["scope"]["paths"]["link_dir"], "symlink")
        self.assertTrue(os.path.islink(os.path.join(output, "repo", "link_dir")),
                        "the snapshot must carry the link, not its target")

        # A symlink to a directory OUTSIDE the repo must be refused, not quietly
        # dropped. The untracked pass used to classify it with `os.path.isdir`,
        # see a directory and omit it, so the persisted scope under-reported
        # what the reviewer was shown and `_check_symlink` never ran.
        out_dir = os.path.join(self._out_tmp.name, "outside-dir")
        os.makedirs(out_dir, exist_ok=True)
        escape_link = os.path.join(self.root, "zz_escaping_dir")
        self._symlink_or_skip(out_dir, escape_link)
        with self.assertRaises(contracts.ContractError) as ctx:
            review_snapshot._scope_paths(self.root, self.TICKET)
        self.assertIn("symlink", str(ctx.exception))

    def test_linked_worktree_is_presented_as_snapshot(self):
        """A linked worktree's context resolves against the linked root."""
    def test_linked_worktree_is_presented_as_snapshot(self):
        """A linked worktree's context resolves against the linked root."""
        self.prepare_v2_review()
        # A real linked worktree: `--git-dir` and `--git-common-dir` differ, so
        # the shared-metadata case this fixture must survive actually exists.
        linked = os.path.join(self._out_tmp.name, "linked-worktree")
        add = self._git("worktree", "add", "--detach", "-q", linked, "HEAD")
        self.assertEqual(add.returncode, 0, add.stdout + add.stderr)
        linked_git = self._abs_git(linked, "--git-dir")
        linked_common = self._abs_git(linked, "--git-common-dir")
        self.assertNotEqual(linked_git, linked_common,
                            "the fixture made an ordinary clone, not a linked "
                            "worktree; this leg would prove nothing")

        head = subprocess.run(["git", "-C", linked, "rev-parse", "HEAD"],
                              capture_output=True, text=True, env=self._env())
        self.assertEqual(head.returncode, 0, head.stderr)
        output = self._new_output("linked-context")
        context = review_snapshot.prepare(linked, self.TICKET,
                                          head.stdout.strip(), output)
        self.assertEqual(context["live_root"], os.path.realpath(linked))
        self.assertEqual(context["reviewed_commit"], head.stdout.strip())

        # The snapshot is an independent repository, not a second worktree over
        # the shared object store: `--is-inside-work-tree` cannot tell those
        # apart, so compare the resolved Git directories themselves.
        clone_root = os.path.join(output, "repo")
        self.assertNotEqual(self._abs_git(clone_root, "--git-dir"), linked_git,
                            "the snapshot clone shares the linked worktree dir")
        self.assertNotEqual(self._abs_git(clone_root, "--git-common-dir"),
                            linked_common,
                            "the snapshot clone shares the live object store")
        self.assertEqual(self._abs_git(clone_root, "--git-dir"),
                         self._abs_git(clone_root, "--git-common-dir"),
                         "the snapshot clone must be an ordinary repository")
        self.assertEqual(review_snapshot.assert_current(linked, self.TICKET,
                                                        output), context)

    def test_assert_current_rejects_changed_and_missing_inputs(self):
        """Changed live code stales a context; a missing input rejects it."""
        reviewed = self.prepare_v2_review()
        context, output = self._prepare(commit=reviewed)

        # A live code change after preparation stales the context: the live
        # repository no longer matches the captured baseline.
        self.commit_code("src/other_module.py", "def other():\n    return 0\n")
        with self.assertRaises(contracts.ContractError):
            review_snapshot.assert_current(self.root, self.TICKET, output)

        # Currentness is a live comparison, not a latch: restoring the
        # repository to the captured state makes the same context current
        # again, because every identity it compares matches once more. (The
        # fixture commits the whole reviewed tree, so `reset --hard` restores
        # State and inputs byte-identically and no capture is re-hashed wrong.)
        self.assertEqual(self._git("reset", "--hard", reviewed).returncode, 0)
        current = review_snapshot.assert_current(self.root, self.TICKET, output)
        self.assertEqual(current, context)

        # A captured input deleted on disk rejects too.
        os.remove(os.path.join(self.root, ".ai", "work", self.TICKET,
                               "state.yaml"))
        with self.assertRaises(contracts.ContractError):
            review_snapshot.assert_current(self.root, self.TICKET, output)

    def test_cli_prepare_review(self):
        """The public CLI prepares a snapshot and prints the context path."""
        reviewed = self.prepare_v2_review()
        records_before = self._record_bytes()
        output = self._new_output()
        proc = self.cli("prepare-review", self.TICKET,
                        "--commit", reviewed, "--output", output)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn(output, proc.stdout)
        self._assert_context_layout(output)
        with open(os.path.join(output, "meta", "context.json"), "rb") as fh:
            context = json.loads(fh.read().decode("utf-8"))
        self.assertEqual(context["reviewed_commit"], reviewed)
        self.assertEqual(records_before, self._record_bytes())

        # Usage errors exit 2; contract rejections exit 1 without a traceback.
        proc = self.cli("prepare-review", self.TICKET,
                        "--commit", reviewed)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        proc = self.cli("prepare-review", self.TICKET,
                        "--commit", "0000000",
                        "--output", self._new_output("bad-commit"))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)


if __name__ == "__main__":
    unittest.main()
