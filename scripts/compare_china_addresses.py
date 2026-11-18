"""Compare scoped CN requests offline with optional normalized provider predictions."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import render_bilingual_address, validate_china_address
from addressing.china_subdivisions import subdivision_catalog
from scripts.evaluate_addresses import evaluate, index_records, load_jsonl, nonempty, require

CASES = ROOT / "evaluation" / "china"
ADMIN_LEVEL = {"state": "province", "city": "city", "city_district": "area"}
TRANSLATABLE = {"state", "city", "city_district", "road"}


def input_digest(request):
    encoded = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_request(request):
    require(request.get("country") == "CN" and request.get("source_language") == "zh-Hans",
            "expected mainland CN and zh-Hans input")
    task = request.get("task")
    require(task in {"component_translation", "component_validation"}, "unsupported CN task")
    translation = task == "component_translation"
    require(request.get("target_language") == ("en" if translation else "zh-Hans"),
            "unsupported target language for task")
    components = request.get("components")
    require(isinstance(components, dict) and all(nonempty(k) and nonempty(v) for k, v in components.items()),
            "input components must contain nonempty strings")
    fields = request.get("fields")
    allowed = TRANSLATABLE if translation else ADMIN_LEVEL.keys()
    require(isinstance(fields, list) and fields
            and all(isinstance(f, str) and f in allowed and f in components for f in fields)
            and len(fields) == len(set(fields)), "invalid requested fields")


def local_prediction(request, label_version):
    fields = request["fields"]
    if request["task"] == "component_translation":
        result = render_bilingual_address(request["components"], "CN", strict=False)
        # Accept only an explicit English label supplied from the named data source.
        labels = {e["component"]: e["value"] for e in result.label_evidence if e["language"] == "en"}
        answer = {"verdict": "abstain"}
        if all(field in labels for field in fields):
            answer = {"verdict": "matched", "components": {field: labels[field] for field in fields}}
        version = label_version
    else:
        result = validate_china_address(request["components"])
        admin = result["administrative"]
        answer = {"verdict": admin["status"]}
        if admin["status"] == "matched":
            chain = admin["candidates"][0]
            target = {}
            for field in fields:
                level = ADMIN_LEVEL[field]
                # Municipalities can occur in the city input but resolve at province level.
                if field == "city" and request["components"][field].strip() == chain["province"]["name"]:
                    level = "province"
                target[field] = chain[level]["name"]
            answer["components"] = target
        elif admin["status"] not in {"no_match", "ambiguous"}:
            answer = {"verdict": "abstain"}
        version = result["source_version"]
    return {
        "case_id": request["case_id"], "country": "CN", "task": request["task"],
        "input_sha256": input_digest(request), "fields": fields,
        "provider": "world-localities", "data_version": version, **answer,
    }


def score_run(requests, expected, predictions):
    inputs = index_records(requests, "request")
    gold = index_records(expected, "expected")
    outputs = index_records(predictions, "prediction")
    require(inputs and inputs.keys() == gold.keys() == outputs.keys(),
            "request, expected and prediction IDs differ or are empty")
    providers = set()
    versions = {}
    for case_id, request in inputs.items():
        validate_request(request)
        prediction = outputs[case_id]
        reference = gold[case_id]
        digest = input_digest(request)
        require(reference.get("input_sha256") == prediction.get("input_sha256") == digest,
                f"input digest differs for {case_id}")
        require(prediction.get("fields") == request["fields"], f"prediction scope differs for {case_id}")
        require((reference.get("country"), reference.get("task")) == (request["country"], request["task"]),
                f"reference task or country differs for {case_id}")
        for target in (reference.get("expected"), prediction):
            require(isinstance(target, dict), f"missing target for {case_id}")
            if target.get("verdict") == "matched":
                components = target.get("components")
                require(isinstance(components, dict) and set(components) == set(request["fields"]),
                        f"accepted fields differ for {case_id}")
        provider, version = prediction.get("provider"), prediction.get("data_version")
        require(nonempty(provider) and nonempty(version), f"missing provider or data version for {case_id}")
        providers.add(provider)
        versions.setdefault(request["task"], set()).add(version)
    require(len(providers) == 1, "mixed providers in one run")
    return {"provider": next(iter(providers)), "data_versions": {k: sorted(v) for k, v in versions.items()},
            "evaluation": evaluate(expected, predictions)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=Path, default=CASES / "requests.jsonl")
    parser.add_argument("--expected", type=Path, default=CASES / "expected.jsonl")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--emit-local", action="store_true", help="print local prediction JSONL")
    mode.add_argument("--compare-with", type=Path, help="score an additional normalized prediction JSONL")
    args = parser.parse_args()
    try:
        requests = load_jsonl(args.requests)
        index_records(requests, "request")
        for request in requests:
            validate_request(request)
        label_version = "CLDR-" + subdivision_catalog()["release"]
        local = [local_prediction(r, label_version) for r in requests]
        if args.emit_local:
            for prediction in local:
                print(json.dumps(prediction, ensure_ascii=False))
            return
        expected = load_jsonl(args.expected)
        runs = [score_run(requests, expected, local)]
        if args.compare_with:
            runs.append(score_run(requests, expected, load_jsonl(args.compare_with)))
        print(json.dumps({"schema_version": 1, "runs": runs}, ensure_ascii=False, indent=2))
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(2, f"CN address comparison failed: {error}\n")


if __name__ == "__main__":
    main()
