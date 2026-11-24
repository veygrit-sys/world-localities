import csv
import gzip
from pathlib import Path
import tempfile
import unittest

from addressing.address_ai import AddressInputError, process_request
from localities.open_reference import tw_roads
from localities.postal_picker import build_index


class TaiwanRoadInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        cls.index = Path(folder.name, "picker.sqlite")
        build_index(cls.index, ["TW"])

    def suggest(self, code, **options):
        return process_request({"operation": "suggest", "country": "TW", "postcode": code, **options},
                               index_path=self.index)["result"]

    def validate(self, **components):
        return process_request({"operation": "validate", "country": "TW", "components": components},
                               index_path=self.index)["result"]

    def test_all_raw_rows_and_duplicate_evidence_are_retained(self):
        areas = tw_roads.areas()
        links = [n for a in areas for numbers in a.roads.values() for n in numbers]
        self.assertEqual(sorted(links), list(range(1, 35799)))
        self.assertEqual(sum(len(a.roads) for a in areas), 35789)
        self.assertEqual((len(areas), len({a.prefix for a in areas})), (371, 368))
        self.assertEqual(len([a for a in areas if a.roads]), 361)
        self.assertEqual(len({a.prefix for a in areas if a.roads}), 358)
        r = self.validate(city="臺北市", city_district="大同區", road="延平北路")
        self.assertEqual(r["matched_scope"], "published_district_street")
        self.assertEqual({e["source_row"] for e in r["evidence"] if e["source_id"] == tw_roads.ROAD_ID},
                         {31267, 31268})

    def test_scoped_suggestions_shared_prefix_and_bound_tokens(self):
        for code in ("300", "300999"):
            root = self.suggest(code)
            self.assertEqual((root["lookup_prefix"], root["postcode"], root["postcode_verified"]), ("300", code, False))
            city, = root["options"]
            self.assertEqual(city["label"], "新竹市")
            districts = self.suggest(code, path=[city["id"]])["options"]
            self.assertEqual({d["label"] for d in districts}, {"北區", "東區", "香山區"})
            path = [city["id"], next(d["id"] for d in districts if d["label"] == "東區")]
            road = next(o for o in self.suggest(code, path=path, query="力行一")["options"] if o["label"] == "力行一路")
            self.assertFalse(road["has_children"])
            self.assertEqual(road["postcode"], code)
            self.assertEqual(self.suggest(code, path=path + [road["id"]])["status"], "leaf")
            with self.assertRaises(AddressInputError):
                self.suggest("300001", path=path)
        self.assertEqual(self.suggest("999999")["options"], [])

    def test_verified_fields_exclude_suffix_house_and_unit(self):
        for code in ("100", "100777"):
            got = self.validate(postcode=code, city="臺北市", city_district="中正區", road="中山南路",
                                house_number="999999", unit="A")
            self.assertEqual(got["matched_scope"], "published_district_street")
            self.assertEqual(set(got["verified_fields"]), {"city", "city_district", "road"})
            self.assertEqual(set(got["unverified_fields"]), {"postcode", "house_number", "unit"})
            self.assertEqual({e["source_id"] for e in got["evidence"]}, {tw_roads.POST_ID, tw_roads.ROAD_ID})
            self.assertFalse(got["deliverability_verified"])
        self.assertNotIn("road", self.validate(postcode="300999", city="新竹市", city_district="北區",
                                              road="力行一路")["verified_fields"])
        for alias in ("district", "ward", "neighbourhood"):
            wrong = self.validate(postcode="300999", city="新竹市", road="力行一路", **{alias: "北區"})
            self.assertNotIn("road", wrong["verified_fields"])
            correct = self.validate(postcode="300999", city="新竹市", road="力行一路", **{alias: "東區"})
            self.assertIn("road", correct["verified_fields"])
            self.assertNotIn("neighbourhood", correct["verified_fields"])
        self.assertEqual(self.validate(postcode="300")["status"], "ambiguous")
        self.assertEqual(self.validate(postcode="1000")["status"], "invalid_format")
        self.assertEqual(self.validate(road="中山南路")["status"], "insufficient_input")
        self.assertEqual(self.validate(postcode="999999", city="臺北市", city_district="中正區",
                                       road="中山南路")["status"], "not_observed")

    def test_legacy_five_digits_are_hinted_and_never_upgraded(self):
        path = []
        for label in ("新竹市", "東區", "力行一路"):
            page = self.suggest("30012", path=path, query=label)
            self.assertEqual(page["postcode"], "30012")
            self.assertEqual(page["lookup_prefix"], "300")
            self.assertEqual(page["postcode_format"], "legacy_3_plus_2")
            self.assertEqual(page["postcode_notice"], "confirm_current_six_digit_postcode")
            self.assertFalse(page["postcode_verified"])
            option = next(o for o in page["options"] if o["label"] == label)
            path.append(option["id"])
        for code in ("30011", "300012"):
            with self.assertRaises(AddressInputError):
                self.suggest(code, path=path)
        addresses = [dict(postcode="30012", city="新竹市", city_district="東區", road="力行一路"),
                     dict(postcode="99912", city="新竹市", city_district="東區", road="力行一路")]
        for address in addresses:
            result = self.validate(**address)
            self.assertEqual(result["postcode_format"], "legacy_3_plus_2")
            self.assertEqual(result["postcode_notice"], "confirm_current_six_digit_postcode")
            self.assertEqual(result["lookup_prefix"], address["postcode"][:3])
            self.assertFalse(result["postcode_verified"])
            self.assertFalse(result["deliverability_verified"])
            self.assertIn("postcode", result["unverified_fields"])
            self.assertEqual("road" in result["verified_fields"], address["postcode"] == "30012")
        self.assertNotIn("postcode_format", self.suggest("300012"))
        self.assertEqual(self.validate(postcode="3001A")["status"], "invalid_format")

    def test_published_source_row_from_each_road_district(self):
        with gzip.open(tw_roads.ROOT / "roads-115.csv.gz", "rt", encoding="utf-8-sig") as f:
            sample = {}
            for n, r in enumerate(csv.DictReader(f), 1):
                sample.setdefault(r["site_id"], (n, r))
        for n, row in sample.values():
            city = row["city"]
            district = row["site_id"].replace("　", "").removeprefix(city)
            result = self.validate(city=city, city_district=district, road=row["road"].strip())
            self.assertEqual(result["matched_scope"], "published_district_street", row)
            self.assertIn(f"{tw_roads.ROAD_ID}:{n}", [r["record_id"] for r in result["evidence"]])
