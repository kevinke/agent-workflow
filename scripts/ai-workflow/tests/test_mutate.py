"""Tests for `ai-workflow` semantic state mutations (TICKET-010)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mutate  # noqa: E402
import start  # noqa: E402
import state  # noqa: E402


class MutateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        start.start(self.root, "T1", title="t")

    def tearDown(self):
        self._tmp.cleanup()

    def _state(self):
        return state.load_file(os.path.join(self.root, ".ai", "work", "T1", "state.yaml"))

    def _phase(self):
        return self._state()["phase"]

    def test_advance_full_chain_with_gate_loop(self):
        mutate.advance(self.root, "T1", "evidence_collection")
        self.assertEqual(self._phase(), "evidence_collection")
        self.assertEqual(self._state()["next_action"]["role"], "scout")

        mutate.advance(self.root, "T1", "evidence_audit")
        self.assertEqual(self._phase(), "evidence_audit")

        # gate insufficient -> the loop back to followup_evidence.
        mutate.set_gate(self.root, "T1", "insufficient", round_no=1)
        mutate.advance(self.root, "T1", "followup_evidence")
        self.assertEqual(self._phase(), "followup_evidence")

        mutate.advance(self.root, "T1", "evidence_audit")
        mutate.set_gate(self.root, "T1", "sufficient", round_no=2)
        mutate.advance(self.root, "T1", "technical_decision")
        self.assertEqual(self._phase(), "technical_decision")
        self.assertEqual(self._state()["next_action"]["role"], "technical-decision")

        mutate.advance(self.root, "T1", "planning")
        mutate.advance(self.root, "T1", "implementation")
        self.assertEqual(self._state()["next_action"]["role"], "ticket-executor")
        mutate.advance(self.root, "T1", "review")
        mutate.advance(self.root, "T1", "done")
        self.assertEqual(self._phase(), "done")
        self.assertEqual(self._state()["next_action"],
                         {"role": None, "action": None, "task": None})

    def test_advance_illegal_transition_rejected(self):
        with self.assertRaises(mutate.MutateError):
            mutate.advance(self.root, "T1", "technical_decision")

    def test_advance_same_phase_rejected(self):
        with self.assertRaises(mutate.MutateError):
            mutate.advance(self.root, "T1", "requirement")

    def test_advance_unknown_phase_rejected(self):
        with self.assertRaises(mutate.MutateError):
            mutate.advance(self.root, "T1", "bogus")

    def test_advance_gate_enforcement(self):
        mutate.advance(self.root, "T1", "evidence_collection")
        mutate.advance(self.root, "T1", "evidence_audit")

        # insufficient gate: technical_decision is a gate violation.
        mutate.set_gate(self.root, "T1", "insufficient")
        with self.assertRaises(mutate.MutateError):
            mutate.advance(self.root, "T1", "technical_decision")

        # sufficient gate: followup_evidence is now the illegal branch.
        mutate.set_gate(self.root, "T1", "sufficient")
        with self.assertRaises(mutate.MutateError):
            mutate.advance(self.root, "T1", "followup_evidence")
        mutate.advance(self.root, "T1", "technical_decision")

    def test_advance_missing_ticket(self):
        with self.assertRaises(mutate.MutateError):
            mutate.advance(self.root, "NOPE", "evidence_collection")

    def test_advance_preserves_unknown_fields(self):
        path = os.path.join(self.root, ".ai", "work", "T1", "state.yaml")
        data = state.load_file(path)
        data["mystery"] = {"keep": "me"}
        state.save_file(path, data)
        mutate.advance(self.root, "T1", "evidence_collection")
        self.assertEqual(self._state()["mystery"], {"keep": "me"})

    def test_claim_sets_claim_and_provenance(self):
        mutate.claim(self.root, "T1", harness="trae", model="claude")
        data = self._state()
        self.assertEqual(data["claim"]["harness"], "trae")
        self.assertEqual(data["claim"]["model"], "claude")
        self.assertIn("claimed_at", data["claim"])
        self.assertEqual(data["provenance"], {"last_harness": "trae", "last_model": "claude"})

    def test_complete_task_increments(self):
        mutate.complete_task(self.root, "T1", total=3)
        mutate.complete_task(self.root, "T1")
        mutate.complete_task(self.root, "T1")
        impl = self._state()["implementation"]
        self.assertEqual(impl["current_task"], 3)
        self.assertEqual(impl["total_tasks"], 3)
        self.assertEqual(impl["completed_tasks"], [1, 2, 3])

    def test_complete_task_rejects_when_all_done(self):
        mutate.complete_task(self.root, "T1", total=1)
        with self.assertRaises(mutate.MutateError):
            mutate.complete_task(self.root, "T1")

    def test_complete_task_requires_total(self):
        with self.assertRaises(mutate.MutateError):
            mutate.complete_task(self.root, "T1")

    def test_set_gate(self):
        mutate.set_gate(self.root, "T1", "sufficient", round_no=2)
        evidence = self._state()["evidence"]
        self.assertEqual(evidence["gate"], "sufficient")
        self.assertEqual(evidence["round"], 2)
        with self.assertRaises(mutate.MutateError):
            mutate.set_gate(self.root, "T1", "bogus")

    def test_escalate_and_clear(self):
        mutate.escalate(self.root, "T1", scope="human", reason="blocked on decision")
        esc = self._state()["escalation"]
        self.assertTrue(esc["required"])
        self.assertEqual(esc["scope"], "human")
        self.assertEqual(esc["reason"], "blocked on decision")

        mutate.escalate(self.root, "T1", clear=True)
        esc = self._state()["escalation"]
        self.assertFalse(esc["required"])
        self.assertEqual(esc["scope"], "machine")

        with self.assertRaises(mutate.MutateError):
            mutate.escalate(self.root, "T1", scope="bogus")


if __name__ == "__main__":
    unittest.main()
