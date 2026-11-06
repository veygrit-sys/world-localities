#!/usr/bin/env python3
"""Audit source-traceable first-level administrative name crosswalk candidates.

Reads *real, manually transcribed* official authorities in official-references
and original GeoNames admin1 projections. Does not mutate GeoNames data or
approve candidate mappings, does not certify administrative boundaries.
"""
import argparse
import csv
import json
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CODES = ("ZA", "NG", "KE", "GH")
EXPECTED = {"ZA": 9, "NG": 37, "KE": 47, "GH": 16}

# Deliberately explicit review-only aliases, not automatic fuzzy matching.
CURATED_LABELS = {
    "KE": {
        "Tharaka Nithi": "Tharaka - Nithi",
        "Elgeyo Marakwet": "Elegeyo-Marakwet",
    },
    "GH": {
        "Western": "Western Region",
        "Volta": "Volta Region",
        "Upper West": "Upper West Region",
        "Upper East": "Upper East Region",
        "Northern": "Northern Region",
        "Greater Accra": "Greater Accra Region",
        "Eastern": "Eastern Region",
        "Central": "Central Region",
        "Ashanti": "Ashanti Region",
    },
}


def norm(name):
    # Keep diacritics and spelling distinctions. Never confuse fuzzy names
    # with verified official geographic identities.
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        yield from csv.DictReader(stream)


def compare_country(code, root=ROOT):
    if code not in CODES:
        raise ValueError("country not in approved first wave")
    source_path = root / "official-references" / (code + "-adm1-source-names.csv")
    official = list(rows(source_path))
    if len(official) != EXPECTED[code]:
        raise ValueError(f"{code}: expected {EXPECTED[code]} official top-level source names, got {len(official)}")
    seq = [r["source_sequence"] for r in official]
    if len(set(seq)) != len(seq):
        raise ValueError(code + ": source sequence duplicates")
    gaz_path = root / "countries" / code / "admin1.csv"
    indexes = defaultdict(dict)
    if gaz_path.is_file():
        for entry in rows(gaz_path):
            if entry["kind"] != "admin_subdivision" or entry["admin_level"] != "1":
                raise ValueError(code + ": unexpected GeoNames ADM1 feature")
            indexes[norm(entry["name"])][entry["id"]] = entry
    output = []
    for entry in official:
        name = entry["official_name"]
        candidates = indexes.get(norm(name), {})
        method = "literal_name"
        if not candidates and name in CURATED_LABELS.get(code, {}):
            candidates = indexes.get(norm(CURATED_LABELS[code][name]), {})
            method = "explicit_review_alias"
        ids = sorted(candidates)
        if not gaz_path.exists():
            status = "source_snapshot_not_migrated"
            method = "no_source_snapshot"
        elif not ids:
            status = "name_not_found"
        elif len(ids) > 1:
            status = "ambiguous_candidates"
        elif method == "explicit_review_alias":
            status = "curated_alias_candidate"
        else:
            status = "exact_name_candidate"
        output.append({
            "country": code,
            "source_sequence": entry["source_sequence"],
            "source_code_type": entry["source_code_type"],
            "official_name": name,
            "source_vintage": entry["source_vintage"],
            "official_source_url": entry["official_source_url"],
            "candidate_geonames_ids": ids,
            "status": status,
            "method": method,
            "approved": False,
        })
    return output


def report(root=ROOT):
    country_rows = {code: compare_country(code, root) for code in CODES}
    return {
        "purpose": "review-only first-level administrative candidates",
        "official_source_records": sum(map(len, country_rows.values())),
        "certified_matches": 0,
        "original_geonames_modified": False,
        "country_results": {
            code: {"source_records": len(recs),
                   "counts": dict(sorted(Counter(r["status"] for r in recs).items())),
                   "records": recs}
            for code, recs in country_rows.items()
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the full report to this local path")
    parser.add_argument("--check", action="store_true", help="Check expected official record counts and unique identity candidates")
    args = parser.parse_args()
    result = report()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({code: country["counts"] for code, country in result["country_results"].items()},
                     ensure_ascii=False, sort_keys=True))
    if args.check:
        for code, value in result["country_results"].items():
            if value["counts"].get("ambiguous_candidates", 0):
                raise SystemExit(code + ": ambiguous exact/alias candidate")
            if value["counts"].get("name_not_found", 0):
                raise SystemExit(code + ": official ADM1 name absent from GeoNames; manual triage required")


if __name__ == "__main__":
    main()
