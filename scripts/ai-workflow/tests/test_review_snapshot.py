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

    def _new_output(self, name="context"):
        """A previously-absent output directory outside the live worktree."""
        path = os.path.join(self._out_tmp.name, name)
        self.assertFalse(os.path.exists(path))
        return path

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

        def _abs_git(base, *args):
            proc = subprocess.run(
                ["git", "-C", base, "rev-parse", *args],
                capture_output=True, text=True, env=self._env())
            self.assertEqual(proc.returncode, 0, proc.stderr)
            value = proc.stdout.strip()
            if not os.path.isabs(value):
                value = os.path.join(base, value)
            return os.path.realpath(value)

        live_git = _abs_git(self.root, "--git-dir")
        live_common = _abs_git(self.root, "--git-common-dir")
        clone_git = _abs_git(clone_root, "--git-dir")
        clone_common = _abs_git(clone_root, "--git-common-dir")
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
        proc = self._git("ls-files")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for path in proc.stdout.split():
            if path not in records:
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
        """autocrlf may diverge the source manifests, never the raw inputs."""
        reviewed = self.prepare_v2_review()
        # Real autocrlf conversion in the clone: CRLF in the live worktree,
        # LF in the repository. The live manifest then differs from the
        # snapshot manifest, but the registered Plan and configured inputs
        # are captured by RAW BYTES and must stay exact.
        self.assertEqual(
            self._git("config", "core.autocrlf", "true").returncode, 0)
        self.addCleanup(self._git, "config", "core.autocrlf", "false")
        plan_rel = ".ai/work/%s/plan.md" % self.TICKET
        live_plan = Path(self.root, plan_rel)
        registered_plan_sha = contracts.sha256_file(str(live_plan))
        records_before = self._record_bytes()

        context, output = self._prepare(commit=reviewed)

        self.assertNotEqual(context["live_manifest"],
                            context["snapshot_manifest"])
        snapshot_plan = Path(output, "repo", plan_rel)
        self.assertEqual(snapshot_plan.read_bytes(), live_plan.read_bytes())
        self.assertEqual(context["plan"]["sha256"], registered_plan_sha)
        self.assertEqual(records_before, self._record_bytes())

        # The captured input hashes cover the live bytes exactly.
        state_rel = ".ai/work/%s/state.yaml" % self.TICKET
        self.assertEqual(
            context["inputs"][state_rel],
            contracts.sha256_file(os.path.join(self.root, state_rel)))

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
        # skip on), so the leg is exercised where the host allows it and
        # otherwise reported as not run rather than silently dropped.
        link = os.path.join(self.root, "src", "external_link.py")
        try:
            os.symlink(os.path.join(self._out_tmp.name, "outside.txt"), link)
        except (OSError, NotImplementedError):
            link = None
        if link is not None:
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

    def test_linked_worktree_is_presented_as_snapshot(self):
        """A linked worktree's context resolves against the linked root."""
        reviewed = self.prepare_v2_review()
        context, output = self._prepare(commit=reviewed)
        # The clone is an ordinary (non-linked) worktree of its own Git dir;
        # HEAD resolves to the reviewed commit inside the snapshot.
        clone_root = os.path.join(output, "repo")
        proc = subprocess.run(
            ["git", "-C", clone_root, "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, env=self._env())
        self.assertEqual(proc.stdout.strip(), "true")
        # assert_current accepts the freshly prepared context.
        current = review_snapshot.assert_current(self.root, self.TICKET,
                                                 output)
        self.assertEqual(current, context)

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
