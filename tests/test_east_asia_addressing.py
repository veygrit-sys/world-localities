"""Native-language and English East Asia address quality tests."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    EastAsiaRegistry,
    MissingLocalizedComponents,
    ProfileRegistry,
    render_address,
    render_bilingual_address,
)


class EastAsiaProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.east_asia = EastAsiaRegistry()

    def test_all_eight_country_and_area_profiles_have_native_and_english(self):
        expected = {
            "CN": ("CN_zh", "CN_en"),
            "HK": ("HK_zh", "HK_en"),
            "JP": ("JP_ja", "JP_en"),
            "KP": ("KP_ko", "KP_en"),
            "KR": ("KR_ko", "KR_en"),
            "MN": ("MN_mn", "MN_en"),
            "MO": ("MO_zh", "MO_en"),
            "TW": ("TW_zh", "TW_en"),
        }
        self.assertEqual(set(self.east_asia.countries), set(expected))
        for country, (native, english) in expected.items():
            with self.subTest(country=country):
                policy = self.east_asia.get(country)
                self.assertEqual(policy["native_profile"], native)
                self.assertEqual(
                    self.profiles.select(
                        country, language=policy["default_native_language"]
                    ).key,
                    native,
                )
                self.assertEqual(
                    self.profiles.select(country, international=True).key,
                    english,
                )

    def test_coverage_report_keeps_unverified_country_visible(self):
        self.assertEqual(
            self.east_asia.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-16",
                "countries": 8,
                "native_language_variants": 10,
                "english_profiles": 8,
                "provisional_countries": ["KP"],
            },
        )

    def test_macao_supports_chinese_portuguese_and_english(self):
        policy = self.east_asia.get("MO")
        self.assertEqual(policy["native_languages"], ["zh-Hant", "pt"])
        self.assertEqual(self.profiles.select("MO", language="pt").key, "MO_pt")
        self.assertEqual(self.profiles.select("MO", language="zh-Hant").key, "MO_zh")
        self.assertEqual(self.profiles.select("MO", language="en").key, "MO_en")

    def test_mongolia_keeps_cyrillic_and_traditional_script_distinct(self):
        policy = self.east_asia.get("MN")
        self.assertEqual(policy["native_languages"], ["mn-Cyrl", "mn-Mong"])
        result = render_bilingual_address(
            {"country_code": "MN", "house_number": "9"},
            "MN",
            native_language="mn-Mong",
        )
        self.assertEqual(result.native_language, "mn-Mong")
        self.assertIn("ᠮᠣᠩᠭᠣᠯ ᠤᠯᠤᠰ", result.native.lines)
        self.assertIn("Mongolia", result.english.lines)

    def test_every_policy_has_provenance_and_romanization_rule(self):
        for country, policy in self.east_asia.countries.items():
            with self.subTest(country=country):
                self.assertTrue(policy["sources"])
                self.assertTrue(policy["romanization_policy"])
                self.assertIn(
                    policy["evidence_status"], {"official_guidance", "provisional"}
                )


class BilingualRendering(unittest.TestCase):
    def test_japanese_and_english_outputs_use_explicit_language_values(self):
        result = render_bilingual_address(
            {
                "country_code": "JP",
                "recipient": {"ja": "山田太郎", "en": "Taro Yamada"},
                "postcode": "1000005",
                "state": {"ja": "東京都", "en": "Tokyo"},
                "city": {"ja": "千代田区", "en": "Chiyoda-ku"},
                "neighbourhood": {"ja": "丸の内", "en": "Marunouchi"},
                "road": {"ja": "丸の内", "en": "Marunouchi"},
                "house_number": "1-1",
                "house": {"ja": "新丸ビル", "en": "Shin-Marunouchi Building"},
                "address2": {"ja": "10階1001号室", "en": "Room 1001, 10F"},
            },
            "JP",
        )
        self.assertEqual(result.native.profile_key, "JP_ja")
        self.assertEqual(result.english.profile_key, "JP_en")
        self.assertIn("東京都", result.native.text)
        self.assertIn("Room 1001, 10F", result.english.lines)
        self.assertIn("Taro Yamada", result.english.lines)
        self.assertNotIn("東京都", result.english.text)
        self.assertFalse(result.native.unrendered_components)
        self.assertFalse(result.english.unrendered_components)

    def test_strict_mode_refuses_silent_native_to_english_fallback(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_bilingual_address(
                {
                    "country_code": "JP",
                    "postcode": "1000005",
                    "state": {"ja": "東京都"},
                    "city": {"ja": "千代田区"},
                    "house_number": "1-1",
                },
                "JP",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "state"))

    def test_english_label_rejects_non_latin_value(self):
        with self.assertRaisesRegex(ValueError, "not Latin-script: city"):
            render_bilingual_address(
                {
                    "country_code": "KR",
                    "city": {"ko": "서울특별시", "en": "서울특별시"},
                    "road": {"ko": "세종대로", "en": "Sejong-daero"},
                    "house_number": "110",
                },
                "KR",
            )

    def test_simplified_chinese_does_not_silently_fill_traditional_chinese(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_bilingual_address(
                {
                    "country_code": "TW",
                    "city": {"zh-Hans": "台北市", "en": "Taipei City"},
                    "house_number": "122",
                },
                "TW",
            )
        self.assertEqual(error.exception.language, "zh-Hant")
        self.assertEqual(error.exception.components, ("city",))

    def test_language_neutral_numbers_are_shared_without_translation(self):
        result = render_bilingual_address(
            {
                "country_code": "TW",
                "postcode": "100006",
                "city": {"zh-Hant": "臺北市", "en": "Taipei City"},
                "city_district": {"zh-Hant": "中正區", "en": "Zhongzheng District"},
                "road": {"zh-Hant": "重慶南路一段", "en": "Sec. 1, Chongqing S. Rd."},
                "house_number": "122",
            },
            "TW",
        )
        self.assertIn("100006", result.native.text)
        self.assertIn("100006", result.english.text)
        self.assertTrue(
            any(item.startswith("language_neutral_fallback:und") for item in result.warnings)
        )

    def test_macao_native_and_english_follow_opposite_information_order(self):
        result = render_bilingual_address(
            {
                "country_code": "MO",
                "recipient": {"zh-Hant": "吳小麗女士", "en": "Ms. Ng Sio Lai"},
                "road": {"zh-Hant": "葡京街", "en": "Rua Cidade de Lisboa"},
                "house_number": "130",
                "house": {"zh-Hant": "葡京花園B3棟", "en": "Lisboa Gardens, Tower B3"},
                "address2": {"zh-Hant": "14樓D座", "en": "14th Floor D"},
                "city_district": {"zh-Hant": "氹仔", "en": "Taipa"},
            },
            "MO",
        )
        self.assertEqual(result.native.lines[0], "澳門")
        self.assertEqual(result.native.lines[-1], "吳小麗女士")
        self.assertEqual(result.english.lines[0], "Ms. Ng Sio Lai")
        self.assertEqual(result.english.lines[-1], "Macao")

    def test_known_but_unused_components_are_reported(self):
        rendered = render_address(
            {
                "country_code": "JP",
                "country": "日本",
                "state": "東京都",
                "city": "千代田区",
                "place": "皇居外苑",
            },
            "JP",
            language="ja",
        )
        self.assertEqual(rendered.unrendered_components, {"place": "皇居外苑"})
        self.assertIn("unrendered_known_components", rendered.warnings)

    def test_provisional_north_korea_profile_never_looks_fully_verified(self):
        result = render_bilingual_address(
            {
                "country_code": "KP",
                "city": {"ko": "평양", "en": "Pyongyang"},
                "road": {"ko": "승리거리", "en": "Sungri Street"},
                "house_number": "1",
            },
            "KP",
        )
        self.assertIn("provisional_country_profile", result.warnings)


if __name__ == "__main__":
    unittest.main()
