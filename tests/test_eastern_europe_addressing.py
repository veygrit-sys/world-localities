"""Native-language and English Eastern Europe address quality tests."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    EasternEuropeRegistry,
    MissingLocalizedComponents,
    ProfileRegistry,
    render_eastern_europe_address,
)


class EasternEuropeProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.eastern_europe = EasternEuropeRegistry()

    def test_all_ten_countries_have_native_variants_and_english(self):
        expected = {
            "BG": ({"bg-Cyrl": "BG_bg"}, "BG_en"),
            "BY": ({"be-Cyrl": "BY_be", "ru-Cyrl": "BY_ru"}, "BY_en"),
            "CZ": ({"cs-Latn": "CZ_cs"}, "CZ_en"),
            "HU": ({"hu-Latn": "HU_hu"}, "HU_en"),
            "MD": (
                {
                    "ro-Latn": "MD_ro",
                    "ru-Cyrl": "MD_ru",
                    "uk-Cyrl": "MD_uk",
                    "gag-Latn": "MD_gag",
                },
                "MD_en",
            ),
            "PL": ({"pl-Latn": "PL_pl"}, "PL_en"),
            "RO": ({"ro-Latn": "RO_ro"}, "RO_en"),
            "RU": ({"ru-Cyrl": "RU_ru"}, "RU_en"),
            "SK": ({"sk-Latn": "SK_sk"}, "SK_en"),
            "UA": ({"uk-Cyrl": "UA_uk"}, "UA_en"),
        }
        self.assertEqual(set(self.eastern_europe.countries), set(expected))
        for country, (native_profiles, english_profile) in expected.items():
            with self.subTest(country=country):
                policy = self.eastern_europe.get(country)
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

    def test_coverage_report_has_no_provisional_country(self):
        self.assertEqual(
            self.eastern_europe.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-17",
                "countries": 10,
                "native_language_variants": 14,
                "english_profiles": 10,
                "provisional_countries": [],
            },
        )

    def test_every_language_has_script_and_every_country_has_provenance(self):
        for country, policy in self.eastern_europe.countries.items():
            with self.subTest(country=country):
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertEqual(policy["evidence_status"], "official_guidance")
                self.assertTrue(policy["sources"])
                self.assertTrue(policy["romanization_policy"])

    def test_country_outside_region_is_rejected(self):
        with self.assertRaisesRegex(KeyError, "outside Eastern Europe"):
            self.eastern_europe.get("DE")


class EasternEuropeBilingualRendering(unittest.TestCase):
    def test_bulgaria_keeps_cyrillic_and_inline_address2(self):
        result = render_eastern_europe_address(
            {
                "country_code": "BG",
                "road": {"bg-Cyrl": "ул. Оборище", "en": "Oborishte Street"},
                "house_number": "15",
                "address2": {"bg-Cyrl": "ет. 2 ап. 6", "en": "floor 2 apartment 6"},
                "city": {"bg-Cyrl": "СОФИЯ", "en": "SOFIA"},
                "postcode": "1000",
            },
            "BG",
        )
        self.assertIn("ул. Оборище 15, ет. 2 ап. 6", result.native.lines)
        self.assertIn("1000 СОФИЯ", result.native.lines)
        self.assertIn("Oborishte Street 15, floor 2 apartment 6", result.english.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_belarus_keeps_belarusian_and_russian_independent(self):
        components = {
            "country_code": "BY",
            "road": {
                "be-Cyrl": "вул. Кісялёва",
                "ru-Cyrl": "ул. Киселёва",
                "en": "Kiselyova Street",
            },
            "house_number": "14",
            "address2": {
                "be-Cyrl": "кв. 7",
                "ru-Cyrl": "кв. 7",
                "en": "apartment 7",
            },
            "city": {"be-Cyrl": "Мінск", "ru-Cyrl": "Минск", "en": "Minsk"},
            "postcode": "220005",
        }
        belarusian = render_eastern_europe_address(components, "BY")
        russian = render_eastern_europe_address(
            components, "BY", native_language="ru-Cyrl"
        )
        self.assertIn("вул. Кісялёва, 14, кв. 7", belarusian.native.lines)
        self.assertIn("220005, Мінск", belarusian.native.lines)
        self.assertIn("ул. Киселёва, 14, кв. 7", russian.native.lines)

    def test_czechia_formats_postcode_and_does_not_duplicate_place(self):
        result = render_eastern_europe_address(
            {
                "country_code": "CZ",
                "road": {"cs-Latn": "Novákových", "en": "Novakovych Street"},
                "house_number": "17/4",
                "address2": {"cs-Latn": "byt 5", "en": "apartment 5"},
                "place": {"cs-Latn": "PRAHA 8", "en": "PRAGUE 8"},
                "city": {"cs-Latn": "PRAHA", "en": "PRAGUE"},
                "postcode": "18000",
            },
            "CZ",
        )
        self.assertIn("Novákových 17/4", result.native.lines)
        self.assertIn("180 00 PRAHA", result.native.lines)
        self.assertEqual(result.native.lines.count("PRAHA 8"), 1)

    def test_hungary_keeps_city_first_and_postcode_last(self):
        result = render_eastern_europe_address(
            {
                "country_code": "HU",
                "city": {"hu-Latn": "BUDAPEST", "en": "BUDAPEST"},
                "road": {"hu-Latn": "Kossuth Lajos utca", "en": "Kossuth Lajos Street"},
                "house_number": "10",
                "address2": {"hu-Latn": "II. emelet 4.", "en": "floor 2 door 4"},
                "postcode": "1055",
            },
            "HU",
        )
        self.assertLess(
            result.native.lines.index("BUDAPEST"),
            result.native.lines.index("Kossuth Lajos utca 10 II. emelet 4."),
        )
        self.assertLess(
            result.native.lines.index("Kossuth Lajos utca 10 II. emelet 4."),
            result.native.lines.index("1055"),
        )

    def test_moldova_supports_domestic_languages_and_md_prefix(self):
        components = {
            "country_code": "MD",
            "road": {
                "ro-Latn": "str. Pușkin",
                "ru-Cyrl": "ул. Пушкина",
                "uk-Cyrl": "вул. Пушкіна",
                "gag-Latn": "Puşkin sokaağı",
                "en": "Pushkin Street",
            },
            "house_number": "22",
            "city": {
                "ro-Latn": "CHIȘINĂU",
                "ru-Cyrl": "КИШИНЭУ",
                "uk-Cyrl": "КИШИНЕУ",
                "gag-Latn": "KİŞİNÄU",
                "en": "CHISINAU",
            },
            "postcode": "2012",
        }
        romanian = render_eastern_europe_address(components, "MD")
        russian = render_eastern_europe_address(
            components, "MD", native_language="ru-Cyrl"
        )
        gagauz = render_eastern_europe_address(
            components, "MD", native_language="gag-Latn"
        )
        self.assertIn("MD-2012, CHIȘINĂU", romanian.native.lines)
        self.assertIn("ул. Пушкина, 22", russian.native.lines)
        self.assertIn("Puşkin sokaağı, 22", gagauz.native.lines)

    def test_poland_formats_postcode_and_keeps_apartment_inline(self):
        result = render_eastern_europe_address(
            {
                "country_code": "PL",
                "road": {"pl-Latn": "ul. Świętokrzyska", "en": "Swietokrzyska Street"},
                "house_number": "31",
                "address2": {"pl-Latn": "lok. 12", "en": "apartment 12"},
                "city": {"pl-Latn": "WARSZAWA", "en": "WARSAW"},
                "postcode": "00950",
            },
            "PL",
        )
        self.assertIn("ul. Świętokrzyska 31 lok. 12", result.native.lines)
        self.assertIn("00-950 WARSZAWA", result.native.lines)

    def test_romania_keeps_subpremise_sector_and_county(self):
        result = render_eastern_europe_address(
            {
                "country_code": "RO",
                "road": {"ro-Latn": "Strada Matei Basarab", "en": "Matei Basarab Street"},
                "house_number": "76",
                "address2": {"ro-Latn": "bl. L120 sc. A et. 4 ap. 20", "en": "building L120 entrance A floor 4 apartment 20"},
                "city_district": {"ro-Latn": "SECTOR 3", "en": "SECTOR 3"},
                "city": {"ro-Latn": "BUCUREȘTI", "en": "BUCHAREST"},
                "county": {"ro-Latn": "MUNICIPIUL BUCUREȘTI", "en": "BUCHAREST MUNICIPALITY"},
                "postcode": "030167",
            },
            "RO",
        )
        self.assertIn(
            "Strada Matei Basarab 76, bl. L120 sc. A et. 4 ap. 20",
            result.native.lines,
        )
        self.assertLess(
            result.native.lines.index("SECTOR 3"),
            result.native.lines.index("030167 BUCUREȘTI"),
        )
        self.assertLess(
            result.native.lines.index("030167 BUCUREȘTI"),
            result.native.lines.index("MUNICIPIUL BUCUREȘTI"),
        )

    def test_russia_keeps_postcode_as_final_line(self):
        result = render_eastern_europe_address(
            {
                "country_code": "RU",
                "road": {"ru-Cyrl": "ул. Мясницкая", "en": "Myasnitskaya Street"},
                "house_number": "26",
                "address2": {"ru-Cyrl": "стр. 1 кв. 12", "en": "building 1 apartment 12"},
                "city": {"ru-Cyrl": "Москва", "en": "Moscow"},
                "state": {"ru-Cyrl": "Москва", "en": "Moscow"},
                "postcode": "101000",
            },
            "RU",
        )
        self.assertIn("ул. Мясницкая, 26, стр. 1 кв. 12", result.native.lines)
        self.assertEqual(result.native.lines[-1], "101000")
        self.assertEqual(result.english.lines[-1], "101000")

    def test_slovakia_formats_postcode_and_keeps_place(self):
        result = render_eastern_europe_address(
            {
                "country_code": "SK",
                "road": {"sk-Latn": "Hlavná", "en": "Main Street"},
                "house_number": "15",
                "address2": {"sk-Latn": "byt 4", "en": "apartment 4"},
                "place": {"sk-Latn": "ZVOLEN 1", "en": "ZVOLEN 1"},
                "city": {"sk-Latn": "ZVOLEN", "en": "ZVOLEN"},
                "postcode": "96001",
            },
            "SK",
        )
        self.assertIn("Hlavná 15, byt 4", result.native.lines)
        self.assertIn("960 01 ZVOLEN", result.native.lines)
        self.assertIn("ZVOLEN 1", result.native.lines)

    def test_ukraine_keeps_postcode_below_region_and_country_last(self):
        result = render_eastern_europe_address(
            {
                "country_code": "UA",
                "road": {"uk-Cyrl": "вул. Хрещатик", "en": "Khreshchatyk Street"},
                "house_number": "22",
                "address2": {"uk-Cyrl": "кв. 14", "en": "apartment 14"},
                "city": {"uk-Cyrl": "Київ", "en": "Kyiv"},
                "state": {"uk-Cyrl": "Київська область", "en": "Kyiv Region"},
                "postcode": "01001",
            },
            "UA",
        )
        self.assertIn("вул. Хрещатик, 22, кв. 14", result.native.lines)
        self.assertLess(
            result.native.lines.index("Київська область"),
            result.native.lines.index("01001"),
        )
        self.assertEqual(result.native.lines[-1], "Україна")

    def test_native_cyrillic_rejects_latin_text(self):
        with self.assertRaisesRegex(ValueError, "not Cyrl-script: city"):
            render_eastern_europe_address(
                {
                    "country_code": "UA",
                    "city": {"uk-Cyrl": "Kyiv", "en": "Kyiv"},
                    "postcode": "01001",
                },
                "UA",
            )

    def test_latin_native_text_never_silently_fills_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_eastern_europe_address(
                {
                    "country_code": "PL",
                    "road": {"pl-Latn": "ul. Długa"},
                    "city": {"pl-Latn": "KRAKÓW"},
                    "postcode": "31000",
                },
                "PL",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "road"))


if __name__ == "__main__":
    unittest.main()
