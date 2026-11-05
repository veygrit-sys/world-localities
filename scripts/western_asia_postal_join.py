#!/usr/bin/env python3
"""Join sourced *postal office/area facts* to candidate GeoNames localities.

A country postcode, post office, postal area and building ID are distinct grains.
Matches are review candidates, NEVER certified delivery or official GeoNames IDs.
Python 3.11+, standard library. Existing gazetteer archives are SHA256 checked.
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
sys.path.insert(0, str(ROOT / "scripts"))
import western_asia_admin_crosswalk as admin

EXCERPT = ROOT / "registries/official/western-asia/postal-data/official_excerpt.json"
SCOPE = ("SA", "BH", "QA", "OM", "PS")
PATTERNS = {
    "SA": ("SPL5_example", r"[0-9]{5}"),
    "BH": ("BH_postal_example", r"[0-9]{3,4}"),
    "OM": ("OM_post_office3", r"[0-9]{3}"),
    "PS": ("P3_area", r"P[0-9]{3}"),
}
ARABIC_RE = re.compile(r"[\u0621-\u064a]")
ARABIC_MARKS_RE = re.compile(r"[\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")
SPACE_RE = re.compile(r"\s+")
OM_AMBIGUOUS_GOV_LABELS = {"Al Sharqiyah North & South",
                           "Al Batinah North & South", "AL BATINA"}


def normalized_name(value: str, language: str) -> str:
    """Candidate search normalization only. Never an official translated name."""
    text = unicodedata.normalize("NFC", value).casefold().strip()
    if language == "ar":
        text = ARABIC_MARKS_RE.sub("", text)
        text = text.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا",
                                             "ٱ": "ا", "ى": "ي"}))
    return SPACE_RE.sub(" ", text)


def load_excerpt(path: Path = EXCERPT, *, administrative: dict | None = None) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or set(data.get("scope", ())) != set(SCOPE):
        raise ValueError("Unexpected postal excerpt schema or scope")
    if data.get("provenance_kind") != (
        "manual_factual_excerpt_of_public_official_webpages_not_original_source_file"
    ):
        raise ValueError("Missing source excerpt provenance")
    ref = administrative or admin.load_reference()
    sources = data["sources"]
    counts = Counter()
    seen_ids = set()
    for src_id, src in sources.items():
        if src["country"] not in SCOPE or not src["source_url"].startswith("https://"):
            raise ValueError("Invalid source country or HTTPS URL")
        if src["original_source_sha256"] is not None:
            raise ValueError("Cannot claim hash of a source HTML file not downloaded")
        if not src["license"] or not src["extract_type"]:
            raise ValueError("Source licence/reuse review and grain required")
    for row in data["records"]:
        cc = row["country"]
        if cc not in PATTERNS or row["source_id"] not in sources or sources[row["source_id"]]["country"] != cc:
            raise ValueError("Bad record source or country")
        scheme, pattern = PATTERNS[cc]
        if row["scheme"] != scheme or re.fullmatch(pattern, row["code"]) is None:
            raise ValueError("Country-specific official code syntax invalid")
        if row["record_id"] in seen_ids or not row["place_name"].strip():
            raise ValueError("Duplicate reference row ID or empty place")
        seen_ids.add(row["record_id"])
        if row["place_language"] not in {"en", "ar"} or (cc == "PS") != (row["place_language"] == "ar"):
            raise ValueError("Incorrect locale for source postal name")
        if cc == "OM" and row["evidence_role"] != "official_post_office_list":
            raise ValueError("Oman post-office grain must not be a city postal range")
        if cc == "PS" and row["evidence_role"] != "official_p3_area_town":
            raise ValueError("P3 area / P7 point codes must be kept separate")
        if cc in {"SA", "BH"} and "example" not in row["evidence_role"]:
            raise ValueError("Published examples must not be promoted to reference registry")
        official_ref = row.get("admin_ref")
        if official_ref and official_ref not in {item["ref"] for item in ref["countries"][cc]["records"]}:
            raise ValueError("Missing government reference: " + official_ref)
        if cc == "QA":
            raise ValueError("Qatar has no conventional national postcode table")
        counts[cc] += 1
    if counts != {"OM":37, "PS":45, "SA":1, "BH":2}:
        raise ValueError("Unexpected excerpt row loss / newly added unreviewed records")
    if data["quality"]["original_bulk_sources_downloaded"] != 0:
        raise ValueError("Original source HTML/CSV not acquired")
    if data["quality"]["geonames_join_verified"] is not False:
        raise ValueError("Unreviewed name hints cannot be certified")
    return data


def source_code_collisions(data: dict) -> dict[tuple[str, str, str], set[str]]:
    groups = defaultdict(set)
    for row in data["records"]:
        groups[(row["country"], row["scheme"], row["code"])].add(
            normalized_name(row["place_name"], row["place_language"])
        )
    return {key: values for key, values in groups.items() if len(values) > 1}


def _build_name_index(geo_rows: list[dict], languages: set[str]) -> dict:
    """Build each locale's index once, avoiding per-postcode whole-country scans."""
    idx = {language: defaultdict(dict) for language in languages}
    for row in geo_rows:
        if row["kind"] != "locality" or row["address_candidate"] != "1":
            continue
        strings = [row["name"], row["asciiname"]]
        if row["alternatenames"]:
            strings.extend(row["alternatenames"].split(","))
        for language, table in idx.items():
            for value in strings:
                if language == "ar" and not ARABIC_RE.search(value):
                    continue
                key = normalized_name(value, language)
                if key:
                    table[key][row["id"]] = row["state_id"]
    return idx


def _matches(index: dict, name: str, language: str,
             allowed_adm1: set[str] | None) -> list[str]:
    token = normalized_name(name, language)
    if not token:
        return []
    candidates = index[language].get(token, {})
    if allowed_adm1 is None:
        return sorted(candidates)
    return sorted(gid for gid, parent in candidates.items() if parent in allowed_adm1)


def report_country(country: str, *, data: dict | None = None,
                   administrative: dict | None = None) -> dict:
    if country not in SCOPE:
        raise ValueError("Country outside policy scope")
    admin_ref = administrative or admin.load_reference()
    data = data or load_excerpt(administrative=admin_ref)
    rows = [r for r in data["records"] if r["country"] == country]
    if country == "QA":
        return {
            "country": "QA", "source_records": 0,
            "scheme": "zone/street/building (not national postcodes)",
            "status": "no_postcode_source_import_expected",
            "official_postal_facts_transcribed": 0,
            "reviewed_postcode_to_geonames_links": 0,
            "source_citation": "https://www.qatarpost.qa/Home/PostalStandards",
            "notes": ["Qatar does not use the postal-number workflow of these four countries.",
                      "Use source-authorized zone/street/building lookup instead."],
        }
    geonames, hashes = admin.load_geo(country)
    official_admin = admin.propose(country, geonames, admin_ref)
    by_ref = {r["official_ref"]: r for r in official_admin}
    collisions = source_code_collisions(data)
    indexed = _build_name_index(geonames, {row["place_language"] for row in rows})
    outputs = []
    for row in rows:
        gov = by_ref.get(row["admin_ref"]) if row["admin_ref"] else None
        # PS government reference is an ADM2 governorate, but GN ADM1 is
        # only West Bank/Gaza. Never treat it as a confirmed foreign key.
        if country == "PS" and gov:
            group = gov["geographic_parent"]
            allowed = {admin.PS_GEO_GROUPS[group][0]} if group else None
            admin_status = ("candidate_governorate" if gov["status"] == "unique_candidate"
                            else "unmatched_governorate" if gov["status"] == "unmatched"
                            else "ambiguous_governorate")
        elif country == "OM" and gov:
            allowed = set(gov["candidate_geonames_ids"]) if gov["status"] == "unique_candidate" else None
            admin_status = ("candidate_governorate" if allowed else "unmatched_governorate")
        elif country == "OM" and row["official_area_label"] in OM_AMBIGUOUS_GOV_LABELS:
            allowed = None
            admin_status = "combined_or_historical_governorate_label"
        elif country == "SA" and gov:
            allowed = set(gov["candidate_geonames_ids"]) if gov["status"] == "unique_candidate" else None
            admin_status = "candidate_governorate" if allowed else "unmatched_governorate"
        else:
            allowed = None
            admin_status = "no_authority_admin_id_in_source_excerpt"
        matches = _matches(indexed, row["place_name"], row["place_language"], allowed)
        candidate_status = ("unmatched" if not matches else
                            "unique_unreviewed" if len(matches) == 1 else "ambiguous_unreviewed")
        key = (country, row["scheme"], row["code"])
        outputs.append({
            "record_id": row["record_id"], "source_id": row["source_id"],
            "code": row["code"], "scheme": row["scheme"],
            "record_role": row["evidence_role"],
            "source_place_name": row["place_name"],
            "place_language": row["place_language"],
            "source_area_label": row["official_area_label"],
            "government_admin_ref": row["admin_ref"],
            "government_admin_match": admin_status,
            "geonames_candidate_ids": matches,
            "geonames_match_status": candidate_status,
            "multiple_places_per_code": key in collisions,
            "official_code_to_source_place_transcribed": True,
            "official_code_to_geonames_identity_verified": False,
            "address_or_deliverability_verified": False,
        })
    counts = Counter(r["geonames_match_status"] for r in outputs)
    distinct_codes = {(r["scheme"], r["code"]) for r in outputs}
    return {
        "country": country, "source_records": len(outputs),
        "distinct_code_values": len(distinct_codes),
        "postcode_code_to_multiple_source_places": len({
            (r["scheme"], r["code"]) for r in outputs if r["multiple_places_per_code"]
        }),
        "candidate_unique_unreviewed": counts["unique_unreviewed"],
        "candidate_ambiguous_unreviewed": counts["ambiguous_unreviewed"],
        "candidate_unmatched": counts["unmatched"],
        "reviewed_postcode_to_geonames_links": 0,
        "nationwide_official_csv_records_imported": 0,
        "carrier_deliverability_verified": False,
        "publication_accuracy_independently_verified": False,
        "source_excerpt_grain": {
            "OM": "postal_office_branch", "PS": "postal_area_to_named_place",
            "SA": "single_published_national_address_example",
            "BH": "two_published_postcode_examples",
        }[country],
        "geonames_archive_sha256": hashes["archive_sha256"],
        "records": outputs,
    }


def summary(data: dict | None = None) -> dict:
    data = data or load_excerpt()
    administrative = admin.load_reference()
    result = [report_country(cc, data=data, administrative=administrative) for cc in SCOPE]
    return {
        "schema_version": 1,
        "status": "official_source_facts_transcribed_geonames_candidates_unreviewed",
        "source_records": sum(x["source_records"] for x in result),
        "reviewed_postcode_to_geonames_links": 0,
        "official_bulk_datasets_with_original_sha256": 0,
        "country_reports": result,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("report", "inspect"))
    p.add_argument("--country", choices=(*SCOPE, "all"), default="all")
    p.add_argument("--code")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.command == "report":
        result = summary() if args.country == "all" else report_country(args.country)
    else:
        if args.country == "all" or not args.code:
            p.error("inspect requires --country and --code")
        report = report_country(args.country)
        result = {"country": args.country, "code": args.code,
                  "records": [r for r in report.get("records", ()) if r["code"] == args.code],
                  "not_found_is_not_invalid": True}
    output = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
