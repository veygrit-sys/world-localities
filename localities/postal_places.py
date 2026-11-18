"""Compare supplied locality fields on the same row of a pinned GeoNames postal source."""

from collections import defaultdict
from pathlib import Path
import re
import unicodedata

from .postal import FULL_CODE_PATTERNS, ROOT, _countries, iter_postal_records, load_sources


PLACE_FIELDS = {"locality": "place_name", "region": "admin_name1", "region_code": "admin_code1"}
ELIGIBLE_KINDS = {"source_full", "source_reported"}


def _label(value):
    # Keep diacritics, ligatures, punctuation and leading zeros significant.
    return unicodedata.normalize("NFC", value.strip()).lower()


def _source_code(country, raw):
    code = raw.strip(" ")
    if country not in FULL_CODE_PATTERNS or not code.isascii():
        return code
    code = code.upper()
    boundary = -3 if country in {"CA", "GB"} else -2
    if " " not in code:
        spaced = code[:boundary] + " " + code[boundary:]
        if FULL_CODE_PATTERNS[country].fullmatch(spaced):
            return spaced
    return code


def _prepare(request, countries):
    if not isinstance(request, dict) or set(request) - {"country", "code", *PLACE_FIELDS}:
        raise ValueError("expected country, code and supported locality fields")
    raw_country = request.get("country")
    if not isinstance(raw_country, str) or not re.fullmatch(r"[A-Za-z]{2}", raw_country):
        raise ValueError("country must be two ASCII letters")
    country = raw_country.upper()
    if country not in countries:
        raise ValueError(f"unknown country: {country}")
    for field, value in request.items():
        if not isinstance(value, str) or not value.strip() or not value.isprintable():
            raise ValueError(f"{field} must be a nonempty single-line string")
    if "code" not in request or not PLACE_FIELDS.keys() & request.keys():
        raise ValueError("supply a postcode and at least one locality, region or region_code")
    return country, _source_code(country, request["code"])


def _score(request, rows, sources, country, code, limit):
    fields = {field: _label(request[field]) for field in PLACE_FIELDS if field in request}
    buckets = {"matched": [], "insufficient_evidence": [], "no_match_in_source": []}
    identities = set()
    for row in rows:
        missing = []
        different = []
        for field, expected in fields.items():
            value = _label(row[PLACE_FIELDS[field]])
            if not value:
                missing.append(field)
            elif value != expected:
                different.append(field)
        if different:
            disposition = "no_match_in_source"
        elif missing:
            disposition = "insufficient_evidence"
        else:
            disposition = "matched"
            identities.add(tuple(_label(row[k]) for k in (
                "place_name", "admin_name1", "admin_code1", "admin_name2", "admin_code2",
                "admin_name3", "admin_code3",
            )))
        candidate = {k: row[k] for k in (
            "source_id", "source_row", "code", "code_kind", "place_name",
            "admin_name1", "admin_code1", "admin_name2", "admin_code2", "admin_name3", "admin_code3",
        )}
        buckets[disposition].append(dict(candidate, status=disposition, missing=missing, different=different))
    if not sources:
        status = "no_eligible_source"
    elif not rows:
        status = "postcode_not_observed"
    elif identities:
        status = "ambiguous" if len(identities) > 1 or buckets["insufficient_evidence"] else "matched"
    elif buckets["insufficient_evidence"]:
        status = "insufficient_evidence"
    else:
        status = "no_match_in_source"
    ordered = [row for group in buckets.values() for row in group]
    return {
        "input": dict(request), "country": country, "lookup_code": code, "status": status,
        "scope": "postcode_and_supplied_locality_fields_in_geonames_snapshot",
        "sources": sources, "postcode_rows": len(rows), "matching_rows": len(buckets["matched"]),
        "distinct_matching_localities": len(identities), "candidates": ordered[:limit],
        "truncated": len(ordered) > limit,
        "current_postal_assignment_verified": False, "deliverability_verified": False,
    }


def validate_postal_places(requests, *, root: Path = ROOT, limit=20):
    """Scan each eligible snapshot once per batch; preserve request order and source rows."""
    if not isinstance(requests, list) or not requests:
        raise ValueError("provide a nonempty JSON list of requests")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer from 1 to 1000")
    countries = {row["code"] for row in _countries(root)}
    keys = [_prepare(r, countries) for r in requests]
    wanted = set(keys)
    requested_countries = {country for country, _ in keys}
    observations = defaultdict(list)
    sources_by_country = defaultdict(dict)
    for source in load_sources(root)["sources"]:
        if source["format"] != "geonames_tsv_zip" or not source.get("active_for_lookup", True):
            continue
        eligible = {
            country for country in requested_countries
            if source.get("expected_country", country) == country
            and source.get("country_code_kinds", {}).get(country, source["default_code_kind"]) in ELIGIBLE_KINDS
        }
        if not eligible:
            continue
        observed = set()
        for record in iter_postal_records(source, root):
            country = record["country_code"]
            if country not in eligible or record["code_kind"] not in ELIGIBLE_KINDS:
                continue
            observed.add(country)
            key = country, record["code"]
            if key in wanted:
                observations[key].append(record)
        for country in observed:
            sources_by_country[country][source["id"]] = {
                field: source.get(field) for field in ("sha256", "retrieved_at", "download_url", "licence")
            }
    return [_score(request, observations[country, code], sources_by_country[country], country, code, limit)
            for request, (country, code) in zip(requests, keys)]
