"""Tests for the read-only continuation brief (SCOUT-006 Task 1, spec decision 7).

Covers the `ai-workflow resume <ticket-id>` CLI and `resume.resume_for_ticket`:
the frozen section headings, the exit-code semantics (0 valid brief, 1 ERROR
blockers/unreadable State, 2 usage), strict read-only behavior (byte identity
*and* mtime identity), v1 missing-contract notices, artifact paths + digests,
dirty-Git and missing-artifact cases, and the two continued-lifecycle contracts.

The lifecycle is driven through the real CLI. Where a test starts a "receiver"
session it does so in a *separate* CLI process, but this is a **simulated CLI
session**: it is not proof of a real model or Harness switch.
"""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from v2_support import V2CLITestCase  # noqa: E402


class ResumeV2Test(V2CLITestCase):
    """Simulated sender/receiver CLI sessions over a throwaway repository.

    Each `self.cli(...)` call is an independent process, standing in for a
    different session whose only shared state is the repository (State and
    artifacts). The simulation is labelled as such; it does not model a real
    model or Harness handoff.
    """

    # -- fixture helpers -----------------------------------------------------

    def _seed_audit(self):
        """Reach `evidence_audit` with a bound sufficient gate."""
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        proc = self.cli("set-gate", self.TICKET, "--gate", "sufficient",
                        "--round", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def _seed_implementation(self, total=2):
        """Reach a ready v2 implementation with a registered `total`-task Plan."""
        self._seed_audit()
        self.write_decision()  # the senior's decision.md precedes planning
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

    def _seed_review(self, total=1):
        """Reach `review` with a bound current `pass` verdict.

        Drives public commands so resume's read path includes the review probe
        (`review.code_drift`). The `implementation -> review` entry guard needs
        a concrete handoff, so the fixture writes one via `write_handoff`.
        """
        self._seed_implementation(total)
        self.commit_code("src/feature.py", "def feature():\n    return 1\n")
        for _ in range(total):
            proc = self.cli("complete-task", self.TICKET,
                            "--total", str(total))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.write_handoff()
        proc = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self._git("add", "-A").returncode, 0)
        commit = self._git("commit", "-q", "-m", "fixture: reviewed tree")
        self.assertEqual(commit.returncode, 0, commit.stderr)
        head = self._git("rev-parse", "HEAD").stdout.strip()
        self.write_review("pass", reviewed_commit=head)
        proc = self.cli("set-review", self.TICKET, "--verdict", "pass")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return head

    def _seed_failed_review(self, total=1):
        """Reach `review` with a bound `changes_requested` verdict."""
        self._seed_implementation(total)
        self.commit_code("src/feature.py", "def feature():\n    return 1\n")
        for _ in range(total):
            proc = self.cli("complete-task", self.TICKET,
                            "--total", str(total))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.write_handoff()
        proc = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self._git("add", "-A").returncode, 0)
        commit = self._git("commit", "-q", "-m", "fixture: reviewed tree")
        self.assertEqual(commit.returncode, 0, commit.stderr)
        head = self._git("rev-parse", "HEAD").stdout.strip()
        self.write_review("changes_requested", reviewed_commit=head)
        proc = self.cli("set-review", self.TICKET, "--verdict",
                        "changes_requested")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return head

    def _write_file(self, rel, text):
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

    # -- index hints (HARDEN-010) ---------------------------------------------

    def _set_flag(self, path, flag):
        """Set one or both index hints via separate Git commands.

        Both bits need their own command: a single `update-index` cannot express
        the combination, and clearing is likewise done bit by bit.
        """
        if flag in ("assume-unchanged", "both"):
            proc = self._git("update-index", "--assume-unchanged", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
        if flag in ("skip-worktree", "both"):
            proc = self._git("update-index", "--skip-worktree", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def _clear_flag(self, path, flag):
        if flag in ("assume-unchanged", "both"):
            proc = self._git("update-index", "--no-assume-unchanged", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)
        if flag in ("skip-worktree", "both"):
            proc = self._git("update-index", "--no-skip-worktree", path)
            self.assertEqual(proc.returncode, 0, proc.stderr)

    def _flagged_edit(self, flag, rel="src/feature.py",
                      old="return 1", new="return 9"):
        """Hint `rel`, then rewrite it at an unchanged byte size."""
        self._set_flag(rel, flag)
        full = os.path.join(self.root, rel)
        with open(full, "r", encoding="utf-8", newline="") as fh:
            original = fh.read()
        dirty = original.replace(old, new)
        self.assertEqual(len(dirty), len(original))
        self.assertNotEqual(dirty, original)
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(dirty)

    def _flagged_delete(self, flag, rel="src/feature.py"):
        self._set_flag(rel, flag)
        os.remove(os.path.join(self.root, rel))

    def _restore_code(self, rel):
        """Rewind `rel`'s worktree bytes from the index, leaving the binding.

        The resume seeds bind their verdict *after* the reviewed commit, so
        `review.md` is untracked there and the bound `state.yaml` is a worktree
        change. A `git clean -fd`/`reset --hard` rewind would therefore delete
        the Review artifact and unbind the verdict, so subcases restore the
        mutated path alone instead. Hints must be cleared first: `git checkout`
        skips a `skip-worktree` path.
        """
        proc = self._git("checkout", "--", rel)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)

    def _assert_flagged_resume_blocker(self, rel, verdict):
        """`resume` must surface the hidden change and change nothing.

        Asserts the currentness blocker, that the recorded verdict was not
        rewritten, and that the real index (bytes, nanosecond mtime and its
        hint flags) plus the State and Review artifact bytes are untouched.
        """
        index = os.path.join(self.root, ".git", "index")
        review_path = os.path.join(self.work, "review.md")
        before_state = self.state_bytes()
        with open(index, "rb") as fh:
            before_index = fh.read()
        before_index_mtime = os.stat(index).st_mtime_ns
        before_flags = self._git("ls-files", "-v", "-z", "--", rel).stdout
        with open(review_path, "rb") as fh:
            before_review = fh.read()

        result = self.cli("resume", self.TICKET)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ERROR", result.stdout)
        self.assertIn("stale", result.stdout)
        self.assertIn(rel, result.stdout)
        self.assertNotIn("Traceback", result.stderr)

        self.assertEqual(self.read_state()["review"]["verdict"], verdict)
        self.assertEqual(self.state_bytes(), before_state)
        with open(index, "rb") as fh:
            self.assertEqual(fh.read(), before_index,
                             ".git/index bytes changed: resume wrote to it")
        self.assertEqual(os.stat(index).st_mtime_ns, before_index_mtime,
                         ".git/index mtime changed: resume rewrote it")
        self.assertEqual(
            self._git("ls-files", "-v", "-z", "--", rel).stdout, before_flags,
            "index hints changed: the probe cleared flags in the real index")
        with open(review_path, "rb") as fh:
            self.assertEqual(fh.read(), before_review)

    def _mtimes(self):
        """st_mtime_ns for every non-Git file currently under the repo."""
        return {rel: os.stat(os.path.join(self.root, rel)).st_mtime_ns
                for rel in self.capture_files()}

    def _digest(self, rel):
        with open(os.path.join(self.root, rel), "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    # -- read-only contract --------------------------------------------------

    def test_resume_does_not_rewrite_files(self):
        self.seed_v2("requirement")
        before = self.capture_files()
        before_mtimes = self._mtimes()
        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 0)
        self.assertIn("checkpoint-handoff", result.stdout)
        self.assertEqual(self.capture_files(), before)
        self.assertEqual(self._mtimes(), before_mtimes)

    def test_resume_does_not_refresh_git_index(self):
        """Read-only covers Git internals too, not just tracked files.

        A plain `git status` (as `validate._git_dirty` runs) opportunistically
        refreshes the stat cache and rewrites `.git/index`; only
        `--no-optional-locks` prevents that. Touch a tracked file so its cached
        stat is stale, then assert the index is byte- and mtime-identical across
        a resume call. This fails if the lock-safety flag is removed.
        """
        self.seed_v2("requirement")
        index = os.path.join(self.root, ".git", "index")
        self.assertTrue(os.path.exists(index), "fixture must have a Git index")

        # Force a stale stat entry: a plain `git status` must then refresh (and
        # rewrite) the index to record the new stat.
        tracked = os.path.join(self.root, "src", "app.py")
        stale = os.stat(tracked).st_mtime_ns + 5_000_000_000
        os.utime(tracked, ns=(stale, stale))

        with open(index, "rb") as fh:
            before_bytes = fh.read()
        before_mtime = os.stat(index).st_mtime_ns

        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        with open(index, "rb") as fh:
            self.assertEqual(fh.read(), before_bytes,
                             ".git/index bytes changed: resume refreshed it")
        self.assertEqual(os.stat(index).st_mtime_ns, before_mtime,
                         ".git/index mtime changed: resume refreshed it")

    def test_resume_review_path_is_lock_safe(self):
        """The review-freshness probe (`review.code_drift`) is lock-safe too.

        A v2 Ticket in `review` with a current `pass` verdict makes resume call
        `review.code_drift`, whose `git diff` (worktree vs index) would refresh
        the stat cache and rewrite `.git/index` without
        `--no-optional-locks`. Force a stale stat and assert the index is
        untouched; this fails if `review._run_git` drops the flag.
        """
        self._seed_review()
        index = os.path.join(self.root, ".git", "index")
        self.assertTrue(os.path.exists(index), "fixture must have a Git index")

        tracked = os.path.join(self.root, "src", "feature.py")
        stale = os.stat(tracked).st_mtime_ns + 5_000_000_000
        os.utime(tracked, ns=(stale, stale))

        with open(index, "rb") as fh:
            before_bytes = fh.read()
        before_mtime = os.stat(index).st_mtime_ns

        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        with open(index, "rb") as fh:
            self.assertEqual(fh.read(), before_bytes,
                             ".git/index bytes changed: resume refreshed it")
        self.assertEqual(os.stat(index).st_mtime_ns, before_mtime,
                         ".git/index mtime changed: resume refreshed it")

    def test_brief_sections_present_and_ordered(self):
        self.seed_v2("requirement")
        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        headings = ["Ticket", "State", "Next action", "Repository",
                    "Artifacts", "Checks"]
        positions = [result.stdout.index(h) for h in headings]
        self.assertEqual(positions, sorted(positions), result.stdout)

    # -- exit-code semantics -------------------------------------------------

    def test_readable_blocked_ticket_prints_brief_exit_one(self):
        self.seed_v2("requirement")
        proc = self.cli("set-status", "T1", "--status", "blocked")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Ticket", result.stdout)
        self.assertIn("blocked", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    def test_unknown_ticket_exits_one(self):
        result = self.cli("resume", "NOPE")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("unknown ticket", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_malformed_state_exits_one_without_traceback(self):
        with open(self._state_path(), "w", encoding="utf-8", newline="") as fh:
            fh.write("- not\n- a\n- map\n")
        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_usage_errors_exit_two(self):
        cases = (("resume",), ("resume", "T1", "extra"))
        for args in cases:
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2,
                                 result.stdout + result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    # -- v1 notices ----------------------------------------------------------

    def test_v1_ticket_gets_missing_contract_notices(self):
        # setUp's `start` now yields v2 (Task 2); the v1 version is explicit.
        self.seed_v1("requirement")
        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("v1", result.stdout)
        self.assertIn("no registered Plan", result.stdout)

    # -- artifacts: paths, digests, missing, dirty ---------------------------

    def test_artifact_path_and_digest_shown(self):
        self._seed_audit()
        digest = self._digest(os.path.join(".ai", "work", "T1", "evidence.md"))
        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("evidence.md", result.stdout)
        self.assertIn(digest, result.stdout)

    def test_dirty_repository_lists_paths(self):
        self._write_file("notes.txt", "uncommitted\n")
        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("notes.txt", result.stdout)

    def test_missing_artifact_is_an_error_blocker(self):
        self._seed_audit()
        for target in ("technical_decision", "planning"):
            proc = self.cli("advance", "T1", "--to", target)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # decision.md is deliberately absent in `planning`.
        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("decision.md", result.stdout)
        self.assertIn("ERROR", result.stdout)

    # -- continued lifecycle: a new process reads the persisted next task ----

    def test_receiver_uses_persisted_next_task(self):
        # Simulated sender session (separate processes): register two tasks and
        # complete the first.
        self._seed_implementation(2)
        proc = self.cli("complete-task", "T1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        persisted = self.state_bytes()

        # A new receiver process knows only the root and the Ticket id.
        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("ticket-executor", result.stdout)
        self.assertIn("2 (executable task)", result.stdout)
        # resume is read-only: the persisted State is byte-identical.
        self.assertEqual(self.state_bytes(), persisted)

        # The receiver completes the ordered next task; the count advances.
        proc = self.cli("complete-task", "T1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        data = self.read_state()
        self.assertEqual(data["implementation"]["current_task"], 2)
        self.assertEqual(data["implementation"]["completed_tasks"], [1, 2])

    # -- older Evidence commit: relevance assessment, not rejection ----------

    def test_old_evidence_requires_relevance_assessment(self):
        self._seed_audit()
        digest = self._digest(os.path.join(".ai", "work", "T1", "evidence.md"))
        # Commit unrelated code *and* change the F-01 pivotal anchor's file after
        # the audit, so HEAD moves past the recorded observed_commit.
        self.commit_code("src/app.py", "def main():\n    return 43\n")
        self.commit_code("src/other.py", "def other():\n    return 0\n")

        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        # Evidence identity (path + digest) is retained; the binding is not
        # discarded merely because HEAD moved.
        self.assertIn("evidence.md", result.stdout)
        self.assertIn(digest, result.stdout)
        # Explicit relevance-assessment notice naming the changed anchor.
        self.assertIn("relevance assessment", result.stdout)
        self.assertIn("src/app.py", result.stdout)
        self.assertIn("F-01", result.stdout)
        # No automatic claim that the anchor still holds.
        self.assertNotIn("anchor is still valid", result.stdout)

    # -- continuation blockers: unresolved escalation (resume's own path) -----

    def test_unresolved_escalation_is_a_continuation_blocker(self):
        """A well-formed escalation blocks continuation via `_continuation_blockers`.

        It is not malformed State and `validate` emits no ERROR for it, so the
        exit-1 comes from resume's own blocker path (not a validate Finding).
        """
        self.seed_v2("requirement")
        proc = self.cli("escalate", "T1", "--scope", "machine",
                        "--reason", "needs a senior design call")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

        # Well-formed: validate itself neither errors nor names the blocker.
        valid = self.cli("validate", "T1")
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
        self.assertNotIn("unresolved escalation", valid.stdout)

        before = self.capture_files()
        before_mtimes = self._mtimes()
        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Ticket", result.stdout)  # the brief is still printed
        self.assertIn("unresolved escalation", result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        # Still read-only.
        self.assertEqual(self.capture_files(), before)
        self.assertEqual(self._mtimes(), before_mtimes)

    # -- late-phase bootstrap recovery names its senior resolver -------------

    def test_late_bootstrap_resume_names_senior_resolver(self):
        """A late-phase v2 start is an unresolved bootstrap recovery brief.

        `start --phase implementation` enters `recovery.kind: bootstrap` with
        the workflow-bootstrap senior route; resume prints the brief with the
        unresolved-escalation blocker, names the resolver, and stays strictly
        read-only (HARDEN-003 Task 2).
        """
        proc = self.cli("start", "T2", "--phase", "implementation")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        t2_state = os.path.join(self.root, ".ai", "work", "T2", "state.yaml")
        with open(t2_state, "rb") as fh:
            persisted = fh.read()

        result = self.cli("resume", "T2")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Ticket", result.stdout)  # the brief is still printed
        self.assertIn("workflow-bootstrap", result.stdout)
        self.assertIn("unresolved escalation", result.stdout)
        self.assertNotIn("Traceback", result.stderr)
        # Still read-only.
        with open(t2_state, "rb") as fh:
            self.assertEqual(fh.read(), persisted)

    # -- stale audit binding (validate surfaces it, resume reports it) -------

    def test_stale_audit_binding_is_surfaced(self):
        """Changing the Evidence after set-gate is a stale-binding ERROR."""
        self._seed_audit()  # evidence + audit + a bound `sufficient` gate
        evidence = os.path.join(self.root, ".ai", "work", "T1", "evidence.md")
        with open(evidence, "a", encoding="utf-8", newline="") as fh:
            fh.write("\n<!-- drift after the gate was recorded -->\n")

        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Checks", result.stdout)
        self.assertIn("ERROR", result.stdout)
        self.assertIn("stale", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    # -- review freshness covers both verdicts (HARDEN-001) ------------------

    def test_resume_reports_changed_failed_review(self):
        """A changed failed Review blocks continuation like a stale pass.

        `changes_requested` is a recorded binding too: editing `review.md`
        after the verdict must surface for the receiving agent (exit 1), not
        only a stale `pass`.
        """
        self._seed_failed_review()
        with open(os.path.join(self.work, "review.md"), "a",
                  encoding="utf-8", newline="") as fh:
            fh.write("\n<!-- edited after verdict -->\n")

        result = self.cli("resume", "T1")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("Review artifact changed", result.stdout)
        self.assertNotIn("Traceback", result.stderr)

    # -- flagged drift reaches the receiving session (HARDEN-010 Task 2) -----

    def test_flagged_binding_is_stale(self):
        """A hidden edit or deletion still blocks the receiving session.

        The `resume` read path runs the same shared assessment as `set-review`,
        so an `assume-unchanged` or `skip-worktree` hint must not let a stale
        pass look current to the agent that picks the Ticket up. One bound Review
        is seeded and each subcase restores only the mutated path, keeping the
        binding the probe measures against.
        """
        rel = "src/feature.py"
        self._seed_review()
        for flag in ("assume-unchanged", "skip-worktree", "both"):
            for kind in ("edit", "delete"):
                with self.subTest(flag=flag, kind=kind):
                    if kind == "edit":
                        self._flagged_edit(flag, rel)
                    else:
                        self._flagged_delete(flag, rel)
                    self._assert_flagged_resume_blocker(rel, "pass")
                    self._clear_flag(rel, flag)
                    self._restore_code(rel)

    def test_flagged_binding_keeps_failed_review_identity(self):
        """A recorded `changes_requested` stays stale, never a fresh pass.

        The other verdict binds too, and the receiver must see the hidden change
        as a blocker while the State still records `changes_requested`.
        """
        rel = "src/feature.py"
        self._seed_failed_review()
        for flag in ("assume-unchanged", "skip-worktree", "both"):
            with self.subTest(flag=flag):
                self._flagged_edit(flag, rel)
                self._assert_flagged_resume_blocker(rel, "changes_requested")
                self._clear_flag(rel, flag)
                self._restore_code(rel)


if __name__ == "__main__":
    unittest.main()