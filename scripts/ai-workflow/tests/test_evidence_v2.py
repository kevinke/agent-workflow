"""Tests for v2 audit binding and stale-gate rejection (SCOUT-002 Task 2).

Drives the real CLI against the V2CLITestCase fixture: a recorded gate binds the
verdict to the SHA-256 of the audited Evidence and its Audit artifact, so a
changed report or audit makes the gate stale and blocks decisionward advances.
Malformed arguments stay usage errors (exit 2), protocol rejections exit 1, and
every rejected mutation leaves the raw State bytes untouched.
"""

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import contracts  # noqa: E402
import workflow_v2  # noqa: E402
from v2_support import V2CLITestCase  # noqa: E402


class EvidenceV2Test(V2CLITestCase):
    # -- binding and staleness --------------------------------------------------

    def test_changed_report_blocks_decision_without_state_write(self):
        self.seed_v2("evidence_audit")
        self.write_evidence()
        self.write_audit()
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "sufficient",
                                  "--round", "1").returncode, 0)
        before = self.state_bytes()
        path = Path(self.root) / ".ai/work/T1/evidence.md"
        path.write_text(path.read_text() + "\nAdditional observation.\n")
        self.assertEqual(self.cli("advance", "T1", "--to",
                                  "technical_decision").returncode, 1)
        self.assertEqual(self.state_bytes(), before)

    def test_changed_audit_blocks_decision_without_state_write(self):
        self.seed_v2("evidence_audit")
        self.write_evidence()
        self.write_audit()
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "sufficient",
                                  "--round", "1").returncode, 0)
        before = self.state_bytes()
        path = Path(self.root) / ".ai/work/T1/evidence-audit.md"
        path.write_text(path.read_text() + "\nAdditional audit note.\n")
        self.assertEqual(self.cli("advance", "T1", "--to",
                                  "technical_decision").returncode, 1)
        self.assertEqual(self.state_bytes(), before)

    def test_validate_flags_stale_binding_after_evidence_change(self):
        self.seed_v2("evidence_audit")
        self.write_evidence()
        self.write_audit()
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "sufficient",
                                  "--round", "1").returncode, 0)
        path = Path(self.root) / ".ai/work/T1/evidence.md"
        path.write_text(path.read_text() + "\nAdditional observation.\n")
        proc = self.cli("validate", "T1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn(
            "evidence.md changed since the evidence gate was recorded "
            "(stale binding: re-audit and set-gate again)", proc.stdout)

    def test_unchanged_rerun_keeps_gate_fresh(self):
        self.seed_v2("evidence_audit")
        self.write_evidence()
        self.write_audit()
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "sufficient",
                                  "--round", "1").returncode, 0)
        # Re-recording the same verdict over unchanged artifacts is idempotent.
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "sufficient",
                                  "--round", "1").returncode, 0)
        self.assertEqual(self.cli("advance", "T1", "--to",
                                  "technical_decision").returncode, 0)

    def test_insufficient_followup_then_reaudit_opens_gate(self):
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        self.write_audit(gate="insufficient", round_no=1)
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "insufficient",
                                  "--round", "1").returncode, 0)
        self.assertEqual(self.cli("advance", "T1", "--to",
                                  "followup_evidence").returncode, 0)
        self.assertEqual(self.cli("advance", "T1", "--to",
                                  "evidence_audit").returncode, 0)
        self.write_evidence(round_no=2)
        self.write_audit(gate="sufficient", round_no=2)
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "sufficient",
                                  "--round", "2").returncode, 0)
        self.assertEqual(self.cli("advance", "T1", "--to",
                                  "technical_decision").returncode, 0)
        evidence = self.read_state()["evidence"]
        self.assertEqual(evidence["gate"], "sufficient")
        self.assertEqual(evidence["round"], 2)

    # -- rejected recordings -----------------------------------------------------

    def test_scaffold_cannot_set_gate_without_state_write(self):
        self.seed_v2("evidence_audit")
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_invalid_report_cannot_bind_gate(self):
        self.seed_v2("evidence_audit")
        path = self.write_evidence()
        self.write_audit()
        with open(path, "a", encoding="utf-8", newline="") as fh:
            fh.write("\n### DQ-01\n\n**Question:** duplicate id\n")
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_gate_metadata_mismatch_rejected(self):
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "insufficient", "--round", "1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_round_metadata_mismatch_rejected(self):
        self.seed_v2("evidence_audit")
        self.write_evidence(round_no=1)
        self.write_audit(gate="sufficient", round_no=1)
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "2")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_set_gate_wrong_phase_rejected(self):
        self.seed_v2("requirement")
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    # -- usage errors and version guards ----------------------------------------

    def test_non_integer_round_is_usage_error(self):
        self.seed_v2("evidence_audit")
        self.write_evidence()
        self.write_audit()
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "abc")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_negative_round_is_usage_error(self):
        self.seed_v2("evidence_audit")
        self.write_evidence()
        self.write_audit()
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "-1")
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_future_version_set_gate_rejected_without_state_write(self):
        self.seed_v2("evidence_audit")
        self.write_evidence()
        self.write_audit()
        data = self.read_state()
        data["workflow_version"] = 3
        self.write_state(data)
        before = self.state_bytes()
        proc = self.cli("set-gate", "T1", "--gate", "sufficient", "--round", "1")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertEqual(self.state_bytes(), before)

    def test_v1_fixture_semantics_unchanged(self):
        # An explicit v1 ticket: loose evidence and an unbound gate remain
        # valid, with no byte-identity binding. (Task 2 flips the default to v2,
        # so v1 is seeded explicitly rather than assumed.)
        self.seed_v1("evidence_audit")
        path = os.path.join(self.work, "evidence.md")
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write("## Facts\n- FACT source artifact spec section\n")
        self.assertEqual(self.cli("set-gate", "T1", "--gate", "sufficient",
                                  "--round", "2").returncode, 0)
        state = self.read_state()
        self.assertEqual(state.get("workflow_version", 1), 1)
        self.assertEqual(state["evidence"]["gate"], "sufficient")
        self.assertNotIn("report_sha256", state["evidence"])


class TransitionTest(unittest.TestCase):
    """The shared v2 transition/route helpers exposed in workflow_v2."""

    def test_next_action_known_phase(self):
        route = workflow_v2.next_action({}, "evidence_collection")
        self.assertEqual(set(route), {"role", "action", "task"})
        self.assertEqual(route["role"], "scout")
        self.assertIsNone(route["task"])

    def test_next_action_done_is_cleared(self):
        self.assertEqual(workflow_v2.next_action({}, "done"),
                         {"role": None, "action": None, "task": None})

    def test_check_transition_accepts_v1_edge(self):
        workflow_v2.check_transition(".", {"phase": "requirement"},
                                     "evidence_collection")

    def test_check_transition_rejects_illegal_target(self):
        with self.assertRaises(contracts.ContractError):
            workflow_v2.check_transition(".", {"phase": "requirement"},
                                         "technical_decision")

    def test_check_transition_rejects_unknown_phase(self):
        with self.assertRaises(contracts.ContractError):
            workflow_v2.check_transition(".", {"phase": "bogus"},
                                         "requirement")


if __name__ == "__main__":
    unittest.main()
