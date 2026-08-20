"""Tests for the bundled zero-dependency libraries.

These exist so that CI needs no pip install. If they are wrong, every validator
and every hook is wrong, so they are tested directly rather than only through
their callers.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts", "lib"))
sys.path.insert(0, os.path.join(ROOT, "hooks", "lib"))

from minyaml import parse, MinYamlError  # noqa: E402
from jsonschema_mini import validate, unsupported_keywords  # noqa: E402
from frontmatter import split  # noqa: E402
from hooklib import path_matches  # noqa: E402


class TestMinYaml(unittest.TestCase):
    def test_nested_mappings_and_types(self):
        d = parse("a:\n  b: 1\n  c: true\n  d: 1.5\n  e: null\n  f: 'text'\n")
        self.assertEqual(d["a"], {"b": 1, "c": True, "d": 1.5, "e": None, "f": "text"})

    def test_sequences_of_scalars_and_mappings(self):
        d = parse("items:\n  - one\n  - two\nobjs:\n  - name: a\n    on: true\n  - name: b\n    on: false\n")
        self.assertEqual(d["items"], ["one", "two"])
        self.assertEqual(d["objs"][1], {"name": "b", "on": False})

    def test_inline_collections(self):
        d = parse("tags: [a, b, c]\nmap: {x: 1, y: 2}\n")
        self.assertEqual(d["tags"], ["a", "b", "c"])
        self.assertEqual(d["map"], {"x": 1, "y": 2})

    def test_comments_stripped_but_not_inside_quotes(self):
        d = parse('a: 1 # comment\nb: "value # not a comment"\n')
        self.assertEqual(d["a"], 1)
        self.assertEqual(d["b"], "value # not a comment")

    def test_block_scalars(self):
        d = parse("literal: |\n  line one\n  line two\nfolded: >\n  a\n  b\n")
        self.assertEqual(d["literal"], "line one\nline two")
        self.assertEqual(d["folded"], "a b")

    def test_tabs_rejected(self):
        with self.assertRaises(MinYamlError):
            parse("a:\n\tb: 1\n")

    def test_missing_colon_rejected(self):
        with self.assertRaises(MinYamlError):
            parse("just a line\n")


class TestJsonSchemaMini(unittest.TestCase):
    SCHEMA = {
        "type": "object",
        "required": ["name", "level"],
        "additionalProperties": False,
        "properties": {
            "name": {"type": "string", "pattern": "^[a-z-]+$", "minLength": 2},
            "level": {"type": "integer", "minimum": 1, "maximum": 4},
            "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "mode": {"type": "string", "enum": ["a", "b"]},
        },
    }

    def test_valid(self):
        self.assertEqual(validate({"name": "ok-name", "level": 2, "tags": ["x"]}, self.SCHEMA), [])

    def test_missing_required(self):
        self.assertTrue(any("required" in e for e in validate({"name": "x-y"}, self.SCHEMA)))

    def test_type_pattern_range_enum_and_extra(self):
        self.assertTrue(validate({"name": "Bad Name", "level": 2}, self.SCHEMA))
        self.assertTrue(validate({"name": "ok", "level": 9}, self.SCHEMA))
        self.assertTrue(validate({"name": "ok", "level": 1, "mode": "c"}, self.SCHEMA))
        self.assertTrue(validate({"name": "ok", "level": 1, "extra": 1}, self.SCHEMA))

    def test_boolean_is_not_an_integer(self):
        self.assertTrue(validate({"name": "ok", "level": True}, self.SCHEMA))

    def test_ref_resolution(self):
        schema = {"definitions": {"t": {"type": "string"}},
                  "type": "object", "properties": {"a": {"$ref": "#/definitions/t"}}}
        self.assertEqual(validate({"a": "x"}, schema), [])
        self.assertTrue(validate({"a": 1}, schema))

    def test_unsupported_keyword_detection_ignores_property_names(self):
        schema = {"type": "object", "properties": {"if": {"type": "string"}}}
        self.assertEqual(unsupported_keywords(schema), set())
        self.assertIn("dependentRequired", unsupported_keywords({"dependentRequired": {}}))


class TestFrontmatter(unittest.TestCase):
    def test_split(self):
        fm, body = split("---\nname: x\ntools: A, B\n---\n\n# Title\n")
        self.assertEqual(fm["name"], "x")
        self.assertIn("# Title", body)

    def test_no_frontmatter(self):
        fm, body = split("# Title\n")
        self.assertEqual(fm, {})

    def test_unterminated_frontmatter_raises(self):
        with self.assertRaises(ValueError):
            split("---\nname: x\n")


class TestPathMatching(unittest.TestCase):
    def test_double_star_is_directory_aware(self):
        self.assertTrue(path_matches("docs/architecture/a/b.md", ["docs/architecture/**"]))
        self.assertFalse(path_matches("docs/other/b.md", ["docs/architecture/**"]))

    def test_single_star_does_not_cross_separators(self):
        self.assertTrue(path_matches("src/a.py", ["src/*"]))
        self.assertFalse(path_matches("srcx/a.py", ["src/**"]))

    def test_leading_double_star(self):
        self.assertTrue(path_matches("/deep/nested/.env", ["**/.env"]))
        self.assertTrue(path_matches(".env", ["**/.env"]))

    def test_extension_patterns(self):
        self.assertTrue(path_matches("a/b/thing_test.go", ["**/*_test.*"]))
        self.assertFalse(path_matches("a/b/thing.go", ["**/*_test.*"]))

    def test_empty_inputs(self):
        self.assertFalse(path_matches("", ["**"]))
        self.assertFalse(path_matches("a.py", []))


if __name__ == "__main__":
    unittest.main()
