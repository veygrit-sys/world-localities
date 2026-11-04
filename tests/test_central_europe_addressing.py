"""Cross-region Central Europe address composition tests."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    CentralEuropeRegistry,
    MissingLocalizedComponents,
    ProfileRegistry,
    render_central_europe_address,
)
from addressing.central_europe import COUNTRY_PROFILE_ORIGINS
from addressing.eastern_europe import EasternEuropeRegistry
from addressing.southern_europe import SouthernEuropeRegistry
from addressing.western_europe import WesternEuropeRegistry


class CentralEuropeProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.central_europe = CentralEuropeRegistry()

    def test_core_nine_countries_have_native_variants_and_english(self):
        expected = {
            "AT": ({"de-Latn": "AT_de"}, "AT_en"),
            "CH": (
                {
                    "de-Latn": "CH_de",
                    "fr-Latn": "CH_fr",
                    "it-Latn": "CH_it",
                    "rm-Latn": "CH_rm",
                },
                "CH_en",
            ),
            "CZ": ({"cs-Latn": "CZ_cs"}, "CZ_en"),
            "DE": ({"de-Latn": "DE_de"}, "DE_en"),
            "HU": ({"hu-Latn": "HU_hu"}, "HU_en"),
            "LI": ({"de-Latn": "LI_de"}, "LI_en"),
            "PL": ({"pl-Latn": "PL_pl"}, "PL_en"),
            "SI": ({"sl-Latn": "SI_sl"}, "SI_en"),
            "SK": ({"sk-Latn": "SK_sk"}, "SK_en"),
        }
        self.assertEqual(set(self.central_europe.countries), set(expected))
        for country, (native_profiles, english_profile) in expected.items():
            with self.subTest(country=country):
                policy = self.central_europe.get(country)
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

    def test_composition_reuses_three_existing_regional_policies(self):
        registries = {
            "Western Europe": WesternEuropeRegistry(),
            "Eastern Europe": EasternEuropeRegistry(),
            "Southern Europe": SouthernEuropeRegistry(),
        }
        self.assertEqual(self.central_europe.profile_origins, COUNTRY_PROFILE_ORIGINS)
        for country, origin in COUNTRY_PROFILE_ORIGINS.items():
            with self.subTest(country=country):
                self.assertEqual(
                    self.central_europe.get(country), registries[origin].get(country)
                )
        self.assertEqual(self.central_europe.payload["profiles"], {})

    def test_coverage_report_counts_twelve_variants_without_provisional_routes(self):
        self.assertEqual(
            self.central_europe.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-17",
                "countries": 9,
                "native_language_variants": 12,
                "english_profiles": 9,
                "provisional_countries": [],
            },
        )

    def test_ambiguous_extended_countries_remain_in_their_existing_regions(self):
        for country in ("HR", "LU"):
            with self.subTest(country=country):
                with self.assertRaisesRegex(KeyError, "outside Central Europe"):
                    self.central_europe.get(country)

    def test_composition_does_not_change_global_profile_inventory(self):
        report = self.profiles.report()
        self.assertEqual(report["locale_profiles"], 558)
        self.assertEqual(report["extension_profiles"], 782)
        self.assertEqual(report["extension_overrides"], 240)


class CentralEuropeBilingualRendering(unittest.TestCase):
    def test_austria_and_germany_keep_address2_on_delivery_line(self):
        cases = {
            "AT": {
                "road": {"de-Latn": "Grünwaldweg", "en": "Gruenwaldweg"},
                "house_number": "16",
                "address2": {"de-Latn": "Stiege 13 Tür 5", "en": "Staircase 13 Door 5"},
                "city": {"de-Latn": "Obersiebenbrunn", "en": "Obersiebenbrunn"},
                "postcode": "2283",
                "expected": "Grünwaldweg 16 Stiege 13 Tür 5",
            },
            "DE": {
                "road": {"de-Latn": "Rhondorfer Str.", "en": "Rhondorfer Street"},
                "house_number": "666",
                "address2": {"de-Latn": "Wohnung 47", "en": "Apartment 47"},
                "city": {"de-Latn": "KÖLN", "en": "COLOGNE"},
                "postcode": "50939",
                "expected": "Rhondorfer Str. 666 Wohnung 47",
            },
        }
        for country, values in cases.items():
            with self.subTest(country=country):
                expected = values["expected"]
                result = render_central_europe_address(
                    {
                        "country_code": country,
                        **{
                            key: value
                            for key, value in values.items()
                            if key != "expected"
                        },
                    },
                    country,
                )
                self.assertIn(expected, result.native.lines)
                self.assertFalse(result.native.unrendered_components)

    def test_switzerland_selects_four_languages_without_cross_filling(self):
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
        romansh = render_central_europe_address(
            components, "CH", native_language="rm-Latn"
        )
        italian = render_central_europe_address(
            components, "CH", native_language="it-Latn"
        )
        self.assertIn("Via da la Staziun 4a Abitaziun 8", romansh.native.lines)
        self.assertIn("8001 Turitg", romansh.native.lines)
        self.assertIn("Via della Stazione 4a Appartamento 8", italian.native.lines)

    def test_czech_polish_and_slovak_postcode_normalization_is_reused(self):
        cases = {
            "CZ": ("cs-Latn", "Dlouhá", "PRAHA", "11000", "110 00 PRAHA"),
            "PL": ("pl-Latn", "ul. Długa", "KRAKÓW", "31000", "31-000 KRAKÓW"),
            "SK": ("sk-Latn", "Hlavná", "BRATISLAVA", "81101", "811 01 BRATISLAVA"),
        }
        for country, (language, road, city, postcode, expected) in cases.items():
            with self.subTest(country=country):
                result = render_central_europe_address(
                    {
                        "country_code": country,
                        "road": {language: road, "en": "Main Street"},
                        "house_number": "1",
                        "city": {language: city, "en": city},
                        "postcode": postcode,
                    },
                    country,
                )
                self.assertIn(expected, result.native.lines)

    def test_hungary_keeps_destination_before_delivery_line_and_postcode(self):
        result = render_central_europe_address(
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

    def test_liechtenstein_preserves_supplied_fl_prefix(self):
        result = render_central_europe_address(
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
        self.assertNotIn("provisional_country_profile", result.warnings)

    def test_slovenia_po_box_route_does_not_invent_a_street(self):
        result = render_central_europe_address(
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

    def test_shared_latin_script_never_fills_missing_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_central_europe_address(
                {
                    "country_code": "CZ",
                    "road": {"cs-Latn": "Dlouhá"},
                    "city": {"cs-Latn": "PRAHA"},
                    "postcode": "11000",
                },
                "CZ",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "road"))


if __name__ == "__main__":
    unittest.main()
