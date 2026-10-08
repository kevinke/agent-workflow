"""Tests for the Review artifact contract and set-review binding (SCOUT-005 T1).

Covers `contracts.validate_review`, `contracts.read_artifact(kind="review")`,
the read-only `review.code_drift` Git assessment, the transactional
`mutate.set_review` command, the additive v2 `review`/`artifacts.review` State
fields, and the set-review CLI. The lifecycle is driven with public commands;
every rejection asserts the State bytes are unchanged.
"""

import hashlib
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contracts  # noqa: E402
import review  # noqa: E402
from v2_support import V2CLITestCase, valid_plan  # noqa: E402


class ReviewV2Test(V2CLITestCase):
    # -- fixture helpers -----------------------------------------------------

    def _seed_implementation(self, total=1):
        """Reach a ready v2 implementation with a registered `total`-task Plan."""
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        proc = self.cli("set-gate", self.TICKET, "--gate", "sufficient",
                        "--round", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for target in ("technical_decision", "planning"):
            proc = self.cli("advance", self.TICKET, "--to", target)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        plan = self.write_plan(total)
        proc = self.cli("register-plan", self.TICKET, "--path", plan,
                        "--total", str(total))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return plan

    def _seed_review(self, total=1, verdict="pass", reviewed_commit=None):
        """Drive the public-command lifecycle into a bind-ready review phase.

        Returns the reviewed commit (the committed, tree-clean HEAD that the
        Review is written against). `decision.md` is written by the senior role
        and committed before that reviewed commit: implementation -> review now
        requires it on a v2 Ticket, and the same boundary requires a concrete
        handoff, so the fixture writes one through `write_handoff`.
        """
        self._seed_implementation(total)
        self.write_decision()
        # The code under review, committed while in implementation.
        self.commit_code("src/feature.py", "def feature():\n    return 1\n")
        for _ in range(total):
            proc = self.cli("complete-task", self.TICKET,
                            "--total", str(total))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.write_handoff()
        proc = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        # Commit every workflow file so the tree is clean; that HEAD is the
        # reviewed commit the Review binds to.
        self._commit_all("fixture: commit reviewed tree")
        head = self._git("rev-parse", "HEAD").stdout.strip()
        self.write_review(verdict, reviewed_commit=reviewed_commit or head)
        return head

    def _write_file(self, rel, text):
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def _append_file(self, abs_path, text):
        with open(abs_path, "a", encoding="utf-8", newline="") as fh:
            fh.write(text)

    def _commit_all(self, message):
        self.assertEqual(self._git("add", "-A").returncode, 0)
        commit = self._git("commit", "-q", "-m", message)
        self.assertEqual(commit.returncode, 0, commit.stderr)

    def _restore(self, commit):
        """Reset the throwaway repo back to `commit` (fresh reviewed tree)."""
        self.assertEqual(self._git("reset", "--hard", commit).returncode, 0)
        self.assertEqual(self._git("clean", "-fd").returncode, 0)

    def _assert_rejected(self, verdict="pass"):
        before = self.state_bytes()
        proc = self.cli("set-review", self.TICKET, "--verdict", verdict)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def _bind(self, verdict):
        proc = self.cli("set-review", self.TICKET, "--verdict", verdict)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def _append_and_repair(self, total):
        """Append rework up to `total` tasks, then return to implementation."""
        plan = self.write_plan(total)
        proc = self.cli("register-plan", self.TICKET, "--path", plan,
                        "--total", str(total))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    # -- happy path ----------------------------------------------------------

    def test_binding_records_artifact_commit_and_plan_identity(self):
        reviewed = self._seed_review()
        proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        data = self.read_state()
        block = data["review"]
        self.assertEqual(block["verdict"], "pass")
        self.assertEqual(block["reviewed_commit"], reviewed)
        self.assertEqual(block["plan_sha256"],
                         data["source_artifacts"]["plan"]["sha256"])
        with open(os.path.join(self.work, "review.md"), "rb") as fh:
            self.assertEqual(block["artifact_sha256"],
                             hashlib.sha256(fh.read()).hexdigest())
        self.assertEqual(data["artifacts"]["review"], "review.md")

    def test_changes_requested_binds_substantive_review(self):
        self._seed_review(verdict="changes_requested")
        proc = self.cli("set-review", self.TICKET, "--verdict",
                        "changes_requested")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["review"]["verdict"],
                         "changes_requested")

    # -- code drift rejections ----------------------------------------------

    def test_code_change_blocks_review_binding(self):
        self._seed_review()
        self.commit_code("src/other_module.py", "def other():\n    return 0\n")
        self._assert_rejected()

    def _drift_committed_test(self):
        self.commit_code("tests/test_added.py", "def test_a():\n    pass\n")

    def _drift_committed_fixture(self):
        self.commit_code("tests/fixtures/sample.json", '{"a": 1}\n')

    def _drift_rename(self):
        self.assertEqual(self._git("mv", "src/feature.py",
                                   "src/renamed_feature.py").returncode, 0)
        self._commit_all("fixture: rename")

    def _drift_deletion(self):
        os.remove(os.path.join(self.root, "src", "feature.py"))
        self._commit_all("fixture: delete")

    def _drift_staged_edit(self):
        self._write_file("src/feature.py", "def feature():\n    return 2\n")
        self.assertEqual(self._git("add", "src/feature.py").returncode, 0)

    def _drift_dirty_edit(self):
        self._write_file("src/feature.py", "def feature():\n    return 3\n")

    def _drift_untracked_test(self):
        self._write_file("tests/test_untracked.py", "def test_u():\n    pass\n")

    def test_drift_variants_block_review_binding(self):
        reviewed = self._seed_review()
        variants = [
            "_drift_committed_test", "_drift_committed_fixture",
            "_drift_rename", "_drift_deletion", "_drift_staged_edit",
            "_drift_dirty_edit", "_drift_untracked_test",
        ]
        for name in variants:
            with self.subTest(variant=name):
                self._restore(reviewed)
                self.write_review("pass", reviewed_commit=reviewed)
                getattr(self, name)()
                self._assert_rejected()

    def test_metadata_only_commit_allows_review_binding(self):
        reviewed = self._seed_review()
        self._append_file(os.path.join(self.work, "progress.md"),
                          "\n- task 1 complete\n")
        self.assertEqual(
            self._git("add", ".ai/work/T1/progress.md").returncode, 0)
        commit = self._git("commit", "-q", "-m", "fixture: progress only")
        self.assertEqual(commit.returncode, 0, commit.stderr)

        proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["review"]["reviewed_commit"],
                         reviewed)

    def test_changed_plan_blocks_review_binding(self):
        reviewed = self._seed_review()
        self._append_file(os.path.join(self.work, "plan.md"),
                          "\n<!-- drifted -->\n")
        self._commit_all("fixture: plan drift")

        drift = review.code_drift(self.root, self.TICKET, reviewed,
                                  ".ai/work/T1/plan.md")
        self.assertTrue(any("Plan" in problem for problem in drift))
        self._assert_rejected()

    # -- racy-stat detection through the copied index (HARDEN-002) -----------

    def _cached_mtime_ns(self, rel):
        """The index's cached mtime (ns) for `rel` from `git ls-files --debug`."""
        proc = self._git("ls-files", "--debug", "--", rel)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for line in proc.stdout.splitlines():
            text = line.strip()
            if text.startswith("mtime:"):
                seconds, nanos = text[len("mtime:"):].strip().split(":")
                return int(seconds) * 10 ** 9 + int(nanos)
        self.fail("no cached index mtime for %s" % rel)

    def _racy_edit(self, rel="src/feature.py"):
        """Plant an equal-length dirty edit under a cached-stat collision.

        The disposable repo's local config narrows stat comparison to mtime and
        size (`core.trustctime=false`, `core.checkstat=minimal`). The file's
        mtime is backdated by two whole seconds and re-recorded into the cached
        stat with a content-identical `git add`; that captured cached value
        (`git ls-files --debug`) is then forced onto both the file and the real
        index with `os.utime(ns=...)` — never sleeps. The collision is already
        seconds old when any probe runs, so a freshness-losing index copy
        (fresh mtime) misses the edit independently of elapsed time, and only a
        stat-preserving copy keeps git's racy-stat re-check engaged. The only
        changed configuration is the temporary repo's local config (restored on
        cleanup); fixture setup may alter index timestamps, production checks
        may not.
        """
        self.assertEqual(
            self._git("config", "core.trustctime", "false").returncode, 0)
        self.assertEqual(
            self._git("config", "core.checkstat", "minimal").returncode, 0)
        self.addCleanup(self._git, "config", "core.trustctime", "true")
        self.addCleanup(self._git, "config", "core.checkstat", "default")
        full = os.path.join(self.root, rel)
        backdated = ((time.time_ns() - 2_000_000_000)
                     // 1_000_000_000 * 1_000_000_000)
        os.utime(full, ns=(backdated, backdated))
        # Content-identical re-add: only the cached stat is re-recorded (at the
        # backdated mtime), so the blob and the index tree stay unchanged.
        self.assertEqual(self._git("add", rel).returncode, 0)
        cached_ns = self._cached_mtime_ns(rel)
        self.assertEqual(cached_ns, backdated)  # deterministic collision base
        with open(full, "r", encoding="utf-8", newline="") as fh:
            original = fh.read()
        self.assertIn("return 1", original)
        dirty = original.replace("return 1", "return 3")
        self.assertEqual(len(dirty), len(original))  # byte-length unchanged
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(dirty)
        os.utime(full, ns=(cached_ns, cached_ns))
        os.utime(os.path.join(self.root, ".git", "index"),
                 ns=(cached_ns, cached_ns))

    def test_racy_equal_size_edit_is_detected_read_only(self):
        """An equal-size edit colliding with the cached stat is still drift.

        git re-checks by content every entry whose cached mtime is not older
        than the index file's own (racy-stat), so the throwaway index copy used
        for the drift probes must preserve the real index's mtime: the
        collision is then re-compared and the dirty edit reported. A copy that
        gets a fresh mtime instead trusts the matching cached stat and misses
        it. The assessment stays read-only: real index bytes and mtime, State
        and the verdict recording are all unchanged.
        """
        reviewed = self._seed_review()
        index_path = Path(self.root, ".git", "index")
        self._racy_edit()
        before_state = self.state_bytes()
        before_index = index_path.read_bytes()
        before_mtime = index_path.stat().st_mtime_ns

        drift = review.code_drift(self.root, self.TICKET, reviewed,
                                  ".ai/work/T1/plan.md")
        self.assertTrue(any("src/feature.py" in item for item in drift))
        review_proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
        self.assertEqual(review_proc.returncode, 1)
        self.assertEqual(self.state_bytes(), before_state)
        self.assertEqual(index_path.read_bytes(), before_index)
        self.assertEqual(index_path.stat().st_mtime_ns, before_mtime)

    def test_drift_path_classes_stay_relevant(self):
        """Every relevant path class stays reported through the copied index.

        The stat-preserving copy must not narrow the drift rules: staged,
        unstaged (the controlled racy edit), untracked and deleted relevant
        code stay reported, and the workflow-only exemption keeps its existing
        scope (a committed progress.md change is not drift).
        """
        reviewed = self._seed_review()

        def staged():
            self._racy_edit()
            self.assertEqual(self._git("add", "src/feature.py").returncode, 0)

        def unstaged():
            self._racy_edit()

        def untracked():
            self._drift_untracked_test()

        def deleted():
            os.remove(os.path.join(self.root, "src", "feature.py"))

        def workflow_only():
            self._append_file(os.path.join(self.work, "progress.md"),
                              "\n- task 1 complete\n")
            self._commit_all("fixture: progress only")

        variants = {
            "staged": (staged, "src/feature.py"),
            "unstaged": (unstaged, "src/feature.py"),
            "untracked": (untracked, "tests/test_untracked.py"),
            "deleted": (deleted, "src/feature.py"),
            "workflow-only": (workflow_only, None),
        }
        for name, (variant, expected) in variants.items():
            with self.subTest(variant=name):
                self._restore(reviewed)
                variant()
                drift = review.code_drift(self.root, self.TICKET, reviewed,
                                          ".ai/work/T1/plan.md")
                if expected is None:
                    self.assertEqual(drift, [])
                else:
                    self.assertTrue(
                        any(expected in item for item in drift), drift)

    def test_racy_edit_blocks_done_and_resume(self):
        """The controlled racy edit blocks done and resume (exit 1), read-only.

        Both public consumers assess the same dirty snapshot:
        `advance --to done` rejects the stale pass without writing, and
        `resume` reports the drift as an ERROR blocker. Neither touches the
        State, the Review artifact, or the real Git index (bytes and mtimes
        unchanged) and neither prints a traceback.
        """
        self._seed_review()
        self._bind("pass")
        self._racy_edit()
        index_path = Path(self.root, ".git", "index")
        review_path = os.path.join(self.work, "review.md")
        before_state = self.state_bytes()
        before_index = index_path.read_bytes()
        before_index_mtime = index_path.stat().st_mtime_ns
        with open(review_path, "rb") as fh:
            before_review = fh.read()
        before_review_mtime = os.stat(review_path).st_mtime_ns

        done_proc = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(done_proc.returncode, 1,
                         done_proc.stdout + done_proc.stderr)
        self.assertNotIn("Traceback", done_proc.stderr)
        self.assertIn("src/feature.py", done_proc.stderr)

        resume_proc = self.cli("resume", self.TICKET)
        self.assertEqual(resume_proc.returncode, 1,
                         resume_proc.stdout + resume_proc.stderr)
        self.assertNotIn("Traceback", resume_proc.stderr)
        self.assertIn("src/feature.py", resume_proc.stdout)

        self.assertEqual(self.state_bytes(), before_state)
        with open(review_path, "rb") as fh:
            self.assertEqual(fh.read(), before_review)
        self.assertEqual(os.stat(review_path).st_mtime_ns, before_review_mtime)
        self.assertEqual(index_path.read_bytes(), before_index)
        self.assertEqual(index_path.stat().st_mtime_ns, before_index_mtime)

    def test_racy_drift_with_real_index_lock(self):
        """An existing real index.lock is neither used nor mutated by the probe.

        The drift probes redirect Git to a disposable index copy, so a stale
        `.git/index.lock` (as a crashed Git leaves behind) must not block the
        racy assessment, mask the dirty edit, or be mutated: the public
        `set-review` still rejects the stale review (exit 1, no traceback) and
        both the lock and the real index keep their bytes and mtimes.
        """
        reviewed = self._seed_review()
        self._racy_edit()
        index_path = Path(self.root, ".git", "index")
        lock_path = Path(self.root, ".git", "index.lock")
        with open(lock_path, "wb") as fh:
            fh.write(b"stale lock from a crashed git\n")

        before_state = self.state_bytes()
        before_index = index_path.read_bytes()
        before_index_mtime = index_path.stat().st_mtime_ns
        before_lock = lock_path.read_bytes()
        before_lock_mtime = lock_path.stat().st_mtime_ns

        drift = review.code_drift(self.root, self.TICKET, reviewed,
                                  ".ai/work/T1/plan.md")
        self.assertTrue(any("src/feature.py" in item for item in drift), drift)
        review_proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
        self.assertEqual(review_proc.returncode, 1,
                         review_proc.stdout + review_proc.stderr)
        self.assertNotIn("Traceback", review_proc.stderr)

        self.assertEqual(self.state_bytes(), before_state)
        self.assertEqual(index_path.read_bytes(), before_index)
        self.assertEqual(index_path.stat().st_mtime_ns, before_index_mtime)
        self.assertEqual(lock_path.read_bytes(), before_lock)
        self.assertEqual(lock_path.stat().st_mtime_ns, before_lock_mtime)

    # -- artifact / verdict rejections --------------------------------------

    def test_malformed_review_artifact_rejected(self):
        self._seed_review()
        with open(os.path.join(self.work, "review.md"), "w",
                  encoding="utf-8", newline="") as fh:
            fh.write("# Review\n\n## Metadata\n\n```yaml\nartifact_type: review\n"
                     "format_version: 1\nticket_id: T1\n```\n\n## Findings\n\nNone\n")
        self._assert_rejected()

    def test_cli_verdict_mismatch_rejected(self):
        self._seed_review(verdict="pass")
        self._assert_rejected(verdict="changes_requested")

    def test_missing_verdict_is_usage_error(self):
        self._seed_review()
        before = self.state_bytes()
        proc = self.cli("set-review", self.TICKET)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    # -- Git identity --------------------------------------------------------

    def test_code_drift_missing_git_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(contracts.ContractError):
                review.code_drift(tmp, self.TICKET, "deadbeef", "plan.md")

    def test_nonancestor_commit_rejected(self):
        self._seed_review()
        tree = self._git("write-tree").stdout.strip()
        side = self._git("commit-tree", tree, "-m", "unrelated").stdout.strip()
        self.assertTrue(side)
        self.write_review("pass", reviewed_commit=side)
        self._assert_rejected()

    def _index_tmpdirs(self):
        """Names of the review probe's temp index dirs in the system temp dir."""
        return {name for name in os.listdir(tempfile.gettempdir())
                if name.startswith("ai-workflow-index-")}

    def test_unreadable_index_is_a_contract_error(self):
        """An index-copy failure degrades to ContractError (no traceback/leak).

        A directory at the index path is unreadable-as-a-file on every platform
        (IsADirectoryError on POSIX, PermissionError on Windows), so the copy in
        `_changed_paths` fails deterministically.
        """
        head = self._git("rev-parse", "HEAD").stdout.strip()
        index = os.path.join(self.root, ".git", "index")
        os.remove(index)
        os.mkdir(index)
        try:
            before = self._index_tmpdirs()
            with self.assertRaises(contracts.ContractError) as ctx:
                review.code_drift(self.root, self.TICKET, head,
                                  ".ai/work/T1/plan.md")
            self.assertIn("cannot read the Git index", str(ctx.exception))
            self.assertEqual(self._index_tmpdirs(), before)  # no temp-dir leak
        finally:
            os.rmdir(index)

    # -- ticket / phase / completeness rejections ---------------------------

    def test_v1_ticket_rejected(self):
        # setUp's `start` now yields v2 (Task 2); the v1 version is explicit.
        self.seed_v1("requirement")
        self._assert_rejected()

    def test_wrong_phase_rejected(self):
        self.seed_v2("implementation")
        self._assert_rejected()

    def test_incomplete_tasks_rejected(self):
        self._seed_review()
        data = self.read_state()
        data["implementation"]["current_task"] = 0
        data["implementation"]["completed_tasks"] = []
        self.write_state(data)
        self._assert_rejected()

    def test_escalation_blocks_review_binding(self):
        self._seed_review()
        proc = self.cli("escalate", self.TICKET, "--scope", "machine",
                        "--reason", "flagged during review")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self._assert_rejected()

    # -- Unicode / spaced ticket paths --------------------------------------

    def test_unicode_spaced_ticket_path_binds_successfully(self):
        spaced = "T1 步骤"
        self.TICKET = spaced
        self.work = os.path.join(self.root, ".ai", "work", spaced)
        proc = self.cli("start", spaced, "--title", "spaced path ticket")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        self._seed_review()
        proc = self.cli("set-review", spaced, "--verdict", "pass")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["review"]["verdict"], "pass")

    # -- v2 routing ----------------------------------------------------------

    def test_review_routes_to_reviewer(self):
        self._seed_review()
        data = self.read_state()
        self.assertEqual(data["next_action"]["role"], "reviewer")

    # -- completion guards: implementation -> review -------------------------

    def test_enter_review_requires_all_tasks_complete(self):
        self._seed_implementation(2)
        self.write_decision()
        self.commit_code("src/feature.py", "def feature():\n    return 1\n")
        self.assertEqual(
            self.cli("complete-task", self.TICKET, "--total", "2").returncode, 0)
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_enter_review_requires_decision_artifact(self):
        self._seed_implementation(1)
        # decision.md is deliberately omitted; it is now required before review.
        self.commit_code("src/feature.py", "def feature():\n    return 1\n")
        self.assertEqual(self.cli("complete-task", self.TICKET).returncode, 0)
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    # -- completion guards: review -> done -----------------------------------

    def test_done_requires_current_pass(self):
        self._seed_review()  # review.md written but no verdict recorded
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_code_change_after_pass_blocks_done(self):
        self._seed_review()
        self._bind("pass")
        self.commit_code("src/other_module.py", "def other():\n    return 0\n")
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_review_artifact_change_after_pass_blocks_done(self):
        self._seed_review()
        self._bind("pass")
        self._append_file(os.path.join(self.work, "review.md"),
                          "\n<!-- edited after verdict -->\n")
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_workflow_only_commit_still_permits_done(self):
        self._seed_review()
        self._bind("pass")
        self._append_file(os.path.join(self.work, "progress.md"),
                          "\n- task 1 complete\n")
        self.assertEqual(
            self._git("add", ".ai/work/T1/progress.md").returncode, 0)
        commit = self._git("commit", "-q", "-m", "fixture: progress only")
        self.assertEqual(commit.returncode, 0, commit.stderr)

        proc = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["phase"], "done")

    def test_done_is_not_reopened(self):
        self._seed_review()
        self._bind("pass")
        self.assertEqual(
            self.cli("advance", self.TICKET, "--to", "done").returncode, 0)
        attempts = (
            ["advance", self.TICKET, "--to", "review"],
            ["advance", self.TICKET, "--to", "implementation"],
            ["complete-task", self.TICKET],
            ["set-review", self.TICKET, "--verdict", "pass"],
        )
        for args in attempts:
            with self.subTest(cmd=" ".join(args[:2])):
                before = self.state_bytes()
                proc = self.cli(*args)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertEqual(self.state_bytes(), before)

    # -- append-only repair --------------------------------------------------

    def test_repair_preserves_completed_prefix(self):
        self._seed_review(total=1, verdict="changes_requested")
        self._bind("changes_requested")
        self._append_and_repair(2)

        data = self.read_state()
        self.assertEqual(data["phase"], "implementation")
        self.assertEqual(data["implementation"]["current_task"], 1)
        self.assertEqual(data["implementation"]["completed_tasks"], [1])
        self.assertEqual(data["next_action"]["role"], "ticket-executor")
        self.assertEqual(data["next_action"]["task"], 2)
        self.assertEqual(data["review"]["verdict"], "pending")

        # Execute the appended task, then a fresh passing Review completes it.
        self.commit_code("src/feature2.py", "def feature2():\n    return 2\n")
        self.assertEqual(
            self.cli("complete-task", self.TICKET, "--total", "2").returncode, 0)
        self.assertEqual(
            self.cli("advance", self.TICKET, "--to", "review").returncode, 0)
        self.write_review("pass")
        self._bind("pass")
        proc = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_state()["phase"], "done")

    def test_pass_cannot_repair(self):
        self._seed_review(verdict="pass")
        self._bind("pass")
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_repair_requires_appended_task(self):
        self._seed_review(verdict="changes_requested")
        self._bind("changes_requested")
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_repair_rejects_stale_failed_review(self):
        self._seed_review(verdict="changes_requested")
        self._bind("changes_requested")
        plan = self.write_plan(2)
        self.assertEqual(
            self.cli("register-plan", self.TICKET, "--path", plan,
                     "--total", "2").returncode, 0)
        self._append_file(os.path.join(self.work, "review.md"),
                          "\n<!-- edited after verdict -->\n")
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_repair_rejects_completed_prefix_edit(self):
        self._seed_review(verdict="changes_requested")
        self._bind("changes_requested")
        rel = os.path.join(".ai", "work", self.TICKET, "plan.md")
        changed = valid_plan(self.TICKET, 2).replace(
            "Carry out bounded step 1 for the fixture.",
            "REDESIGNED: do something else entirely.")
        self._write_file(rel, changed)
        before = self.state_bytes()
        proc = self.cli("register-plan", self.TICKET, "--path", rel,
                        "--total", "2")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_second_repair_cycle(self):
        self._seed_review(total=1, verdict="changes_requested")
        self._bind("changes_requested")
        self._append_and_repair(2)

        self.commit_code("src/feature2.py", "def feature2():\n    return 2\n")
        self.assertEqual(
            self.cli("complete-task", self.TICKET, "--total", "2").returncode, 0)
        self.assertEqual(
            self.cli("advance", self.TICKET, "--to", "review").returncode, 0)
        self.write_review("changes_requested")
        self._bind("changes_requested")
        self._append_and_repair(3)

        data = self.read_state()
        self.assertEqual(data["implementation"]["current_task"], 2)
        self.assertEqual(data["implementation"]["completed_tasks"], [1, 2])
        self.assertEqual(data["next_action"]["task"], 3)
        self.assertEqual(data["review"]["verdict"], "pending")

    def test_escalation_blocks_repair(self):
        self._seed_review(verdict="changes_requested")
        self._bind("changes_requested")
        plan = self.write_plan(2)
        self.assertEqual(
            self.cli("register-plan", self.TICKET, "--path", plan,
                     "--total", "2").returncode, 0)
        self.assertEqual(
            self.cli("escalate", self.TICKET, "--scope", "machine",
                     "--reason", "design change needs a senior").returncode, 0)
        before = self.state_bytes()
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    # -- validate agreement --------------------------------------------------

    def test_validate_reports_done_without_pass(self):
        self._seed_review()  # no verdict recorded
        data = self.read_state()
        data["phase"] = "done"
        data["next_action"] = {"role": None, "action": None, "task": None}
        self.write_state(data)
        proc = self.cli("validate", self.TICKET)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("review.verdict", proc.stdout)

    def test_validate_reports_stale_pass_binding(self):
        self._seed_review()
        self._bind("pass")
        self._append_file(os.path.join(self.work, "review.md"),
                          "\n<!-- edited after verdict -->\n")
        proc = self.cli("validate", self.TICKET)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("Review artifact changed", proc.stdout)

    def test_validate_accepts_repair_intermediate_state(self):
        self._seed_review(total=1, verdict="changes_requested")
        self._bind("changes_requested")
        self._append_and_repair(2)
        proc = self.cli("validate", self.TICKET)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("validate: OK", proc.stdout)

    def test_validate_and_resume_accept_pending_review_state(self):
        """A Ticket freshly advanced to `review` is valid at pending/pending.

        `advance --to review` never records a verdict, so `verdict == pending`
        with the three null bindings is the normal entry state -- not "a verdict
        is recorded". `validate` must stay clean and `resume` must not exit 1.
        """
        self._seed_review()  # phase=review, review.verdict=pending, all null
        data = self.read_state()
        self.assertEqual(data["phase"], "review")
        self.assertEqual(data["review"]["verdict"], "pending")
        for key in ("artifact_sha256", "reviewed_commit", "plan_sha256"):
            self.assertIsNone(data["review"][key])

        proc = self.cli("validate", self.TICKET)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("is missing but a verdict is recorded", proc.stdout)

        brief = self.cli("resume", self.TICKET)
        self.assertEqual(brief.returncode, 0, brief.stdout + brief.stderr)

    def test_converted_v1_review_has_no_false_binding_error(self):
        """A v1 Ticket at `review` converted to v2 keeps the pending scaffold.

        Conversion requires senior reconstruction (so validate is not clean),
        but it must never invent a recorded-verdict binding error for the
        `pending` scaffold it just wrote.
        """
        self.seed_v1("review")
        proc = self.cli("upgrade-ticket", self.TICKET)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = self.read_state()
        self.assertEqual(data["workflow_version"], 2)
        self.assertEqual(data["phase"], "review")
        self.assertEqual(data["review"]["verdict"], "pending")

        proc = self.cli("validate", self.TICKET)
        self.assertNotIn("is missing but a verdict is recorded", proc.stdout)

    # -- immutable commit identity and both-verdict binding (HARDEN-001) -----

    def test_review_rejects_symbolic_refs(self):
        """HEAD, branch and tag names are rejected even though they resolve.

        A recorded review must never follow a moving ref: the verdict binds to
        the immutable commit that was actually reviewed.
        """
        self._seed_review()
        branch = "wip-fix"
        self.assertEqual(self._git("branch", branch).returncode, 0)
        self.assertEqual(self._git("tag", "rel-1").returncode, 0)
        for ref in ("HEAD", branch, "rel-1"):
            with self.subTest(ref=ref):
                self.write_review("pass", reviewed_commit=ref)
                before = self.state_bytes()
                proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertEqual(self.state_bytes(), before)

    def test_review_short_oid_is_canonicalized(self):
        """An abbreviated hex prefix binds as the full object ID, both verdicts."""
        for verdict in ("pass", "changes_requested"):
            # Zero the counters so the next full lifecycle re-drive starts
            # fresh (register-plan preserves completed counts otherwise).
            data = self.read_state()
            data["implementation"] = {"current_task": 0, "total_tasks": 0,
                                      "completed_tasks": [], "task_hashes": []}
            self.write_state(data)
            reviewed = self._seed_review(verdict=verdict)
            self.write_review(verdict, reviewed_commit=reviewed[:7])
            proc = self.cli("set-review", self.TICKET, "--verdict", verdict)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(self.read_state()["review"]["reviewed_commit"],
                             reviewed)

    def test_changed_failed_review_blocks_validate_resume_repair(self):
        """Changed Review bytes block validate, resume AND the repair edge.

        The Review bytes are part of a `changes_requested` binding too: the
        appended-rework Plan stays registered, so the Review edit is the only
        defect, and every consumer must reject it without writing State.
        """
        self._seed_review(verdict="changes_requested")
        self._bind("changes_requested")
        plan = self.write_plan(2)
        proc = self.cli("register-plan", self.TICKET, "--path", plan,
                        "--total", "2")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self._append_file(os.path.join(self.work, "review.md"),
                          "\n<!-- edited after verdict -->\n")
        before_repair = self.state_bytes()

        validate_proc = self.cli("validate", self.TICKET)
        resume_proc = self.cli("resume", self.TICKET)
        repair_proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(validate_proc.returncode, 1,
                         validate_proc.stdout + validate_proc.stderr)
        self.assertEqual(resume_proc.returncode, 1,
                         resume_proc.stdout + resume_proc.stderr)
        self.assertEqual(repair_proc.returncode, 1,
                         repair_proc.stdout + repair_proc.stderr)
        self.assertEqual(self.state_bytes(), before_repair)

    def test_validate_and_resume_accept_failed_review_with_append(self):
        """A coherent failed-review append stays a valid intermediate state."""
        self._seed_review(verdict="changes_requested")
        self._bind("changes_requested")
        plan = self.write_plan(2)
        proc = self.cli("register-plan", self.TICKET, "--path", plan,
                        "--total", "2")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        proc = self.cli("validate", self.TICKET)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("validate: OK", proc.stdout)
        brief = self.cli("resume", self.TICKET)
        self.assertEqual(brief.returncode, 0, brief.stdout + brief.stderr)

    def test_failed_review_append_keeps_prefix(self):
        """The append-only repair preserves the completed task contracts."""
        self._seed_review(total=1, verdict="changes_requested")
        self._bind("changes_requested")
        completed = 1
        prefix = self.read_state()["implementation"]["task_hashes"][:completed]

        plan = self.write_plan(2)
        proc = self.cli("register-plan", self.TICKET, "--path", plan,
                        "--total", "2")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        repair_proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(repair_proc.returncode, 0,
                         repair_proc.stdout + repair_proc.stderr)

        data = self.read_state()
        self.assertEqual(data["implementation"]["task_hashes"][:completed],
                         prefix)
        self.assertEqual(data["implementation"]["current_task"], completed)
        self.assertEqual(data["review"]["verdict"], "pending")

    def test_deleted_binding_field_blocks_done(self):
        """A recorded pass with a deleted binding field cannot complete.

        The mutation guards must stay at least as strict as the pre-refactor
        unconditional comparisons: `advance` does not run validate, so a
        hand-corrupted State (verdict `pass`, `artifact_sha256` or
        `plan_sha256` removed) has to be rejected by the guard itself, with
        State bytes unchanged.
        """
        self._seed_review()
        self._bind("pass")
        for field in ("artifact_sha256", "plan_sha256"):
            with self.subTest(field=field):
                data = self.read_state()
                del data["review"][field]
                self.write_state(data)
                before = self.state_bytes()
                proc = self.cli("advance", self.TICKET, "--to", "done")
                self.assertEqual(proc.returncode, 1,
                                 proc.stdout + proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)
                self.assertIn("is missing but a verdict is recorded",
                              proc.stderr)
                self.assertEqual(self.state_bytes(), before)

    def test_symbolic_stored_binding_is_stale(self):
        """A legacy symbolic State binding is stale, never re-authenticated.

        Seeded directly (the only fixture doing so): a historical State that
        recorded `HEAD` must be reported by validate and resume without
        normalizing the value or resolving today's HEAD as the old approval.
        """
        self._seed_review()
        self._bind("pass")
        data = self.read_state()
        block = dict(data["review"])
        block["reviewed_commit"] = "HEAD"
        data["review"] = block
        self.write_state(data)
        before = self.state_bytes()

        proc = self.cli("validate", self.TICKET)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("review.reviewed_commit", proc.stdout)
        self.assertIn("stale", proc.stdout)
        self.assertEqual(self.state_bytes(), before)  # reported, not rewritten

        result = self.cli("resume", self.TICKET)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("review.reviewed_commit", result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_hex_named_ref_does_not_override_object_identity(self):
        """A branch named like a real object prefix never shadows the object.

        `resolve_commit` consults the object database, so a ref whose name
        happens to be the seven-character prefix of the reviewed commit
        cannot redirect the resolution to its own (different) target.
        """
        self._seed_review()
        original = self._git("rev-parse", "HEAD~1").stdout.strip()
        prefix = original[:7]
        self.assertEqual(self._git("branch", prefix, "HEAD").returncode, 0)
        self.assertEqual(review.resolve_commit(self.root, prefix), original)

    def test_resolve_commit_rejects_noncommit_and_unknown_hex(self):
        """Blob/tree objects and unknown hex prefixes raise ContractError."""
        self._seed_review()
        blob = self._git("rev-parse", "HEAD:src/feature.py").stdout.strip()
        tree = self._git("rev-parse", "HEAD^{tree}").stdout.strip()
        for revision in (blob, tree, "0000000"):
            with self.subTest(revision=revision):
                with self.assertRaises(contracts.ContractError):
                    review.resolve_commit(self.root, revision)

    def test_resolve_commit_rejects_ambiguous_prefix(self):
        """A prefix matching several objects is rejected, never guessed."""
        prefix = "abc1234"
        replies = {
            ("--is-inside-work-tree",): (0, b"true\n"),
            ("--show-object-format",): (0, b"sha1\n"),
            ("--disambiguate=%s" % prefix,): (
                0, ("abc1234" + "0" * 33 + "\n" + "abc1234" + "f" * 33 + "\n"
                    ).encode("ascii")),
        }

        def fake_run_git(root, args, env=None):
            rc, out = replies[tuple(args[1:])]
            proc = subprocess.CompletedProcess(args, rc)
            proc.stdout = out
            proc.stderr = b""
            return proc

        with mock.patch.object(review, "_run_git", fake_run_git):
            with self.assertRaises(contracts.ContractError) as ctx:
                review.resolve_commit("ignored", prefix)
        self.assertIn("ambiguous", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()