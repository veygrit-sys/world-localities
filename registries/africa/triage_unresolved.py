#!/usr/bin/env python3
"""Extract exact GeoNames unresolved parent cases for Africa priority review.

The output contains original source IDs/codes and preserves null parent links.
No inferred administrative membership, no automatic GeoNames edits.
"""
import argparse
import csv
import gzip
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PARENT_GAPS = {"missing_code", "missing_reference", "ambiguous_code"}


def triage(country, root=ROOT):
    if country not in ("ZA", "NG", "KE", "GH"):
        raise ValueError("first-wave countries only")
    path = root / "countries" / country / "entities.csv.gz"
    if not path.is_file():
        return {"country": country, "source_present": False,
                "cases": [], "reason": "original_archive_not_migrated"}
    cases, missing_adm1, kinds = [], [], Counter()
    with gzip.open(path, "rt", encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            if row["parent_relation"] in PARENT_GAPS:
                case = {
                    "id": row["id"],
                    "name": row["name"],
                    "feature_code": row["feature_code"],
                    "record_type": row["kind"],
                    "relation": row["parent_relation"],
                    "adm_codes": [row.get(f"admin{n}_code", "") for n in range(1, 5)],
                    "state_id": row["state_id"] or None,
                    "state_relation": row["state_relation"],
                    "parent_id": None,
                    "official_reconciliation_status": "not_checked",
                    "allowed_fix": "source-backed, independently reviewed only",
                }
                if row["parent_id"]:
                    raise ValueError("unresolved source record has unexpected parent_id")
                cases.append(case)
                kinds[row["parent_relation"]] += 1
            if row["kind"] == "locality" and not row["state_id"]:
                missing_adm1.append({
                    "id": row["id"], "name": row["name"],
                    "feature_code": row["feature_code"],
                    "admin1_code": row["admin1_code"],
                    "state_relation": row["state_relation"],
                })
    cases.sort(key=lambda r: r["id"])
    missing_adm1.sort(key=lambda r: r["id"])
    return {
        "country": country,
        "source_present": True,
        "unresolved_parent_count": len(cases),
        "localities_without_adm1_count": len(missing_adm1),
        "parent_issue_categories": dict(sorted(kinds.items())),
        "cases": cases,
        "localities_without_adm1": missing_adm1,
        "auto_reparented_records": 0,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--country", required=True, choices=("ZA","NG","KE","GH"))
    p.add_argument("--output", type=Path)
    p.add_argument("--summary-only", action="store_true")
    args = p.parse_args()
    report = triage(args.country)
    output = report
    if args.summary_only and report["source_present"]:
        output = {k: v for k, v in report.items()
                  if k not in ("cases", "localities_without_adm1")}
    payload = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
