import json
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

from addressing import address_ranker

from addressing.address_ranker import (
    FEATURES, MAX_CANDIDATES, MAX_QUERY, MODEL_FILE, fold, fuzzy_matches, rank_candidates, supports_pool,
)


def street(label, **kwargs):
    return dict(dict(country_code="US", postcode="01234", label=label, source_id="us-dc-mar",
                     kind="street"), **kwargs)


class RankerTests(unittest.TestCase):
    def test_scope_gate_applies_even_without_a_query_and_preserves_zero(self):
        valid = street("Main Street NE")
        candidates = [street("wrong code", postcode="1234"), street("same postcode", country_code="FR"),
                      street("blank source", source_id="  "), street("control", postcode="01234\n"),
                      {}, None, valid]
        self.assertEqual([valid], rank_candidates("", candidates, country_code="us", postcode="01234"))
        self.assertEqual([], rank_candidates("", candidates, country_code="US", postcode=1234))

    def test_source_rows_are_not_modified_and_only_source_order_breaks_ties(self):
        items = [street("First Street NE"), street("Harbor Road NW", id="a"),
                 street("Harbor Road NW", id="b"), street("Third Street NE")]
        result = rank_candidates("Harbr Road", items, country_code="US", postcode="01234")
        self.assertIs(result[0], items[1])
        self.assertIs(result[1], items[2])
        self.assertEqual({id(r) for r in items}, {id(r) for r in result})
        self.assertNotIn("score", items[0])

    def test_source_scope_and_numeric_levels_that_were_not_trained_keep_order(self):
        cases = [([street("15", kind="house_number"), street("2", kind="house_number")], "2"),
                 ([street("East Avenue", source_id="other"), street("North", source_id="other")], "north"),
                 ([street("East Avenue", country_code="NZ"), street("North", country_code="NZ")], "north")]
        for options, q in cases:
            country = options[0]["country_code"]
            self.assertFalse(supports_pool(country, options))
            self.assertEqual(options, rank_candidates(q, options, country_code=country, postcode="01234"))

    def test_fullwidth_japanese_postcode_preserves_digits_and_voicing(self):
        options = [dict(country_code="JP", postcode="0010001", source_id="japanpost-postal-20261030",
                        kind="town", label=l) for l in ("バラ町", "ハラ町")]
        self.assertEqual("ハラ町", rank_candidates("ﾊﾗ町", options, country_code="JP",
                                                 postcode="００１－０００１")[0]["label"])
        self.assertNotEqual(fold("パ"), fold("バ"))
        self.assertEqual(fold("Évreux"), fold("Evreux"))

    def test_artifacts_are_linked_to_real_parameters_and_held_out_metrics(self):
        model = json.loads(MODEL_FILE.read_text())
        report = json.loads((Path(MODEL_FILE).parent / "report.json").read_text())
        self.assertEqual(model["features"], list(FEATURES))
        for c, w in model["country_weights"].items():
            self.assertTrue(any(abs(x) > 0.1 for x in w))
            self.assertGreater(report["split"]["test"][c]["postcodes"], 1)
            case = report["held_out"][c]["all"]
            self.assertGreater(case["model_top1"], case["baseline_top1"])
            subset = report["prefix_retrieval_and_ranking"][c]["all"]
            self.assertEqual(case["queries"], subset["queries"])
            self.assertLess(subset["target_recalled"], subset["queries"])

    def test_malformed_artifact_never_silently_claims_to_rank(self):
        options = [street("East Street"), street("West Street")]
        with tempfile.TemporaryDirectory() as temp:
            model = Path(temp) / "model.json"
            model.write_text(json.dumps({"version": address_ranker.MODEL_VERSION,
                                         "features": list(FEATURES), "country_weights": []}))
            with patch.object(address_ranker, "MODEL_FILE", model):
                address_ranker._weights.cache_clear()
                with self.assertRaisesRegex(ValueError, "invalid address ranker coefficients"):
                    rank_candidates("West", options, country_code="US", postcode="01234")
            address_ranker._weights.cache_clear()

    def test_spelling_rescue_requires_similar_names_in_the_same_script(self):
        for query, label in [("harbr", "Harbor Road NW"), ("Habrour", "Harbour Road NW"),
                             ("steet", "Main Street NW"), ("霞カ関", "霞ケ関")]:
            self.assertTrue(fuzzy_matches(query, label), (query, label))
        for query, label in [("hbrr", "Harbor"), ("近所", "近町"), ("h", "Harbor"),
                             ("霞カ関", "Harbor"), ("9 harbr", "9 Harbor"), ("harbr", "Harbor 12"),
                             ("H*rbr", "Harbor"), ("harbr", "Harbor / NE"),
                             ("AБCD", "ABCD"), ("田町１", "田町２"), ("大字一番", "大字二番")]:
            self.assertFalse(fuzzy_matches(query, label), (query, label))

    def test_oversized_requests_rejected(self):
        with self.assertRaises(ValueError):
            rank_candidates("x"*(MAX_QUERY+1), [], country_code="US", postcode="00123")
        with self.assertRaises(ValueError):
            rank_candidates("", [street("Park")]*(MAX_CANDIDATES+1), country_code="US", postcode="00123")


if __name__ == "__main__":
    unittest.main()
