"""Smoke tests for the `ai-workflow` CLI dispatch (TICKET-006)."""

import contextlib
import io
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

# Superscript two: str.isdigit() is True but int() raises ValueError, so a
# naive `raw.isdigit()` guard followed by int() leaks an uncaught traceback.
UNICODE_DIGIT = "\u00b2"


class MainTest(unittest.TestCase):
    def _run_capturing_stderr(self, argv):
        """Run the CLI, capturing stderr; return (exit_code, stderr_text)."""
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            code = main.main(argv)
        return code, buf.getvalue()

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

    def test_drive_relative_repo_is_rejected_before_chdir(self):
        code, err = self._run_capturing_stderr(["--repo", "C:repo", "status"])
        self.assertEqual(code, 1)
        self.assertIn("startup-environment-unsupported", err)
        self.assertNotIn("Traceback", err)

    def test_repo_option_requires_root_and_command(self):
        for args in (["--repo"], ["--repo", "somewhere"],
                     ["--repo", "--help", "status"]):
            code, err = self._run_capturing_stderr(args)
            self.assertEqual(code, 2, err)

    def test_upgrade_without_installed_protocol_is_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(main.cmd_upgrade(["upgrade"], tmp), 2)

    def test_commands_recognized(self):
        self.assertTrue({"init", "status", "validate", "start", "adopt", "upgrade"}
                        <= main.COMMANDS)

    # -- malformed numeric arguments reject cleanly (usage error, no traceback) --

    def test_malformed_register_plan_total_is_usage_error(self):
        code, err = self._run_capturing_stderr(
            ["register-plan", "T1", "--path", "P", "--total", UNICODE_DIGIT])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)
        self.assertIn("total", err)

    def test_malformed_set_gate_round_is_usage_error(self):
        code, err = self._run_capturing_stderr(
            ["set-gate", "T1", "--gate", "sufficient", "--round", UNICODE_DIGIT])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)
        self.assertIn("round", err)

    def test_malformed_complete_task_total_is_usage_error(self):
        code, err = self._run_capturing_stderr(
            ["complete-task", "T1", "--total", UNICODE_DIGIT])
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)
        self.assertIn("total", err)


if __name__ == "__main__":
    unittest.main()
