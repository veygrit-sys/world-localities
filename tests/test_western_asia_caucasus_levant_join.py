"""Quality gates for AM GE AZ IL JO official-source candidate reconciler."""
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import western_asia_caucasus_levant_join as m

class EvidenceInventory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources=m.load_sources()
        cls.reports={cc:m.country_report(cc,dataset=cls.sources) for cc in m.COUNTRIES}

    def test_5_country_scope_and_source_name_grain(self):
        self.assertEqual(set(m.COUNTRIES),{"AM","GE","AZ","IL","JO"})
        self.assertEqual({cc:r["official_admin_names"] for cc,r in self.reports.items()},
                         {"AM":11,"GE":12,"AZ":2,"IL":6,"JO":12})
        self.assertEqual({cc:r["published_postal_source_rows"] for cc,r in self.reports.items()},
                         {"AM":14,"GE":3,"AZ":24,"IL":2,"JO":3})
        self.assertEqual(sum(r["published_postal_source_rows"] for r in self.reports.values()),46)

    def test_existing_five_archives_hashed_and_ids_unchanged(self):
        source=json.loads((ROOT/"registries/asia/archives.json").read_text())
        refs={r["country"]:r for r in source["archives"]}
        for cc in m.COUNTRIES:
            self.assertEqual(self.reports[cc]["source_rows"],refs[cc]["rows"])
            self.assertEqual(self.reports[cc]["archive_sha256"],refs[cc]["sha256"])
            self.assertGreater(self.reports[cc]["source_rows"],100)

    def test_canonical_postcode_syntax_exact_country_and_leading_zeros(self):
        examples={"AM":["0001","0601"],"GE":["0100","0160"],
                  "AZ":["AZ1000","AZ7001"],"IL":["9414219","7178437"],
                  "JO":["11937","11118"]}
        for cc,codes in examples.items():
            for code in codes:
                item=m.postcode_format(cc,code)
                self.assertEqual(item["status"],"format_only")
                self.assertEqual(item["code"],code)
                self.assertFalse(item["postcode_assigned_verified"])
        self.assertEqual(m.postcode_format("AZ","az1000")["code"],"AZ1000")
        for cc,bad in (("AM","001"),("GE","01AB"),("AZ","1000"),
                       ("IL","94142"),("JO","119370"),("JO","１１９３７")):
            self.assertEqual(m.postcode_format(cc,bad)["status"],"invalid_format")
        with self.assertRaises(ValueError):
            m.postcode_format("AZ","AZ1000\u202e")

    def test_government_names_only_generate_unreviewed_candidates(self):
        for cc,report in self.reports.items():
            self.assertEqual(report["official_admin_names"],
                             sum(report[key] for key in ("admin_unique_candidates_unreviewed",
                                 "admin_ambiguous_candidates_unreviewed","admin_names_unmatched")))
            for rec in report["government_admin_records"]:
                self.assertFalse(rec["government_identity_verified"])
                self.assertFalse(rec["postal_assignment_verified"])
                self.assertTrue(all(x.startswith("gn:") for x in rec["geonames_candidate_ids"]))
        self.assertGreaterEqual(self.reports["AM"]["admin_unique_candidates_unreviewed"],8)
        self.assertEqual(self.reports["JO"]["geonames_adm1_rows"],12)
        self.assertEqual(self.reports["GE"]["geonames_adm1_rows"],12)

    def test_israel_six_cbs_districts_not_auto_merge_geonames_special_seventh(self):
        result=self.reports["IL"]
        self.assertEqual(result["official_admin_names"],6)
        self.assertEqual(result["geonames_adm1_rows"],7)
        records=result["government_admin_records"]
        self.assertTrue(all(not any(gid=="gn:11821181" for gid in row["geonames_candidate_ids"]) for row in records))

    def test_azerbaijan_nakhchivan_office_not_implied_locality_postcode(self):
        rows=self.reports["AZ"]["published_postal_records"]
        self.assertEqual(len([r for r in rows if r["code"].startswith("AZ70")]),11)
        for row in rows:
            self.assertIn(row["source_grain"],{"post_office_branch","operator_contact_example",
                                              "home_address_example","rural_home_address_example"})
            self.assertFalse(row["postal_assignment_to_geonames_verified"])

    def test_armenian_multiple_post_offices_do_not_mean_city_has_single_postcode(self):
        records=self.reports["AM"]["published_postal_records"]
        codes={r["code"] for r in records if r["name"]=="Yerevan"}
        self.assertIn("0001",codes)
        self.assertIn("0014",codes)
        self.assertGreaterEqual(len(codes),10)
        self.assertFalse(any(row["building_address_verified"] for row in records))

    def test_multilingual_separation(self):
        from addressing import WesternAsiaRegistry
        reg=WesternAsiaRegistry()
        self.assertEqual(set(reg.get("IL")["native_languages"]),{"he-Hebr","ar"})
        self.assertEqual(reg.get("GE")["native_scripts"]["ka-Geor"],"Geor")
        self.assertEqual(reg.get("AM")["native_scripts"]["hy-Armn"],"Armn")
        self.assertEqual(reg.get("AZ")["native_scripts"]["az-Latn"],"Latn")

    def test_zip_input_cannot_claim_empty_bulk_license_or_verified_ids(self):
        self.assertFalse(self.sources["quality_flags"]["national_postcode_coverage_verified"])
        self.assertEqual(self.sources["official_original_source_datasets_imported"],0)
        for cc in m.COUNTRIES:
            r=self.reports[cc]
            self.assertEqual(r["approved_admin_geonames_identity_links"],0)
            self.assertEqual(r["approved_postal_geonames_identity_links"],0)
            self.assertFalse(r["delivery_verified"])
            for row in r["published_postal_records"]:
                self.assertFalse(row["carrier_deliverability_verified"])
                self.assertTrue(all(g.startswith("gn:") for g in row["candidate_geonames_ids"]))
        print("CAUCASUS_LEVANT_SOURCE_JOIN_SUMMARY "+json.dumps(
            {cc:{k:v for k,v in self.reports[cc].items() if k in (
               "official_admin_names","admin_unique_candidates_unreviewed","admin_names_unmatched",
               "published_postal_source_rows","postal_unique_candidates_unreviewed",
               "postal_ambiguous_candidates_unreviewed","postal_unmatched",
               "geonames_localities_without_adm1")} for cc in m.COUNTRIES},sort_keys=True))

    def test_unknown_postcode_is_not_invalid_by_absence_from_small_excerpt(self):
        result=self.reports["JO"]
        self.assertLess(result["distinct_published_codes"],10)
        self.assertEqual(m.postcode_format("JO","11932")["status"],"format_only")
        self.assertFalse(result["delivery_verified"])

    def test_candidate_never_auto_approved_when_name_unique(self):
        admin_fixture=[{"kind":"admin_subdivision","admin_level":"1","feature_code":"ADM1",
                        "name":"Same","asciiname":"Same","alternatenames":"","id":"gn:1"},
                       {"kind":"admin_subdivision","admin_level":"1","feature_code":"ADM1",
                        "name":"Same","asciiname":"Same","alternatenames":"","id":"gn:2"}]
        fixture=json.loads(json.dumps(self.sources))
        fixture["country_administrations"]["AM"]["records"]=[
            {"source_key":"AM:test","name":"Same","aliases":[],
             "legally_equivalent_to_geonames_verified":False}]
        got=m.compare_admin("AM",admin_fixture,fixture)[0]
        self.assertEqual(got["status"],"ambiguous_candidates")
        self.assertFalse(got["government_identity_verified"])

if __name__=="__main__":unittest.main()
