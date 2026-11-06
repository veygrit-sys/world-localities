"""All 18 West Asian source-preserving validators form one country-level baseline."""
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from addressing import validate_western_asia_country, western_asia_quality_inventory

CODES=["AE","AM","AZ","BH","CY","GE","IL","IQ","JO",
       "KW","LB","OM","PS","QA","SA","SY","TR","YE"]

class RegionalCoverage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory=western_asia_quality_inventory()

    def test_eighteen_country_profiles_and_archives(self):
        r=self.inventory
        self.assertEqual(r["m49_country_codes"],18)
        self.assertEqual(r["countries_with_saved_gazetteer"],18)
        self.assertEqual(r["countries_with_native_and_english_address_profiles"],18)
        self.assertEqual(r["countries_with_format_validators"],18)
        self.assertEqual({x["country"] for x in r["countries"]},set(CODES))
        self.assertTrue(all(x["gazetteer_snapshot_rows"]>0 for x in r["countries"]))

    def test_country_specific_ownership_is_disjoint(self):
        groups={}
        for r in self.inventory["countries"]:
            groups.setdefault(r["validation_module"],[]).append(r["country"])
        self.assertEqual({k:len(v) for k,v in groups.items()},
                         {"first_nine":9,"caucasus_levant":5,"last_four":4})

    def test_no_fictitious_national_completeness_or_deliverability(self):
        self.assertEqual(self.inventory["official_postal_registers_verified_countrywide"],0)
        self.assertEqual(self.inventory["countries_with_delivery_coverage_verified"],0)
        self.assertTrue(all(not r["national_completeness_verified"] for r in
                            self.inventory["countries"]))
        self.assertTrue(all(not r["deliverability_verified"] for r in
                            self.inventory["countries"]))

    def test_valid_syntax_examples_per_country(self):
        examples={
            "AE":None,"AM":"0002","AZ":"AZ1000","BH":"317",
            "CY":"2008","GE":"0160","IL":"9414219","IQ":"54001",
            "JO":"11118","KW":"54404","LB":None,"OM":"133",
            "PS":"P6100154","QA":None,"SA":"13337","SY":None,
            "TR":"06101","YE":None,
        }
        for cc in CODES:
            with self.subTest(country=cc):
                kwargs={"locality":"Example"} if cc in ("LB","SY","YE") else {}
                result=validate_western_asia_country(cc,examples[cc],**kwargs)
                self.assertEqual(result["country"],cc)
                self.assertIn(result["status"],
                              {"format_only","format_unverified","incomplete"})
                self.assertFalse(result["checks"]["official_postal_assignment_verified"])
                self.assertFalse(result["checks"]["carrier_deliverability_verified"])

    def test_no_postcodes_fabricated_for_syria_yemen_lebanon(self):
        for cc in ("LB","SY","YE"):
            r=validate_western_asia_country(cc,None,locality="Example")
            self.assertNotIn("postcode",r["normalized"])
            self.assertEqual(validate_western_asia_country(cc,"00000")["status"],
                             "invalid_format")

    def test_cyprus_inbound_and_azerbaijan_prefix(self):
        cy=validate_western_asia_country("CY","2008",direction="inbound")
        self.assertEqual(cy["normalized"]["postcode"],"CY-2008")
        az=validate_western_asia_country("AZ","az1000")
        self.assertEqual(az["normalized"]["postcode"],"AZ1000")

    def test_unrecognized_country_or_unsupported_extra_option_rejected(self):
        with self.assertRaises(ValueError):
            validate_western_asia_country("XX","12345")
        with self.assertRaises(ValueError):
            validate_western_asia_country("AM","0002",makani="123")
        with self.assertRaises(TypeError):
            validate_western_asia_country(None)

    def test_syria_humanitarian_pcode_not_postcode(self):
        r=validate_western_asia_country("SY",None,locality="Homs",
                                        humanitarian_pcode="SY0400")
        self.assertIn("humanitarian_pcode_not_a_postcode",r["warnings"])
        self.assertNotIn("postcode",r["normalized"])


if __name__=="__main__":unittest.main()
