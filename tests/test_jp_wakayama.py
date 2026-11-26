import csv
import io
import unittest
import zipfile

from addressing.address_ai import process_request
from localities.open_reference import jp_wakayama as wk
from localities.postal import ROOT


def validate(**fields):
    return process_request({"operation": "validate", "country": "JP", "components": fields})["result"]


class WakayamaAddressTests(unittest.TestCase):
    def test_addresses_published_by_the_prefecture(self):
        for name, line, number in (("今福第一", "今福２丁目３番４５号", "003:045"),
                                   ("今福第二", "今福三丁目6番22号", "006:022"),
                                   ("雄湊", "男野芝丁3番地", "000030000000000"),
                                   ("城北", "八番丁8番地", "000080000000000")):
            r = validate(city="和歌山市", address_line1=line, house=name)
            with self.subTest(name=name):
                self.assertEqual(r["address1_decision"]["level"], "premise")
                self.assertEqual(r["address1_decision"]["status"], "verified")
                self.assertEqual(r["address1_decision"]["candidate_count"], 1)
                self.assertTrue(r["evidence"][1]["record_id"].endswith(number))
                self.assertEqual(r["evidence"][0]["record_id"], "p29:" + name)

    def test_number_not_proven_by_frontage_or_parcel(self):
        r = validate(city="和歌山市", town="今福2丁目", block="3", house_number="44")
        self.assertEqual(r["matched_scope"], "published_street_block")
        self.assertIn("block", r["verified_fields"])
        self.assertNotIn("house_number", r["verified_fields"])
        parcel = validate(city="和歌山市", town="男野芝丁", lot="3番地")
        self.assertEqual(parcel["matched_scope"], "published_land_parcel")
        self.assertIn("lot", parcel["verified_fields"])
        self.assertNotEqual(parcel["address1_decision"]["level"], "premise")

    def test_unit_is_independent_and_ordinary_postcode_is_locality_evidence(self):
        r = validate(city="和歌山市", town="今福", house_number="2-3-45", unit="404", postcode="641-0044")
        self.assertEqual(r["address1_decision"]["level"], "premise")
        self.assertIn("unit", r["unverified_fields"])
        self.assertIn("postcode", r["verified_fields"])
        for fields in ({"address_line1": "今福2-3-45", "postcode": "100-0001"},
                       {"address_line1": "今福2-3-45", "town": "今福3丁目", "house_number": "6-22"},
                       {"address_line1": "今福2-3-45", "block": "7"},
                       {"address_line1": "今福2-3-45", "state": "東京都"}):
            self.assertEqual(validate(city="和歌山市", **fields)["status"], "conflict")
        outside = validate(city="海南市", address_line1="今福2-3-45")
        self.assertNotIn(outside["matched_scope"], {"published_street_block", "published_address_point"})

    def test_pinned_source_row_counts_and_postal_join(self):
        by_key, meta = wk._reference()
        counts = {kind: sum(len(ids) for (_, k, _), ids in by_key.items() if kind == k)
                  for kind in ("frontage", "parcel")}
        self.assertEqual(counts, {"frontage": 651, "parcel": 732})
        path = ROOT / "postal/sources/japanpost/20261030/utf_ken_all.zip"
        with zipfile.ZipFile(path) as archive:
            reader = csv.reader(io.TextIOWrapper(archive.open("utf_ken_all.csv"), encoding="utf-8-sig"))
            needed = {row for _, row in meta["town_postcodes"].values()}
            observed = {i: (r[0], r[2], r[7], r[8]) for i, r in enumerate(reader, 1) if i in needed}
        for town, (town_id, _) in wk.TOWNS.items():
            code, row = meta["town_postcodes"][town_id]
            self.assertEqual(observed[row], ("30201", code, "和歌山市", town.split("2丁目")[0].split("3丁目")[0]))
