"""Domestic-language, English and postcode tests for the Caribbean."""

import csv
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    CaribbeanRegistry,
    MissingLocalizedComponents,
    ProfileRegistry,
    render_caribbean_address,
)


EXPECTED_PROFILES = {
    "AG": ({"en": "AG_en"}, "AG_en"),
    "AI": ({"en": "AI_en"}, "AI_en"),
    "AW": ({"nl-Latn": "AW_nl", "pap-Latn": "AW_pap"}, "AW_en"),
    "BB": ({"en": "BB_en"}, "BB_en"),
    "BL": ({"fr-Latn": "BL_fr"}, "BL_en"),
    "BQ": ({"nl-Latn": "BQ_nl", "pap-Latn": "BQ_pap", "en": "BQ_en"}, "BQ_en"),
    "BS": ({"en": "BS_en"}, "BS_en"),
    "CU": ({"es-Latn": "CU_es"}, "CU_en"),
    "CW": ({"nl-Latn": "CW_nl", "pap-Latn": "CW_pap", "en": "CW_en"}, "CW_en"),
    "DM": ({"en": "DM_en"}, "DM_en"),
    "DO": ({"es-Latn": "DO_es"}, "DO_en"),
    "GD": ({"en": "GD_en"}, "GD_en"),
    "GP": ({"fr-Latn": "GP_fr"}, "GP_en"),
    "HT": ({"ht-Latn": "HT_ht", "fr-Latn": "HT_fr"}, "HT_en"),
    "JM": ({"en": "JM_en"}, "JM_en"),
    "KN": ({"en": "KN_en"}, "KN_en"),
    "KY": ({"en": "KY_en"}, "KY_en"),
    "LC": ({"en": "LC_en"}, "LC_en"),
    "MF": ({"fr-Latn": "MF_fr"}, "MF_en"),
    "MQ": ({"fr-Latn": "MQ_fr"}, "MQ_en"),
    "MS": ({"en": "MS_en"}, "MS_en"),
    "PR": ({"es-Latn": "PR_es", "en": "PR_en"}, "PR_en"),
    "SX": ({"nl-Latn": "SX_nl", "en": "SX_en"}, "SX_en"),
    "TC": ({"en": "TC_en"}, "TC_en"),
    "TT": ({"en": "TT_en"}, "TT_en"),
    "VC": ({"en": "VC_en"}, "VC_en"),
    "VG": ({"en": "VG_en"}, "VG_en"),
    "VI": ({"en": "VI_en"}, "VI_en"),
}


class CaribbeanProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.caribbean = CaribbeanRegistry()

    def test_all_28_m49_areas_have_domestic_and_english_profiles(self):
        self.assertEqual(set(self.caribbean.countries), set(EXPECTED_PROFILES))
        for country, (native_profiles, english_profile) in EXPECTED_PROFILES.items():
            with self.subTest(country=country):
                policy = self.caribbean.get(country)
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

    def test_report_has_36_domestic_variants_and_no_provisional_route(self):
        self.assertEqual(
            self.caribbean.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-17",
                "countries": 28,
                "native_language_variants": 36,
                "english_profiles": 28,
                "provisional_countries": [],
            },
        )

    def test_every_area_has_postcode_script_and_source_policy(self):
        for country, policy in self.caribbean.countries.items():
            with self.subTest(country=country):
                self.assertIn("postcode_pattern", policy)
                self.assertIsInstance(policy["postcode_required"], bool)
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertTrue(policy["romanization_policy"])
                self.assertTrue(policy["sources"])

    def test_locality_linkage_keeps_cuba_pending_and_counts_reproducible(self):
        linkage = self.caribbean.locality_registry
        scope = json.loads((ROOT / linkage["scope_file"]).read_text(encoding="utf-8"))
        with (ROOT / "caribbean-registry/coverage.csv").open(
            encoding="utf-8", newline=""
        ) as handle:
            coverage = list(csv.DictReader(handle))

        self.assertEqual(scope["m49_scope_count"], 28)
        self.assertEqual(scope["published_scope_count"], 27)
        self.assertEqual(
            {item["country"] for item in scope["omitted_countries"]}, {"CU"}
        )
        self.assertEqual(linkage["pending_locality_source_countries"], ["CU"])
        self.assertNotIn("CU", linkage["published_country_layers"])
        self.assertEqual(len(linkage["published_country_layers"]), 27)
        self.assertEqual(linkage["split_materialization_required"], ["DO"])
        self.assertEqual(
            sum(int(row["entities"]) for row in coverage),
            linkage["source_entity_rows"],
        )
        self.assertEqual(
            sum(int(row["locality_rows"]) for row in coverage),
            linkage["source_locality_rows"],
        )
        self.assertEqual(
            sum(int(row["address_candidates"]) for row in coverage),
            linkage["address_candidate_rows"],
        )
        self.assertEqual(
            sum(int(row["alternate_rows"]) for row in coverage),
            linkage["alternate_rows"],
        )
        self.assertEqual(
            sum(int(row["postal_rows"]) for row in coverage),
            linkage["direct_id_postal_observations"],
        )

    def test_country_outside_region_is_rejected(self):
        with self.assertRaisesRegex(KeyError, "outside Caribbean"):
            self.caribbean.get("BZ")


class CaribbeanPostcodePolicies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.caribbean = CaribbeanRegistry()

    def test_current_area_specific_postcode_syntax_is_accepted(self):
        valid = {
            "AI": ("AI-2640",),
            "BB": ("BB11000",),
            "BL": ("97133",),
            "CU": ("10600",),
            "DO": ("11903",),
            "GP": ("97110",),
            "HT": ("HT6120",),
            "KN": ("KN0101",),
            "KY": ("KY1-1100", "KY2-2001", "KY3-2500"),
            "LC": ("LC04 101", "LC04  101"),
            "MF": ("97150",),
            "MQ": ("97200",),
            "MS": ("MSR1110",),
            "PR": ("00926", "00926-3232"),
            "TC": ("TKCA 1ZZ",),
            "TT": ("500234",),
            "VC": ("VC0120",),
            "VG": ("VG1110",),
            "VI": ("00802", "00802-1234"),
        }
        for country, postcodes in valid.items():
            for postcode in postcodes:
                with self.subTest(country=country, postcode=postcode):
                    self.assertTrue(self.caribbean.validate_postcode(country, postcode))

    def test_wrong_area_forms_are_rejected(self):
        invalid = {
            "AI": ("AI2640", "AI-2641"),
            "BB": ("11000", "BB1100"),
            "BL": ("97150",),
            "CU": ("CP 10600", "1060"),
            "DO": ("DO11903",),
            "GP": ("97133", "97149", "97150", "97200"),
            "HT": ("6120", "HT61200"),
            "KN": ("KN101",),
            "KY": ("KY4-1100", "KY1 1100"),
            "LC": ("LC04101", "LC04-101"),
            "MF": ("97133",),
            "MQ": ("97100",),
            "MS": ("MS1110",),
            "PR": ("PR00926", "009263232"),
            "TC": ("TKCA1ZZ", "TKCA 2ZZ"),
            "TT": ("50023",),
            "VC": ("0120",),
            "VG": ("VG111",),
            "VI": ("VI00802",),
        }
        for country, postcodes in invalid.items():
            for postcode in postcodes:
                with self.subTest(country=country, postcode=postcode):
                    self.assertFalse(self.caribbean.validate_postcode(country, postcode))

    def test_nine_no_code_areas_reject_placeholders(self):
        no_code = {"AG", "AW", "BQ", "BS", "CW", "DM", "GD", "JM", "SX"}
        for country in no_code:
            with self.subTest(country=country):
                self.assertTrue(self.caribbean.validate_postcode(country, None))
                self.assertTrue(self.caribbean.validate_postcode(country, ""))
                self.assertFalse(self.caribbean.validate_postcode(country, "00000"))

    def test_19_coded_areas_require_a_postcode(self):
        no_code = {"AG", "AW", "BQ", "BS", "CW", "DM", "GD", "JM", "SX"}
        for country in set(EXPECTED_PROFILES) - no_code:
            with self.subTest(country=country):
                self.assertFalse(self.caribbean.validate_postcode(country, None))

    def test_fixed_and_usps_forms_are_classified(self):
        classify = self.caribbean.postcode_variant
        self.assertEqual(classify("AI", "AI-2640"), "territory_fixed")
        self.assertEqual(classify("TC", "TKCA 1ZZ"), "territory_fixed")
        self.assertEqual(classify("PR", "00926"), "zip_5")
        self.assertEqual(classify("PR", "00926-3232"), "zip_plus_4")
        self.assertEqual(classify("HT", "HT6120"), "current")
        self.assertIsNone(classify("TC", "TKCA 2ZZ"))

    def test_cayman_island_digit_must_match_explicit_island(self):
        validate = self.caribbean.validate_cayman_island_route
        self.assertTrue(validate("KY1-1100", "Grand Cayman"))
        self.assertTrue(validate("ky2-2001", "Cayman Brac"))
        self.assertTrue(validate("KY3-2500", "Little Cayman"))
        self.assertFalse(validate("KY2-2001", "Grand Cayman"))
        self.assertFalse(validate("KY1-1100", "Cayman Islands"))


class CaribbeanAddressRendering(unittest.TestCase):
    def test_barbados_keeps_premises_address2_road_sub_locality_and_code(self):
        result = render_caribbean_address(
            {
                "country_code": "BB",
                "house": {"en": "The Grotto"},
                "house_number": "35",
                "address2": {"en": "Apt 4"},
                "road": {"en": "4th Ave., Cherry Lane"},
                "neighbourhood": {"en": "Farm Road"},
                "city": {"en": "St. Peter"},
                "postcode": "BB26028",
            },
            "BB",
        )
        self.assertIn("35 The Grotto", result.native.lines)
        self.assertIn("Apt 4", result.native.lines)
        self.assertIn("4th Ave., Cherry Lane", result.native.lines)
        self.assertIn("Farm Road", result.native.lines)
        self.assertIn("St. Peter BB26028", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_cuba_keeps_cross_streets_zone_and_cp_label(self):
        result = render_caribbean_address(
            {
                "country_code": "CU",
                "road": {"es-Latn": "Ave Independencia", "en": "Independence Avenue"},
                "house_number": "s/n",
                "place": {"es-Latn": "19 de Mayo y Aranguren", "en": "19 de Mayo and Aranguren"},
                "neighbourhood": {"es-Latn": "Habana 6", "en": "Havana 6"},
                "city": {"es-Latn": "CIUDAD HABANA", "en": "HAVANA CITY"},
                "postcode": "10600",
            },
            "CU",
        )
        self.assertIn("Ave Independencia s/n", result.native.lines)
        self.assertIn("19 de Mayo y Aranguren", result.native.lines)
        self.assertIn("Habana 6", result.native.lines)
        self.assertIn("CP 10600 CIUDAD HABANA", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_haiti_creole_and_french_routes_keep_ht_integral_code(self):
        result = render_caribbean_address(
            {
                "country_code": "HT",
                "road": {"ht-Latn": "Ri Samba", "fr-Latn": "Rue Samba", "en": "Samba Street"},
                "house_number": "1",
                "city": {"ht-Latn": "Dèlma", "fr-Latn": "DELMAS", "en": "DELMAS"},
                "state": {"ht-Latn": "Lwès", "fr-Latn": "Ouest", "en": "West"},
                "postcode": "HT6120",
            },
            "HT",
            native_language="ht-Latn",
        )
        self.assertEqual(result.native.profile_key, "HT_ht")
        self.assertIn("Ri Samba 1", result.native.lines)
        self.assertIn("HT6120 Dèlma", result.native.lines)
        self.assertIn("Lwès", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_cayman_keeps_po_box_official_island_and_postcode_together(self):
        result = render_caribbean_address(
            {
                "country_code": "KY",
                "po_box": {"en": "P.O. Box 802"},
                "state": {"en": "Grand Cayman"},
                "postcode": "KY1-1100",
            },
            "KY",
        )
        self.assertIn("P.O. Box 802", result.native.lines)
        self.assertIn("Grand Cayman KY1-1100", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_saint_lucia_keeps_address2_street_post_office_and_code(self):
        result = render_caribbean_address(
            {
                "country_code": "LC",
                "address2": {"en": "Block A, Apt 146"},
                "road": {"en": "High Street"},
                "place": {"en": "Marchand Post Office"},
                "city": {"en": "CASTRIES"},
                "postcode": "LC05 201",
            },
            "LC",
        )
        self.assertIn("Block A, Apt 146", result.native.lines)
        self.assertIn("High Street", result.native.lines)
        self.assertIn("Marchand Post Office", result.native.lines)
        self.assertIn("CASTRIES, LC05 201", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_french_saint_martin_keeps_lieu_dit_address2_and_fixed_code(self):
        result = render_caribbean_address(
            {
                "country_code": "MF",
                "road": {"fr-Latn": "rue de la Liberté", "en": "Liberty Street"},
                "house_number": "25",
                "address2": {"fr-Latn": "Bâtiment 2 RDC", "en": "Building 2 Ground Floor"},
                "place": {"fr-Latn": "Quartier d'Orléans", "en": "Orleans Quarter"},
                "city": {"fr-Latn": "SAINT-MARTIN", "en": "SAINT MARTIN"},
                "postcode": "97150",
            },
            "MF",
        )
        self.assertIn("25 rue de la Liberté", result.native.lines)
        self.assertIn("Bâtiment 2 RDC", result.native.lines)
        self.assertIn("Quartier d'Orléans", result.native.lines)
        self.assertIn("97150 SAINT-MARTIN", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_puerto_rico_keeps_urbanization_before_untranslated_spanish_street(self):
        result = render_caribbean_address(
            {
                "country_code": "PR",
                "neighbourhood": {"es-Latn": "URB HIGHLAND GDNS", "en": "URB HIGHLAND GDNS"},
                "road": {"es-Latn": "CALLE MAIN", "en": "CALLE MAIN"},
                "house_number": "125",
                "address2": {"es-Latn": "COND AMAPOLA APT 103", "en": "COND AMAPOLA APT 103"},
                "city": {"es-Latn": "SAN JUAN", "en": "SAN JUAN"},
                "postcode": "00926-3232",
            },
            "PR",
        )
        self.assertLess(
            result.native.lines.index("URB HIGHLAND GDNS"),
            result.native.lines.index("125 CALLE MAIN COND AMAPOLA APT 103"),
        )
        self.assertIn("SAN JUAN PR 00926-3232", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_trinidad_keeps_rural_sub_locality_and_six_digit_code(self):
        result = render_caribbean_address(
            {
                "country_code": "TT",
                "road": {"en": "Dam Road"},
                "house_number": "13",
                "neighbourhood": {"en": "Longdenville"},
                "city": {"en": "CHAGUANAS"},
                "postcode": "500234",
            },
            "TT",
        )
        self.assertIn("13 Dam Road", result.native.lines)
        self.assertIn("Longdenville", result.native.lines)
        self.assertIn("CHAGUANAS 500234", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_bahamas_po_box_and_island_render_without_fake_postcode(self):
        result = render_caribbean_address(
            {
                "country_code": "BS",
                "po_box": {"en": "P.O. Box GT 2001"},
                "city": {"en": "Nassau"},
                "state": {"en": "New Providence"},
            },
            "BS",
        )
        self.assertIn("P.O. Box GT 2001", result.native.lines)
        self.assertIn("Nassau, New Providence", result.native.lines)
        self.assertNotIn("postcode", result.native.components)
        self.assertFalse(result.native.unrendered_components)

    def test_shared_latin_script_does_not_fill_missing_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_caribbean_address(
                {
                    "country_code": "DO",
                    "road": {"es-Latn": "Calle 45"},
                    "house_number": "33",
                    "neighbourhood": {"es-Latn": "Katanga, Los Minas"},
                    "city": {"es-Latn": "SANTO DOMINGO"},
                    "postcode": "11903",
                },
                "DO",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "neighbourhood", "road"))


if __name__ == "__main__":
    unittest.main()
