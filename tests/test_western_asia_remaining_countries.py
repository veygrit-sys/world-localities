"""Four remaining western-Asia country rule and source-evidence regression tests."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import western_asia_remaining_countries as w

class CountryReferences(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source=w.source_inventory()
        cls.results={cc:w.report_country(cc) for cc in w.SCOPE}

    def test_four_governorate_references_and_source_links(self):
        expected={"LB":8,"IQ":19,"SY":14,"YE":22}
        self.assertEqual({cc:len(self.source["countries"][cc]["admin1"]) for cc in w.SCOPE},expected)
        self.assertEqual({cc:self.results[cc]["source_admin1_labels"] for cc in w.SCOPE},expected)
        self.assertEqual(sum(expected.values()),63)
        self.assertTrue(all(x["sources"] for x in self.source["countries"].values()) is False
                        if False else all(self.source["sources"][c] for c in w.SCOPE))

    def test_archived_geonames_snapshot_integrity(self):
        archive=json.loads((ROOT/"registries/asia/archives.json").read_text())
        by_country={x["country"]:x for x in archive["archives"]}
        for cc in w.SCOPE:
            report=self.results[cc]
            self.assertEqual(report["gazetteer_rows"],by_country[cc]["rows"])
            self.assertEqual(report["source_snapshot_sha256"],by_country[cc]["sha256"])
            self.assertGreater(report["gazetteer_rows"],1000)
            self.assertGreaterEqual(report["admin_unique_unreviewed"],0)

    def test_iraq_2025_halabja_new_admin_not_in_old_upu_governorate(self):
        row=self.results["IQ"]["halabja_admin_2025"]
        self.assertEqual(row["official_or_source_name"],"Halabja")
        self.assertEqual(row["effective_from"],"2025-05-05")
        self.assertFalse(row["government_to_geonames_identity_verified"])
        self.assertFalse(row["postal_association_verified"])
        self.assertEqual(self.results["IQ"]["source_admin1_labels"],19)

    def test_yemen_22_subdivision_codes_not_postcodes(self):
        ref=self.source["countries"]["YE"]["admin1"]
        self.assertEqual(len({x["unlocode_subdivision_code"] for x in ref}),22)
        self.assertTrue(all(x["not_a_postal_code"] for x in ref))
        self.assertNotEqual(next(x for x in ref if x["display_en"]=="Sana'a City")["id"],
                            next(x for x in ref if x["display_en"]=="Sanaa Governorate")["id"])

    def test_lebanon_home_and_po_box_without_synthetic_national_postcode(self):
        home=w.postcode_format("LB",None,locality="Beirut",district="Beirut")
        self.assertIn(home["status"],("format_unverified","format_only"))
        box=w.postcode_format("LB",None,locality="Beirut",delivery_mode="po_box",po_box="11-5544")
        self.assertNotIn("postcode",box["normalized"])
        self.assertEqual(box["normalized"]["po_box"],"11-5544")
        self.assertEqual(w.postcode_format("LB","12345")["status"],"invalid_format")

    def test_iraq_five_digit_postcode_preserves_string_and_gaps(self):
        result=w.postcode_format("IQ","05401",locality="Najaf")
        self.assertEqual(result["status"],"format_only")
        self.assertEqual(result["normalized"]["postcode"],"05401")
        self.assertEqual(w.postcode_format("IQ","5401")["status"],"invalid_format")
        self.assertEqual(w.postcode_format("IQ","５４００１")["status"],"invalid_format")
        self.assertEqual(w.postcode_format("IQ",None)["status"],"format_unverified")

    def test_syria_and_yemen_humanitarian_pcode_is_not_postcode(self):
        for cc in ("SY","YE"):
            row=w.postcode_format(cc,None,locality="Test",humanitarian_pcode="X123")
            self.assertNotIn("postcode",row["normalized"])
            self.assertEqual(row["status"],"format_unverified")
            self.assertIn("humanitarian_pcode_not_a_postcode",row["warnings"])
            self.assertEqual(w.postcode_format(cc,"00000")["status"],"invalid_format")
            self.assertIn("synthetic_placeholder_is_not_a_postcode",
                          w.postcode_format(cc,"00000")["warnings"])

    def test_iraqi_post_source_examples_are_only_source_office_rows(self):
        records=self.source["postal_evidence"]
        self.assertEqual(len(records),9)
        self.assertEqual({r["country"] for r in records},{"IQ"})
        self.assertTrue(all(len(r["code"])==5 and r["geonames_identity_verified"] is False
                            for r in records))
        self.assertEqual(self.results["IQ"]["authenticated_postcode_to_geonames_links"],0)

    def test_invalid_bidirectional_controls_and_delivery_mode(self):
        with self.assertRaises(ValueError):
            w.postcode_format("SY",None,locality="دمشق\u202e")
        with self.assertRaises(ValueError):
            w.postcode_format("IQ","54001",delivery_mode="unknown")
        with self.assertRaises(ValueError):
            w.postcode_format("ZZ",None)

    def test_syria_7953_source_items_have_complete_hierarchies_and_languages(self):
        sy=w.verify_syria_source()
        self.assertEqual(tuple(sy[key] for key in ("source_gov","source_districts",
                         "source_subdistricts","source_localities")),(14,62,272,7605))
        self.assertEqual(sy["native_english_pairs_count"],7605)
        self.assertEqual(len(sy["locality_rows_by_governorate"]),14)
        self.assertFalse(sy["humanitarian_pcodes_are_postal_codes"])
        self.assertFalse(sy["countrywide_postal_delivery_verified"])

    def test_no_false_completeness_claims(self):
        for cc in w.SCOPE:
            r=self.results[cc]
            self.assertFalse(r["official_nationwide_postcode_table_imported"])
            self.assertEqual(r["authenticated_postcode_to_geonames_links"],0)
            self.assertEqual(r["government_admin_to_geonames_links_verified"],0)
            self.assertFalse(r["carrier_deliverability_verified"])
            for g in r["admin_candidate_records"]:
                self.assertFalse(g["government_to_geonames_identity_verified"])
        print("WESTERN_ASIA_FINAL_FOUR_AUDIT "+json.dumps(
            {cc:{key:self.results[cc][key] for key in (
             "source_admin1_labels","geonames_adm1_rows",
             "admin_unique_unreviewed","admin_ambiguous_unreviewed",
             "admin_unmatched","gazetteer_localities_without_adm1")}
             for cc in w.SCOPE},ensure_ascii=False,sort_keys=True))


if __name__=="__main__":unittest.main()
