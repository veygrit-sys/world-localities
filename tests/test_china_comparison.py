"""Keep the same unmodified CN requests, output fields and references across runs."""

from copy import deepcopy
import unittest

from scripts.compare_china_addresses import CASES, load_jsonl, local_prediction, score_run


class ChinaComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = load_jsonl(CASES / "requests.jsonl")
        cls.expected = load_jsonl(CASES / "expected.jsonl")
        cls.predictions = [local_prediction(case, "CLDR-48") for case in cls.requests]

    def test_fixed_cases_and_abstention(self):
        report = score_run(self.requests, self.expected, self.predictions)["evaluation"]
        self.assertEqual(report["claim_status"], "diagnostic_only")
        metrics = report["diagnostic_metrics"]
        self.assertEqual((metrics["cases"], metrics["correct_outputs"], metrics["false_accepts"]), (7, 6, 0))
        self.assertEqual(metrics["abstained_cases"], 1)
        road = next(p for p in self.predictions if p["case_id"] == "hebei-road-en")
        self.assertEqual(road["verdict"], "abstain")
        self.assertNotIn("components", road)

    def test_provider_order_independent_and_wrong_translation_is_scored(self):
        external = [dict(row, provider="test-adapter", data_version="fixture-v1")
                    for row in reversed(self.predictions)]
        next(p for p in external if p["case_id"] == "beijing-province-en")["components"] = {"state": "Shanghai"}
        run = score_run(self.requests, self.expected, external)
        self.assertEqual(run["evaluation"]["diagnostic_metrics"]["false_accepts"], 1)
        self.assertEqual(run["provider"], "test-adapter")

    def test_same_case_id_with_modified_input_is_rejected(self):
        requests = deepcopy(self.requests)
        requests[0]["components"]["house_number"] = "030"
        with self.assertRaisesRegex(ValueError, "digest differs"):
            score_run(requests, self.expected, self.predictions)

    def test_missing_result_metadata_and_different_scopes_are_rejected(self):
        for change in ({"fields": ["state"]}, {"provider": ""}, {"provider": "other"}, {"data_version": ""},
                       {"components": {"state": "北京市"}}, {"input_sha256": ""}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                predictions = deepcopy(self.predictions)
                predictions[0].update(change)
                score_run(self.requests, self.expected, predictions)
