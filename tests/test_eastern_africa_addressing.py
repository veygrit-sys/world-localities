"""Domestic-language, English and postcode quality tests for Eastern Africa."""

import csv
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    EasternAfricaRegistry,
    MissingLocalizedComponents,
    ProfileRegistry,
    render_eastern_africa_address,
)


EXPECTED_PROFILES = {
    "BI": ({"rn-Latn": "BI_rn", "fr-Latn": "BI_fr", "en": "BI_en"}, "BI_en"),
    "DJ": ({"ar-Arab": "DJ_ar", "fr-Latn": "DJ_fr", "so-Latn": "DJ_so", "aa-Latn": "DJ_aa"}, "DJ_en"),
    "ER": ({"ti-Ethi": "ER_ti", "ar-Arab": "ER_ar", "en": "ER_en"}, "ER_en"),
    "ET": ({"am-Ethi": "ET_am", "aa-Latn": "ET_aa", "om-Latn": "ET_om", "so-Latn": "ET_so", "ti-Ethi": "ET_ti"}, "ET_en"),
    "IO": ({"en": "IO_en"}, "IO_en"),
    "KE": ({"sw-Latn": "KE_sw", "en": "KE_en"}, "KE_en"),
    "KM": ({"zdj-Latn": "KM_zdj", "ar-Arab": "KM_ar", "fr-Latn": "KM_fr"}, "KM_en"),
    "MG": ({"mg-Latn": "MG_mg", "fr-Latn": "MG_fr"}, "MG_en"),
    "MU": ({"mfe-Latn": "MU_mfe", "fr-Latn": "MU_fr", "en": "MU_en"}, "MU_en"),
    "MW": ({"ny-Latn": "MW_ny", "en": "MW_en"}, "MW_en"),
    "MZ": ({"pt-Latn": "MZ_pt"}, "MZ_en"),
    "RE": ({"rcf-Latn": "RE_rcf", "fr-Latn": "RE_fr"}, "RE_en"),
    "RW": ({"rw-Latn": "RW_rw", "en": "RW_en", "fr-Latn": "RW_fr", "sw-Latn": "RW_sw"}, "RW_en"),
    "SC": ({"crs-Latn": "SC_crs", "en": "SC_en", "fr-Latn": "SC_fr"}, "SC_en"),
    "SO": ({"so-Latn": "SO_so", "ar-Arab": "SO_ar"}, "SO_en"),
    "SS": ({"en": "SS_en"}, "SS_en"),
    "TF": ({"fr-Latn": "TF_fr"}, "TF_en"),
    "TZ": ({"sw-Latn": "TZ_sw", "en": "TZ_en"}, "TZ_en"),
    "UG": ({"en": "UG_en", "sw-Latn": "UG_sw"}, "UG_en"),
    "YT": ({"fr-Latn": "YT_fr", "swb-Latn": "YT_swb", "buc-Latn": "YT_buc"}, "YT_en"),
    "ZM": ({"en": "ZM_en"}, "ZM_en"),
    "ZW": ({"en": "ZW_en", "sn-Latn": "ZW_sn", "nd-Latn": "ZW_nd"}, "ZW_en"),
}


def coverage_rows(relative_path: str) -> dict[str, dict[str, str]]:
    with (ROOT / relative_path).open(encoding="utf-8", newline="") as source:
        return {row["country"]: row for row in csv.DictReader(source)}


class EasternAfricaProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.eastern_africa = EasternAfricaRegistry()

    def test_all_22_m49_entities_have_domestic_and_english_profiles(self):
        self.assertEqual(set(self.eastern_africa.countries), set(EXPECTED_PROFILES))
        for country, (native_profiles, english_profile) in EXPECTED_PROFILES.items():
            with self.subTest(country=country):
                policy = self.eastern_africa.get(country)
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

    def test_report_makes_evidence_gaps_visible(self):
        self.assertEqual(
            self.eastern_africa.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-17",
                "countries": 22,
                "native_language_variants": 53,
                "english_profiles": 22,
                "provisional_countries": [
                    "ER", "ET", "KM", "RW", "SC", "SO", "SS", "ZM", "ZW"
                ],
            },
        )

    def test_every_country_has_postcode_script_and_source_policy(self):
        for country, policy in self.eastern_africa.countries.items():
            with self.subTest(country=country):
                self.assertIn("postcode_pattern", policy)
                self.assertIsInstance(policy["postcode_required"], bool)
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertTrue(policy["romanization_policy"])
                self.assertTrue(policy["sources"])

    def test_existing_africa_registry_is_reused_with_madagascar_upstream_only(self):
        linkage = self.eastern_africa.locality_registry
        materialized = coverage_rows(linkage["materialized_scope_file"])
        upstream = coverage_rows(linkage["upstream_scope_file"])
        materialized_countries = set(linkage["materialized_countries"])
        all_countries = set(EXPECTED_PROFILES)

        self.assertEqual(materialized_countries, all_countries - {"MG"})
        self.assertEqual(set(linkage["upstream_only_countries"]), {"MG"})
        self.assertEqual(
            sum(int(materialized[country]["locality_rows"]) for country in materialized_countries),
            linkage["materialized_locality_rows"],
        )
        self.assertEqual(linkage["materialized_locality_rows"], 113668)
        self.assertEqual(
            sum(int(upstream[country]["locality_rows"]) for country in all_countries),
            linkage["upstream_locality_rows"],
        )
        self.assertEqual(linkage["upstream_locality_rows"], 137842)
        self.assertFalse((ROOT / linkage["country_directory"] / "MG").exists())

    def test_country_outside_region_is_rejected(self):
        with self.assertRaisesRegex(KeyError, "outside Eastern Africa"):
            self.eastern_africa.get("ZA")


class EasternAfricaPostcodePolicies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eastern_africa = EasternAfricaRegistry()

    def test_current_country_specific_syntax_is_accepted(self):
        valid = {
            "DJ": "77101",
            "ET": "1000",
            "IO": "BBND 1ZZ",
            "KE": "00100",
            "MG": "101",
            "MU": "11328",
            "MW": "102010",
            "MZ": "1100",
            "RE": "97400",
            "SC": "0000",
            "SO": "JH  09010",
            "TF": "97408",
            "TZ": "14111",
            "UG": "10000",
            "YT": "97600",
        }
        for country, postcode in valid.items():
            with self.subTest(country=country):
                self.assertTrue(self.eastern_africa.validate_postcode(country, postcode))

    def test_wrong_lengths_and_unassigned_codes_are_rejected(self):
        invalid = {
            "DJ": "7710",
            "ET": "10000",
            "IO": "BIOT 1ZZ",
            "MG": "1010",
            "MW": "10201",
            "RE": "97600",
            "SC": "1234",
            "SO": "09010",
            "TF": "97400",
            "UG": "1000",
            "YT": "97400",
            "ZM": "10101",
            "ZW": "00000",
        }
        for country, postcode in invalid.items():
            with self.subTest(country=country):
                self.assertFalse(self.eastern_africa.validate_postcode(country, postcode))

    def test_required_optional_and_no_code_absence_are_distinct(self):
        for country in ("DJ", "ET", "IO", "KE", "MG", "MU", "MW", "MZ", "RE", "SO", "TZ", "UG", "YT"):
            with self.subTest(country=country):
                self.assertFalse(self.eastern_africa.validate_postcode(country, None))
        for country in ("BI", "ER", "KM", "RW", "SC", "SS", "TF", "ZM", "ZW"):
            with self.subTest(country=country):
                self.assertTrue(self.eastern_africa.validate_postcode(country, None))


class EasternAfricaAddressRendering(unittest.TestCase):
    def test_malawi_six_digit_route_preserves_address2(self):
        result = render_eastern_africa_address(
            {
                "country_code": "MW",
                "address2": {"ny-Latn": "Chipinda 2", "en": "Unit 2"},
                "road": {"ny-Latn": "Msewu wa Mchinji", "en": "Mchinji Road"},
                "house_number": "14",
                "city": {"ny-Latn": "Lilongwe", "en": "LILONGWE"},
                "postcode": "102010",
            },
            "MW",
        )
        self.assertEqual(result.native.profile_key, "MW_ny")
        self.assertLess(
            result.native.lines.index("Chipinda 2"),
            result.native.lines.index("14 Msewu wa Mchinji"),
        )
        self.assertIn("102010 Lilongwe", result.native.lines)
        self.assertIn("102010 LILONGWE", result.english.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_uganda_2026_five_digit_route_is_before_locality(self):
        result = render_eastern_africa_address(
            {
                "country_code": "UG",
                "po_box": {"en": "P.O. Box 125", "sw-Latn": "S.L.P. 125"},
                "city": {"en": "KAMPALA", "sw-Latn": "Kampala"},
                "postcode": "10000",
            },
            "UG",
        )
        self.assertIn("10000 KAMPALA", result.native.lines)
        self.assertLess(
            result.native.lines.index("P.O. Box 125"),
            result.native.lines.index("10000 KAMPALA"),
        )

    def test_djibouti_arabic_keeps_po_box_and_postcode_route(self):
        result = render_eastern_africa_address(
            {
                "country_code": "DJ",
                "po_box": {"ar-Arab": "ص ب 100", "en": "P.O. Box 100"},
                "city": {"ar-Arab": "جيبوتي", "en": "DJIBOUTI"},
                "postcode": "77101",
            },
            "DJ",
        )
        self.assertEqual(result.native.profile_key, "DJ_ar")
        self.assertIn("77101 جيبوتي", result.native.lines)
        self.assertIn("77101 DJIBOUTI", result.english.lines)

    def test_ethiopia_checks_ethiopic_and_separates_english(self):
        result = render_eastern_africa_address(
            {
                "country_code": "ET",
                "road": {"am-Ethi": "ቦሌ መንገድ", "en": "Bole Road"},
                "house_number": "18",
                "city": {"am-Ethi": "አዲስ አበባ", "en": "ADDIS ABABA"},
                "postcode": "1000",
            },
            "ET",
        )
        self.assertIn("1000 አዲስ አበባ", result.native.lines)
        self.assertIn("1000 ADDIS ABABA", result.english.lines)
        self.assertIn("provisional_country_profile", result.warnings)

    def test_somalia_retains_region_prefixed_postcode(self):
        result = render_eastern_africa_address(
            {
                "country_code": "SO",
                "city": {"so-Latn": "Jowhar", "en": "JOWHAR"},
                "postcode": "JH 09010",
            },
            "SO",
        )
        self.assertIn("JH  09010", result.native.components["postcode"])
        self.assertIn("Jowhar, JH 09010", result.native.lines)
        self.assertIn("provisional_country_profile", result.warnings)

    def test_tanzania_rural_hierarchy_and_address2_are_not_dropped(self):
        result = render_eastern_africa_address(
            {
                "country_code": "TZ",
                "address2": {"sw-Latn": "Jengo B, Chumba 4", "en": "Building B, Room 4"},
                "village": {"sw-Latn": "Kijiji cha Mbuyuni", "en": "Mbuyuni Village"},
                "city": {"sw-Latn": "Dodoma", "en": "DODOMA"},
                "county": {"sw-Latn": "Wilaya ya Dodoma", "en": "Dodoma District"},
                "state": {"sw-Latn": "Mkoa wa Dodoma", "en": "Dodoma Region"},
                "postcode": "41101",
            },
            "TZ",
        )
        for expected in (
            "Jengo B, Chumba 4",
            "Kijiji cha Mbuyuni",
            "41101 Dodoma",
            "Wilaya ya Dodoma",
            "Mkoa wa Dodoma",
        ):
            self.assertIn(expected, result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_zambia_does_not_render_an_unassigned_example_as_postcode(self):
        registry = EasternAfricaRegistry()
        self.assertFalse(registry.validate_postcode("ZM", "10101"))
        result = render_eastern_africa_address(
            {
                "country_code": "ZM",
                "road": {"en": "Independence Avenue"},
                "house_number": "12",
                "city": {"en": "LUSAKA"},
                "postcode": "10101",
            },
            "ZM",
        )
        self.assertNotIn("10101", result.native.text)
        self.assertEqual(result.native.unrendered_components["postcode"], "10101")
        self.assertIn("provisional_country_profile", result.warnings)

    def test_seychelles_legacy_placeholder_is_explicitly_provisional(self):
        result = render_eastern_africa_address(
            {
                "country_code": "SC",
                "road": {"crs-Latn": "Lari Lendepandans", "en": "Independence Avenue"},
                "city": {"crs-Latn": "Viktorya", "en": "VICTORIA"},
                "island": {"crs-Latn": "Mae", "en": "Mahé"},
                "postcode": "0000",
            },
            "SC",
        )
        self.assertIn("0000", result.native.lines)
        self.assertIn("provisional_country_profile", result.warnings)

    def test_special_territory_routes_do_not_imply_residential_coverage(self):
        registry = EasternAfricaRegistry()
        self.assertEqual(
            registry.get("IO")["delivery_scope"],
            "special_territory_route_not_ordinary_residential_coverage",
        )
        self.assertEqual(
            registry.get("TF")["delivery_scope"],
            "institutional_or_station_route_not_ordinary_residential_coverage",
        )
        result = render_eastern_africa_address(
            {
                "country_code": "IO",
                "organization": {"en": "BFPO 485"},
                "city": {"en": "BIOT"},
                "postcode": "bbnd1zz",
            },
            "IO",
        )
        self.assertIn("BBND 1ZZ", result.native.lines)

    def test_reunion_french_route_preserves_address2(self):
        result = render_eastern_africa_address(
            {
                "country_code": "RE",
                "address2": {"fr-Latn": "Appartement 8", "en": "Apartment 8"},
                "road": {"fr-Latn": "Rue de Paris", "en": "Paris Street"},
                "house_number": "4",
                "city": {"fr-Latn": "SAINT-DENIS", "en": "SAINT-DENIS"},
                "postcode": "97400",
            },
            "RE",
            native_language="fr-Latn",
        )
        self.assertIn("Appartement 8", result.native.lines)
        self.assertIn("97400 SAINT-DENIS", result.native.lines)

    def test_latin_domestic_value_does_not_silently_fill_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_eastern_africa_address(
                {
                    "country_code": "MZ",
                    "road": {"pt-Latn": "Avenida 25 de Setembro"},
                    "city": {"pt-Latn": "MAPUTO"},
                    "postcode": "1100",
                },
                "MZ",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "road"))

    def test_bidi_controls_and_wrong_ethiopic_script_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "dangerous bidirectional control"):
            render_eastern_africa_address(
                {
                    "country_code": "DJ",
                    "city": {"ar-Arab": "جيبو\u202eتي", "en": "DJIBOUTI"},
                    "postcode": "77101",
                },
                "DJ",
            )
        with self.assertRaisesRegex(ValueError, "not Ethi-script"):
            render_eastern_africa_address(
                {
                    "country_code": "ET",
                    "road": {"am-Ethi": "Bole Road", "en": "Bole Road"},
                    "city": {"am-Ethi": "አዲስ አበባ", "en": "ADDIS ABABA"},
                    "postcode": "1000",
                },
                "ET",
            )


if __name__ == "__main__":
    unittest.main()
