"""Tests for `ai-workflow upgrade` (spec §9, TICKET-008)."""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import start  # noqa: E402
import state  # noqa: E402
import upgrade  # noqa: E402


def _kit_workflow_dir():
    # this file: scripts/ai-workflow/tests/test_upgrade.py -> 4 levels up.
    kit = os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(kit, ".ai", "workflow")


class UpgradeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _install_kit(self, version):
        """Install the bundled protocol into self.root at the given version."""
        shutil.copytree(_kit_workflow_dir(),
                        os.path.join(self.root, ".ai", "workflow"))
        if version is not None:
            tmpl = os.path.join(self.root, ".ai", "workflow",
                                "templates", "state.yaml")
            data = state.load_file(tmpl)
            data["workflow_version"] = version
            state.save_file(tmpl, data)

    def _installed_template_version(self):
        tmpl = os.path.join(self.root, ".ai", "workflow", "templates", "state.yaml")
        return state.load_file(tmpl)["workflow_version"]

    def test_noop_when_already_current(self):
        self._install_kit(upgrade.kit_workflow_version())
        updated, bumped = upgrade.upgrade(self.root)
        self.assertEqual((updated, bumped), ([], []))

    def test_upgrade_overwrites_older_protocol(self):
        self._install_kit(0)
        self.assertEqual(self._installed_template_version(), 0)

        updated, bumped = upgrade.upgrade(self.root)
        self.assertTrue(updated)
        self.assertEqual(bumped, [])
        self.assertEqual(self._installed_template_version(),
                         upgrade.kit_workflow_version())
        # Installed protocol docs are overwritten with the bundled ones.
        proto = os.path.join(self.root, ".ai", "workflow", "PROTOCOL.md")
        self.assertTrue(os.path.exists(proto))

    def test_upgrade_bumps_older_tickets(self):
        self._install_kit(0)
        start.start(self.root, "T1", title="old ticket")
        state_path = os.path.join(self.root, ".ai", "work", "T1", "state.yaml")
        data = state.load_file(state_path)
        data["workflow_version"] = 0  # started under an older protocol
        state.save_file(state_path, data)

        updated, bumped = upgrade.upgrade(self.root)
        self.assertTrue(updated)
        self.assertEqual(bumped, ["T1"])

        data = state.load_file(state_path)
        self.assertEqual(data["workflow_version"], upgrade.kit_workflow_version())
        # Bumping preserves every other field.
        self.assertEqual(data["ticket"]["title"], "old ticket")
        self.assertEqual(data["phase"], "requirement")

    def test_upgrade_leaves_current_tickets_alone(self):
        self._install_kit(0)
        start.start(self.root, "T1")  # starts at the kit's current version
        updated, bumped = upgrade.upgrade(self.root)
        self.assertEqual(bumped, [])
        data = state.load_file(
            os.path.join(self.root, ".ai", "work", "T1", "state.yaml"))
        self.assertEqual(data["workflow_version"], 1)

    def test_upgrade_is_idempotent(self):
        self._install_kit(0)
        upgrade.upgrade(self.root)
        updated, bumped = upgrade.upgrade(self.root)
        self.assertEqual((updated, bumped), ([], []))

    def test_upgrade_raises_when_not_installed(self):
        with self.assertRaises(upgrade.UpgradeError):
            upgrade.upgrade(self.root)


if __name__ == "__main__":
    unittest.main()
