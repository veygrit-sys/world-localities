import unittest

from localities.open_reference.au_gnaf import validate_point


def check(**values):
    return validate_point(values, lambda status, **detail: dict(status=status, **detail))


class AustraliaGnafContextTest(unittest.TestCase):
    def test_gnaf_only_does_not_authorize_mailing_at_public_boundary(self):
        from addressing.address_ai import process_request
        fields = {"line1": "24 Marrawaraga Road", "city": "Jervis Bay", "state": "OT"}
        request = {"country": "AU", "components": fields}
        doc = process_request({"operation": "validate", **request})["result"]
        decision = doc["address1_decision"]
        self.assertEqual((decision["status"], decision["level"], decision["candidate_count"]), ("partial", "premise", 1))
        self.assertIn("address_line1", decision["verified_fields"])
        self.assertIn("gnaf_independent_mailing_source_required", doc["issues"])
        prepared = process_request({"operation": "prepare_label", **request, "profile_id": "test-au"},
                                   label_profiles={"test-au": {"id": "test-au"}})["result"]
        self.assertEqual((prepared["status"], prepared["carrier_fields"]), ("review_required", None))

    def test_single_extracted_unit_does_not_substitute_for_parent(self):
        from unittest.mock import patch
        from addressing.address_ai import process_request
        from localities.open_reference.au_gnaf import _index
        manifest, lines, links = _index()
        street = ("jervis bay", "66 village road")
        unit = lines[street][0]
        with patch("localities.open_reference.au_gnaf._index", return_value=(manifest, {street: [unit]}, links)):
            fields = {"line1": "66 Village Road", "city": "Jervis Bay", "state": "OT"}
            def decision(values):
                return process_request({"operation": "validate", "country": "AU", "components": values})["result"]["address1_decision"]
            self.assertEqual(decision(fields)["level"], "street")
            self.assertEqual(decision(fields | {"unit": "UNIT 1"})["level"], "unit")

    def test_jervis_bay_physical_point_with_original_geocode_type(self):
        result = check(city="Jervis Bay", state="OT", address_line1="24 Marrawaraga Road",
                       postcode="2540")
        self.assertEqual((result["status"], result["scope"]), ("partial", "physical_address_context"))
        self.assertEqual(result["candidate_count"], 1)
        self.assertNotIn("postcode", result["checked"])
        receipt = result["evidence"][0]
        self.assertEqual(receipt["record_id"], "GAOT_719401230")
        self.assertEqual(receipt["geography"]["geocode_type"], "BUILDING CENTROID")
        self.assertAlmostEqual(receipt["geography"]["latitude"], -35.16855224)
        self.assertIn("gnaf_independent_mailing_source_required", result["issues"])

    def test_jervis_bay_is_not_an_act_locality_or_an_external_island_alias(self):
        fields = {"city": "Jervis Bay", "road": "Marrawaraga Road", "house_number": "24"}
        self.assertIsNone(check(**fields, state_code="ACT"))
        self.assertIsNone(check(**dict(fields, city="Christmas Island")))
        self.assertIsNone(check(**fields, po_box="24"))

    def test_explicit_secondary_edge_keeps_provenance(self):
        fields = dict(suburb="Jervis Bay", state="Jervis Bay Territory", road="Village Road", house_number="66")
        self.assertEqual(check(**fields)["status"], "ambiguous")
        unit = check(**fields, unit="UNIT 1")
        self.assertEqual(unit["candidate_count"], 1)
        receipt = unit["evidence"][0]
        self.assertEqual(receipt["record_id"], "GAOT_717321094")
        self.assertEqual(receipt["primary_address_relation"]["primary_pid"], "GAOT_717321601")
        self.assertEqual(receipt["primary_address_relation"]["join_type"], "AUTO")
        self.assertEqual(receipt["geography"]["geocode_type"], "STREET LOCALITY")
        self.assertEqual(check(**fields, unit="UNIT 99999")["candidate_count"], 0)

    def test_structured_street_and_number_stay_bound_to_one_row(self):
        result = check(city="Barton", state_code="ACT", address_line1="24 Darling Street",
                       road="Darling Street", house_number="22")
        self.assertEqual(result["candidate_count"], 0)
        self.assertIsNone(check(suburb="Acton", state_code="ACT", road="Darling Street", house_number="24"))
