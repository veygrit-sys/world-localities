import unittest

from localities.open_reference.ca_nt import validate_point


def check(**values):
    return validate_point(values, lambda status, **detail: dict(status=status, **detail))


class NorthwestTerritoriesPointsTest(unittest.TestCase):
    def test_community_keeps_publisher_road_and_identifier(self):
        result = check(city="Detah", address_line1="12 DETTAH", state_code="NT", postcode="X0E 0A0")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["evidence"][0]["record_id"], "589842f6a05b08373e9a")
        self.assertEqual(result["checked"], {"city", "state_code", "address_line1"})
        self.assertEqual(result["evidence"][0]["snapshot"], "2021-01-15")
        self.assertIsNone(check(municipality="Yellowknife", address_line1="12 DETTAH"))

    def test_current_community_name_uses_explicit_territorial_cross_reference(self):
        point = check(city="Dettah", municipality="Detah", address_line1="12 DETTAH")
        self.assertEqual(point["candidate_count"], 1)
        self.assertEqual([r["source_id"] for r in point["evidence"]],
                         ["ca-statcan-oda-nt", "nwt-official-community-names"])
        self.assertIsNone(check(city="Dettah", municipality="Yellowknife", address_line1="12 DETTAH"))

    def test_units_at_one_civic_address_stay_distinct(self):
        fields = {"municipality": "Yellowknife", "road": "Moyle Dr", "house_number": "111"}
        self.assertEqual(check(**fields)["candidate_count"], 64)
        self.assertEqual(check(**fields)["status"], "ambiguous")
        unit = check(**fields, unit="101")
        self.assertEqual(unit["status"], "matched")
        self.assertEqual(unit["candidate_count"], 1)
        self.assertEqual(unit["evidence"][0]["record_id"], "f29f42aeaf3bfc6cc5d4")
        self.assertIn("unit", unit["checked"])
        self.assertEqual(check(**fields, unit="invalid")["status"], "not_observed")
        correct_line = check(**fields, address_line1="101 111 Moyle Dr", unit="101")
        self.assertEqual(correct_line["status"], "matched")
        altered_line = check(**fields, address_line1="101 111 Moyle Dr", unit="102")
        self.assertEqual(altered_line["candidate_count"], 0)

    def test_single_published_suite_and_real_published_parent(self):
        from addressing.address_ai import process_request
        def call(line):
            request = {"operation": "validate", "country": "CA", "components": {"line1": line, "city": "Yellowknife"}}
            return process_request(request)["result"]
        base = call("5016 50 AVE")["address1_decision"]
        self.assertEqual((base["status"], base["level"], base["candidate_count"]), ("partial", "street", 1))
        suite = call("A 5016 50 AVE")
        self.assertEqual(suite["address1_decision"]["level"], "unit")
        self.assertEqual(suite["evidence"][0]["record_id"], "8dfbbec322a064dcbdf7")
        parent = call("100 IDAA RD")
        self.assertEqual(parent["address1_decision"]["level"], "premise")
        self.assertEqual(parent["evidence"][0]["record_id"], "3366c818fd759d07ee20")

    def test_strict_scope_disallows_post_boxes_and_wrong_component(self):
        fields = {"city": "Detah", "address_line1": "12 DETTAH"}
        self.assertIsNone(check(**fields, state="Ontario"))
        self.assertIsNone(check(**fields, po_box="12"))
        self.assertIsNone(check(city="Detah", house_number="12"))
        self.assertIsNone(check(postal_city="Detah", address_line1="12 DETTAH"))
        self.assertEqual(check(**fields, house_number="13")["status"], "conflict")
        self.assertIsNone(check(city="Iqaluit", address_line1="12 DETTAH"))
