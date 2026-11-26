"""Public address API behaviour for a bounded LINZ district snapshot."""

import unittest

from addressing.address_ai import process_request


class LinzPointTests(unittest.TestCase):
    def validate(self, **components):
        return process_request(dict(operation="validate", country="NZ", components=components))["result"]

    def test_official_record_and_unverified_postcode(self):
        fields = dict(municipality="Chatham Islands Territory", road="North Road", house_number="1059",
                      city="Chatham Islands", suburb="Chatham Island")
        result = self.validate(**fields)
        self.assertEqual(result["matched_scope"], "published_address_point")
        self.assertEqual(set(result["verified_fields"]), set(fields))
        self.assertEqual(result["evidence"][0]["record_id"], "35142")
        self.assertEqual(result["evidence"][0]["license"], "CC BY 4.0")
        self.assertFalse(result["deliverability_verified"])
        with_postcode = self.validate(**fields, postcode="9999")
        self.assertEqual(with_postcode["status"], "partial")
        self.assertEqual(with_postcode["unverified_fields"], ["postcode"])

    def test_fields_are_compared_on_one_record(self):
        fields = dict(municipality="Chatham Islands Territory", road="North Road", house_number="1059")
        for change in (dict(suburb="Waitangi"), dict(city="Hamilton"), dict(municipality="Gore District"),
                       dict(house_number="999999"), dict(unit="999"), dict(address_line1="9 North Road")):
            with self.subTest(change=change):
                self.assertNotIn("house_number", self.validate(**(fields | change))["verified_fields"])
        self.assertNotIn("house_number", self.validate(road="North Road", house_number="1059")["verified_fields"])

    def test_unitless_search_preserves_published_choices(self):
        fields = dict(municipality="Gore District", road="Kana Street", house_number="57")
        validation = self.validate(**fields)
        result = validation["address1_decision"]
        self.assertEqual((result["status"], result["level"], result["candidate_count"]), ("ambiguous", "street", 8))
        self.assertIn("house_number", result["unverified_fields"])
        self.assertIn("unit_required_to_distinguish_address", validation["issues"])
        unit = self.validate(**fields, unit="1")["address1_decision"]
        self.assertEqual((unit["status"], unit["level"], unit["candidate_count"]), ("verified", "unit", 1))

    def test_wallet_locality_and_intact_primary_line_search_the_covered_districts(self):
        unit = self.validate(city="Mataura", line1="1/57 Kana Street")
        self.assertEqual(unit["address1_decision"]["level"], "unit")
        self.assertEqual(unit["evidence"][0]["record_id"], "114023")
        shared = self.validate(city="Mataura", line1="57 Kana Street")["address1_decision"]
        self.assertEqual((shared["level"], shared["candidate_count"]), ("street", 8))
        self.assertEqual(self.validate(city="Hamilton", line1="1/57 Kana Street")["address1_decision"]["level"], "none")
        self.assertNotEqual(self.validate(line1="1/57 Kana Street")["address1_decision"]["status"], "verified")
        extra = self.validate(city="Mataura", line1="1/57 Kana Street", state="Other region")
        self.assertEqual(extra["address1_decision"]["status"], "partial")
        self.assertIn("state", extra["address1_decision"]["unverified_fields"])

    def test_unit_and_source_range(self):
        fields = dict(municipality="Gore District", road="Kana Street", house_number="57", unit="1",
                      address_line1="1/57 Kana Street")
        result = self.validate(**fields)
        self.assertEqual(set(result["verified_fields"]), set(fields))
        self.assertIn("114023", [r["record_id"] for r in result["evidence"]])
        wrong = self.validate(**(fields | {"unit": "999"}))
        self.assertNotIn("unit", wrong["verified_fields"])

        fields = dict(municipality="Kaikoura District", road="West End", house_number="17-19", city="Kaikōura")
        result = self.validate(**fields)
        self.assertIn("328984", [r["record_id"] for r in result["evidence"]])
        others = self.validate(**(fields | {"house_number": "18"}))
        self.assertNotIn("328984", [r["record_id"] for r in others["evidence"]])
