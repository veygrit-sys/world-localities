"""Reproducible tests using checked-in GeoNames zip snapshots and curated official names."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import western_asia_admin_crosswalk as cross

class SourceEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = cross.load_reference()
        cls.reports = {cc: cross.report(cc, reference=cls.source) for cc in cross.COUNTRIES}

    def test_official_name_inventory_is_not_postal_snapshot(self):
        expected = {"SA":13, "BH":4, "QA":8, "OM":11, "PS":16}
        self.assertEqual({cc: len(self.source["countries"][cc]["records"]) for cc in cross.COUNTRIES}, expected)
        for cc in cross.COUNTRIES:
            r = self.reports[cc]
            self.assertEqual(r["official_names_compared"], expected[cc])
            self.assertEqual(sum(r[key] for key in ("unique_candidates_unreviewed",
                             "ambiguous_candidates_unreviewed","official_names_unmatched")), expected[cc])
            self.assertEqual(r["verified_identity_links"], 0)
            self.assertEqual(r["verified_postal_geonames_links"], 0)
            self.assertFalse(r["national_completeness_verified"])
            self.assertFalse(r["deliverability_verified"])

    def test_geo_source_counts_are_manifest_grounded(self):
        archive = json.loads((ROOT / "registries/asia/archives.json").read_text())
        reference = {x["country"]: x for x in archive["archives"]}
        for cc in cross.COUNTRIES:
            self.assertEqual(self.reports[cc]["geonames_records"], reference[cc]["rows"])
            self.assertEqual(self.reports[cc]["archive_sha256"], reference[cc]["sha256"])

    def test_palestine_adm_level_and_parent(self):
        ps = self.reports["PS"]
        self.assertEqual(len([x for x in ps["candidates"] if x["geographic_parent"]=="West Bank"]),11)
        self.assertEqual(len([x for x in ps["candidates"] if x["geographic_parent"]=="Gaza Strip"]),5)
        rows,_ = cross.load_geo("PS")
        self.assertEqual(sum(r["admin_level"]=="1" for r in rows),2)
        self.assertEqual(sum(r["admin_level"]=="2" for r in rows),16)

    def test_no_geonames_ids_changed_or_verified(self):
        for cc in cross.COUNTRIES:
            for row in self.reports[cc]["candidates"]:
                self.assertFalse(row["reviewed_identity_verified"])
                self.assertFalse(row["postal_assignment_verified"])
                self.assertTrue(all(gid.startswith("gn:") for gid in row["candidate_geonames_ids"]))
        print("OFFICIAL_ADMIN_UNMATCHED_NAMES "+json.dumps({
            cc:[x["official_name"] for x in self.reports[cc]["candidates"] if x["status"]=="unmatched"]
            for cc in cross.COUNTRIES},sort_keys=True))
        print("OFFICIAL_ADMIN_CANDIDATE_SUMMARY "+json.dumps({
            cc:{k:self.reports[cc][k] for k in ("official_names_compared","unique_candidates_unreviewed",
            "ambiguous_candidates_unreviewed","official_names_unmatched","localities_without_adm1")}
            for cc in cross.COUNTRIES},sort_keys=True))

    def test_ambiguous_names_cannot_turn_verified(self):
        fixture = json.loads(json.dumps(self.source))
        fixture["countries"]["BH"]["records"] = [{"ref":"BH:fixture","name":"Same",
                                                  "parent":"","aliases":[]}]
        geo = [
            {"name":"Same","asciiname":"Same","alternatenames":"","admin_level":"1",
             "feature_code":"ADM1","id":"gn:1","state_id":"gn:1"},
            {"name":"Same","asciiname":"Same","alternatenames":"","admin_level":"1",
             "feature_code":"ADM1","id":"gn:2","state_id":"gn:2"}
        ]
        p = cross.propose("BH",geo,fixture)[0]
        self.assertEqual(p["status"],"ambiguous_candidates")
        self.assertFalse(p["reviewed_identity_verified"])

    def test_pcbs_official_governorate_codes_from_1999_guide(self):
        ps = self.source["countries"]["PS"]
        codes = {item["governorate_code"] for item in ps["records"]}
        self.assertEqual(codes, {"01","05","10","15","20","25","30","35",
                                 "40","45","50","55","60","65","70","75"})
        self.assertEqual(ps["governorate_code_source"]["publication_year"], 1999)

    def test_pcbs_locality_code_prefix_is_not_a_postcode_or_identity_join(self):
        examples = [("010005", "01", "Jenin"),("200905", "20", "Qalqilya"),
                    ("602825", "60", "Gaza")]
        for code, prefix, gov in examples:
            result = cross.inspect_pcbs_locality_code(code, reference=self.source)
            self.assertEqual(result["status"], "known_governorate_prefix_format_only")
            self.assertEqual(result["governorate_code"], prefix)
            self.assertEqual(result["governorate_name"], gov)
            for field in ("locality_assignment_verified", "geonames_identity_verified",
                          "postal_code_verified", "deliverability_verified"):
                self.assertFalse(result[field])
        for invalid in ("P6100154", "P610", "60123", "６０２８２５", "60-2825"):
            with self.assertRaises(ValueError):
                cross.inspect_pcbs_locality_code(invalid, reference=self.source)
        unknown = cross.inspect_pcbs_locality_code("999999", reference=self.source)
        self.assertEqual(unknown["status"], "unrecognized_governorate_prefix")
        self.assertIsNone(unknown["governorate_ref"])

    def test_postal_source_must_be_pinned_and_remains_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"post.csv"
            raw=b"official_ref,scheme,code\nPS:PCBS-SURVEY-30,P3_AREA,P610\nPS:unknown,P7_POINT,P6100154\n"
            path.write_bytes(raw)
            kwargs=dict(country="PS",expected_sha256=hashlib.sha256(raw).hexdigest(),
                        source_url="https://opendata.ps/dataset/postcodes",
                        licence="CC-BY",source_version="synthetic-test",reference=self.source)
            got=cross.postal_audit(path,**kwargs)
            self.assertEqual(got["status_counts"]["admin_association_candidate"],1)
            self.assertEqual(got["status_counts"]["unresolved_admin_ref"],1)
            self.assertEqual(got["verified_postal_geonames_links"],0)
            self.assertTrue(all(item["geonames_id"] is None for item in got["outcomes"]))
            with self.assertRaises(ValueError):
                cross.postal_audit(path,**(kwargs|{"expected_sha256":"0"*64}))

if __name__ == "__main__":
    unittest.main()
