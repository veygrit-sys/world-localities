"""Domestic-language, English and postal-policy tests for Western Africa."""

import csv
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    MissingLocalizedComponents,
    ProfileRegistry,
    WesternAfricaRegistry,
    render_western_africa_address,
)


EXPECTED_PROFILES = {
    "BJ": ({"fr-Latn": "BJ_fr"}, "BJ_en"),
    "BF": ({"fr-Latn": "BF_fr", "mos-Latn": "BF_mos"}, "BF_en"),
    "CV": ({"pt-Latn": "CV_pt", "kea-Latn": "CV_kea"}, "CV_en"),
    "CI": ({"fr-Latn": "CI_fr"}, "CI_en"),
    "GM": ({"en": "GM_en"}, "GM_en"),
    "GH": ({"en": "GH_en", "ak-Latn": "GH_ak"}, "GH_en"),
    "GN": ({"fr-Latn": "GN_fr"}, "GN_en"),
    "GW": ({"pt-Latn": "GW_pt", "pov-Latn": "GW_pov"}, "GW_en"),
    "LR": ({"en": "LR_en"}, "LR_en"),
    "ML": ({"fr-Latn": "ML_fr", "bm-Latn": "ML_bm"}, "ML_en"),
    "MR": ({"ar-Arab": "MR_ar", "fr-Latn": "MR_fr"}, "MR_en"),
    "NE": ({"fr-Latn": "NE_fr", "ha-Latn": "NE_ha"}, "NE_en"),
    "NG": (
        {
            "en": "NG_en",
            "ha-Latn": "NG_ha",
            "yo-Latn": "NG_yo",
            "ig-Latn": "NG_ig",
        },
        "NG_en",
    ),
    "SH": ({"en": "SH_en"}, "SH_en"),
    "SL": ({"en": "SL_en", "kri-Latn": "SL_kri"}, "SL_en"),
    "SN": ({"fr-Latn": "SN_fr", "wo-Latn": "SN_wo"}, "SN_en"),
    "TG": ({"fr-Latn": "TG_fr", "ee-Latn": "TG_ee"}, "TG_en"),
}


def coverage_rows(relative_path: str) -> dict[str, dict[str, str]]:
    with (ROOT / relative_path).open(encoding="utf-8", newline="") as source:
        return {row["country"]: row for row in csv.DictReader(source)}


class WesternAfricaProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.western_africa = WesternAfricaRegistry()

    def test_all_17_m49_entities_have_domestic_and_english_profiles(self):
        self.assertEqual(set(self.western_africa.countries), set(EXPECTED_PROFILES))
        for country, (native_profiles, english_profile) in EXPECTED_PROFILES.items():
            with self.subTest(country=country):
                policy = self.western_africa.get(country)
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

    def test_report_exposes_dated_public_evidence(self):
        self.assertEqual(
            self.western_africa.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-17",
                "countries": 17,
                "native_language_variants": 30,
                "english_profiles": 17,
                "provisional_countries": [
                    "CI",
                    "CV",
                    "GM",
                    "GN",
                    "GW",
                    "LR",
                    "ML",
                    "NE",
                    "SL",
                    "SN",
                    "TG",
                ],
            },
        )

    def test_every_country_has_postcode_sorting_script_and_source_policy(self):
        for country, policy in self.western_africa.countries.items():
            with self.subTest(country=country):
                self.assertIn("postcode_pattern", policy)
                self.assertIsInstance(policy["postcode_required"], bool)
                self.assertIn("sorting_code_pattern", policy)
                self.assertIsInstance(policy["sorting_code_required"], bool)
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertTrue(policy["romanization_policy"])
                self.assertTrue(policy["sources"])

    def test_africa_registry_is_reused_with_nigeria_upstream_only(self):
        linkage = self.western_africa.locality_registry
        materialized = coverage_rows(linkage["materialized_scope_file"])
        upstream = coverage_rows(linkage["upstream_scope_file"])
        materialized_countries = set(linkage["materialized_countries"])
        all_countries = set(EXPECTED_PROFILES)

        self.assertEqual(materialized_countries, all_countries - {"NG"})
        self.assertEqual(set(linkage["upstream_only_countries"]), {"NG"})
        self.assertEqual(
            sum(
                int(materialized[country]["locality_rows"])
                for country in materialized_countries
            ),
            linkage["materialized_locality_rows"],
        )
        self.assertEqual(linkage["materialized_locality_rows"], 131560)
        self.assertEqual(
            sum(int(upstream[country]["locality_rows"]) for country in all_countries),
            linkage["upstream_locality_rows"],
        )
        self.assertEqual(linkage["upstream_locality_rows"], 192989)
        self.assertFalse((ROOT / linkage["country_directory"] / "NG").exists())

    def test_country_outside_region_is_rejected(self):
        with self.assertRaisesRegex(KeyError, "outside Western Africa"):
            self.western_africa.get("ZA")


class WesternAfricaPostalPolicies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.western_africa = WesternAfricaRegistry()

    def test_current_country_specific_postcode_syntax_is_accepted(self):
        valid = {
            "BF": "10001",
            "CV": "7600",
            "GH": "GA-183",
            "GN": "001",
            "GW": "1000",
            "LR": "1000",
            "NE": "8001",
            "NG": "900001",
            "SH": "STHL 1ZZ",
            "SN": "12500",
        }
        for country, postcode in valid.items():
            with self.subTest(country=country):
                self.assertTrue(
                    self.western_africa.validate_postcode(country, postcode)
                )
        self.assertTrue(
            self.western_africa.validate_postcode("GH", "GA-183-8164")
        )
        self.assertTrue(self.western_africa.validate_postcode("SH", "sthl1zz"))

    def test_wrong_lengths_and_forms_are_rejected(self):
        invalid = {
            "BF": "1000",
            "CV": "76000",
            "GH": "GA183",
            "GN": "01",
            "GW": "100",
            "LR": "10000",
            "NE": "800",
            "NG": "90001",
            "SH": "STH 1ZZ",
            "SN": "1250",
        }
        for country, postcode in invalid.items():
            with self.subTest(country=country):
                self.assertFalse(
                    self.western_africa.validate_postcode(country, postcode)
                )

    def test_no_code_countries_reject_form_placeholders(self):
        for country in ("BJ", "CI", "GM", "ML", "MR", "SL", "TG"):
            with self.subTest(country=country):
                self.assertTrue(self.western_africa.validate_postcode(country, None))
                self.assertFalse(
                    self.western_africa.validate_postcode(country, "00000")
                )

    def test_required_code_absence_is_rejected(self):
        for country in ("CV", "GH", "GN", "GW", "LR", "NE", "NG", "SH", "SN"):
            with self.subTest(country=country):
                self.assertFalse(
                    self.western_africa.validate_postcode(country, None)
                )

    def test_burkina_faso_accepts_documented_code_without_requiring_it(self):
        self.assertTrue(self.western_africa.validate_postcode("BF", None))
        self.assertTrue(self.western_africa.validate_postcode("BF", "10001"))

    def test_delivery_office_codes_are_not_treated_as_postcodes(self):
        self.assertTrue(self.western_africa.validate_sorting_code("BJ", "10"))
        self.assertTrue(self.western_africa.validate_sorting_code("CI", "06"))
        self.assertTrue(self.western_africa.validate_sorting_code("CI", "104"))
        self.assertTrue(self.western_africa.validate_sorting_code("LR", "40"))
        self.assertFalse(self.western_africa.validate_sorting_code("CI", "6"))
        self.assertFalse(self.western_africa.validate_sorting_code("CI", None))
        self.assertFalse(self.western_africa.validate_sorting_code("GH", "GA"))


class WesternAfricaAddressRendering(unittest.TestCase):
    def test_benin_keeps_delivery_office_code_separate_from_postcode(self):
        result = render_western_africa_address(
            {
                "country_code": "BJ",
                "po_box": {"fr-Latn": "BP 648", "en": "P.O. Box 648"},
                "sorting_code": "10",
                "city": {"fr-Latn": "COTONOU", "en": "COTONOU"},
            },
            "BJ",
        )
        self.assertIn("10 BP 648", result.native.lines)
        self.assertNotIn("postcode", result.native.components)
        self.assertEqual(result.native.components["sorting_code"], "10")

    def test_cote_divoire_preserves_office_code_at_both_ends(self):
        result = render_western_africa_address(
            {
                "country_code": "CI",
                "po_box": {"fr-Latn": "B.P. 37", "en": "P.O. Box 37"},
                "sorting_code": "06",
                "city": {"fr-Latn": "ABIDJAN", "en": "ABIDJAN"},
            },
            "CI",
        )
        self.assertIn("06 B.P. 37 ABIDJAN 06", result.native.lines)
        self.assertIn("provisional_country_profile", result.warnings)

    def test_ghana_postcode_and_digital_address_share_one_verified_field(self):
        result = render_western_africa_address(
            {
                "country_code": "GH",
                "address2": {"ak-Latn": "Ɔdan B, dan 2", "en": "Block B, Floor 2"},
                "road": {"ak-Latn": "Independence Avenue", "en": "Independence Avenue"},
                "house_number": "14",
                "city": {"ak-Latn": "ACCRA", "en": "ACCRA"},
                "postcode": "GA-183-8164",
                "county": {"ak-Latn": "Ayawaso West", "en": "Ayawaso West"},
                "state": {"ak-Latn": "GREATER ACCRA", "en": "GREATER ACCRA"},
            },
            "GH",
            native_language="ak-Latn",
        )
        self.assertEqual(result.native.profile_key, "GH_ak")
        self.assertIn("Ɔdan B, dan 2", result.native.lines)
        self.assertIn("ACCRA GA-183-8164", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_guinea_keeps_postal_radical_and_po_box_distinct(self):
        result = render_western_africa_address(
            {
                "country_code": "GN",
                "postcode": "001",
                "po_box": {"fr-Latn": "BP 457", "en": "P.O. Box 457"},
                "city": {"fr-Latn": "CONAKRY", "en": "CONAKRY"},
            },
            "GN",
        )
        self.assertIn("001 BP 457 CONAKRY", result.native.lines)
        self.assertEqual(result.native.components["postcode"], "001")
        self.assertEqual(result.native.components["po_box"], "BP 457")

    def test_nigeria_keeps_address2_and_admin_hierarchy(self):
        result = render_western_africa_address(
            {
                "country_code": "NG",
                "address2": {"yo-Latn": "Ilé B, Yàrá 4", "en": "Block B, Unit 4"},
                "road": {"yo-Latn": "Ọ̀nà Post Office", "en": "Post Office Road"},
                "house_number": "7",
                "city": {"yo-Latn": "ABUJA", "en": "ABUJA"},
                "postcode": "900001",
                "municipality": {"yo-Latn": "AMAC", "en": "AMAC"},
                "state": {"yo-Latn": "FCT", "en": "FCT"},
            },
            "NG",
            native_language="yo-Latn",
        )
        self.assertEqual(result.native.profile_key, "NG_yo")
        self.assertIn("Ilé B, Yàrá 4", result.native.lines)
        self.assertIn("ABUJA 900001", result.native.lines)
        self.assertLess(result.native.lines.index("AMAC"), result.native.lines.index("FCT"))
        self.assertFalse(result.native.unrendered_components)

    def test_saint_helena_normalizes_its_single_postcode(self):
        result = render_western_africa_address(
            {
                "country_code": "SH",
                "address2": {"en": "Flat 2"},
                "road": {"en": "Market Street"},
                "house_number": "1",
                "city": {"en": "JAMESTOWN"},
                "postcode": "sthl1zz",
            },
            "SH",
        )
        self.assertIn("STHL 1ZZ", result.native.lines)
        self.assertIn("Saint Helena", result.native.lines)

    def test_mauritania_po_box_number_is_not_promoted_to_postcode(self):
        result = render_western_africa_address(
            {
                "country_code": "MR",
                "road": {"ar-Arab": "شارع الملك فيصل", "en": "King Faisal Avenue"},
                "po_box": {"ar-Arab": "ص.ب. 10000", "en": "P.O. Box 10000"},
                "city": {"ar-Arab": "نواكشوط", "en": "NOUAKCHOTT"},
            },
            "MR",
        )
        self.assertIn("ص.ب. 10000", result.native.lines)
        self.assertNotIn("postcode", result.native.components)

    def test_same_latin_script_does_not_fill_missing_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_western_africa_address(
                {
                    "country_code": "SN",
                    "road": {"fr-Latn": "Avenue Léopold Sédar Senghor"},
                    "city": {"fr-Latn": "DAKAR"},
                    "postcode": "12500",
                },
                "SN",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "road"))

    def test_wrong_arabic_script_and_bidi_controls_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "not Arab-script"):
            render_western_africa_address(
                {
                    "country_code": "MR",
                    "city": {"ar-Arab": "Nouakchott", "en": "NOUAKCHOTT"},
                },
                "MR",
            )
        with self.assertRaisesRegex(ValueError, "dangerous bidirectional control"):
            render_western_africa_address(
                {
                    "country_code": "MR",
                    "city": {"ar-Arab": "نواكش‮وط", "en": "NOUAKCHOTT"},
                },
                "MR",
            )


if __name__ == "__main__":
    unittest.main()
