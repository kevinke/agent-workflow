"""Lint for the kit's role skills: state mutations must go through the CLI.

Since TICKET-010, `ai-workflow advance/set-gate/complete-task/claim/escalate`
are the sanctioned way to mutate workflow state. The role skills must teach
agents to call the CLI, never to hand-edit `state.yaml` state-machine fields
(TICKET-011). This test locks that in.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# this file: scripts/ai-workflow/tests/test_skills.py -> 4 levels up to kit root.
_KIT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SKILLS_DIR = os.path.join(_KIT_ROOT, ".agents", "skills")

# Phrasings that mean "hand-edit the state machine directly" — banned.
BANNED = [
    "Update `state.yaml`",
    "set `evidence.gate`",
    "advance `phase` to",
    "clear `next_action` in state.yaml",
    "increment `evidence.round`",
]


class SkillsLintTest(unittest.TestCase):
    def _skills(self):
        return sorted(os.listdir(SKILLS_DIR))

    def _text(self, skill):
        with open(os.path.join(SKILLS_DIR, skill, "SKILL.md"), encoding="utf-8") as fh:
            return fh.read()

    def test_no_skill_instructs_hand_editing_state(self):
        for skill in self._skills():
            with self.subTest(skill=skill):
                text = self._text(skill)
                for phrase in BANNED:
                    self.assertNotIn(
                        phrase, text,
                        "%s still instructs %r (use the ai-workflow CLI instead)" % (skill, phrase))

    def test_every_skill_references_the_cli(self):
        for skill in self._skills():
            with self.subTest(skill=skill):
                self.assertIn("ai-workflow", self._text(skill),
                              "%s never references the ai-workflow CLI" % skill)


if __name__ == "__main__":
    unittest.main()
