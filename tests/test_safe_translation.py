import unittest

from addressing.safe_translation import translate_address


class SafeTranslationTests(unittest.TestCase):
    def test_japan_post_exact_row_and_reversibility(self):
        data = {"province": "東京都", "city": "渋谷区", "town": "神宮前",
                "postcode": "150-0001", "unit": "Ｂ-０３", "house_number": "００２-1"}
        result = translate_address("JP", data, "ja-JP", "en-US")
        self.assertEqual("complete", result["status"])
        self.assertEqual(result["components"], {**data, "province": "TOKYO TO", "city": "SHIBUYA KU",
                                                "town": "JINGUUMAE"})
        self.assertEqual(result["original_components"], data)
        self.assertIsNot(result["original_components"], data)
        receipt = result["fields"]["town"]
        self.assertEqual(receipt["status"], "romanized")
        self.assertEqual(receipt["provenance"]["published_language"], "ja-Latn")
        self.assertEqual(receipt["provenance"]["source_row"], "40059")
        back = translate_address("JP", result["components"], "ja-Latn", "ja")
        self.assertEqual(back["components"], data)
        self.assertFalse(back["delivery_verified"])

    def test_no_postal_qualifier_removed_or_town_fabricated(self):
        data = {"city": "千代田区", "town": "丸の内", "postcode": "100-0005"}
        result = translate_address("JP", data, "ja", "en")
        self.assertTrue(result["needs_review"])
        self.assertEqual(result["components"]["town"], data["town"])
        for postcode in ("100-0005", "150-0001"):
            r = translate_address("JP", {"postcode": postcode, "town": "私製町（１～９階）"}, "ja", "en")
            self.assertEqual(r["components"]["town"], "私製町（１～９階）")

    def test_unambiguous_gazetteer_only_and_no_lookup_of_record_ids_as_names(self):
        r = translate_address("JP", {"city": "網走市", "name": " 山田  太郎 ", "unit": "Ａ-０２"}, "ja", "en")
        self.assertEqual(r["components"]["city"], "Abashiri Shi")
        self.assertEqual(r["components"]["name"], " 山田  太郎 ")
        self.assertEqual(r["components"]["unit"], "Ａ-０２")
        self.assertEqual(r["status"], "partial")
        for value in ("府中市", r["fields"]["city"]["provenance"]["record_id"]):
            r = translate_address("JP", {"city": value}, "ja", "en")
            self.assertTrue(r["needs_review"])
            self.assertEqual(r["components"]["city"], value)

    def test_state_and_country_labels_are_scoped(self):
        us = translate_address("US", {"country": "United States", "state": "California", "unit": "004-B"},
                               "en", "ja")
        self.assertEqual(us["components"]["state"], "カリフォルニア州")
        self.assertEqual(us["fields"]["state"]["provenance"]["record_id"], "subdivision:usca")
        self.assertEqual(us["fields"]["unit"]["status"], "preserved_identifier")
        for cc, fields in (("CN", {"state":"California"}), ("US", {"state":"California", "state_code":"NY"}),
                           ("CN", {"country":"Japan"})):
            self.assertTrue(translate_address(cc, fields, "en", "ja")["needs_review"])

    def test_chinese_municipality_script_parent_and_full_field_boundaries(self):
        r = translate_address("CN", {"state":"广东省", "city":"深圳市", "road":"深圳市路123号"},
                              "zh-CN", "en")
        self.assertEqual(r["components"], {"state":"Guangdong", "city":"Shenzhen", "road":"深圳市路123号"})
        self.assertTrue(r["needs_review"])
        for parent in ("江苏省", "海南省"):
            r = translate_address("CN", {"state":parent, "city":"深圳市"}, "zh-CN", "en")
            self.assertEqual(r["components"]["city"], "深圳市")
        for key in ("state", "city"):
            r = translate_address("CN", {key:"上海市"}, "zh-Hans", "en")
            self.assertEqual(r["components"][key], "Shanghai")
        r = translate_address("CN", {"state_code":"GD","city":"Dongguan"}, "en", "zh-TW")
        self.assertEqual(r["components"]["city"], "東莞市")
        r = translate_address("CN", {"city":"广东省"}, "zh-Hans", "en")
        self.assertTrue(r["needs_review"])
        r = translate_address("CN", {"state":"江苏省", "city":"上海市"}, "zh-Hans", "en")
        self.assertIn("city", r["unverified_fields"])
        r = translate_address("CN", {"state":"香港"}, "zh-Hans", "en")
        self.assertTrue(r["needs_review"])

    def test_bilingual_published_office_only_with_compatible_supplied_postcode(self):
        data = {"organization": "駐深圳聯絡處", "postcode": "518033"}
        r = translate_address("CN", data, "zh-HK", "en")
        self.assertEqual(r["components"]["organization"], "Shenzhen Liaison Unit")
        self.assertIn("terms_url", r["fields"]["organization"]["provenance"])
        for postcode in ("000000", "519000"):
            wrong = translate_address("CN", {**data,"postcode":postcode}, "zh-HK","en")
            self.assertEqual(wrong["components"]["organization"], "駐深圳聯絡處")
            self.assertTrue(wrong["needs_review"])
        self.assertTrue(translate_address("CN", data, "zh-Hans", "en")["needs_review"])

    def test_unknown_languages_cannot_succeed_even_for_same_tag_or_identifier(self):
        for source, target in (("und", "und"), ("en", "und"), ("xx", "xx"), ("ja", "en-Cyrl")):
            result = translate_address("JP", {"postcode":"001-0001"}, source, target)
            self.assertEqual("needs_review", result["status"])
            self.assertEqual(["001-0001"], result["lines"])

    def test_opaque_extra_and_two_fields_with_identical_values_survive(self):
        data = {"x_extra": " 甲  02 ", "building":"甲", "recipient":"甲", "postcode":"100-0001"}
        r = translate_address("JP", data, "ja", "en")
        self.assertEqual(r["components"], data)
        self.assertCountEqual(r["lines"], data.values())
        self.assertEqual(r["unverified_fields"], ["x_extra","building","recipient"])

    def test_ambiguous_field_and_dangerous_controls_rejected(self):
        for data in ({"room":"1","unit":"2"}, {"country_code":"US"}, {"address1":"A\nB"},
                     {"road":"abc\u202e123"}, {"postcode":10001}):
            with self.assertRaises(ValueError):
                translate_address("JP", data, "ja", "en")


if __name__ == "__main__":
    unittest.main()
