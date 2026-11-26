"""Versioned private address-processing boundary; this module never submits shipments."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from collections.abc import Mapping

MAX_BODY = 16 * 1024
OPERATIONS = {
    "validate": {"components"},
    "translate": {"components", "source_language", "target_language"},
    "suggest": {"postcode", "path", "after", "limit", "query"},
    "fit_label": {"components", "profile_id"},
    "prepare_label": {"components", "profile_id", "source_language", "target_language"},
}


class AddressInputError(ValueError):
    """Safe for the transport to report as a generic input error."""


class AddressServiceUnavailable(RuntimeError):
    """The installed reference/index is unavailable, not an invalid address."""


def _bad(*_):
    raise AddressInputError("invalid_request")


def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            _bad()
        obj[key] = value
    return obj


def decode_request(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BODY:
        _bad()
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_bad)
    except (ValueError, UnicodeError, RecursionError):
        raise AddressInputError("invalid_json") from None


def _string(value, limit, *, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        _bad()
    if any(ch in "\u061c\u200e\u200f" or unicodedata.category(ch) in {"Cc", "Cs", "Zl", "Zp"} or
           unicodedata.bidirectional(ch) in {"LRE", "RLE", "PDF", "LRO", "RLO", "RLI", "LRI", "FSI", "PDI"}
           for ch in value):
        _bad()
    return value


def _parse(payload):
    if not isinstance(payload, dict):
        _bad()
    op = payload.get("operation")
    if not isinstance(op, str) or op not in OPERATIONS or payload.keys() - (OPERATIONS[op] | {"operation", "country"}):
        _bad()
    cc = _string(payload.get("country"), 2)
    if not re.fullmatch(r"[A-Za-z]{2}", cc):
        _bad()
    components = payload.get("components")
    if op != "suggest":
        if not isinstance(components, dict) or not 1 <= len(components) <= 40:
            _bad()
        from .components import normalize_key
        seen = set()
        for k, v in components.items():
            if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_ -]{0,39}", _string(k, 40)):
                _bad()
            _string(v, 512)
            key = normalize_key(k)
            if key in seen:
                _bad()
            seen.add(key)
            if op == "translate" and key == "country_code" and v.upper() != cc.upper():
                _bad()
    for key in ("source_language", "target_language"):
        if op == "translate" or key in payload:
            if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,3}", _string(payload.get(key), 35)):
                _bad()
            from .localized import normalize_language_tag
            try:
                normalize_language_tag(payload[key])
            except ValueError:
                _bad()
    if op == "prepare_label" and (("source_language" in payload) != ("target_language" in payload)):
        _bad()
    if op in ("fit_label", "prepare_label"):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", _string(payload.get("profile_id"), 64)):
            _bad()
    if op == "suggest":
        _string(payload.get("postcode"), 64)
        _string(payload.get("query", ""), 96, empty=True)
        path = payload.get("path", [])
        if not isinstance(path, list) or len(path) > 16:
            _bad()
        for item in path:
            _string(item, 2048)
        if type(payload.get("limit", 20)) is not int or not 1 <= payload.get("limit", 20) <= 50:
            _bad()
        after = payload.get("after")
        if after is not None and (type(after) is not int or not 0 <= after <= 1000000):
            _bad()
    return op, cc.upper(), components


def _profile(profile_id, profiles):
    if profile_id in {"ups-us-shipto", "yamato-jp-b2"}:
        return profile_id
    if profiles is not None and profile_id in profiles:
        profile = profiles[profile_id]
        if not isinstance(profile, Mapping) or profile.get("id") != profile_id:
            raise AddressServiceUnavailable("invalid_profile_configuration")
        return profile
    raise AddressInputError("unknown_profile")


def _prepare(p, cc, components, profile, index_path):
    from .evidence_validation import validate_address
    from .label_fit import fit_label
    from .safe_translation import translate_address
    from .components import normalize_key

    check = validate_address(cc, components, index_path=index_path)
    result = {"status": "review_required", "fields": None, "carrier_fields": None, "validation": check,
              "deliverability_verified": False, "submitted": False, "issues": []}
    # Recipients/attention are supplied by the caller; location components may
    # only pass this gate if verified together, at the address-point level.
    identity = {"recipient", "organization", "attention", "country_code"}
    missing = {normalize_key(k) for k in components} - identity - set(check["verified_fields"])
    if check["address1_decision"]["status"] != "verified" or missing:
        result["issues"].append("address_evidence_insufficient_or_conflicting")
        return result
    if "target_language" in p:
        translated = translate_address(cc, components, p["source_language"], p["target_language"])
        result["translation_status"] = translated["status"]
        if translated["needs_review"]:
            result["issues"].append("translation_requires_review")
            return result
        components = translated["components"]
    fit = fit_label(cc, components, profile)
    result["fit"] = fit
    if fit["status"] == "fits":
        result.update(status="prepared", fields=fit["fields"], carrier_fields=fit.get("carrier_fields"))
    else:
        result["issues"].append("carrier_field_layout_requires_review")
    return result


def _process(payload, *, index_path=None, label_profiles=None):
    """Run one operation. Index and carrier limits are trusted deployment settings."""
    from .evidence_validation import validate_address
    from .safe_translation import translate_address
    from .label_fit import fit_label

    from .components import canonicalize_components
    op, cc, components = _parse(payload)
    if components is not None:
        try:
            canonicalize_components(components)
        except ValueError:
            raise AddressInputError("invalid_components") from None
    if op == "suggest":
        if index_path is None:
            raise AddressServiceUnavailable("index_not_configured")
        from .safe_suggest import suggest
        try:
            result = suggest(index_path, cc, payload["postcode"], path=payload.get("path", []),
                             after=payload.get("after"), limit=payload.get("limit", 20),
                             query=payload.get("query", ""))
        except ValueError:
            raise AddressInputError("invalid_selection_or_postcode") from None
        except (sqlite3.Error, OSError, RuntimeError):
            raise AddressServiceUnavailable("index_unavailable") from None
    elif op == "validate":
        result = validate_address(cc, components, index_path=index_path)
    elif op == "translate":
        result = translate_address(cc, components, payload["source_language"], payload["target_language"])
    else:
        profile = _profile(payload["profile_id"], label_profiles)
        if op == "fit_label":
            result = fit_label(cc, components, profile)
        else:
            result = _prepare(payload, cc, components, profile, index_path)
    return {"schema_version": 1, "operation": op, "result": result}


def process_request(payload, *, index_path=None, label_profiles=None):
    """Public Python entry point; separate invalid input from unavailable references."""
    try:
        return _process(payload, index_path=index_path, label_profiles=label_profiles)
    except (AddressInputError, AddressServiceUnavailable):
        raise
    except (OSError, sqlite3.Error, ValueError, RuntimeError) as exc:
        raise AddressServiceUnavailable("reference_unavailable") from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", help="Trusted local postcode SQLite index")
    parser.add_argument("--profiles", help="Trusted local JSON file keyed by carrier profile ID")
    args = parser.parse_args()
    try:
        profiles = None
        if args.profiles:
            with open(args.profiles, encoding="utf-8") as stream:
                profiles = json.load(stream)
        req = decode_request(sys.stdin.buffer.read(MAX_BODY + 1))
        print(json.dumps(process_request(req, index_path=args.index, label_profiles=profiles),
                         ensure_ascii=False, allow_nan=False))
    except (AddressInputError, ValueError):
        parser.exit(2, "Invalid address processing request.\n")
    except (AddressServiceUnavailable, OSError, sqlite3.Error):
        parser.exit(3, "Address processing resources are unavailable.\n")


if __name__ == "__main__":
    main()
