"""Replay one source-derived positive and one incompatible locality per covered territory."""

from collections import defaultdict
import json
from pathlib import Path
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from localities.postal import iter_postal_records, load_sources
from localities.postal_places import ELIGIBLE_KINDS, validate_postal_places


def check():
    samples = {}
    same_code_names = defaultdict(set)
    other_places = defaultdict(dict)
    for source in load_sources()["sources"]:
        if source["format"] != "geonames_tsv_zip" or not source.get("active_for_lookup", True):
            continue
        for row in iter_postal_records(source):
            name = row["place_name"]
            if not name or row["code_kind"] not in ELIGIBLE_KINDS:
                continue
            cc, code = row["country_code"], row["code"]
            if cc not in samples:
                samples[cc] = {"country": cc, "code": code, "locality": name}
            folded = unicodedata.normalize("NFC", name.strip()).lower()
            if code == samples[cc]["code"]:
                same_code_names[cc].add(folded)
            elif len(other_places[cc]) < 32:
                other_places[cc][folded] = name

    queries = []
    synthetic = []
    for cc, sample in sorted(samples.items()):
        negative = next((name for key, name in other_places[cc].items() if key not in same_code_names[cc]), None)
        if negative is None:
            negative = "__negative_control_unlisted_locality__"
            synthetic.append(cc)
        queries.extend([sample, dict(sample, locality=negative)])
    public = json.loads((ROOT / "evaluation/postal-places/public-examples.json").read_text(encoding="utf-8"))
    results = validate_postal_places(queries + public, limit=1)
    public_results = results[len(queries):]
    public_failures = [r["country"] for r in public_results if r["status"] != "matched"]
    results = results[:len(queries)]
    failures = []
    ambiguous = []
    for good, bad in zip(results[::2], results[1::2]):
        if (good["status"] not in {"matched", "ambiguous"} or not good["matching_rows"]
                or bad["status"] not in {"no_match_in_source", "insufficient_evidence"}
                or bad["matching_rows"] or bad["postcode_rows"] != good["postcode_rows"]):
            failures.append(good["country"])
        if good["status"] == "ambiguous":
            ambiguous.append(good["country"])
    return {"scope": "pinned source replay with incompatible locality controls", "countries": sorted(samples),
            "country_count": len(samples), "checks": len(queries), "synthetic_negative_countries": synthetic,
            "other_observed_locality_controls": len(samples) - len(synthetic),
            "ambiguous_positives": ambiguous, "failures": failures,
            "public_examples": len(public_results), "public_example_failures": public_failures}


if __name__ == "__main__":
    summary = check()
    print(json.dumps(summary, indent=2))
    sys.exit(1 if summary["failures"] or summary["public_example_failures"] or not summary["public_examples"] or not summary["country_count"] else 0)
