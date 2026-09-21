"""Smoke tests for the `ai-workflow` CLI dispatch (TICKET-006)."""

import os
import sys
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

    def test_stub_commands_report_not_implemented(self):
        self.assertEqual(main.main(["start"]), 2)
        self.assertEqual(main.main(["upgrade"]), 2)

    def test_commands_recognized(self):
        self.assertTrue({"init", "status", "validate", "adopt"} <= main.COMMANDS)


if __name__ == "__main__":
    unittest.main()
