"""Native-language and English Southern Asia address quality tests."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    MissingLocalizedComponents,
    ProfileRegistry,
    SouthAsiaRegistry,
    render_south_asia_address,
)


class SouthAsiaProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.south_asia = SouthAsiaRegistry()

    def test_all_nine_countries_have_every_native_variant_and_english(self):
        expected = {
            "AF": ({"fa-AF": "AF_fa", "ps": "AF_ps"}, "AF_en"),
            "BD": ({"bn": "BD_bn"}, "BD_en"),
            "BT": ({"dz": "BT_dz"}, "BT_en"),
            "IN": ({"hi": "IN_hi"}, "IN_en"),
            "IR": ({"fa": "IR_fa"}, "IR_en"),
            "LK": ({"si": "LK_si", "ta": "LK_ta"}, "LK_en"),
            "MV": ({"dv": "MV_dv"}, "MV_en"),
            "NP": ({"ne": "NP_ne"}, "NP_en"),
            "PK": ({"ur": "PK_ur"}, "PK_en"),
        }
        self.assertEqual(set(self.south_asia.countries), set(expected))
        for country, (native_profiles, english_profile) in expected.items():
            with self.subTest(country=country):
                policy = self.south_asia.get(country)
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

    def test_coverage_report_keeps_postcode_transition_visible(self):
        self.assertEqual(
            self.south_asia.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-16",
                "countries": 9,
                "native_language_variants": 11,
                "english_profiles": 9,
                "provisional_countries": ["NP"],
            },
        )

    def test_afghanistan_and_sri_lanka_keep_native_languages_distinct(self):
        self.assertEqual(
            self.south_asia.get("AF")["native_languages"],
            ["fa-AF", "ps"],
        )
        self.assertEqual(
            self.south_asia.get("LK")["native_languages"],
            ["si", "ta"],
        )
        self.assertEqual(self.profiles.select("AF", language="ps").key, "AF_ps")
        self.assertEqual(self.profiles.select("LK", language="ta").key, "LK_ta")

    def test_every_native_language_has_script_and_provenance(self):
        for country, policy in self.south_asia.countries.items():
            with self.subTest(country=country):
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertTrue(policy["sources"])
                self.assertTrue(policy["romanization_policy"])
                self.assertIn(
                    policy["evidence_status"],
                    {"official_guidance", "source_derived_domestic", "provisional"},
                )


class SouthAsiaBilingualRendering(unittest.TestCase):
    def test_india_hindi_and_english_keep_address2_and_official_order(self):
        result = render_south_asia_address(
            {
                "country_code": "IN",
                "recipient": {"hi": "राजीव रतन", "en": "Rajiv Rattan"},
                "house_number": "4",
                "road": {
                    "hi": "अमृता शेरगिल मार्ग",
                    "en": "Amrita Shergill Road",
                },
                "address2": {"hi": "फ्लैट ४०८", "en": "Flat 408"},
                "city": {"hi": "नई दिल्ली", "en": "New Delhi"},
                "state": {"hi": "दिल्ली", "en": "Delhi"},
                "postcode": "110003",
            },
            "IN",
        )
        self.assertEqual(result.native.profile_key, "IN_hi")
        self.assertEqual(result.english.profile_key, "IN_en")
        self.assertIn("फ्लैट ४०८", result.native.lines)
        self.assertIn("Flat 408", result.english.lines)
        self.assertLess(
            result.english.lines.index("Delhi"),
            result.english.lines.index("110003"),
        )
        self.assertEqual(result.english.lines[-1], "India")
        self.assertFalse(result.native.unrendered_components)
        self.assertFalse(result.english.unrendered_components)

    def test_strict_mode_refuses_bengali_to_english_fallback(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_south_asia_address(
                {
                    "country_code": "BD",
                    "city": {"bn": "ঢাকা"},
                    "road": {"bn": "ধানমন্ডি সড়ক"},
                    "house_number": "10",
                    "postcode": "1209",
                },
                "BD",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "road"))

    def test_native_script_validation_rejects_latin_text_labelled_urdu(self):
        with self.assertRaisesRegex(ValueError, "not Arab-script: road"):
            render_south_asia_address(
                {
                    "country_code": "PK",
                    "road": {"ur": "Main Road", "en": "Main Road"},
                    "house_number": "17",
                    "city": {"ur": "اسلام آباد", "en": "Islamabad"},
                    "postcode": "44000",
                },
                "PK",
            )

    def test_english_label_rejects_persian_script(self):
        with self.assertRaisesRegex(ValueError, "not Latin-script: city"):
            render_south_asia_address(
                {
                    "country_code": "IR",
                    "city": {"fa": "تهران", "en": "تهران"},
                    "house_number": "12",
                    "postcode": "1619614153",
                },
                "IR",
            )

    def test_dangerous_bidirectional_override_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "bidirectional control"):
            render_south_asia_address(
                {
                    "country_code": "PK",
                    "road": {
                        "ur": "مین روڈ\u202eabc",
                        "en": "Main Road",
                    },
                    "house_number": "1",
                },
                "PK",
            )

    def test_pashto_does_not_fill_dari_even_with_the_same_script(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_south_asia_address(
                {
                    "country_code": "AF",
                    "road": {"ps": "د کابل سړک", "en": "Kabul Road"},
                    "house_number": "16",
                    "postcode": "100208",
                },
                "AF",
                native_language="fa-AF",
            )
        self.assertEqual(error.exception.language, "fa-AF")
        self.assertEqual(error.exception.components, ("road",))

    def test_tamil_does_not_fill_sinhala(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_south_asia_address(
                {
                    "country_code": "LK",
                    "city": {"ta": "கொழும்பு", "en": "Colombo"},
                    "house_number": "10",
                    "postcode": "00100",
                },
                "LK",
                native_language="si",
            )
        self.assertEqual(error.exception.language, "si")
        self.assertEqual(error.exception.components, ("city",))

    def test_iran_preserves_ten_digit_postcode_as_language_neutral(self):
        result = render_south_asia_address(
            {
                "country_code": "IR",
                "city": {"fa": "تهران", "en": "Tehran"},
                "road": {"fa": "خیابان ۱۹۶ غربی", "en": "West 196 Street"},
                "house_number": "12",
                "postcode": "1619614153",
            },
            "IR",
        )
        self.assertIn("1619614153", result.native.lines)
        self.assertIn("1619614153", result.english.lines)
        self.assertEqual(result.native.profile_key, "IR_fa")
        self.assertEqual(result.english.profile_key, "IR_en")

    def test_nepal_postcode_transition_is_always_visible(self):
        result = render_south_asia_address(
            {
                "country_code": "NP",
                "city": {"ne": "भरतपुर", "en": "Bharatpur"},
                "municipality": {"ne": "भरतपुर महानगरपालिका", "en": "Bharatpur Metropolitan City"},
                "road": {"ne": "मुख्य मार्ग", "en": "Main Road"},
                "house_number": "1",
                "postcode": "3130401",
            },
            "NP",
        )
        self.assertIn("provisional_country_profile", result.warnings)


if __name__ == "__main__":
    unittest.main()
