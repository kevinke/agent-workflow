"""Frozen PAIR-01 behavior acceptance; run against the disposable target."""

from pathlib import Path
import tempfile
import unittest

from config import Config


class ConfigBehaviorTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "settings.conf"
        self.path.write_text("# settings\n\nmode=initial\nkeep=original\n", encoding="utf-8")

    def test_reads_initial(self):
        """Ignoring blank/comment lines must not discard configuration values."""
        config = Config(str(self.path))
        self.assertEqual(config.get("mode"), "initial")
        self.assertEqual(config.get("keep"), "original")

    def test_cached_until_reload(self):
        """Reading disk on every get would expose an unrequested update."""
        config = Config(str(self.path))
        self.path.write_text("mode=configured\nkeep=updated\n", encoding="utf-8")
        self.assertEqual(config.get("mode"), "initial")
        self.assertEqual(config.get("keep"), "original")
        config.reload()
        self.assertEqual(config.get("mode"), "configured")
        self.assertEqual(config.get("keep"), "updated")

    def test_reload_valid(self):
        """Reload must replace values for this instance without updating another."""
        config = Config(str(self.path))
        other = Config(str(self.path))
        self.path.write_text("mode=configured\nkeep=updated\n", encoding="utf-8")
        self.assertIsNone(config.reload())
        self.assertEqual(config.get("mode"), "configured")
        self.assertEqual(config.get("keep"), "updated")
        self.assertEqual(other.get("mode"), "initial")
        self.assertEqual(other.get("keep"), "original")

    def test_bad_reload_preserves_previous(self):
        """Partial parsing must not change any value after malformed input."""
        config = Config(str(self.path))
        self.path.write_text("mode=configured\nkeep=updated\n", encoding="utf-8")
        config.reload()
        self.path.write_text("mode=corrupted\nnot a key/value\nkeep=corrupted\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            config.reload()
        self.assertEqual(config.get("mode"), "configured")
        self.assertEqual(config.get("keep"), "updated")

    def test_instances_isolated(self):
        """A cache shared by file path would overwrite an existing instance."""
        first = Config(str(self.path))
        self.path.write_text("mode=second\nkeep=second\n", encoding="utf-8")
        second = Config(str(self.path))
        self.assertEqual(first.get("mode"), "initial")
        self.assertEqual(first.get("keep"), "original")
        self.assertEqual(second.get("mode"), "second")
        self.assertEqual(second.get("keep"), "second")


if __name__ == "__main__":
    unittest.main()
