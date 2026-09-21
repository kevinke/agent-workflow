"""Tests for state.yaml load/save (TICKET-006)."""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import state  # noqa: E402


class StateTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.path = os.path.join(self.root, "state.yaml")

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_missing_raises(self):
        with self.assertRaises(state.StateError):
            state.load_file(os.path.join(self.root, "nope.yaml"))

    def test_load_invalid_yaml_raises(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("a: {b: 1}\n")  # flow style, outside subset
        with self.assertRaises(state.StateError):
            state.load_file(self.path)

    def test_load_non_map_root_raises(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write("- 1\n- 2\n")
        with self.assertRaises(state.StateError):
            state.load_file(self.path)

    def test_save_stamps_updated_at_and_roundtrips(self):
        state.save_file(self.path, {"phase": "requirement", "ticket": {"id": "T1"}})
        data = state.load_file(self.path)
        self.assertEqual(data["phase"], "requirement")
        self.assertEqual(data["ticket"]["id"], "T1")
        self.assertIn("updated_at", data)
        self.assertEqual(os.listdir(self.root), ["state.yaml"])  # no .tmp left

    def test_unknown_fields_preserved(self):
        state.save_file(self.path, {"known": 1, "mystery": {"anything": "goes"}})
        data = state.load_file(self.path)
        self.assertEqual(data["mystery"], {"anything": "goes"})
        self.assertEqual(data["known"], 1)

    def test_save_requires_map(self):
        with self.assertRaises(state.StateError):
            state.save_file(self.path, [1, 2])


if __name__ == "__main__":
    unittest.main()
