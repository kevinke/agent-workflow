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

    def _write_file(self, rel, text):
        full = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)

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
        # setUp leaves a fresh v1 ticket in `requirement`.
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


if __name__ == "__main__":
    unittest.main()