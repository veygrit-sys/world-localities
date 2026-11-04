"""M49 scope, country gaps, PR boundary and source-preserving query regressions."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def imported(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = imported("unified_americas", "americas-registry/audit.py")
northern = imported("northern_localities", "north-america-registry/query.py")


class AmericasAreaQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = audit.audit(ROOT)
        cls.areas = {x["key"]: x for x in cls.report["areas"]}

    def test_all_57_m49_country_areas_have_explicit_status(self):
        self.assertEqual([x["key"] for x in self.report["areas"]],
                         ["northern-america", "central-america", "caribbean", "south-america"])
        self.assertEqual(self.report["m49_country_area_count"], 57)
        self.assertEqual(self.report["source_country_area_count"], 53)
        self.assertEqual([x["m49_country_area_count"] for x in self.report["areas"]],
                         [5, 8, 28, 16])
        self.assertEqual([x["source_country_area_count"] for x in self.report["areas"]],
                         [2, 8, 27, 16])
        self.assertEqual([x["pending_country_area_codes"] for x in self.report["areas"]],
                         [["BM", "GL", "PM"], [], ["CU"], []])
        self.assertIs(self.report["postal_street_delivery_verified"], False)

    def test_northern_coverage_excludes_puerto_rico_from_us_source_count(self):
        area = self.areas["northern-america"]
        self.assertEqual(area["source_locality_rows_in_m49_area"], 72567)
        by_code = {x["country"]: x for x in area["countries"]}
        self.assertEqual(by_code["US"]["source_locality_rows"], 68744)
        self.assertEqual(by_code["US"]["excluded_source_locality_rows"], 1231)
        self.assertEqual(by_code["CA"]["source_locality_rows"], 5054)
        self.assertEqual(by_code["GL"]["status"], "pending_source")

    def test_central_mexico_layer_is_not_lost_or_wrongly_reclassified(self):
        area = self.areas["central-america"]
        by_code = {x["country"]: x for x in area["countries"]}
        self.assertEqual(by_code["MX"]["layer"], "official-registry/MX")
        self.assertEqual(by_code["MX"]["source_locality_rows"], 2478)
        self.assertNotIn("CR", area["pending_country_area_codes"])

    def test_caribbean_pr_and_us_source_pr_remain_distinct(self):
        by_code = {x["country"]: x for x in self.areas["caribbean"]["countries"]}
        self.assertEqual(by_code["PR"]["layer"], "caribbean-registry")
        self.assertEqual(by_code["CU"]["status"], "pending_source")
        with self.assertRaisesRegex(northern.QueryError, "outside M49"):
            northern.search("US", region="US-PR", root=ROOT)
        included = northern.search(
            "US", region="US-PR", include_cross_region_pr=True, limit=1, root=ROOT
        )
        self.assertEqual(included["rows_scanned"], 1231)
        self.assertTrue(included["cross_region_override_used"])
        self.assertEqual(included["results"][0]["address_country"], "PR")

    def test_nova_scotia_is_corrected_only_at_display_time(self):
        result = northern.search("CA", region="CA-NS", text="Shelburne", limit=2, root=ROOT)
        self.assertGreater(result["matches_found"], 0)
        self.assertEqual(result["results"][0]["region_name"], "Nova Scotia")
        self.assertEqual(result["results"][0]["region_name_in_snapshot"], "New Scotia")
        self.assertEqual(result["results"][0]["language"], "und")
        with self.assertRaisesRegex(northern.QueryError, "source region name changed"):
            northern.display_region_name(
                "CA", {"code": "CA-NS", "name": "already corrected"},
                {("CA", "CA-NS"): {
                    "snapshot_name": "New Scotia",
                    "display_name_en": "Nova Scotia",
                    "status": "verified_presentation_correction",
                    "evidence_url": "https://www150.statcan.gc.ca/"
                }}
            )

    def test_address_candidate_is_not_delivery_verification(self):
        result = northern.search("US", region="US-CA", candidate_only=True,
                                 limit=5, root=ROOT)
        self.assertEqual(result["rows_scanned"], 2026)
        self.assertTrue(result["results"])
        self.assertTrue(all(x["address_candidate_flag"] for x in result["results"]))
        self.assertTrue(all(not x["delivery_verified"] for x in result["results"]))
        self.assertTrue(all(not x["postal_assignment_verified"] for x in result["results"]))

    def test_pending_source_returns_administrative_seeds_not_fake_localities(self):
        counts = {"BM": 11, "GL": 5, "PM": 2}
        self.assertEqual(audit.verify_administrative_seeds(ROOT), counts)
        for cc, count in counts.items():
            result = northern.search(cc, root=ROOT)
            self.assertEqual(result["status"], "not_loaded")
            self.assertIsNone(result["source_locality_rows"])
            self.assertIsNone(result["matches_found"])
            self.assertEqual(result["results"], [])
            self.assertEqual(len(result["administrative_seeds"]), count)
            self.assertTrue(all(not x["postal_or_street_verified"] for x in result["administrative_seeds"]))
        pm = northern.search("PM", text="Miquelon", root=ROOT)
        self.assertEqual(pm["administrative_seed_matches"], 1)
        self.assertEqual(pm["administrative_seeds"][0]["official_code"], "97501")

    def test_plan_starts_with_northern_gaps(self):
        queue = audit.quality_queue(self.report)
        self.assertEqual([x["country"] for x in queue[:3]], ["BM", "GL", "PM"])
        self.assertFalse(self.report["official_municipality_completeness_verified"])


if __name__ == "__main__":
    unittest.main()
