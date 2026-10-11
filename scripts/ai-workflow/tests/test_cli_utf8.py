"""CLI pipes are UTF-8 even when the caller supplies a legacy encoding."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CLI = str(Path(__file__).resolve().parents[1] / "main.py")


class CLIUTF8Test(unittest.TestCase):
    def run_cli(self, cwd, *args):
        env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
        return subprocess.run([sys.executable, CLI, *args], cwd=cwd,
                              env=env, capture_output=True)

    def test_stdout_chinese_path_after_install(self):
        with tempfile.TemporaryDirectory(prefix="中文 空格 ") as root:
            proc = self.run_cli(root, "init")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(root, proc.stdout.decode("utf-8"))
            self.assertTrue((Path(root) / ".ai/workflow/PROTOCOL.md").exists())

    def test_stderr_chinese_ticket_keeps_failure_code(self):
        with tempfile.TemporaryDirectory() as root:
            proc = self.run_cli(root, "resume", "中文票据")
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertIn("中文票据", proc.stderr.decode("utf-8"))
            self.assertNotIn(b"Traceback", proc.stderr)

    def test_explicit_repository_root_does_not_use_callers_cwd(self):
        with tempfile.TemporaryDirectory(prefix="中文 空格 ") as root, \
                tempfile.TemporaryDirectory() as caller:
            proc = self.run_cli(caller, "--repo", root, "init")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn(root, proc.stdout.decode("utf-8"))
            self.assertTrue((Path(root) / ".ai/workflow/PROTOCOL.md").exists())
            self.assertFalse((Path(caller) / ".ai").exists())

    def test_missing_repository_is_refused_before_install(self):
        with tempfile.TemporaryDirectory() as caller:
            missing = str(Path(caller) / "不存在 项目")
            proc = self.run_cli(caller, "--repo", missing, "init")
            self.assertEqual(proc.returncode, 1, proc.stderr)
            self.assertIn("cannot open repository", proc.stderr.decode("utf-8"))
            self.assertIn("不存在 项目", proc.stderr.decode("utf-8"))
            self.assertFalse((Path(caller) / ".ai").exists())
            self.assertFalse(Path(missing).exists())


if __name__ == "__main__":
    unittest.main()
