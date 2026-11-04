"""Domestic-language, English and postcode quality tests for Northern Africa."""

import csv
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    MissingLocalizedComponents,
    NorthernAfricaRegistry,
    ProfileRegistry,
    render_northern_africa_address,
)


EXPECTED_PROFILES = {
    "DZ": (
        {"ar-Arab": "DZ_ar", "kab-Latn": "DZ_kab", "fr-Latn": "DZ_fr"},
        "DZ_en",
    ),
    "EG": ({"ar-Arab": "EG_ar"}, "EG_en"),
    "EH": (
        {"ar-Arab": "EH_ar", "es-Latn": "EH_es", "fr-Latn": "EH_fr"},
        "EH_en",
    ),
    "LY": ({"ar-Arab": "LY_ar"}, "LY_en"),
    "MA": (
        {"ar-Arab": "MA_ar", "zgh-Tfng": "MA_zgh", "fr-Latn": "MA_fr"},
        "MA_en",
    ),
    "SD": ({"ar-Arab": "SD_ar", "en": "SD_en"}, "SD_en"),
    "TN": ({"ar-Arab": "TN_ar", "fr-Latn": "TN_fr"}, "TN_en"),
}


def coverage_rows(relative_path: str) -> dict[str, dict[str, str]]:
    with (ROOT / relative_path).open(encoding="utf-8", newline="") as source:
        return {row["country"]: row for row in csv.DictReader(source)}


class NorthernAfricaProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.northern_africa = NorthernAfricaRegistry()

    def test_all_seven_m49_entities_have_domestic_and_english_profiles(self):
        self.assertEqual(set(self.northern_africa.countries), set(EXPECTED_PROFILES))
        for country, (native_profiles, english_profile) in EXPECTED_PROFILES.items():
            with self.subTest(country=country):
                policy = self.northern_africa.get(country)
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
            self.northern_africa.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-16",
                "countries": 7,
                "native_language_variants": 15,
                "english_profiles": 7,
                "provisional_countries": ["EH", "LY", "SD"],
            },
        )

    def test_every_country_has_postcode_script_and_source_policy(self):
        for country, policy in self.northern_africa.countries.items():
            with self.subTest(country=country):
                self.assertIn("postcode_pattern", policy)
                self.assertIsInstance(policy["postcode_required"], bool)
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertTrue(policy["romanization_policy"])
                self.assertTrue(policy["sources"])

    def test_existing_africa_registry_is_reused_without_claiming_missing_morocco_pack(self):
        linkage = self.northern_africa.locality_registry
        materialized = coverage_rows(linkage["materialized_scope_file"])
        upstream = coverage_rows(linkage["upstream_scope_file"])
        materialized_countries = set(linkage["materialized_countries"])
        all_countries = set(EXPECTED_PROFILES)

        self.assertEqual(materialized_countries, {"DZ", "EG", "EH", "LY", "SD", "TN"})
        self.assertEqual(set(linkage["upstream_only_countries"]), {"MA"})
        self.assertEqual(
            sum(int(materialized[country]["locality_rows"]) for country in materialized_countries),
            linkage["materialized_locality_rows"],
        )
        self.assertEqual(linkage["materialized_locality_rows"], 31778)
        self.assertEqual(
            sum(int(upstream[country]["locality_rows"]) for country in all_countries),
            linkage["upstream_locality_rows"],
        )
        self.assertEqual(linkage["upstream_locality_rows"], 78724)
        self.assertFalse((ROOT / linkage["country_directory"] / "MA").exists())

    def test_country_outside_region_is_rejected(self):
        with self.assertRaisesRegex(KeyError, "outside Northern Africa"):
            self.northern_africa.get("ZA")


class NorthernAfricaPostcodePolicies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.northern_africa = NorthernAfricaRegistry()

    def test_country_specific_current_lengths_are_accepted(self):
        valid = {
            "DZ": "16027",
            "EG": "3759914",
            "EH": "70000",
            "MA": "20370",
            "SD": "11111",
            "TN": "1002",
        }
        for country, postcode in valid.items():
            with self.subTest(country=country):
                self.assertTrue(
                    self.northern_africa.validate_postcode(country, postcode)
                )

    def test_wrong_lengths_and_unassigned_libyan_codes_are_rejected(self):
        invalid = {
            "DZ": "1602",
            "EG": "12345",
            "MA": "2037A",
            "SD": "1111",
            "TN": "10020",
            "LY": "10001",
        }
        for country, postcode in invalid.items():
            with self.subTest(country=country):
                self.assertFalse(
                    self.northern_africa.validate_postcode(country, postcode)
                )

    def test_required_and_optional_absence_are_distinct(self):
        for country in ("DZ", "EG", "MA", "SD", "TN"):
            with self.subTest(country=country):
                self.assertFalse(self.northern_africa.validate_postcode(country, None))
        for country in ("EH", "LY"):
            with self.subTest(country=country):
                self.assertTrue(self.northern_africa.validate_postcode(country, None))


class NorthernAfricaAddressRendering(unittest.TestCase):
    def test_algeria_preserves_address2_and_postcode_before_locality(self):
        result = render_northern_africa_address(
            {
                "country_code": "DZ",
                "address2": {"ar-Arab": "الطابق 2", "en": "Floor 2"},
                "road": {"ar-Arab": "شارع الاستقلال", "en": "Independence Street"},
                "house_number": "2",
                "city": {"ar-Arab": "الجزائر", "en": "ALGIERS"},
                "postcode": "16027",
            },
            "DZ",
        )
        self.assertEqual(result.native.profile_key, "DZ_ar")
        self.assertLess(
            result.native.lines.index("الطابق 2"),
            result.native.lines.index("2 شارع الاستقلال"),
        )
        self.assertIn("16027 الجزائر", result.native.lines)
        self.assertIn("16027 ALGIERS", result.english.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_egypt_uses_seven_digit_postcode_below_governorate(self):
        result = render_northern_africa_address(
            {
                "country_code": "EG",
                "road": {"ar-Arab": "شارع موسى جلال", "en": "Moussa Galal Street"},
                "house_number": "30",
                "neighbourhood": {"ar-Arab": "المهندسين", "en": "Al-Mohandessine"},
                "city": {"ar-Arab": "الجيزة", "en": "GIZA"},
                "state": {"ar-Arab": "محافظة الجيزة", "en": "GIZA GOVERNORATE"},
                "postcode": "3759914",
            },
            "EG",
        )
        self.assertLess(
            result.native.lines.index("محافظة الجيزة"),
            result.native.lines.index("3759914"),
        )
        self.assertEqual(result.native.lines[-1], "مصر")
        self.assertEqual(result.english.lines[-1], "Egypt")

    def test_morocco_validates_tifinagh_and_keeps_it_separate_from_english(self):
        result = render_northern_africa_address(
            {
                "country_code": "MA",
                "address2": {"zgh-Tfng": "ⵜⵉⴳⵎⵉ 13", "en": "Apartment 13"},
                "road": {"zgh-Tfng": "ⴰⵙⵙⵉⴼ", "en": "River Avenue"},
                "house_number": "23",
                "city": {"zgh-Tfng": "ⵕⵕⴱⴰⵟ", "en": "RABAT"},
                "postcode": "10000",
            },
            "MA",
            native_language="zgh-Tfng",
        )
        self.assertEqual(result.native.profile_key, "MA_zgh")
        self.assertIn("ⵜⵉⴳⵎⵉ 13", result.native.lines)
        self.assertIn("10000 ⵕⵕⴱⴰⵟ", result.native.lines)
        self.assertEqual(result.native.lines[-1], "ⵍⵎⵖⵔⵉⴱ")
        self.assertIn("10000 RABAT", result.english.lines)

    def test_tunisian_french_does_not_silently_fill_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_northern_africa_address(
                {
                    "country_code": "TN",
                    "road": {"fr-Latn": "Avenue de la Liberté"},
                    "house_number": "42",
                    "city": {"fr-Latn": "TUNIS BELVÉDÈRE"},
                    "postcode": "1002",
                },
                "TN",
                native_language="fr-Latn",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "road"))

    def test_sudan_preserves_po_box_address2_and_postcode_line(self):
        result = render_northern_africa_address(
            {
                "country_code": "SD",
                "address2": {"ar-Arab": "مبنى الأخوة", "en": "Fraternity Building"},
                "road": {"ar-Arab": "شارع الجمهورية", "en": "Al-Gomhouria Street"},
                "po_box": {"ar-Arab": "ص ب 211", "en": "P.O. Box 211"},
                "city": {"ar-Arab": "الخرطوم", "en": "KHARTOUM"},
                "postcode": "11111",
            },
            "SD",
        )
        self.assertLess(
            result.native.lines.index("ص ب 211"),
            result.native.lines.index("11111"),
        )
        self.assertLess(
            result.native.lines.index("11111"),
            result.native.lines.index("الخرطوم"),
        )
        self.assertIn("provisional_country_profile", result.warnings)

    def test_western_sahara_route_is_sovereignty_neutral_and_provisional(self):
        result = render_northern_africa_address(
            {
                "country_code": "EH",
                "road": {"ar-Arab": "شارع السلام", "en": "Peace Street"},
                "house_number": "4",
                "city": {"ar-Arab": "العيون", "en": "LAAYOUNE"},
            },
            "EH",
        )
        self.assertNotIn("postcode", result.native.components)
        self.assertEqual(result.native.lines[-1], "الصحراء الغربية")
        self.assertEqual(result.english.lines[-1], "Western Sahara")
        self.assertIn("provisional_country_profile", result.warnings)

    def test_bidi_controls_and_wrong_script_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "dangerous bidirectional control"):
            render_northern_africa_address(
                {
                    "country_code": "LY",
                    "road": {"ar-Arab": "شارع\u202eالسلام", "en": "Peace Street"},
                    "city": {"ar-Arab": "طرابلس", "en": "TRIPOLI"},
                },
                "LY",
            )
        with self.assertRaisesRegex(ValueError, "not Tfng-script"):
            render_northern_africa_address(
                {
                    "country_code": "MA",
                    "road": {"zgh-Tfng": "Avenue Hassan", "en": "Hassan Avenue"},
                    "city": {"zgh-Tfng": "ⵕⵕⴱⴰⵟ", "en": "RABAT"},
                    "postcode": "10000",
                },
                "MA",
                native_language="zgh-Tfng",
            )


if __name__ == "__main__":
    unittest.main()
