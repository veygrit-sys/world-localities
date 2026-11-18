from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from addressing.china_reference import REFERENCE, load_statistical_table
from addressing.china_subdivisions import subdivision_catalog
from addressing.china_validation import _load_reference, validate_china_address


class ChinaValidationTests(unittest.TestCase):
    def test_snapshot_pins_and_explicit_parent_fields_are_consistent(self):
        tables, receipts = _load_reference()
        self.assertEqual([len(tables[key]) for key in ("province", "city", "area")], [31, 342, 2978])
        for city in tables["city"].values():
            self.assertIn(city["provinceCode"], tables["province"])
        for area in tables["area"].values():
            self.assertEqual(tables["city"][area["cityCode"]]["provinceCode"], area["provinceCode"])
        for receipt in receipts.values():
            self.assertEqual(receipt["source_date"], "2023-06-30")
            self.assertIn(receipt["upstream_commit"], receipt["url"])

    def test_same_size_modified_source_is_rejected(self):
        with TemporaryDirectory() as path:
            tables = Path(path) / "tables"
            tables.mkdir()
            raw = (REFERENCE / "tables" / "provinces.json").read_bytes()
            (tables / "provinces.json").write_bytes(raw.replace(b'"11"', b'"99"', 1))
            # Bypass the process cache to simulate first use of a damaged checkout.
            with patch("addressing.china_reference.REFERENCE", Path(path)):
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    load_statistical_table.__wrapped__("province")

    def test_same_name_preserves_both_candidates_until_parent_is_provided(self):
        result = validate_china_address({"district": "朝阳区"})["administrative"]
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual([r["area"]["code"] for r in result["candidates"]], ["110105", "220104"])
        result = validate_china_address({"province": "吉林省", "city_district": "朝阳区"})
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["administrative"]["candidates"][0]["city"]["name"], "长春市")

    def test_municipality_city_style_does_not_fabricate_a_city_row(self):
        result = validate_china_address({"city": "北京市"})["administrative"]
        self.assertEqual(result["level"], "province")
        self.assertEqual(result["candidates"], [{"province": {"code": "11", "name": "北京市"}}])
        result = validate_china_address({"city": "北京市", "county": "110105"})
        chain = result["administrative"]["candidates"][0]
        self.assertEqual(chain["city"]["name"], "市辖区")
        self.assertEqual(result["sources"]["area"]["source_id"], "CN-statistical-areas")

    def test_all_supplied_parents_must_agree(self):
        for values in [
            {"state": "河北省", "city": "北京市"},
            {"state": "北京市", "city": "长春市", "city_district": "110105"},
            {"city": "长春市", "district": "110105"},
            {"county": "110105", "city_district": "220104"},
        ]:
            with self.subTest(values=values):
                self.assertEqual(validate_china_address(values)["status"], "no_match")

    def test_province_code_is_an_independent_required_parent_constraint(self):
        for code in ["31", "CN-SH", "SH", "cnsh"]:
            with self.subTest(code=code):
                values = {"state": "北京市", "state_code": code, "district": "110105"}
                self.assertEqual(validate_china_address(values)["status"], "no_match")
        for code in ["11", "CN-BJ", "bj", "cnBj"]:
            for components in [{}, {"province": "北京市", "road": "示例路"}]:
                result = validate_china_address({"state_code": code, **components})
                self.assertEqual(result["status"], "matched")
                self.assertEqual(result["state_code"]["statistical_code"], "11")
                self.assertNotIn("state_code", result["unchecked_fields"])
                self.assertEqual(result["administrative"]["candidates"][0]["province"]["name"], "北京市")
                if "road" in components:
                    self.assertIn("road", result["unchecked_fields"])
                    self.assertEqual(result["status_scope"], "administrative_snapshot_and_postcode_syntax_only")
                    self.assertFalse(result["checks"]["street_verified"])

    def test_each_alphabetic_code_joins_one_exact_chinese_province_label(self):
        catalog = subdivision_catalog()["subdivisions"]
        codes = set()
        for key, row in catalog.items():
            result = validate_china_address({"state_code": key})["state_code"]
            self.assertEqual(result["matched_label"], row["zh"])
            self.assertEqual(result["subdivision_id"], key)
            self.assertIn("common/subdivisions/zh.xml", result["reference"])
            codes.add(result["statistical_code"])
        self.assertEqual(codes, set(_load_reference()[0]["province"]))

    def test_unsupported_state_code_abstains_and_preserves_the_input(self):
        for code in ["CN-99", "CN-HK", "11X", "99", "ſh"]:
            for fields in [{}, {"city": "北京市", "postcode": "100000"}]:
                values = {"state_code": code, **fields}
                result = validate_china_address(values)
                self.assertEqual(result["status"], "unsupported_state_code")
                self.assertEqual(result["state_code"], {"value": code, "status": "unsupported"})
                self.assertEqual(result["input"], values)
                self.assertIn("state_code", result["unchecked_fields"])
                self.assertEqual(result["administrative"]["candidates"], [])

    def test_table_does_not_infer_from_prefix_or_translate_input(self):
        for values in [{"city_district": "11010"}, {"state": "Beijing"}, {"city": "石家庄"}]:
            self.assertEqual(validate_china_address(values)["status"], "no_match")

    def test_postcode_syntax_preserves_zero_and_rejects_fullwidth_or_spaced_codes(self):
        result = validate_china_address({"postal_code": "050024"})
        self.assertEqual(result["postcode"]["value"], "050024")
        self.assertEqual(result["status"], "format_only")
        self.assertFalse(result["checks"]["postal_assignment_verified"])
        for code in ["０５００２４", "050 024", "50024", "050024A"]:
            result = validate_china_address({"city": "北京市", "postcode": code})
            self.assertEqual(result["status"], "invalid_format")
            self.assertEqual(result["administrative"]["status"], "matched")

    def test_unsupported_fields_retained_and_reported(self):
        supplied = {"street": "东华门街道", "neighbourhood": "朝阳区", "unit": "008", "external_id": "X"}
        result = validate_china_address(supplied)
        self.assertEqual(result["status"], "insufficient_input")
        self.assertEqual(result["unchecked_fields"], ["external_id", "neighbourhood", "road", "unit"])
        self.assertEqual(result["input"], supplied)
        self.assertEqual(result["postcode"]["status"], "not_supplied")
        self.assertFalse(result["checks"]["deliverability_verified"])

    def test_mutating_result_does_not_alter_the_snapshot_or_other_queries(self):
        query = {"city": " 北京市 "}
        result = validate_china_address(query)
        query["city"] = "other"
        self.assertEqual(result["input"]["city"], " 北京市 ")
        result["administrative"]["candidates"][0]["province"]["name"] = "other"
        result["sources"]["province"]["sha256"] = ""
        second = validate_china_address({"city": "北京市"})
        self.assertEqual(second["status"], "matched")
        self.assertEqual(len(second["sources"]["province"]["sha256"]), 64)

    def test_out_of_scope_country_and_conflicting_aliases_are_rejected(self):
        for country in ("HK", "TW", "MO", "US"):
            with self.assertRaises(ValueError):
                validate_china_address({"country_code": country})
        with self.assertRaisesRegex(ValueError, "conflicting"):
            validate_china_address({"district": "110105", "city_district": "220104"})
        with self.assertRaises(TypeError):
            validate_china_address({"city": {"zh": "北京市"}})
