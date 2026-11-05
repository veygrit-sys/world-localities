"""Official publisher excerpt → country-specific postal facts → GeoNames candidates."""
from collections import Counter
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import western_asia_postal_join as p

class PostalOfficialEvidence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = p.load_excerpt()
        cls.report = p.summary(cls.data)
        cls.by_country = {x["country"]: x for x in cls.report["country_reports"]}

    def test_85_real_published_office_area_or_example_code_rows(self):
        self.assertEqual(len(self.data["records"]), 85)
        self.assertEqual({cc: self.by_country[cc]["source_records"] for cc in p.SCOPE},
                         {"SA":1,"BH":2,"QA":0,"OM":37,"PS":45})
        self.assertEqual(self.report["source_records"], 85)

    def test_source_row_grain_and_license_are_explicit(self):
        self.assertTrue(all(src["original_source_sha256"] is None
                            for src in self.data["sources"].values()))
        self.assertTrue(all(src["source_url"].startswith("https://")
                            for src in self.data["sources"].values()))
        self.assertEqual(self.data["quality"]["original_bulk_sources_downloaded"],0)
        self.assertEqual(self.report["official_bulk_datasets_with_original_sha256"],0)
        for cc in ("OM","PS"):
            self.assertGreater(self.by_country[cc]["distinct_code_values"],0)

    def test_palestine_multiple_towns_share_postal_area_code(self):
        rows=self.by_country["PS"]["records"]
        group={code:[r for r in rows if r["code"]==code] for code in ("P626","P663","P113","P350")}
        self.assertTrue(all(len(v)==2 for v in group.values()))
        self.assertTrue(all(x["multiple_places_per_code"] for values in group.values() for x in values))
        self.assertLess(self.by_country["PS"]["distinct_code_values"],45)

    def test_oman_multiple_offices_with_same_city_can_have_different_codes(self):
        rows=self.by_country["OM"]["records"]
        self.assertEqual({r["code"] for r in rows if r["source_place_name"]=="Ruwi"},
                         {"112","168"})
        self.assertEqual({r["code"] for r in rows if r["source_place_name"]=="Khasab"},
                         {"811","819"})
        self.assertEqual(self.by_country["OM"]["source_excerpt_grain"],"postal_office_branch")
        self.assertFalse(any(r["official_code_to_geonames_identity_verified"] for r in rows))

    def test_source_gov_and_geonames_separate(self):
        rows=self.by_country["OM"]["records"]
        self.assertTrue(any(r["government_admin_match"]=="combined_or_historical_governorate_label"
                            for r in rows))
        for country in ("OM","PS"):
            for record in self.by_country[country]["records"]:
                self.assertFalse(record["official_code_to_geonames_identity_verified"])
                self.assertFalse(record["address_or_deliverability_verified"])
                self.assertTrue(all(v.startswith("gn:") for v in record["geonames_candidate_ids"]))
        self.assertEqual(self.report["reviewed_postcode_to_geonames_links"],0)

    def test_example_codes_are_not_regarded_as_directory(self):
        sa=self.by_country["SA"]
        bh=self.by_country["BH"]
        self.assertEqual(sa["records"][0]["code"],"13337")
        self.assertEqual({r["code"] for r in bh["records"]},{"317","926"})
        self.assertEqual(sa["source_excerpt_grain"],
                         "single_published_national_address_example")
        self.assertEqual(bh["source_excerpt_grain"],
                         "two_published_postcode_examples")

    def test_no_qatar_postcode_invented(self):
        qa=self.by_country["QA"]
        self.assertEqual(qa["source_records"],0)
        self.assertEqual(qa["reviewed_postcode_to_geonames_links"],0)
        self.assertEqual(qa["status"],"no_postcode_source_import_expected")

    def test_must_not_confuse_palestine_statistical_and_postcode_schemes(self):
        with self.assertRaises(ValueError):
            p.load_excerpt(path=ROOT/"registries/official/western-asia/admin-crosswalk/source_names.json")
        for r in self.by_country["PS"]["records"]:
            self.assertRegex(r["code"],r"^P[0-9]{3}$")

    def test_source_codes_can_be_queried_without_claiming_absence(self):
        subset=[r for r in self.by_country["PS"]["records"] if r["code"]=="P610"]
        self.assertEqual(len(subset),1)
        self.assertEqual(subset[0]["source_place_name"],"البيرة")
        self.assertFalse(self.report["reviewed_postcode_to_geonames_links"])

if __name__=="__main__":
    unittest.main()
