"""SPL / Bahrain Post / Qatar Post / Oman Post / Palestine Post syntax-only rules.

No reference lookup, building matching, code assignment or delivery validation is
performed. Locality names and native language must be verified via their own layers.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

BIDI_CONTROLS = re.compile(r"[\u202a-\u202e\u2066-\u2069]")
DIGITS = re.compile(r"[0-9]+")
CODES = frozenset({"SA", "BH", "QA", "OM", "PS"})

def _clean(value: str | None, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(key + " must be string")
    text = unicodedata.normalize("NFC", value.strip())
    if BIDI_CONTROLS.search(text) or any(ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise ValueError("Unsafe control character in " + key)
    return text or None

def validate_gulf_levant_reference(
    country_code: str, *, postcode: str | None = None, delivery_mode: str = "home",
    direction: str = "domestic", po_box: str | None = None,
    building_number: str | None = None, additional_number: str | None = None,
    short_address: str | None = None, road: str | None = None,
    district: str | None = None, city: str | None = None,
    locality: str | None = None, zone: str | None = None,
    street_number: str | None = None, phone: str | None = None,
    block: str | None = None, require_complete: bool = False,
    emirate: str | None = None, makani: str | None = None,
    onwani_postcode: str | None = None,
) -> dict[str, Any]:
    """Validate *syntax* only, preserving different identifiers and address schemes.

    If require_complete is true, check a minimum set of address components for
    a selected delivery mode. This never guarantees address completeness for a
    real recipient, existence or deliverability.
    """
    from .western_asia_reference import reference_rules
    cc = country_code.upper()
    if cc not in CODES:
        raise ValueError("Unsupported Gulf/Levant reference: " + country_code)
    if delivery_mode not in {"home", "po_box"}:
        raise ValueError("delivery_mode must be home or po_box")
    if direction not in {"domestic", "inbound"}:
        raise ValueError("direction must be domestic or inbound")
    if not isinstance(require_complete, bool):
        raise TypeError("require_complete must be bool")
    fields = {key: _clean(raw, key) for key, raw in {
        "postcode": postcode, "po_box": po_box,
        "building_number": building_number, "additional_number": additional_number,
        "short_address": short_address, "road": road, "district": district,
        "city": city, "locality": locality, "zone": zone,
        "street_number": street_number, "phone": phone, "block": block,
        "emirate": emirate, "makani": makani, "onwani_postcode": onwani_postcode
    }.items()}
    errors: list[str] = []
    warnings: list[str] = []
    normalized: dict[str, str] = {"country_code": cc}
    allowed = {
        "SA": {"postcode", "po_box", "building_number", "additional_number",
               "short_address", "road", "district", "city"},
        "BH": {"postcode", "po_box", "building_number", "road", "city",
               "locality", "block"},
        "QA": {"postcode", "po_box", "building_number", "zone",
               "street_number", "phone", "city"},
        "OM": {"postcode", "po_box", "locality", "city", "road",
               "building_number", "phone"},
        "PS": {"postcode", "po_box", "city", "locality", "road",
               "building_number", "district"},
    }[cc]
    for key, value in fields.items():
        if value and key not in allowed:
            errors.append("field_not_applicable:" + key)
        elif value and key not in {"postcode", "short_address"}:
            normalized[key] = value
    code = fields["postcode"]
    incomplete: list[str] = []
    if cc == "SA":
        if code:
            if re.fullmatch(r"[0-9]{5}", code):
                normalized["postcode"] = code
            else:
                errors.append("postcode_format_invalid")
        if not code and not fields["short_address"]:
            incomplete.append("postcode_or_short_address_missing")
        for key in ("building_number", "additional_number"):
            v = fields[key]
            if v and not re.fullmatch(r"[0-9]{4}", v):
                errors.append(key + "_format_invalid")
        short = fields["short_address"]
        if short:
            if re.fullmatch(r"[A-Za-z]{4}[0-9]{4}", short):
                normalized["short_address"] = short.upper()
                if fields["building_number"] and short[-4:] != fields["building_number"]:
                    errors.append("short_address_building_mismatch")
            else:
                errors.append("short_address_format_invalid")
        if require_complete:
            for key in ("building_number", "road", "district", "city",
                        "postcode", "additional_number"):
                if not fields[key]:
                    incomplete.append(key + "_missing")
            warnings.append("completeness_is_component_only_not_official_address_match")
        if delivery_mode == "po_box":
            warnings.append("sa_po_box_mode_not_covered_by_national_address_rules")
    elif cc == "BH":
        if not code:
            incomplete.append("postcode_missing")
        elif re.fullmatch(r"[0-9]{3,4}", code) and 100 <= int(code) <= 1299:
            normalized["postcode"] = code
            warnings.append("bahrain_postcode_range_not_assignment")
        else:
            errors.append("postcode_format_invalid")
        if require_complete:
            needed = ("po_box", "city") if delivery_mode == "po_box" else ("building_number", "road", "city")
            for key in needed:
                if not (fields[key] or (key == "city" and fields["locality"])):
                    incomplete.append(key + "_missing")
        if fields["block"]:
            warnings.append("bahrain_block_to_postcode_not_verified")
    elif cc == "QA":
        if code:
            normalized["postcode"] = code
            warnings.append("qatar_has_no_national_postcode_rule")
        else:
            warnings.append("qatar_no_postcode_required")
        if delivery_mode == "home":
            for key in ("zone", "street_number", "building_number"):
                if fields[key] and not DIGITS.fullmatch(fields[key]):
                    errors.append(key + "_format_invalid")
                if not fields[key]:
                    incomplete.append(key + "_missing")
            if not fields["phone"]:
                warnings.append("qatar_home_contact_phone_not_provided")
        else:
            if not fields["po_box"]:
                incomplete.append("po_box_missing")
        if direction == "inbound":
            warnings.append("qatar_inbound_postal_lines_use_english_doha_qatar")
        warnings.append("qatar_anwani_identity_not_checked")
    elif cc == "OM":
        if code:
            if re.fullmatch(r"[0-9]{3}", code):
                normalized["postcode"] = code
            else:
                errors.append("postcode_format_invalid")
        if delivery_mode == "po_box":
            if not fields["po_box"]:
                incomplete.append("po_box_missing")
            if not code:
                incomplete.append("postcode_missing")
            if require_complete and not (fields["locality"] or fields["city"]):
                incomplete.append("locality_missing")
            warnings.append("oman_postcode_is_post_office_reference_not_building")
        else:
            warnings.append("oman_home_address_not_verified_by_po_box_reference")
            if require_complete and not (fields["city"] or fields["locality"]):
                incomplete.append("locality_missing")
    elif cc == "PS":
        if not code:
            incomplete.append("postcode_missing")
        else:
            value = code.upper()
            if re.fullmatch(r"P[0-9]{3}", value):
                normalized["postcode"] = value
                normalized["postcode_kind"] = "area"
                warnings.append("palestine_area_code_not_final_delivery_point")
            elif re.fullmatch(r"P[0-9]{7}", value):
                normalized["postcode"] = value
                normalized["postcode_kind"] = "delivery_point_structure"
                warnings.append("palestine_delivery_point_code_not_assigned_checked")
            else:
                errors.append("postcode_format_invalid")
        if require_complete:
            if not (fields["city"] or fields["locality"]):
                incomplete.append("locality_missing")
            if normalized.get("postcode_kind") == "area":
                incomplete.append("final_delivery_point_code_missing")
            if delivery_mode == "po_box" and not fields["po_box"]:
                incomplete.append("po_box_missing")
        warnings.append("palestine_boundary_and_delivery_routes_not_asserted")

    if delivery_mode == "po_box" and not fields["po_box"] and cc in {"SA", "BH", "OM", "PS"}:
        incomplete.append("po_box_missing")
    warnings += [
        "postcode_assignment_not_checked", "address_existence_not_checked",
        "carrier_deliverability_not_checked"
    ]
    if errors:
        status = "invalid_format"
    elif incomplete:
        status = "incomplete"
    elif (cc == "QA" and code) or (cc == "OM" and delivery_mode == "home"):
        status = "format_unverified"
    else:
        status = "format_only"
    return {
        "country_code": cc,
        "status": status,
        "normalized": normalized,
        "errors": sorted(set(errors)),
        "missing": sorted(set(incomplete)),
        "warnings": sorted(set(warnings)),
        "checks": {
            "syntax_checked": True,
            "postcode_assignment_verified": False,
            "locality_membership_verified": False,
            "building_verified": False,
            "deliverability_verified": False,
        },
        "source_ids": [s["id"] for s in reference_rules()["countries"][cc]["sources"]],
    }
