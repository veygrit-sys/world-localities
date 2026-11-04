"""Domestic-language, English and postcode quality tests for Middle Africa."""

import csv
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    MiddleAfricaRegistry,
    MissingLocalizedComponents,
    ProfileRegistry,
    render_middle_africa_address,
)


EXPECTED_PROFILES = {
    "AO": ({"pt-Latn": "AO_pt"}, "AO_en"),
    "CM": ({"fr-Latn": "CM_fr", "en": "CM_en"}, "CM_en"),
    "CF": ({"fr-Latn": "CF_fr", "sg-Latn": "CF_sg"}, "CF_en"),
    "TD": ({"ar-Arab": "TD_ar", "fr-Latn": "TD_fr"}, "TD_en"),
    "CG": (
        {"fr-Latn": "CG_fr", "ln-Latn": "CG_ln", "mkw-Latn": "CG_mkw"},
        "CG_en",
    ),
    "CD": (
        {
            "fr-Latn": "CD_fr",
            "kg-Latn": "CD_kg",
            "ln-Latn": "CD_ln",
            "sw-Latn": "CD_sw",
            "lua-Latn": "CD_lua",
        },
        "CD_en",
    ),
    "GQ": (
        {"es-Latn": "GQ_es", "fr-Latn": "GQ_fr", "pt-Latn": "GQ_pt"},
        "GQ_en",
    ),
    "GA": ({"fr-Latn": "GA_fr"}, "GA_en"),
    "ST": ({"pt-Latn": "ST_pt"}, "ST_en"),
}


def coverage_rows(relative_path: str) -> dict[str, dict[str, str]]:
    with (ROOT / relative_path).open(encoding="utf-8", newline="") as source:
        return {row["country"]: row for row in csv.DictReader(source)}


class MiddleAfricaProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.middle_africa = MiddleAfricaRegistry()

    def test_all_nine_m49_countries_have_domestic_and_english_profiles(self):
        self.assertEqual(set(self.middle_africa.countries), set(EXPECTED_PROFILES))
        for country, (native_profiles, english_profile) in EXPECTED_PROFILES.items():
            with self.subTest(country=country):
                policy = self.middle_africa.get(country)
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

    def test_report_keeps_dated_public_sheets_visible(self):
        self.assertEqual(
            self.middle_africa.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-17",
                "countries": 9,
                "native_language_variants": 20,
                "english_profiles": 9,
                "provisional_countries": ["AO", "CM", "GA", "TD"],
            },
        )

    def test_every_country_has_postcode_script_and_source_policy(self):
        for country, policy in self.middle_africa.countries.items():
            with self.subTest(country=country):
                self.assertIn("postcode_pattern", policy)
                self.assertIsInstance(policy["postcode_required"], bool)
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertTrue(policy["romanization_policy"])
                self.assertTrue(policy["sources"])

    def test_africa_registry_is_reused_with_dr_congo_upstream_only(self):
        linkage = self.middle_africa.locality_registry
        materialized = coverage_rows(linkage["materialized_scope_file"])
        upstream = coverage_rows(linkage["upstream_scope_file"])
        materialized_countries = set(linkage["materialized_countries"])
        all_countries = set(EXPECTED_PROFILES)

        self.assertEqual(materialized_countries, all_countries - {"CD"})
        self.assertEqual(set(linkage["upstream_only_countries"]), {"CD"})
        self.assertEqual(
            sum(
                int(materialized[country]["locality_rows"])
                for country in materialized_countries
            ),
            linkage["materialized_locality_rows"],
        )
        self.assertEqual(linkage["materialized_locality_rows"], 64477)
        self.assertEqual(
            sum(int(upstream[country]["locality_rows"]) for country in all_countries),
            linkage["upstream_locality_rows"],
        )
        self.assertEqual(linkage["upstream_locality_rows"], 101713)
        self.assertFalse((ROOT / linkage["country_directory"] / "CD").exists())

    def test_country_outside_region_is_rejected(self):
        with self.assertRaisesRegex(KeyError, "outside Middle Africa"):
            self.middle_africa.get("ZA")


class MiddleAfricaPostcodePolicies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.middle_africa = MiddleAfricaRegistry()

    def test_dr_congo_seven_digits_and_gabon_two_digits_are_accepted(self):
        self.assertTrue(self.middle_africa.validate_postcode("CD", "1004131"))
        self.assertTrue(self.middle_africa.validate_postcode("GA", "05"))

    def test_wrong_lengths_are_rejected(self):
        for country, postcode in {"CD": "100413", "GA": "005"}.items():
            with self.subTest(country=country):
                self.assertFalse(
                    self.middle_africa.validate_postcode(country, postcode)
                )

    def test_no_code_countries_reject_form_placeholders(self):
        for country in ("AO", "CM", "CF", "TD", "CG", "GQ", "ST"):
            with self.subTest(country=country):
                self.assertTrue(self.middle_africa.validate_postcode(country, None))
                self.assertFalse(
                    self.middle_africa.validate_postcode(country, "00000")
                )

    def test_required_code_absence_is_rejected(self):
        for country in ("CD", "GA"):
            with self.subTest(country=country):
                self.assertFalse(self.middle_africa.validate_postcode(country, None))


class MiddleAfricaAddressRendering(unittest.TestCase):
    def test_dr_congo_keeps_address2_rural_hierarchy_and_seven_digit_code(self):
        result = render_middle_africa_address(
            {
                "country_code": "CD",
                "address2": {
                    "fr-Latn": "Bâtiment B, porte 4",
                    "en": "Building B, Door 4",
                },
                "village": {"fr-Latn": "Village Ngieme", "en": "Ngieme Village"},
                "place": {"fr-Latn": "Secteur de Niadi Nkara", "en": "Niadi Nkara Sector"},
                "municipality": {
                    "fr-Latn": "Territoire de Bulungu",
                    "en": "Bulungu Territory",
                },
                "state": {"fr-Latn": "KWILU", "en": "KWILU"},
                "postcode": "3202011",
            },
            "CD",
        )
        for line in (
            "Bâtiment B, porte 4",
            "Village Ngieme",
            "Secteur de Niadi Nkara",
            "Territoire de Bulungu",
            "3202011 KWILU",
        ):
            self.assertIn(line, result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_dr_congo_selects_national_languages_without_cross_filling(self):
        result = render_middle_africa_address(
            {
                "country_code": "CD",
                "road": {"sw-Latn": "Barabara ya Posta", "en": "Post Office Road"},
                "house_number": "1",
                "state": {"sw-Latn": "KINSHASA", "en": "KINSHASA"},
                "postcode": "1004131",
            },
            "CD",
            native_language="sw-Latn",
        )
        self.assertEqual(result.native.profile_key, "CD_sw")
        self.assertIn("1 Barabara ya Posta", result.native.lines)
        self.assertIn("1004131 KINSHASA", result.native.lines)

    def test_gabon_keeps_postcode_and_delivery_office_code_distinct(self):
        result = render_middle_africa_address(
            {
                "country_code": "GA",
                "po_box": {"fr-Latn": "BP 13210", "en": "P.O. Box 13210"},
                "city": {
                    "fr-Latn": "LIBREVILLE–GROS-BOUQUET",
                    "en": "LIBREVILLE–GROS-BOUQUET",
                },
                "postcode": "01",
                "sorting_code": "03",
            },
            "GA",
        )
        self.assertIn("01 LIBREVILLE–GROS-BOUQUET 03", result.native.lines)
        self.assertEqual(result.native.components["postcode"], "01")
        self.assertEqual(result.native.components["sorting_code"], "03")
        self.assertIn("provisional_country_profile", result.warnings)

    def test_equatorial_guinea_preserves_premises_and_admin_hierarchy(self):
        result = render_middle_africa_address(
            {
                "country_code": "GQ",
                "organization": {
                    "es-Latn": "Viviendas sociales Vicatana",
                    "en": "Vicatana Social Housing",
                },
                "address2": {
                    "es-Latn": "Portal 5, puerta 29",
                    "en": "Entrance 5, Door 29",
                },
                "state": {"es-Latn": "BIOKO NORTE", "en": "BIOKO NORTE"},
                "municipality": {"es-Latn": "MALABO", "en": "MALABO"},
                "city": {"es-Latn": "REBOLA", "en": "REBOLA"},
            },
            "GQ",
        )
        self.assertLess(
            result.native.lines.index("BIOKO NORTE"),
            result.native.lines.index("MALABO"),
        )
        self.assertLess(
            result.native.lines.index("MALABO"),
            result.native.lines.index("REBOLA"),
        )
        self.assertIn("Portal 5, puerta 29", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_central_african_sango_and_english_are_explicit(self):
        result = render_middle_africa_address(
            {
                "country_code": "CF",
                "address2": {"sg-Latn": "S/C André", "en": "Care of André"},
                "organization": {
                    "sg-Latn": "Église Elim Bangui–M'Poko",
                    "en": "Elim Church Bangui–M'Poko",
                },
                "po_box": {"sg-Latn": "BP 729", "en": "P.O. Box 729"},
                "city": {"sg-Latn": "BANGUI", "en": "BANGUI"},
            },
            "CF",
            native_language="sg-Latn",
        )
        self.assertEqual(result.native.profile_key, "CF_sg")
        self.assertIn("S/C André", result.native.lines)
        self.assertIn("BP 729", result.native.lines)

    def test_republic_of_congo_retains_po_box_without_inventing_code(self):
        result = render_middle_africa_address(
            {
                "country_code": "CG",
                "po_box": {"ln-Latn": "BP 131", "en": "P.O. Box 131"},
                "city": {"ln-Latn": "Brazzaville", "en": "BRAZZAVILLE"},
            },
            "CG",
            native_language="ln-Latn",
        )
        self.assertEqual(result.native.profile_key, "CG_ln")
        self.assertIn("BP 131", result.native.lines)
        self.assertNotIn("postcode", result.native.components)

    def test_sao_tome_keeps_street_po_box_and_island(self):
        result = render_middle_africa_address(
            {
                "country_code": "ST",
                "road": {
                    "pt-Latn": "Avenida das Nações Unidas",
                    "en": "United Nations Avenue",
                },
                "po_box": {"pt-Latn": "Caixa Postal 1048", "en": "P.O. Box 1048"},
                "city": {"pt-Latn": "S. Tomé", "en": "SÃO TOMÉ"},
                "island": {"pt-Latn": "Ilha de São Tomé", "en": "São Tomé Island"},
            },
            "ST",
        )
        self.assertIn("Avenida das Nações Unidas", result.native.lines)
        self.assertIn("Caixa Postal 1048", result.native.lines)
        self.assertIn("Ilha de São Tomé", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_angola_address2_is_kept_and_dummy_postcode_is_not_rendered(self):
        registry = MiddleAfricaRegistry()
        self.assertFalse(registry.validate_postcode("AO", "0000"))
        result = render_middle_africa_address(
            {
                "country_code": "AO",
                "address2": {"pt-Latn": "7.º andar", "en": "7th Floor"},
                "road": {
                    "pt-Latn": "Rua Frederik Engels",
                    "en": "Frederik Engels Street",
                },
                "house_number": "92",
                "city": {"pt-Latn": "LUANDA", "en": "LUANDA"},
                "postcode": "0000",
            },
            "AO",
        )
        self.assertIn("7.º andar", result.native.lines)
        self.assertNotIn("0000", result.native.text)
        self.assertEqual(result.native.unrendered_components["postcode"], "0000")
        self.assertIn("provisional_country_profile", result.warnings)

    def test_same_latin_script_does_not_fill_missing_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_middle_africa_address(
                {
                    "country_code": "CM",
                    "po_box": {"fr-Latn": "BP 6000"},
                    "city": {"fr-Latn": "YAOUNDÉ"},
                },
                "CM",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "po_box"))

    def test_bidi_controls_and_wrong_arabic_script_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "dangerous bidirectional control"):
            render_middle_africa_address(
                {
                    "country_code": "TD",
                    "city": {"ar-Arab": "نجام\u202eينا", "en": "N'DJAMENA"},
                },
                "TD",
            )
        with self.assertRaisesRegex(ValueError, "not Arab-script"):
            render_middle_africa_address(
                {
                    "country_code": "TD",
                    "city": {"ar-Arab": "N'Djamena", "en": "N'DJAMENA"},
                },
                "TD",
            )


if __name__ == "__main__":
    unittest.main()
