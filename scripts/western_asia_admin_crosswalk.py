#!/usr/bin/env python3
"""Source-preserving official-name vs GeoNames candidate review. No auto verification."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "registries/official/western-asia/admin-crosswalk/source_names.json"
ASIA = ROOT / "registries/asia"
COUNTRIES = ("SA", "BH", "QA", "OM", "PS")
PS_GEO_GROUPS = {"West Bank": ("gn:285153", "West Bank"),
                 "Gaza Strip": ("gn:281132", "Gaza Strip")}
POSTAL_SCHEMES = {
    "SA": {"SPL5": r"[0-9]{5}"},
    "BH": {"BH3_4": r"[0-9]{3,4}"},
    "QA": {"ANWANI_ZSB_NOT_POSTCODE": r"[0-9]+/[0-9]+/[0-9]+"},
    "OM": {"OM_POST_OFFICE3": r"[0-9]{3}"},
    "PS": {"P3_AREA": r"P[0-9]{3}", "P7_POINT": r"P[0-9]{7}"},
}

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def normalize(text: str) -> str:
    # No script conversion, Arabic decomposition, transliteration, or suffix stripping.
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())

def load_reference(path: Path = DATA) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or set(data["countries"]) != set(COUNTRIES):
        raise ValueError("Unsupported official reference scope")
    if data.get("national_completeness_verified") is not False or data.get("postal_assignment_verified") is not False:
        raise ValueError("Unverified source cannot be marked complete")
    for country, entry in data["countries"].items():
        if not entry["url"].startswith("https://") or entry["level"] not in (1, 2):
            raise ValueError("Bad provenance or administrative level")
        if entry["postal_source"]["records_imported"] != 0:
            raise ValueError("Postal source records not yet imported")
        keys = set()
        for name in entry["records"]:
            if not name["ref"].startswith(country + ":") or not name["name"]:
                raise ValueError("Invalid official reference row")
            if name["ref"] in keys:
                raise ValueError("Duplicate source reference key")
            keys.add(name["ref"])
            if name["parent"] and name["parent"] not in PS_GEO_GROUPS:
                raise ValueError("Unknown geopolitical grouping in excerpt")
    return data

def load_geo(country: str, registry: Path = ASIA) -> tuple[list[dict], dict]:
    if country not in COUNTRIES:
        raise ValueError("Country outside crosswalk scope")
    inventory = json.loads((registry / "archives.json").read_text(encoding="utf-8"))
    matches = [item for item in inventory["archives"] if item["country"] == country]
    if len(matches) != 1:
        raise ValueError("Missing or ambiguous country archive")
    spec = matches[0]
    if spec["path"] != "country-archives/" + country + ".zip":
        raise ValueError("Unexpected country archive path")
    blobs = []
    for index, part in enumerate(spec["parts"], 1):
        expected = spec["path"] if len(spec["parts"]) == 1 else spec["path"] + ".part%03d" % index
        if part["path"] != expected:
            raise ValueError("Archive part path mismatch")
        piece = (registry / expected).read_bytes()
        if len(piece) != part["bytes"] or digest(piece) != part["sha256"]:
            raise ValueError("Archive part checksum mismatch")
        blobs.append(piece)
    if not blobs:
        raise ValueError("No source archive parts")
    packed = b"".join(blobs)
    if len(packed) != spec["bytes"] or digest(packed) != spec["sha256"]:
        raise ValueError("Archive checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(packed)) as archive:
        if set(archive.namelist()) != set(spec["members"]):
            raise ValueError("Unexpected archive member set")
        member = country + "/entities.csv.gz"
        raw = archive.read(member)
        if digest(raw) != spec["members"][member]["sha256"]:
            raise ValueError("Entity member checksum mismatch")
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(raw).decode("utf-8"))))
    needed = {"id", "kind", "admin_level", "name", "asciiname", "alternatenames",
              "state_id", "country_code", "feature_code"}
    if not rows or not needed.issubset(rows[0]) or len(rows) != spec["rows"]:
        raise ValueError("Invalid gazetteer schema or row count")
    if len({x["id"] for x in rows}) != len(rows):
        raise ValueError("Duplicate GeoNames IDs")
    if any(x["country_code"] != country or not re.fullmatch(r"gn:[1-9][0-9]*", x["id"]) for x in rows):
        raise ValueError("Unexpected GeoNames ID or country")
    return rows, {"archive_sha256": spec["sha256"], "geonames_records": len(rows)}

def propose(country: str, geo: list[dict], references: dict) -> list[dict]:
    spec = references["countries"][country]
    admin_level = str(spec["level"])
    candidates = [r for r in geo if r["admin_level"] == admin_level
                  and r["feature_code"] == "ADM" + admin_level]
    if country == "PS":
        lookup = {r["id"]: r["name"] for r in geo}
        for group, (gid, expected_name) in PS_GEO_GROUPS.items():
            if lookup.get(gid) != expected_name:
                raise ValueError("GeoNames West Bank/Gaza parent guard changed: " + group)
    output = []
    for official in spec["records"]:
        name = normalize(official["name"])
        aliases = {normalize(alias) for alias in official["aliases"]}
        exact, alternative = [], []
        for r in candidates:
            if official["parent"] and r["state_id"] != PS_GEO_GROUPS[official["parent"]][0]:
                continue
            base = {normalize(r["name"]), normalize(r["asciiname"])}
            if name in base:
                exact.append(r["id"])
            else:
                # GeoNames alternate names are unlabelled and never official evidence.
                unlabelled = {normalize(item) for item in r["alternatenames"].split(",") if item}
                if name in unlabelled or aliases.intersection(base | unlabelled):
                    alternative.append(r["id"])
        matched = sorted(set(exact if exact else alternative))
        status = ("unmatched" if not matched else "unique_candidate" if len(matched) == 1
                  else "ambiguous_candidates")
        output.append({
            "country": country, "official_ref": official["ref"],
            "official_name": official["name"],
            "source_url": spec["url"], "reference_date": spec["date"],
            "geonames_admin_level": spec["level"],
            "geographic_parent": official["parent"] or None,
            "status": status,
            "match_kind": "exact_name" if exact else "alias_unverified" if matched else None,
            "candidate_geonames_ids": matched,
            "reviewed_identity_verified": False,
            "postal_assignment_verified": False,
        })
    return output

def report(country: str, *, reference: dict | None = None, registry: Path = ASIA) -> dict:
    if country not in COUNTRIES:
        raise ValueError("Unknown country")
    reference = reference or load_reference()
    rows, summary = load_geo(country, registry)
    results = propose(country, rows, reference)
    counts = Counter(result["status"] for result in results)
    return {
        "country": country, **summary,
        "official_source": reference["countries"][country]["publisher"],
        "source_date": reference["countries"][country]["date"],
        "official_names_compared": len(results),
        "unique_candidates_unreviewed": counts["unique_candidate"],
        "ambiguous_candidates_unreviewed": counts["ambiguous_candidates"],
        "official_names_unmatched": counts["unmatched"],
        "localities_without_adm1": sum(x["kind"] == "locality" and not x["state_id"] for x in rows),
        "verified_identity_links": 0,
        "postal_reference_records_imported": 0,
        "verified_postal_geonames_links": 0,
        "national_completeness_verified": False,
        "deliverability_verified": False,
        "candidates": results,
    }


def inspect_pcbs_locality_code(code: str, *, reference: dict | None = None) -> dict:
    """Decode 1999 PCBS six-digit statistical locality code. NOT a postcode.

    A valid format and governorate prefix do NOT prove the locality was assigned
    this code; that requires the authoritative locality dataset and source date.
    """
    if not isinstance(code, str):
        raise TypeError("PCBS locality code must be a string")
    if not re.fullmatch(r"[0-9]{6}", code):
        raise ValueError("PCBS locality code must be 6 ASCII digits")
    source = (reference or load_reference())["countries"]["PS"]
    table = {item["governorate_code"]: item for item in source["records"]}
    if len(table) != 16:
        raise ValueError("PCBS governorate code inventory is incomplete or duplicated")
    prefix = code[:2]
    row = table.get(prefix)
    return {
        "input_code": code,
        "scheme": "PCBS-locality6-1999",
        "governorate_code": prefix,
        "governorate_name": row["name"] if row else None,
        "governorate_ref": row["ref"] if row else None,
        "status": "known_governorate_prefix_format_only" if row else "unrecognized_governorate_prefix",
        "source_url": source["governorate_code_source"]["url"],
        "locality_assignment_verified": False,
        "geonames_identity_verified": False,
        "postal_code_verified": False,
        "deliverability_verified": False,
        "note": "PCBS statistical locality code is NOT a Palestine P3/P7 postal code.",
    }

def postal_audit(path: Path, *, country: str, expected_sha256: str,
                 source_url: str, licence: str, source_version: str,
                 reference: dict | None = None) -> dict:
    """Examine an explicitly sourced CSV but never create postal-to-GeoNames links."""
    if country not in COUNTRIES or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Valid country and pinned hex SHA-256 required")
    if not source_url.startswith("https://") or not licence or not source_version:
        raise ValueError("Source URL, licence, version required")
    binary = path.read_bytes()
    if digest(binary) != expected_sha256:
        raise ValueError("Postal CSV differs from pinned content")
    csv_rows = list(csv.DictReader(io.StringIO(binary.decode("utf-8-sig"))))
    if not csv_rows or not {"official_ref", "scheme", "code"}.issubset(csv_rows[0]):
        raise ValueError("Bad postal source schema")
    ids = {s["ref"] for s in (reference or load_reference())["countries"][country]["records"]}
    outcomes = []
    counts = Counter()
    for row in csv_rows:
        scheme, code, ref = row["scheme"], row["code"], row["official_ref"]
        if scheme not in POSTAL_SCHEMES[country] or not re.fullmatch(POSTAL_SCHEMES[country][scheme], code):
            status = "invalid_format"
        elif ref not in ids:
            status = "unresolved_admin_ref"
        else:
            status = "admin_association_candidate"
        counts[status] += 1
        outcomes.append({"official_ref": ref, "scheme": scheme, "code": code,
                         "status": status, "geonames_id": None})
    return {
        "country": country, "sha256": expected_sha256, "source_url": source_url,
        "licence": licence, "source_version": source_version, "source_rows": len(csv_rows),
        "outcomes": outcomes, "status_counts": dict(sorted(counts.items())),
        "verified_postal_geonames_links": 0, "deliverability_verified": False
    }

def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("report", "postal-audit"))
    p.add_argument("--country", choices=(*COUNTRIES, "all"), default="all")
    p.add_argument("--output", type=Path)
    p.add_argument("--postal-csv", type=Path)
    p.add_argument("--sha256")
    p.add_argument("--source-url")
    p.add_argument("--licence")
    p.add_argument("--source-version")
    args = p.parse_args()
    if args.command == "report":
        entries = [report(cc) for cc in (COUNTRIES if args.country == "all" else (args.country,))]
        payload = {"schema_version": 1, "countries": entries,
                   "total_official_names": sum(r["official_names_compared"] for r in entries),
                   "total_unreviewed_unique_candidates": sum(r["unique_candidates_unreviewed"] for r in entries),
                   "verified_identity_links": 0, "verified_postal_geonames_links": 0}
    else:
        if args.country == "all" or not args.postal_csv:
            p.error("postal-audit requires --country and --postal-csv")
        payload = postal_audit(args.postal_csv, country=args.country,
                              expected_sha256=args.sha256 or "",
                              source_url=args.source_url or "",
                              licence=args.licence or "", source_version=args.source_version or "")
    output = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")

if __name__ == "__main__":
    main()
