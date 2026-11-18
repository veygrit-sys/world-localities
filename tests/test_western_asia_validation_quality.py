"""Country validators keep published examples, syntax, and assignment distinct."""

import unittest
from unittest.mock import patch

from addressing import inspect_western_asia_reference, validate_western_asia_country as validate
from addressing import validate_western_asia_reference
from addressing.western_asia_reference_expanded import validate_gulf_levant_reference
from scripts.western_asia_caucasus_levant_join import load_sources


class PostalExcerptQuality(unittest.TestCase):
    def test_all_46_excerpt_records_can_be_recovered_by_their_own_fields(self):
        data = load_sources()
        self.assertEqual(len(data["postal_evidence"]), 46)
        for row in data["postal_evidence"]:
            with self.subTest(record=row["record_id"]):
                result = validate(row["country"], row["code"], locality=row["place"],
                                  admin_name=row["admin_name"])
                self.assertEqual(result["status"], "fields_observed_together")
                excerpt = result["postal_excerpt"]
                self.assertIn(row["record_id"], excerpt["matching_record_ids"])
                rec = next(r for r in excerpt["postcode_records"] if r["record_id"] == row["record_id"])
                source = data["postal_sources"][row["source_id"]]
                self.assertEqual((rec["grain"], rec["published"], rec["source_url"]),
                                 (row["grain"], source["published"], source["url"]))
                self.assertFalse(result["checks"]["official_postal_assignment_verified"])
                self.assertFalse(result["checks"]["carrier_deliverability_verified"])

    def test_mismatched_or_missing_evidence_never_rejects_a_real_address(self):
        wrong = validate("AM", "0002", locality="Vedi", admin_name="Ararat")
        self.assertEqual(wrong["status"], "format_unverified")
        self.assertEqual(wrong["postal_excerpt"]["status"], "fields_not_observed_together")
        self.assertEqual(wrong["postal_excerpt"]["matching_record_ids"], [])
        self.assertEqual(wrong["postal_excerpt"]["postcode_records"][0]["locality"], "Yerevan")
        unlisted = validate("AM", "9999", locality="Yerevan")
        self.assertEqual(unlisted["postal_excerpt"]["status"], "postcode_not_in_excerpt")
        unavailable = validate("IL", "7178437", locality="Modiin-Maccabim-Reut", admin_name="Central")
        self.assertEqual(unavailable["status"], "format_unverified")
        self.assertIsNone(unavailable["postal_excerpt"]["postcode_records"][0]["admin_name"])

    def test_filters_cannot_combine_place_and_parent_from_different_records(self):
        data = load_sources()
        first = data["postal_evidence"][0]
        second = dict(first, record_id="test-only", place="Other", admin_name="Ararat")
        data["postal_evidence"] = [first, second]
        with patch("scripts.western_asia_caucasus_levant_join.load_sources", return_value=data):
            result = validate("AM", first["code"], locality=first["place"], admin_name="Ararat")
            self.assertEqual(result["postal_excerpt"]["matching_record_ids"], [])
            self.assertEqual(len(result["postal_excerpt"]["postcode_records"]), 2)
            self.assertEqual(result["status"], "format_unverified")

    def test_normalization_preserves_local_names_and_only_matches_in_selected_country(self):
        value = validate("az", "az7213", locality="  Dizə  ")
        rec = value["postal_excerpt"]["postcode_records"][0]
        self.assertEqual((rec["postcode"], rec["locality"], rec["language"]), ("AZ7213", "Dizə", "az-Latn"))
        self.assertEqual(value["status"], "fields_observed_together")
        self.assertEqual(validate("AZ", "AZ7213", locality="Diza")["status"], "format_unverified")
        self.assertEqual(validate("GE", "0001", locality="Yerevan")["status"], "format_unverified")

    def test_azeri_dotted_and_dotless_i_remain_distinct(self):
        for code, label in (("AZ7403", "QIVRAQ"), ("AZ7213", "DİZƏ"), ("AZ7213", "DI\u0307ZƏ")):
            with self.subTest(code=code, label=label):
                self.assertEqual(validate("AZ", code, locality=label)["status"], "fields_observed_together")
        self.assertEqual(validate("AZ", "AZ7213", locality="DIZƏ")["status"], "format_unverified")

    def test_exact_source_match_preserves_distinct_letters_and_rejects_controls(self):
        self.assertEqual(validate("GE", "0160", locality="TBILISI", admin_name="Tbilisi  City")["status"],
                         "fields_observed_together")
        for fields in ({"locality": "Tbiliſi"}, {"admin_name": "Tbiliſi City"}):
            with self.subTest(fields=fields):
                result = validate("GE", "0160", **fields)
                self.assertEqual(result["status"], "format_unverified")
                self.assertEqual(result["postal_excerpt"]["matching_record_ids"], [])
        for fields in ({"locality": "Tbilisi\n"}, {"admin_name": "\tTbilisi City"}, {"locality": "\x00"}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                validate("GE", "0160", **fields)

    def test_postcode_only_remains_syntax_check_and_bad_input_cannot_match(self):
        result = validate("GE", "0160")
        self.assertEqual(result["status"], "format_only")
        self.assertEqual(result["postal_excerpt"]["status"], "postcode_observed")
        self.assertEqual(validate("GE", "016", locality="Tbilisi")["status"], "invalid_format")
        self.assertEqual(validate("GE", locality="Tbilisi")["status"], "incomplete")
        with self.assertRaises(TypeError):
            validate("GE", 160)
        with self.assertRaises(ValueError):
            validate("GE", "0160", locality="Tbi\u202elisi")


class IdentifierScope(unittest.TestCase):
    def test_only_two_ascii_letters_select_a_country(self):
        self.assertEqual(validate("il", "9414219")["country"], "IL")
        for code in ("ıL", "Pſ", "ſY"):
            with self.subTest(code=code), self.assertRaises(ValueError):
                validate(code)
        for entry in (inspect_western_asia_reference, validate_western_asia_reference,
                      validate_gulf_levant_reference):
            with self.subTest(entry=entry), self.assertRaises(ValueError):
                entry("Pſ")

    def test_emirate_code_is_not_a_selector_for_turkish_cypriot_or_kuwaiti_addresses(self):
        for country, code in (("TR", "06101"), ("CY", "2008"), ("KW", "54404")):
            with self.subTest(country=country):
                result = validate(country, code, emirate="AE-DU")
                self.assertEqual(result["status"], "invalid_format")
                self.assertIn("uae_identifier_on_non_uae_address", result["errors"])
                self.assertNotIn("emirate", result["normalized"])

    def test_qatari_po_box_does_not_validate_malformed_optional_locator(self):
        for field in ("zone", "street_number", "building_number"):
            with self.subTest(field=field):
                result = validate("QA", delivery_mode="po_box", po_box="3263", **{field: "abc"})
                self.assertEqual(result["status"], "invalid_format")
                self.assertIn(field + "_format_invalid", result["errors"])
        self.assertEqual(validate("QA", delivery_mode="po_box", po_box="3263")["status"], "format_only")

    def test_country_wrapper_reports_which_missing_fields_need_attention(self):
        result = validate("SA", short_address="RAGI2929", require_complete=True)
        self.assertEqual(result["status"], "incomplete")
        self.assertIn("postcode_missing", result["missing"])
        self.assertIn("po_box_missing", validate("IQ", "54001", delivery_mode="po_box")["missing"])
        self.assertIn("postcode_missing", validate("TR")["missing"])
