"""No false-deliverability claims in African postcode format diagnostics."""
import unittest

from priority_address_codes import plausible, COUNTRIES

class AfricaAddressCodeSyntax(unittest.TestCase):
    def test_syntax_examples_are_not_verified_addresses(self):
        examples={
            "ZA":"0083", "NG":"100283", "KE":"00100",
            "GH":"GA-183-8164", "EG":"3759914", "MA":"53000", "DZ":"16027",
        }
        for country, code in examples.items():
            with self.subTest(country=country):
                result=plausible(country,code)
                self.assertEqual(result["status"],"syntax_plausible")
                self.assertIsNone(result["valid_address"])
                self.assertFalse(result["deliverability_verified"])
                self.assertTrue(result["provider_verification_required"])

    def test_new_nipost_code_preserves_11_characters(self):
        a=plausible("NG","FC 02 A09 DB 09")
        self.assertEqual(a["normalized"],"FC02A09DB09")
        self.assertEqual(a["format"],"NG-NIPOST-2026-11character")
        self.assertIsNone(a["valid_address"])

    def test_rwanda_not_assessed_not_rejected(self):
        self.assertEqual(plausible("RW","arbitrary")["status"],"unassessed")
        self.assertEqual(plausible("RW",None)["status"],"not_supplied")

    def test_invalid_syntax_does_not_imply_invalid_address(self):
        for country in COUNTRIES-{"RW"}:
            with self.subTest(country=country):
                r=plausible(country,"***")
                self.assertEqual(r["status"],"syntax_not_recognized")
                self.assertIsNone(r["valid_address"])
                self.assertFalse(r["deliverability_verified"])

    def test_country_names_are_not_inferred(self):
        with self.assertRaises(ValueError):
            plausible("XX","12345")

    def test_egypt_uses_explicit_upu_seven_digit_reference(self):
        self.assertEqual(plausible("EG","3759914")["status"],"syntax_plausible")
        self.assertEqual(plausible("EG","37599")["status"],"syntax_not_recognized")

if __name__=="__main__":
    unittest.main()
