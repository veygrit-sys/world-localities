"""Native-language and English Southern Europe address quality tests."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    MissingLocalizedComponents,
    ProfileRegistry,
    SouthernEuropeRegistry,
    render_southern_europe_address,
)


class SouthernEuropeProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.southern_europe = SouthernEuropeRegistry()

    def test_all_sixteen_countries_have_native_variants_and_english(self):
        expected = {
            "AD": ({"ca-Latn": "AD_ca"}, "AD_en"),
            "AL": ({"sq-Latn": "AL_sq"}, "AL_en"),
            "BA": (
                {
                    "bs-Latn": "BA_bs",
                    "hr-Latn": "BA_hr",
                    "sr-Cyrl": "BA_sr",
                    "sr-Latn": "BA_sr",
                },
                "BA_en",
            ),
            "ES": (
                {
                    "es-Latn": "ES_es",
                    "ca-Latn": "ES_ca",
                    "eu-Latn": "ES_eu",
                    "gl-Latn": "ES_gl",
                    "oc-Latn": "ES_oc",
                },
                "ES_en",
            ),
            "GI": ({"en": "GI_en"}, "GI_en"),
            "GR": ({"el-Grek": "GR_el"}, "GR_en"),
            "HR": ({"hr-Latn": "HR_hr"}, "HR_en"),
            "IT": ({"it-Latn": "IT_it", "de-Latn": "IT_de"}, "IT_en"),
            "ME": (
                {
                    "cnr-Latn": "ME_cnr",
                    "cnr-Cyrl": "ME_cnr",
                    "sr-Latn": "ME_sr",
                    "sr-Cyrl": "ME_sr",
                    "bs-Latn": "ME_bs",
                    "sq-Latn": "ME_sq",
                    "hr-Latn": "ME_hr",
                },
                "ME_en",
            ),
            "MK": ({"mk-Cyrl": "MK_mk", "sq-Latn": "MK_sq"}, "MK_en"),
            "MT": ({"mt-Latn": "MT_mt", "en": "MT_en"}, "MT_en"),
            "PT": ({"pt-Latn": "PT_pt"}, "PT_en"),
            "RS": ({"sr-Cyrl": "RS_sr", "sr-Latn": "RS_sr"}, "RS_en"),
            "SI": ({"sl-Latn": "SI_sl"}, "SI_en"),
            "SM": ({"it-Latn": "SM_it"}, "SM_en"),
            "VA": ({"it-Latn": "VA_it", "la-Latn": "VA_la"}, "VA_en"),
        }
        self.assertEqual(set(self.southern_europe.countries), set(expected))
        for country, (native_profiles, english_profile) in expected.items():
            with self.subTest(country=country):
                policy = self.southern_europe.get(country)
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

    def test_coverage_report_keeps_andorra_operator_ambiguity_visible(self):
        self.assertEqual(
            self.southern_europe.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-17",
                "countries": 16,
                "native_language_variants": 34,
                "english_profiles": 16,
                "provisional_countries": ["AD"],
            },
        )

    def test_every_language_has_script_and_every_country_has_provenance(self):
        for country, policy in self.southern_europe.countries.items():
            with self.subTest(country=country):
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertTrue(policy["sources"])
                self.assertTrue(policy["romanization_policy"])


class SouthernEuropeBilingualRendering(unittest.TestCase):
    def test_albania_keeps_delivery_point_and_postcode_on_separate_lines(self):
        result = render_southern_europe_address(
            {
                "country_code": "AL",
                "road": {"sq-Latn": "Rruga Myslym Shyri", "en": "Myslym Shyri Street"},
                "house": {"sq-Latn": "Pallati 37", "en": "Building 37"},
                "address2": {"sq-Latn": "shkalla 4 apartamenti 15", "en": "staircase 4 apartment 15"},
                "city": {"sq-Latn": "TIRANË", "en": "TIRANA"},
                "postcode": "1001",
            },
            "AL",
        )
        self.assertIn("Pallati 37 shkalla 4 apartamenti 15", result.native.lines)
        self.assertLess(result.native.lines.index("1001"), result.native.lines.index("TIRANË"))
        self.assertFalse(result.native.unrendered_components)

    def test_andorra_preserves_ad_postcode_and_warns_about_provisional_route(self):
        result = render_southern_europe_address(
            {
                "country_code": "AD",
                "road": {"ca-Latn": "AVINGUDA CARLEMANY", "en": "CARLEMANY AVENUE"},
                "house_number": "2",
                "city": {"ca-Latn": "ESCALDES ENGORDANY", "en": "ESCALDES-ENGORDANY"},
                "postcode": "AD700",
            },
            "AD",
        )
        self.assertIn("2 AVINGUDA CARLEMANY", result.native.lines)
        self.assertIn("AD700 ESCALDES ENGORDANY", result.native.lines)
        self.assertIn("provisional_country_profile", result.warnings)

    def test_bosnia_keeps_bosnian_croatian_and_two_serbian_scripts_distinct(self):
        components = {
            "country_code": "BA",
            "road": {
                "bs-Latn": "Ulica Skenderija",
                "hr-Latn": "Skenderijina ulica",
                "sr-Cyrl": "Улица Скендерија",
                "sr-Latn": "Ulica Skenderija",
                "en": "Skenderija Street",
            },
            "house_number": "60",
            "city": {
                "bs-Latn": "SARAJEVO",
                "hr-Latn": "SARAJEVO",
                "sr-Cyrl": "САРАЈЕВО",
                "sr-Latn": "SARAJEVO",
                "en": "SARAJEVO",
            },
            "postcode": "71000",
        }
        bosnian = render_southern_europe_address(components, "BA")
        croatian = render_southern_europe_address(components, "BA", native_language="hr-Latn")
        cyrillic = render_southern_europe_address(components, "BA", native_language="sr-Cyrl")
        latin = render_southern_europe_address(components, "BA", native_language="sr-Latn")
        self.assertIn("Ulica Skenderija 60", bosnian.native.lines)
        self.assertIn("Skenderijina ulica 60", croatian.native.lines)
        self.assertIn("Улица Скендерија 60", cyrillic.native.lines)
        self.assertIn("Ulica Skenderija 60", latin.native.lines)

    def test_croatia_preserves_hr_prefix_and_inline_apartment(self):
        result = render_southern_europe_address(
            {
                "country_code": "HR",
                "road": {"hr-Latn": "Krapinska", "en": "Krapinska Street"},
                "house_number": "17/I",
                "address2": {"hr-Latn": "stan 4", "en": "apartment 4"},
                "city": {"hr-Latn": "ZAGREB", "en": "ZAGREB"},
                "postcode": "HR-10000",
            },
            "HR",
        )
        self.assertIn("Krapinska 17/I stan 4", result.native.lines)
        self.assertIn("HR-10000 ZAGREB", result.native.lines)

    def test_gibraltar_keeps_locality_before_generic_postcode(self):
        result = render_southern_europe_address(
            {
                "country_code": "GI",
                "road": {"en": "Gardiner's Road"},
                "house_number": "109",
                "city": {"en": "Gibraltar"},
                "postcode": "GX11 1AA",
            },
            "GI",
        )
        self.assertLess(result.native.lines.index("Gibraltar"), result.native.lines.index("GX11 1AA"))
        self.assertEqual(result.native.profile_key, "GI_en")
        self.assertEqual(result.english.profile_key, "GI_en")

    def test_greece_normalizes_postcode_spacing_and_checks_greek_script(self):
        result = render_southern_europe_address(
            {
                "country_code": "GR",
                "road": {"el-Grek": "Οδός Απέλλου", "en": "Apellou Street"},
                "house_number": "1",
                "city": {"el-Grek": "ΑΘΗΝΑ", "en": "ATHENS"},
                "postcode": "10188",
            },
            "GR",
        )
        self.assertIn("101 88 ΑΘΗΝΑ", result.native.lines)
        with self.assertRaisesRegex(ValueError, "not Grek-script: city"):
            render_southern_europe_address(
                {"country_code": "GR", "city": {"el-Grek": "Athina", "en": "Athens"}},
                "GR",
            )

    def test_italy_places_address2_above_street_and_keeps_province_code(self):
        result = render_southern_europe_address(
            {
                "country_code": "IT",
                "address2": {"it-Latn": "INTERNO 12 PIANO 10", "en": "APARTMENT 12 FLOOR 10"},
                "road": {"it-Latn": "VIALE EUROPA", "en": "EUROPA AVENUE"},
                "house_number": "300",
                "city": {"it-Latn": "ROMA", "en": "ROME"},
                "county": {"it-Latn": "RM", "en": "RM"},
                "postcode": "00144",
            },
            "IT",
        )
        self.assertLess(
            result.native.lines.index("INTERNO 12 PIANO 10"),
            result.native.lines.index("VIALE EUROPA 300"),
        )
        self.assertIn("00144 ROMA RM", result.native.lines)

    def test_italian_never_silently_fills_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_southern_europe_address(
                {
                    "country_code": "IT",
                    "road": {"it-Latn": "VIA ROMA"},
                    "city": {"it-Latn": "MILANO"},
                    "postcode": "20121",
                },
                "IT",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "road"))

    def test_malta_supports_maltese_and_english_and_normalizes_postcode_space(self):
        components = {
            "country_code": "MT",
            "road": {"mt-Latn": "Triq it-Tempji Neolitiċi", "en": "Neolithic Temples Street"},
            "house_number": "38",
            "city": {"mt-Latn": "IL-ĦAMRUN", "en": "HAMRUN"},
            "postcode": "HMR1428",
        }
        maltese = render_southern_europe_address(components, "MT")
        english = render_southern_europe_address(components, "MT", native_language="en")
        self.assertIn("38 Triq it-Tempji Neolitiċi", maltese.native.lines)
        self.assertIn("HMR 1428", maltese.native.lines)
        self.assertLess(maltese.native.lines.index("IL-ĦAMRUN"), maltese.native.lines.index("HMR 1428"))
        self.assertIn("38 Neolithic Temples Street", english.native.lines)

    def test_montenegro_keeps_languages_and_scripts_independent(self):
        components = {
            "country_code": "ME",
            "road": {
                "cnr-Latn": "Ulica Slobode",
                "cnr-Cyrl": "Улица Слободе",
                "sr-Latn": "Ulica slobode",
                "sr-Cyrl": "Улица слободе",
                "bs-Latn": "Ulica slobode",
                "sq-Latn": "Rruga e Lirisë",
                "hr-Latn": "Ulica slobode",
                "en": "Freedom Street",
            },
            "house_number": "1",
            "city": {
                "cnr-Latn": "PODGORICA",
                "cnr-Cyrl": "ПОДГОРИЦА",
                "sr-Latn": "PODGORICA",
                "sr-Cyrl": "ПОДГОРИЦА",
                "bs-Latn": "PODGORICA",
                "sq-Latn": "PODGORICË",
                "hr-Latn": "PODGORICA",
                "en": "PODGORICA",
            },
            "postcode": "81000",
        }
        latin = render_southern_europe_address(components, "ME")
        cyrillic = render_southern_europe_address(components, "ME", native_language="cnr-Cyrl")
        albanian = render_southern_europe_address(components, "ME", native_language="sq-Latn")
        self.assertIn("Ulica Slobode 1", latin.native.lines)
        self.assertIn("Улица Слободе 1", cyrillic.native.lines)
        self.assertIn("Rruga e Lirisë 1", albanian.native.lines)

    def test_montenegrin_never_fills_serbian_despite_shared_script(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_southern_europe_address(
                {
                    "country_code": "ME",
                    "road": {"cnr-Latn": "Njegoševa", "en": "Njegoseva Street"},
                    "city": {"cnr-Latn": "CETINJE", "en": "CETINJE"},
                    "postcode": "81250",
                },
                "ME",
                native_language="sr-Latn",
            )
        self.assertEqual(error.exception.language, "sr-Latn")
        self.assertEqual(error.exception.components, ("city", "road"))

    def test_north_macedonia_keeps_macedonian_and_albanian_distinct(self):
        components = {
            "country_code": "MK",
            "road": {"mk-Cyrl": "Илинденска", "sq-Latn": "Rruga Ilinden", "en": "Ilinden Street"},
            "house_number": "2/1-8",
            "city": {"mk-Cyrl": "СКОПЈЕ", "sq-Latn": "SHKUP", "en": "SKOPJE"},
            "postcode": "1020",
        }
        macedonian = render_southern_europe_address(components, "MK")
        albanian = render_southern_europe_address(components, "MK", native_language="sq-Latn")
        self.assertIn("Илинденска 2/1-8", macedonian.native.lines)
        self.assertIn("Rruga Ilinden 2/1-8", albanian.native.lines)

    def test_portugal_normalizes_postcode_and_keeps_floor_on_street_line(self):
        result = render_southern_europe_address(
            {
                "country_code": "PT",
                "road": {"pt-Latn": "R LEAL DA CÂMARA", "en": "LEAL DA CAMARA STREET"},
                "house_number": "31",
                "address2": {"pt-Latn": "RC ESQ", "en": "GROUND FLOOR LEFT"},
                "place": {"pt-Latn": "ALGUEIRÃO", "en": "ALGUEIRAO"},
                "city": {"pt-Latn": "MEM MARTINS", "en": "MEM MARTINS"},
                "postcode": "2725079",
            },
            "PT",
        )
        self.assertIn("R LEAL DA CÂMARA 31 RC ESQ", result.native.lines)
        self.assertIn("2725-079 MEM MARTINS", result.native.lines)

    def test_serbia_keeps_pak_separate_from_delivery_office_code(self):
        components = {
            "country_code": "RS",
            "road": {"sr-Cyrl": "Београдска", "sr-Latn": "Beogradska", "en": "Beogradska Street"},
            "house_number": "3",
            "place": {"sr-Cyrl": "БАЈМОК", "sr-Latn": "BAJMOK", "en": "BAJMOK"},
            "city": {"sr-Cyrl": "БАЈМОК", "sr-Latn": "BAJMOK", "en": "BAJMOK"},
            "postcode": "24210",
            "sorting_code": "PAK 456769",
        }
        cyrillic = render_southern_europe_address(components, "RS")
        latin = render_southern_europe_address(components, "RS", native_language="sr-Latn")
        self.assertIn("24210 БАЈМОК", cyrillic.native.lines)
        self.assertIn("PAK 456769", cyrillic.native.lines)
        self.assertIn("Beogradska 3", latin.native.lines)
        self.assertLess(cyrillic.native.lines.index("24210 БАЈМОК"), cyrillic.native.lines.index("PAK 456769"))

    def test_slovenia_po_box_form_does_not_invent_a_street(self):
        result = render_southern_europe_address(
            {
                "country_code": "SI",
                "organization": {"sl-Latn": "Prodajalna AVTO-HIT", "en": "AVTO-HIT Shop"},
                "po_box": {"sl-Latn": "p.p. 1635", "en": "P.O. Box 1635"},
                "city": {"sl-Latn": "LJUBLJANA", "en": "LJUBLJANA"},
                "postcode": "1001",
            },
            "SI",
        )
        self.assertIn("p.p. 1635", result.native.lines)
        self.assertIn("1001 LJUBLJANA", result.native.lines)
        self.assertNotIn("road", result.native.components)

    def test_spain_selects_five_languages_and_keeps_address2_and_province(self):
        components = {
            "country_code": "ES",
            "road": {
                "es-Latn": "Plaza de las Descalzas",
                "ca-Latn": "Plaça de les Descalces",
                "eu-Latn": "Descalzas plaza",
                "gl-Latn": "Praza das Descalzas",
                "oc-Latn": "Plaça de las Descalças",
                "en": "Descalzas Square",
            },
            "house_number": "27",
            "address2": {
                "es-Latn": "Esc 2, 3º, C",
                "ca-Latn": "Esc 2, 3r, C",
                "eu-Latn": "2 esk, 3, C",
                "gl-Latn": "Esc 2, 3º, C",
                "oc-Latn": "Esc 2, 3au, C",
                "en": "Staircase 2, Floor 3, Door C",
            },
            "city": {
                "es-Latn": "TOLEDO",
                "ca-Latn": "TOLEDO",
                "eu-Latn": "TOLEDO",
                "gl-Latn": "TOLEDO",
                "oc-Latn": "TOLEDO",
                "en": "TOLEDO",
            },
            "state": {
                "es-Latn": "TOLEDO",
                "ca-Latn": "TOLEDO",
                "eu-Latn": "TOLEDO",
                "gl-Latn": "TOLEDO",
                "oc-Latn": "TOLEDO",
                "en": "TOLEDO",
            },
            "postcode": "45012",
        }
        for language, expected_road in {
            "es-Latn": "Plaza de las Descalzas 27, Esc 2, 3º, C",
            "ca-Latn": "Plaça de les Descalces 27, Esc 2, 3r, C",
            "eu-Latn": "Descalzas plaza 27, 2 esk, 3, C",
            "gl-Latn": "Praza das Descalzas 27, Esc 2, 3º, C",
            "oc-Latn": "Plaça de las Descalças 27, Esc 2, 3au, C",
        }.items():
            with self.subTest(language=language):
                result = render_southern_europe_address(components, "ES", native_language=language)
                self.assertIn(expected_road, result.native.lines)
                self.assertIn("45012 TOLEDO", result.native.lines)
                self.assertEqual(result.native.lines[-2], "TOLEDO")

    def test_san_marino_preserves_47890_without_provisional_warning(self):
        result = render_southern_europe_address(
            {
                "country_code": "SM",
                "road": {"it-Latn": "Viale Antonio Onofri", "en": "Antonio Onofri Avenue"},
                "house_number": "117",
                "city": {"it-Latn": "San Marino", "en": "San Marino"},
                "postcode": "47890",
            },
            "SM",
        )
        self.assertIn("47890 San Marino", result.native.lines)
        self.assertNotIn("provisional_country_profile", result.warnings)

    def test_vatican_supports_italian_and_latin_without_province(self):
        components = {
            "country_code": "VA",
            "house": {"it-Latn": "Palazzo San Calisto", "la-Latn": "Palatium Sancti Callisti", "en": "San Calisto Palace"},
            "road": {"it-Latn": "Piazza San Calisto", "la-Latn": "Platea Sancti Callisti", "en": "San Calisto Square"},
            "city": {"it-Latn": "Città del Vaticano", "la-Latn": "Civitas Vaticana", "en": "Vatican City"},
            "postcode": "00120",
        }
        italian = render_southern_europe_address(components, "VA")
        latin = render_southern_europe_address(components, "VA", native_language="la-Latn")
        self.assertIn("00120 Città del Vaticano", italian.native.lines)
        self.assertIn("00120 Civitas Vaticana", latin.native.lines)
        self.assertNotIn("county", italian.native.components)


if __name__ == "__main__":
    unittest.main()
