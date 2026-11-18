"""Fixed-source postal comparisons for Japan and Taiwan."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

from registries.official.query import validate_postal_address


ROOT = Path(__file__).resolve().parents[1]


class SourcePostalValidation(unittest.TestCase):
    def test_jp_updated_assignment_and_real_town_named_ichien(self):
        for code, fields in [
            ("313-0065", {"prefecture": "茨城県", "municipality": "常陸太田市", "town": "まいづる町"}),
            ("5220317", {"state": "滋賀県", "city": "犬上郡多賀町", "town": "一円"}),
            ("064-0941", {"prefecture": "ホッカイドウ", "town": "アサヒガオカ", "unit": "007"}),
        ]:
            with self.subTest(code=code):
                result = validate_postal_address("JP", code, fields)
                self.assertEqual(result["status"], "matched")
                self.assertTrue(result["complete_postcode_observed"])
                self.assertFalse(result["delivery_verified"])
                self.assertEqual(result["input_components"], fields)
                self.assertEqual(result["input_code"], code)
                self.assertEqual(result["sources"]["japanpost-postal-20261030"]["published_on"], "2026-10-30")
                self.assertEqual(result["unchecked_fields"], ["unit"] if "unit" in fields else [])
                self.assertEqual(result["candidates"][0]["source_code"], code.replace("-", ""))

    def test_jp_designated_city_ward_requires_the_same_registered_boundary(self):
        for fields in [
            {"city": "札幌市", "city_district": "中央区", "town": "旭ケ丘"},
            {"municipality": "札幌市中央区", "ward": "中央区"},
        ]:
            with self.subTest(fields=fields):
                result = validate_postal_address("JP", "0640941", fields)
                self.assertEqual(result["status"], "matched")
                evidence = result["candidates"][0]["ward_evidence"]
                self.assertEqual(evidence["category"], "designated_city_ward")
                self.assertEqual(evidence["source_id"], "jp-abr-snapshot")
                self.assertIn("#lg_code=011011", evidence["source_row"])
        for city, ward in [("札幌市中央区", "北区"), ("札幌", "市中央区")]:
            with self.subTest(city=city, ward=ward):
                result = validate_postal_address("JP", "0640941", {"city": city, "district": ward})
                self.assertEqual(result["status"], "no_match_in_source")

    def test_jp_tokyo_special_ward_and_unknown_subdivision_are_distinct(self):
        result = validate_postal_address("JP", "1000001", {"prefecture": "東京都", "ward": "千代田区"})
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["candidates"][0]["ward_evidence"]["category"], "special_ward")
        result = validate_postal_address("JP", "1000001", {"city": "東京市", "ward": "千代田区"})
        self.assertEqual(result["status"], "no_match_in_source")
        result = validate_postal_address("JP", "3130065", {"city": "常陸太田市", "ward": "中央区"})
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIn("city_district", result["candidates"][0]["unverified_fields"])

    def test_jp_missing_code_conflict_and_ambiguous_readings(self):
        result = validate_postal_address("JP", "0000000", {"town": "旭ケ丘"})
        self.assertEqual(result["status"], "postcode_not_observed")
        self.assertFalse(result["complete_postcode_observed"])
        result = validate_postal_address("JP", "0640941", {"prefecture": "東京都", "town": "旭ケ丘"})
        self.assertEqual(result["status"], "no_match_in_source")
        self.assertEqual(result["candidates"][0]["conflicting_fields"], ["prefecture"])
        result = validate_postal_address("JP", "6730012", {"municipality": "明石市", "town": "和坂"})
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["matching_rows"], 2)

    def test_jp_general_instruction_does_not_match_town(self):
        for code, town in [
            ("0600000", "以下に掲載がない場合"), ("1000301", "利島村一円"),
            ("4090142", "小菅村の次に１〜６６３番地がくる場合"), ("4090211", "小菅村の次に６６４番地以降がくる場合"),
            ("7660002", "琴平町の次に１〜４２６番地がくる場合（川東）"), ("7660001", "琴平町の次に４２７番地以降がくる場合（川西）"),
        ]:
            with self.subTest(code=code):
                result = validate_postal_address("JP", code, {"town": town})
                self.assertEqual(result["status"], "insufficient_evidence")
                self.assertEqual(result["matching_rows"], 0)
                self.assertIn("town", result["candidates"][0]["unverified_fields"])
                self.assertEqual(result["candidates"][0]["postal_instruction"]["ja"], town)
                self.assertNotIn("town", result["candidates"][0]["labels"])

    def test_jp_qualifier_requires_more_than_the_base_town(self):
        result = validate_postal_address("JP", "0600042", {"city": "札幌市中央区", "town": "大通西"})
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIn("大通西（１〜１９丁目）", result["candidates"][0]["labels"]["town"])
        self.assertIn("town", result["candidates"][0]["unverified_fields"])

    def test_jp_restricted_code_requires_organization(self):
        for code, organization, use in [("0608621", "株式会社　日本経済新聞社　札幌支社", "business"),
                                        ("0608703", "ＮＨＫ札幌拠点放送局", "po_box")]:
            fields = {"municipality": "札幌市中央区"}
            with self.subTest(code=code):
                result = validate_postal_address("JP", code, fields)
                self.assertEqual(result["status"], "insufficient_evidence")
                self.assertEqual(result["candidates"][0]["postal_use"], use)
                result = validate_postal_address("JP", code, {**fields, "organization": organization})
                self.assertEqual(result["status"], "matched")
                result = validate_postal_address("JP", code, {**fields, "organization": "別組織"})
                self.assertEqual(result["status"], "no_match_in_source")

    def test_tw_exact_bilingual_label_keeps_six_digit_result_at_prefix_scope(self):
        for area in ["新竹市北區", "North Dist., Hsinchu City"]:
            with self.subTest(area=area):
                result = validate_postal_address("TW", "300999", {"postal_area": area}, include_prefix=True)
                self.assertEqual(result["status"], "matched")
                self.assertEqual(result["match_scope"], "prefix")
                self.assertEqual((result["matching_rows"], result["postal_source_rows"]), (1, 3))
                self.assertFalse(result["complete_postcode_observed"])
                self.assertFalse(result["delivery_verified"])
                matched, = [row for row in result["candidates"] if row["status"] == "matched"]
                self.assertEqual((matched["source_code"], matched["source_row"]), ("300", "67"))
                self.assertEqual(result["sources"]["tw-chunghwa-names"]["published_on"], "2020-06-12")

    def test_tw_labels_reject_noncanonical_compatibility_letters(self):
        for label in ["Eaſt Dist., Hsinchu City", "Eaﬆ Dist., Hsinchu City"]:
            with self.subTest(label=label):
                result = validate_postal_address("TW", "300", {"postal_area": label}, include_prefix=True)
                self.assertEqual(result["status"], "no_match_in_source")

    def test_tw_structured_place_fields_resolve_a_shared_prefix(self):
        for fields, status, count in [
            ({"city": "新竹市"}, "ambiguous", 3),
            ({"city": "新竹市", "district": "北區"}, "matched", 1),
            ({"city_or_county": "Hsinchu City", "postal_locality": "North Dist."}, "matched", 1),
            ({"city": "臺北市", "district": "北區"}, "no_match_in_source", 0),
        ]:
            with self.subTest(fields=fields):
                result = validate_postal_address("TW", "300001", fields, include_prefix=True)
                self.assertEqual((result["status"], result["matching_rows"]), (status, count))
                self.assertFalse(result["complete_postcode_observed"])
        island = validate_postal_address("TW", "290", {"city": "Taipei City"}, include_prefix=True)
        self.assertEqual(island["status"], "insufficient_evidence")

    def test_tw_missing_insufficient_and_wrong_place_are_distinct(self):
        for code, fields, status in [
            ("300", {"postal_area": "臺北市中正區"}, "no_match_in_source"),
            ("000", {"postal_area": "臺北市中正區"}, "postcode_not_observed"),
            ("300", {"house_number": "007"}, "insufficient_evidence"),
            ("300", {}, "insufficient_evidence"),
            ("30000", {"postal_area": "新竹市北區"}, "invalid_format"),
        ]:
            with self.subTest(code=code, fields=fields):
                result = validate_postal_address("TW", code, fields, include_prefix=True)
                self.assertEqual(result["status"], status)
                self.assertFalse(result["complete_postcode_observed"])

    def test_invalid_code_and_conflicting_context(self):
        for code in ("０６４０９４１", "064--0941", "64-0941"):
            self.assertEqual(validate_postal_address("JP", code, {})["status"], "invalid_format")
        for fields in ({"city": "札幌市", "municipality": "明石市"}, {"country_code": "US"}, {"postcode": "9999999"}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                validate_postal_address("JP", "0640941", fields)
        with self.assertRaisesRegex(ValueError, "include-prefix"):
            validate_postal_address("TW", "100", {"postal_area": "臺北市中正區"})

    def test_cli_limit_does_not_hide_candidates_during_validation(self):
        run = subprocess.run([sys.executable, str(ROOT / "registries/official/query.py"),
                              "--country", "TW", "--postal-code", "300999", "--include-prefix",
                              "--components-json", '{"postal_area":"新竹市北區"}', "--limit", "0"],
                             check=True, text=True, capture_output=True)
        result = json.loads(run.stdout)
        self.assertTrue(result["rows_truncated"])
        self.assertEqual(result["candidates"], [])
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["matching_rows"], 1)
