"""Tests for the restricted YAML subset parser (ADR-0002, TICKET-006).

Run from `scripts/ai-workflow/`:  python -m unittest discover -s tests -v
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import parser  # noqa: E402

KIT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
TEMPLATE_PATH = os.path.join(KIT_ROOT, ".ai", "workflow", "templates", "state.yaml")


class ParseScalarsTest(unittest.TestCase):
    def test_null_forms(self):
        for raw in ("null", "Null", "NULL", "~"):
            self.assertIsNone(parser.parse("k: %s\n" % raw)["k"], raw)
        self.assertIsNone(parser.parse("k:\n")["k"])

    def test_bools(self):
        self.assertTrue(parser.parse("k: true\n")["k"])
        self.assertTrue(parser.parse("k: True\n")["k"])
        self.assertFalse(parser.parse("k: false\n")["k"])
        self.assertFalse(parser.parse("k: FALSE\n")["k"])

    def test_ints(self):
        self.assertEqual(parser.parse("k: 42\n")["k"], 42)
        self.assertEqual(parser.parse("k: -7\n")["k"], -7)
        self.assertEqual(parser.parse("k: 0\n")["k"], 0)

    def test_quoted_scalars(self):
        self.assertEqual(parser.parse('k: "hello"\n')["k"], "hello")
        self.assertEqual(parser.parse("k: 'single'\n")["k"], "single")
        self.assertEqual(parser.parse("k: ''\n")["k"], "")

    def test_plain_scalars(self):
        self.assertEqual(parser.parse("k: plain\n")["k"], "plain")
        # An unquoted comma is a plain-scalar character, not flow syntax.
        self.assertEqual(parser.parse("k: a, b\n")["k"], "a, b")
        # Quoted scalar containing a comma parses and round-trips.
        self.assertEqual(parser.parse('k: "a, b"\n')["k"], "a, b")
        self.assertEqual(parser.dump(parser.parse('k: "a, b"\n')), 'k: "a, b"\n')

    def test_comments(self):
        self.assertEqual(parser.parse("k: value # comment\n")["k"], "value")
        self.assertEqual(parser.parse('k: "a # b"\n')["k"], "a # b")
        self.assertEqual(parser.parse("k: a#b\n")["k"], "a#b")


class RejectionTest(unittest.TestCase):
    def assert_rejected(self, text, label):
        with self.assertRaises(parser.YAMLParseError, msg=label):
            parser.parse(text)

    def test_anchors_aliases_tags(self):
        self.assert_rejected("a: &x 1\n", "anchor")
        self.assert_rejected("a: *x\n", "alias")
        self.assert_rejected("a: !tag val\n", "tag")

    def test_flow_collections(self):
        self.assert_rejected("a: {b: 1}\n", "flow map")
        self.assert_rejected("a: [1, 2]\n", "flow list")

    def test_block_scalars(self):
        self.assert_rejected("a: |\n  x\n", "literal block")
        self.assert_rejected("a: >\n  x\n", "folded block")

    def test_multi_document(self):
        self.assert_rejected("---\na: 1\n", "doc start")
        self.assert_rejected("a: 1\n...\n", "doc end")

    def test_root_indented(self):
        self.assert_rejected(" a: 1\n", "indented root")

    def test_misplaced_structure(self):
        # map entry inside a sequence at the same list indent
        self.assert_rejected("a:\n  - 1\n  b: 2\n", "map in sequence")
        # sequence dash inside a map
        self.assert_rejected("a:\n  b: 1\n  - c\n", "dash in map")


class StructureTest(unittest.TestCase):
    def test_nested_maps(self):
        self.assertEqual(parser.parse("a:\n  b:\n    c: 1\n"), {"a": {"b": {"c": 1}}})

    def test_lists(self):
        self.assertEqual(parser.parse("a:\n  - 1\n  - 2\n"), {"a": [1, 2]})

    def test_inline_map_items(self):
        self.assertEqual(
            parser.parse("a:\n  - x: 1\n  - y: 2\n"),
            {"a": [{"x": 1}, {"y": 2}]},
        )

    def test_nested_list_in_map(self):
        self.assertEqual(
            parser.parse("a:\n  b:\n    - 1\n    - 2\n"),
            {"a": {"b": [1, 2]}},
        )

    def test_empty_list(self):
        self.assertEqual(parser.parse("a: []\n"), {"a": []})

    def test_empty_document(self):
        self.assertEqual(parser.parse(""), {})

    def test_map_with_nested_map_item_in_list(self):
        self.assertEqual(
            parser.parse("a:\n  - \n    x: 1\n  - \n    x: 2\n"),
            {"a": [{"x": 1}, {"x": 2}]},
        )


class RoundTripTest(unittest.TestCase):
    def test_template_roundtrips_exactly(self):
        with open(TEMPLATE_PATH, encoding="utf-8") as fh:
            template = fh.read()
        parsed = parser.parse(template)
        self.assertEqual(parser.dump(parsed), template)

    def test_roundtrip_structures(self):
        structures = [
            {"a": 1, "b": {"c": [1, 2, 3]}, "d": []},
            {"x": None, "y": True, "z": "plain"},
            {"items": [{"k": "v"}, {"k2": None}]},
        ]
        for data in structures:
            self.assertEqual(parser.parse(parser.dump(data)), data)


class OrphanedContentTest(unittest.TestCase):
    """The TICKET-002 silent-drop bug: deeper-indented content after an inline
    `- key: value` (or inline scalar) item, or after a map entry, must raise
    instead of being silently discarded."""

    def test_deeper_after_inline_map_item_raises(self):
        with self.assertRaises(parser.YAMLParseError):
            parser.parse("list:\n  - a: 1\n    b: 2\n")

    def test_deeper_after_inline_scalar_raises(self):
        with self.assertRaises(parser.YAMLParseError):
            parser.parse("list:\n  - one\n    two\n")

    def test_deeper_after_map_entry_raises(self):
        with self.assertRaises(parser.YAMLParseError):
            parser.parse("a:\n  b: 1\n    c: 2\n")

    def test_legit_siblings_still_parse(self):
        # Same-indent siblings and shallower continuation must keep working.
        self.assertEqual(parser.parse("a:\n  - 1\n  - 2\n"), {"a": [1, 2]})
        self.assertEqual(parser.parse("a:\n  b: 1\nc: 2\n"), {"a": {"b": 1}, "c": 2})


if __name__ == "__main__":
    unittest.main()
