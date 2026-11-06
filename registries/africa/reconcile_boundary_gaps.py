#!/usr/bin/env python3
"""Produce reviewable spatial links for KE/GH GeoNames unresolved parents.

Does not certify a legal administrative parent, update GeoNames or infer
missing GeoNames ADM identifiers. Shapes carry vintages from gbOpen.
"""
import argparse
import csv
import json
from pathlib import Path
from shapely.geometry import Point

from import_pinned_boundary_units import generate
from triage_unresolved import triage, ROOT

HEADERS = ("country", "geonames_id", "geonames_name", "geonames_feature",
           "unresolved_reason", "original_adm_codes", "existing_state_geonames_id",
           "latitude", "longitude", "spatial_adm1_id", "spatial_adm1_name",
           "spatial_adm2_id", "spatial_adm2_name",
           "same_state_name_in_spatial_source", "adm2_name_matches_geonames",
           "finding", "approved_administrative_parent", "source_license",
           "source_geoboundaries_release")

def norm(s):
    return " ".join(str(s).casefold().replace("’", "'").split())

def coarse_name(s, country):
    n = norm(s)
    if country == "GH" and n.endswith(" region"):
        return n[:-7]
    return n

def load_states(country, root=ROOT):
    states = {}
    with (root / "countries" / country / "admin1.csv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row["admin_level"] == "1":
                states[row["id"]] = row["name"]
    return states

def spatial_cases(records, root=ROOT):
    outcome = []
    for iso, code in (("KEN", "KE"), ("GHA", "GH")):
        state_names = load_states(code, root)
        areas1, areas2 = records[(iso, "ADM1")], records[(iso, "ADM2")]
        source = triage(code, root)
        if not source["source_present"]:
            raise ValueError(f"{code}: existing source snapshot missing")
        for case in source["cases"]:
            point = Point(float(case["longitude"]), float(case["latitude"]))
            top = [r for r in areas1 if r["geometry"].covers(point)]
            level2 = [r for r in areas2 if r["geometry"].covers(point)]
            top_item = top[0] if len(top) == 1 else None
            l2_item = level2[0] if len(level2) == 1 else None
            source_state = state_names.get(case["state_id"])
            same_state = bool(top_item and source_state and
                              coarse_name(top_item["name"], code) == coarse_name(source_state, code))
            l2_in_state = bool(l2_item and top_item and l2_item["parent_id"] == top_item["shapeID"])
            name_match = bool(l2_item and coarse_name(case["name"], code) ==
                              coarse_name(l2_item["name"], code))
            if not top_item or not l2_item:
                finding = "no_unique_spatial_area"
            elif not l2_in_state:
                finding = "spatial_sources_parent_disagree"
            elif case["state_id"] and not same_state:
                finding = "source_state_conflicts_with_spatial_area"
            elif not case["state_id"]:
                finding = "spatial_candidate_missing_source_state"
            elif name_match and case["record_type"] == "admin_subdivision":
                finding = "name_and_spatial_area_candidate"
            else:
                finding = "spatial_area_candidate_only"
            outcome.append({
                "country": code,
                "geonames_id": case["id"],
                "geonames_name": case["name"],
                "geonames_feature": case["feature_code"],
                "unresolved_reason": case["relation"],
                "original_adm_codes": "/".join(case["adm_codes"]),
                "existing_state_geonames_id": case["state_id"] or "",
                "latitude": case["latitude"], "longitude": case["longitude"],
                "spatial_adm1_id": top_item["shapeID"] if top_item else "",
                "spatial_adm1_name": top_item["name"] if top_item else "",
                "spatial_adm2_id": l2_item["shapeID"] if l2_item else "",
                "spatial_adm2_name": l2_item["name"] if l2_item else "",
                "same_state_name_in_spatial_source": str(same_state).lower(),
                "adm2_name_matches_geonames": str(name_match).lower(),
                "finding": finding, "approved_administrative_parent": "false",
                "source_license": "CC BY 3.0 IGO" if code == "KE" else "CC BY 4.0",
                "source_geoboundaries_release": "9469f09",
            })
    if sum(r["country"] == "KE" for r in outcome) != 69:
        raise ValueError("Kenya pinned 69-parent gap baseline changed")
    if sum(r["country"] == "GH" for r in outcome) != 11:
        raise ValueError("Ghana pinned 11-parent gap baseline changed")
    return sorted(outcome, key=lambda r:(r["country"],r["geonames_id"]))

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, default=ROOT / ".cache/gb-pinned")
    p.add_argument("--output", type=Path, default=ROOT / "reference-boundaries")
    args = p.parse_args()
    records, source = generate(args.cache, args.output)
    rows = spatial_cases(records)
    args.output.mkdir(parents=True, exist_ok=True)
    with (args.output / "unresolved-spatial-review.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    import collections
    counts = {code:dict(sorted(collections.Counter(
             r["finding"] for r in rows if r["country"]==code).items())) for code in ("KE","GH")}
    report = {
        "schema_version":1, "input_unresolved_cases": {"KE":69,"GH":11},
        "approved_administrative_parent_links":0,
        "original_geonames_changed":False,
        "only_spatial_candidates_reviewed":True,
        "counts":counts, "sources":source,
        "warning":"A point within a 2019/2020 statistical/election boundary does not repair a missing GeoNames code or confirm present-day national legal administration. Independently verify original official source IDs and hierarchy before approving.",
    }
    (args.output / "unresolved-spatial-summary.json").write_text(
        json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="sources"},ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
