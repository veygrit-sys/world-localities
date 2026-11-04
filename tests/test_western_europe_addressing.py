"""Native-language and English Western Europe address quality tests."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    MissingLocalizedComponents,
    ProfileRegistry,
    WesternEuropeRegistry,
    render_western_europe_address,
)


class WesternEuropeProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.western_europe = WesternEuropeRegistry()

    def test_all_nine_countries_have_native_variants_and_english(self):
        expected = {
            "AT": ({"de-Latn": "AT_de"}, "AT_en"),
            "BE": (
                {
                    "nl-Latn": "BE_nl",
                    "fr-Latn": "BE_fr",
                    "de-Latn": "BE_de",
                },
                "BE_en",
            ),
            "CH": (
                {
                    "de-Latn": "CH_de",
                    "fr-Latn": "CH_fr",
                    "it-Latn": "CH_it",
                    "rm-Latn": "CH_rm",
                },
                "CH_en",
            ),
            "DE": ({"de-Latn": "DE_de"}, "DE_en"),
            "FR": ({"fr-Latn": "FR_fr"}, "FR_en"),
            "LI": ({"de-Latn": "LI_de"}, "LI_en"),
            "LU": (
                {
                    "lb-Latn": "LU_lb",
                    "fr-Latn": "LU_fr",
                    "de-Latn": "LU_de",
                },
                "LU_en",
            ),
            "MC": ({"fr-Latn": "MC_fr"}, "MC_en"),
            "NL": ({"nl-Latn": "NL_nl"}, "NL_en"),
        }
        self.assertEqual(set(self.western_europe.countries), set(expected))
        for country, (native_profiles, english_profile) in expected.items():
            with self.subTest(country=country):
                policy = self.western_europe.get(country)
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
            self.western_europe.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-16",
                "countries": 9,
                "native_language_variants": 16,
                "english_profiles": 9,
                "provisional_countries": [],
            },
        )

    def test_every_native_language_has_latin_script_and_provenance(self):
        for country, policy in self.western_europe.countries.items():
            with self.subTest(country=country):
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertEqual(set(policy["native_scripts"].values()), {"Latn"})
                self.assertTrue(policy["sources"])
                self.assertTrue(policy["romanization_policy"])


class WesternEuropeBilingualRendering(unittest.TestCase):
    def test_austria_keeps_staircase_and_door_address2_on_delivery_line(self):
        result = render_western_europe_address(
            {
                "country_code": "AT",
                "road": {"de-Latn": "Grünwaldweg", "en": "Gruenwaldweg"},
                "house_number": "16",
                "address2": {"de-Latn": "Stiege 13 Tür 5", "en": "Staircase 13 Door 5"},
                "city": {"de-Latn": "Obersiebenbrunn", "en": "Obersiebenbrunn"},
                "postcode": "2283",
            },
            "AT",
        )
        self.assertIn("Grünwaldweg 16 Stiege 13 Tür 5", result.native.lines)
        self.assertIn("Gruenwaldweg 16 Staircase 13 Door 5", result.english.lines)
        self.assertFalse(result.native.unrendered_components)
        self.assertFalse(result.english.unrendered_components)

    def test_belgium_selects_dutch_french_and_german_independently(self):
        components = {
            "country_code": "BE",
            "road": {
                "nl-Latn": "Wetstraat",
                "fr-Latn": "Rue de la Loi",
                "de-Latn": "Gesetzesstraße",
                "en": "Law Street",
            },
            "house_number": "16",
            "city": {
                "nl-Latn": "Brussel",
                "fr-Latn": "Bruxelles",
                "de-Latn": "Brüssel",
                "en": "Brussels",
            },
            "postcode": "1000",
        }
        dutch = render_western_europe_address(components, "BE")
        french = render_western_europe_address(
            components, "BE", native_language="fr-Latn"
        )
        german = render_western_europe_address(
            components, "BE", native_language="de-Latn"
        )
        self.assertIn("Wetstraat 16", dutch.native.lines)
        self.assertIn("Rue de la Loi 16", french.native.lines)
        self.assertIn("Gesetzesstraße 16", german.native.lines)
        self.assertIn("Law Street 16", dutch.english.lines)

    def test_same_latin_script_never_fills_missing_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_western_europe_address(
                {
                    "country_code": "FR",
                    "road": {"fr-Latn": "Rue des Fleurs"},
                    "house_number": "25",
                    "city": {"fr-Latn": "Libourne"},
                    "postcode": "33500",
                },
                "FR",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "road"))

    def test_belgian_french_never_fills_dutch(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_western_europe_address(
                {
                    "country_code": "BE",
                    "road": {"fr-Latn": "Rue du Vivier", "en": "Vivier Street"},
                    "city": {"fr-Latn": "Bruxelles", "en": "Brussels"},
                    "postcode": "1000",
                },
                "BE",
            )
        self.assertEqual(error.exception.language, "nl-Latn")
        self.assertEqual(error.exception.components, ("city", "road"))

    def test_france_places_address2_before_building_and_delivery_line(self):
        result = render_western_europe_address(
            {
                "country_code": "FR",
                "address2": {"fr-Latn": "Appartement 2 Escalier A", "en": "Apartment 2 Staircase A"},
                "house": {"fr-Latn": "Bâtiment Jonquille", "en": "Jonquille Building"},
                "road": {"fr-Latn": "RUE DE L EGLISE", "en": "RUE DE L EGLISE"},
                "house_number": "25",
                "city": {"fr-Latn": "MIOS", "en": "MIOS"},
                "postcode": "33380",
            },
            "FR",
        )
        self.assertLess(
            result.native.lines.index("Appartement 2 Escalier A"),
            result.native.lines.index("Bâtiment Jonquille"),
        )
        self.assertLess(
            result.native.lines.index("Bâtiment Jonquille"),
            result.native.lines.index("25 RUE DE L EGLISE"),
        )
        self.assertIn("33380 MIOS", result.native.lines)

    def test_germany_preserves_apartment_on_street_line_and_no_prefix_is_invented(self):
        result = render_western_europe_address(
            {
                "country_code": "DE",
                "road": {"de-Latn": "Rhondorfer Str.", "en": "Rhondorfer Street"},
                "house_number": "666",
                "address2": {"de-Latn": "Wohnung 47", "en": "Apartment 47"},
                "city": {"de-Latn": "KÖLN", "en": "COLOGNE"},
                "postcode": "50939",
            },
            "DE",
        )
        self.assertIn("Rhondorfer Str. 666 Wohnung 47", result.native.lines)
        self.assertIn("50939 KÖLN", result.native.lines)
        self.assertNotIn("DE-50939", result.native.text)

    def test_liechtenstein_preserves_supplied_fl_prefix(self):
        result = render_western_europe_address(
            {
                "country_code": "LI",
                "road": {"de-Latn": "Städtle", "en": "Staedtle"},
                "house_number": "36",
                "city": {"de-Latn": "Vaduz", "en": "Vaduz"},
                "postcode": "FL-9490",
            },
            "LI",
        )
        self.assertIn("FL-9490 Vaduz", result.native.lines)
        self.assertIn("FL-9490 Vaduz", result.english.lines)

    def test_luxembourg_supports_three_domestic_languages_and_l_prefix(self):
        components = {
            "country_code": "LU",
            "road": {
                "lb-Latn": "Wäistrooss",
                "fr-Latn": "route du Vin",
                "de-Latn": "Weinstraße",
                "en": "Wine Road",
            },
            "house_number": "71",
            "city": {
                "lb-Latn": "Diddeleng",
                "fr-Latn": "DUDELANGE",
                "de-Latn": "DÜDELINGEN",
                "en": "Dudelange",
            },
            "postcode": "L-1234",
        }
        luxembourgish = render_western_europe_address(components, "LU")
        french = render_western_europe_address(
            components, "LU", native_language="fr-Latn"
        )
        german = render_western_europe_address(
            components, "LU", native_language="de-Latn"
        )
        self.assertIn("71 Wäistrooss", luxembourgish.native.lines)
        self.assertIn("71 route du Vin", french.native.lines)
        self.assertIn("71 Weinstraße", german.native.lines)
        self.assertIn("L-1234 Diddeleng", luxembourgish.native.lines)

    def test_monaco_preserves_standard_and_cedex_postcodes(self):
        standard = render_western_europe_address(
            {
                "country_code": "MC",
                "road": {"fr-Latn": "Quai des Hirondelles", "en": "Quai des Hirondelles"},
                "city": {"fr-Latn": "MONACO", "en": "MONACO"},
                "postcode": "98000",
            },
            "MC",
        )
        cedex = render_western_europe_address(
            {
                "country_code": "MC",
                "road": {"fr-Latn": "avenue de Fonvieille", "en": "avenue de Fonvieille"},
                "house_number": "1",
                "city": {"fr-Latn": "MONACO CEDEX", "en": "MONACO CEDEX"},
                "postcode": "98020",
            },
            "MC",
        )
        self.assertIn("98000 MONACO", standard.native.lines)
        self.assertIn("98020 MONACO CEDEX", cedex.native.lines)

    def test_netherlands_normalizes_postcode_space_and_keeps_house_addition(self):
        result = render_western_europe_address(
            {
                "country_code": "NL",
                "road": {"nl-Latn": "Drieslag", "en": "Drieslag"},
                "house_number": "5",
                "address2": {"nl-Latn": "-1", "en": "-1"},
                "city": {"nl-Latn": "ARNHEM", "en": "ARNHEM"},
                "postcode": "6832AM",
            },
            "NL",
        )
        self.assertIn("Drieslag 5 -1", result.native.lines)
        self.assertIn("6832 AM ARNHEM", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_switzerland_selects_four_languages_and_preserves_subpremise(self):
        components = {
            "country_code": "CH",
            "road": {
                "de-Latn": "Bahnhofstrasse",
                "fr-Latn": "Rue de la Gare",
                "it-Latn": "Via della Stazione",
                "rm-Latn": "Via da la Staziun",
                "en": "Station Street",
            },
            "house_number": "4a",
            "address2": {
                "de-Latn": "Wohnung 8",
                "fr-Latn": "Appartement 8",
                "it-Latn": "Appartamento 8",
                "rm-Latn": "Abitaziun 8",
                "en": "Apartment 8",
            },
            "city": {
                "de-Latn": "Zürich",
                "fr-Latn": "Zurich",
                "it-Latn": "Zurigo",
                "rm-Latn": "Turitg",
                "en": "Zurich",
            },
            "postcode": "8001",
        }
        german = render_western_europe_address(components, "CH")
        french = render_western_europe_address(
            components, "CH", native_language="fr-Latn"
        )
        italian = render_western_europe_address(
            components, "CH", native_language="it-Latn"
        )
        romansh = render_western_europe_address(
            components, "CH", native_language="rm-Latn"
        )
        self.assertIn("Bahnhofstrasse 4a Wohnung 8", german.native.lines)
        self.assertIn("Rue de la Gare 4a Appartement 8", french.native.lines)
        self.assertIn("Via della Stazione 4a Appartamento 8", italian.native.lines)
        self.assertIn("Via da la Staziun 4a Abitaziun 8", romansh.native.lines)

    def test_latin_profile_rejects_non_latin_mislabelling(self):
        with self.assertRaisesRegex(ValueError, "not Latn-script: city"):
            render_western_europe_address(
                {
                    "country_code": "AT",
                    "city": {"de-Latn": "Βιέννη", "en": "Vienna"},
                    "postcode": "1010",
                },
                "AT",
            )


if __name__ == "__main__":
    unittest.main()
