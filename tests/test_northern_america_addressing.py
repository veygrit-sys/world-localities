"""Domestic-language, English and postcode tests for Northern America."""

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    MissingLocalizedComponents,
    NorthernAmericaRegistry,
    ProfileRegistry,
    render_northern_america_address,
)


EXPECTED_PROFILES = {
    "BM": ({"en": "BM_en"}, "BM_en"),
    "CA": ({"en": "CA_en", "fr-Latn": "CA_fr"}, "CA_en"),
    "GL": ({"kl-Latn": "GL_kl", "da-Latn": "GL_da"}, "GL_en"),
    "PM": ({"fr-Latn": "PM_fr"}, "PM_en"),
    "US": ({"en": "US_en"}, "US_en"),
}


class NorthernAmericaProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.northern_america = NorthernAmericaRegistry()

    def test_all_five_m49_countries_have_domestic_and_english_profiles(self):
        self.assertEqual(set(self.northern_america.countries), set(EXPECTED_PROFILES))
        for country, (native_profiles, english_profile) in EXPECTED_PROFILES.items():
            with self.subTest(country=country):
                policy = self.northern_america.get(country)
                self.assertEqual(policy["native_profiles"], native_profiles)
                for language, profile_key in native_profiles.items():
                    self.assertEqual(
                        self.profiles.select(country, language=language).key,
                        profile_key,
                    )
                self.assertEqual(
                    self.profiles.select(country, international=True).key,
                    english_profile,
                )
                self.assertEqual(
                    self.profiles.select(country).key,
                    native_profiles[policy["default_native_language"]],
                )

    def test_report_has_seven_written_variants_and_no_provisional_route(self):
        self.assertEqual(
            self.northern_america.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-17",
                "countries": 5,
                "native_language_variants": 7,
                "english_profiles": 5,
                "provisional_countries": [],
            },
        )

    def test_every_country_has_postcode_script_and_source_policy(self):
        for country, policy in self.northern_america.countries.items():
            with self.subTest(country=country):
                self.assertIn("postcode_pattern", policy)
                self.assertIsInstance(policy["postcode_required"], bool)
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertTrue(policy["romanization_policy"])
                self.assertTrue(policy["sources"])

    def test_locality_linkage_keeps_pending_sources_explicit(self):
        linkage = self.northern_america.locality_registry
        scope = json.loads((ROOT / linkage["scope_file"]).read_text(encoding="utf-8"))
        countries = {item["country"]: item for item in scope["countries"]}

        self.assertEqual(set(countries), set(EXPECTED_PROFILES))
        self.assertEqual(set(linkage["materialized_countries"]), {"CA", "US"})
        self.assertEqual(
            set(linkage["pending_locality_source_countries"]), {"BM", "GL", "PM"}
        )
        self.assertEqual(linkage["source_locality_rows_in_m49_area"], 72567)
        self.assertEqual(
            linkage["administrative_seed_counts"], {"BM": 11, "GL": 5, "PM": 2}
        )
        self.assertEqual(countries["BM"]["status"], "pending_locality_source")
        self.assertEqual(countries["CA"]["status"], "preserved_official_snapshot")
        self.assertFalse(scope["coverage_claims"]["postal_address_verification"])
        self.assertFalse(scope["coverage_claims"]["street_and_house_number_verification"])

    def test_country_outside_region_is_rejected(self):
        with self.assertRaisesRegex(KeyError, "outside Northern America"):
            self.northern_america.get("MX")


class NorthernAmericaPostcodePolicies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.northern_america = NorthernAmericaRegistry()

    def test_current_country_specific_postcode_syntax_is_accepted(self):
        valid = {
            "BM": ("FL 07", "HM GX"),
            "CA": ("H3Z 2Y7", "k1a0b1"),
            "GL": ("3900", "3980"),
            "PM": ("97500",),
            "US": ("20500", "20260-1120"),
        }
        for country, postcodes in valid.items():
            for postcode in postcodes:
                with self.subTest(country=country, postcode=postcode):
                    self.assertTrue(
                        self.northern_america.validate_postcode(country, postcode)
                    )

    def test_wrong_country_forms_are_rejected(self):
        invalid = {
            "BM": ("FL 7", "FL 007"),
            "CA": ("D3Z 2Y7", "H3Z-2Y7"),
            "GL": ("2100", "390"),
            "PM": ("97501", "9750"),
            "US": ("2050", "202601120"),
        }
        for country, postcodes in invalid.items():
            for postcode in postcodes:
                with self.subTest(country=country, postcode=postcode):
                    self.assertFalse(
                        self.northern_america.validate_postcode(country, postcode)
                    )

    def test_all_five_routes_require_a_postcode(self):
        for country in EXPECTED_PROFILES:
            with self.subTest(country=country):
                self.assertFalse(self.northern_america.validate_postcode(country, None))

    def test_bermuda_po_box_prefix_must_match_alphabetic_postcode(self):
        validate = self.northern_america.validate_bermuda_po_box_route
        self.assertTrue(validate("HM GX", "PO Box HM 2469"))
        self.assertTrue(validate("hm gx", "P.O. BOX HM 2469"))
        self.assertFalse(validate("HM GX", "PO Box FL 2469"))
        self.assertFalse(validate("HM 12", "PO Box HM 2469"))


class NorthernAmericaAddressRendering(unittest.TestCase):
    def test_bermuda_keeps_unit_street_and_parish_postcode_line(self):
        result = render_northern_america_address(
            {
                "country_code": "BM",
                "address2": {"en": "Upper Apt 1"},
                "road": {"en": "Leafy Lane"},
                "house_number": "9",
                "city": {"en": "SMITH'S"},
                "postcode": "FL 07",
            },
            "BM",
        )
        self.assertIn("Upper Apt 1", result.native.lines)
        self.assertIn("9 Leafy Lane", result.native.lines)
        self.assertIn("SMITH'S FL 07", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_bermuda_po_box_keeps_repeated_delivery_office_prefix(self):
        result = render_northern_america_address(
            {
                "country_code": "BM",
                "po_box": {"en": "PO Box HM 2469"},
                "city": {"en": "HAMILTON"},
                "postcode": "HM GX",
            },
            "BM",
        )
        self.assertIn("PO Box HM 2469", result.native.lines)
        self.assertIn("HAMILTON HM GX", result.native.lines)

    def test_canada_french_keeps_address2_and_normalizes_province_and_postcode(self):
        result = render_northern_america_address(
            {
                "country_code": "CA",
                "address2": {
                    "fr-Latn": "SERVICE DU MARKETING",
                    "en": "MARKETING DEPARTMENT",
                },
                "road": {"fr-Latn": "RUE BEAUDRY", "en": "BEAUDRY STREET"},
                "house_number": "123 ½",
                "city": {"fr-Latn": "MONTRÉAL", "en": "MONTREAL"},
                "state": {"fr-Latn": "Québec", "en": "Quebec"},
                "postcode": "H3Z2Y7",
            },
            "CA",
            native_language="fr-Latn",
        )
        self.assertEqual(result.native.profile_key, "CA_fr")
        self.assertIn("SERVICE DU MARKETING", result.native.lines)
        self.assertIn("123 ½ RUE BEAUDRY", result.native.lines)
        self.assertIn("MONTRÉAL QC H3Z 2Y7", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_canada_rural_route_and_po_box_routes_are_preserved_separately(self):
        rural = render_northern_america_address(
            {
                "country_code": "CA",
                "road": {"en": "7TH CONCESSION"},
                "house_number": "2364",
                "place": {"en": "RR 8 MSC MILLARVILLE"},
                "city": {"en": "MILLARVILLE"},
                "state_code": "AB",
                "postcode": "T0L 1K0",
            },
            "CA",
        )
        self.assertLess(
            rural.native.lines.index("2364 7TH CONCESSION"),
            rural.native.lines.index("RR 8 MSC MILLARVILLE"),
        )
        self.assertIn("MILLARVILLE AB T0L 1K0", rural.native.lines)

        po_box = render_northern_america_address(
            {
                "country_code": "CA",
                "po_box": {"en": "PO BOX 4001 STN A"},
                "city": {"en": "VICTORIA"},
                "state_code": "BC",
                "postcode": "V8X 3X4",
            },
            "CA",
        )
        self.assertIn("PO BOX 4001 STN A", po_box.native.lines)
        self.assertIn("VICTORIA BC V8X 3X4", po_box.native.lines)

    def test_greenlandic_keeps_street_building_po_box_and_39xx_code(self):
        result = render_northern_america_address(
            {
                "country_code": "GL",
                "address2": {"kl-Latn": "B-679", "en": "Building B-679"},
                "road": {"kl-Latn": "Poul Ibsenip Aqqutaa", "en": "Poul Ibsen Street"},
                "po_box": {"kl-Latn": "Postboks 512", "en": "P.O. Box 512"},
                "city": {"kl-Latn": "Paamiut", "en": "Paamiut"},
                "postcode": "3940",
            },
            "GL",
        )
        self.assertEqual(result.native.profile_key, "GL_kl")
        self.assertIn("Poul Ibsenip Aqqutaa", result.native.lines)
        self.assertIn("B-679", result.native.lines)
        self.assertIn("Postboks 512", result.native.lines)
        self.assertIn("3940 Paamiut", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_saint_pierre_keeps_french_po_box_and_fixed_code(self):
        result = render_northern_america_address(
            {
                "country_code": "PM",
                "road": {"fr-Latn": "rue de Paris", "en": "Paris Street"},
                "house_number": "22",
                "po_box": {"fr-Latn": "B.P. 4213", "en": "P.O. Box 4213"},
                "city": {"fr-Latn": "Saint-Pierre", "en": "Saint Pierre"},
                "postcode": "97500",
            },
            "PM",
        )
        self.assertIn("22 rue de Paris", result.native.lines)
        self.assertIn("B.P. 4213", result.native.lines)
        self.assertIn("97500 Saint-Pierre", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_us_secondary_unit_and_state_code_share_standard_lines(self):
        result = render_northern_america_address(
            {
                "country_code": "US",
                "road": {"en": "L'Enfant Plaza SW"},
                "house_number": "475",
                "address2": {"en": "RM 6627"},
                "city": {"en": "WASHINGTON"},
                "state": {"en": "District of Columbia"},
                "postcode": "20260-1120",
            },
            "US",
        )
        self.assertIn("475 L'Enfant Plaza SW RM 6627", result.native.lines)
        self.assertIn("WASHINGTON, DC 20260-1120", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_us_po_box_and_rural_route_paths_remain_distinct(self):
        po_box = render_northern_america_address(
            {
                "country_code": "US",
                "po_box": {"en": "PO BOX 34"},
                "city": {"en": "DULUTH"},
                "state_code": "MN",
                "postcode": "55803-0034",
            },
            "US",
        )
        self.assertIn("PO BOX 34", po_box.native.lines)
        self.assertIn("DULUTH, MN 55803-0034", po_box.native.lines)

        rural = render_northern_america_address(
            {
                "country_code": "US",
                "place": {"en": "RR 3 BOX 9"},
                "city": {"en": "CANTON"},
                "state_code": "OH",
                "postcode": "44730-9521",
            },
            "US",
        )
        self.assertIn("RR 3 BOX 9", rural.native.lines)
        self.assertIn("CANTON, OH 44730-9521", rural.native.lines)

    def test_same_latin_script_does_not_fill_missing_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_northern_america_address(
                {
                    "country_code": "CA",
                    "road": {"fr-Latn": "RUE BEAUDRY"},
                    "house_number": "123",
                    "city": {"fr-Latn": "MONTRÉAL"},
                    "state": {"fr-Latn": "Québec"},
                    "postcode": "H3Z 2Y7",
                },
                "CA",
                native_language="fr-Latn",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "road", "state"))


if __name__ == "__main__":
    unittest.main()
