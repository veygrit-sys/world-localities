"""Evidence-aware postal/locator syntax tests: SA, BH, QA, OM and PS."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from addressing import WesternAsiaRegistry, validate_western_asia_reference as check
from addressing.western_asia_reference import reference_rules, inspect_western_asia_reference


class Inventory(unittest.TestCase):
    def test_existing_18_country_native_profiles_remain(self):
        p = WesternAsiaRegistry()
        self.assertEqual(len(p.countries), 18)
        self.assertEqual({key: p.get(key)["native_languages"] for key in
            ("SA", "BH", "QA", "OM", "PS")},
            {"SA": ["ar"], "BH": ["ar"], "QA": ["ar"], "OM": ["ar"], "PS": ["ar"]})

    def test_source_gates(self):
        for code in ("SA", "BH", "QA", "OM", "PS"):
            entry = inspect_western_asia_reference(code)
            self.assertTrue(entry["sources"])
            self.assertFalse(entry["deliverability_verified"])
            self.assertFalse(entry["national_completeness_verified"])
            self.assertEqual(entry["verified_postcode_records"], 0)
        self.assertEqual(set(reference_rules()["countries"]),
                         {"TR","CY","KW","AE","SA","BH","QA","OM","PS"})


class SaudiNationalAddress(unittest.TestCase):
    def test_five_digit_postcode_and_short_address_distinct(self):
        r = check("SA", postcode="13337", building_number="2929",
                  additional_number="8118", short_address="RAGI2929",
                  road="Rayhanah Bint Zaid", district="Al Arid", city="Riyadh",
                  require_complete=True)
        self.assertEqual(r["status"], "format_only")
        self.assertEqual(r["normalized"]["short_address"], "RAGI2929")
        self.assertEqual(r["normalized"]["postcode"], "13337")
        self.assertFalse(r["checks"]["building_verified"])
        self.assertEqual(check("SA", short_address="ragi2929")["normalized"]["short_address"], "RAGI2929")
        self.assertNotIn("postcode", check("SA", short_address="RAGI2929")["normalized"])

    def test_bad_short_and_number_mismatch(self):
        self.assertEqual(check("SA", short_address="RAGI29A9")["status"], "invalid_format")
        self.assertEqual(check("SA", short_address="RAGI2929", building_number="1234")["status"], "invalid_format")
        self.assertEqual(check("SA", postcode="۱۳۳۳۷")["status"], "invalid_format")
        self.assertEqual(check("SA", postcode="13337", additional_number="12")["status"], "invalid_format")

    def test_no_claim_of_full_address_from_short_code(self):
        r = check("SA", short_address="RAGI2929", require_complete=True)
        self.assertEqual(r["status"], "incomplete")
        self.assertIn("postcode_missing", r["missing"])

class BahrainPost(unittest.TestCase):
    def test_three_and_four_digit_examples(self):
        a = check("BH", postcode="317")
        b = check("BH", postcode="1200")
        self.assertEqual(a["status"], "format_only")
        self.assertEqual(b["status"], "format_only")
        self.assertEqual(check("BH", postcode="926", building_number="916",
                               road="Road 2035", city="Riffa", require_complete=True)["status"], "format_only")

    def test_invalid_range_and_missing_full_address(self):
        self.assertEqual(check("BH", postcode="0099")["status"], "invalid_format")
        self.assertEqual(check("BH", postcode="1300")["status"], "invalid_format")
        self.assertEqual(check("BH", postcode="317", require_complete=True)["status"], "incomplete")
        self.assertEqual(check("BH", postcode="317", delivery_mode="po_box",
                               po_box="1212", city="Manama",
                               require_complete=True)["status"], "format_only")

class QatarAnwani(unittest.TestCase):
    def test_home_delivery_three_numbers_without_postcode(self):
        r = check("QA", zone="38", street_number="904",
                  building_number="15", phone="33312826")
        self.assertEqual(r["status"], "format_only")
        self.assertNotIn("postcode", r["normalized"])
        self.assertFalse(r["checks"]["locality_membership_verified"])

    def test_missing_plate_fields_and_english_inbound_note(self):
        self.assertEqual(check("QA", zone="38", street_number="904")["status"], "incomplete")
        r = check("QA", delivery_mode="po_box", po_box="3263", direction="inbound")
        self.assertEqual(r["status"], "format_only")
        self.assertIn("qatar_inbound_postal_lines_use_english_doha_qatar", r["warnings"])
        self.assertEqual(check("QA", zone="III", street_number="904",
                               building_number="15")["status"], "invalid_format")

    def test_not_fabricating_a_national_postcode(self):
        r = check("QA", postcode="00000", zone="38",
                  street_number="904", building_number="15")
        self.assertEqual(r["status"], "format_unverified")
        self.assertEqual(r["normalized"]["postcode"], "00000")
        self.assertFalse(r["checks"]["postcode_assignment_verified"])

class OmanPost(unittest.TestCase):
    def test_po_box_three_digit_office_code(self):
        r = check("OM", postcode="133", po_box="15",
                  locality="Al-Khuwair", delivery_mode="po_box", require_complete=True)
        self.assertEqual(r["status"], "format_only")
        self.assertEqual(r["normalized"]["postcode"], "133")
        self.assertFalse(r["checks"]["deliverability_verified"])

    def test_missing_box_and_wrong_code(self):
        self.assertEqual(check("OM", postcode="133", delivery_mode="po_box")["status"], "incomplete")
        self.assertEqual(check("OM", postcode="1333", po_box="15",
                               delivery_mode="po_box")["status"], "invalid_format")
        self.assertEqual(check("OM", postcode="133", locality="Muscat")["status"], "format_unverified")

class PalestinePost(unittest.TestCase):
    def test_area_fallback_and_full_delivery_point_are_separate(self):
        area = check("PS", postcode="p610")
        full = check("PS", postcode="P6100154")
        self.assertEqual(area["status"], "format_only")
        self.assertEqual(area["normalized"]["postcode"], "P610")
        self.assertEqual(area["normalized"]["postcode_kind"], "area")
        self.assertEqual(full["normalized"]["postcode_kind"], "delivery_point_structure")
        self.assertFalse(full["checks"]["building_verified"])
        self.assertIn("palestine_area_code_not_final_delivery_point", area["warnings"])

    def test_require_point_rejects_area_only_completeness(self):
        self.assertEqual(check("PS", postcode="P610", city="Ramallah",
                               require_complete=True)["status"], "incomplete")
        self.assertEqual(check("PS", postcode="P6100154", city="Ramallah",
                               require_complete=True)["status"], "format_only")
        self.assertEqual(check("PS", postcode="P610xxxx")["status"], "invalid_format")
        self.assertEqual(check("PS", postcode="P61")["status"], "invalid_format")
        self.assertEqual(check("PS", postcode="6100154")["status"], "invalid_format")
        self.assertEqual(check("PS", postcode="P6100154", po_box="674",
                               city="Ramallah", delivery_mode="po_box",
                               require_complete=True)["status"], "format_only")

class CrossCountryBoundary(unittest.TestCase):
    def test_unrelated_identifiers_refused(self):
        self.assertEqual(check("QA", zone="1", street_number="2", building_number="3",
                               short_address="RAGI2929")["status"], "invalid_format")
        self.assertEqual(check("PS", postcode="P6100154",
                               makani="3003295320")["status"], "invalid_format")
        self.assertEqual(check("OM", postcode="133", zone="3")["status"], "invalid_format")

    def test_unsafe_unicode_and_unsupported_country(self):
        with self.assertRaises(ValueError):
            check("SA", short_address="RAGI2929\u202e")
        with self.assertRaises(ValueError):
            check("XX", postcode="12345")

    def test_all_five_never_claim_verification(self):
        checks = [
            check("SA", postcode="13337"),
            check("BH", postcode="317"),
            check("QA", zone="38", street_number="904", building_number="15"),
            check("OM", postcode="133", po_box="15", delivery_mode="po_box"),
            check("PS", postcode="P6100154"),
        ]
        for rec in checks:
            self.assertFalse(rec["checks"]["postcode_assignment_verified"])
            self.assertFalse(rec["checks"]["locality_membership_verified"])
            self.assertFalse(rec["checks"]["building_verified"])
            self.assertFalse(rec["checks"]["deliverability_verified"])


if __name__ == "__main__":
    unittest.main()
