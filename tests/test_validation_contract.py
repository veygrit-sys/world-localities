"""Result boundaries prevent malformed claims and post-check mutation."""

import copy
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing.contracts import LocationPrecision, ValidationLevel, ValidationResult
from jsonschema import Draft202012Validator


EVIDENCE = {
    "evidence_type": "carrier",
    "source_id": "test-only-carrier",
    "reference": "test-only:lookup-1",
}


def result(**overrides):
    return ValidationResult(**{
        "status": "verified",
        "level": ValidationLevel.LOCALITY,
        "confidence": 0.9,
        "components": {"country_code": "JP", "city": "Example"},
        **overrides,
    })


class ValidationResultBoundary(unittest.TestCase):
    def test_rejects_untyped_levels_and_precision_before_serialization(self):
        for value in (0, 7, True, 7.0, "deliverability", None):
            with self.subTest(level=value), self.assertRaises(ValueError):
                result(level=value)
        for value in ("entrance", None, 0):
            with self.subTest(precision=value), self.assertRaises(ValueError):
                result(location_precision=value)

    def test_confidence_is_a_finite_number_not_a_boolean(self):
        for value in (True, False, float("nan"), float("inf"), -float("inf"),
                      -0.1, 1.1, "0.9", None, 10 ** 1000):
            with self.subTest(value=value), self.assertRaises(ValueError):
                result(confidence=value)
        for value in (0, 1, 0.5):
            json.dumps(result(confidence=value).to_dict(), allow_nan=False)

    def test_requires_string_components_and_unique_string_warnings(self):
        for value in (None, [], {1: "Example"}, {"city": 123}, {" ": "Example"}):
            with self.subTest(components=value), self.assertRaises(ValueError):
                result(components=value)
        for value in ("warning", None, (1,), ("duplicate", "duplicate")):
            with self.subTest(warnings=value), self.assertRaises(ValueError):
                result(warnings=value)
        self.assertEqual(result(warnings=["review_needed"]).warnings, ("review_needed",))

    def test_deliverability_requires_one_traceable_operator_record(self):
        invalid = (
            (),
            ({"evidence_type": "carrier"},),
            ({"evidence_type": "carrier", "source_id": "test-only"},),
            ({**EVIDENCE, "reference": " "},),
            ({**EVIDENCE, "evidence_type": "geocoder"},),
            # Required fields cannot be assembled from unrelated records.
            ({"evidence_type": "carrier"}, {"source_id": "test-only", "reference": "test-only:1"}),
        )
        for evidence in invalid:
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                result(level=ValidationLevel.DELIVERABILITY, evidence=evidence)
        for kind in ("carrier", "postal_operator"):
            payload = result(
                level=ValidationLevel.DELIVERABILITY,
                evidence=({**EVIDENCE, "evidence_type": kind},),
                location_precision=LocationPrecision.ENTRANCE,
            ).to_dict()
            self.assertEqual(payload["verification_level_number"], 7)

    def test_evidence_is_json_shaped_and_trace_fields_are_not_blank(self):
        for evidence in (None, {}, (None,), ("carrier",),
                         ({"source_id": " "},), ({"reference": 123},),
                         ({"nested": {1: "value"}},), ({"value": object()},),
                         ({"value": float("nan")},)):
            with self.subTest(evidence=evidence), self.assertRaises(ValueError):
                result(evidence=evidence)
        cyclic = {}
        cyclic["self"] = cyclic
        with self.assertRaisesRegex(ValueError, "circular"):
            result(evidence=(cyclic,))

    def test_caller_and_serialized_mutations_do_not_change_checked_claim(self):
        components = {"country_code": "JP"}
        evidence = [copy.deepcopy(EVIDENCE)]
        evidence[0]["details"] = {"ids": ["original"], "matched": True}
        warnings = ["declared_evidence_only"]
        checked = result(level=ValidationLevel.DELIVERABILITY, components=components,
                         evidence=evidence, warnings=warnings)
        before = checked.to_dict()
        components["country_code"] = "US"
        evidence[0]["reference"] = ""
        evidence[0]["details"]["ids"].append("changed")
        warnings.clear()
        serialized = checked.to_dict()
        serialized["evidence"][0]["details"]["ids"].clear()
        self.assertEqual(checked.to_dict(), before)
        with self.assertRaises(TypeError):
            checked.components["country_code"] = "US"
        with self.assertRaises(TypeError):
            checked.evidence[0]["details"]["matched"] = False
        self.assertIsInstance(checked.evidence[0]["details"]["ids"], tuple)
        json.dumps(checked.to_dict(), allow_nan=False)


class ValidationResultSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        schema = json.loads((Path(__file__).resolve().parents[1] /
                             "addressing/validation-result.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema)

    def test_every_typed_level_serializes_to_a_valid_schema_result(self):
        for level in ValidationLevel:
            with self.subTest(level=level):
                self.validator.validate(result(level=level, evidence=(EVIDENCE,)).to_dict())

    def test_level_name_and_number_must_correspond(self):
        payload = result().to_dict()
        payload["verification_level_number"] = 7
        self.assertFalse(self.validator.is_valid(payload))

    def test_schema_rejects_untraceable_delivery_and_invalid_structures(self):
        payload = result(level=ValidationLevel.DELIVERABILITY, evidence=(EVIDENCE,)).to_dict()
        changes = (
            {"evidence": []},
            {"evidence": [{"evidence_type": "carrier"}]},
            {"evidence": [{**EVIDENCE, "reference": " "}]},
            {"evidence": [{**EVIDENCE, "evidence_type": "geocoder"}]},
            {"confidence": True},
            {"components": {" ": "Example"}},
            {"warnings": ["duplicate", "duplicate"]},
        )
        for change in changes:
            with self.subTest(change=change):
                self.assertFalse(self.validator.is_valid({**payload, **change}))


if __name__ == "__main__":
    unittest.main()
