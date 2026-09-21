"""Smoke tests for the `ai-workflow` CLI dispatch (TICKET-006)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402


class MainTest(unittest.TestCase):
    def test_help_exits_zero(self):
        self.assertEqual(main.main(["-h"]), 0)
        self.assertEqual(main.main(["help"]), 0)
        self.assertEqual(main.main([]), 0)

    def test_unknown_command_exits_two(self):
        self.assertEqual(main.main(["frobnicate"]), 2)

    def test_start_requires_ticket_id(self):
        # Missing ticket-id is a usage error (no filesystem access needed).
        self.assertEqual(main.main(["start"]), 2)
        self.assertEqual(main.main(["start", "--title", "x"]), 2)

    def test_upgrade_without_installed_protocol_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main.cmd_upgrade(["upgrade"], tmp), 2)

    def test_commands_recognized(self):
        self.assertTrue({"init", "status", "validate", "start", "adopt", "upgrade"}
                        <= main.COMMANDS)


if __name__ == "__main__":
    unittest.main()
