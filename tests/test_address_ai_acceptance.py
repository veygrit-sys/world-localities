"""Cross-operation release regressions on synthetic addresses. Never quality gold."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from addressing.address_ai import AddressInputError, process_request
from addressing.safe_suggest import build_index


CASES = json.loads((Path(__file__).resolve().parents[1] / "evaluation" / "address-ai" /
                    "acceptance-cases.json").read_text(encoding="utf-8"))


def fixture_profile(country, line_limit=128):
    return {"id": "fixture-" + country.lower(), "unit": "utf8_bytes",
            "line_limit": line_limit, "max_lines": 3, "countries": [country],
            "field_limits": {"city": 64, "state": 64, "postcode": 12, "country_code": 2},
            "required_fields": ["city", "postcode"]}


class AddressAIAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        cls.index = Path(folder.name) / "acceptance.sqlite"
        with patch("localities.postal_picker._records", return_value=CASES["picker_records"]):
            build_index(cls.index)

    def call(self, operation, *, config=None, **kwargs):
        request = {"operation": operation, **kwargs}
        before = copy.deepcopy(request)
        with patch("socket.socket.connect", side_effect=AssertionError("unexpected network call")):
            response = process_request(request, **(config or {}))
        self.assertEqual(request, before, "a request must remain available for manual review")
        self.assertEqual(response["schema_version"], 1)
        self.assertEqual(response["operation"], operation)
        # Results are suitable for a JSON API; no unserializable or nonfinite values.
        json.dumps(response, allow_nan=False)
        return response["result"]

    def fit(self, country, components, line_limit=128):
        profile = fixture_profile(country, line_limit)
        return self.call("fit_label", country=country, components=components, profile_id=profile["id"],
                         config={"label_profiles": {profile["id"]: profile}})

    def lookup(self, country, postcode, **kwargs):
        return self.call("suggest", config={"index_path": self.index},
                         country=country, postcode=postcode, **kwargs)

    def test_typed_candidates_are_scoped_to_country_postcode_and_parent(self):
        cases = [("JP", "００１－０００１", "架空試験市", "見本", {"見本北町", "見本南町"}),
                 ("CN", "100000", "虚构测试区", "测", {"测试路"}),
                 ("US", "02116", "Fixture Town, MA", "fiction", {"Fictional Acceptance Test Avenue"})]
        for country, code, area, prefix, expected in cases:
            with self.subTest(country=country):
                result = self.lookup(country, code)
                self.assertFalse(result["deliverability_verified"])
                self.assertTrue(result["manual_entry_available"])
                self.assertEqual([o["label"] for o in result["options"]], [area])
                path = [result["options"][0]["id"]]
                children = self.lookup(country, code, path=path, query=prefix)
                self.assertEqual({o["label"] for o in children["options"]}, expected)
                self.assertTrue(all(o["country_code"] == country and
                                    "acceptance-fixture" in o["supporting_sources"]
                                    for o in children["options"]))

    def test_unobserved_house_number_never_becomes_a_suggestion(self):
        root = self.lookup("US", "02116")
        path = [root["options"][0]["id"]]
        street = self.lookup("US", "02116", path=path)
        path.append(street["options"][0]["id"])
        houses = self.lookup("US", "02116", path=path)
        self.assertEqual({o["label"] for o in houses["options"]}, {"07B", "09B"})
        for query in ("08B", "%", "_"):
            with self.subTest(query=query):
                empty = self.lookup("US", "02116", path=path, query=query)
                self.assertEqual(empty["options"], [])
                self.assertTrue(empty["manual_entry_available"])
        with self.assertRaises(AddressInputError):
            self.lookup("US", "02117", path=path)

    def test_locality_evidence_or_plausible_format_cannot_release_synthetic_premise(self):
        for case in CASES["addresses"]:
            with self.subTest(case=case["id"]):
                country, components = case["country"], case["components"]
                val = self.call("validate", country=country, components=components)
                self.assertFalse(val["deliverability_verified"])
                detail = "unit" if "unit" in components else "address_line2"
                self.assertNotIn(detail, val["verified_fields"])
                profile = fixture_profile(country)
                result = self.call("prepare_label", country=country, components=components,
                                   profile_id=profile["id"],
                                   config={"label_profiles": {profile["id"]: profile}})
                self.assertEqual(result["status"], "review_required")
                self.assertIsNone(result["fields"])

    def test_unsupported_country_and_invalid_postcode_do_not_pass_validation(self):
        for country, code, status in (("ZZ", "12345", "unsupported"), ("JP", "12", "invalid_format"),
                                      ("CN", "00000X", "invalid_format"), ("US", "21A16", "invalid_format")):
            with self.subTest(country=country):
                result = self.call("validate", country=country,
                                   components={"city": "Fixture", "postcode": code})
                self.assertEqual(result["status"], status)
                self.assertFalse(result["deliverability_verified"])
        self.assertEqual(self.lookup("ZZ", "12345")["options"], [])

    def test_public_dc_address_point_prepares_fields_but_extra_unit_or_wrong_zip_blocks(self):
        # Public White House address, DC MAR record 293211. No customer or private contact.
        components = {"city": "WASHINGTON", "state": "DC", "postcode": "20500",
                      "house_number": "1600", "road": "PENNSYLVANIA AVENUE NW"}
        def prepare(**extra):
            return self.call("prepare_label", country="US", components=components | extra,
                             profile_id="ups-us-shipto")

        prepared = prepare()
        self.assertEqual(prepared["status"], "prepared")
        self.assertEqual(prepared["fields"]["address_lines"], ["1600 PENNSYLVANIA AVENUE NW"])
        self.assertEqual(prepared["fields"]["postcode"], "20500")
        self.assertFalse(prepared["submitted"])
        self.assertFalse(prepared["deliverability_verified"])
        for change in ({"unit": "07B"}, {"postcode": "20004"}):
            with self.subTest(change=change):
                result = prepare(**change)
                self.assertEqual(result["status"], "review_required")
                self.assertIsNone(result["fields"])
                self.assertFalse(result["submitted"])

    def test_unknown_translation_keeps_source_and_protected_identifiers(self):
        for case in CASES["addresses"]:
            with self.subTest(case=case["id"]):
                original = case["components"]
                result = self.call("translate", country=case["country"], components=original,
                                   source_language=case["source_language"],
                                   target_language=case["target_language"])
                self.assertEqual(result["original_components"], original)
                preserved = ("postcode", "house_number", "unit", "address_line1", "address_line2")
                for key in preserved:
                    if key in original:
                        self.assertEqual(result["components"][key], original[key])
                if "address_line1" in original:
                    self.assertTrue(result["needs_review"])

    def test_fitting_can_succeed_without_carrier_release_and_without_losing_identifiers(self):
        for case in CASES["addresses"]:
            with self.subTest(case=case["id"]):
                country, components = case["country"], case["components"]
                result = self.fit(country, components)
                self.assertEqual(result["status"], "fits")
                self.assertFalse(result["deliverability_verified"])
                fields = result["fields"]
                self.assertEqual(fields["country_code"], country)
                self.assertEqual(fields["postcode"], components["postcode"])
                self.assertEqual(fields["city"], components["city"])
                lines = " ".join(fields["address_lines"])
                keys = ("house_number", "unit") if country == "US" else ("address_line1", "address_line2")
                for key in keys:
                    self.assertIn(components[key], lines)
                self.assertTrue(all(len(line.encode("utf-8")) <= 128 for line in fields["address_lines"]))

    def test_multibyte_budget_cannot_split_or_erase_a_unit(self):
        jp = CASES["addresses"][0]
        components = jp["components"] | {"address_line1": "1"}
        unit_line = components["address_line2"]
        # Isolate the second line: the primary line and every structured field
        # still fit. A single UTF-8 byte must be sufficient to flip the result.
        size = len(unit_line.encode("utf-8"))
        self.assertLess(len(unit_line), size - 1)
        exact = self.fit("JP", components, size)
        self.assertEqual(exact["fields"]["address_lines"], ["1", unit_line])
        result = self.fit("JP", components, size - 1)
        self.assertEqual(result["status"], "review_required")
        self.assertIsNone(result["fields"])


if __name__ == "__main__":
    unittest.main()
