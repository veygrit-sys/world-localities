"""Same-row Japan Post Latin labels through the public API."""

import unittest

from addressing.address_ai import process_request
from localities.open_reference import jp_post_roman


def validate(**components):
    return process_request({"operation": "validate", "country": "JP", "components": components})["result"]


class JapanPostRomanTests(unittest.TestCase):
    def test_mixed_scripts_provenance_and_identifier_scope(self):
        r = validate(postcode="150-0001", state="東京都", city="Shibuya Ku",
                     town="JINGUUMAE", house_number="12")
        self.assertEqual(r["matched_scope"], "postal_locality")
        self.assertEqual(set(r["verified_fields"]), {"postcode", "state", "city", "town"})
        self.assertEqual(r["unverified_fields"], ["house_number"])
        ref = r["evidence"][0]
        self.assertEqual(ref["record_id"], ref["roman_reference"]["native_record_id"])
        self.assertEqual(ref["roman_reference"]["source_row"], "40059")
        self.assertNotIn("ward_reference", ref)
        self.assertFalse(r["deliverability_verified"])

    def test_multiple_towns_share_a_postcode(self):
        for town in ["TSUCHIZAKIMINATO SOUZENMACHI", "TSUCHIZAKIMINATO FURUKAWAMACHI"]:
            r = validate(postcode="011-0951", city="Akita Shi", town=town)
            self.assertEqual(r["status"], "matched")
            self.assertEqual(r["evidence_count"], 1)
            self.assertIn("town", r["verified_fields"])
        # A town name given for the wrong postcode or in the city role is not verified.
        r = validate(postcode="150-0001", city="JINGUUMAE", town="TSUCHIZAKIMINATO SOUZENMACHI")
        self.assertEqual(r["verified_fields"], ["postcode"])

    def test_roman_postal_instruction_is_not_a_town(self):
        r = validate(postcode="060-0000", city="SAPPORO SHI CHUUOU KU", town="IKANIKEISAIGANAIBAAI")
        self.assertIn("city", r["verified_fields"])
        self.assertIn("town", r["unverified_fields"])
        self.assertIn("postal_qualifier_unverified", r["issues"])
        # Whole qualifier strings retain their postal meaning.
        r = validate(postcode="100-0005", town="MARUNOUCHI (TSUGINOBIRUONOZOKU)")
        self.assertNotIn("town", r["verified_fields"])

    def test_old_spelling_can_still_be_read_with_its_original_receipt(self):
        components = {"postcode": "150-0001", "city": "SHIBUYA KU", "town": "JINGUMAE"}
        r = process_request(dict(operation="translate", country="JP", source_language="ja-Latn",
                                 target_language="ja", components=components))["result"]
        self.assertEqual(r["components"]["town"], "神宮前")
        self.assertEqual(r["fields"]["town"]["provenance"]["source_as_of"], "2025-06")
        self.assertEqual(jp_post_roman.rows("1500"), [])
        # The published readings of 明石市和坂 cannot be reconciled by text alone.
        self.assertFalse(any(r.town_ja == "和坂" for r in jp_post_roman.rows("6730012")))
