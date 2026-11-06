"""Two Georgian regional names repaired as search aliases, not as verified IDs."""
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import western_asia_caucasus_levant_join as join

class GeorgiaAdminNames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=join.load_sources()
        cls.ge=join.country_report("GE",dataset=cls.data)

    def test_all_12_official_statistical_labels_propose_unique_candidates(self):
        self.assertEqual(self.ge["official_admin_names"],12)
        self.assertEqual(self.ge["admin_unique_candidates_unreviewed"],12)
        self.assertEqual(self.ge["admin_names_unmatched"],0)
        self.assertEqual(self.ge["geonames_adm1_rows"],12)

    def test_samegrelo_and_samtskhe_variants_keep_unverified(self):
        names=("Samegrelo-Zemo Svaneti","Samtskhe-Javaxeti")
        for name in names:
            candidates=[r for r in self.ge["government_admin_records"]
                        if r["source_name"]==name]
            self.assertEqual(len(candidates),1)
            self.assertEqual(candidates[0]["status"],"unique_candidate")
            self.assertFalse(candidates[0]["government_identity_verified"])
            self.assertFalse(candidates[0]["postal_assignment_verified"])
        self.assertEqual(self.ge["approved_admin_geonames_identity_links"],0)

    def test_georgian_native_name_and_english_remain_separate(self):
        from addressing import WesternAsiaRegistry
        r=WesternAsiaRegistry().get("GE")
        self.assertEqual(r["native_languages"],["ka-Geor"])
        self.assertEqual(r["native_scripts"]["ka-Geor"],"Geor")
        self.assertEqual(self.ge["approved_postal_geonames_identity_links"],0)

if __name__=="__main__": unittest.main()
