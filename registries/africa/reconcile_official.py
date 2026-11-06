#!/usr/bin/env python3
"""Create *unapproved* official-to-GeoNames candidate links for Africa.

Source records are never modified. A matching name is never considered a
certified administrative identity or proof that a place can receive mail.
"""
import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from build import ROOT, read_csv


def normalize_name(value):
    """Conservative normalisation: do not discard diacritics or transliterate."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def build_candidates(official_rows, registry_rows, verified_parents=None):
    """Compare source IDs with names, levels and optional reviewed parent map.

    Required official columns: official_id, name, admin_level, parent_official_id.
    The parent map must be independently reviewed before use. All output links
    are explicitly marked unapproved, including exact unique matches.
    """
    parents = verified_parents or {}
    index = defaultdict(dict)
    for record in registry_rows:
        if record.get("kind") != "admin_subdivision":
            continue
        level = record.get("admin_level", "")
        if level not in {"1", "2", "3", "4", "5"}:
            continue
        for label in (record.get("name", ""), record.get("asciiname", "")):
            key = normalize_name(label)
            if key:
                index[(level, key)][record["id"]] = record

    result, seen = [], set()
    for row in official_rows:
        official_id = row.get("official_id", "").strip()
        name = row.get("name", "").strip()
        level = row.get("admin_level", "").strip()
        parent = row.get("parent_official_id", "").strip()
        if not official_id or not name or level not in {"1", "2", "3", "4", "5"}:
            raise ValueError("official rows require official_id, name and admin_level 1..5")
        if official_id in seen:
            raise ValueError("duplicate official_id: " + official_id)
        seen.add(official_id)
        if level == "1" and parent:
            raise ValueError("ADM1 must not have parent_official_id")
        names = [name]
        aliases = row.get("aliases", "")
        if aliases:
            names.extend(x.strip() for x in aliases.split("|") if x.strip())
        candidates = {}
        for label in names:
            candidates.update(index.get((level, normalize_name(label)), {}))
        scope = "country_only"
        if level != "1":
            if parent and parent in parents:
                scope = "verified_parent"
                candidates = {gid: rec for gid, rec in candidates.items()
                              if rec.get("parent_id") == parents[parent]}
            else:
                scope = "parent_not_verified"
        ids = sorted(candidates)
        if not ids:
            status = "no_exact_name_candidate"
        elif len(ids) > 1:
            status = "ambiguous_candidates"
        elif scope == "verified_parent":
            status = "unique_parent_scoped_candidate"
        elif scope == "parent_not_verified":
            status = "unique_name_but_parent_unverified"
        else:
            status = "unique_country_scoped_candidate"
        result.append({
            "official_id": official_id,
            "official_name": name,
            "official_level": int(level),
            "official_parent_id": parent or None,
            "scope": scope,
            "status": status,
            "candidate_geonames_ids": ids,
            "approved": False,
        })
    return result


def compare(country, official_path, verified_parent_map=None):
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("country must be a two-letter ISO-style code")
    source = ROOT / "countries" / country / "entities.csv.gz"
    if not source.exists():
        raise FileNotFoundError(f"{country} snapshot unavailable: restore and verify the pinned original first")
    with Path(official_path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or not {
            "official_id", "name", "admin_level", "parent_official_id"
        }.issubset(reader.fieldnames):
            raise ValueError("official CSV requires official_id,name,admin_level,parent_official_id")
        official_rows = list(reader)
    parent_map = {}
    if verified_parent_map:
        parent_map = json.loads(Path(verified_parent_map).read_text(encoding="utf-8"))
        if not isinstance(parent_map, dict) or not all(
            isinstance(k, str) and isinstance(v, str) and v.startswith("gn:")
            for k, v in parent_map.items()
        ):
            raise ValueError("parent map must be official-ID -> verified gn:ID string")
    result = build_candidates(official_rows, read_csv(source), parent_map)
    return {
        "country": country,
        "official_records_checked": len(result),
        "status": "candidate_review_only",
        "automatic_parent_assignment": False,
        "source_postal_address_validated": False,
        "approved_crosswalks": 0,
        "counts": dict(sorted(Counter(r["status"] for r in result).items())),
        "rows": result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", required=True)
    parser.add_argument("--official-csv", type=Path, required=True)
    parser.add_argument("--verified-parent-map", type=Path,
                        help="JSON official parent ID -> manually verified GeoNames parent ID")
    parser.add_argument("--source-url", required=True, help="Exact URL for provenance; never auto-fetched")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = compare(args.country, args.official_csv, args.verified_parent_map)
    report["official_source_url"] = args.source_url
    report["official_source_file"] = str(args.official_csv)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "country": args.country, "review_file": str(args.out),
        "counts": report["counts"], "approved_crosswalks": 0
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
