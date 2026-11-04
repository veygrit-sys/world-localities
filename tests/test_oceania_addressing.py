"""Domestic-language, English and postcode quality tests for Oceania."""

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    MissingLocalizedComponents,
    OceaniaRegistry,
    ProfileRegistry,
    render_oceania_address,
)


EXPECTED_PROFILES = {
    "AS": ({"sm-Latn": "AS_sm", "en": "AS_en"}, "AS_en"),
    "AU": ({"en": "AU_en"}, "AU_en"),
    "CC": ({"ms-Latn": "CC_ms", "en": "CC_en"}, "CC_en"),
    "CK": ({"rar-Latn": "CK_rar", "en": "CK_en"}, "CK_en"),
    "CX": ({"en": "CX_en"}, "CX_en"),
    "FJ": (
        {"fj-Latn": "FJ_fj", "hif-Latn": "FJ_hif", "en": "FJ_en"},
        "FJ_en",
    ),
    "FM": (
        {
            "en": "FM_en",
            "chk-Latn": "FM_chk",
            "pon-Latn": "FM_pon",
            "kos-Latn": "FM_kos",
            "yap-Latn": "FM_yap",
        },
        "FM_en",
    ),
    "GU": ({"ch-Latn": "GU_ch", "en": "GU_en"}, "GU_en"),
    "HM": ({"en": "HM_en"}, "HM_en"),
    "KI": ({"gil-Latn": "KI_gil", "en": "KI_en"}, "KI_en"),
    "MH": ({"mh-Latn": "MH_mh", "en": "MH_en"}, "MH_en"),
    "MP": (
        {"ch-Latn": "MP_ch", "cal-Latn": "MP_cal", "en": "MP_en"},
        "MP_en",
    ),
    "NC": ({"fr-Latn": "NC_fr"}, "NC_en"),
    "NF": ({"pih-Latn": "NF_pih", "en": "NF_en"}, "NF_en"),
    "NR": ({"na-Latn": "NR_na", "en": "NR_en"}, "NR_en"),
    "NU": ({"niu-Latn": "NU_niu", "en": "NU_en"}, "NU_en"),
    "NZ": ({"mi-Latn": "NZ_mi", "en": "NZ_en"}, "NZ_en"),
    "PF": ({"ty-Latn": "PF_ty", "fr-Latn": "PF_fr"}, "PF_en"),
    "PG": (
        {"tpi-Latn": "PG_tpi", "ho-Latn": "PG_ho", "en": "PG_en"},
        "PG_en",
    ),
    "PN": ({"pih-Latn": "PN_pih", "en": "PN_en"}, "PN_en"),
    "PW": ({"pau-Latn": "PW_pau", "en": "PW_en"}, "PW_en"),
    "SB": ({"pis-Latn": "SB_pis", "en": "SB_en"}, "SB_en"),
    "TK": ({"tkl-Latn": "TK_tkl", "en": "TK_en"}, "TK_en"),
    "TO": ({"to-Latn": "TO_to", "en": "TO_en"}, "TO_en"),
    "TV": ({"tvl-Latn": "TV_tvl", "en": "TV_en"}, "TV_en"),
    "UM": ({"en": "UM_en"}, "UM_en"),
    "VU": (
        {"bi-Latn": "VU_bi", "fr-Latn": "VU_fr", "en": "VU_en"},
        "VU_en",
    ),
    "WF": (
        {"wls-Latn": "WF_wls", "fud-Latn": "WF_fud", "fr-Latn": "WF_fr"},
        "WF_en",
    ),
    "WS": ({"sm-Latn": "WS_sm", "en": "WS_en"}, "WS_en"),
}


class OceaniaProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.oceania = OceaniaRegistry()

    def test_all_twenty_nine_m49_entities_have_domestic_and_english_profiles(self):
        self.assertEqual(set(self.oceania.countries), set(EXPECTED_PROFILES))
        for country, (native_profiles, english_profile) in EXPECTED_PROFILES.items():
            with self.subTest(country=country):
                policy = self.oceania.get(country)
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

    def test_coverage_report_exposes_only_known_evidence_gaps(self):
        self.assertEqual(
            self.oceania.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-16",
                "countries": 29,
                "native_language_variants": 61,
                "english_profiles": 29,
                "provisional_countries": ["CK", "HM", "NU", "PN", "SB", "TK", "VU"],
            },
        )

    def test_every_country_has_postcode_policy_script_and_provenance(self):
        for country, policy in self.oceania.countries.items():
            with self.subTest(country=country):
                self.assertIn("postcode_pattern", policy)
                self.assertIsInstance(policy["postcode_required"], bool)
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertTrue(policy["romanization_policy"])
                self.assertTrue(policy["sources"])

    def test_existing_locality_pack_is_the_data_reference(self):
        linkage = self.oceania.locality_registry
        self.assertEqual(linkage["path"], "oceania-registry")
        summary_path = ROOT / linkage["summary_file"]
        pack_path = ROOT / linkage["pack_manifest_file"]
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        manifest = json.loads(pack_path.read_text(encoding="utf-8"))
        self.assertEqual(len(summary), 29)
        self.assertEqual(sum(item["total_records"] for item in summary), 46594)
        self.assertEqual(set(manifest["countries"]), set(EXPECTED_PROFILES))
        self.assertEqual(
            len(list((ROOT / linkage["country_split_directory"]).glob("*/part-*.b64"))),
            60,
        )

    def test_country_outside_region_is_rejected(self):
        with self.assertRaisesRegex(KeyError, "outside Oceania"):
            self.oceania.get("JP")


class OceaniaPostcodePolicies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.oceania = OceaniaRegistry()

    def test_current_new_oceanic_postcodes_are_accepted(self):
        valid = {
            "KI": ("KI0107", "ki 0107"),
            "NR": ("NRU68", "nru-70"),
            "TV": ("TUV150", "tuv 150"),
            "PN": ("PCRN 1ZZ", "pcrn-1zz"),
        }
        for country, postcodes in valid.items():
            for postcode in postcodes:
                with self.subTest(country=country, postcode=postcode):
                    self.assertTrue(self.oceania.validate_postcode(country, postcode))

    def test_usps_australasian_french_and_png_forms_are_accepted(self):
        valid = {
            "AS": "96799-1234",
            "AU": "2000",
            "CC": "6799",
            "CX": "6798",
            "FM": "96944",
            "GU": "96913",
            "MH": "96960",
            "MP": "96952",
            "NC": "98800",
            "NF": "2899",
            "NZ": "1010",
            "PF": "98714",
            "PG": "111",
            "PW": "96940",
            "UM": "96898",
            "WF": "98600",
        }
        for country, postcode in valid.items():
            with self.subTest(country=country):
                self.assertTrue(self.oceania.validate_postcode(country, postcode))

    def test_invalid_or_invented_postcodes_are_rejected(self):
        invalid = {
            "AU": "200",
            "KI": "0107",
            "MH": "96961",
            "NC": "98714",
            "NR": "NRU69",
            "PG": "1111",
            "TV": "150",
        }
        for country, postcode in invalid.items():
            with self.subTest(country=country):
                self.assertFalse(self.oceania.validate_postcode(country, postcode))
        for country in ("CK", "FJ", "NU", "SB", "TK", "TO", "VU", "WS"):
            with self.subTest(country=country):
                self.assertTrue(self.oceania.validate_postcode(country, None))
                self.assertFalse(self.oceania.validate_postcode(country, "12345"))


class OceaniaAddressRendering(unittest.TestCase):
    def test_australia_keeps_address2_before_delivery_line(self):
        result = render_oceania_address(
            {
                "country_code": "AU",
                "address2": {"en": "Level 7, Suite 3"},
                "road": {"en": "George Street"},
                "house_number": "200",
                "city": {"en": "SYDNEY"},
                "state": {"en": "New South Wales"},
                "postcode": "2000",
            },
            "AU",
        )
        self.assertLess(
            result.native.lines.index("Level 7, Suite 3"),
            result.native.lines.index("200 George Street"),
        )
        self.assertIn("SYDNEY NSW 2000", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_new_zealand_keeps_maori_english_and_suburb_separate(self):
        result = render_oceania_address(
            {
                "country_code": "NZ",
                "address2": {"mi-Latn": "Whare 4", "en": "Unit 4"},
                "road": {"mi-Latn": "Te Ara o Kuīni", "en": "Queen Street"},
                "house_number": "12",
                "neighbourhood": {
                    "mi-Latn": "Tāmaki Makaurau Waenga",
                    "en": "Auckland Central",
                },
                "city": {"mi-Latn": "TĀMAKI MAKAURAU", "en": "AUCKLAND"},
                "postcode": "1010",
            },
            "NZ",
        )
        self.assertEqual(result.native.profile_key, "NZ_mi")
        self.assertIn("12 Te Ara o Kuīni", result.native.lines)
        self.assertIn("Tāmaki Makaurau Waenga", result.native.lines)
        self.assertIn("TĀMAKI MAKAURAU 1010", result.native.lines)
        self.assertIn("12 Queen Street", result.english.lines)

    def test_kiribati_and_tuvalu_normalize_new_codes_and_keep_island(self):
        cases = {
            "KI": {
                "language": "gil-Latn",
                "postcode": "ki 0107",
                "city": None,
                "island": "Tarawa",
                "expected": "Tarawa KI0107",
            },
            "TV": {
                "language": "tvl-Latn",
                "postcode": "tuv 150",
                "city": "Funafuti",
                "island": "Fongafale",
                "expected": "TUV150 Funafuti",
            },
        }
        for country, item in cases.items():
            language = item["language"]
            components = {
                "country_code": country,
                "road": {language: "Main Road", "en": "Main Road"},
                "house_number": "2",
                "island": {language: item["island"], "en": item["island"]},
                "postcode": item["postcode"],
            }
            if item["city"]:
                components["city"] = {language: item["city"], "en": item["city"]}
            result = render_oceania_address(components, country)
            with self.subTest(country=country):
                self.assertIn(item["expected"], result.native.lines)
                self.assertTrue(
                    any(item["island"] in line for line in result.native.lines)
                )
                self.assertFalse(result.native.unrendered_components)

    def test_usps_territories_include_routing_code_and_normalize_zip_plus_four(self):
        cases = {
            "AS": ("sm-Latn", "PAGO PAGO", "967991234", "AS"),
            "GU": ("ch-Latn", "TAMUNING", "969131234", "GU"),
            "MH": ("mh-Latn", "MAJURO", "969601234", "MH"),
            "PW": ("pau-Latn", "KOROR", "969401234", "PW"),
        }
        for country, (language, city, postcode, route) in cases.items():
            result = render_oceania_address(
                {
                    "country_code": country,
                    "road": {language: "Main Road", "en": "Main Road"},
                    "house_number": "1",
                    "city": {language: city, "en": city},
                    "postcode": postcode,
                },
                country,
            )
            with self.subTest(country=country):
                self.assertIn(f"{city} {route} {postcode[:5]}-{postcode[5:]}", result.native.lines)

    def test_french_polynesia_keeps_address2_postcode_and_island(self):
        components = {
            "country_code": "PF",
            "address2": {
                "ty-Latn": "Fare 2",
                "fr-Latn": "Appartement 2",
                "en": "Apartment 2",
            },
            "road": {
                "ty-Latn": "Avenue Pouvanaa a Oopa",
                "fr-Latn": "Avenue Pouvanaa a Oopa",
                "en": "Pouvanaa a Oopa Avenue",
            },
            "house_number": "10",
            "city": {
                "ty-Latn": "PAPEETE",
                "fr-Latn": "PAPEETE",
                "en": "PAPEETE",
            },
            "island": {
                "ty-Latn": "Tahiti",
                "fr-Latn": "Tahiti",
                "en": "Tahiti",
            },
            "postcode": "98714",
        }
        result = render_oceania_address(components, "PF")
        french = render_oceania_address(
            components,
            "PF",
            native_language="fr-Latn",
        )
        self.assertIn("Fare 2", result.native.lines)
        self.assertIn("98714 PAPEETE Tahiti", result.native.lines)
        self.assertEqual(french.native_language, "fr-Latn")
        self.assertIn("Appartement 2", french.native.lines)

    def test_png_keeps_three_digit_postcode_before_province(self):
        result = render_oceania_address(
            {
                "country_code": "PG",
                "road": {"tpi-Latn": "Klinki Strit", "en": "Klinki Street"},
                "house_number": "5",
                "city": {"tpi-Latn": "BOROKO", "en": "BOROKO"},
                "postcode": "111",
                "state_code": {"tpi-Latn": "NCD", "en": "NCD"},
            },
            "PG",
        )
        self.assertIn("BOROKO 111 NCD", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_tonga_uses_house_road_village_and_island_without_postcode(self):
        result = render_oceania_address(
            {
                "country_code": "TO",
                "road": {"to-Latn": "Hala Taufaʻahau", "en": "Taufaahau Road"},
                "house_number": "15",
                "village": {"to-Latn": "Nukuʻalofa", "en": "Nukualofa"},
                "island": {"to-Latn": "Tongatapu", "en": "Tongatapu"},
            },
            "TO",
        )
        self.assertIn("15 Hala Taufaʻahau", result.native.lines)
        self.assertIn("Nukuʻalofa", result.native.lines)
        self.assertIn("Tongatapu", result.native.lines)
        self.assertNotIn("provisional_country_profile", result.warnings)

    def test_po_box_route_does_not_invent_street_or_postcode(self):
        result = render_oceania_address(
            {
                "country_code": "FJ",
                "organization": {
                    "fj-Latn": "Post Fiji",
                    "en": "Post Fiji",
                },
                "po_box": {"fj-Latn": "PO Box 100", "en": "PO Box 100"},
                "city": {"fj-Latn": "SUVA", "en": "SUVA"},
            },
            "FJ",
        )
        self.assertIn("PO Box 100", result.native.lines)
        self.assertIn("SUVA", result.native.lines)
        self.assertNotIn("road", result.native.components)
        self.assertNotIn("postcode", result.native.components)

    def test_provisional_island_route_is_machine_visible(self):
        result = render_oceania_address(
            {
                "country_code": "SB",
                "city": {"pis-Latn": "HONIARA", "en": "HONIARA"},
                "island": {"pis-Latn": "Guadalcanal", "en": "Guadalcanal"},
            },
            "SB",
        )
        self.assertIn("provisional_country_profile", result.warnings)

    def test_same_latin_script_never_silently_fills_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_oceania_address(
                {
                    "country_code": "WS",
                    "road": {"sm-Latn": "Alatele Beach Road"},
                    "city": {"sm-Latn": "APIA"},
                },
                "WS",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(error.exception.components, ("city", "road"))


if __name__ == "__main__":
    unittest.main()
