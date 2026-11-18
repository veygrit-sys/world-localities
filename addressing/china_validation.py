"""Offline comparison with the pinned mainland Chinese statistical hierarchy."""

from __future__ import annotations

import re
from collections.abc import Mapping
from functools import cache
from typing import Any

from .china_reference import TABLES, load_statistical_table
from .china_subdivisions import subdivision_catalog
from .components import canonicalize_components

POSTCODE_REFERENCE = "https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/chnEn.pdf"
LEVELS = tuple(TABLES)
MUNICIPALITIES = {"北京市", "天津市", "上海市", "重庆市"}


@cache
def _load_reference():
    tables = {}
    receipts = {}
    for level in LEVELS:
        tables[level], receipts[level] = load_statistical_table(level)
    return tables, receipts


def _state_code_constraint(value, provinces, receipt):
    """Resolve an explicit code, accepting alphabetic IDs only on a unique exact label join."""
    if value is None:
        return {"value": None, "status": "not_supplied"}
    if value in provinces:
        return {
            "value": value,
            "status": "recognized",
            "statistical_code": value,
            "source_id": receipt["source_id"],
        }
    code = re.fullmatch(r"(?:CN-?)?([A-Z]{2})", value, re.IGNORECASE | re.ASCII)
    if code:
        catalog = subdivision_catalog()
        subdivision_id = "cn" + code.group(1).lower()
        row = catalog["subdivisions"].get(subdivision_id)
        if row:
            matching = [r for r in provinces.values() if r["name"] == row["zh"]]
            if len(matching) == 1:
                return {
                    "value": value,
                    "status": "recognized",
                    "statistical_code": matching[0]["code"],
                    "matched_label": row["zh"],
                    "source_id": catalog["source_id"],
                    "subdivision_id": subdivision_id,
                    "source_version": catalog["release"],
                    "source_draft_status": row["zh_draft_status"],
                    "reference": (
                        f"{catalog['repository']}/blob/{catalog['revision']}/"
                        + catalog["source_files"]["zh"]["path"]
                    ),
                }
    return {"value": value, "status": "unsupported"}


def _candidates(values, tables, state_code):
    criteria = {
        "province": [values["state"]] if "state" in values else [],
        "city": [],
        "area": [values[key] for key in ("city_district", "county") if key in values],
    }
    if state_code["status"] == "unsupported":
        return {"status": "unsupported_state_code", "level": None, "candidates": []}
    if state_code["status"] == "recognized":
        criteria["province"].append(state_code["statistical_code"])
    if "city" in values:
        city = values["city"]
        # The four directly administered municipalities occur at province level.
        criteria["province" if city in MUNICIPALITIES else "city"].append(city)
    deepest = next((level for level in reversed(LEVELS) if criteria[level]), None)
    if deepest is None:
        return {"status": "insufficient_input", "level": None, "candidates": []}
    candidates = []
    for row in tables[deepest].values():
        if not all(v in (row["name"], row["code"]) for v in criteria[deepest]):
            continue
        chain = {deepest: row}
        if deepest == "area":
            chain["city"] = tables["city"][row["cityCode"]]
        if deepest != "province":
            chain["province"] = tables["province"][row["provinceCode"]]
        if all(
            value in (chain[level]["name"], chain[level]["code"])
            for level, requested in criteria.items()
            for value in requested
        ):
            candidates.append({level: dict(chain[level]) for level in LEVELS if level in chain})
    if len(candidates) == 1:
        status = "matched"
    else:
        status = "ambiguous" if candidates else "no_match"
    return {"status": status, "level": deepest, "candidates": candidates}


def validate_china_address(components: Mapping[str, str | None]) -> dict[str, Any]:
    """Match explicit names or codes and parent links. A match concerns only this snapshot."""
    if not isinstance(components, Mapping) or not all(isinstance(k, str) for k in components):
        raise TypeError("components must be an object with string keys")
    original = dict(components)
    # In this country API an explicit 'district' denotes the county-level field.
    # Keep the global 'neighbourhood' alias semantics for all other field names.
    ordinary = {}
    districts = []
    for key, value in original.items():
        if key.strip().casefold() == "district":
            districts.append(value)
        else:
            ordinary[key] = value
    parsed = canonicalize_components(ordinary)
    values = dict(parsed.values)
    for district in districts:
        normalized = canonicalize_components({"city_district": district}).values
        if "city_district" in normalized:
            if "city_district" in values and normalized["city_district"] != values["city_district"]:
                raise ValueError("conflicting values for address component: city_district")
            values.update(normalized)
    if values.get("country_code", "CN") != "CN":
        raise ValueError("mainland China reference requires country_code CN")
    tables, receipts = _load_reference()
    state_code = _state_code_constraint(values.get("state_code"), tables["province"], receipts["province"])
    administrative = _candidates(values, tables, state_code)
    code = values.get("postcode")
    postcode_status = "not_supplied"
    if code is not None:
        postcode_status = "valid_format" if re.fullmatch(r"[0-9]{6}", code) else "invalid_format"
    status = administrative["status"]
    if postcode_status == "invalid_format":
        status = "invalid_format"
    elif postcode_status == "valid_format" and status == "insufficient_input":
        status = "format_only"
    checked_fields = {"state", "city", "city_district", "county", "postcode", "country_code"}
    if state_code["status"] == "recognized":
        checked_fields.add("state_code")
    return {
        "country": "CN",
        "input": original,
        "status": status,
        "status_scope": "administrative_snapshot_and_postcode_syntax_only",
        "state_code": state_code,
        "source_version": receipts["province"]["source_date"],
        "sources": {level: dict(receipt) for level, receipt in receipts.items()},
        "administrative": administrative,
        "postcode": {"value": code, "status": postcode_status, "reference": POSTCODE_REFERENCE},
        "unchecked_fields": sorted((set(values) | set(parsed.extras)) - checked_fields),
        "checks": {
            "administrative_scope": "statistical_snapshot",
            "current_legal_administration_verified": False,
            "postal_assignment_verified": False,
            "street_verified": False,
            "premise_verified": False,
            "deliverability_verified": False,
            "national_completeness_verified": False,
        },
    }
