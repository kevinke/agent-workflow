"""Tests for `ai-workflow adopt` scaffolding (spec §10, TICKET-006)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import adopt  # noqa: E402
import state  # noqa: E402
import validate  # noqa: E402


class AdoptTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_adoption_scaffolds_state_and_artifacts(self):
        created = adopt.adopt(self.root, "T1", title="Legacy ticket")
        self.assertTrue(created)

        report = os.path.join(self.root, ".ai", adopt.MIGRATION_REPORT_NAME)
        self.assertTrue(os.path.exists(report))

        work = os.path.join(self.root, ".ai", "work", "T1")
        self.assertTrue(os.path.exists(os.path.join(work, "state.yaml")))
        self.assertTrue(os.path.exists(os.path.join(work, "evidence.md")))
        self.assertTrue(os.path.exists(os.path.join(work, "handoff.md")))
        self.assertTrue(os.path.exists(os.path.join(work, "progress.md")))
        # decision.md is reconstructed by a senior, never fake-started here.
        self.assertFalse(os.path.exists(os.path.join(work, "decision.md")))

        data = state.load_file(os.path.join(work, "state.yaml"))
        self.assertTrue(data["migration"]["adopted_existing_repo"])
        self.assertEqual(data["phase"], "requirement")
        self.assertFalse(data["adoption_checkpoint"]["continuation_safe"])
        self.assertEqual(data["next_action"]["role"], "workflow-bootstrap")
        for p in data["historical_phases"].values():
            self.assertEqual(p["status"], "not_performed")

    def test_adopt_phase_option(self):
        adopt.adopt(self.root, "T1", phase="implementation")
        data = state.load_file(os.path.join(self.root, ".ai", "work", "T1", "state.yaml"))
        self.assertEqual(data["phase"], "implementation")
        self.assertEqual(data["migration"]["adopted_at_phase"], "implementation")

    def test_adopt_ignores_illegal_phase(self):
        adopt.adopt(self.root, "T1", phase="bogus")
        data = state.load_file(os.path.join(self.root, ".ai", "work", "T1", "state.yaml"))
        self.assertEqual(data["phase"], "requirement")

    def test_adopt_idempotent(self):
        adopt.adopt(self.root, "T1")
        created = adopt.adopt(self.root, "T1")
        self.assertEqual(created, [])

    def test_adopted_state_validates_clean_at_requirement(self):
        adopt.adopt(self.root, "T1")
        findings = validate.validate_repo(self.root)
        errors = [f.message for f in findings if f.severity == "ERROR"]
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
