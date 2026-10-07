"""Lint for the kit's role skills: state mutations must go through the CLI.

Since TICKET-010, `ai-workflow advance/set-gate/complete-task/claim/escalate`
are the sanctioned way to mutate workflow state. The role skills must teach
agents to call the CLI, never to hand-edit `state.yaml` state-machine fields
(TICKET-011). This test locks that in.
"""

import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402
import skills  # noqa: E402

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

    def test_install_skills_copies_bundle_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            written = skills.install_skills(tmp)
            self.assertEqual(len(written), len(skills.KIT_SKILLS))
            for name in skills.KIT_SKILLS:
                self.assertTrue(os.path.exists(
                    os.path.join(tmp, ".agents", "skills", name, "SKILL.md")), name)
            # Second run is a true no-op (nothing rewritten).
            self.assertEqual(skills.install_skills(tmp), [])

    def test_install_skills_updates_changed_skill_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills.install_skills(tmp)
            dst = os.path.join(tmp, ".agents", "skills", "repo-scout", "SKILL.md")
            with open(dst, "w", encoding="utf-8") as fh:
                fh.write("stale copy\n")
            written = skills.install_skills(tmp)
            self.assertIn(dst, written)
            with open(dst, encoding="utf-8") as fh:
                self.assertNotEqual(fh.read(), "stale copy\n")

    # -- the eight-skill bundle includes the Reviewer ------------------------

    def test_kit_ships_eight_skills_including_reviewer(self):
        self.assertEqual(len(skills.KIT_SKILLS), 8)
        self.assertIn("reviewer", skills.KIT_SKILLS)
        for name in skills.KIT_SKILLS:
            self.assertTrue(
                os.path.isfile(os.path.join(SKILLS_DIR, name, "SKILL.md")), name)

    def test_install_skills_installs_reviewer(self):
        with tempfile.TemporaryDirectory() as tmp:
            skills.install_skills(tmp)
            self.assertTrue(os.path.isfile(os.path.join(
                tmp, ".agents", "skills", "reviewer", "SKILL.md")))

    def test_help_and_install_text_report_eight_role_skills(self):
        self.assertIn("eight role skills", main.USAGE)
        self.assertNotIn("seven", main.USAGE)
        with tempfile.TemporaryDirectory() as tmp:
            skills.install_skills(tmp)
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = main.cmd_install_skills(["install-skills", tmp], tmp)
            self.assertEqual(code, 0)
            self.assertIn("eight role skills", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
