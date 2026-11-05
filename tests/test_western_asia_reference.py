"""Regression checks for nine source-aware reference policies."""
from pathlib import Path
import json
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing.western_asia_reference import (
    COUNTRIES, inspect_western_asia_reference, reference_rules,
    validate_western_asia_reference as check,
)


class ReferenceInventoryTests(unittest.TestCase):
    def test_nine_countries_have_sources_without_false_completeness(self):
        self.assertEqual(COUNTRIES, {"TR", "CY", "KW", "AE", "SA", "BH", "QA", "OM", "PS"})
        self.assertEqual(set(reference_rules()["countries"]), COUNTRIES)
        for cc in COUNTRIES:
            record = inspect_western_asia_reference(cc)
            self.assertEqual(record["verified_postcode_records"], 0)
            self.assertFalse(record["national_completeness_verified"])
            self.assertFalse(record["deliverability_verified"])
            self.assertTrue(record["sources"])

    def test_manifest_has_no_unlicensed_bulk_import(self):
        for spec in reference_rules()["countries"].values():
            self.assertTrue(all(s["url"].startswith("https://") for s in spec["sources"]))
        self.assertEqual(next(s for s in reference_rules()["countries"]["CY"]["sources"]
                              if s["id"] == "CY-POST-DIRECTORY")["reuse"],
                         "CC-BY-4.0_dataset_not_imported")


class CountryReferenceTests(unittest.TestCase):
    def test_turkiye_preserves_zero_and_special_suffix(self):
        normal = check("TR", postcode="06101")
        self.assertEqual(normal["status"], "format_only")
        self.assertEqual(normal["normalized"]["postcode"], "06101")
        suffix = check("TR", postcode="06050-01")
        self.assertEqual(suffix["normalized"]["postcode_base"], "06050")
        self.assertEqual(suffix["normalized"]["postcode_sublocality_suffix"], "01")
        self.assertFalse(suffix["checks"]["postcode_assignment_verified"])

    def test_turkiye_invalid_and_missing(self):
        self.assertEqual(check("TR", postcode="611")["status"], "invalid_format")
        self.assertEqual(check("TR")["status"], "incomplete")
        self.assertEqual(check("TR", postcode="۰۶۱۰۱")["status"], "invalid_format")

    def test_cyprus_inbound_and_domestic_prefix(self):
        self.assertEqual(check("CY", postcode="2008", direction="inbound")["normalized"]["postcode"], "CY-2008")
        self.assertEqual(check("CY", postcode="CY-2008")["normalized"]["postcode"], "2008")
        self.assertEqual(check("CY", postcode="cy 2008", direction="inbound")["normalized"]["postcode"], "CY-2008")
        self.assertEqual(check("CY", postcode="CY-2008", direction="inbound")["status"], "format_only")
        self.assertEqual(check("CY", postcode="20089")["status"], "invalid_format")

    def test_cyprus_has_two_distinct_languages_in_existing_registry(self):
        from addressing import WesternAsiaRegistry
        cy = WesternAsiaRegistry().get("CY")
        self.assertEqual(set(cy["native_languages"]), {"el-Grek", "tr-Latn"})

    def test_kuwait_po_box_and_home_are_not_assumed_equivalent(self):
        home = check("KW", postcode="54404", block="4")
        po = check("KW", postcode="54551", delivery_mode="po_box", po_box="48001")
        self.assertEqual(home["status"], "format_only")
        self.assertEqual(po["status"], "format_only")
        self.assertEqual(home["normalized"]["block"], "4")
        self.assertEqual(po["normalized"]["po_box"], "48001")
        self.assertFalse(po["checks"]["postcode_assignment_verified"])

    def test_kuwait_missing_po_box_is_incomplete(self):
        self.assertEqual(check("KW", postcode="54551", delivery_mode="po_box")["status"], "incomplete")
        self.assertEqual(check("KW", postcode="123456")["status"], "invalid_format")

    def test_uae_no_fabricated_national_postcode(self):
        value = check("AE", emirate="AE-DU")
        self.assertEqual(value["status"], "format_only")
        self.assertNotIn("postcode", value["normalized"])
        given = check("AE", postcode="00000")
        self.assertEqual(given["status"], "format_unverified")
        self.assertFalse(given["checks"]["postcode_assignment_verified"])

    def test_makani_separate_from_postcode(self):
        r = check("AE", emirate="AE-DU", makani="30032 95320")
        self.assertEqual(r["normalized"]["makani"], "3003295320")
        self.assertNotIn("postcode", r["normalized"])
        self.assertEqual(check("AE", makani="12345")["status"], "invalid_format")
        self.assertFalse(r["checks"]["building_verified"])

    def test_onwani_not_promoted_to_national_postcode(self):
        r = check("AE", emirate="AE-AZ", onwani_postcode="23251")
        self.assertEqual(r["status"], "format_only")
        self.assertEqual(r["normalized"]["onwani_postcode"], "23251")
        self.assertNotIn("postcode", r["normalized"])
        self.assertEqual(check("AE", emirate="AE-DU", onwani_postcode="23251")["status"], "invalid_format")

    def test_refuse_cross_country_identity_and_unsafe_unicode(self):
        self.assertEqual(check("KW", postcode="54551", makani="3003295320")["status"], "invalid_format")
        with self.assertRaises(ValueError):
            check("TR", postcode="06101\u202e")
        with self.assertRaises(ValueError):
            check("XX", postcode="12345")
        with self.assertRaises(ValueError):
            check("KW", postcode="54551", direction="outbound")

    def test_no_format_check_claims_deliverability(self):
        samples = [check("TR", postcode="06101"), check("CY", postcode="2008"),
                   check("KW", postcode="54404"), check("AE", makani="3003295320")]
        for sample in samples:
            self.assertFalse(any(sample["checks"][k] for k in (
                "postcode_assignment_verified", "locality_membership_verified",
                "building_verified", "deliverability_verified")))
            self.assertIn("carrier_deliverability_not_checked", sample["warnings"])


if __name__ == "__main__":
    unittest.main()
