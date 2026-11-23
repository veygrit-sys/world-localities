import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from addressing.safe_suggest import build_index, suggest
from localities.postal_picker import IndexUnavailable, PostalPicker


class SourceBackedSuggestionTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.index = Path(folder.name) / "index.sqlite"
        rows = [
            ("US", "01234", (("area", "A City, TX"), ("street", "Alta Road")), "s1"),
            ("US", "01234", (("area", "A City, TX"), ("street", "Beta Avenue")), "s2"),
            ("US", "01234", (("area", "A City, TX"), ("street", "Oak Boulevard")), "s1"),
            ("US", "01234", (("area", "A City, TX"), ("street", "Zero Boulevard")), "s1"),
            ("US", "01234", (("area", "A City, TX"), ("street", "Zero Boulevard")), "s2"),
            ("US", "01234", (("area", "B City, TX"), ("street", "North Boulevard")), "s3"),
            ("CA", "01234", (("area", "A City, TX"), ("street", "Other Boulevard")), "s3"),
        ]
        with patch("localities.postal_picker._records", return_value=rows):
            build_index(self.index)

    def test_filter_before_pagination_and_attach_exact_child_evidence(self):
        scope = suggest(self.index, "us", "01234", query="a city")
        area = scope["options"][0]["id"]
        self.assertEqual(scope["options"][0]["supporting_sources"], ["s1", "s2"])
        args = dict(index=self.index, country="US", postcode="01234", path=[area], query="ＢＯＵ", limit=1)
        first = suggest(**args)
        second = suggest(**args, after=first["next_after"])
        self.assertEqual([x["options"][0]["label"] for x in [first, second]], ["Oak Boulevard", "Zero Boulevard"])
        option = second["options"][0]
        self.assertEqual(option["supporting_sources"], ["s1", "s2"])
        self.assertEqual((option["source_id"], option["country_code"], option["postcode"]), ("s1", "US", "01234"))
        self.assertFalse(second["deliverability_verified"])
        self.assertTrue(second["manual_entry_available"])
        self.assertIsNone(second["next_after"])
        with self.assertRaises(ValueError):
            suggest(self.index, "CA", "01234", path=[area])

    def test_search_miss_is_not_leaf_or_country_coverage_signal(self):
        first = suggest(self.index, "US", "01234", query="A City")
        area = first["options"][0]["id"]
        for literal in ("zzzz", "%", "_", "' OR 1=1"):
            found = suggest(self.index, "US", "01234", query=literal, path=[area])
            self.assertEqual((found["status"], found["options"]), ("no_matching_options", []))
        street = suggest(self.index, "US", "01234", path=[area], query="Oak")["options"][0]["id"]
        self.assertEqual(suggest(self.index, "US", "01234", path=[area, street], query="12")["status"], "leaf")
        self.assertEqual(suggest(self.index, "US", "1234", query="Oak")["status"], "not_found")
        self.assertEqual(suggest(self.index, "ZZ", "01234", query="Oak")["status"], "unsupported_country")

    def test_empty_rebuild_preserves_index_and_bad_version_is_server_error(self):
        with patch("localities.postal_picker._records", return_value=[]), self.assertRaisesRegex(ValueError, "no eligible"):
            build_index(self.index)
        self.assertEqual(PostalPicker(self.index).countries(), ["CA", "US"])
        with sqlite3.connect(self.index) as db:
            db.execute("PRAGMA user_version=0")
        with self.assertRaises(IndexUnavailable):
            PostalPicker(self.index)

    def test_cmab_only_shows_same_published_offices_language_and_postcode(self):
        from localities.open_reference.cn import lookup
        build_index(self.index, ["CN"])
        directory = lookup("518033")[0]
        offices = suggest(self.index, "CN", "518033")
        self.assertEqual({r["label"] for r in offices["options"]}, set(directory["name"].values()))
        self.assertTrue(all(r["kind"] == "published_office" for r in offices["options"]))
        for lang in ("en", "zh-Hant"):
            office = next(r for r in offices["options"] if r["label"] == directory["name"][lang])
            result = suggest(self.index, "CN", "518033", path=[office["id"]])
            self.assertEqual([r["label"] for r in result["options"]], [directory["address"][lang]])
            self.assertEqual(result["source_details"][directory["source_id"]]["scope"], "published_offices_only")
            self.assertTrue(result["source_details"][directory["source_id"]]["terms_url"])
        self.assertEqual(suggest(self.index, "CN", "518034")["status"], "not_found")
        self.assertEqual(suggest(self.index, "CN", "518")["status"], "not_found")

    def test_spelling_rescue_is_small_scoped_confirmed_and_never_replaces_prefix(self):
        def entry(postcode, label, kind="street", source="us-dc-mar"):
            return "US", postcode, (("area", "Washington, DC"), (kind, label)), source

        rows = [entry("20001", street) for street in ("Harbor Road NW", "Harbor Rise NW", "River Road NW")]
        rows += [entry("20002", street) for street in ("Harbr Circle NW", "Harbor Avenue NW")]
        rows += [entry("20003", "Harbor Road NW", source="other")]
        rows += [entry("20004", "Harbor Road NW", kind="house_number")]
        rows += [entry("20005", "Harbor Road NW"), *[entry("20005", f"Street {n}") for n in range(100)]]
        with patch("localities.postal_picker._records", return_value=rows):
            build_index(self.index)

        def streets(code, query, **kwargs):
            area = suggest(self.index, "US", code)["options"][0]["id"]
            return suggest(self.index, "US", code, path=[area], query=query, **kwargs)

        first = streets("20001", "harbr", limit=1)
        second = streets("20001", "harbr", limit=1, after=first["next_after"])
        self.assertEqual({r["options"][0]["label"] for r in [first, second]}, {"Harbor Road NW", "Harbor Rise NW"})
        self.assertTrue(all(r["match_mode"] == "similar_spelling" for r in [first, second]))
        self.assertEqual(first["spelling_notice"], "confirm_suggested_spelling")
        self.assertFalse(first["auto_selected"])
        exact = streets("20002", "harbr")
        self.assertEqual(([o["label"] for o in exact["options"]], exact["match_mode"]), (["Harbr Circle NW"], "prefix"))
        with self.assertRaises(ValueError):
            streets("20002", "harbr", after=1)
        for code, query in [("20003", "harbr"), ("20004", "harbr"), ("20005", "harbr"),
                            ("20001", "har%br"), ("20001", "har3br"), ("20001", "XYZ")]:
            with self.subTest(code=code, query=query):
                self.assertEqual(streets(code, query)["options"], [])
