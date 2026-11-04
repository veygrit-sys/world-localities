"""Score explicit address evaluation cases without inventing independent gold."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import re

TASKS = {"entity_resolution", "component_validation", "format_rendering"}
VERDICTS = {"matched", "no_match", "ambiguous", "abstain"}
PROVENANCE_KINDS = {"synthetic", "source_derived", "external_reviewed"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def load_jsonl(path):
    records = []
    with Path(path).open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            require(isinstance(value, dict), f"{path}:{number}: expected an object")
            records.append(value)
    return records


def validate_target(record, expected=False):
    verdict = record.get("verdict")
    allowed = VERDICTS - {"abstain"} if expected else VERDICTS
    require(verdict in allowed, "invalid expected or predicted verdict")
    if verdict != "matched":
        require(not any(key in record for key in ("entity_id", "components", "rendered")),
                "non-matched verdict must not include an accepted target")
        return
    task = record["task"]
    field = {"entity_resolution": "entity_id", "component_validation": "components",
             "format_rendering": "rendered"}[task]
    require(not any(key in record for key in {"entity_id", "components", "rendered"} - {field}),
            "target fields do not match the selected task")
    value = record.get(field)
    if field == "components":
        require(isinstance(value, dict) and value and
                all(nonempty(k) and isinstance(v, str) for k, v in value.items()),
                "components must be an explicit nonempty string mapping")
    else:
        require(nonempty(value), f"matched verdict requires {field}")


def index_records(records, label):
    require(isinstance(records, list), f"{label} must be a list")
    index = {}
    for record in records:
        require(isinstance(record, dict), f"{label} record must be an object")
        case_id = record.get("case_id")
        require(nonempty(case_id), f"{label} requires case_id")
        require(case_id not in index, f"duplicate {label} case_id: {case_id}")
        index[case_id] = record
    return index


def independent_case(example):
    provenance = example["provenance"]
    return provenance["kind"] == "external_reviewed" and provenance["independently_reviewed"]


def validate_example(example):
    require(isinstance(example.get("country"), str) and
            re.fullmatch(r"[A-Z]{2}", example["country"]), "country must be a two-letter code")
    require(example.get("task") in TASKS, "unsupported task; deliverability is not inferred")
    require(example.get("split") == "evaluation", "case must belong to the evaluation split")
    require(example.get("used_for_training") is False, "evaluation case was used for training or is unreviewed")
    evidence = example.get("evidence")
    require(isinstance(evidence, dict) and nonempty(evidence.get("source_id")) and
            nonempty(evidence.get("reference")), "case requires source evidence and reference")
    provenance = example.get("provenance")
    require(isinstance(provenance, dict) and provenance.get("kind") in PROVENANCE_KINDS and
            type(provenance.get("independently_reviewed")) is bool,
            "case requires explicit provenance and independence status")
    if provenance["independently_reviewed"]:
        require(provenance["kind"] == "external_reviewed" and
                nonempty(provenance.get("review_reference")),
                "independent status requires external review and its reference")
    require(isinstance(example.get("expected"), dict), "case requires expected result")
    validate_target({**example["expected"], "task": example["task"]}, expected=True)
    if "equivalence_group" in example:
        require(nonempty(example["equivalence_group"]), "equivalence_group must be nonempty")


def exact_result(example, prediction):
    expected = example["expected"]
    if expected["verdict"] != prediction["verdict"]:
        return False
    if expected["verdict"] != "matched":
        return True
    field = {"entity_resolution": "entity_id", "component_validation": "components",
             "format_rendering": "rendered"}[example["task"]]
    return expected[field] == prediction[field]


def rate(numerator, denominator):
    return numerator / denominator if denominator else None


def latency_metrics(predictions):
    values = sorted(p["latency_ms"] for p in predictions if "latency_ms" in p)
    if not values:
        return {"measured_cases": 0, "measurement_coverage": 0.0, "p50_ms": None, "p95_ms": None}
    def percentile(fraction):
        return values[max(0, math.ceil(fraction * len(values)) - 1)]
    return {"measured_cases": len(values), "measurement_coverage": rate(len(values), len(predictions)),
            "p50_ms": percentile(0.50), "p95_ms": percentile(0.95)}


def score_cases(examples, predictions):
    count = len(examples)
    correct = accepted = correct_accepted = abstained = ambiguous = 0
    by_country = defaultdict(lambda: [0, 0])
    for example, prediction in zip(examples, predictions):
        right = exact_result(example, prediction)
        accept = prediction["verdict"] == "matched"
        correct += right
        accepted += accept
        correct_accepted += accept and right
        abstained += prediction["verdict"] == "abstain"
        ambiguous += prediction["verdict"] == "ambiguous"
        by_country[example["country"]][0] += right
        by_country[example["country"]][1] += 1
    per_country = {country: {"cases": total, "correct_outputs": good,
                             "exact_output_accuracy": good / total}
                   for country, (good, total) in sorted(by_country.items())}
    macro = sum(row["exact_output_accuracy"] for row in per_country.values()) / len(per_country)
    return {"cases": count, "correct_outputs": correct, "exact_output_accuracy": correct / count,
            "country_macro_accuracy": macro, "countries": per_country,
            "accepted_cases": accepted, "correct_accepted_cases": correct_accepted,
            "false_accepts": accepted - correct_accepted,
            "accepted_error_rate": rate(accepted - correct_accepted, accepted),
            "acceptance_coverage": accepted / count,
            "correct_acceptance_coverage": correct_accepted / count,
            "abstained_cases": abstained, "abstention_rate": abstained / count,
            "ambiguous_predictions": ambiguous, "latency": latency_metrics(predictions)}


def grouped_scores(examples, predictions):
    result = score_cases(examples, predictions)
    result["by_task"] = {}
    for task in sorted({e["task"] for e in examples}):
        pairs = [(e, p) for e, p in zip(examples, predictions) if e["task"] == task]
        result["by_task"][task] = score_cases([e for e, _ in pairs], [p for _, p in pairs])
    return result


def evaluate(examples, predictions, training_records=None):
    example_index = index_records(examples, "example")
    prediction_index = index_records(predictions, "prediction")
    require(example_index, "evaluation set is empty")
    require(set(example_index) == set(prediction_index),
            "prediction case IDs differ from evaluation cases (missing or extra predictions)")
    for example in example_index.values():
        validate_example(example)
    for case_id, prediction in prediction_index.items():
        example = example_index[case_id]
        require(prediction.get("country") == example["country"], f"country differs for {case_id}")
        require(prediction.get("task") == example["task"], f"task differs for {case_id}")
        validate_target(prediction)
        if "latency_ms" in prediction:
            value = prediction["latency_ms"]
            require(type(value) in {int, float} and math.isfinite(value) and value >= 0,
                    "latency_ms must be a finite nonnegative number")
    training_index = index_records(training_records if training_records is not None else [], "training")
    require(set(example_index).isdisjoint(training_index), "evaluation/training case_id overlap")
    train_groups = set()
    for record in training_index.values():
        if "equivalence_group" in record:
            require(nonempty(record["equivalence_group"]), "training equivalence_group must be nonempty")
            train_groups.add(record["equivalence_group"])
    eval_groups = {e["equivalence_group"] for e in examples if "equivalence_group" in e}
    require(eval_groups.isdisjoint(train_groups), "evaluation/training equivalence_group overlap")
    ordered_examples = list(example_index.values())
    ordered_predictions = [prediction_index[e["case_id"]] for e in ordered_examples]
    independent = [(e, p) for e, p in zip(ordered_examples, ordered_predictions) if independent_case(e)]
    result = {
        "schema_version": 1,
        "claim_status": "independently_reviewed_subset" if independent else "diagnostic_only",
        "independence_basis": "Supplied provenance declarations; external review was not audited by this tool.",
        "claims_not_measured": ["national_completeness", "source_freshness", "carrier_deliverability"],
        "leakage_check": {"training_records_supplied": training_records is not None,
                          "training_records": len(training_index),
                          "case_id_overlap": 0, "equivalence_group_overlap": 0,
                          "evaluation_cases_with_equivalence_group": sum("equivalence_group" in e for e in examples),
                          "scope": "Supplied IDs/groups only; absent or undeclared training data cannot be checked."},
        "diagnostic_metrics": grouped_scores(ordered_examples, ordered_predictions),
        "independently_reviewed_cases": len(independent),
    }
    if independent:
        result["independent_metrics"] = grouped_scores([e for e, _ in independent],
                                                       [p for _, p in independent])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--examples", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--training-records", type=Path)
    args = parser.parse_args()
    try:
        report = evaluate(load_jsonl(args.examples), load_jsonl(args.predictions),
                          load_jsonl(args.training_records) if args.training_records else None)
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f"address evaluation failed: {error}\n")


if __name__ == "__main__":
    main()
