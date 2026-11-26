import unittest

from addressing.address1_profiles import address1_profile


class Address1ProfileTests(unittest.TestCase):
    def test_country_selected_explicitly_and_pr_override_only_with_consistent_state(self):
        for values in ({"state": "Puerto Rico"}, {"state": "Puerto Rico", "state_code": "PR"}):
            profile = address1_profile("US", values)
            self.assertEqual(profile["jurisdiction"], "PR")
            self.assertIn("urbanization", profile["disambiguation_fields"])
        for values in ({"postcode": "00901"}, {"state": "Puerto Rico", "state_code": "DC"}):
            self.assertEqual(address1_profile("US", values)["jurisdiction"], "US")
        self.assertEqual(address1_profile("PR", {})["jurisdiction"], "PR")

    def test_country_specific_postal_destinations(self):
        examples = [
            ("CA", "Case postale 44"), ("CA", "RR 2 STN MAIN"),
            ("CA", "Poste restante"), ("US", "RR 3 BOX 14"), ("PR", "HC 4 BOX 45"),
            ("MX", "Apartado postal 36"), ("AU", "GPO Box 44"),
            ("AU", "Locked Bag 2"), ("NZ", "Private Bag 32"),
            ("VU", "P.M.B. 9052"), ("CK", "P.O. BOX 98"),
        ]
        for cc, line in examples:
            with self.subTest(cc=cc, line=line):
                result = address1_profile(cc, {"address_line1": line, "city": "Example"})
                self.assertEqual(result["address_kind"], "postal_delivery")
        self.assertEqual(address1_profile("US", {"address_line1": "PO Box Road"})["address_kind"], "unspecified")

    def test_mailing_and_separate_civic_components_can_coexist(self):
        for values in ({"road": "Bay Street", "house_number": "4", "po_box": "12"},
                       {"address_line1": "7 Pine St", "address_line2": "PO Box 23"},
                       {"address_line1": "PO Box 23", "address_line2": "7 Pine St"},
                       {"address_line1": "7 Pine St, PO Box 23"}):
            self.assertEqual(address1_profile("CA", values)["address_kind"], "mixed")
        self.assertEqual(address1_profile("CA", {"organization": "Example", "po_box": "2"})["address_kind"],
                         "postal_delivery")
        self.assertEqual(address1_profile("AU", {"road": "Box Road", "house_number": "10"})["address_kind"],
                         "physical")

    def test_locality_and_no_number_remain_unverified_descriptions(self):
        for number in ("S/N", "s / n.", "sin número"):
            self.assertEqual(address1_profile("MX", {"house_number": number})["address_kind"], "locality_description")
        self.assertEqual(address1_profile("MX", {"house_number": "15B"})["address_kind"], "physical")
        for cc in ("CK", "FJ", "VU"):
            response = address1_profile(cc, {"village": "Example", "island": "Island"})
            self.assertEqual(response["address_kind"], "locality_description")
            self.assertIn("island", response["disambiguation_fields"])
        self.assertEqual(address1_profile("NZ", {"unit": "4B"})["address_kind"], "unspecified")
