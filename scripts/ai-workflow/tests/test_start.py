"""Tests for `ai-workflow start` scaffolding (spec §9, TICKET-008)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import start  # noqa: E402
import state  # noqa: E402
import validate  # noqa: E402


class StartTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _state(self, ticket="T1"):
        return state.load_file(
            os.path.join(self.root, ".ai", "work", ticket, "state.yaml"))

    def test_start_scaffolds_state_and_artifacts(self):
        created = start.start(self.root, "T1", title="New ticket")
        self.assertTrue(created)

        work = os.path.join(self.root, ".ai", "work", "T1")
        for name in ("state.yaml", "evidence.md", "handoff.md", "progress.md"):
            self.assertTrue(os.path.exists(os.path.join(work, name)), name)
        # decision.md is senior-only; evidence-audit.md comes when audited.
        self.assertFalse(os.path.exists(os.path.join(work, "decision.md")))
        self.assertFalse(os.path.exists(os.path.join(work, "evidence-audit.md")))

        data = self._state()
        self.assertEqual(data["ticket"], {"id": "T1", "title": "New ticket"})
        self.assertEqual(data["phase"], "requirement")
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["workflow_version"], 1)
        # Greenfield: no migration blocks (those are adoption-only).
        self.assertNotIn("migration", data)
        self.assertNotIn("adoption_checkpoint", data)

    def test_start_phase_option(self):
        start.start(self.root, "T1", phase="implementation")
        data = self._state()
        self.assertEqual(data["phase"], "implementation")
        self.assertIn("implementation", data["next_action"]["action"])

    def test_start_ignores_illegal_phase(self):
        start.start(self.root, "T1", phase="bogus")
        self.assertEqual(self._state()["phase"], "requirement")

    def test_start_writes_source_artifacts(self):
        start.start(self.root, "T1",
                    spec_path="docs/spec.md",
                    ticket_path=".scratch/feature/01.md",
                    plan_path="docs/plan.md")
        data = self._state()
        self.assertEqual(data["source_artifacts"]["spec"]["path"], "docs/spec.md")
        self.assertEqual(data["source_artifacts"]["ticket"]["path"],
                         ".scratch/feature/01.md")
        self.assertEqual(data["source_artifacts"]["plan"]["path"], "docs/plan.md")

    def test_start_idempotent(self):
        start.start(self.root, "T1", title="first")
        self.assertEqual(start.start(self.root, "T1", title="second"), [])
        data = self._state()
        self.assertEqual(data["ticket"]["title"], "first")  # untouched

    def test_started_state_validates_clean_at_requirement(self):
        start.start(self.root, "T1")
        findings = validate.validate_repo(self.root)
        errors = [f.message for f in findings if f.severity == "ERROR"]
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
