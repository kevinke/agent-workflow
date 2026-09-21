"""Tests for `ai-workflow init` install/idempotency/managed block (TICKET-006)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import init  # noqa: E402


def _count_marker(text, marker):
    return text.count(marker)


class InitTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.target = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _read_agents(self):
        with open(os.path.join(self.target, "AGENTS.md"), encoding="utf-8") as fh:
            return fh.read()

    def test_installs_protocol_and_scaffolds(self):
        created = init.init(self.target)
        self.assertNotEqual(created, [])
        self.assertTrue(os.path.exists(os.path.join(
            self.target, ".ai", "workflow", "STATE_SCHEMA.md")))
        self.assertTrue(os.path.exists(os.path.join(
            self.target, ".ai", "workflow", "PROTOCOL.md")))
        self.assertTrue(os.path.exists(os.path.join(
            self.target, ".ai", "workflow", "templates", "state.yaml")))
        self.assertTrue(os.path.isdir(os.path.join(self.target, ".agents", "skills")))
        agents = self._read_agents()
        self.assertEqual(_count_marker(agents, init.BEGIN_MARKER), 1)
        self.assertEqual(_count_marker(agents, init.END_MARKER), 1)

    def test_second_run_is_noop(self):
        init.init(self.target)
        agents_before = self._read_agents()
        created = init.init(self.target)
        self.assertEqual(created, [])
        self.assertEqual(self._read_agents(), agents_before)
        self.assertEqual(_count_marker(self._read_agents(), init.BEGIN_MARKER), 1)

    def test_user_content_preserved_verbatim(self):
        sentinel = "# My Repo\n\nsome user content\n\n- list item\n"
        with open(os.path.join(self.target, "AGENTS.md"), "w", encoding="utf-8") as fh:
            fh.write(sentinel)
        init.init(self.target)
        self.assertTrue(sentinel in self._read_agents())
        self.assertEqual(_count_marker(self._read_agents(), init.BEGIN_MARKER), 1)

    def test_never_overwrites_existing_protocol_file(self):
        os.makedirs(os.path.join(self.target, ".ai", "workflow"), exist_ok=True)
        proto = os.path.join(self.target, ".ai", "workflow", "PROTOCOL.md")
        with open(proto, "w", encoding="utf-8") as fh:
            fh.write("user-customized protocol\n")
        init.init(self.target)
        with open(proto, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "user-customized protocol\n")

    def test_unbalanced_marker_refuses(self):
        with open(os.path.join(self.target, "AGENTS.md"), "w", encoding="utf-8") as fh:
            fh.write(init.BEGIN_MARKER + "\nonly begin, no end\n")
        with self.assertRaises(init.ManagedBlockError):
            init.init(self.target)
        # File untouched.
        with open(os.path.join(self.target, "AGENTS.md"), encoding="utf-8") as fh:
            self.assertIn("only begin, no end", fh.read())

    def test_updates_block_in_place_when_present(self):
        with open(os.path.join(self.target, "AGENTS.md"), "w", encoding="utf-8") as fh:
            fh.write("# repo\n" + init.BEGIN_MARKER + "\nold block\n" + init.END_MARKER + "\n# tail\n")
        init.init(self.target)
        text = self._read_agents()
        self.assertIn("# repo\n", text)
        self.assertIn("# tail\n", text)
        self.assertNotIn("old block", text)
        self.assertEqual(_count_marker(text, init.BEGIN_MARKER), 1)


if __name__ == "__main__":
    unittest.main()
