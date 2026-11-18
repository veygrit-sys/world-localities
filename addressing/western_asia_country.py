"""Country format rules and scoped postal excerpt checks for 18 Western Asian countries.

Its scope is country-level syntax and address presentation, NOT nationwide
official postal identity, building existence, or carrier deliverability.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Any
from .western_asia import COUNTRIES as M49_COUNTRIES
from .western_asia_reference import (
    COUNTRIES as FIRST_NINE,
    normalize_country_code,
    validate_western_asia_reference,
)

CAUCASUS_LEVANT = frozenset({"AM","AZ","GE","IL","JO"})
FINAL_FOUR = frozenset({"LB","IQ","SY","YE"})
ALL_COUNTRIES = frozenset(M49_COUNTRIES)
ROOT = Path(__file__).resolve().parents[1]

if FIRST_NINE & CAUCASUS_LEVANT or FIRST_NINE & FINAL_FOUR or CAUCASUS_LEVANT & FINAL_FOUR:
    raise AssertionError("Duplicate Western Asia validator ownership")
if set(FIRST_NINE | CAUCASUS_LEVANT | FINAL_FOUR) != set(ALL_COUNTRIES):
    raise AssertionError("Western Asia 18-country validator coverage incomplete")


def western_asia_quality_inventory() -> dict[str, Any]:
    """Inspect published GeoNames archives and presentation profiles by country.

    No nationwide coverage, current legal status, or delivery inference is made.
    """
    from .western_asia import WesternAsiaRegistry
    profile=WesternAsiaRegistry()
    archives=json.loads((ROOT/"registries/asia/archives.json").read_text(encoding="utf-8"))
    catalogue=json.loads((ROOT/"countries/catalog.json").read_text(encoding="utf-8"))
    zipcodes={r["country"]:r for r in archives["archives"]}
    regions={r["code"]:r for r in catalogue["countries"]}
    if len(zipcodes)!=len(archives["archives"]):
        raise ValueError("GeoNames inventory has duplicate country archives")
    values=[]
    for country in sorted(ALL_COUNTRIES):
        if country not in zipcodes or country not in regions:
            raise ValueError("West Asian country missing country source archive: "+country)
        spec=regions[country]
        if spec.get("inventory_status")!="source_layers_available":
            raise ValueError("Country source layer not published: "+country)
        rules="first_nine" if country in FIRST_NINE else (
              "caucasus_levant" if country in CAUCASUS_LEVANT else "last_four")
        evidence=profile.get(country)
        values.append({
            "country":country,
            "gazetteer_snapshot_rows":zipcodes[country]["rows"],
            "source_archive_sha256":zipcodes[country]["sha256"],
            "validation_module":rules,
            "native_languages":evidence["native_languages"],
            "english_format_profile":evidence["english_profile"],
            "address_evidence_status":evidence["evidence_status"],
            "national_completeness_verified":False,
            "official_postcode_coverage_verified":False,
            "deliverability_verified":False,
        })
    return {
        "m49_country_codes":len(ALL_COUNTRIES),
        "countries_with_saved_gazetteer":len(values),
        "countries_with_native_and_english_address_profiles":len(values),
        "countries_with_format_validators":len(values),
        "official_postal_registers_verified_countrywide":0,
        "countries_with_delivery_coverage_verified":0,
        "phase1_country_level_baseline":"implemented_not_nationally_verified",
        "countries":values,
    }


def _source_label_key(value, language):
    value = unicodedata.normalize("NFC", value)
    if language == "az-Latn":
        # Unicode SpecialCasing: I/ı and İ/i are distinct Azerbaijani case pairs.
        value = value.replace("I", "ı").replace("İ", "i")
    # Casefold also expands spellings such as ſ to s; a transcription match
    # uses ordinary letter case without those additional equivalences.
    return " ".join(value.lower().split())


def _postal_excerpt(country, code, selectors):
    from scripts.western_asia_caucasus_levant_join import load_sources

    data = load_sources()
    records = []
    matching_ids = []
    for row in data["postal_evidence"]:
        if row["country"] != country or row["code"] != code:
            continue
        source = data["postal_sources"][row["source_id"]]
        record = {
            "record_id": row["record_id"], "source_id": row["source_id"],
            "source_url": source["url"], "published": source["published"],
            "grain": row["grain"], "language": row["locale"],
            "postcode": code, "locality": row["place"], "admin_name": row["admin_name"],
        }
        records.append(record)
        languages = {"locality": row["locale"], "admin_name": "en"}
        if all(record[key] and
               _source_label_key(record[key], languages[key]) == _source_label_key(value, languages[key])
               for key, value in selectors.items()):
            matching_ids.append(row["record_id"])

    if not records:
        status = "postcode_not_in_excerpt"
    elif not selectors:
        status = "postcode_observed"
    elif matching_ids:
        status = "fields_observed_together"
    else:
        status = "fields_not_observed_together"
    return {
        "status": status, "reviewed_at": data["reviewed_at"],
        "postcode_records": records, "matching_record_ids": matching_ids,
    }


def _validate_caucasus_levant(country, postcode, options):
    from scripts.western_asia_caucasus_levant_join import postcode_format

    if options.keys() - {"locality", "admin_name"}:
        raise ValueError("AM/AZ/GE/IL/JO support postcode, locality and admin_name")
    selectors = {}
    for field, value in options.items():
        if value is None:
            continue
        if not isinstance(value, str):
            raise TypeError(field + " must be a string")
        if any(unicodedata.category(char).startswith("C") for char in value):
            raise ValueError("Control character in " + field)
        if value.strip():
            selectors[field] = value.strip()

    normalized = {"country_code": country, **selectors}
    result = {
        "country": country, "normalized": normalized, "errors": [], "missing": [], "warnings": [],
        "source_validation_module": "caucasus_levant",
        "checks": {"format_checked": False, "official_postal_assignment_verified": False,
                   "building_verified": False, "carrier_deliverability_verified": False},
    }
    syntax = postcode_format(country, postcode) if postcode is not None else None
    if syntax is None or not syntax["input"]:
        result.update(status="incomplete", missing=["postcode_missing"],
                      warnings=["postcode_not_supplied", "address_existence_not_checked"])
        return result
    result["checks"]["format_checked"] = True
    result["status"] = syntax["status"]
    result["warnings"] = ["postcode_assignment_not_checked", "carrier_deliverability_not_checked"]
    if syntax["code"] is None:
        result["errors"] = ["postcode_format_invalid"]
        return result
    normalized["postcode"] = syntax["code"]
    excerpt = _postal_excerpt(country, syntax["code"], selectors)
    result["postal_excerpt"] = excerpt
    if selectors:
        result["status"] = ("fields_observed_together" if excerpt["matching_record_ids"]
                            else "format_unverified")
    return result


def validate_western_asia_country(
    country_code: str, postcode: str | None = None, **options: Any
) -> dict[str, Any]:
    """Check format and, for AM/AZ/GE/IL/JO, an optional place against published excerpts."""
    cc = normalize_country_code(country_code)
    if cc not in ALL_COUNTRIES:
        raise ValueError("Unsupported Western Asian country: "+country_code)
    if cc in FIRST_NINE:
        raw=validate_western_asia_reference(cc,postcode=postcode,**options)
        checks=raw["checks"]
        return {
            "country":cc,"status":raw["status"],
            "normalized":raw["normalized"],
            "errors":raw.get("errors",[]),
            "missing":raw.get("missing", [e for e in raw["errors"] if e.endswith("_missing")]),
            "warnings":raw.get("warnings",[]),
            "source_validation_module":"first_nine",
            "checks":{
                "format_checked":checks["syntax_checked"],
                "official_postal_assignment_verified":False,
                "building_verified":False,
                "carrier_deliverability_verified":False,
            }
        }
    if cc in CAUCASUS_LEVANT:
        return _validate_caucasus_levant(cc, postcode, options)
    from scripts.western_asia_remaining_countries import postcode_format
    raw=postcode_format(cc,postcode,**options)
    return {
        "country":cc,"status":raw["status"],
        "normalized":raw["normalized"],
        "errors":raw["errors"],"missing":raw["missing"],"warnings":raw["warnings"],
        "source_validation_module":"last_four",
        "checks":{
            "format_checked":raw["checks"]["country_format_policy_checked"],
            "official_postal_assignment_verified":False,
            "building_verified":False,
            "carrier_deliverability_verified":False,
        }
    }
