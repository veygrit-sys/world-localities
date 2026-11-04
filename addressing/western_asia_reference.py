"""Source-aware, format-only address reference checks for TR, CY, KW and AE.

This module deliberately cannot certify that an address, postcode, Makani number,
or other identifier exists. No live lookup or carrier check is performed.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
import re
import unicodedata
from typing import Any

RULES_PATH = Path(__file__).resolve().parents[1] / "registries" / "official" / "western-asia" / "rules.json"
COUNTRIES = frozenset({"TR", "CY", "KW", "AE"})
BIDI_CONTROLS = re.compile(r"[\u202a-\u202e\u2066-\u2069]")
VALID_DELIVERY_MODES = frozenset({"home", "po_box"})
VALID_DIRECTIONS = frozenset({"domestic", "inbound"})
EMIRATES = frozenset({"AE-AZ", "AE-AJ", "AE-DU", "AE-FU", "AE-RK", "AE-SH", "AE-UQ"})


@lru_cache(maxsize=1)
def reference_rules() -> dict[str, Any]:
    """Load and audit the official-reference inventory, not source datasets."""
    payload = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or set(payload.get("countries", {})) != COUNTRIES:
        raise ValueError("Western Asia reference inventory/schema mismatch")
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", payload.get("reviewed_at", "")):
        raise ValueError("Missing reference review date")
    for cc, spec in payload["countries"].items():
        if spec.get("country_code") != cc:
            raise ValueError("Country code mismatch: " + cc)
        if spec.get("national_completeness_verified") is not False:
            raise ValueError("National completeness must not be asserted: " + cc)
        if spec.get("deliverability_verified") is not False:
            raise ValueError("Deliverability must not be asserted: " + cc)
        if not spec.get("sources") or not spec.get("locality_fields"):
            raise ValueError("Missing sources/locality fields: " + cc)
        source_ids = [s["id"] for s in spec["sources"]]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Duplicate source IDs: " + cc)
        if any(not s["url"].startswith("https://") for s in spec["sources"]):
            raise ValueError("Source URLs must be HTTPS: " + cc)
    return payload


def _text(value: str | None, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(key + " must be text")
    value = unicodedata.normalize("NFC", value.strip())
    if BIDI_CONTROLS.search(value) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Unsafe controls in " + key)
    return value or None


def inspect_western_asia_reference(country_code: str) -> dict[str, Any]:
    cc = country_code.upper()
    if cc not in COUNTRIES:
        raise ValueError("Unsupported country: " + country_code)
    item = reference_rules()["countries"][cc]
    return {"country_code": cc, "reviewed_at": reference_rules()["reviewed_at"],
            "locality_fields": item["locality_fields"],
            "sources": item["sources"],
            "national_completeness_verified": False,
            "deliverability_verified": False,
            "verified_postcode_records": 0,
            "note": "This is a rules and source inventory; nationwide reference data not imported."}


def validate_western_asia_reference(
    country_code: str, *, postcode: str | None = None,
    delivery_mode: str = "home", direction: str = "domestic",
    emirate: str | None = None, block: str | None = None,
    po_box: str | None = None, makani: str | None = None,
    onwani_postcode: str | None = None,
) -> dict[str, Any]:
    """Normalize and flag country-specific reference syntax without existence claims.

    CY inbound output uses CY- plus four digits. TR keeps the optional
    two-digit postal sublocality suffix. KW never infers a code from an area
    or block, and UAE never repurposes Makani or Onwani as a national postcode.
    """
    cc = country_code.upper()
    if cc not in COUNTRIES:
        raise ValueError("Unsupported country: " + country_code)
    if delivery_mode not in VALID_DELIVERY_MODES:
        raise ValueError("delivery_mode must be home or po_box")
    if direction not in VALID_DIRECTIONS:
        raise ValueError("direction must be domestic or inbound")
    values = {key: _text(val, key) for key, val in {
        "postcode": postcode, "emirate": emirate, "block": block,
        "po_box": po_box, "makani": makani, "onwani_postcode": onwani_postcode
    }.items()}
    errors: list[str] = []
    warnings: list[str] = []
    result: dict[str, str] = {"country_code": cc}
    for k in ("emirate", "block", "po_box"):
        if values[k]:
            result[k] = values[k]
    if values["emirate"]:
        result["emirate"] = values["emirate"].upper()
        if cc == "AE" and result["emirate"] not in EMIRATES:
            errors.append("invalid_ae_emirate_code")
    if delivery_mode == "po_box" and not values["po_box"]:
        errors.append("po_box_missing")
    if cc == "KW" and delivery_mode == "home" and not values["block"]:
        warnings.append("block_not_provided_for_kuwait_home")
    if cc == "KW" and delivery_mode == "po_box" and values["block"]:
        warnings.append("block_not_a_po_box_postcode_lookup")

    raw = values["postcode"]
    if cc in {"TR", "CY", "KW"}:
        if not raw:
            errors.append("postcode_missing")
        elif cc == "TR":
            match = re.fullmatch(r"([0-9]{5})(?:-([0-9]{2}))?", raw)
            if match is None:
                errors.append("postcode_format_invalid")
            else:
                result["postcode"] = raw
                result["postcode_base"] = match.group(1)
                if match.group(2) is not None:
                    result["postcode_sublocality_suffix"] = match.group(2)
                    warnings.append("sublocality_suffix_not_independently_verified")
        elif cc == "CY":
            match = re.fullmatch(r"(?:(?i:CY)[ -]?)?([0-9]{4})", raw)
            if match is None:
                errors.append("postcode_format_invalid")
            else:
                digits = match.group(1)
                formatted = "CY-" + digits if direction == "inbound" else digits
                result["postcode"] = formatted
                result["postcode_base"] = digits
                if formatted != raw:
                    warnings.append("cyprus_postcode_display_normalized")
        elif cc == "KW":
            if re.fullmatch(r"[0-9]{5}", raw) is None:
                errors.append("postcode_format_invalid")
            else:
                result["postcode"] = raw
                warnings.append("kuwait_block_and_po_box_postcodes_not_interchangeable")
    else:
        if raw:
            result["postcode"] = raw
            warnings.append("no_uae_national_postcode_validation")
        else:
            warnings.append("no_uae_national_postcode_required")
        if values["makani"]:
            digits = values["makani"].replace(" ", "")
            if re.fullmatch(r"[0-9]{10}", digits) is None:
                errors.append("makani_format_invalid")
            else:
                result["makani"] = digits
                warnings.append("makani_existence_and_emirate_scope_unverified")
        if values["onwani_postcode"]:
            # Abu Dhabi Onwani examples include building-specific codes, but no
            # nationally applicable numeric format is assumed from one example.
            result["onwani_postcode"] = values["onwani_postcode"]
            warnings.append("onwani_code_not_verified_against_authority")
            if result.get("emirate") not in (None, "AE-AZ"):
                errors.append("onwani_emirate_conflict")
    if cc != "AE" and (values["makani"] or values["onwani_postcode"]):
        errors.append("uae_identifier_on_non_uae_address")
    warnings.extend(("postcode_assignment_not_checked", "address_existence_not_checked",
                     "carrier_deliverability_not_checked"))
    if any(x.endswith("_invalid") or x.startswith("invalid_") or x.endswith("_conflict")
           or x == "uae_identifier_on_non_uae_address" for x in errors):
        status = "invalid_format"
    elif errors:
        status = "incomplete"
    elif cc == "AE" and raw:
        status = "format_unverified"
    else:
        status = "format_only"
    return {
        "country_code": cc, "status": status,
        "normalized": result, "errors": sorted(set(errors)),
        "warnings": sorted(set(warnings)),
        "checks": {"syntax_checked": True, "postcode_assignment_verified": False,
                   "locality_membership_verified": False, "building_verified": False,
                   "deliverability_verified": False},
        "source_ids": [s["id"] for s in reference_rules()["countries"][cc]["sources"]],
    }
