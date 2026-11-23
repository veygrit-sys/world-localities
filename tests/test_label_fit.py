"""Regression tests for lossless label fitting, independent of a carrier API."""
import unittest

from addressing.label_fit import fit_label


def contract(**overrides):
    return {"id": "account-v4", "unit": "utf8_bytes", "line_limit": 35, "max_lines": 3,
            "field_limits": {"city": 32, "state": 32, "postcode": 10, "country_code": 2},
            **overrides}


def us(**overrides):
    return {"house_number": "0012B", "road": "Example Avenue", "unit": "003",
            "city": "Boston", "state": "Massachusetts", "postcode": "02108-0001", **overrides}


class LabelFitTests(unittest.TestCase):
    def review(self, r, issue):
        self.assertEqual(r["status"], "review_required", r)
        self.assertIn(issue, r["issues"])
        self.assertIsNone(r["fields"])
        self.assertFalse(r["deliverability_verified"])

    def test_ups_printed_city_limit_and_zip4(self):
        r = fit_label("US", us(city="A" * 15), "ups-us-shipto")
        self.assertEqual(r["fields"], {"country_code": "US", "city": "A" * 15, "state": "MA",
            "postcode": "021080001", "address_lines": ["0012B Example Avenue", "UNIT 003"]})
        self.assertEqual(set(r["edits"]), {"us_state_code", "zip4_separator_removed"})
        self.assertFalse(r["deliverability_verified"])
        self.review(fit_label("US", us(city="A" * 16), "ups-us-shipto"), "field_overflow:city")
        self.review(fit_label("US", us(postcode="1234"), "ups-us-shipto"), "invalid_us_postcode")
        self.review(fit_label("US", us(state="AA"), "ups-us-shipto"), "state_outside_profile")
        self.review(fit_label("JP", us(), "ups-us-shipto"), "country_outside_profile")

    def test_ups_ascii_and_names(self):
        self.review(fit_label("US", us(road="Café Road"), "ups-us-shipto"), "unsupported_charset")
        self.review(fit_label("US", us(organization="A" * 36), "ups-us-shipto"), "field_overflow:organization")
        self.review(fit_label("US", us(recipient="One", organization="Two", attention="Three"),
                              "ups-us-shipto"), "ambiguous_contact_fields")

    def test_suffix_only_if_needed_and_only_from_structured_road(self):
        v = {"house_number": "09", "road": "Avenue House Boulevard", "unit": "0002"}
        before = dict(v)
        r = fit_label("US", v, contract(line_limit=22))
        self.assertEqual(r["fields"]["address_lines"], ["09 Avenue House BLVD", "UNIT 0002"])
        self.assertEqual(r["edits"], ["us_street_suffix"])
        self.assertEqual(v, before)
        self.assertEqual(fit_label("US", v)["fields"]["address_lines"][0], "09 Avenue House Boulevard")
        r = fit_label("US", {"address_line1": "09 Avenue House Boulevard"}, contract(line_limit=22, max_lines=1))
        self.review(r, "address_lines_overflow")

    def test_utf8_boundary_and_nontruncation(self):
        jp = {"address_line1": "新町１", "address_line2": "１０１"}
        self.assertEqual(fit_label("JP", jp, contract(line_limit=9))["fields"]["address_lines"], list(jp.values()))
        self.review(fit_label("JP", jp, contract(line_limit=8)), "address_lines_overflow")
        self.assertEqual(fit_label("JP", jp, contract(line_limit=3, unit="codepoints"))["status"], "fits")
        self.review(fit_label("JP", jp | {"city": "春日部市"}, contract(field_limits={"city": 11,
                     "country_code": 2})), "field_overflow:city")

    def test_never_drops_or_rewrites_an_identifier(self):
        v = {"house_number": "01B", "road": "Loop Street", "house": "TOWER 2",
             "floor": "02", "unit": "02", "postcode": "00700"}
        r = fit_label("US", v, contract(line_limit=23, max_lines=2))
        self.assertEqual(r["fields"]["address_lines"], ["01B Loop Street TOWER 2", "FL 02 UNIT 02"])
        self.assertEqual(r["fields"]["postcode"], "00700")
        self.review(fit_label("US", v, contract(line_limit=10, max_lines=1)), "address_lines_overflow")
        self.review(fit_label("JP", {"address_line1": "丸の内", "railway_station": "東京駅"}), "unmapped_component")
        self.review(fit_label("US", us(address_line1="99 Other Road")), "ambiguous_street_components")

    def test_unrated_and_ambiguous_fields_fail_closed(self):
        self.review(fit_label("US", us(country="Canada")), "country_name_needs_review")
        self.review(fit_label("US", us(state_code="AK")), "conflicting_state_fields")
        self.review(fit_label("US", us(postal_city="Cambridge")), "conflicting_city_fields")
        self.review(fit_label("US", us(recipient="A"), contract()), "unsupported_field:recipient")
        self.review(fit_label("JP", {"address_line1": "例町"}, contract(required_fields=["city"])),
                    "missing_field:city")
        self.review(fit_label("DE", {"road": "Straße", "house_number": "4"}), "explicit_address_line_required")

    def test_inputs_and_profiles_fail_closed(self):
        for bad in (contract(unit="auto"), contract(max_lines=True), contract(id="ups-us-shipto"),
                    contract(required_fields=["invented"]), contract(typo=True), contract(countries=[])):
            self.review(fit_label("US", us(), bad), "invalid_profile")
        self.review(fit_label("US", us(), "nonexistent"), "unknown_profile")
        self.review(fit_label("US", us(street="Other Name")), "invalid_or_conflicting_components")
        for text in ("A\nB", "A\rB", "A\u202eB", "A\ud800B", "A\u2028B"):
            self.review(fit_label("US", us(city=text)), "unsafe_characters")
        self.review(fit_label("US", us(country_code="GB")), "country_mismatch")

    def test_japanese_explicit_fields_stay_separate(self):
        v = {"address_line1": "丸の内1-2-3", "address_line2": "サンプルビル105号室", "city": "千代田区",
             "state": "東京都", "postcode": "100-0005"}
        r = fit_label("JP", v, contract(countries=["JP"]))
        self.assertEqual(r["status"], "fits", r)
        self.assertEqual(r["fields"]["address_lines"], [v["address_line1"], v["address_line2"]])
        self.assertEqual(r["issues"], [])

    def test_ups_wraps_overflow_at_spaces_and_emits_an_address_fragment(self):
        line = "07 A Long Opaque Street Name With Several Words Unit 0002-B"
        v = {"address_line1": line, "city": "Boston", "state_code": "MA", "postcode": "02108",
             "recipient": "Test Contact", "organization": "Example Company"}
        r = fit_label("US", v, "ups-us-shipto")
        fragment = r["carrier_fields"]["ShipTo"]
        self.assertEqual(fragment["Name"], "Example Company")
        self.assertEqual(fragment["AttentionName"], "Test Contact")
        self.assertEqual(" ".join(fragment["Address"]["AddressLine"]), line)
        self.assertLessEqual(max(map(len, fragment["Address"]["AddressLine"])), 35)
        self.assertIn("wrapped_words", r["edits"])
        r = fit_label("US", v | {"address_line1": "A" * 36}, "ups-us-shipto")
        self.review(r, "address_lines_overflow")
        self.assertIsNone(r["carrier_fields"])

    def test_yamato_b2_columns_keep_building_and_home_number(self):
        v = {"state": "東京都", "city": "千代田区", "address_line1": "丸の内１－２－３",
             "address_line2": "架空ビル０７号室", "postcode": "100-0005", "recipient": "試験 宛名"}
        r = fit_label("JP", v, "yamato-jp-b2")
        self.assertEqual(r["carrier_fields"], {
            "お届け先郵便番号": "100-0005", "お届け先住所": "東京都千代田区丸の内1-2-3",
            "お届け先住所（アパートマンション名）": v["address_line2"], "お届け先名": v["recipient"]})
        self.assertEqual(r["edits"], ["halfwidth_ascii:town_street"])
        self.assertEqual(v["address_line1"], "丸の内１－２－３")
        self.assertFalse(r["deliverability_verified"])
        for key, value, issue in [
            ("address_line2", "見" * 17, "field_overflow:building"),
            ("address_line2", "見" * 16 + "1", "field_overflow:building"),
            ("city", "町" * 13, "field_overflow:city"),
            ("address_line1", "町" * 17, "field_overflow:town_street"),
            ("address_line1", "中央 区", "ambiguous_yamato_address"),
            ("address_line1", "東京都千代田区丸の内1", "ambiguous_yamato_address"),
            ("postcode", "01000", "invalid_jp_postcode"), ("state", "未知県", "invalid_jp_prefecture"),
            ("recipient", "試験①", "unsupported_charset"),
            ("recipient", "¥", "unsupported_charset"),
        ]:
            with self.subTest(key=key, value=value):
                result = fit_label("JP", v | {key: value}, "yamato-jp-b2")
                self.review(result, issue)
                self.assertIsNone(result["carrier_fields"])

    def test_yamato_uses_halfwidth_only_when_needed_and_can_verify_roundtrip(self):
        v = {"state": "北海道", "city": "札幌市", "address_line1": "架空町1",
             "address_line2": "見" * 15 + "０７", "postcode": "0010000"}
        r = fit_label("JP", v, "yamato-jp-b2")
        self.assertEqual(r["fields"]["address_lines"][1], "見" * 15 + "07")
        self.assertEqual(r["edits"], ["halfwidth_ascii:building"])
        r = fit_label("JP", v | {"address_line2": "見" * 14 + "０７"}, "yamato-jp-b2")
        self.assertEqual(r["fields"]["address_lines"][1], "見" * 14 + "０７")
        self.assertEqual(r["edits"], [])
        r = fit_label("JP", {"address_line1": "見本"}, contract(unit="shift_jis_bytes", line_limit=4))
        self.assertEqual(r["status"], "fits")

if __name__ == "__main__":
    unittest.main()
