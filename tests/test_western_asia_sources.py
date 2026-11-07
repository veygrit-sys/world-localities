"""Real-source replay, source-grain safety and index corruption regression tests."""
import copy
import gzip
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import western_asia_sources as wa


class PublishedSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = wa.load_manifest()
        cls.specs = {s["id"]: s for s in cls.manifest["sources"]}
        cls.result = wa.verify_sources()

    def rows(self, source):
        return list(wa.normalized(self.specs[source]))

    def test_all_eighteen_countries_have_actual_pinned_source_rows(self):
        self.assertEqual({s["country"] for s in self.manifest["sources"]}, set(wa.COUNTRIES))
        self.assertEqual(self.result["status"], "passed")
        self.assertTrue(self.result["source_originals_replayed"])
        self.assertGreater(self.result["records"], 70_000)

    def test_country_verification_reads_only_selected_source_payloads(self):
        with patch.object(wa, "read_pinned", wraps=wa.read_pinned) as read:
            result = wa.verify_sources(country="JO")
        self.assertEqual(result["records"], 240)
        self.assertEqual({s["country"] for s in result["sources"]}, {"JO"})
        self.assertTrue(all("JO-" in call.args[1]["path"] for call in read.call_args_list))

    def test_common_country_entry_exposes_source_counts(self):
        from localities.country import inspect_country
        result = inspect_country("JO")
        layer = next(s for s in result["layers"] if s["id"] == "western-asia-source-snapshots")
        self.assertEqual(layer["counts"]["source_records"], 240)
        self.assertFalse(layer["national_completeness_verified"])

    def test_country_restore_keeps_other_countries_originals_out(self):
        from localities.country import restore_country
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "jordan"
            result = restore_country("JO", output)
            self.assertEqual(result["status"], "passed")
            base = output / "registries/official/western-asia/imports"
            self.assertTrue((base / "originals/JO-offices-corrected.raw.gz").is_file())
            self.assertFalse((base / "originals/CY-directory.xlsx").exists())
            self.assertFalse((base / "records/CY-POST-DIRECTORY-2024.jsonl.gz").exists())

    def test_qatar_xlsx_indentation_does_not_corrupt_codes_or_language_keys(self):
        rows = self.rows("QA-OCHA-COD-20261108")
        doha = next(r for r in rows if r["source_code"] == "QAT006" and r["grain"] == "admin1")
        self.assertEqual(doha["names"]["en"], "Doha Municipality")
        self.assertIn("ar", doha["names"])
        self.assertTrue(all(not r["postcode"] for r in rows))
        self.assertTrue(all(r["code_scheme"] == "humanitarian_pcode_not_postcode" for r in rows))

    def test_jordan_real_directory_has_two_distinct_offices_for_11190(self):
        rows = self.rows("JO-POST-OFFICES-2023-1661")
        offices = [r for r in rows if r["postcode"] == "11190"]
        self.assertGreaterEqual(len(offices), 2)
        self.assertGreaterEqual(len({r["names"]["ar"] for r in offices}), 2)
        self.assertTrue(all(r["grain"] == "post_office" for r in rows))

    def test_jordan_services_file_is_rejected_as_postcode_directory(self):
        spec = self.specs["JO-POST-OFFICES-2023-1661"]
        with self.assertRaisesRegex(ValueError, "not the postcode-bearing"):
            list(wa.parse_jo_offices(spec, "الخدمات البريدية,معلومات\n1,البريد المسجل\n".encode()))

    def test_israel_api_capture_must_contain_every_reported_record(self):
        spec = self.specs["IL-PIBA-LOCALITIES-20261108"]
        capture = json.loads(wa.read_pinned(wa.DATA, spec["original"]))
        capture["result"]["records"].pop()
        with self.assertRaisesRegex(ValueError, "truncated"):
            list(wa.parse_il_cities(spec, wa.canonical(capture)))

    def test_cyprus_pobox_and_street_records_remain_separate(self):
        rows = self.rows("CY-POST-DIRECTORY-2024")
        self.assertIn("po_box", {r["grain"] for r in rows})
        self.assertIn("street", {r["grain"] for r in rows})
        boxes = [r for r in rows if r["grain"] == "po_box"]
        self.assertGreater(len(boxes), 30_000)
        self.assertTrue(all(r["postal_kind"] == "po_box" for r in boxes))
        self.assertTrue(any(r["grain"] == "post_office" for r in rows))
        self.assertTrue(any(r["grain"] == "parcel_locker" for r in rows))

    def test_geostat_footnotes_are_not_places_or_current_identity_claims(self):
        rows = self.rows("GE-CITIES-2026")
        self.assertFalse(any(r["names"]["en"].startswith("Note:") for r in rows))
        self.assertTrue(any(r.get("latest_year_with_value") == 2026 for r in rows))
        self.assertTrue(all(not r["source_code"] for r in rows))

    def test_bahrain_historic_central_governorate_is_not_promoted_to_current(self):
        rows = self.rows("BH-IGA-GOVERNORATE-AREA-2024")
        current = [r for r in rows if r["latest_period_governorate"]]
        self.assertEqual(len(current), 4)
        self.assertNotIn("Central", {r["names"]["en"] for r in current})
        self.assertTrue(any(r["names"]["en"] == "Central" for r in rows))

    def test_lebanon_conflict_parent_is_preserved_without_fabricating_a_code(self):
        rows = self.rows("LB-ATLAS-ADM3-20261108")
        conflicts = [r for r in rows if r["parents"].get("admin1") == "Conflict"]
        self.assertTrue(conflicts)
        self.assertTrue(all(not r["government_geonames_identity_verified"] for r in conflicts))

    def test_iraq_historic_table_is_explicitly_not_current_nineteen_governorates(self):
        rows = self.rows("IQ-OCHA-COD-20261108")
        self.assertEqual(sum(r["grain"] == "admin1" for r in rows), 18)
        self.assertFalse(self.manifest["national_completeness_verified"])


class IdentityBoundaries(unittest.TestCase):
    def setUp(self):
        self.rows = [dict(id="gn:1", name="Example", asciiname="Example", alternatenames="",
                          kind="locality", feature_code="PPL", address_candidate="1", state_id=""),
                     dict(id="gn:2", name="Example", asciiname="Example", alternatenames="",
                          kind="locality", feature_code="PPL", address_candidate="1", state_id="")]
        self.index = wa.CandidateIndex(self.rows)

    def test_ambiguous_names_never_become_verified_ids(self):
        r = self.index.match(dict(grain="locality", names={"en": "Example"}))
        self.assertEqual(r["status"], "ambiguous_unreviewed")
        self.assertEqual(r["candidate_geonames_ids"], ["gn:1", "gn:2"])
        self.assertFalse(r["government_identity_verified"])

    def test_post_office_name_is_not_identified_with_a_locality(self):
        r = self.index.match(dict(grain="post_office", names={"en": "Example"}))
        self.assertEqual(r["status"], "different_grain")
        self.assertEqual(r["candidate_geonames_ids"], [])

    def test_admin_level_must_match(self):
        r = self.index.match(dict(grain="admin2", names={"en": "Example"}))
        self.assertEqual(r["status"], "grain_unavailable_in_gazetteer")

    def test_paths_cannot_escape_source_registry(self):
        with self.assertRaises(ValueError):
            wa.safe_path(wa.DATA, "../README.md")
        with self.assertRaises(ValueError):
            wa.safe_path(wa.DATA, "/etc/passwd")

    def test_original_hash_failure_prevents_source_parsing(self):
        source = wa.load_manifest()["sources"][0]
        bad = copy.deepcopy(source["original"])
        bad["original_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Original source checksum"):
            wa.read_pinned(wa.DATA, bad)


class IndexCorruption(unittest.TestCase):
    def test_lookup_postcode_tampering_is_detected_even_if_payload_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            r = wa.source_record({"id": "JO-TEST", "country": "JO"}, "1", "post_office",
                                 names={"ar": "مكتب"}, postcode="11118", postal_kind="post_office")
            spec = dict(id="JO-TEST", country="JO", parser="jo_offices", url="https://example.test/data",
                        rights={"test": True}, normalized=wa.write_records(base / "records/test.gz", [r]))
            (base / "manifest.json").write_text(json.dumps(dict(schema_version=1, country_scope=["JO"], sources=[spec])))
            geo = dict(id="gn:1", kind="locality", name="Amman", asciiname="Amman", alternatenames="",
                       state_id="", country_code="JO")
            db = base / "index.sqlite"
            with patch.object(wa, "COUNTRIES", ("JO",)), patch.object(wa, "gazetteer", return_value=([geo], {})):
                wa.build_index(db, base)
                self.assertEqual(wa.verify_index(db, base)["status"], "passed")
                with sqlite3.connect(db) as conn:
                    conn.execute("UPDATE source_records SET postcode='99999'")
                with self.assertRaisesRegex(ValueError, "Source index differs"):
                    wa.verify_index(db, base)


if __name__ == "__main__":
    unittest.main()
