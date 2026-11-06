"""Azerbaijan name-to-GeoNames proposal, without certified identity claims."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import western_asia_azerbaijan_administration as az


class OfficialEconomicRegionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = az.read_source()
        cls.report = az.report(source=cls.source)

    def test_official_economic_regions_and_68_members(self):
        self.assertEqual(self.report["economic_reporting_regions"], 14)
        self.assertEqual(self.report["source_administrative_unit_labels"], 68)
        self.assertEqual(len(self.source["economic_regions"]), 14)
        self.assertFalse(self.report["original_official_geojson_downloaded"])

    def test_nakhchivan_is_single_reference_autonomous_republic(self):
        all_members = [m for group in self.source["economic_regions"] for m in group["members"]]
        ar = [m for m in all_members if m["unit_kind"] == "autonomous_republic"]
        self.assertEqual(len(ar), 1)
        self.assertEqual(ar[0]["name_az"], "Naxçıvan")

    def test_aghdere_is_government_listed_but_not_assigned_to_a_gn_id(self):
        entries = [x for x in self.report["candidate_records"] if x["name_az"] == "Ağdərə"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["economic_region"], "Qarabağ")
        self.assertFalse(entries[0]["verified_official_gn_identity"])

    def test_2026_geographical_source_is_not_adm1_directly(self):
        self.assertEqual(self.source["source_updated_at"], "2026-06-29")
        for group in self.source["economic_regions"]:
            self.assertEqual(group["classification"], "economic_reporting_region_not_administrative_parent_id")
            for member in group["members"]:
                self.assertFalse(member["accepted_id_crosswalk"])
                self.assertIsNone(member["geonames_id"])

    def test_name_key_not_promoted_as_official_translation(self):
        self.assertEqual(az.name_key("Ağdərə"), "aghdara")
        self.assertEqual(az.base_name("Şuşa rayonu"), "shusha")
        self.assertEqual(az.base_name("Shusha Rayon"), "shusha")
        self.assertEqual(az.base_name("Şəki şəhəri"), "shaki")

    def test_rayon_and_city_names_not_collapsed(self):
        geo = [
            {"id": "gn:1", "name": "Shusha Rayon", "asciiname": "Shusha Rayon",
             "alternatenames": "", "admin_level": "1", "feature_code": "ADM1"},
            {"id": "gn:2", "name": "Shusha City", "asciiname": "Shusha City",
             "alternatenames": "", "admin_level": "1", "feature_code": "ADM1"},
        ]
        rayon = {"ref": "example:rayon", "name_az": "Şuşa", "unit_kind": "rayon",
                 "source_economic_region": "Qarabağ"}
        result = az.candidates_for(rayon, geo)
        self.assertEqual(result["geonames_candidates"], ["gn:1"])
        self.assertFalse(result["verified_official_gn_identity"])

    def test_actual_archived_geonames_preserved(self):
        self.assertEqual(self.report["geonames_adm1_in_snapshot"], 71)
        self.assertEqual(self.report["verified_government_to_geonames_ids"], 0)
        self.assertEqual(sum(self.report[x] for x in
                             ("unique_unreviewed_name_candidates", "ambiguous_candidates",
                              "unmatched_source_labels")), 68)
        for row in self.report["candidate_records"]:
            self.assertTrue(all(id.startswith("gn:") for id in row["geonames_candidates"]))
            self.assertFalse(row["verified_official_postcode_assignment"])
        print("AZ_ECON_CANDIDATE_SUMMARY " + json.dumps({
            k: self.report[k] for k in ("source_administrative_unit_labels",
            "geonames_adm1_in_snapshot", "unique_unreviewed_name_candidates",
            "ambiguous_candidates", "unmatched_source_labels",
            "geonames_adm1_without_name_candidate")}, sort_keys=True))


if __name__ == "__main__":
    unittest.main()
