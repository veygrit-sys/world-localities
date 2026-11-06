#!/usr/bin/env python3
"""Audit official Azerbaijan economic-region member labels against GeoNames ADM1.

The 14 economic regions are statistical groupings, not an alternative set of
GeoNames ADM1 codes or statutory district IDs. All name links are review-only.
Works offline with pinned, SHA256-verified source ZIPs; no bulk official data claim.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "registries/official/western-asia/caucasus-levant/azerbaijan-statistical-regions-2026.json"
sys.path.insert(0, str(ROOT / "scripts"))
from western_asia_caucasus_levant_join import load_gazetteer

TRANSLIT = {"ə": "a", "ğ": "gh", "ı": "i", "ş": "sh", "ç": "ch",
            "ö": "o", "ü": "u", "x": "kh", "c": "j"}
KINDS = frozenset({"rayon", "city", "autonomous_republic"})


def name_key(value: str) -> str:
    """Loose Latin search key, not an official translation or identity mapping."""
    value = unicodedata.normalize("NFC", value.strip().casefold())
    for before, after in TRANSLIT.items():
        value = value.replace(before, after)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^a-z0-9 ]+", " ", value).split())


def base_name(value: str) -> str:
    parts = name_key(value).split()
    while parts and parts[-1] in {"rayon", "rayonu", "district", "city",
                                   "sahari", "shahari", "municipality"}:
        parts.pop()
    return " ".join(parts)


def read_source(path: Path = SOURCE) -> dict:
    source = json.loads(path.read_text(encoding="utf-8"))
    if source.get("schema_version") != 1 or source.get("country") != "AZ":
        raise ValueError("Unexpected Azerbaijan official-name source")
    if source.get("original_webpage_bytes_downloaded") is not False:
        raise ValueError("Manual transcription cannot be presented as original source")
    groups = source.get("economic_regions", ())
    if len(groups) != 14 or sum(len(x["members"]) for x in groups) != 68:
        raise ValueError("Azerbaijan name excerpt has unexpected number of members")
    all_refs = set()
    for group in groups:
        if group.get("classification") != "economic_reporting_region_not_administrative_parent_id":
            raise ValueError("Economic region must not be treated as ADM1")
        for member in group["members"]:
            key = member["ref"]
            if key in all_refs or member["unit_kind"] not in KINDS:
                raise ValueError("Duplicate name reference / unknown unit kind")
            all_refs.add(key)
            if member["source_economic_region"] != group["name_az"]:
                raise ValueError("Source economic region differs")
            if member.get("geonames_id") is not None or member.get("postal_code") is not None:
                raise ValueError("An unreviewed source cannot assert GN/postcode")
            if member.get("accepted_id_crosswalk") is not False:
                raise ValueError("Government ID crosswalk has not been verified")
    return source


def guess_type(name: str) -> str:
    """Textual hint only; a legal class still requires independent verification."""
    n = name_key(name)
    if "autonomous republic" in n:
        return "autonomous_republic"
    if re.search(r"\b(city|sahari|shahari)\b", n):
        return "city"
    if re.search(r"\b(rayon|district)\b", n):
        return "rayon"
    return "unclassified"


def candidates_for(item: dict, adm1: list[dict]) -> dict:
    target = name_key(item["name_az"])
    kind = item["unit_kind"]
    direct, weak = set(), set()
    for record in adm1:
        if record["admin_level"] != "1" or record["feature_code"] != "ADM1":
            continue
        observed_type = guess_type(record["name"])
        if observed_type not in (kind, "unclassified"):
            continue
        primary = {base_name(record["name"]), base_name(record["asciiname"])}
        alt = {base_name(v) for v in record.get("alternatenames", "").split(",") if v}
        if target in primary:
            bucket = direct
        elif target in alt:
            bucket = weak
        else:
            continue
        bucket.add((record["id"], observed_type))
    matches = direct if direct else weak
    # A typed administrative match is stronger than an unclassified name.
    typed = {gid for gid, category in matches if category == kind}
    ids = sorted(typed if typed else (gid for gid, _ in matches))
    if not ids:
        status = "unmatched"
    elif len(ids) == 1:
        status = "unique_unreviewed_candidate"
    else:
        status = "ambiguous_candidates"
    return {"source_ref": item["ref"], "name_az": item["name_az"],
            "unit_kind": kind, "economic_region": item["source_economic_region"],
            "geonames_candidates": ids, "status": status,
            "name_match_method": "normalized_name" if direct else
                                 "geo_alternate_name" if weak else None,
            "type_inferred_from_name_only": True,
            "verified_official_gn_identity": False,
            "verified_official_postcode_assignment": False}


def report(*, source: dict | None = None, geonames: list[dict] | None = None) -> dict:
    source = source or read_source()
    if geonames is None:
        geonames, meta = load_gazetteer("AZ")
    else:
        meta = {"source_rows": len(geonames), "archive_sha256": None}
    admin1 = [r for r in geonames if r["admin_level"] == "1" and r["feature_code"] == "ADM1"]
    out = [candidates_for(row, admin1)
           for group in source["economic_regions"] for row in group["members"]]
    counts = Counter(item["status"] for item in out)
    unique_gn = {id for row in out for id in row["geonames_candidates"]}
    return {"country": "AZ", **meta, "economic_reporting_regions": 14,
            "source_administrative_unit_labels": len(out),
            "geonames_adm1_in_snapshot": len(admin1),
            "unique_unreviewed_name_candidates": counts["unique_unreviewed_candidate"],
            "ambiguous_candidates": counts["ambiguous_candidates"],
            "unmatched_source_labels": counts["unmatched"],
            "geonames_adm1_without_name_candidate": len(admin1) - len(unique_gn),
            "original_official_geojson_downloaded": False,
            "verified_government_to_geonames_ids": 0,
            "verified_government_postcodes": 0,
            "candidate_records": out}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("report", "find"))
    ap.add_argument("--name")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    result = report()
    if args.command == "find":
        if not args.name:
            ap.error("--name is required")
        result = {"query": args.name,
                  "candidates": [r for r in result["candidate_records"]
                                 if name_key(r["name_az"]) == name_key(args.name)],
                  "no_candidate_is_not_proof_of_nonexistence": True}
    dump = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(exist_ok=True, parents=True)
        args.output.write_text(dump, encoding="utf-8")
    else:
        print(dump, end="")


if __name__ == "__main__":
    main()
