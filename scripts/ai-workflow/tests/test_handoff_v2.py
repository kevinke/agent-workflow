"""Tests for phase-aware Handoff readiness at transfer boundaries (HARDEN-007).

Covers `contracts.validate_handoff` — the syntax-only readiness check over the
ten required H2 sections, the structured Artifact identity / Known relevant
drift bullets and the four Repository State fields — and its phase-aware
consumers: `implementation -> review` entry, `done`, the review/done
continuation (validate and resume through the shared phase checks), and the
implementation recovery clear. An untouched template scaffold is rejected at
every boundary while early drafts stay permitted with WARN notices; explicit
None, justified N/A and code angle-bracket literals are legitimate. Every
rejected mutation asserts the State bytes are unchanged, and every negative
mutation runs on its own valid prerequisite fixture (everything else ready),
so a missing Plan/gate can never masquerade as a Handoff result.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contracts  # noqa: E402
from v2_support import (V2CLITestCase, scaffold_handoff,  # noqa: E402
                        valid_handoff)

RESOLUTION = "resolved per evidence.md and decision.md"

TEMPLATE_EVIDENCE_BULLET = ("- Evidence: <path> sha256 <hash> observed_commit "
                            "<sha> round <n>")


class HandoffReadinessV2Test(V2CLITestCase):
    # -- fixture helpers -----------------------------------------------------

    def _seed_completed_implementation(self, total=1):
        """A ready v2 implementation with every registered task complete.

        This is the valid prerequisite for every transfer boundary: a current
        sufficient gate, a registered `total`-task Plan with every task
        complete, and `decision.md` written and committed. Only the handoff
        varies: it stays whatever the test wrote (the `start` scaffold by
        default), so a boundary rejection here is caused by the handoff alone.
        """
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        proc = self.cli("set-gate", self.TICKET, "--gate", "sufficient",
                        "--round", "1")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        for target in ("technical_decision", "planning"):
            proc = self.cli("advance", self.TICKET, "--to", target)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        rel = self.write_plan(total)
        proc = self.cli("register-plan", self.TICKET, "--path", rel,
                        "--total", str(total))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        proc = self.cli("advance", self.TICKET, "--to", "implementation")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.write_decision()
        self.commit_code("src/feature.py", "def feature():\n    return 1\n")
        for _ in range(total):
            proc = self.cli("complete-task", self.TICKET, "--total", str(total))
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def _write_handoff_text(self, text):
        path = os.path.join(self.work, "handoff.md")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        return path

    def _replace_evidence_bullet(self, text):
        """Swap the concrete Evidence bullet for the template placeholder one."""
        for line in text.splitlines():
            if line.startswith("- Evidence:") and "sha256" in line:
                return text.replace(line, TEMPLATE_EVIDENCE_BULLET, 1)
        self.fail("concrete handoff has no Evidence sha256 bullet")

    # -- 1: the untouched scaffold cannot enter review -----------------------

    def test_scaffold_blocks_review_entry(self):
        scaffold = scaffold_handoff(self.TICKET)
        self.assertTrue(contracts.validate_handoff(scaffold))
        self._seed_completed_implementation()
        self._write_handoff_text(scaffold)

        before_rejected_mutation = self.state_bytes()
        review_entry_proc = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(review_entry_proc.returncode, 1)
        self.assertNotIn("Traceback", review_entry_proc.stderr)
        self.assertIn("transfer boundary", review_entry_proc.stderr)
        self.assertEqual(self.state_bytes(), before_rejected_mutation)

        # Positive control: the same valid fixture passes with a concrete
        # handoff, so the scaffold was the only blocker.
        self.write_handoff()
        entry = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(entry.returncode, 0, entry.stdout + entry.stderr)
        self.assertEqual(self.read_state()["phase"], "review")

    # -- 2: an early draft is a notice, never an error -----------------------

    def test_early_handoff_draft_is_notice_only(self):
        scaffold = scaffold_handoff(self.TICKET)
        self.assertTrue(contracts.validate_handoff(scaffold))

        # Fresh requirement phase: the scaffold draft validates clean (WARN).
        early_validate_proc = self.cli("validate", self.TICKET)
        self.assertEqual(early_validate_proc.returncode, 0)
        self.assertIn("handoff.md", early_validate_proc.stdout)
        resume_proc = self.cli("resume", self.TICKET)
        self.assertEqual(resume_proc.returncode, 0,
                         resume_proc.stdout + resume_proc.stderr)

        # Ordinary implementation drafting stays permitted too.
        self._seed_completed_implementation()
        impl_validate_proc = self.cli("validate", self.TICKET)
        self.assertEqual(impl_validate_proc.returncode, 0,
                         impl_validate_proc.stdout + impl_validate_proc.stderr)
        self.assertIn("handoff.md", impl_validate_proc.stdout)
        impl_resume_proc = self.cli("resume", self.TICKET)
        self.assertEqual(impl_resume_proc.returncode, 0,
                         impl_resume_proc.stdout + impl_resume_proc.stderr)

    # -- 3: placeholder bullets nested in structured sections ----------------

    def test_handoff_nested_placeholders_rejected(self):
        self._seed_completed_implementation()
        nested = self._replace_evidence_bullet(self.write_handoff())
        problems = contracts.validate_handoff(nested)
        self.assertTrue(problems)
        self.assertTrue(any("Evidence" in problem for problem in problems),
                        problems)
        self._write_handoff_text(nested)

        before_rejected_mutation = self.state_bytes()
        review_entry_proc = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(review_entry_proc.returncode, 1,
                         review_entry_proc.stdout + review_entry_proc.stderr)
        self.assertEqual(self.state_bytes(), before_rejected_mutation)

    # -- 4: explicit None, justified N/A and code literals are concrete ------

    def test_handoff_concrete_empty_cases_and_literals(self):
        head = self._git("rev-parse", "HEAD").stdout.strip()
        branch = self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        concrete_none_and_code_literals = valid_handoff(
            self.TICKET, branch, head,
            failure="None",
            changed="N/A — no relevant paths changed since the observed commit",
            next="Pair<T> style literals and comparisons like a < b are "
                 "ordinary text; record the verdict with set-review, then "
                 "advance --to done.")
        self.assertEqual(contracts.validate_handoff(concrete_none_and_code_literals), [])

        # The same text passes the real boundary through the public CLI.
        self._seed_completed_implementation()
        self._write_handoff_text(concrete_none_and_code_literals)
        entry = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(entry.returncode, 0, entry.stdout + entry.stderr)

    # -- 5: clear, review entry, done and resume agree on one malformed handoff

    def test_handoff_boundary_agreement(self):
        scaffold = scaffold_handoff(self.TICKET)

        # Implementation recovery clear: rejected with the untouched scaffold.
        self._seed_completed_implementation()
        self.assertEqual(self.cli("escalate", self.TICKET, "--scope", "machine",
                                  "--reason", "blocked before review")
                         .returncode, 0)
        before_rejected_mutation = self.state_bytes()
        clear_proc = self.cli("escalate", self.TICKET, "--clear",
                              "--resolution", RESOLUTION)
        self.assertEqual(clear_proc.returncode, 1)
        self.assertNotIn("Traceback", clear_proc.stderr)
        self.assertIn("transfer boundary", clear_proc.stderr)
        self.assertEqual(self.state_bytes(), before_rejected_mutation)

        # Positive control, then review entry rejects the scaffold again.
        self.write_handoff()
        cleared = self.cli("escalate", self.TICKET, "--clear",
                           "--resolution", RESOLUTION)
        self.assertEqual(cleared.returncode, 0, cleared.stdout + cleared.stderr)
        self._write_handoff_text(scaffold)
        before_rejected_mutation = self.state_bytes()
        review_entry_proc = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(review_entry_proc.returncode, 1)
        self.assertEqual(self.state_bytes(), before_rejected_mutation)

        # Review continuation: validate AND resume report the same blocker.
        self.write_handoff()
        entered = self.cli("advance", self.TICKET, "--to", "review")
        self.assertEqual(entered.returncode, 0, entered.stdout + entered.stderr)
        self._write_handoff_text(scaffold)
        continuation_snapshot = self.state_bytes()
        validate_proc = self.cli("validate", self.TICKET)
        self.assertEqual(validate_proc.returncode, 1,
                         validate_proc.stdout + validate_proc.stderr)
        resume_proc = self.cli("resume", self.TICKET)
        self.assertEqual(resume_proc.returncode, 1,
                         resume_proc.stdout + resume_proc.stderr)
        self.assertEqual(self.state_bytes(), continuation_snapshot)

        # Done: the same malformed handoff blocks completion, bytes unchanged.
        self.write_handoff()
        self.write_review("pass")
        self.assertEqual(
            self.cli("set-review", self.TICKET, "--verdict", "pass").returncode,
            0)
        self._write_handoff_text(scaffold)
        before_rejected_mutation = self.state_bytes()
        done_proc = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(done_proc.returncode, 1)
        self.assertEqual(self.state_bytes(), before_rejected_mutation)
        self.write_handoff()
        completed = self.cli("advance", self.TICKET, "--to", "done")
        self.assertEqual(completed.returncode, 0,
                         completed.stdout + completed.stderr)

        # Done continuation agrees: the scaffold is an ERROR for the receiver.
        self._write_handoff_text(scaffold)
        done_validate_proc = self.cli("validate", self.TICKET)
        self.assertEqual(done_validate_proc.returncode, 1,
                         done_validate_proc.stdout + done_validate_proc.stderr)
        done_resume_proc = self.cli("resume", self.TICKET)
        self.assertEqual(done_resume_proc.returncode, 1,
                         done_resume_proc.stdout + done_resume_proc.stderr)
        self.write_handoff()
        ok = self.cli("validate", self.TICKET)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)


if __name__ == "__main__":
    unittest.main()
