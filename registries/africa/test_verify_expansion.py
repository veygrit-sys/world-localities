"""Regression coverage for Africa eight-priority-country administrative source layers."""
import unittest

from verify_expansion import verify

class SourceQuality(unittest.TestCase):
    def test_pinned_source_data_integrity_and_no_delivery_claim(self):
        r=verify()
        self.assertEqual(r["errors"],[],msg="; ".join(r["errors"]))
        self.assertFalse(r["deliverability_verified"])
        self.assertTrue(r["source_layers_are_distinct"])
        self.assertEqual(r["reports"]["RW"]["rows"],14823)
        self.assertEqual(r["reports"]["MA"]["rows"],1503)
        self.assertEqual(r["reports"]["DZ"]["wilayas"],69)
        self.assertEqual(r["reports"]["DZ"]["communes"],1541)
        self.assertEqual(r["reports"]["EG"]["rows"],365)
        self.assertEqual(r["reports"]["ZA-NG"]["rows"],1085)
        self.assertEqual(r["reports"]["KE-GH-gaps"]["original_missing_geonames_parent_ids"],80)
        self.assertEqual(r["reports"]["KE-GH-gaps"]["original_parent_ids_officially_repaired"],0)

    def test_missing_original_nigerian_archive_not_falsely_claimed(self):
        from pathlib import Path
        from verify_expansion import ROOT
        original=ROOT/"countries/NG/entities.csv.gz"
        self.assertFalse(original.exists(),
                         "If the historical NG source was restored, update migration evidence before claiming 57 areas")

if __name__=="__main__":
    unittest.main()
