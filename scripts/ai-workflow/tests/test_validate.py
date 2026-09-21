"""Tests for `ai-workflow validate` ERROR/WARN rules (TICKET-006)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import state  # noqa: E402
import validate  # noqa: E402

HANDOFF_SECTIONS = [
    "What was done", "What remains", "Important discoveries",
    "Current failure", "Do not repeat", "Next recommended action",
    "Repository State",
]


def _valid_state():
    return {
        "schema_version": 1,
        "ticket": {"id": "T1", "title": "t"},
        "phase": "requirement",
        "status": "active",
        "artifacts": {
            "evidence": "evidence.md",
            "evidence_audit": "evidence-audit.md",
            "decision": "decision.md",
            "handoff": "handoff.md",
        },
        "evidence": {"round": 0, "gate": "insufficient"},
        "implementation": {"current_task": 0, "total_tasks": 0, "completed_tasks": []},
        "escalation": {"required": False, "scope": "machine", "reason": None},
        "claim": {"harness": None, "model": None, "claimed_at": None},
        "next_action": {"role": "checkpoint-handoff", "action": "advance", "task": None},
        "provenance": {"last_harness": None, "last_model": None},
    }


class ValidateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.ticket = "T1"
        self.work = os.path.join(self.root, ".ai", "work", self.ticket)
        os.makedirs(self.work)

    def tearDown(self):
        self._tmp.cleanup()

    def _write_state(self, data):
        state.save_file(os.path.join(self.work, "state.yaml"), data)

    def _write_handoff(self):
        with open(os.path.join(self.work, "handoff.md"), "w", encoding="utf-8") as fh:
            fh.write("\n\n".join("## %s" % s for s in HANDOFF_SECTIONS) + "\n")

    def _findings(self):
        out = []
        validate.validate_ticket(self.root, self.ticket, out)
        return out

    def _errors(self, findings=None):
        findings = findings if findings is not None else self._findings()
        return [f.message for f in findings if f.severity == "ERROR"]

    def test_clean_state_no_errors(self):
        self._write_state(_valid_state())
        self._write_handoff()
        self.assertEqual(self._errors(), [])

    def test_gate_violating_transition(self):
        data = _valid_state()
        data["phase"] = "technical_decision"
        data["evidence"]["gate"] = "insufficient"
        self._write_state(data)
        self._write_handoff()
        self.assertTrue(any("gate-violating" in m for m in self._errors()))

    def test_current_task_over_total(self):
        data = _valid_state()
        data["implementation"]["current_task"] = 5
        data["implementation"]["total_tasks"] = 3
        self._write_state(data)
        self._write_handoff()
        self.assertTrue(any("current_task" in m for m in self._errors()))

    def test_done_with_next_action(self):
        data = _valid_state()
        data["phase"] = "done"
        data["evidence"]["gate"] = "sufficient"
        data["next_action"] = {"role": "checkpoint-handoff", "action": "x", "task": None}
        self._write_state(data)
        self._write_handoff()
        self.assertTrue(any("phase=done" in m for m in self._errors()))

    def test_done_with_cleared_next_action_passes(self):
        data = _valid_state()
        data["phase"] = "done"
        data["evidence"]["gate"] = "sufficient"
        data["next_action"] = {"role": None, "action": None, "task": None}
        self._write_state(data)
        self._write_handoff()
        for name in ("evidence.md", "evidence-audit.md", "decision.md"):
            with open(os.path.join(self.work, name), "w", encoding="utf-8") as fh:
                fh.write("x\n")
        self.assertEqual(self._errors(), [])

    def test_illegal_enums(self):
        for field, bad, marker in (
            ("phase", "bogus", "illegal phase"),
            ("status", "bogus", "illegal status"),
        ):
            with self.subTest(field=field):
                data = _valid_state()
                data[field] = bad
                self._write_state(data)
                self._write_handoff()
                self.assertTrue(any(marker in m for m in self._errors()), field)

    def test_illegal_gate(self):
        data = _valid_state()
        data["evidence"]["gate"] = "bogus"
        self._write_state(data)
        self._write_handoff()
        self.assertTrue(any("evidence.gate" in m for m in self._errors()))

    def test_illegal_role(self):
        data = _valid_state()
        data["next_action"]["role"] = "bogus"
        self._write_state(data)
        self._write_handoff()
        self.assertTrue(any("next_action.role" in m for m in self._errors()))

    def test_illegal_escalation_scope(self):
        data = _valid_state()
        data["escalation"] = {"required": True, "scope": "bogus", "reason": "x"}
        self._write_state(data)
        self._write_handoff()
        self.assertTrue(any("escalation.scope" in m for m in self._errors()))

    def test_missing_state_yaml(self):
        self._write_handoff()
        self.assertTrue(any("missing state.yaml" in m for m in self._errors()))

    def test_unparseable_state_yaml(self):
        with open(os.path.join(self.work, "state.yaml"), "w", encoding="utf-8") as fh:
            fh.write("a: {b: 1}\n")
        self.assertTrue(any("invalid state.yaml" in m for m in self._errors()))

    def test_missing_required_artifacts(self):
        data = _valid_state()
        data["phase"] = "implementation"
        data["evidence"]["gate"] = "sufficient"
        self._write_state(data)
        # handoff + evidence present, decision + evidence-audit missing
        self._write_handoff()
        with open(os.path.join(self.work, "evidence.md"), "w", encoding="utf-8") as fh:
            fh.write("facts\n")
        errors = self._errors()
        self.assertTrue(any("evidence-audit.md" in m for m in errors))
        self.assertTrue(any("decision.md" in m for m in errors))

    def test_missing_handoff_sections_is_warn_only(self):
        data = _valid_state()
        self._write_state(data)
        with open(os.path.join(self.work, "handoff.md"), "w", encoding="utf-8") as fh:
            fh.write("## What was done\nonly one section\n")
        findings = self._findings()
        self.assertEqual(self._errors(findings), [])
        self.assertTrue(any(f.severity == "WARN" and "handoff.md missing section" in f.message
                            for f in findings))

    def test_validate_repo_empty_repo_warns_no_errors(self):
        findings = validate.validate_repo(self.root)
        self.assertFalse(validate.has_errors(findings))
        self.assertTrue(any("no tickets" in f.message for f in findings))


if __name__ == "__main__":
    unittest.main()
