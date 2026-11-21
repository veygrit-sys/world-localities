import unittest

from localities.open_reference.cn import _records, lookup


class MainlandOfficeReferenceTest(unittest.TestCase):
    def test_complete_bilingual_office_directory(self):
        records = list(_records())
        ids = {row["record_id"] for row in records}
        self.assertEqual(len(records), 16)
        self.assertEqual(len(ids), len(records))
        self.assertEqual(sum(row["kind"] == "office" for row in records), 5)
        for row in records:
            self.assertEqual(row["country"], "CN")
            self.assertEqual(row["source_updated_on"], "2024-11-21")
            self.assertEqual(row["evidence_type"], "published_office_address")
            for language in ("en", "zh-Hant"):
                for field in ("name", "address"):
                    self.assertIn(row["record_id"],
                                  [found["record_id"] for found in lookup(row[field][language])])
            self.assertIn(row["record_id"],
                          [found["record_id"] for found in lookup(row["postcode"])])

    def test_sourced_fields_and_postcode_in_same_row(self):
        [shenzhen] = lookup("駐深圳聯絡處")
        self.assertEqual(shenzhen["record_id"], "hk-cmab:guangdong/shenzhen-liaison-unit")
        self.assertEqual(lookup("518033"), [shenzhen])
        self.assertEqual(lookup("  SHENZHEN    liaison UNIT "), [shenzhen])
        self.assertIn("Room 2805A", shenzhen["address"]["en"])
        self.assertIn("2805A室", shenzhen["address"]["zh-Hant"])
        self.assertNotEqual(lookup("100009"), [shenzhen])

    def test_map_points_require_an_identical_published_address(self):
        rows = list(_records())
        matching = [row for row in rows if row["map_point"] is not None]
        self.assertEqual(len(matching), 10)
        for row in matching:
            self.assertEqual(row["address"]["en"], row["map_point"]["source_address"])
            self.assertEqual(row["map_point"]["crs"], "EPSG:4326")
        [beijing] = lookup("100009")
        self.assertAlmostEqual(beijing["map_point"]["longitude"], 116.389627)
        self.assertAlmostEqual(beijing["map_point"]["latitude"], 39.933678)
        [jinan] = lookup("250012")
        self.assertIn("102 Luoyuan Street", jinan["address"]["en"])
        self.assertIsNone(jinan["map_point"])

    def test_does_not_infer_a_new_address_or_script(self):
        self.assertFalse(lookup("5180333"))
        self.assertFalse(lookup("驻深圳联络处"))
        self.assertFalse(lookup("Shenzhen"))
        self.assertFalse(lookup("taiwan"))
        self.assertFalse(lookup(""))
        [shenzhen] = lookup("518033")
        self.assertFalse(lookup(shenzhen["address"]["en"].replace("2805A", "2806A")))
