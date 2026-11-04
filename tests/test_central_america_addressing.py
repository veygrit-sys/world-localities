"""Domestic-language, English and postcode tests for Central America."""

import importlib.util
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    CentralAmericaRegistry,
    MissingLocalizedComponents,
    ProfileRegistry,
    render_central_america_address,
)


EXPECTED_PROFILES = {
    "BZ": ({"en": "BZ_en", "es-Latn": "BZ_es"}, "BZ_en"),
    "CR": ({"es-Latn": "CR_es"}, "CR_en"),
    "GT": ({"es-Latn": "GT_es"}, "GT_en"),
    "HN": ({"es-Latn": "HN_es"}, "HN_en"),
    "MX": ({"es-Latn": "MX_es"}, "MX_en"),
    "NI": ({"es-Latn": "NI_es"}, "NI_en"),
    "PA": ({"es-Latn": "PA_es"}, "PA_en"),
    "SV": ({"es-Latn": "SV_es"}, "SV_en"),
}


def imported(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CentralAmericaProfileCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.profiles = ProfileRegistry()
        cls.central_america = CentralAmericaRegistry()

    def test_all_eight_m49_countries_have_domestic_and_english_profiles(self):
        self.assertEqual(set(self.central_america.countries), set(EXPECTED_PROFILES))
        for country, (native_profiles, english_profile) in EXPECTED_PROFILES.items():
            with self.subTest(country=country):
                policy = self.central_america.get(country)
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

    def test_report_has_nine_domestic_variants_and_no_provisional_route(self):
        self.assertEqual(
            self.central_america.report(),
            {
                "status": "passed",
                "reviewed_at": "2026-10-17",
                "countries": 8,
                "native_language_variants": 9,
                "english_profiles": 8,
                "provisional_countries": [],
            },
        )

    def test_every_country_has_postcode_script_and_source_policy(self):
        for country, policy in self.central_america.countries.items():
            with self.subTest(country=country):
                self.assertIn("postcode_pattern", policy)
                self.assertIsInstance(policy["postcode_required"], bool)
                self.assertEqual(
                    set(policy["native_scripts"]), set(policy["native_languages"])
                )
                self.assertTrue(policy["romanization_policy"])
                self.assertTrue(policy["sources"])

    def test_all_eight_locality_sources_replay_without_delivery_claims(self):
        linkage = self.central_america.locality_registry
        quality = imported("addressing_central_quality", linkage["quality_module"])
        report = quality.verify_all(ROOT)
        by_country = {item["country"]: item for item in report["countries"]}

        self.assertEqual(report["country_source_coverage"], "8/8")
        self.assertEqual(set(linkage["materialized_countries"]), set(EXPECTED_PROFILES))
        self.assertEqual(linkage["source_locality_rows"], 59641)
        self.assertEqual(
            sum(item["source_locality_rows"] for item in by_country.values()),
            linkage["source_locality_rows"],
        )
        self.assertEqual(linkage["direct_id_postal_alias_rows"], 6)
        self.assertEqual(
            sum((item.get("postal_links") or 0) for item in by_country.values()),
            linkage["direct_id_postal_alias_rows"],
        )
        self.assertTrue(all(not item["delivery_verified"] for item in by_country.values()))
        self.assertTrue(
            all(not item["current_official_hierarchy_verified"] for item in by_country.values())
        )

    def test_country_outside_region_is_rejected(self):
        with self.assertRaisesRegex(KeyError, "outside Central America"):
            self.central_america.get("CU")


class CentralAmericaPostcodePolicies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.central_america = CentralAmericaRegistry()

    def test_current_country_specific_postcode_syntax_is_accepted(self):
        valid = {
            "CR": ("10102",),
            "GT": ("01001",),
            "HN": ("11101",),
            "MX": ("02860",),
            "NI": ("12005",),
            "PA": ("0801", "69R3E8CV", "A7C95-69R3E", "A31234-5678"),
            "SV": ("1120",),
        }
        for country, postcodes in valid.items():
            for postcode in postcodes:
                with self.subTest(country=country, postcode=postcode):
                    self.assertTrue(
                        self.central_america.validate_postcode(country, postcode)
                    )

    def test_honduras_and_panama_transition_forms_are_classified(self):
        classify = self.central_america.postcode_variant
        self.assertEqual(classify("HN", "11101"), "current_numeric")
        self.assertEqual(classify("HN", "CM1102"), "legacy_alphanumeric")
        self.assertEqual(classify("PA", "0801"), "legacy_four_digit")
        self.assertEqual(classify("PA", "69R3E8CV"), "geolocated_grid")
        self.assertEqual(classify("PA", "A7C95-69R3E"), "geolocated_full")
        self.assertIsNone(classify("PA", "00000"))

    def test_wrong_country_forms_are_rejected(self):
        invalid = {
            "CR": ("1010", "101020"),
            "GT": ("0100", "GT01001"),
            "HN": ("CM102", "CM-1102"),
            "MX": ("2860", "028600"),
            "NI": ("1200", "NI12005"),
            "PA": ("00000", "A7C95_69R3E"),
            "SV": ("112", "01120"),
        }
        for country, postcodes in invalid.items():
            for postcode in postcodes:
                with self.subTest(country=country, postcode=postcode):
                    self.assertFalse(
                        self.central_america.validate_postcode(country, postcode)
                    )

    def test_belize_rejects_invented_postcode_placeholders(self):
        self.assertTrue(self.central_america.validate_postcode("BZ", None))
        self.assertTrue(self.central_america.validate_postcode("BZ", ""))
        self.assertFalse(self.central_america.validate_postcode("BZ", "00000"))

    def test_seven_coded_countries_require_a_postcode(self):
        for country in set(EXPECTED_PROFILES) - {"BZ"}:
            with self.subTest(country=country):
                self.assertFalse(self.central_america.validate_postcode(country, None))


class CentralAmericaAddressRendering(unittest.TestCase):
    def test_belize_spanish_route_keeps_address2_area_and_city_without_postcode(self):
        result = render_central_america_address(
            {
                "country_code": "BZ",
                "road": {"es-Latn": "C Street", "en": "C Street"},
                "house_number": "12",
                "address2": {"es-Latn": "Apto 2", "en": "Apt 2"},
                "neighbourhood": {"es-Latn": "KINGS PARK", "en": "KINGS PARK"},
                "city": {"es-Latn": "BELIZE CITY", "en": "BELIZE CITY"},
            },
            "BZ",
            native_language="es-Latn",
        )
        self.assertEqual(result.native.profile_key, "BZ_es")
        self.assertIn("Apto 2", result.native.lines)
        self.assertIn("12 C Street", result.native.lines)
        self.assertIn("KINGS PARK, BELIZE CITY", result.native.lines)
        self.assertNotIn("postcode", result.native.components)
        self.assertFalse(result.native.unrendered_components)

    def test_costa_rica_keeps_descriptive_direction_and_three_level_hierarchy(self):
        result = render_central_america_address(
            {
                "country_code": "CR",
                "road": {"es-Latn": "Calle 15 Avenida 37", "en": "15th Street 37th Avenue"},
                "house_number": "55",
                "place": {"es-Latn": "100 m este de la iglesia", "en": "100 m east of the church"},
                "state": {"es-Latn": "Heredia", "en": "Heredia"},
                "county": {"es-Latn": "San Rafael", "en": "San Rafael"},
                "city": {"es-Latn": "San Rafael", "en": "San Rafael"},
                "postcode": "40501",
            },
            "CR",
        )
        self.assertIn("Calle 15 Avenida 37 55", result.native.lines)
        self.assertIn("100 m este de la iglesia", result.native.lines)
        self.assertIn("Heredia, San Rafael, San Rafael", result.native.lines)
        self.assertIn("40501", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_guatemala_keeps_zone_address2_and_rural_reference(self):
        result = render_central_america_address(
            {
                "country_code": "GT",
                "road": {"es-Latn": "6a Avenida A", "en": "6th Avenue A"},
                "house_number": "10-13",
                "neighbourhood": {"es-Latn": "Zona 1", "en": "Zone 1"},
                "address2": {"es-Latn": "Torre 2, apartamento 608", "en": "Tower 2, apartment 608"},
                "place": {"es-Latn": "Finca Parga, lote 5", "en": "Parga Estate, lot 5"},
                "municipality": {"es-Latn": "Guatemala", "en": "Guatemala City"},
                "state": {"es-Latn": "Guatemala", "en": "Guatemala Department"},
                "postcode": "01001",
            },
            "GT",
        )
        self.assertIn("6a Avenida A 10-13", result.native.lines)
        self.assertIn("Zona 1", result.native.lines)
        self.assertIn("Torre 2, apartamento 608", result.native.lines)
        self.assertIn("Finca Parga, lote 5", result.native.lines)
        self.assertIn("01001 Guatemala, Guatemala", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_honduras_keeps_barrio_locality_department_and_legacy_code(self):
        result = render_central_america_address(
            {
                "country_code": "HN",
                "road": {"es-Latn": "3era Avenida", "en": "3rd Avenue"},
                "house_number": "14",
                "neighbourhood": {"es-Latn": "Barrio El Centro", "en": "El Centro District"},
                "city": {"es-Latn": "LAS LAJAS", "en": "LAS LAJAS"},
                "state": {"es-Latn": "Comayagua", "en": "Comayagua"},
                "postcode": "CM1102",
            },
            "HN",
        )
        self.assertIn("3era Avenida 14", result.native.lines)
        self.assertIn("Barrio El Centro", result.native.lines)
        self.assertIn("CM1102 LAS LAJAS, Comayagua", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_mexico_keeps_exterior_interior_colonia_municipality_and_postal_state_code(self):
        result = render_central_america_address(
            {
                "country_code": "MX",
                "road": {"es-Latn": "Urión", "en": "Urion Street"},
                "house_number": "30",
                "address2": {"es-Latn": "Interior 4", "en": "Interior 4"},
                "neighbourhood": {"es-Latn": "Col. Tlatilco", "en": "Tlatilco"},
                "municipality": {"es-Latn": "Azcapotzalco", "en": "Azcapotzalco"},
                "city": {"es-Latn": "MÉXICO", "en": "MEXICO CITY"},
                "state_code": "CDMX",
                "postcode": "02860",
            },
            "MX",
        )
        self.assertIn("Urión 30", result.native.lines)
        self.assertIn("Interior 4", result.native.lines)
        self.assertIn("Col. Tlatilco", result.native.lines)
        self.assertIn("Azcapotzalco", result.native.lines)
        self.assertIn("02860 MÉXICO, CDMX", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_nicaragua_keeps_traditional_direction_neighbourhood_and_code_line(self):
        result = render_central_america_address(
            {
                "country_code": "NI",
                "place": {"es-Latn": "Portón Cementerio General 1c Este, 1/2c Norte", "en": "General Cemetery gate, 1 block east and half a block north"},
                "neighbourhood": {"es-Latn": "Barrio Santa Ana Sur", "en": "South Santa Ana District"},
                "city": {"es-Latn": "Managua", "en": "Managua"},
                "state": {"es-Latn": "Managua", "en": "Managua"},
                "postcode": "12005",
            },
            "NI",
        )
        self.assertIn("Portón Cementerio General 1c Este, 1/2c Norte", result.native.lines)
        self.assertIn("Barrio Santa Ana Sur", result.native.lines)
        self.assertIn("12005", result.native.lines)
        self.assertIn("Managua, Managua", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_panama_keeps_new_geolocated_code_and_complex_address2(self):
        result = render_central_america_address(
            {
                "country_code": "PA",
                "road": {"es-Latn": "Vía España, Calle 6ta", "en": "Via Espana, 6th Street"},
                "address2": {"es-Latn": "Edificio Del Padro No. 2, piso 3, local 10", "en": "Del Padro Building No. 2, floor 3, unit 10"},
                "neighbourhood": {"es-Latn": "Parque Lefevre", "en": "Parque Lefevre"},
                "city": {"es-Latn": "Ciudad de Panamá", "en": "Panama City"},
                "state": {"es-Latn": "Provincia de Panamá", "en": "Panama Province"},
                "postcode": "A7C95-69R3E",
            },
            "PA",
        )
        self.assertIn("Vía España, Calle 6ta", result.native.lines)
        self.assertIn("Edificio Del Padro No. 2, piso 3, local 10", result.native.lines)
        self.assertIn("A7C95-69R3E", result.native.lines)
        self.assertIn("Ciudad de Panamá", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_panama_po_box_path_remains_separate_from_home_delivery(self):
        result = render_central_america_address(
            {
                "country_code": "PA",
                "po_box": {"es-Latn": "APARTADO POSTAL 0832-02345", "en": "P.O. BOX 0832-02345"},
                "city": {"es-Latn": "PARQUE LEFEVRE", "en": "PARQUE LEFEVRE"},
                "state": {"es-Latn": "PROVINCIA DE PANAMÁ", "en": "PANAMA PROVINCE"},
                "postcode": "0801",
            },
            "PA",
        )
        self.assertIn("APARTADO POSTAL 0832-02345", result.native.lines)
        self.assertIn("0801", result.native.lines)
        self.assertNotIn("road", result.native.components)

    def test_el_salvador_keeps_address2_colonia_postcode_locality_and_department(self):
        result = render_central_america_address(
            {
                "country_code": "SV",
                "road": {"es-Latn": "6a Avenida Norte", "en": "6th Avenue North"},
                "house_number": "165",
                "address2": {"es-Latn": "Casa H, segundo nivel", "en": "House H, second floor"},
                "neighbourhood": {"es-Latn": "Colonia San Fernando", "en": "San Fernando District"},
                "city": {"es-Latn": "SOYAPANGO", "en": "SOYAPANGO"},
                "state": {"es-Latn": "SAN SALVADOR", "en": "SAN SALVADOR"},
                "postcode": "1120",
            },
            "SV",
        )
        self.assertIn("6a Avenida Norte 165", result.native.lines)
        self.assertIn("Casa H, segundo nivel", result.native.lines)
        self.assertIn("Colonia San Fernando", result.native.lines)
        self.assertIn("1120 SOYAPANGO, SAN SALVADOR", result.native.lines)
        self.assertFalse(result.native.unrendered_components)

    def test_shared_latin_script_does_not_fill_missing_english(self):
        with self.assertRaises(MissingLocalizedComponents) as error:
            render_central_america_address(
                {
                    "country_code": "CR",
                    "place": {"es-Latn": "100 m este de la iglesia"},
                    "city": {"es-Latn": "San Rafael"},
                    "state": {"es-Latn": "Heredia"},
                    "county": {"es-Latn": "San Rafael"},
                    "postcode": "40501",
                },
                "CR",
            )
        self.assertEqual(error.exception.language, "en")
        self.assertEqual(
            error.exception.components,
            ("city", "county", "place", "state"),
        )


if __name__ == "__main__":
    unittest.main()
