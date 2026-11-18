"""The CN renderer may only supply a province label supported by a CLDR pair."""

import json
import unittest

from addressing import EastAsiaRegistry, MissingLocalizedComponents, ProfileRegistry, render_bilingual_address
from addressing.china_subdivisions import DATA


class ChinaSubdivisionLabels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ProfileRegistry()
        cls.region = EastAsiaRegistry()
        cls.catalog = json.loads(DATA.read_text(encoding="utf-8"))

    def render(self, components, *, country="CN", strict=True):
        return render_bilingual_address(
            components, country, strict=strict, registry=self.registry, east_asia=self.region,
        )

    def test_all_mainland_pairs_work_in_both_directions_and_have_evidence(self):
        subdivisions = self.catalog["subdivisions"]
        self.assertEqual(len(subdivisions), 31)
        self.assertFalse({"cnhk", "cnmo", "cntw"} & subdivisions.keys())
        for code, row in subdivisions.items():
            for source, source_locale, target, target_locale in (
                ("zh-Hans", "zh", "en", "en"), ("en", "en", "zh-Hans", "zh"),
            ):
                with self.subTest(code=code, target=target):
                    original = {"province": {source: " " + row[source_locale] + " "}}
                    rendered = self.render(original)
                    self.assertEqual(rendered.native.components["state"], row["zh"])
                    self.assertEqual(rendered.english.components["state"], row["en"])
                    self.assertEqual(rendered.source_components, original)
                    evidence, = rendered.to_dict()["label_evidence"]
                    self.assertEqual(evidence["language"], target)
                    self.assertEqual(evidence["source_version"], "48")
                    self.assertEqual(evidence["subdivision_id"], code)
                    self.assertEqual(evidence["matched_source_locale"], source_locale)
                    self.assertEqual(evidence["source_draft_status"], row[target_locale + "_draft_status"])
                    self.assertEqual(evidence["matched_source_draft_status"], row[source_locale + "_draft_status"])
                    self.assertIn(self.catalog["revision"], evidence["reference"])

    def test_exact_names_not_prefixes_and_identifiers_stay_intact(self):
        for raw, expected in ((" 陕西省 ", "Shaanxi"), ("山西省", "Shanxi")):
            result = self.render({
                "province": raw, "postcode": "000001", "house_number": "001-2",
                "unit": {"en": "02", "zh-Hans": "02"},
            })
            self.assertIn(expected, result.english.text)
            self.assertEqual(result.source_components["province"], raw)
            for output in (result.native, result.english):
                for identifier in ("000001", "001-2", "02"):
                    self.assertIn(identifier, output.text)

    def test_untagged_and_source_language_variants(self):
        for value in ("北京市", {"zh-CN": "北京市"}, {"zh": "北京市"}, {"en-GB": "Beijing"}):
            with self.subTest(value=value):
                result = self.render({"state": value, "state_code": "CN-BJ"})
                self.assertEqual(result.native.components["state"], "北京市")
                self.assertEqual(result.english.components["state"], "Beijing")

    def test_scopes_and_unresolved_values(self):
        for components in (
            {"state": "北京"}, {"city": "北京市"}, {"road": "北京市"}, {"state": {"en": "Shanx"}},
            {"state": {"zh-Hant": "北京市"}}, {"state": {"en-Cyrl": "Beijing"}},
            {"state": "香港"}, {"state": "澳门"}, {"state": "台湾省"},
            {"state": "北京市", "road": "未収録路"},
            {"state": "北京市", "state_code": "CN-SH"},
        ):
            with self.subTest(components=components), self.assertRaises(MissingLocalizedComponents):
                self.render(components)
        with self.assertRaises(MissingLocalizedComponents):
            self.render({"state": {"en": "Beijing"}}, country="HK")

    def test_conflicting_known_labels_keep_original_and_warn(self):
        original = {"state": {"zh-Hans": "北京市", "en": "Shanghai"}}
        result = self.render(original)
        self.assertEqual(result.source_components, original)
        self.assertEqual(result.native.components["state"], "北京市")
        self.assertEqual(result.english.components["state"], "Shanghai")
        self.assertIn("conflicting_province_labels:state", result.warnings)
        self.assertNotIn("label_evidence", result.to_dict())
        unrecognized = self.render({"state": {"zh-Hans": "北京市", "en": "Custom Beijing"}})
        self.assertNotIn("conflicting_province_labels:state", unrecognized.warnings)

    def test_province_code_can_only_conflict_on_source_recognition(self):
        state = {"zh-Hans": "北京市", "en": "Beijing"}
        for code in ("CN-SH", "31"):
            output = self.render({"state": state, "state_code": code})
            self.assertIn("conflicting_state_and_state_code", output.warnings)
            self.assertEqual(output.english.components["state"], "Beijing")
        for code in ("XX", "99", "110000"):
            output = self.render({"state": state, "state_code": code})
            self.assertNotIn("conflicting_state_and_state_code", output.warnings)
        # Two pinned sources independently give the same unique Chinese label.
        output = self.render({"state": {"zh-Hans": "北京市"}, "state_code": "11"})
        self.assertEqual(output.english.components["state"], "Beijing")
        self.assertNotIn("conflicting_state_and_state_code", output.warnings)
        output = self.render({"state": {"zh-Hans": "北京市"}, "state_code": "31"}, strict=False)
        self.assertIn("conflicting_state_and_state_code", output.warnings)
        self.assertNotIn("state", output.english.components)
        self.assertNotIn("label_evidence", output.to_dict())

    def test_explicit_values_and_ambiguous_variants_do_not_get_replaced(self):
        result = self.render({"state": {"zh-Hans": "北京市", "en-GB": "User-confirmed Beijing"}})
        self.assertEqual(result.english.components["state"], "User-confirmed Beijing")
        self.assertNotIn("label_evidence", result.to_dict())
        ambiguous = {"state": {"zh-Hans": "北京市", "en-GB": "Beijing", "en-US": "Shanghai"}}
        result = self.render(ambiguous, strict=False)
        self.assertIn("ambiguous_language_variants:state", result.warnings)
        self.assertNotIn("state", result.english.components)
        self.assertNotIn("label_evidence", result.to_dict())


if __name__ == "__main__":
    unittest.main()
