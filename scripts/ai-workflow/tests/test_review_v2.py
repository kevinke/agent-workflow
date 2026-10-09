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

    def _seed_review(self, total=1, verdict="pass", reviewed_commit=None,
                     extra_files=None):
        """Drive the public-command lifecycle into a bind-ready review phase.

        Returns the reviewed commit (the committed, tree-clean HEAD that the
        Review is written against). `decision.md` is written by the senior role
        and committed before that reviewed commit: implementation -> review now
        requires it on a v2 Ticket, and the same boundary requires a concrete
        handoff, so the fixture writes one through `write_handoff`.

        `extra_files` commits additional {repo-relative path: text} files into
        the reviewed tree (HARDEN-010 flag-matrix targets such as a tracked
        test fixture or a foreign Ticket record).
        """
        self._seed_implementation(total)
        self.write_decision()
        # The code under review, committed while in implementation.
        self.commit_code("src/feature.py", "def feature():\n    return 1\n")
        for rel, text in (extra_files or {}).items():
            self.commit_code(rel, text)
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
        """The index's cached mtime (ns) for `rel` from `git ls-files --debug`.

        Only called after any index-writing child has fully exited
        (`subprocess.run` waits), so the child's index write is visible here.
        """
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
        stat with a content-identical `git add`; the value the add child
        actually recorded is then captured from `git ls-files --debug` (the
        child has fully exited, so its index write is visible) and is the
        single source of truth: both the file and the real index are forced
        onto that captured value with `os.utime(ns=...)` — never sleeps.

        Windows can serve a just-backdated mtime to a later child process
        (cross-process metadata visibility), so the add child may record the
        pre-backdate value instead. The capture is therefore never compared to
        the requested backdate; whatever the child recorded becomes the
        collision base. Only if the captured value is less than a whole second
        old — too fresh for the deterministic freshness margin below — does one
        bounded re-backdate round run, and its capture is accepted
        unconditionally, so setup can never fail on an mtime value. The
        collision is thus at least a second old when any probe runs: a
        freshness-losing index copy (fresh mtime) misses the edit
        independently of elapsed time, and only a stat-preserving copy keeps
        git's racy-stat re-check engaged. No git child runs between the final
        `os.utime` pair and the command under test (the staged path-class
        variant's re-add is itself the scenario), so no later process can
        observe a stale worktree mtime inside that window. The only changed
        configuration is the temporary repo's local config (restored on
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
        # Content-identical re-add: only the cached stat is re-recorded, so the
        # blob and the index tree stay unchanged. Cross-process mtime
        # visibility is not assumed: whichever mtime this child records
        # (the requested backdate or a stale pre-backdate value) is what the
        # capture below turns into the collision base.
        for _ in range(2):
            backdated = ((time.time_ns() - 2_000_000_000)
                         // 1_000_000_000 * 1_000_000_000)
            os.utime(full, ns=(backdated, backdated))
            self.assertEqual(self._git("add", rel).returncode, 0)
            cached_ns = self._cached_mtime_ns(rel)
            if cached_ns <= time.time_ns() - 1_000_000_000:
                break  # collision base is already a whole second in the past
        with open(full, "r", encoding="utf-8", newline="") as fh:
            original = fh.read()
        self.assertIn("return 1", original)
        dirty = original.replace("return 1", "return 3")
        self.assertEqual(len(dirty), len(original))  # byte-length unchanged
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(dirty)
        # The captured value — not the requested backdate — is forced onto both
        # the file and the real index, so the entry's cached mtime equals the
        # index file's own mtime (git's racy-stat trigger) in every run.
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
        # Attribution is checked against the staleness lines: `resume` also names
        # every path changed since the Evidence observed commit, which includes
        # this file while the binding is still current.
        stale = self._stale_lines(resume_proc.stdout)
        self.assertTrue(any("src/feature.py" in line for line in stale), stale)

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

    # -- index-flag-independent drift (HARDEN-010) ---------------------------
    # `_set_flag`, `_clear_flag`, `_flagged_edit` and `_flagged_delete` are
    # inherited from `IndexHintFixture` in `v2_support`.

    def _flagged_append(self, flag, rel, text):
        """Set flag(s) on `rel`, then append `text` to it."""
        self._set_flag(rel, flag)
        self._append_file(os.path.join(self.root, rel), text)

    def _flagged_rejection_matrix(self, rel, mutate, extra_files=None):
        """Pin rejection of `rel` under every hint combination and verdict.

        Seeds once, then per (flag, verdict) subcase: rewrites the Review
        artifact for the verdict, applies `mutate(rel, flag)`, asserts the
        shared assessment names `rel`, asserts `set-review` rejects with the
        State bytes preserved, and finally clears the hints before restoring
        the reviewed tree (`git reset --hard` does not rewrite skip-worktree
        paths, so hints must be cleared first or leftover dirt would poison
        the next subcase).
        """
        reviewed = self._seed_review(extra_files=extra_files)
        for flag in self.INDEX_HINTS:
            for verdict in ("pass", "changes_requested"):
                with self.subTest(flag=flag, verdict=verdict):
                    # Cleanup in a `finally`: subTest continues after a failed
                    # assertion, so end-of-body cleanup would leak this subcase's
                    # hint and dirty path into the next one.
                    try:
                        self.write_review(verdict, reviewed_commit=reviewed)
                        # Baseline before any probe, so a probe that wrote to the
                        # real index could not be compared against its own output.
                        before = self.state_bytes()
                        mutate(rel, flag)
                        drift = review.code_drift(self.root, self.TICKET,
                                                  reviewed,
                                                  ".ai/work/T1/plan.md")
                        self.assertTrue(any(rel in item for item in drift),
                                        drift)
                        proc = self.cli("set-review", self.TICKET,
                                        "--verdict", verdict)
                        self.assertEqual(proc.returncode, 1,
                                         proc.stdout + proc.stderr)
                        self.assertNotIn("Traceback", proc.stderr)
                        self.assertEqual(self.state_bytes(), before)
                    finally:
                        self._unhint_and_rewind(rel)
                        self._restore(reviewed)

    def test_flagged_edit_blocks_both_verdicts(self):
        """A flagged equal-size source edit invalidates either verdict.

        Parameterized over `--assume-unchanged`, `--skip-worktree` and both,
        for `pass` and `changes_requested`: index hints are Git performance
        hints, not Workflow Protocol exemptions, so the dirty edit must still
        be reported as drift and `set-review` must reject.
        """
        self._flagged_rejection_matrix(
            "src/feature.py", lambda rel, flag: self._flagged_edit(flag, rel))

    def test_flagged_delete_blocks_both_verdicts(self):
        """A flagged source deletion invalidates either recorded verdict."""
        self._flagged_rejection_matrix(
            "src/feature.py",
            lambda rel, flag: self._flagged_delete(flag, rel))

    def test_flagged_fixture_edit_blocks_both_verdicts(self):
        """A flagged fixture edit invalidates either recorded verdict."""
        self._flagged_rejection_matrix(
            "tests/fixtures/sample.json",
            lambda rel, flag: self._flagged_edit(flag, rel,
                                                 old='"a": 1', new='"a": 2'),
            extra_files={"tests/fixtures/sample.json": '{"a": 1}\n'})

    def test_flagged_fixture_delete_blocks_both_verdicts(self):
        """A flagged fixture deletion invalidates either recorded verdict."""
        self._flagged_rejection_matrix(
            "tests/fixtures/sample.json",
            lambda rel, flag: self._flagged_delete(flag, rel),
            extra_files={"tests/fixtures/sample.json": '{"a": 1}\n'})

    def test_flagged_plan_edit_blocks_both_verdicts(self):
        """A flagged edit to the registered Plan invalidates either verdict."""
        self._flagged_rejection_matrix(
            ".ai/work/T1/plan.md",
            lambda rel, flag: self._flagged_append(
                flag, rel, "\n<!-- flagged plan drift -->\n"))

    def test_flagged_plan_delete_blocks_both_verdicts(self):
        """A flagged Plan deletion invalidates either recorded verdict."""
        self._flagged_rejection_matrix(
            ".ai/work/T1/plan.md",
            lambda rel, flag: self._flagged_delete(flag, rel))

    def test_clean_flags_and_exact_exemptions(self):
        """Unchanged flagged paths are accepted; exemptions stay exact.

        A flag on a present, unchanged relevant file must not create drift or
        block the verdict; each of the four exact Ticket records stays exempt
        even when flagged and modified, while another Ticket's record,
        untracked source and the registered Plan stay relevant under both
        hints.
        """
        other = ".ai/work/T2/state.yaml"
        reviewed = self._seed_review(
            extra_files={other: "placeholder: true\n"})
        plan_rel = ".ai/work/T1/plan.md"

        # A flagged, unchanged relevant file: no drift, and the verdict binds.
        self._set_flag("src/feature.py", "both")
        drift = review.code_drift(self.root, self.TICKET, reviewed, plan_rel)
        self.assertEqual(drift, [])
        proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self._clear_flag("src/feature.py", "both")

        # Each exact Ticket record stays exempt even when flagged and edited.
        for name in review.TICKET_EXEMPT_FILES:
            with self.subTest(record=name):
                rel = ".ai/work/T1/%s" % name
                if name == "review.md":
                    # The Review artifact is written after the reviewed
                    # commit (untracked until committed), so commit it here
                    # to make the hint applicable; an exempt path stays
                    # exempt whether committed, staged or dirty.
                    self.write_review("pass", reviewed_commit=reviewed)
                    self._commit_all("fixture: commit review artifact")
                self._flagged_append("both", rel, "\nflagged note\n")
                drift = review.code_drift(self.root, self.TICKET, reviewed,
                                          plan_rel)
                self.assertEqual(drift, [])
                self._clear_flag(rel, "both")
                self._restore(reviewed)

        # Another Ticket's record, untracked source and the registered Plan
        # stay relevant even under both hints.
        self._flagged_append("both", other, "# edited\n")
        self._write_file("src/untracked_new.py", "def new():\n    return 0\n")
        self._flagged_append("both", plan_rel,
                             "\n<!-- flagged plan drift -->\n")
        drift = review.code_drift(self.root, self.TICKET, reviewed, plan_rel)
        self.assertTrue(any(other in item for item in drift), drift)
        self.assertTrue(any("src/untracked_new.py" in item for item in drift),
                        drift)
        self.assertTrue(any(plan_rel in item for item in drift), drift)

    def test_flagged_unusual_paths(self):
        """Space and non-ASCII path names appear as intact drift paths.

        The hint-clearing payload is the raw NUL-delimited `ls-files -z` byte
        stream and every probe is NUL-delimited, so tracked paths containing
        spaces or non-ASCII bytes survive `update-index -z --stdin` and the
        diff probes without quoting or truncation. (A literal newline in a
        path cannot be fixtured on this host: both NTFS and git's path
        verification reject control characters, so no tracked entry can carry
        one here; the byte-transparent NUL framing covers it structurally.)
        """
        self._seed_review()
        spaced = "src/my file.py"
        unicode_spaced = "src/ünïcodé file.py"
        head = self.commit_code(spaced, "def spaced():\n    return 1\n")
        head = self.commit_code(unicode_spaced,
                                "def unicode():\n    return 1\n")
        self._flagged_edit("both", spaced, old="return 1", new="return 2")
        self._flagged_edit("both", unicode_spaced,
                           old="return 1", new="return 2")
        drift = review.code_drift(self.root, self.TICKET, head,
                                  ".ai/work/T1/plan.md")
        self.assertTrue(any(spaced in item for item in drift), drift)
        self.assertTrue(any(unicode_spaced in item for item in drift), drift)

    def test_sparse_absence_is_not_current(self):
        """A sparse-absent tracked path is drift or a named blocker.

        A real non-cone sparse checkout removes a tracked relevant path from
        the worktree and sets skip-worktree on it; the assessment must not
        report currentness — it names the path as deletion drift (or an
        explicit blocker). The verification is read-only: the real index keeps
        its bytes and nanosecond mtime, and the sparse path is still absent
        afterward (never materialized as a side effect).
        """
        reviewed = self._seed_review()
        self.assertEqual(
            self._git("config", "core.sparseCheckout", "true").returncode, 0)
        self.assertEqual(
            self._git("config", "core.sparseCheckoutCone", "false").returncode,
            0)
        sparse_dir = os.path.join(self.root, ".git", "info")
        os.makedirs(sparse_dir, exist_ok=True)
        with open(os.path.join(sparse_dir, "sparse-checkout"), "w",
                  encoding="utf-8", newline="") as fh:
            fh.write("/*\n!src/feature.py\n")
        self.assertEqual(self._git("read-tree", "-mu", "HEAD").returncode, 0)
        feature = os.path.join(self.root, "src", "feature.py")
        self.assertFalse(os.path.exists(feature))
        index_path = Path(self.root, ".git", "index")
        before_index = index_path.read_bytes()
        before_mtime = index_path.stat().st_mtime_ns

        drift = review.code_drift(self.root, self.TICKET, reviewed,
                                  ".ai/work/T1/plan.md")
        self.assertTrue(drift, "a sparse-absent relevant path is not current")
        self.assertTrue(any("src/feature.py" in item for item in drift), drift)
        self.assertEqual(index_path.read_bytes(), before_index)
        self.assertEqual(index_path.stat().st_mtime_ns, before_mtime)
        self.assertFalse(os.path.exists(feature))

    def test_flagged_racy_edit_preserves_real_index(self):
        """Hint clearing in the copy keeps racy-stat detection engaged.

        Extends the HARDEN-002 collision with index hints on the entry.
        `git add` refuses skip-worktree paths and does not re-stat
        assume-unchanged ones, so the hints are set after the cached-stat
        capture; marking them rewrites the real index, so the captured
        nanosecond collision (entry cached mtime == file mtime == index
        mtime, byte size unchanged, content dirty) is re-forced with
        `os.utime(ns=...)` afterwards -- never sleeps. The disposable copy's
        hint-clearing `update-index` rewrites bump its own mtime; only
        restoring the captured timestamps before the diffs keeps git's
        racy-stat re-check engaged so the equal-size edit stays detected. The
        real index bytes, hint flags and nanosecond mtime, State, the Review
        artifact and a pre-existing real index.lock must all survive.
        """
        reviewed = self._seed_review()
        rel = "src/feature.py"
        index_path = Path(self.root, ".git", "index")
        lock_path = Path(self.root, ".git", "index.lock")
        review_path = os.path.join(self.work, "review.md")
        for flag in self.INDEX_HINTS:
            with self.subTest(flag=flag):
                self.write_review("pass", reviewed_commit=reviewed)
                self._racy_edit(rel)
                self._set_flag(rel, flag)
                # Marking the hints rewrote the real index; the cached stat is
                # unchanged, so re-force the captured collision onto the file
                # and the real index before any probe runs.
                cached_ns = self._cached_mtime_ns(rel)
                full = os.path.join(self.root, rel)
                os.utime(full, ns=(cached_ns, cached_ns))
                os.utime(index_path, ns=(cached_ns, cached_ns))
                if not lock_path.exists():
                    with open(lock_path, "wb") as fh:
                        fh.write(b"stale lock from a crashed git\n")

                before_state = self.state_bytes()
                before_index = index_path.read_bytes()
                before_index_mtime = index_path.stat().st_mtime_ns
                before_flags = self._git("ls-files", "-v", "-z",
                                         "--", rel).stdout
                with open(review_path, "rb") as fh:
                    before_review = fh.read()
                before_lock = lock_path.read_bytes()
                before_lock_mtime = lock_path.stat().st_mtime_ns

                drift = review.code_drift(self.root, self.TICKET, reviewed,
                                          ".ai/work/T1/plan.md")
                self.assertTrue(any(rel in item for item in drift), drift)
                proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
                self.assertEqual(proc.returncode, 1,
                                 proc.stdout + proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)

                self.assertEqual(self.state_bytes(), before_state)
                self.assertEqual(index_path.read_bytes(), before_index)
                self.assertEqual(index_path.stat().st_mtime_ns,
                                 before_index_mtime)
                after_flags = self._git("ls-files", "-v", "-z",
                                        "--", rel).stdout
                self.assertEqual(after_flags, before_flags)
                with open(review_path, "rb") as fh:
                    self.assertEqual(fh.read(), before_review)
                self.assertEqual(lock_path.read_bytes(), before_lock)
                self.assertEqual(lock_path.stat().st_mtime_ns,
                                 before_lock_mtime)

                # The planted real index.lock blocks index-writing children,
                # so remove it before the flag cleanup and the restore (the
                # assessment itself never touches it, as just asserted).
                os.remove(lock_path)
                self._clear_flag(rel, flag)
                self._restore(reviewed)

    def test_index_preparation_failure_is_closed(self):
        """Every preparation failure closes the assessment; none falls back.

        Five failure modes -- the index copy, the `--no-assume-unchanged`
        update-index, the `--no-skip-worktree` update-index, the `os.utime`
        timestamp restore and a missing real index -- must each raise a named
        `ContractError`; a split index whose shared part cannot be safely
        expanded in the disposable copy returns a named blocker problem
        instead (never an empty result). The flagged file is dirty throughout,
        so any silent fallback to the real hinted index would wrongly report
        currentness. No mode leaks a temporary directory, and the real index
        bytes, hint flags, nanosecond mtime and shared-index parts survive.
        """
        reviewed = self._seed_review()
        rel = "src/feature.py"
        self._flagged_edit("both", rel)
        index_path = Path(self.root, ".git", "index")

        def drift_call():
            return review.code_drift(self.root, self.TICKET, reviewed,
                                     ".ai/work/T1/plan.md")

        def assert_closed(expect):
            before_dirs = self._index_tmpdirs()
            before_bytes = index_path.read_bytes()
            before_mtime = index_path.stat().st_mtime_ns
            before_flags = self._git("ls-files", "-v", "-z", "--", rel).stdout
            with self.assertRaises(contracts.ContractError) as ctx:
                drift_call()
            self.assertIn(expect, str(ctx.exception))
            self.assertEqual(self._index_tmpdirs(), before_dirs)
            self.assertEqual(index_path.read_bytes(), before_bytes)
            self.assertEqual(index_path.stat().st_mtime_ns, before_mtime)
            self.assertEqual(
                self._git("ls-files", "-v", "-z", "--", rel).stdout,
                before_flags)

        with self.subTest(mode="index-copy"):
            real_copy2 = review.shutil.copy2

            def failing_copy2(src, dst, **kwargs):
                if "ai-workflow-index-" in str(dst):
                    raise OSError("simulated index copy failure")
                return real_copy2(src, dst, **kwargs)

            with mock.patch("review.shutil.copy2", failing_copy2):
                assert_closed("cannot read the Git index")

        for mode, flag in (
                ("assume-unchanged-command", "--no-assume-unchanged"),
                ("skip-worktree-command", "--no-skip-worktree")):
            with self.subTest(mode=mode):
                real_run_git = review._run_git

                def failing_run_git(root, args, env=None, input_bytes=None,
                                    _flag=flag, _real=real_run_git):
                    if _flag in args:
                        return subprocess.CompletedProcess(
                            list(args), 1, b"", b"simulated git failure")
                    return _real(root, args, env, input_bytes)

                with mock.patch.object(review, "_run_git", failing_run_git):
                    assert_closed(flag)

        with self.subTest(mode="utime"):
            real_utime = os.utime

            def failing_utime(path, *args, **kwargs):
                if "ai-workflow-index-" in str(path):
                    raise OSError("simulated timestamp failure")
                return real_utime(path, *args, **kwargs)

            with mock.patch("review.os.utime", failing_utime):
                assert_closed("timestamp")

        with self.subTest(mode="missing-index"):
            saved = str(index_path) + ".saved"
            os.rename(index_path, saved)
            try:
                before_dirs = self._index_tmpdirs()
                with self.assertRaises(contracts.ContractError) as ctx:
                    drift_call()
                self.assertIn("cannot read the Git index", str(ctx.exception))
                self.assertEqual(self._index_tmpdirs(), before_dirs)
            finally:
                os.replace(saved, index_path)

        with self.subTest(mode="split-index"):
            proc = self._git("update-index", "--split-index")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            try:
                git_dir = Path(self.root, ".git")
                before_dirs = self._index_tmpdirs()
                before_shared = {p.name: p.read_bytes()
                                 for p in git_dir.glob("sharedindex.*")}
                self.assertTrue(before_shared)
                before_bytes = index_path.read_bytes()
                before_mtime = index_path.stat().st_mtime_ns
                before_flags = self._git("ls-files", "-v", "-z",
                                         "--", rel).stdout
                before_state = self.state_bytes()

                problems = drift_call()
                self.assertTrue(problems,
                                "a split index must never assess as current")
                self.assertTrue(any("split index" in item
                                    for item in problems), problems)
                proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
                self.assertEqual(proc.returncode, 1,
                                 proc.stdout + proc.stderr)
                self.assertNotIn("Traceback", proc.stderr)

                self.assertEqual(self.state_bytes(), before_state)
                self.assertEqual(index_path.read_bytes(), before_bytes)
                self.assertEqual(index_path.stat().st_mtime_ns, before_mtime)
                self.assertEqual(
                    self._git("ls-files", "-v", "-z", "--", rel).stdout,
                    before_flags)
                self.assertEqual(
                    {p.name: p.read_bytes()
                     for p in git_dir.glob("sharedindex.*")},
                    before_shared)
                self.assertEqual(self._index_tmpdirs(), before_dirs)
            finally:
                proc = self._git("update-index", "--no-split-index")
                self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_unmerged_index_still_assesses_drift(self):
        """An in-progress merge conflict must not break the assessment.

        Clearing hints by rewriting *every* tracked path makes `update-index`
        refuse the unmerged entry ("Unable to mark file"), which turned an
        ordinary mid-merge repository into one where the shared assessment raised
        a Git-internal error instead of reporting the drift it was asked about,
        and all five consumers inherited that opaque refusal. Only entries that
        actually carry a hint are rewritten, so a conflicted path is still named.
        """
        conflict = "src/other.py"
        self._seed_review(extra_files={
            conflict: "def other():\n    return 1\n"})
        branch = self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        # Diverge both sides of the same region so the merge cannot fast-forward.
        self.assertEqual(
            self._git("checkout", "-q", "-b", "side").returncode, 0)
        self._write_file(conflict, "def other():\n    return 2\n")
        self.assertEqual(
            self._git("commit", "-q", "-am", "fixture: side edit").returncode, 0)
        self.assertEqual(
            self._git("checkout", "-q", branch).returncode, 0)
        self._write_file(conflict, "def other():\n    return 3\n")
        self.assertEqual(
            self._git("commit", "-q", "-am", "fixture: main edit").returncode, 0)
        head = self._git("rev-parse", "HEAD").stdout.strip()
        merge = self._git("merge", "--no-commit", "side")
        self.assertNotEqual(merge.returncode, 0, merge.stdout + merge.stderr)
        self.assertIn("UU", self._git("status", "--porcelain").stdout)

        drift = review.code_drift(self.root, self.TICKET, head,
                                  ".ai/work/T1/plan.md")
        self.assertTrue(any(conflict in item for item in drift), drift)
        self.assertFalse(any("update-index" in item for item in drift), drift)

        # The public command must reject because of drift, not because Git
        # could not mark an unmerged entry.
        self.write_review("pass", reviewed_commit=head)
        proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertNotIn("update-index", combined)
        self.assertIn(conflict, combined)

    def test_assessment_creates_nothing_in_git_dir(self):
        """A read-only assessment must not create files inside `.git`.

        Clearing hints rewrites the disposable index copy, and git honors
        `core.splitIndex` (which its own `feature.manyFiles` recipe turns on) by
        splitting whatever index it writes — dropping an orphan
        `sharedindex.<oid>` into the real common dir. Nothing is rewritten when
        no entry carries a hint, and the rewrite that is needed passes
        `--no-split-index`, so the common dir keeps exactly the files it had.

        The listing is taken with `os.listdir` immediately before each
        assessment rather than through the shared snapshot: once the setting is
        on, any Git command that touches the index — including `ls-files` in the
        snapshot helper and the fixture's own `update-index` that sets the hint —
        may split it, and that write must not be mistaken for the assessment's.
        """
        rel = "src/feature.py"
        reviewed = self._seed_review()
        git_dir = os.path.join(self.root, ".git")

        def listing():
            return sorted(os.listdir(git_dir))

        cfg = self._git("config", "core.splitIndex", "true")
        self.assertEqual(cfg.returncode, 0, cfg.stderr)
        self.addCleanup(self._git, "config", "--unset", "core.splitIndex")

        # No hint set anywhere: the copy is never rewritten at all.
        before = listing()
        self.assertEqual(review.code_drift(self.root, self.TICKET, reviewed,
                                           ".ai/work/T1/plan.md"), [])
        self.assertEqual(listing(), before,
                         "a hint-free assessment created files under .git")

        # Setting a hint runs `update-index` against the real index, which git
        # splits once the setting is on. From there the assessment must refuse
        # with the documented blocker instead of expanding the shared half, and
        # it must still add nothing of its own — the non-empty blocker is also
        # proof an unassessable tree is never reported as current.
        self._flagged_edit("both", rel)
        before = listing()
        drift = review.code_drift(self.root, self.TICKET, reviewed,
                                  ".ai/work/T1/plan.md")
        self.assertTrue(any("split index" in item for item in drift), drift)
        self.assertEqual(listing(), before,
                         "a refused assessment created files under .git")
        self._unhint_and_rewind(rel)

    # -- consumer agreement on flagged staleness (HARDEN-010 Task 2) ---------
    # `_snapshot`, `_assert_unchanged` and the hint primitives are inherited
    # from `IndexHintFixture` in `v2_support`.

    def _assert_binding_clean(self, rel):
        """Pin the pre-mutation baseline so a later rejection is not vacuous.

        Without this a subcase could inherit dirt from a failed predecessor and
        its rejection would be true for the wrong reason. Attribution is checked
        against the staleness lines rather than the whole output, because
        `resume` names `rel` in its Evidence anchor notice even while the Review
        binding is current.
        """
        snap = self._snapshot(rel)
        proc = self.cli("validate", self.TICKET)
        self.assertFalse(any(rel in line for line in
                             self._stale_lines(proc.stdout)), proc.stdout)
        self._assert_unchanged(rel, snap)

    def _assert_flagged_staleness(self, rel, verdict):
        """Assert `validate`, `resume` and the done gate all reject the binding.

        `validate` and `resume` must name `rel` for either verdict: the shared
        assessment prefixes every drift problem with `review is stale: ...` plus
        the path, regardless of which verdict was recorded. The `review -> done`
        gate is the one exception — it requires a `pass` before it reaches any
        drift check, so a recorded `changes_requested` fails there for its own
        reason and legitimately names nothing.
        """
        snap = self._snapshot(rel)

        validate_proc = self.cli("validate", self.TICKET)
        self.assertEqual(validate_proc.returncode, 1,
                         validate_proc.stdout + validate_proc.stderr)
        self.assertNotIn("Traceback", validate_proc.stderr)
        stale = self._stale_lines(validate_proc.stdout)
        self.assertTrue(stale, validate_proc.stdout)
        self.assertTrue(any(rel in line for line in stale), stale)

        resume_proc = self.cli("resume", self.TICKET)
        self.assertEqual(resume_proc.returncode, 1,
                         resume_proc.stdout + resume_proc.stderr)
        self.assertNotIn("Traceback", resume_proc.stderr)
        stale = self._stale_lines(resume_proc.stdout)
        self.assertTrue(stale, resume_proc.stdout)
        self.assertTrue(any(rel in line for line in stale), stale)

        done_proc = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(done_proc.returncode, 1,
                         done_proc.stdout + done_proc.stderr)
        self.assertNotIn("Traceback", done_proc.stderr)
        if verdict == "pass":
            stale = self._stale_lines(done_proc.stderr)
            self.assertTrue(stale, done_proc.stderr)
            self.assertTrue(any(rel in line for line in stale), stale)

        # A stale verdict stays stale: no consumer upgraded it to a fresh pass.
        self.assertEqual(self.read_state()["review"]["verdict"], verdict)
        self._assert_unchanged(rel, snap)

    def _run_flagged_subcase(self, reviewed, rel, verdict, flag, kind):
        """Bind, prove clean, hide a change, then prove every consumer rejects.

        Cleanup runs in a `finally`: `subTest` swallows a failed assertion and
        continues with the next subcase, so end-of-body cleanup never runs on the
        path that matters and a leaked hint or deleted file would make every
        later subcase's rejection vacuously true. `setUp` builds one repository
        per method, so the leak that matters is between subcases, not tests.
        """
        try:
            self.write_review(verdict, reviewed_commit=reviewed)
            self._bind(verdict)
            self._assert_binding_clean(rel)
            if kind == "edit":
                self._flagged_edit(flag, rel)
            else:
                self._flagged_delete(flag, rel)
            self._assert_flagged_staleness(rel, verdict)
        finally:
            self._unhint_and_rewind(rel)
            self._restore(reviewed)

    def test_flagged_binding_is_stale(self):
        """Hints cannot keep a bound Review current for the other consumers.

        `set-review` is only one reader of the shared assessment. Here the
        Review is bound against a clean tree first, then an index hint hides an
        equal-size edit or a deletion. `validate`, `resume` and the
        `review -> done` gate must all reject, and none of them may write or
        upgrade the recorded verdict.
        """
        rel = "src/feature.py"
        reviewed = self._seed_review()
        for verdict in ("pass", "changes_requested"):
            for flag in self.INDEX_HINTS:
                for kind in ("edit", "delete"):
                    with self.subTest(verdict=verdict, flag=flag, kind=kind):
                        self._run_flagged_subcase(reviewed, rel, verdict,
                                                  flag, kind)

    def test_flagged_binding_stale_survives_metadata_commit(self):
        """A workflow-only commit does not launder a flagged dirty file current.

        Committing only a workflow record advances HEAD while `rel` stays dirty
        under its hint, so the drift probe still compares the worktree against
        the reviewed commit and every consumer keeps rejecting. This pins the
        interaction between the existing metadata-only allowance and hint
        clearing rather than trusting that the reviewed commit moved.
        """
        rel = "src/feature.py"
        reviewed = self._seed_review()
        for flag in self.INDEX_HINTS:
            with self.subTest(flag=flag):
                try:
                    self.write_review("pass", reviewed_commit=reviewed)
                    self._bind("pass")
                    self._flagged_edit(flag, rel)
                    self._append_file(os.path.join(self.work, "progress.md"),
                                      "\n- flagged-cycle note\n")
                    # Stage the record alone, so the bound State stays a worktree
                    # change and this commit is genuinely workflow-only.
                    add = self._git("add", "--", ".ai/work/T1/progress.md")
                    self.assertEqual(add.returncode, 0, add.stderr)
                    commit = self._git("commit", "-q", "-m",
                                       "fixture: workflow-only commit")
                    self.assertEqual(commit.returncode, 0, commit.stderr)
                    self._assert_flagged_staleness(rel, "pass")
                finally:
                    self._unhint_and_rewind(rel)
                    self._restore(reviewed)

    def test_clean_flagged_binding_still_accepted_by_consumers(self):
        """A hint on an unchanged file must not make a consumer reject the Review.

        Task 1 pins the no-false-positive rule at the assessment level; this pins
        it where a future probe that rejected any hinted path would regress:
        while either or both bits are set on a present, unmodified tracked file,
        `validate` and `resume` stay silent and write nothing, and only then may
        the `review -> done` gate succeed. The done call legitimately mutates
        State, so the byte-preservation check runs before it.
        """
        rel = "src/feature.py"
        reviewed = self._seed_review()
        for flag in self.INDEX_HINTS:
            with self.subTest(flag=flag):
                try:
                    self.write_review("pass", reviewed_commit=reviewed)
                    self._bind("pass")
                    self._set_flag(rel, flag)
                    snap = self._snapshot(rel)

                    validate_proc = self.cli("validate", self.TICKET)
                    self.assertEqual(validate_proc.returncode, 0,
                                     validate_proc.stdout + validate_proc.stderr)
                    self.assertNotIn("stale", validate_proc.stdout)

                    resume_proc = self.cli("resume", self.TICKET)
                    self.assertEqual(resume_proc.returncode, 0,
                                     resume_proc.stdout + resume_proc.stderr)
                    self.assertNotIn("Traceback", resume_proc.stderr)

                    # Read-only probes so far: nothing may have moved.
                    self._assert_unchanged(rel, snap)

                    done_proc = self.cli("advance", self.TICKET, "--to", "done")
                    self.assertEqual(done_proc.returncode, 0,
                                     done_proc.stdout + done_proc.stderr)
                    self.assertEqual(self.read_state()["review"]["verdict"],
                                     "pass")
                finally:
                    self._unhint_and_rewind(rel)
                    self._restore(reviewed)

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