"""Domestic-language, English and postcode tests for Southern Africa."""

import csv
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    MissingLocalizedComponents,
    ProfileRegistry,
    SouthernAfricaRegistry,
    render_southern_africa_address,
)


EXPECTED_PROFILES = {
    "BW": ({"en": "BW_en", "tn-Latn": "BW_tn"}, "BW_en"),
    "LS": ({"st-Latn": "LS_st", "en": "LS_en"}, "LS_en"),
    "NA": (
        {
            "en": "NA_en",
            "af-Latn": "NA_af",
            "de-Latn": "NA_de",
            "ng-Latn": "NA_ng",
            "kj-Latn": "NA_kj",
        },
        "NA_en",
    ),
    "SZ": ({"ss-Latn": "SZ_ss", "en": "SZ_en"}, "SZ_en"),
    "ZA": (
        {
            "en": "ZA_en",
            "af-Latn": "ZA_af",
            "nr-Latn": "ZA_nr",
            "xh-Latn": "ZA_xh",
            "zu-Latn": "ZA_zu",
            "nso-Latn": "ZA_nso",
            "st-Latn": "ZA_st",
            "tn-Latn": "ZA_tn",
            "ss-Latn": "ZA_ss",
            "ve-Latn": "ZA_ve",
            "ts-Latn": "ZA_ts",
        },
        "ZA_en",
    ),
}


def coverage_rows(relative_path: str) -> dict[str, dict[str, str]]:
    with (ROOT / relative_path).open(encoding="utf-8", newline="") as source:
        return {row["country"]: row for row in csv.DictReader(source)}


class SouthernAfricaProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.southern_africa = SouthernAfricaRegistry()

    def test_all_five_m49_countries_have_domestic_and_english_profiles(self):
        self.assertEqual(set(self.southern_africa.countries), set(EXPECTED_PROFILES))
        for country, (native_profiles, english_profile) in EXPECTED_PROFILES.items():
            with self.subTest(country=country):
                policy = self.southern_africa.get(country)
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

    def test_report_exposes_dated_public_sheet_risk(self):
        self.assertEqual(
            self.southern_africa.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-17",
                "countries": 5,
                "native_language_variants": 22,
                "english_profiles": 5,
                "provisional_countries": ["BW", "LS", "NA", "SZ", "ZA"],
            },
        )

    def test_every_country_has_postcode_script_source_and_romanization_policy(self):
        for country, policy in self.southern_africa.countries.items():
            with self.subTest(country=country):
                self.assertIn("postcode_pattern", policy)
                self.assertIsInstance(policy["postcode_required"], bool)
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertTrue(policy["romanization_policy"])
                self.assertTrue(policy["sources"])

    def test_south_african_sign_language_is_documented_not_serialized_as_text(self):
        policy = self.southern_africa.get("ZA")
        self.assertIn("South African Sign Language", policy["non_text_official_language_policy"])
        self.assertNotIn("sfs", policy["native_languages"])

    def test_all_locality_rows_are_materialized_and_match_upstream(self):
        linkage = self.southern_africa.locality_registry
        materialized = coverage_rows(linkage["materialized_scope_file"])
        upstream = coverage_rows(linkage["upstream_scope_file"])
        countries = set(EXPECTED_PROFILES)

        self.assertEqual(set(linkage["materialized_countries"]), countries)
        self.assertEqual(linkage["upstream_only_countries"], [])
        self.assertEqual(
            sum(int(materialized[country]["locality_rows"]) for country in countries),
            linkage["materialized_locality_rows"],
        )
        self.assertEqual(linkage["materialized_locality_rows"], 19365)
        self.assertEqual(
            sum(int(upstream[country]["locality_rows"]) for country in countries),
            linkage["upstream_locality_rows"],
        )
        self.assertEqual(linkage["upstream_locality_rows"], 19365)
        for country in countries:
            self.assertTrue((ROOT / linkage["country_directory"] / country).is_dir())

    def test_country_outside_region_is_rejected(self):
        with self.assertRaisesRegex(KeyError, "outside Southern Africa"):
            self.southern_africa.get("ZW")


class SouthernAfricaPostcodePolicies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.southern_africa = SouthernAfricaRegistry()

    def test_current_country_specific_postcode_syntax_is_accepted(self):
        valid = {"LS": "100", "NA": "12056", "SZ": "H100", "ZA": "0002"}
        for country, postcode in valid.items():
            with self.subTest(country=country):
                self.assertTrue(
                    self.southern_africa.validate_postcode(country, postcode)
                )
        self.assertTrue(self.southern_africa.validate_postcode("SZ", "h100"))

    def test_wrong_lengths_and_forms_are_rejected(self):
        invalid = {"LS": "1000", "NA": "1205", "SZ": "1000", "ZA": "79750"}
        for country, postcode in invalid.items():
            with self.subTest(country=country):
                self.assertFalse(
                    self.southern_africa.validate_postcode(country, postcode)
                )

    def test_botswana_rejects_placeholder_and_coded_countries_require_values(self):
        self.assertTrue(self.southern_africa.validate_postcode("BW", None))
        self.assertFalse(self.southern_africa.validate_postcode("BW", "0000"))
        for country in ("LS", "NA", "SZ", "ZA"):
            with self.subTest(country=country):
                self.assertFalse(self.southern_africa.validate_postcode(country, None))


class SouthernAfricaAddressRendering(unittest.TestCase):
    def test_botswana_private_bag_has_no_synthesized_postcode(self):
        result = render_southern_africa_address(
            {
                "country_code": "BW",
                "po_box": {"en": "Private Bag 1061"},
                "city": {"en": "GABORONE"},
            },
            "BW",
        )
        self.assertIn("Private Bag 1061", result.native.lines)
        self.assertNotIn("postcode", result.native.components)
        self.assertIn("provisional_country_profile", result.warnings)

    def test_lesotho_keeps_address2_street_and_three_digit_code(self):
        result = render_southern_africa_address(
            {
                "country_code": "LS",
                "address2": {"st-Latn": "Ntlo B, phaposi 4", "en": "Building B, Room 4"},
                "road": {"st-Latn": "Kingsway", "en": "Kingsway"},
                "house_number": "12",
                "city": {"st-Latn": "MASERU", "en": "MASERU"},
                "postcode": "100",
            },
            "LS",
        )
        self.assertIn("Ntlo B, phaposi 4", result.native.lines)
        self.assertIn("12 Kingsway", result.native.lines)
        self.assertIn("MASERU 100", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_namibia_keeps_multi_unit_and_postcode_on_own_line(self):
        result = render_southern_africa_address(
            {
                "country_code": "NA",
                "address2": {"af-Latn": "Eenheid 4, Blok B", "en": "Unit 4, Block B"},
                "road": {"af-Latn": "Frankie Fredericksstraat", "en": "Frankie Fredericks Street"},
                "house_number": "289",
                "neighbourhood": {"af-Latn": "OLYMPIA", "en": "OLYMPIA"},
                "postal_city": {"af-Latn": "WINDHOEK", "en": "WINDHOEK"},
                "postcode": "12056",
            },
            "NA",
            native_language="af-Latn",
        )
        self.assertEqual(result.native.profile_key, "NA_af")
        self.assertIn("Eenheid 4, Blok B", result.native.lines)
        self.assertIn("289 Frankie Fredericksstraat", result.native.lines)
        self.assertIn("12056", result.native.lines)
        self.assertNotIn("12056 WINDHOEK", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_namibia_rural_delivery_point_and_village_are_retained(self):
        result = render_southern_africa_address(
            {
                "country_code": "NA",
                "road": {"ng-Latn": "Onyaanya Communal Area", "en": "Onyaanya Communal Area"},
                "house_number": "300181",
                "village": {"ng-Latn": "Ondjamba", "en": "Ondjamba"},
                "postal_city": {"ng-Latn": "ONDANGWA", "en": "ONDANGWA"},
                "postcode": "15006",
            },
            "NA",
            native_language="ng-Latn",
        )
        self.assertIn("300181 Onyaanya Communal Area", result.native.lines)
        self.assertIn("Ondjamba", result.native.lines)
        self.assertIn("15006", result.native.lines)

    def test_eswatini_po_box_keeps_code_below_locality(self):
        result = render_southern_africa_address(
            {
                "country_code": "SZ",
                "po_box": {"ss-Latn": "P.O. Box 125", "en": "P.O. Box 125"},
                "city": {"ss-Latn": "MBABANE", "en": "MBABANE"},
                "postcode": "H100",
            },
            "SZ",
        )
        self.assertLess(result.native.lines.index("MBABANE"), result.native.lines.index("H100"))
        self.assertIn("eSwatini", result.native.lines)

    def test_south_africa_complex_address_keeps_address2_and_omits_province(self):
        result = render_southern_africa_address(
            {
                "country_code": "ZA",
                "address2": {"zu-Latn": "1023 Collet Heights", "en": "1023 Collet Heights"},
                "road": {"zu-Latn": "Collet Drive", "en": "Collet Drive"},
                "house_number": "449",
                "postal_city": {"zu-Latn": "LYNDHURST", "en": "LYNDHURST"},
                "postcode": "1852",
            },
            "ZA",
            native_language="zu-Latn",
        )
        self.assertEqual(result.native.profile_key, "ZA_zu")
        self.assertIn("1023 Collet Heights", result.native.lines)
        self.assertIn("449 Collet Drive", result.native.lines)
        self.assertIn("1852", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_south_africa_all_written_official_languages_are_selectable(self):
        registry = SouthernAfricaRegistry()
        for language, expected_profile in EXPECTED_PROFILES["ZA"][0].items():
            with self.subTest(language=language):
                result = render_southern_africa_address(
                    {"country_code": "ZA"},
                    "ZA",
                    native_language=language,
                )
                self.assertEqual(result.native.profile_key, expected_profile)
                self.assertEqual(result.native_language, language)
                self.assertIn(
                    registry.get("ZA")["country_names"][language],
                    result.native.lines,
                )

    def test_same_latin_script_does_not_fill_missing_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_southern_africa_address(
                {
                    "country_code": "BW",
                    "po_box": {"tn-Latn": "Private Bag 1"},
                    "city": {"tn-Latn": "GABORONE"},
                },
                "BW",
                native_language="tn-Latn",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "po_box"))


if __name__ == "__main__":
    unittest.main()
