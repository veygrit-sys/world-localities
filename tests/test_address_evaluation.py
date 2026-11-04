"""Synthetic evaluator fixtures are diagnostics, never independent address gold."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "address_evaluation", Path(__file__).resolve().parents[1] / "scripts/evaluate_addresses.py")
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)


def case(identifier, country="JP", verdict="matched", task="entity_resolution"):
    expected = {"verdict": verdict}
    if verdict == "matched":
        expected.update({"entity_resolution": {"entity_id": "fixture:" + identifier},
                         "component_validation": {"components": {"city": "synthetic fixture"}},
                         "format_rendering": {"rendered": "synthetic rendering"}}[task])
    return {"case_id": identifier, "country": country, "task": task, "expected": expected,
            "split": "evaluation", "used_for_training": False,
            "evidence": {"source_id": "test-fixture", "reference": "synthetic evaluator fixture"},
            "provenance": {"kind": "synthetic", "independently_reviewed": False}}


def prediction(example, verdict=None, **overrides):
    record = {"case_id": example["case_id"], "country": example["country"],
              "task": example["task"], **copy.deepcopy(example["expected"])}
    if verdict is not None:
        for field in ("entity_id", "components", "rendered"):
            record.pop(field, None)
        record["verdict"] = verdict
    record.update(overrides)
    return record


class AddressEvaluationTests(unittest.TestCase):
    def test_correct_wrong_abstain_and_country_macro(self):
        examples = [case("a"), case("b"), case("c", "DE", verdict="no_match"),
                    case("d", "DE", verdict="ambiguous")]
        predictions = [prediction(examples[0], latency_ms=10),
                       prediction(examples[1], entity_id="fixture:wrong", latency_ms=30),
                       prediction(examples[2], "matched", entity_id="fixture:unsupported", latency_ms=20),
                       prediction(examples[3], "abstain", latency_ms=40)]
        report = evaluation.evaluate(examples, predictions)
        metrics = report["diagnostic_metrics"]
        self.assertEqual(report["claim_status"], "diagnostic_only")
        self.assertNotIn("independent_metrics", report)
        self.assertEqual(metrics["correct_outputs"], 1)
        self.assertEqual(metrics["country_macro_accuracy"], 0.25)
        self.assertEqual(metrics["false_accepts"], 2)
        self.assertAlmostEqual(metrics["accepted_error_rate"], 2 / 3)
        self.assertEqual(metrics["acceptance_coverage"], 0.75)
        self.assertEqual(metrics["correct_acceptance_coverage"], 0.25)
        self.assertEqual(metrics["abstention_rate"], 0.25)
        self.assertEqual(metrics["latency"]["p50_ms"], 20)
        self.assertEqual(metrics["latency"]["p95_ms"], 40)

    def test_abstaining_on_every_case_does_not_earn_acceptance_accuracy(self):
        example = case("a")
        metrics = evaluation.evaluate([example], [prediction(example, "abstain")])["diagnostic_metrics"]
        self.assertEqual(metrics["acceptance_coverage"], 0)
        self.assertIsNone(metrics["accepted_error_rate"])
        self.assertEqual(metrics["exact_output_accuracy"], 0)
        self.assertIsNone(metrics["latency"]["p95_ms"])

    def test_exact_negative_or_ambiguous_verdict_can_be_correct_without_acceptance(self):
        examples = [case("negative", verdict="no_match"), case("ambiguous", verdict="ambiguous")]
        metrics = evaluation.evaluate(examples, [prediction(e) for e in examples])["diagnostic_metrics"]
        self.assertEqual(metrics["exact_output_accuracy"], 1)
        self.assertEqual(metrics["accepted_cases"], 0)

    def test_missing_extra_and_duplicate_predictions_are_rejected(self):
        example = case("a")
        for predictions in ([], [prediction(example), prediction(example)],
                            [prediction(example), prediction(case("extra"))]):
            with self.assertRaises(ValueError):
                evaluation.evaluate([example], predictions)

    def test_case_and_equivalence_group_training_leakage_are_rejected(self):
        example = case("a")
        example["equivalence_group"] = "same-entity-and-aliases"
        for training in ([{"case_id": "a"}], [{"case_id": "other-query", "equivalence_group": "same-entity-and-aliases"}]):
            with self.assertRaisesRegex(ValueError, "overlap"):
                evaluation.evaluate([example], [prediction(example)], training)
        report = evaluation.evaluate([example], [prediction(example)], [{"case_id": "disjoint"}])
        self.assertTrue(report["leakage_check"]["training_records_supplied"])
        with self.assertRaisesRegex(ValueError, "training must be a list"):
            evaluation.evaluate([example], [prediction(example)], {})

    def test_country_or_task_mismatch_is_rejected(self):
        example = case("a")
        for override in ({"country": "DE"}, {"task": "format_rendering"}):
            with self.assertRaisesRegex(ValueError, "differs"):
                evaluation.evaluate([example], [prediction(example, **override)])

    def test_unreviewed_or_training_split_cannot_be_independent_gold(self):
        example = case("a")
        for field, value in (("split", "training"), ("used_for_training", True), ("used_for_training", None)):
            changed = copy.deepcopy(example)
            changed[field] = value
            with self.assertRaises(ValueError):
                evaluation.evaluate([changed], [prediction(changed)])
        changed = copy.deepcopy(example)
        changed["provenance"]["independently_reviewed"] = True
        with self.assertRaisesRegex(ValueError, "external review"):
            evaluation.evaluate([changed], [prediction(changed)])

    def test_independent_metrics_use_only_declared_reviewed_subset(self):
        diagnostic, reviewed = case("diagnostic"), case("reviewed")
        # This tests metadata handling only; it is not a real external address example.
        reviewed["provenance"] = {"kind": "external_reviewed", "independently_reviewed": True,
                                  "review_reference": "synthetic-review-reference-for-test"}
        report = evaluation.evaluate([diagnostic, reviewed],
                                     [prediction(diagnostic, entity_id="fixture:wrong"), prediction(reviewed)])
        self.assertEqual(report["independently_reviewed_cases"], 1)
        self.assertEqual(report["diagnostic_metrics"]["exact_output_accuracy"], 0.5)
        self.assertEqual(report["independent_metrics"]["exact_output_accuracy"], 1)
        self.assertEqual(report["independent_metrics"]["cases"], 1)
        self.assertIn("not audited", report["independence_basis"])

    def test_components_and_rendering_are_separate_tasks(self):
        component = case("c", task="component_validation")
        rendering = case("r", task="format_rendering")
        report = evaluation.evaluate([component, rendering],
                                     [prediction(component, components={"city": "different"}), prediction(rendering)])
        self.assertEqual(report["diagnostic_metrics"]["by_task"]["format_rendering"]["exact_output_accuracy"], 1)
        self.assertEqual(report["diagnostic_metrics"]["by_task"]["component_validation"]["exact_output_accuracy"], 0)
        self.assertIn("carrier_deliverability", report["claims_not_measured"])

    def test_invalid_latency_and_unsupported_task_are_rejected(self):
        example = case("a")
        for value in (-1, True, float("nan"), float("inf"), "20"):
            with self.assertRaisesRegex(ValueError, "latency_ms"):
                evaluation.evaluate([example], [prediction(example, latency_ms=value)])
        example["task"] = "deliverability"
        with self.assertRaisesRegex(ValueError, "unsupported task"):
            evaluation.evaluate([example], [prediction(example)])

    def test_required_evidence_and_unique_example_ids(self):
        example = case("a")
        with self.assertRaisesRegex(ValueError, "duplicate example"):
            evaluation.evaluate([example, example], [prediction(example)])
        del example["evidence"]
        with self.assertRaisesRegex(ValueError, "source evidence"):
            evaluation.evaluate([example], [prediction(example)])

    def test_jsonl_loader_rejects_non_objects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cases.jsonl"
            path.write_text("[]\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "expected an object"):
                evaluation.load_jsonl(path)


if __name__ == "__main__":
    unittest.main()
