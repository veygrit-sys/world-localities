"""Native-language and English Western Asia address quality tests."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    MissingLocalizedComponents,
    ProfileRegistry,
    WesternAsiaRegistry,
    render_western_asia_address,
)


class WesternAsiaProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.western_asia = WesternAsiaRegistry()

    def test_all_eighteen_countries_have_native_variants_and_english(self):
        expected = {
            "AE": ({"ar": "AE_ar"}, "AE_en"),
            "AM": ({"hy-Armn": "AM_hy"}, "AM_en"),
            "AZ": ({"az-Latn": "AZ_az"}, "AZ_en"),
            "BH": ({"ar": "BH_ar"}, "BH_en"),
            "CY": ({"el-Grek": "CY_el", "tr-Latn": "CY_tr"}, "CY_en"),
            "GE": ({"ka-Geor": "GE_ka"}, "GE_en"),
            "IL": ({"he-Hebr": "IL_he", "ar": "IL_ar"}, "IL_en"),
            "IQ": ({"ar": "IQ_ar", "ku-Arab": "IQ_ku"}, "IQ_en"),
            "JO": ({"ar": "JO_ar"}, "JO_en"),
            "KW": ({"ar": "KW_ar"}, "KW_en"),
            "LB": ({"ar": "LB_ar", "fr-Latn": "LB_fr"}, "LB_en"),
            "OM": ({"ar": "OM_ar"}, "OM_en"),
            "PS": ({"ar": "PS_ar"}, "PS_en"),
            "QA": ({"ar": "QA_ar"}, "QA_en"),
            "SA": ({"ar": "SA_ar"}, "SA_en"),
            "SY": ({"ar": "SY_ar"}, "SY_en"),
            "TR": ({"tr-Latn": "TR_tr"}, "TR_en"),
            "YE": ({"ar": "YE_ar"}, "YE_en"),
        }
        self.assertEqual(set(self.western_asia.countries), set(expected))
        for country, (native_profiles, english_profile) in expected.items():
            with self.subTest(country=country):
                policy = self.western_asia.get(country)
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

    def test_coverage_report_preserves_evidence_gaps(self):
        self.assertEqual(
            self.western_asia.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-16",
                "countries": 18,
                "native_language_variants": 22,
                "english_profiles": 18,
                "provisional_countries": ["AE", "IQ", "JO", "KW", "SY", "YE"],
            },
        )

    def test_every_native_language_has_script_and_provenance(self):
        for country, policy in self.western_asia.countries.items():
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


class WesternAsiaBilingualRendering(unittest.TestCase):
    def test_armenia_domestic_and_international_orders_are_distinct(self):
        result = render_western_asia_address(
            {
                "country_code": "AM",
                "road": {"hy-Armn": "Սարյան փողոց", "en": "Saryan Street"},
                "house_number": "22",
                "address2": {"hy-Armn": "բնակարան 25", "en": "Apartment 25"},
                "city": {"hy-Armn": "Երևան", "en": "Yerevan"},
                "postcode": "0002",
            },
            "AM",
        )
        self.assertEqual(result.native.profile_key, "AM_hy")
        self.assertEqual(result.english.profile_key, "AM_en")
        self.assertEqual(result.native.lines[-1], "0002")
        self.assertIn("0002 Yerevan", result.english.lines)
        self.assertEqual(result.english.lines[-1], "Armenia")
        self.assertIn("բնակարան 25", result.native.lines)
        self.assertIn("Apartment 25", result.english.lines)

    def test_azerbaijan_preserves_iso_prefixed_postcode(self):
        result = render_western_asia_address(
            {
                "country_code": "AZ",
                "road": {"az-Latn": "Zərifə Əliyeva küçəsi", "en": "Zarifa Aliyeva Street"},
                "house_number": "9",
                "city": {"az-Latn": "Bakı", "en": "Baku"},
                "postcode": "AZ1010",
            },
            "AZ",
        )
        self.assertIn("AZ1010 Bakı", result.native.lines)
        self.assertIn("AZ1010 Baku", result.english.lines)

    def test_bahrain_places_three_digit_postcode_after_locality(self):
        result = render_western_asia_address(
            {
                "country_code": "BH",
                "house": {"ar": "منزل", "en": "House"},
                "house_number": "888",
                "road": {"ar": "طريق الشيخ عبد الله", "en": "Sheikh Abdulla Road"},
                "city": {"ar": "المنامة", "en": "Manama"},
                "postcode": "317",
            },
            "BH",
        )
        self.assertIn("المنامة 317", result.native.lines)
        self.assertIn("Manama 317", result.english.lines)

    def test_cyprus_greek_turkish_and_english_are_distinct(self):
        components = {
            "country_code": "CY",
            "road": {
                "el-Grek": "Σοφοκλέους",
                "tr-Latn": "Atatürk Caddesi",
                "en": "Sofocleous Street",
            },
            "house_number": "26",
            "city": {
                "el-Grek": "Στρόβολος",
                "tr-Latn": "Lefkoşa",
                "en": "Strovolos",
            },
            "postcode": "CY-2008",
        }
        greek = render_western_asia_address(components, "CY")
        turkish = render_western_asia_address(
            components, "CY", native_language="tr-Latn"
        )
        self.assertEqual(greek.native.profile_key, "CY_el")
        self.assertEqual(turkish.native.profile_key, "CY_tr")
        self.assertIn("CY-2008 Στρόβολος", greek.native.lines)
        self.assertIn("CY-2008 Lefkoşa", turkish.native.lines)
        self.assertIn("CY-2008 Strovolos", greek.english.lines)

    def test_georgian_script_is_validated(self):
        with self.assertRaisesRegex(ValueError, "not Geor-script: city"):
            render_western_asia_address(
                {
                    "country_code": "GE",
                    "city": {"ka-Geor": "Tbilisi", "en": "Tbilisi"},
                    "postcode": "0160",
                },
                "GE",
            )

    def test_israel_hebrew_and_arabic_profiles_are_distinct(self):
        components = {
            "country_code": "IL",
            "road": {"he-Hebr": "רחוב יפו", "ar": "شارع يافا", "en": "Yafo Street"},
            "house_number": "16",
            "city": {"he-Hebr": "ירושלים", "ar": "القدس", "en": "Jerusalem"},
            "postcode": "9414219",
        }
        hebrew = render_western_asia_address(components, "IL")
        arabic = render_western_asia_address(components, "IL", native_language="ar")
        self.assertEqual(hebrew.native.profile_key, "IL_he")
        self.assertEqual(arabic.native.profile_key, "IL_ar")
        self.assertIn("9414219 ירושלים", hebrew.native.lines)
        self.assertIn("9414219 القدس", arabic.native.lines)

    def test_iraqi_arabic_does_not_fill_kurdish(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_western_asia_address(
                {
                    "country_code": "IQ",
                    "road": {"ar": "شارع القهوة", "en": "Qahwa Street"},
                    "house_number": "10",
                    "postcode": "61002",
                },
                "IQ",
                native_language="ku-Arab",
            )
        self.assertEqual(error.exception.language, "ku-Arab")
        self.assertEqual(error.exception.components, ("road",))

    def test_lebanese_french_is_not_silently_used_as_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_western_asia_address(
                {
                    "country_code": "LB",
                    "road": {"fr-Latn": "Rue d’Australie"},
                    "city": {"fr-Latn": "Beyrouth"},
                },
                "LB",
                native_language="fr-Latn",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "road"))

    def test_oman_keeps_postcode_on_separate_line(self):
        result = render_western_asia_address(
            {
                "country_code": "OM",
                "po_box": {"ar": "صندوق بريد 15", "en": "P.O. Box 15"},
                "city": {"ar": "الخوير", "en": "Al-Khuwair"},
                "postcode": "133",
            },
            "OM",
        )
        self.assertIn("133", result.native.lines)
        self.assertLess(result.native.lines.index("133"), result.native.lines.index("الخوير"))
        self.assertLess(result.english.lines.index("133"), result.english.lines.index("Al-Khuwair"))

    def test_palestine_preserves_new_eight_character_postcode(self):
        result = render_western_asia_address(
            {
                "country_code": "PS",
                "road": {"ar": "شارع المطران", "en": "Almataran Street"},
                "town": {"ar": "الرام", "en": "Ar Ram"},
                "city": {"ar": "القدس", "en": "Jerusalem"},
                "postcode": "P6100154",
            },
            "PS",
        )
        self.assertIn("القدس P6100154", result.native.lines)
        self.assertIn("Jerusalem P6100154", result.english.lines)

    def test_qatar_does_not_invent_a_postcode(self):
        result = render_western_asia_address(
            {
                "country_code": "QA",
                "po_box": {"ar": "صندوق بريد 3263", "en": "P.O. Box 3263"},
                "city": {"ar": "الدوحة", "en": "Doha"},
            },
            "QA",
        )
        self.assertNotIn("postcode", result.native.components)
        self.assertEqual(result.native.lines[-2:], ("الدوحة", "قطر"))
        self.assertEqual(result.english.lines[-2:], ("Doha", "Qatar"))

    def test_saudi_address2_and_national_address_order_are_retained(self):
        result = render_western_asia_address(
            {
                "country_code": "SA",
                "road": {"ar": "طريق الملك عبدالعزيز", "en": "King Abdulaziz Road"},
                "house_number": "8228",
                "address2": {"ar": "الوحدة 18", "en": "Unit 18"},
                "neighbourhood": {"ar": "حي الأمل 2121", "en": "2121 Alamal District"},
                "city": {"ar": "الرياض", "en": "Riyadh"},
                "postcode": "12643",
            },
            "SA",
        )
        self.assertIn("الوحدة 18", result.native.lines)
        self.assertIn("Unit 18", result.english.lines)
        self.assertLess(result.native.lines.index("12643"), result.native.lines.index("الرياض"))
        self.assertFalse(result.native.unrendered_components)
        self.assertFalse(result.english.unrendered_components)

    def test_turkiye_keeps_address2_and_locality_province_separator(self):
        result = render_western_asia_address(
            {
                "country_code": "TR",
                "neighbourhood": {"tr-Latn": "Doğanbey Mahallesi", "en": "Doganbey Neighbourhood"},
                "road": {"tr-Latn": "Şehitteğmenkalmaz Caddesi", "en": "Sehittegmenkalmaz Avenue"},
                "house_number": "28/A",
                "address2": {"tr-Latn": "3. kat, daire 8", "en": "Floor 3, Unit 8"},
                "city_district": {"tr-Latn": "Ulus", "en": "Ulus"},
                "state": {"tr-Latn": "Ankara", "en": "Ankara"},
                "postcode": "06101",
            },
            "TR",
        )
        self.assertIn("06101 Ulus/Ankara", result.native.lines)
        self.assertIn("3. kat, daire 8", result.native.lines)
        self.assertIn("Floor 3, Unit 8", result.english.lines)

    def test_provisional_profiles_always_warn(self):
        result = render_western_asia_address(
            {
                "country_code": "SY",
                "city": {"ar": "دمشق", "en": "Damascus"},
            },
            "SY",
        )
        self.assertIn("provisional_country_profile", result.warnings)

    def test_english_label_rejects_arabic_text(self):
        with self.assertRaisesRegex(ValueError, "not Latin-script: city"):
            render_western_asia_address(
                {
                    "country_code": "JO",
                    "city": {"ar": "عمّان", "en": "عمّان"},
                    "postcode": "11937",
                },
                "JO",
            )


if __name__ == "__main__":
    unittest.main()
