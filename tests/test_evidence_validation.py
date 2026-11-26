import sqlite3
import tempfile
import unittest
from pathlib import Path

from addressing.evidence_validation import validate_address


class EvidenceValidationTest(unittest.TestCase):
    point = {"house_number": "1600", "road": "Pennsylvania Ave. NW", "city": "Washington",
             "state": "District of Columbia", "postcode": "20500"}
    jp = {"postcode": "100-0005", "state": "東京都", "city": "千代田区"}
    office = "中國廣東省深圳市福田區金田路3088號中洲大廈28樓2805A室"

    def test_address_point_does_not_certify_unit_addressee_or_delivery(self):
        r = validate_address("US", dict(self.point, unit="999", recipient="TEST PERSON"))
        self.assertEqual((r["status"], r["matched_scope"]), ("partial", "published_address_point"))
        self.assertEqual(set(r["verified_fields"]), set(self.point))
        self.assertEqual(r["unverified_fields"], ["unit"])
        self.assertEqual(r["ignored_fields"], ["recipient"])
        self.assertFalse(r["deliverability_verified"])
        self.assertNotIn("TEST PERSON", str(r))
        self.assertEqual(r["evidence"][0]["record_id"], "US-DC-MAR:293211")

    def test_exact_decision_and_unverified_secondary_line(self):
        from addressing.address_ai import process_request
        fields = {"addressLine1": "1600 Pennsylvania Ave NW", "state": "DC", "postcode": "20500"}
        call = lambda c: process_request({"operation": "validate", "country": "US", "components": c})["result"]
        exact = call(fields)["address1_decision"]
        self.assertEqual((exact["status"], exact["level"], exact["candidate_count"]), ("verified", "premise", 1))
        extra = call(fields | {"line2": "Apt 4B"})["address1_decision"]
        self.assertEqual((extra["status"], extra["level"], extra["unverified_fields"]),
                         ("partial", "premise", ["address_line2"]))
        mixed = call(fields | {"line2": "PO BOX 9"})
        self.assertEqual(mixed["address1_profile"]["address_kind"], "mixed")
        self.assertNotIn(mixed["address1_decision"]["level"], ("premise", "unit"))
        self.assertNotIn("address_line1", mixed["address1_decision"]["verified_fields"])
        self.assertFalse(mixed["deliverability_verified"])

    def test_us_puerto_rico_routes_to_territory_reference(self):
        fields = {"state_code": "PR", "city": "San Juan", "house": "Castillo San Cristobal",
                  "address_line1": "501 Norzagaray Street"}
        result = validate_address("US", fields)
        self.assertEqual(result["country"], "US")
        self.assertEqual(result["address1_profile"]["jurisdiction"], "PR")
        self.assertEqual((result["address1_decision"]["status"], result["evidence"][0]["record_id"]),
                         ("verified", "nps-san-juan"))
        self.assertEqual(validate_address("US", fields | {"state_code": "CA"})["address1_decision"]["level"], "none")

    def test_wallet_freeform_facility_name_requires_a_match_on_the_same_record(self):
        for country, fields in (
            ("AU", {"city": "Barton", "state": "ACT", "postcode": "0221",
                    "line1": "John McEwen Crescent", "line2": "RG Casey Building"}),
            ("VU", {"city": "Port Vila", "line1": "Winston Churchill Avenue", "line2": "Australian High Commission"}),
            ("JP", {"postcode": "100-8919", "state": "東京都", "city": "千代田区",
                    "line1": "霞が関2丁目2-1", "line2": "外務省"}),
        ):
            with self.subTest(country=country):
                result = validate_address(country, fields)
                self.assertEqual(result["address1_decision"]["status"], "verified")
                self.assertIn("address_line2", result["verified_fields"])
                extra = validate_address(country, fields | {"line2": fields["line2"] + " Apt 4B"})
                self.assertNotEqual(extra["address1_decision"]["status"], "verified")

    def test_point_contradictions_block_and_postal_extension_is_not_verified(self):
        for bad in ({"postcode": "20004"}, {"city": "Baltimore"}, {"state_code": "CA"},
                    {"address_line1": "901 G St. NW"}):
            with self.subTest(bad=bad):
                r = validate_address("US", self.point | bad)
                self.assertEqual(r["status"], "conflict")
                self.assertTrue(r["blocking_conflict"])
        plus = validate_address("US", self.point | {"postcode": "20500-1234"})
        self.assertIn("postcode", plus["unverified_fields"])
        self.assertIn("zip_plus_four_unverified", plus["issues"])

    def test_concatenation_cannot_verify_wrong_component_roles(self):
        r = validate_address("US", self.point | {"house_number": "1600 Pennsylvania", "road": "Ave NW"})
        self.assertEqual(r["status"], "conflict")
        self.assertNotIn("road", r["verified_fields"])

    def test_us_point_requires_dc_context_and_an_actual_street(self):
        for components in ({"address_line1": "1600 Pennsylvania Ave NW"},
                           self.point | {"state": "CA", "postcode": "90210"},
                           {"address_line1": "Washington", "state": "DC"},
                           {"address_line1": "20500", "postcode": "20500", "state": "DC"}):
            r = validate_address("US", components)
            self.assertIsNone(r["matched_scope"])
            self.assertFalse(r["blocking_conflict"])

    def test_jp_scoped_native_match_and_building_exclusion(self):
        base = validate_address("jp", self.jp)
        self.assertEqual(base["status"], "matched")
        self.assertEqual(base["matched_scope"], "postal_locality")
        self.assertEqual(base["evidence"][0]["source_id"], "japanpost-postal-20261030")
        r = validate_address("JP", self.jp | {"town": "丸の内", "unit": "123"})
        self.assertEqual(r["status"], "partial")
        self.assertEqual(set(r["unverified_fields"]), {"unit", "town"})
        self.assertIn("postal_qualifier_unverified", r["issues"])
        self.assertFalse(r["deliverability_verified"])
        self.assertEqual(validate_address("JP", self.jp | {"city": "札幌市"})["status"], "conflict")
        self.assertEqual(validate_address("JP", self.jp | {"city": "Chiyoda-ku"})["status"], "partial")

    def test_jp_width_conversion_is_lossless_and_does_not_fix_misplaced_digits(self):
        request = self.jp | {"postcode": "１００－０００５"}
        r = validate_address("JP", request)
        self.assertEqual(r["status"], "matched")
        self.assertEqual(request["postcode"], "１００－０００５")
        for malformed in ("１０００－００５", "１⁰０－０００５", "１００－－０００５", "１００－００５"):
            self.assertEqual(validate_address("JP", self.jp | {"postcode": malformed})["status"], "invalid_format")
        self.assertEqual(validate_address("US", {"postcode": "２０５００"})["status"], "invalid_format")

    def test_designated_city_business_requires_ward(self):
        office = {"state": "神奈川県", "city": "横浜市", "postcode": "2308550", "organization": "鶴見 税務署",
                  "address_line1": "鶴見中央4丁目38-32"}
        self.assertNotEqual(validate_address("JP", office)["matched_scope"], "published_office_address")
        with_ward = validate_address("JP", office | {"city_district": "鶴見区"})
        self.assertEqual((with_ward["matched_scope"], with_ward["status"]), ("published_office_address", "matched"))
        self.assertIn("ODbL", with_ward["evidence"][0]["ward_reference"]["license"])

    def test_jp_exact_named_business_office_from_the_same_postal_row(self):
        office = {"postcode": "100-8919", "organization": "外務省", "state": "東京都",
                  "city": "千代田区", "neighbourhood": "霞が関", "house_number": "2丁目2-1"}
        r = validate_address("JP", office)
        self.assertEqual((r["status"], r["matched_scope"]), ("matched", "published_office_address"))
        self.assertEqual(set(r["verified_fields"]), set(office))
        self.assertTrue(r["evidence"][0]["record_id"].startswith("japanpost-business-20261030:"))
        line = {k: v for k, v in office.items() if k not in {"neighbourhood", "house_number"}}
        r = validate_address("JP", line | {"address_line1": "霞が関２丁目２－１"})
        self.assertEqual((r["matched_scope"], r["unverified_fields"]), ("published_office_address", []))
        explicit = office | {"address_line1": "霞が関２丁目２番１号", "house_number": "2丁目2番1号"}
        self.assertEqual(validate_address("JP", explicit)["address1_decision"]["status"], "verified")
        self.assertEqual(validate_address("JP", office | {"house_number": "2-2-1"})["status"], "conflict")
        for changed in ({"organization": "法務省"}, {"house_number": "2丁目2-9"},
                        {"address_line1": "霞が関2丁目2-8"}):
            self.assertEqual(validate_address("JP", office | changed)["status"], "conflict")
        for key in ("organization", "state", "city", "neighbourhood", "house_number"):
            r = validate_address("JP", {k: v for k, v in office.items() if k != key})
            self.assertNotEqual(r["matched_scope"], "published_office_address")
        extra = validate_address("JP", office | {"unit": "123"})
        self.assertEqual((extra["status"], extra["unverified_fields"]), ("partial", ["unit"]))
        self.assertFalse(extra["deliverability_verified"])

    def test_jp_po_box_and_incomplete_business_numbers_cannot_authorize_premise(self):
        for office in [
            {"postcode":"1028688", "organization":"東京都千代田区役所", "state":"東京都",
             "city":"千代田区", "address_line1":"九段南１丁目２－１（麹町郵便局私書箱第９号）"},
            {"postcode":"0608611", "organization":"札幌市役所", "state":"北海道",
             "city":"札幌市中央区", "address_line1":"北一条西２丁目"},
        ]:
            r = validate_address("JP", office)
            self.assertNotEqual(r["matched_scope"], "published_office_address")
            self.assertIn("address_line1", r["unverified_fields"])

    def test_jp_missing_town_evidence_not_a_contradiction(self):
        r = validate_address("JP", {"postcode": "0600000", "city": "札幌市", "city_district": "中央区",
                                    "town": "以下に掲載がない場合"})
        self.assertEqual(r["status"], "partial")
        self.assertEqual(r["unverified_fields"], ["town"])

    def test_cn_requires_published_address_and_agreeing_postcode(self):
        r = validate_address("CN", {"address_line1": self.office, "postcode": "518033"})
        self.assertEqual((r["status"], r["matched_scope"]), ("matched", "published_office_address"))
        self.assertEqual(set(r["verified_fields"]), {"address_line1", "postcode"})
        named = validate_address("CN", {"line1": self.office, "organization": "駐深圳聯絡處"})
        self.assertIn("organization", named["address1_decision"]["verified_fields"])
        self.assertEqual(validate_address("CN", {"line1": self.office, "organization": "別の事務所"})
                         ["address1_decision"]["status"], "conflict")
        self.assertEqual(validate_address("CN", {"address_line1": self.office, "postcode": "100009"})["status"], "conflict")
        self.assertEqual(validate_address("CN", {"address_line1": "駐深圳聯絡處", "postcode": "518033"})["status"], "not_observed")
        r = validate_address("CN", {"address_line1": self.office, "city": "北京"})
        self.assertEqual(r["status"], "partial")
        self.assertIn("city", r["unverified_fields"])

    def test_local_chinese_office_requires_same_published_city_and_name(self):
        base = dict(line1="金田路3088號中洲大廈28樓2805A室", line2="駐深圳聯絡處", city="深圳市",
                    state="廣東省", city_district="福田區", road="金田路", house_number="3088", unit="2805A")
        result = validate_address("CN", base)
        self.assertEqual((result["address1_decision"]["status"], result["address1_decision"]["level"]),
                         ("verified", "unit"))
        self.assertEqual(result["evidence"][0]["record_id"], "hk-cmab:guangdong/shenzhen-liaison-unit")
        english = validate_address("CN", base | {"road": "Jintian Road", "city": "Shenzhen"})
        self.assertEqual(english["address1_decision"]["level"], "unit")
        conflicting_state = validate_address("CN", {"line1": self.office, "state": "福建省"})
        self.assertEqual(conflicting_state["address1_decision"]["status"], "conflict")
        for changes in ({"city": "廣州市"}, {"line2": "未收錄設施"}, {"house_number": "3089"}, {"unit": "2810"}):
            self.assertNotEqual(validate_address("CN", base | changes)["address1_decision"]["status"], "verified")

    def test_postal_places_and_territory_scope(self):
        for country, postcode, city in (("FR", "75007", "Paris"), ("BL", "97133", "ST BARTHELEMY")):
            r = validate_address(country, {"postcode": postcode, "city": city, "house_number": "42"})
            self.assertEqual((r["status"], r["matched_scope"]), ("partial", "postal_locality"))
            self.assertEqual(r["unverified_fields"], ["house_number"])
        self.assertEqual(validate_address("FR", {"postcode": "97133", "city": "ST BARTHELEMY"})["status"], "not_observed")
        self.assertEqual(validate_address("FR", {"postcode": "75007", "city": "Ajaccio"})["status"], "conflict")
        self.assertEqual(validate_address("PM", {"postcode": "97500", "postal_city": "ST PIERRE ET MIQUELON"})["status"], "ambiguous")

    def test_country_aliases_invalid_format_and_uncovered(self):
        for components in ({"country_code": "JP"}, {"country": "日本"}, {"postcode": "20500", "zip": "20004"}):
            self.assertTrue(validate_address("US", components)["blocking_conflict"])
        self.assertEqual(validate_address("US", {"postcode": "٢٠٥٠٠"})["status"], "invalid_format")
        self.assertEqual(validate_address("CN", {"postcode": "1234"})["status"], "invalid_format")
        r = validate_address("ZZ", {"postcode": "12345"})
        self.assertEqual(r["status"], "unsupported")
        self.assertFalse(r["deliverability_verified"])
        with self.assertRaises(ValueError):
            validate_address("US", {"city": "Washington\nDC"})

    def test_optional_index_proves_only_postcode_observation(self):
        from localities.postal_picker import _write
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "postal.db"
            with sqlite3.connect(p) as db:
                _write(db, [("DE", "10115", (("area", "Berlin, Berlin"),), "geonames-postal-20261118")])
            r = validate_address("DE", {"postcode": "10115", "city": "Madeup"}, index_path=p)
            self.assertEqual(r["matched_scope"], "postcode_observation")
            self.assertEqual(r["unverified_fields"], ["city"])
            self.assertEqual(validate_address("DE", {"postcode": "00000"}, index_path=p)["status"], "not_observed")
            self.assertEqual(validate_address("XY", {"postcode": "10115"}, index_path=p)["status"], "unsupported")


if __name__ == "__main__":
    unittest.main()
