import unittest

from localities.open_reference.un_cities import COUNTRIES, SOURCE, lookup


class UnUrbanCentreTest(unittest.TestCase):
    def test_all_2025_source_codes_in_inventory(self):
        self.assertEqual(len(COUNTRIES), 191)
        counts = SOURCE["country_counts"]
        self.assertEqual(sum(counts.values()), 12138)
        self.assertEqual((counts["CN"], counts["JP"], counts["US"]), (2082, 137, 348))
        self.assertEqual((counts["HK"], counts["MO"], counts["TW"]), (6, 1, 21))
        self.assertEqual(counts["NA"], 4)  # Namibia's country code is a literal value.

    def test_china_preserves_source_code_name_and_population_weighted_point(self):
        [row] = lookup(" bEiJIng ", country="cn")
        self.assertEqual(row["record_id"], "un-wup2025:9020")
        self.assertEqual(row["name"], "Beijing")
        self.assertEqual(row["evidence_type"], "statistical_urban_centre")
        self.assertAlmostEqual(row["population_weighted_centroid"]["latitude"], 39.9287511)
        self.assertAlmostEqual(row["population_weighted_centroid"]["longitude"], 116.3724445)
        self.assertEqual(lookup(row["record_id"], country="CN"), [row])
        self.assertFalse(lookup("9020", country="CN"))
        self.assertFalse(lookup(row["record_id"], country="HK"))
        self.assertFalse(lookup("北京市", country="CN"))
        self.assertFalse(lookup("9020", country="US"))

    def test_same_name_never_collapses_distinct_source_cities(self):
        rows = lookup("Anping", country="CN")
        self.assertEqual({row["city_code"] for row in rows}, {"9266", "9296"})
        self.assertEqual(len({row["source_row"] for row in rows}), 2)
        rows[0]["name"] = "changed"
        self.assertTrue(all(row["name"] == "Anping" for row in lookup("Anping", country="CN")))
