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

# Instructions that make the *reviewer* write or commit a live record — the exact
# gap HARDEN-011 closes, so they must not survive in the reviewer entry point.
LIVE_WRITE_INSTRUCTIONS = [
    "Commit per",
    "Commits and rollback",
    "git commit",
    "Write `review.md`",
    "Write `handoff.md`",
    "commit live",
]

# Limit statements that HARDEN-011 forbids softening. Compared on normalized
# whitespace because the protocol wraps its prose.
PROTOCOL_LIMITS = [
    "Independent context and a final clean diff alone do not establish isolation.",
    "Copying alone, a prompt-only prohibition or a restriction the unrestricted "
    "verifier can undo is not evidence of enforcement.",
    "Sharing writable Git metadata with the live tree is not an isolated snapshot.",
    "It supplies no technical judgment and performs no source repair or phase "
    "transition during publication.",
    "Review provenance cannot prove acceptance or reconstruct past transient writes.",
    "Historical reviews keep their original binding semantics; do not fabricate "
    "isolation claims for them.",
]

ISOLATION_SECTION = 'Reviewer verification isolation and publication'


def _flat(text):
    return " ".join(text.split())


def _doc(*parts):
    path = os.path.join(_KIT_ROOT, *parts)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


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

    # -- HARDEN-011: every reviewer entry point routes through the boundary ---

    def test_reviewer_entry_points_require_boundary(self):
        """The reviewer role is never told to write or commit a live record.

        Skills stay thin pointers: they name the commands and route to the
        protocol, and the protocol keeps the business rules.
        """
        text = self._text("reviewer")
        for needle in ("prepare-review", "run-review", "--review-context",
                       "--report", "--handoff", ISOLATION_SECTION, "candidate",
                       "no live commit"):
            self.assertIn(needle, text,
                          "the reviewer skill never names %r" % needle)
        for phrase in LIVE_WRITE_INSTRUCTIONS:
            self.assertNotIn(phrase, text,
                             "the reviewer skill still instructs %r" % phrase)
        for line in text.splitlines():
            if "set-review" in line and "--verdict" in line:
                self.assertIn("--review-context", line,
                              "the reviewer skill offers an unguarded set-review: "
                              "%s" % line)
        # Thin pointer: the skill must not restate the protocol's limit rules.
        flat = _flat(text)
        for sentence in PROTOCOL_LIMITS:
            self.assertNotIn(_flat(sentence), flat,
                             "the reviewer skill restates a protocol limit rule: %r"
                             % sentence)

        handoff = self._text("checkpoint-handoff")
        for needle in ("--review-context", ISOLATION_SECTION,
                       "Do not write `review.md`"):
            self.assertIn(needle, handoff,
                          "the checkpoint-handoff skill never names %r" % needle)
        self.assertIn("phase transition during publication", _flat(handoff),
                      "the checkpoint-handoff skill still lets publication "
                      "advance the phase")

        roles = _doc(".ai", "workflow", "ROLES.md")
        reviewer = roles.split("## reviewer")[1].split("## checkpoint-handoff")[0]
        self.assertIn(ISOLATION_SECTION, reviewer)
        self.assertIn("candidate", reviewer)
        self.assertIn("writes no live record", _flat(reviewer),
                      "the reviewer routing entry still makes the reviewer the "
                      "author of a live record")
        for phrase in LIVE_WRITE_INSTRUCTIONS:
            self.assertNotIn(phrase.lower(), reviewer.lower(),
                             "the reviewer routing entry instructs %r" % phrase)

        # The public command surface documents the guarded options it really has.
        for needle in ("prepare-review", "run-review", "--review-context"):
            self.assertIn(needle, main.USAGE,
                          "the CLI usage block never names %r" % needle)
        readme = _doc("README.md")
        for needle in ("prepare-review", "run-review", "--review-context"):
            self.assertIn(needle, readme,
                          "README's command overview never names %r" % needle)

    def test_protocol_and_template_keep_the_limit_statements(self):
        """The protocol documents the real commands and keeps every limit."""
        protocol = _flat(_doc(".ai", "workflow", "PROTOCOL.md"))
        for sentence in PROTOCOL_LIMITS:
            self.assertIn(sentence, protocol,
                          "PROTOCOL.md lost a limit statement: %r" % sentence)
        self.assertNotIn("pending HARDEN-011", protocol,
                         "PROTOCOL.md still calls the mechanism pending")
        for needle in ("prepare-review", "run-review", "--review-context",
                       "linux-bwrap-v1", "blocker"):
            self.assertIn(needle, protocol,
                          "PROTOCOL.md never names %r" % needle)

        artifacts = _flat(_doc(".ai", "workflow", "ARTIFACTS.md"))
        self.assertNotIn("pending HARDEN-011", artifacts,
                         "the provenance contract still calls enforcement pending")
        self.assertIn("--review-context", artifacts)
        self.assertIn("Structural report checks cannot attest that a host denied "
                      "writes", artifacts)

        template = _doc(".ai", "workflow", "templates", "review.md")
        self.assertIn("Isolation provenance", template)
        self.assertIn("draft", template.lower(),
                      "the template provenance is not a marked draft placeholder")

        # The adapter docs say plainly what is not supported.
        windows = _doc("adapters", "codex", "windows.md")
        self.assertIn("CreateProcess", windows,
                      "the observed Windows launch diagnostics were laundered away")
        self.assertIn("unsupported", windows.lower())
        local = _doc("adapters", "local-review.md")
        for needle in ("linux-bwrap-v1", "EROFS", "ENETUNREACH", "unsupported"):
            self.assertIn(needle, local,
                          "the local adapter doc never records %r" % needle)


if __name__ == "__main__":
    unittest.main()
