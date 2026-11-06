"""Regression tests for official first-level source intake, not delivery readiness."""
import unittest
from reconcile_adm1 import compare_country, norm, report


class FourCountryOfficialAdminNames(unittest.TestCase):
    def test_imported_official_name_counts(self):
        result = report()
        self.assertEqual(result["official_source_records"], 109)
        expected = {"ZA": 9, "NG": 37, "KE": 47, "GH": 16}
        self.assertEqual({c: v["source_records"] for c, v in result["country_results"].items()}, expected)
        self.assertEqual(result["certified_matches"], 0)
        self.assertFalse(result["original_geonames_modified"])

    def test_south_africa_province_names_exact(self):
        result = compare_country("ZA")
        self.assertTrue(all(r["status"] == "exact_name_candidate" and not r["approved"] for r in result))
        self.assertEqual(len({r["candidate_geonames_ids"][0] for r in result}), 9)

    def test_kenya_counties_reconcile_as_review_only(self):
        result = compare_country("KE")
        self.assertEqual(sum(r["status"] == "curated_alias_candidate" for r in result), 2)
        self.assertEqual(sum(r["status"] == "exact_name_candidate" for r in result), 45)
        self.assertEqual(len({r["candidate_geonames_ids"][0] for r in result}), 47)
        self.assertFalse(any(r["approved"] for r in result))

    def test_ghana_region_suffixes_not_automatically_certified(self):
        result = compare_country("GH")
        self.assertEqual(sum(r["status"] == "curated_alias_candidate" for r in result), 9)
        self.assertEqual(sum(r["status"] == "exact_name_candidate" for r in result), 7)
        self.assertEqual(len({r["candidate_geonames_ids"][0] for r in result}), 16)
        self.assertFalse(any(r["approved"] for r in result))

    def test_nigeria_does_not_fake_missing_geonames(self):
        result = compare_country("NG")
        self.assertTrue(all(r["status"] == "source_snapshot_not_migrated"
                            and not r["candidate_geonames_ids"] for r in result))

    def test_normalization_keeps_local_names_distinct(self):
        self.assertEqual(norm("  Northern  Region"), "northern region")
        self.assertNotEqual(norm("Sao"), norm("São"))


if __name__ == "__main__":
    unittest.main()
