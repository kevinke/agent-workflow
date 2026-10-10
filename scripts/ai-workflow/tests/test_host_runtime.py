"""Platform routing unit tests. WSL discovery/launch seams are simulated here."""
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import contracts
import host_runtime


class HostRuntimeTest(unittest.TestCase):
    def test_unc_names_and_chinese_spaces(self):
        for server in ("wsl$", "wsl.localhost", "WSL.LOCALHOST"):
            self.assertEqual(host_runtime.wsl_unc(
                "\\\\%s\\Ubuntu-24.04\\home\\kevin\\中文 空格" % server),
                ("Ubuntu-24.04", "/home/kevin/中文 空格"))

    def test_local_windows_and_linux_stay_in_process(self):
        self.assertIsNone(host_runtime.handoff_command(
            ["status"], "C:\\kit\\main.py", "D:\\repo", host_os="nt"))
        self.assertIsNone(host_runtime.handoff_command(
            ["status"], "/kit/main.py", "/home/kevin/repo", host_os="posix"))

    def test_unc_handoff_translates_only_host_paths(self):
        root = r"\\wsl$\Ubuntu-24.04\home\kevin\中文 空格"
        context = r"\\wsl.localhost\Ubuntu-24.04\tmp\审查 空格"
        args = ["run-review", "T1", "--review-context", context,
                "--kind", "probe", "--", "python3", "-c",
                "print('中文; $(echo nope)')", r"C:\verifier\opaque"]
        with mock.patch.object(host_runtime, "wsl_distro", return_value="Ubuntu-24.04"):
            command = host_runtime.handoff_command(args, root + r"\main.py", root,
                                                   host_os="nt")
        self.assertEqual(command[:4], ["wsl.exe", "-d", "Ubuntu-24.04", "--exec"])
        self.assertEqual(command[8:10], ["--repo", "/home/kevin/中文 空格"])
        self.assertIn("/tmp/审查 空格", command)
        self.assertEqual(command[-5:], args[-5:])

    def test_mixed_distro_and_generic_unc_refused_before_launch(self):
        for root, script, args in (
            (r"\\server\share\repo", r"C:\kit\main.py", ["status"]),
            (r"\\wsl$\Ubuntu\repo", r"\\wsl$\Debian\main.py", ["status"]),
            (r"\\wsl$\Ubuntu\repo", r"\\wsl$\Ubuntu\main.py",
             ["prepare-review", "T1", "--output", r"\\wsl$\Debian\out"]),
        ):
            with self.subTest(root=root, args=args), \
                    mock.patch.object(host_runtime, "wsl_distro", return_value="Ubuntu"), \
                    self.assertRaises(contracts.ContractError):
                host_runtime.handoff_command(args, script, root, host_os="nt")

    def test_linux_cli_confirms_root_instead_of_wsl_cd_fallback(self):
        root = r"\\wsl$\Ubuntu\tmp\missing repo"
        with mock.patch.object(host_runtime, "wsl_distro", return_value="Ubuntu"):
            command = host_runtime.handoff_command(
                ["init"], root + r"\main.py", root, host_os="nt")
        self.assertNotIn("--cd", command)
        self.assertEqual(command[-3:], ["--repo", "/tmp/missing repo", "init"])

    def test_empty_unc_invocation_keeps_native_help(self):
        root = r"\\wsl$\Ubuntu\repo"
        with mock.patch.object(host_runtime, "wsl_distro", return_value="Ubuntu"):
            command = host_runtime.handoff_command([], root + r"\main.py", root,
                                                   host_os="nt")
        self.assertEqual(command[-3:], ["--repo", "/repo", "help"])

    def test_init_target_translates_after_with_skills_flag(self):
        root = r"\\wsl$\Ubuntu\repo"
        for args in (["init", "--with-skills", r"C:\中文 target"],
                     ["init", r"C:\中文 target", "--with-skills"]):
            with self.subTest(args=args), \
                    mock.patch.object(host_runtime, "wsl_distro", return_value="Ubuntu"), \
                    mock.patch.object(host_runtime, "_drive_path", return_value="/mnt/c/中文 target"):
                command = host_runtime.handoff_command(args, root + r"\main.py", root,
                                                       host_os="nt")
                self.assertIn("/mnt/c/中文 target", command)
                self.assertNotIn(r"C:\中文 target", command)

    def test_distro_override_conflict_refused(self):
        with mock.patch.dict(os.environ, {"AI_WORKFLOW_BWRAP_DISTRO": "Debian"}), \
                self.assertRaisesRegex(contracts.ContractError, "distro"):
            host_runtime.wsl_distro("Ubuntu")

    def test_wsl1_or_failed_discovery_refused(self):
        for proc in (
            mock.Mock(returncode=1, stdout=b"", stderr=b"unavailable"),
            mock.Mock(returncode=0, stdout=json.dumps({"distro": "Ubuntu",
                "platform": "linux", "release": "4.4.0-Microsoft"}).encode(), stderr=b""),
        ):
            host_runtime._discover_wsl.cache_clear()
            with mock.patch.object(host_runtime.subprocess, "run", return_value=proc), \
                    self.assertRaises(contracts.ContractError):
                host_runtime._discover_wsl("Ubuntu")
        host_runtime._discover_wsl.cache_clear()

    def test_encoding_does_not_change_raw_bytes(self):
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="cp1252", newline="")
        with mock.patch.object(sys, "stdout", stream):
            host_runtime.configure_stdio()
            print("中文输出")
            stream.flush()
        self.assertEqual(raw.getvalue(), "中文输出\n".encode())

    def test_linux_preparation_rejects_windows_path_spelling(self):
        for output in (r"C:\contexts\审查", r"\\wsl$\Ubuntu\tmp\context"):
            with self.subTest(output=output), \
                    mock.patch.object(host_runtime.os, "name", "posix"), \
                    mock.patch.object(host_runtime, "review_runtime", return_value={
                        "platform": "linux", "distro": "Ubuntu"}), \
                    self.assertRaisesRegex(contracts.ContractError, "POSIX"):
                host_runtime.prepare_paths("/home/kevin/repo", output)

    def test_windows_drive_relative_output_rejected_before_normalizing(self):
        with mock.patch.object(host_runtime.os, "name", "nt"), \
                mock.patch.object(host_runtime, "review_runtime", return_value={
                    "platform": "win32", "distro": "Ubuntu"}), \
                mock.patch.object(host_runtime, "_drive_path", return_value="/mnt/c/out"), \
                self.assertRaisesRegex(contracts.ContractError, "absolute drive path"):
            host_runtime.prepare_paths(r"C:\repo", "C:contexts")

    def test_linux_override_matches_distro_case_insensitively(self):
        with mock.patch.object(host_runtime.os, "name", "posix"), \
                mock.patch.object(host_runtime.sys, "platform", "linux"), \
                mock.patch.object(host_runtime.platform, "release", return_value="microsoft-standard-WSL2"), \
                mock.patch.dict(os.environ, {"WSL_DISTRO_NAME": "Ubuntu", "AI_WORKFLOW_BWRAP_DISTRO": "ubuntu"}):
            self.assertEqual(host_runtime.review_runtime(), {"platform": "linux", "distro": "Ubuntu"})


if __name__ == "__main__":
    unittest.main()
