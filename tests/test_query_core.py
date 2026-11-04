"""Behavioral tests for query rules shared by regional registries."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from localities.query import matching_rows, page, validate_country_code


def row(entity_id, name, *, candidate="1", kind="locality", level="", state="", parent=""):
    return {
        "id": entity_id,
        "name": name,
        "asciiname": name,
        "alternatenames": "Alias," + name,
        "address_candidate": candidate,
        "kind": kind,
        "admin_level": level,
        "state_id": state,
        "parent_id": parent,
    }


class SharedQueryRules(unittest.TestCase):
    def setUp(self):
        self.rows = [
            row("gn:1", "Alpha", state="gn:10", parent="gn:20"),
            row("gn:2", "Beta", candidate="0"),
            row("gn:10", "Region", candidate="0", kind="admin_subdivision", level="1"),
        ]

    def test_country_code_is_strict(self):
        validate_country_code("JP")
        for value in ("jp", "JPN", "1P", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_country_code(value)

    def test_default_returns_only_address_candidates(self):
        self.assertEqual([item["id"] for item in matching_rows(self.rows)], ["gn:1"])

    def test_explicit_kind_or_level_includes_non_candidates(self):
        self.assertEqual(
            [item["id"] for item in matching_rows(self.rows, kind="locality")],
            ["gn:1", "gn:2"],
        )
        self.assertEqual(
            [item["id"] for item in matching_rows(self.rows, level=1)], ["gn:10"]
        )

    def test_text_and_exact_relationship_filters(self):
        self.assertEqual(
            [item["id"] for item in matching_rows(self.rows, text="alias")], ["gn:1"]
        )
        self.assertEqual(
            [
                item["id"]
                for item in matching_rows(
                    self.rows, state="gn:10", parent="gn:20", include_other=True
                )
            ],
            ["gn:1"],
        )

    def test_pagination_counts_all_matches_without_overlap(self):
        total, first = page(iter(self.rows), 0, 2)
        next_total, second = page(iter(self.rows), 2, 2)
        self.assertEqual(total, next_total)
        self.assertEqual(total, 3)
        self.assertFalse({item["id"] for item in first} & {item["id"] for item in second})
        with self.assertRaises(ValueError):
            page(iter(self.rows), 0, True)


if __name__ == "__main__":
    unittest.main()
