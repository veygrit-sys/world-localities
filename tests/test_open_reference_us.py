import unittest

from localities.open_reference.us import get_record, lookup, lookup_ids
from localities.open_reference.us.verify_mar import verify_corridor


class DCMarReferenceTests(unittest.TestCase):
    def test_citywide_scope_is_pinned_against_count_and_ids(self):
        washington = lookup_ids("Washington")
        self.assertEqual(len(washington), 141189)
        self.assertEqual(len(set(washington)), len(washington))
        self.assertEqual(washington, lookup_ids("DC"))

    def test_independent_corridor_query_matches_published_points(self):
        self.assertEqual(verify_corridor(), 101)

    def test_exact_keys_refer_to_the_same_source_record(self):
        address = lookup(" 1600 Pennsylvania   Avenue NW ")
        self.assertEqual(len(address), 1)
        rid = "US-DC-MAR:293211"
        self.assertEqual(address[0]["record_id"], rid)
        self.assertEqual(address, lookup("1600 Pennsylvania Ave. NW"))
        self.assertEqual(address, lookup(rid.lower()))
        self.assertIn(rid, lookup_ids("20500"))
        self.assertNotIn(rid, lookup_ids("20004"))
        self.assertEqual(address[0]["evidence_kind"], "published_address_point")
        self.assertEqual(lookup("1350 PENNSYLVANIA AVENUE NW")[0]["postal_code"], "20004")

    def test_library_and_other_quadrants(self):
        for address, postal, rid in [
            ("901 G St. NW", "20001", "US-DC-MAR:239815"),
            ("1801 Hamlin St NE", "20018", "US-DC-MAR:286483"),
            ("900 Wesley Pl SW", "20024", "US-DC-MAR:295165"),
        ]:
            self.assertEqual(lookup_ids(address), (rid,))
            self.assertIn(rid, lookup_ids(postal))

    def test_partial_address_wrong_quadrant_and_unit_do_not_match_target(self):
        for text in ("", "1600", "1600 Pennsylvania Avenue NE", "1600 Pennsylvania Avenue NW Apt 1"):
            self.assertNotIn("US-DC-MAR:293211", lookup_ids(text))

    def test_results_are_independent(self):
        get_record("US-DC-MAR:293211")["postal_code"] = "00000"
        self.assertEqual(get_record("US-DC-MAR:293211")["postal_code"], "20500")


if __name__ == "__main__":
    unittest.main()
