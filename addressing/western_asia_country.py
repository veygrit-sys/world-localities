"""One format-only API for all 18 UN-M49 Western Asian countries.

Its scope is country-level syntax and address presentation, NOT nationwide
official postal identity, building existence, or carrier deliverability.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from .western_asia import COUNTRIES as M49_COUNTRIES
from .western_asia_reference import (
    COUNTRIES as FIRST_NINE,
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


def validate_western_asia_country(
    country_code: str, postcode: str | None = None, **options: Any
) -> dict[str, Any]:
    """Return uniform syntax-only results. Reject unknown options; never invent codes."""
    if not isinstance(country_code,str):
        raise TypeError("country_code must be a string")
    cc=country_code.upper()
    if cc not in ALL_COUNTRIES:
        raise ValueError("Unsupported Western Asian country: "+country_code)
    if cc in FIRST_NINE:
        raw=validate_western_asia_reference(cc,postcode=postcode,**options)
        checks=raw["checks"]
        return {
            "country":cc,"status":raw["status"],
            "normalized":raw["normalized"],
            "errors":raw.get("errors",[]),
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
        if options:
            raise ValueError("AM/AZ/GE/IL/JO reference syntax only supports postcode")
        from scripts.western_asia_caucasus_levant_join import postcode_format
        if postcode is None or not postcode.strip():
            return {
                "country":cc,"status":"incomplete",
                "normalized":{"country_code":cc},"errors":[],
                "warnings":["postcode_not_supplied","address_existence_not_checked"],
                "source_validation_module":"caucasus_levant",
                "checks":{"format_checked":False,
                          "official_postal_assignment_verified":False,
                          "building_verified":False,
                          "carrier_deliverability_verified":False},
            }
        result=postcode_format(cc,postcode)
        return {
            "country":cc,"status":result["status"],
            "normalized":{"country_code":cc,**({"postcode":result["code"]} if result["code"] else {})},
            "errors":["postcode_format_invalid"] if result["status"]=="invalid_format" else [],
            "warnings":["postcode_assignment_not_checked","carrier_deliverability_not_checked"],
            "source_validation_module":"caucasus_levant",
            "checks":{"format_checked":True,
                      "official_postal_assignment_verified":False,
                      "building_verified":False,
                      "carrier_deliverability_verified":False},
        }
    from scripts.western_asia_remaining_countries import postcode_format
    raw=postcode_format(cc,postcode,**options)
    return {
        "country":cc,"status":raw["status"],
        "normalized":raw["normalized"],
        "errors":raw["errors"],"warnings":raw["warnings"],
        "source_validation_module":"last_four",
        "checks":{
            "format_checked":raw["checks"]["country_format_policy_checked"],
            "official_postal_assignment_verified":False,
            "building_verified":False,
            "carrier_deliverability_verified":False,
        }
    }
