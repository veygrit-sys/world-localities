import unittest

from localities.open_reference.regional_offices import validate_office


def check(country, **values):
    def result(status, **details):
        return {"status": status, **details}
    return validate_office(country, values, result)


class RegionalOfficeTest(unittest.TestCase):
    def test_named_office_with_separate_street_and_number(self):
        result = check("CA", city="Ottawa", organization="Australian High Commission",
                       house_number="50", road="O'Connor Street", unit="1301", postcode="K1P 6L2")
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["scope"], "published_office_address")
        self.assertEqual(result["checked"], {"city", "organization", "house_number", "road", "unit", "postcode"})
        self.assertEqual(result["evidence"][0]["record_id"], "dfat-ottawa")
        self.assertEqual(result["evidence"][0]["license"], "CC-BY-4.0")

    def test_numberless_facility_requires_locality_and_official_name(self):
        fields = {"city": "Port Vila", "address_line1": "Winston Churchill Avenue"}
        self.assertIsNone(check("VU", **fields))
        self.assertIsNone(check("VU", **fields, organization="Local school"))
        self.assertIsNone(check("VU", address_line1=fields["address_line1"], organization="Australian High Commission"))
        result = check("VU", **fields, organization="Australian High Commission")
        self.assertEqual(result["checked"], {"city", "organization", "address_line1"})

    def test_locality_or_nearby_road_alone_cannot_identify_a_building(self):
        fields = {"city": "Port Vila", "organization": "Australian High Commission",
                  "road": "Winston Churchill Avenue"}
        self.assertIsNone(check("VU", **fields, house_number="123"))
        self.assertIsNone(check("VU", **dict(fields, city="Luganville")))
        self.assertIsNone(check("WS", **fields))
        self.assertIsNone(check("VU", **fields, po_box="111"))

    def test_unknown_unit_and_conflicting_official_postcodes(self):
        fields = {"city": "Mexico City", "organization": "Australian Embassy", "address_line1": "Ruben Dario 55"}
        for postcode in ["11560", "11580"]:
            with self.subTest(postcode=postcode):
                result = check("MX", **fields, postcode=postcode, unit="4B")
                self.assertNotIn("postcode", result["checked"])
                self.assertNotIn("unit", result["checked"])
                self.assertIn("office_sources_disagree_on_supplied_fields", result["issues"])

    def test_mismatched_component_cannot_be_confirmed(self):
        fields = {"city": "San Juan", "house": "Castillo San Cristobal", "address_line1": "501 Norzagaray Street"}
        self.assertEqual(check("PR", **fields, postcode="00901")["evidence"][0]["source_id"], "us-nps-physical-facilities")
        self.assertEqual(check("PR", **fields, house_number="503")["status"], "conflict")
        self.assertEqual(check("PR", **fields, postcode="00902")["candidate_count"], 0)
        self.assertIsNone(check("PR", city="San Juan", address_line1="501 Norzagaray Street"))

    def test_island_and_floor_are_independent_fields(self):
        fields = {"city": "Avarua", "house": "Philatelic Bureau Building", "road": "Takuvaine Rd"}
        result = check("CK", **fields, floor="1st floor", island="Rarotonga")
        self.assertIn("floor", result["checked"])
        self.assertEqual(check("CK", **fields, island="Aitutaki")["status"], "conflict")


if __name__ == "__main__":
    unittest.main()
