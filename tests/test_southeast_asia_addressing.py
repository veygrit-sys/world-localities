"""Native-language and English Southeast Asia address quality tests."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    MissingLocalizedComponents,
    ProfileRegistry,
    SoutheastAsiaRegistry,
    render_southeast_asia_address,
)


class SoutheastAsiaProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.southeast_asia = SoutheastAsiaRegistry()

    def test_all_eleven_countries_have_every_native_variant_and_english(self):
        expected = {
            "BN": ({"ms": "BN_ms"}, "BN_en"),
            "KH": ({"km": "KH_km"}, "KH_en"),
            "ID": ({"id": "ID_id"}, "ID_en"),
            "LA": ({"lo": "LA_lo"}, "LA_en"),
            "MY": ({"ms": "MY_ms"}, "MY_en"),
            "MM": ({"my": "MM_my"}, "MM_en"),
            "PH": ({"fil": "PH_fil"}, "PH_en"),
            "SG": (
                {"ms": "SG_ms", "zh-Hans": "SG_zh", "ta": "SG_ta"},
                "SG_en",
            ),
            "TH": ({"th": "TH_th"}, "TH_en"),
            "TL": ({"tet": "TL_tet", "pt": "TL_pt"}, "TL_en"),
            "VN": ({"vi": "VN_vi"}, "VN_en"),
        }
        self.assertEqual(set(self.southeast_asia.countries), set(expected))
        for country, (native_profiles, english_profile) in expected.items():
            with self.subTest(country=country):
                policy = self.southeast_asia.get(country)
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

    def test_coverage_report_keeps_provisional_countries_visible(self):
        self.assertEqual(
            self.southeast_asia.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-16",
                "countries": 11,
                "native_language_variants": 14,
                "english_profiles": 11,
                "provisional_countries": ["MM", "TL"],
            },
        )

    def test_singapore_and_timor_leste_keep_multilingual_profiles_distinct(self):
        self.assertEqual(
            self.southeast_asia.get("SG")["native_languages"],
            ["ms", "zh-Hans", "ta"],
        )
        self.assertEqual(
            self.southeast_asia.get("TL")["native_languages"],
            ["tet", "pt"],
        )
        self.assertEqual(self.profiles.select("SG", language="ta").key, "SG_ta")
        self.assertEqual(self.profiles.select("TL", language="pt").key, "TL_pt")

    def test_every_policy_has_sources_and_a_romanization_rule(self):
        for country, policy in self.southeast_asia.countries.items():
            with self.subTest(country=country):
                self.assertTrue(policy["sources"])
                self.assertTrue(policy["romanization_policy"])
                self.assertIn(
                    policy["evidence_status"],
                    {"official_guidance", "source_derived_domestic", "provisional"},
                )


class SoutheastAsiaBilingualRendering(unittest.TestCase):
    def test_thai_and_english_outputs_keep_address2_and_line_order(self):
        result = render_southeast_asia_address(
            {
                "country_code": "TH",
                "recipient": {"th": "สมชาย ใจดี", "en": "Somchai Jaidee"},
                "house_number": "491",
                "road": {
                    "th": "ถนนรังสิต-นครนายก 4",
                    "en": "Rangsit-Nakhon Nayok 4 Road",
                },
                "neighbourhood": {"th": "ประชาธิปัตย์", "en": "Prachathipat"},
                "city_district": {"th": "ธัญบุรี", "en": "Thanyaburi District"},
                "state": {"th": "ปทุมธานี", "en": "Pathum Thani"},
                "postcode": "12130",
                "address2": {"th": "ชั้น 6 ห้อง 7", "en": "Floor 6, Room 7"},
            },
            "TH",
        )
        self.assertEqual(result.native.profile_key, "TH_th")
        self.assertEqual(result.english.profile_key, "TH_en")
        self.assertIn("ชั้น 6 ห้อง 7", result.native.lines)
        self.assertIn("Floor 6, Room 7", result.english.lines)
        self.assertEqual(result.native.lines[-1], "ประเทศไทย")
        self.assertEqual(result.english.lines[-1], "Thailand")
        self.assertFalse(result.native.unrendered_components)
        self.assertFalse(result.english.unrendered_components)

    def test_strict_mode_refuses_silent_burmese_to_english_fallback(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_southeast_asia_address(
                {
                    "country_code": "MM",
                    "city": {"my": "ရန်ကုန်"},
                    "road": {"my": "ကုန်သည်လမ်း"},
                    "house_number": "10",
                },
                "MM",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "road"))

    def test_english_label_rejects_non_latin_thai_value(self):
        with self.assertRaisesRegex(ValueError, "not Latin-script: road"):
            render_southeast_asia_address(
                {
                    "country_code": "TH",
                    "road": {"th": "ถนนสีลม", "en": "ถนนสีลม"},
                    "house_number": "1",
                },
                "TH",
            )

    def test_traditional_chinese_does_not_fill_singapore_simplified_chinese(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_southeast_asia_address(
                {
                    "country_code": "SG",
                    "road": {"zh-Hant": "烏節路", "en": "Orchard Road"},
                    "house_number": "1",
                    "postcode": "238823",
                },
                "SG",
                native_language="zh-Hans",
            )
        self.assertEqual(error.exception.language, "zh-Hans")
        self.assertEqual(error.exception.components, ("road",))

    def test_latin_script_malay_is_not_silently_relabelled_as_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_southeast_asia_address(
                {
                    "country_code": "MY",
                    "road": {"ms": "Jalan Tun Razak"},
                    "house_number": "1",
                    "postcode": "50400",
                },
                "MY",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("road",))

    def test_singapore_address2_uses_official_unit_position(self):
        result = render_southeast_asia_address(
            {
                "country_code": "SG",
                "organization": {
                    "ms": "Singapore Post Limited",
                    "en": "Singapore Post Limited",
                },
                "house_number": "10",
                "road": {"ms": "Eunos Road 8", "en": "Eunos Road 8"},
                "address2": {"ms": "#01-38", "en": "#01-38"},
                "house": {
                    "ms": "Singapore Post Centre",
                    "en": "Singapore Post Centre",
                },
                "postcode": "408600",
            },
            "SG",
        )
        self.assertIn("#01-38 Singapore Post Centre", result.english.lines)
        self.assertEqual(result.english.lines[-1], "Singapore 408600")
        self.assertNotIn("generic_subpremise_placement", result.english.warnings)

    def test_structured_block_floor_and_unit_are_not_reported_as_dropped(self):
        result = render_southeast_asia_address(
            {
                "country_code": "PH",
                "house_number": "12",
                "road": {"fil": "Rizal Street", "en": "Rizal Street"},
                "block": {"fil": "Block A", "en": "Block A"},
                "floor": {"fil": "Ika-4 na palapag", "en": "4th Floor"},
                "unit": {"fil": "Yunit 2", "en": "Unit 2"},
                "city": {"fil": "Lungsod Quezon", "en": "Quezon City"},
                "postcode": "1100",
            },
            "PH",
        )
        self.assertIn("Block A 4th Floor Unit 2", result.english.lines)
        self.assertFalse(result.english.unrendered_components)
        self.assertFalse(result.native.unrendered_components)

    def test_provisional_profiles_are_never_presented_as_fully_verified(self):
        result = render_southeast_asia_address(
            {
                "country_code": "TL",
                "city": {"tet": "Díli", "en": "Dili"},
                "road": {
                    "tet": "Avenida Nicolau Lobato",
                    "en": "Nicolau Lobato Avenue",
                },
                "house_number": "1",
            },
            "TL",
        )
        self.assertIn("provisional_country_profile", result.warnings)

    def test_country_code_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            render_southeast_asia_address(
                {"country_code": "VN", "house_number": "1"},
                "TH",
            )


if __name__ == "__main__":
    unittest.main()
