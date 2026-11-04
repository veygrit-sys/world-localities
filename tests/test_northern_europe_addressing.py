"""Native-language and English Northern Europe address quality tests."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    MissingLocalizedComponents,
    NorthernEuropeRegistry,
    ProfileRegistry,
    render_northern_europe_address,
)


class NorthernEuropeProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.northern_europe = NorthernEuropeRegistry()

    def test_all_sixteen_countries_and_territories_have_native_and_english_profiles(self):
        expected = {
            "AX": ({"sv-Latn": "AX_sv", "fi-Latn": "AX_fi"}, "AX_en"),
            "DK": ({"da-Latn": "DK_da"}, "DK_en"),
            "EE": ({"et-Latn": "EE_et"}, "EE_en"),
            "FI": ({"fi-Latn": "FI_fi", "sv-Latn": "FI_sv"}, "FI_en"),
            "FO": ({"fo-Latn": "FO_fo", "da-Latn": "FO_da"}, "FO_en"),
            "GB": (
                {
                    "en": "GB_en",
                    "cy-Latn": "GB_cy",
                    "gd-Latn": "GB_gd",
                    "ga-Latn": "GB_ga",
                },
                "GB_en",
            ),
            "GG": ({"en": "GG_en", "nrf-Latn": "GG_nrf"}, "GG_en"),
            "IE": ({"en": "IE_en", "ga-Latn": "IE_ga"}, "IE_en"),
            "IM": ({"en": "IM_en", "gv-Latn": "IM_gv"}, "IM_en"),
            "IS": ({"is-Latn": "IS_is"}, "IS_en"),
            "JE": (
                {"en": "JE_en", "fr-Latn": "JE_fr", "nrf-Latn": "JE_nrf"},
                "JE_en",
            ),
            "LT": ({"lt-Latn": "LT_lt"}, "LT_en"),
            "LV": ({"lv-Latn": "LV_lv"}, "LV_en"),
            "NO": (
                {
                    "nb-Latn": "NO_nb",
                    "nn-Latn": "NO_nn",
                    "se-Latn": "NO_se",
                    "sma-Latn": "NO_sma",
                    "smj-Latn": "NO_smj",
                },
                "NO_en",
            ),
            "SE": ({"sv-Latn": "SE_sv"}, "SE_en"),
            "SJ": ({"nb-Latn": "SJ_nb", "nn-Latn": "SJ_nn"}, "SJ_en"),
        }
        self.assertEqual(set(self.northern_europe.countries), set(expected))
        for country, (native_profiles, english_profile) in expected.items():
            with self.subTest(country=country):
                policy = self.northern_europe.get(country)
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

    def test_coverage_report_keeps_source_derived_sj_out_of_provisional(self):
        self.assertEqual(
            self.northern_europe.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-17",
                "countries": 16,
                "native_language_variants": 32,
                "english_profiles": 16,
                "provisional_countries": [],
            },
        )

    def test_every_language_has_script_and_every_country_has_provenance(self):
        for country, policy in self.northern_europe.countries.items():
            with self.subTest(country=country):
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertTrue(policy["sources"])
                self.assertTrue(policy["romanization_policy"])

    def test_country_outside_region_is_rejected(self):
        with self.assertRaisesRegex(KeyError, "outside Northern Europe"):
            self.northern_europe.get("DE")


class NorthernEuropeBilingualRendering(unittest.TestCase):
    def test_aland_normalizes_ax_prefix_and_keeps_swedish_and_finnish_separate(self):
        components = {
            "country_code": "AX",
            "road": {"sv-Latn": "Postgränd", "fi-Latn": "Postikuja", "en": "Post Alley"},
            "house_number": "8",
            "address2": {"sv-Latn": "B", "fi-Latn": "B", "en": "B"},
            "city": {"sv-Latn": "MARIEHAMN", "fi-Latn": "MAARIANHAMINA", "en": "MARIEHAMN"},
            "postcode": "22100",
        }
        swedish = render_northern_europe_address(components, "AX")
        finnish = render_northern_europe_address(
            components, "AX", native_language="fi-Latn"
        )
        self.assertIn("Postgränd 8 B", swedish.native.lines)
        self.assertIn("AX-22100 MARIEHAMN", swedish.native.lines)
        self.assertIn("Postikuja 8 B", finnish.native.lines)

    def test_denmark_keeps_floor_on_street_delivery_line(self):
        result = render_northern_europe_address(
            {
                "country_code": "DK",
                "road": {"da-Latn": "Kastanievej", "en": "Kastanievej"},
                "house_number": "15",
                "address2": {"da-Latn": "2. sal", "en": "second floor"},
                "city": {"da-Latn": "SKANDERBORG", "en": "SKANDERBORG"},
                "postcode": "8660",
            },
            "DK",
        )
        self.assertIn("Kastanievej 15, 2. sal", result.native.lines)
        self.assertIn("8660 SKANDERBORG", result.native.lines)

    def test_estonia_keeps_apartment_suffix_and_rural_hierarchy(self):
        result = render_northern_europe_address(
            {
                "country_code": "EE",
                "road": {"et-Latn": "Astri", "en": "Astri Street"},
                "house_number": "6",
                "address2": {"et-Latn": "–1", "en": "–1"},
                "city": {"et-Latn": "TALLINN", "en": "TALLINN"},
                "postcode": "11212",
            },
            "EE",
        )
        self.assertIn("Astri 6–1", result.native.lines)
        self.assertIn("11212 TALLINN", result.native.lines)

    def test_faroe_islands_normalizes_prefix_and_supports_faroese_and_danish(self):
        components = {
            "country_code": "FO",
            "road": {"fo-Latn": "Óðinshædd", "da-Latn": "Odinshøj", "en": "Odin Hill"},
            "house_number": "2",
            "city": {"fo-Latn": "Tórshavn", "da-Latn": "Thorshavn", "en": "Torshavn"},
            "postcode": "100",
        }
        faroese = render_northern_europe_address(components, "FO")
        danish = render_northern_europe_address(
            components, "FO", native_language="da-Latn"
        )
        self.assertIn("FO-100 Tórshavn", faroese.native.lines)
        self.assertIn("Odinshøj 2", danish.native.lines)

    def test_finland_keeps_entrance_and_apartment_inline_in_two_languages(self):
        components = {
            "country_code": "FI",
            "road": {"fi-Latn": "Mäkelänkatu", "sv-Latn": "Backasgatan", "en": "Makela Street"},
            "house_number": "25",
            "address2": {"fi-Latn": "B 13", "sv-Latn": "B 13", "en": "B 13"},
            "city": {"fi-Latn": "HELSINKI", "sv-Latn": "HELSINGFORS", "en": "HELSINKI"},
            "postcode": "00550",
        }
        finnish = render_northern_europe_address(components, "FI")
        swedish = render_northern_europe_address(
            components, "FI", native_language="sv-Latn"
        )
        self.assertIn("Mäkelänkatu 25 B 13", finnish.native.lines)
        self.assertIn("00550 HELSINGFORS", swedish.native.lines)

    def test_guernsey_keeps_island_and_postcode_lines_distinct(self):
        result = render_northern_europe_address(
            {
                "country_code": "GG",
                "road": {"en": "La Vrangue"},
                "city": {"en": "St Peter Port"},
                "postcode": "GY11AA",
            },
            "GG",
        )
        self.assertLess(result.native.lines.index("Guernsey"), result.native.lines.index("GY1 1AA"))
        self.assertEqual(result.native.profile_key, "GG_en")

    def test_iceland_keeps_three_digit_postcode_before_locality(self):
        result = render_northern_europe_address(
            {
                "country_code": "IS",
                "road": {"is-Latn": "Tryggvagata", "en": "Tryggvagata"},
                "house_number": "5",
                "city": {"is-Latn": "HAFNARFIRÐI", "en": "HAFNARFJORDUR"},
                "postcode": "220",
            },
            "IS",
        )
        self.assertIn("220 HAFNARFIRÐI", result.native.lines)

    def test_ireland_normalizes_eircode_and_keeps_irish_independent(self):
        components = {
            "country_code": "IE",
            "road": {"en": "Broomfield", "ga-Latn": "Gort na Scuab"},
            "house_number": "56",
            "city": {"en": "MACROOM", "ga-Latn": "MAIGH CHROMTHA"},
            "county": {"en": "CO. CORK", "ga-Latn": "CO. CHORCAÍ"},
            "postcode": "T37F8HK",
        }
        english = render_northern_europe_address(components, "IE")
        irish = render_northern_europe_address(
            components, "IE", native_language="ga-Latn"
        )
        self.assertIn("T37 F8HK", english.native.lines)
        self.assertIn("56 Gort na Scuab", irish.native.lines)

    def test_isle_of_man_supports_manx_and_keeps_im_postcode_separate(self):
        components = {
            "country_code": "IM",
            "road": {"en": "Athol Street", "gv-Latn": "Straid Athol"},
            "house_number": "2",
            "city": {"en": "DOUGLAS", "gv-Latn": "DOOLISH"},
            "postcode": "IM991AN",
        }
        manx = render_northern_europe_address(
            components, "IM", native_language="gv-Latn"
        )
        self.assertIn("2 Straid Athol", manx.native.lines)
        self.assertIn("IM99 1AN", manx.native.lines)

    def test_jersey_supports_english_french_and_jerriais(self):
        components = {
            "country_code": "JE",
            "road": {"en": "La Route de Saint-Aubin", "fr-Latn": "Route de Saint-Aubin", "nrf-Latn": "La Route dé Saint Aubîn"},
            "house_number": "12",
            "place": {"en": "St Helier", "fr-Latn": "Saint-Hélier", "nrf-Latn": "Saint Hélyi"},
            "postcode": "JE23AA",
        }
        french = render_northern_europe_address(
            components, "JE", native_language="fr-Latn"
        )
        jerriais = render_northern_europe_address(
            components, "JE", native_language="nrf-Latn"
        )
        self.assertIn("Saint-Hélier", french.native.lines)
        self.assertIn("12 La Route dé Saint Aubîn", jerriais.native.lines)
        self.assertIn("JE2 3AA", jerriais.native.lines)

    def test_latvia_places_prefixed_postcode_to_right_of_locality(self):
        result = render_northern_europe_address(
            {
                "country_code": "LV",
                "road": {"lv-Latn": "Krišjāņa Barona iela", "en": "Krisjana Barona Street"},
                "house_number": "7",
                "address2": {"lv-Latn": "dz. 1", "en": "apt. 1"},
                "city": {"lv-Latn": "RĪGA", "en": "RIGA"},
                "postcode": "1073",
            },
            "LV",
        )
        self.assertIn("Krišjāņa Barona iela 7, dz. 1", result.native.lines)
        self.assertIn("RĪGA, LV-1073", result.native.lines)

    def test_lithuania_hyphenates_apartment_and_normalizes_lt_prefix(self):
        result = render_northern_europe_address(
            {
                "country_code": "LT",
                "road": {"lt-Latn": "Laisvės pr.", "en": "Laisves Avenue"},
                "house_number": "40",
                "address2": {"lt-Latn": "12", "en": "12"},
                "city": {"lt-Latn": "Vilnius", "en": "Vilnius"},
                "postcode": "04340",
            },
            "LT",
        )
        self.assertIn("Laisvės pr. 40-12", result.native.lines)
        self.assertIn("LT-04340 Vilnius", result.native.lines)

    def test_norway_places_residential_number_above_street_and_supports_sami(self):
        components = {
            "country_code": "NO",
            "address2": {"nb-Latn": "Bolignummer H0302", "se-Latn": "Orrunlohku H0302", "en": "Residential number H0302"},
            "road": {"nb-Latn": "Storgata", "se-Latn": "Stuorragáhta", "en": "Main Street"},
            "house_number": "15",
            "city": {"nb-Latn": "OSLO", "se-Latn": "OSLO", "en": "OSLO"},
            "postcode": "0161",
        }
        bokmal = render_northern_europe_address(components, "NO")
        sami = render_northern_europe_address(
            components, "NO", native_language="se-Latn"
        )
        self.assertLess(
            bokmal.native.lines.index("Bolignummer H0302"),
            bokmal.native.lines.index("Storgata 15"),
        )
        self.assertIn("Stuorragáhta 15", sami.native.lines)

    def test_svalbard_uses_norwegian_format_and_norway_routing_country(self):
        result = render_northern_europe_address(
            {
                "country_code": "SJ",
                "road": {"nb-Latn": "Vei 100", "en": "Road 100"},
                "house_number": "7",
                "city": {"nb-Latn": "LONGYEARBYEN", "en": "LONGYEARBYEN"},
                "postcode": "9170",
            },
            "SJ",
        )
        self.assertIn("9170 LONGYEARBYEN", result.native.lines)
        self.assertEqual(result.native.lines[-1], "Norge")
        self.assertEqual(result.english.lines[-1], "Norway")

    def test_sweden_normalizes_postcode_spacing(self):
        result = render_northern_europe_address(
            {
                "country_code": "SE",
                "road": {"sv-Latn": "Ekgatan", "en": "Oak Street"},
                "house_number": "1",
                "city": {"sv-Latn": "TYRESÖ", "en": "TYRESO"},
                "postcode": "12035",
            },
            "SE",
        )
        self.assertIn("120 35 TYRESÖ", result.native.lines)

    def test_united_kingdom_keeps_postcode_own_line_and_languages_separate(self):
        components = {
            "country_code": "GB",
            "road": {"en": "High Street", "cy-Latn": "Stryd Fawr", "gd-Latn": "An t-Sràid Àrd", "ga-Latn": "An Phríomhshráid"},
            "house_number": "10",
            "city": {"en": "CARDIFF", "cy-Latn": "CAERDYDD", "gd-Latn": "CAERDYDD", "ga-Latn": "CAERDYDD"},
            "postcode": "CF101AA",
        }
        welsh = render_northern_europe_address(
            components, "GB", native_language="cy-Latn"
        )
        gaelic = render_northern_europe_address(
            components, "GB", native_language="gd-Latn"
        )
        self.assertIn("10 Stryd Fawr", welsh.native.lines)
        self.assertIn("CF10 1AA", welsh.native.lines)
        self.assertIn("10 An t-Sràid Àrd", gaelic.native.lines)

    def test_same_latin_script_does_not_fill_missing_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_northern_europe_address(
                {
                    "country_code": "FI",
                    "road": {"fi-Latn": "Mäkelänkatu"},
                    "city": {"fi-Latn": "HELSINKI"},
                    "postcode": "00550",
                },
                "FI",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "road"))


if __name__ == "__main__":
    unittest.main()
