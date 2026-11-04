"""Native-language and English Central Asia address quality tests."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    CentralAsiaRegistry,
    MissingLocalizedComponents,
    ProfileRegistry,
    render_central_asia_address,
)


class CentralAsiaProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.central_asia = CentralAsiaRegistry()

    def test_all_five_countries_have_every_native_variant_and_english(self):
        expected = {
            "KG": ({"ky-Cyrl": "KG_ky", "ru": "KG_ru"}, "KG_en"),
            "KZ": ({"kk-Cyrl": "KZ_kk", "ru": "KZ_ru"}, "KZ_en"),
            "TJ": ({"tg-Cyrl": "TJ_tg", "ru": "TJ_ru"}, "TJ_en"),
            "TM": ({"tk-Latn": "TM_tk"}, "TM_en"),
            "UZ": ({"uz-Latn": "UZ_uz", "uz-Cyrl": "UZ_uz"}, "UZ_en"),
        }
        self.assertEqual(set(self.central_asia.countries), set(expected))
        for country, (native_profiles, english_profile) in expected.items():
            with self.subTest(country=country):
                policy = self.central_asia.get(country)
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

    def test_coverage_report_counts_languages_and_evidence(self):
        self.assertEqual(
            self.central_asia.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-16",
                "countries": 5,
                "native_language_variants": 9,
                "english_profiles": 5,
                "provisional_countries": [],
            },
        )

    def test_every_native_language_has_script_and_provenance(self):
        for country, policy in self.central_asia.countries.items():
            with self.subTest(country=country):
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertTrue(policy["sources"])
                self.assertTrue(policy["romanization_policy"])
                self.assertEqual(policy["evidence_status"], "official_guidance")


class CentralAsiaBilingualRendering(unittest.TestCase):
    def test_kazakhstan_keeps_address2_and_new_postcode_before_locality(self):
        result = render_central_asia_address(
            {
                "country_code": "KZ",
                "recipient": {"kk-Cyrl": "Серік Батыров", "en": "Serik Batyrov"},
                "road": {"kk-Cyrl": "Рысқұлбеков көшесі", "en": "Ryskulbekov Street"},
                "house_number": "16",
                "address2": {"kk-Cyrl": "224-пәтер", "en": "Apartment 224"},
                "city": {"kk-Cyrl": "Астана", "en": "Astana"},
                "postcode": "Z00Y5M7",
            },
            "KZ",
        )
        self.assertEqual(result.native.profile_key, "KZ_kk")
        self.assertEqual(result.english.profile_key, "KZ_en")
        self.assertIn("224-пәтер", result.native.lines)
        self.assertIn("Apartment 224", result.english.lines)
        self.assertIn("Z00Y5M7, Астана", result.native.lines)
        self.assertIn("Z00Y5M7, Astana", result.english.lines)
        self.assertFalse(result.native.unrendered_components)
        self.assertFalse(result.english.unrendered_components)

    def test_kazakhstan_preserves_transitional_numeric_postcode(self):
        result = render_central_asia_address(
            {
                "country_code": "KZ",
                "city": {"kk-Cyrl": "Астана", "en": "Astana"},
                "postcode": "010013",
            },
            "KZ",
        )
        self.assertIn("010013, Астана", result.native.lines)
        self.assertIn("010013, Astana", result.english.lines)

    def test_kyrgyz_and_russian_profiles_are_distinct(self):
        kyrgyz = render_central_asia_address(
            {
                "country_code": "KG",
                "city": {"ky-Cyrl": "Бишкек", "ru": "Бишкек", "en": "Bishkek"},
                "road": {
                    "ky-Cyrl": "Чүй проспектиси",
                    "ru": "проспект Чуй",
                    "en": "Chuy Avenue",
                },
                "house_number": "193",
                "postcode": "720001",
            },
            "KG",
        )
        russian = render_central_asia_address(
            {
                "country_code": "KG",
                "city": {"ky-Cyrl": "Бишкек", "ru": "Бишкек", "en": "Bishkek"},
                "road": {
                    "ky-Cyrl": "Чүй проспектиси",
                    "ru": "проспект Чуй",
                    "en": "Chuy Avenue",
                },
                "house_number": "193",
                "postcode": "720001",
            },
            "KG",
            native_language="ru",
        )
        self.assertEqual(kyrgyz.native.profile_key, "KG_ky")
        self.assertEqual(russian.native.profile_key, "KG_ru")
        self.assertIn("193 Чүй проспектиси", kyrgyz.native.lines)
        self.assertIn("193 проспект Чуй", russian.native.lines)

    def test_tajik_does_not_fill_russian_despite_shared_script(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_central_asia_address(
                {
                    "country_code": "TJ",
                    "road": {"tg-Cyrl": "кӯчаи Рӯдакӣ", "en": "Rudaki Street"},
                    "house_number": "7",
                    "postcode": "734012",
                },
                "TJ",
                native_language="ru",
            )
        self.assertEqual(error.exception.language, "ru")
        self.assertEqual(error.exception.components, ("road",))

    def test_uzbek_latin_and_cyrillic_are_explicit_alternatives(self):
        components = {
            "country_code": "UZ",
            "road": {
                "uz-Latn": "Amir Temur koʻchasi",
                "uz-Cyrl": "Амир Темур кўчаси",
                "en": "Amir Temur Street",
            },
            "house_number": "4",
            "city": {
                "uz-Latn": "Toshkent",
                "uz-Cyrl": "Тошкент",
                "en": "Tashkent",
            },
            "postcode": "100123",
        }
        latin = render_central_asia_address(components, "UZ")
        cyrillic = render_central_asia_address(
            components, "UZ", native_language="uz-Cyrl"
        )
        self.assertEqual(latin.native_language, "uz-Latn")
        self.assertIn("100123, Toshkent", latin.native.lines)
        self.assertEqual(cyrillic.native_language, "uz-Cyrl")
        self.assertIn("100123, Тошкент", cyrillic.native.lines)
        self.assertEqual(latin.native.profile_key, "UZ_uz")
        self.assertEqual(cyrillic.native.profile_key, "UZ_uz")

    def test_uzbek_cyrillic_does_not_fill_latin(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_central_asia_address(
                {
                    "country_code": "UZ",
                    "city": {"uz-Cyrl": "Тошкент", "en": "Tashkent"},
                    "postcode": "100123",
                },
                "UZ",
            )
        self.assertEqual(error.exception.language, "uz-Latn")
        self.assertEqual(error.exception.components, ("city",))

    def test_cyrillic_profile_rejects_latin_text(self):
        with self.assertRaisesRegex(ValueError, "not Cyrl-script: city"):
            render_central_asia_address(
                {
                    "country_code": "KZ",
                    "city": {"kk-Cyrl": "Astana", "en": "Astana"},
                    "postcode": "Z00Y5M7",
                },
                "KZ",
            )

    def test_english_profile_rejects_cyrillic_text(self):
        with self.assertRaisesRegex(ValueError, "not Latin-script: city"):
            render_central_asia_address(
                {
                    "country_code": "TJ",
                    "city": {"tg-Cyrl": "Душанбе", "en": "Душанбе"},
                    "postcode": "734000",
                },
                "TJ",
            )

    def test_turkmen_latin_is_not_silently_used_as_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_central_asia_address(
                {
                    "country_code": "TM",
                    "road": {"tk-Latn": "Ankara köçesi"},
                    "house_number": "39",
                    "postcode": "744027",
                },
                "TM",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("road",))

    def test_turkmen_postcode_follows_locality_and_region(self):
        result = render_central_asia_address(
            {
                "country_code": "TM",
                "city": {"tk-Latn": "Balkanabat", "en": "Balkanabat"},
                "state": {"tk-Latn": "Balkan welaýaty", "en": "Balkan Province"},
                "road": {"tk-Latn": "Magtymguly köçesi", "en": "Magtymguly Street"},
                "house_number": "19",
                "postcode": "745100",
            },
            "TM",
        )
        self.assertLess(
            result.native.lines.index("Balkan welaýaty"),
            result.native.lines.index("745100"),
        )
        self.assertEqual(result.native.lines[-1], "Türkmenistan")
        self.assertEqual(result.english.lines[-1], "Turkmenistan")


if __name__ == "__main__":
    unittest.main()
