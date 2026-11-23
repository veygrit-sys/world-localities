import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from localities.postal_picker import PostalPicker, _OPTIONS, _postcode, build_index


class PostalPickerTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.file = Path(folder.name) / "index.sqlite"
        self.records = [
            ("JP", "001-0001", (("area", "北海道札幌市"), ("town", "北一条")), "jp"),
            ("JP", "0010001", (("area", "北海道札幌市"), ("town", "北二条")), "jp"),
            ("JP", "0010001", (("area", "北海道札幌市"), ("town", "北二条")), "jp"),
            ("JP", "0010001", (("area", "別の市"), ("town", "北一条")), "jp"),
            ("JP", "0020001", (("area", "北海道札幌市"), ("town", "北一条")), "jp"),
            ("CA", "T0A 0A0", (("area", "Abee, Alberta"),), "geo"),
            ("US", "00501", (("area", "Holtsville, NY"),), "geo"),
            ("US", "20001", (("area", "Washington, DC"),), "geo"),
            ("US", "20001", (("area", "Washington, DC"), ("street", "Example Street"),
                            ("house_number", "12")), "mar"),
            ("US", "20001", (("area", "Washington, DC"), ("street", "Example Street"),
                            ("house_number", "2")), "mar"),
            ("DE", "0010001", (("area", "北海道札幌市"),), "fixture"),
        ]
        with patch("localities.postal_picker._records", return_value=self.records):
            summary = build_index(self.file)
        self.assertEqual(summary["countries"], ["CA", "DE", "JP", "US"])
        self.picker = PostalPicker(self.file)

    def test_exact_lookup_and_normalization(self):
        result = self.picker.lookup("jp", "００１－０００１")
        self.assertEqual((result["status"], result["postcode"]), ("options", "0010001"))
        self.assertEqual({o["label"] for o in result["options"]}, {"北海道札幌市", "別の市"})
        self.assertEqual(self.picker.lookup("CA", "t0a0a0")["options"][0]["label"], "Abee, Alberta")
        for country, code in [("JP", "001"), ("US", "501"), ("US", "00501-0000"), ("CA", "T0A")]:
            with self.subTest(country=country, code=code):
                self.assertEqual(self.picker.lookup(country, code)["status"], "not_found")
        match = self.picker.lookup("US", "00501")
        self.assertEqual(match["options"][0]["label"], "Holtsville, NY")
        self.assertFalse(match["options"][0]["has_children"])
        self.assertFalse(match["deliverability_verified"])
        self.assertEqual(self.picker.lookup("ZZ", "123")["status"], "unsupported_country")

    def test_compact_complete_codes(self):
        for country, raw, canonical in [
            ("PL", "00002", "00-002"), ("SK", "01001", "010 01"), ("CZ", "10000", "100 00"),
            ("SE", "10004", "100 04"), ("PT", "1000001", "1000-001"), ("AZ", "az0100", "AZ 0100"),
            ("LV", "lv1001", "LV-1001"), ("BM", "cr01", "CR 01"),
        ]:
            with self.subTest(country=country):
                self.assertEqual(_postcode(country, raw), canonical)
                self.assertEqual(_postcode(country, canonical), canonical)

    def test_parent_child_scoping_and_pagination(self):
        lookup = self.picker.lookup
        jp = lookup("JP", "0010001")
        area = next(x["id"] for x in jp["options"] if x["label"] == "北海道札幌市")
        other_area = next(x["id"] for x in jp["options"] if x["label"] == "別の市")
        first = lookup("JP", "0010001", [area], limit=1)
        second = lookup("JP", "0010001", [area], after=first["next_after"], limit=1)
        self.assertEqual({first["options"][0]["label"], second["options"][0]["label"]}, {"北一条", "北二条"})
        self.assertIsNone(second["next_after"])
        town = first["options"][0]["id"]
        for country, code, path in [("JP", "0020001", [area]), ("DE", "0010001", [area]),
                                    ("JP", "0010001", [other_area, town]), ("JP", "0010001", [town])]:
            with self.subTest(country=country, code=code, path=path):
                with self.assertRaises(ValueError):
                    lookup(country, code, path)
        leaf = lookup("JP", "0010001", [area, town])
        self.assertEqual(leaf["status"], "leaf")
        self.assertEqual([x["id"] for x in leaf["selected"]], [area, town])
        self.assertFalse(leaf["options"])

    def test_source_aggregation_and_only_observed_house_numbers(self):
        def us(path):
            return self.picker.lookup("US", "20001", path)
        root = us([])
        self.assertEqual(root["sources"], ["geo", "mar"])
        self.assertEqual(len(root["options"]), 1)
        area = root["options"][0]
        self.assertTrue(area["has_children"])
        street = us([area["id"]])["options"][0]
        result = us([area["id"], street["id"]])
        self.assertEqual(result["sources"], ["mar"])
        self.assertEqual([n["label"] for n in result["options"]], ["2", "12"])
        self.assertTrue(all(not n["has_children"] for n in result["options"]))

    def test_indexed_range_and_no_read_time_source_scan(self):
        with sqlite3.connect(self.file) as db:
            plan = db.execute("EXPLAIN QUERY PLAN " + _OPTIONS, ("US", "20001", b"", 51, 0))
            self.assertTrue(any("SEARCH edges USING PRIMARY KEY" in row[-1] for row in plan))
        with patch("localities.postal_picker._records", side_effect=AssertionError):
            self.assertEqual(self.picker.countries(), ["CA", "DE", "JP", "US"])
            self.assertEqual(self.picker.lookup("US", "00501")["status"], "options")

    def test_failed_rebuild_keeps_previous_database(self):
        def interrupted():
            yield self.records[0]
            raise ValueError("damaged source")
        with patch("localities.postal_picker._records", return_value=interrupted()):
            with self.assertRaisesRegex(ValueError, "damaged source"):
                build_index(self.file)
        self.assertEqual(self.picker.lookup("US", "00501")["status"], "options")
        self.assertEqual(list(self.file.parent.iterdir()), [self.file])

    def test_rebuilt_index_rejects_vanished_selection(self):
        selected = self.picker.lookup("US", "00501")["options"][0]["id"]
        with patch("localities.postal_picker._records", return_value=self.records[-4:]):
            build_index(self.file)
        with self.assertRaises(ValueError):
            self.picker.lookup("US", "00501", [selected])

    def test_invalid_requests(self):
        for country, code, path, kwargs in [
            ("USA", "00501", [], {}), ("US", "", [], {}), ("US", "00501", [], {"limit": 0}),
            ("US", "00501", [], {"after": -1}), ("US", "00501", ["bad"], {}),
            ("US", "00501", ["x" * 2100], {}), ("US", "00501", [], {"after": 17}),
        ]:
            with self.subTest(country=country, path=path, kwargs=kwargs):
                with self.assertRaises(ValueError):
                    self.picker.lookup(country, code, path, **kwargs)


if __name__ == "__main__":
    unittest.main()
