"""Validate first-wave unresolved source records without guessing parents."""
import unittest
from triage_unresolved import triage


class SourceUnresolvedReview(unittest.TestCase):
    def test_kenya_parent_cases(self):
        result = triage("KE")
        self.assertTrue(result["source_present"])
        self.assertEqual(result["unresolved_parent_count"], 69)
        self.assertEqual(result["localities_without_adm1_count"], 54)
        self.assertEqual(result["auto_reparented_records"], 0)
        self.assertTrue(all(x["parent_id"] is None and x["official_reconciliation_status"] == "not_checked"
                            for x in result["cases"]))
        print("KE first unresolved cases:", [(x["id"], x["name"], x["relation"],
                                               x["adm_codes"], x["state_id"])
                                              for x in result["cases"][:8]])

    def test_ghana_parent_cases(self):
        result = triage("GH")
        self.assertTrue(result["source_present"])
        self.assertEqual(result["unresolved_parent_count"], 11)
        self.assertEqual(result["localities_without_adm1_count"], 39)
        self.assertEqual(result["auto_reparented_records"], 0)
        print("GH first unresolved cases:", [(x["id"], x["name"], x["relation"],
                                               x["adm_codes"], x["state_id"])
                                              for x in result["cases"][:8]])

    def test_south_africa_no_parent_gaps(self):
        result = triage("ZA")
        self.assertEqual(result["unresolved_parent_count"], 0)

    def test_nigeria_snapshot_missing_is_not_zero_errors(self):
        result = triage("NG")
        self.assertFalse(result["source_present"])
        self.assertEqual(result["reason"], "original_archive_not_migrated")


if __name__ == "__main__":
    unittest.main()
