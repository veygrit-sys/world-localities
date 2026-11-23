"""Evidence-backed address translation. Results are display labels, not proof of delivery.

The original mapping and every opaque component survive intact. No address is sent
over the network; no generated spelling or untagged GeoNames alias is substituted.
"""
from __future__ import annotations

from collections.abc import Mapping
import csv
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path
import re
from threading import Lock
import unicodedata

from .components import normalize_key
from .localized import normalize_language_tag
from localities.open_reference import cn, jp
from registries.official.query import expand_roman


_DIR = Path(__file__).resolve().parent
_JP_PATH = _DIR.parent / "registries" / "official" / "JP"
_JP_HASH = "42966a0a1e85173c37cfc2aeb37f9d1e3792b3173ba54f670e2d02b6254c004f"
_JP_INDEX_LOCK = Lock()
# Source snapshot: rows, joins and reproducible romanization are documented in
# registries/official/JP. Do not guess when a row lacks a complete unique join.
_JP_FIELDS = {"prefecture": "prefecture", "state": "prefecture", "municipality": "municipality",
              "city": "municipality", "city_district": "municipality", "town": "town",
              "neighbourhood": "town", "suburb": "town", "hamlet": "town"}
_CN_CITIES = {"cnbj", "cncq", "cnsh", "cntj"}  # provincial-level municipalities
_GBA_CITIES = (
    ("Guangzhou", "广州", "廣州"), ("Shenzhen", "深圳", "深圳"), ("Zhuhai", "珠海", "珠海"),
    ("Foshan", "佛山", "佛山"), ("Huizhou", "惠州", "惠州"), ("Dongguan", "东莞", "東莞"),
    ("Zhongshan", "中山", "中山"), ("Jiangmen", "江门", "江門"), ("Zhaoqing", "肇庆", "肇慶"),
)
_ID_FIELDS = {"country_code", "state_code", "postcode", "sorting_code", "house_number",
              "unit", "floor", "entrance", "block", "lot", "po_box", "subpremise"}
_PRIVATE = {"recipient", "attention", "organization", "house"}
_ORDER = "recipient attention organization house_number road address_line1 address_line2 house block lot entrance floor unit subpremise po_box hamlet neighbourhood suburb village town city_district city municipality postal_city county state_district state prefecture state_code region postcode sorting_code country country_code".split()
_NATIVE_ORDER = "country country_code postcode sorting_code region state prefecture state_code state_district county municipality city postal_city city_district village town suburb neighbourhood hamlet road house_number block lot address_line1 address_line2 house entrance floor unit subpremise po_box organization attention recipient".split()


def _key(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def _locale(tag):
    """Only fall back within an interchangeable script; unknown tags fail closed."""
    if not isinstance(tag, str) or len(tag) > 35:
        raise ValueError("invalid language tag")
    parts = normalize_language_tag(tag).split("-")
    lang = parts[0]
    script = next((p for p in parts[1:] if len(p) == 4 and p.istitle()), "")
    if lang == "zh":
        if script not in {"", "Hans", "Hant"}:
            return None
        return "zh-" + (script or ("Hant" if set(parts) & {"TW", "HK", "MO"} else "Hans"))
    if lang == "ja" and script in {"", "Jpan", "Latn", "Kana"}:
        return "ja" + ("-" + script if script in {"Latn", "Kana"} else "")
    if lang == "en" and script in {"", "Latn"}:
        return "en"
    return None


@lru_cache(maxsize=1)
def _labels():
    return json.loads((_DIR / "translation_labels.json").read_bytes())


def _cldr(country, field, original, source, target, address):
    data = _labels()
    if field == "country":
        records = [(country, data["countries"].get(country, {}))]
        directory, element = "main", "territory"
    elif field in {"state", "prefecture", "city", "municipality"}:
        prefix = country.lower()
        code = address.get("state_code", "").upper().removeprefix(country + "-")
        records = [(k, labels) for k, labels in data["subdivisions"].items()
                   if k.startswith(prefix) and (not code or k[2:] == code.lower())
                   and k not in {"cnhk", "cnmo", "cntw"}  # separate postal profiles
                   and (field not in {"city", "municipality"} or (
                        k in _CN_CITIES and (not address.get("state") or (
                            source in labels and _key(address["state"]) == _key(labels[source][0])))))]
        directory, element = "subdivisions", "subdivision"
    else:
        return None
    found = [(k, r) for k, r in records if source in r and target in r
             and _key(r[source][0]) == _key(original)]
    if len(found) != 1:
        return None
    k, row = found[0]
    langs = {"zh-Hans": "zh", "zh-Hant": "zh_Hant"}
    files = [f"common/{directory}/{langs.get(lang, lang)}.xml" for lang in (source, target)]
    return row[target][0], "localized", {
        "source_id": "unicode-cldr-48", "record_id": element + ":" + k,
        "source_url": "https://github.com/unicode-org/cldr/tree/release-48/" + "common/" + directory,
        "blobs": {p: data["source_blobs"][p] for p in files},
        "draft_status": {lang: row[lang][1] for lang in (source, target)},
        "attribution": "Unicode, Inc. CLDR 48", "license": "Unicode-3.0"}


@lru_cache(maxsize=1)
def _jp_index():
    packed = (_JP_PATH / "postal_rows.csv.gz").read_bytes()
    if hashlib.sha256(packed).hexdigest() != _JP_HASH:
        raise ValueError("Japan Post translation projection hash mismatch")
    data = gzip.decompress(packed)
    header = next(csv.reader([data[:data.index(b"\n")].decode()]))
    # Build offsets into a single immutable buffer, rather than retaining 124k
    # parsed records. The four leading columns in this pinned CSV are ASCII.
    offsets = {}
    for m in re.finditer(rb"^jp-postal:[a-z0-9]+,JP,JapanPost,([0-9]{7}),full,", data, re.M):
        k, pos = m[1], m.start()
        prior = offsets.get(k)
        offsets[k] = pos if prior is None else ((*prior, pos) if isinstance(prior, tuple) else (prior, pos))
    return data, header, offsets


def _jp_rows(postcode):
    if not re.fullmatch("[0-9]{3}-?[0-9]{4}", postcode):
        return []
    # functools.lru_cache may invoke a cold loader concurrently. Serialize the
    # one-time build to avoid retaining multiple decompressed 42 MB projections.
    with _JP_INDEX_LOCK:
        data, header, index = _jp_index()
    offsets = index.get(postcode.replace("-", "").encode(), ())
    rows = []
    for start in (offsets,) if isinstance(offsets, int) else offsets:
        end = data.find(b"\n", start)
        values = next(csv.reader([data[start:end if end >= 0 else None].decode()]))
        row = dict(zip(header, values, strict=True))
        rows.append(expand_roman(row) if row["roman_match_status"] == "matched_unique" else row)
    return rows


def _jp_label(field, original, source, target, rows):
    role = _JP_FIELDS.get(field)
    columns = {"ja": "ja", "ja-Kana": "kana", "ja-Latn": "roman", "en": "roman"}
    if not role or source not in columns or target not in columns:
        return None
    a, b = columns[source], columns[target]
    matched = [r for r in rows if _key(original) == _key(r[role + "_" + a])
               and (role != "town" or r["town_is_postal_instruction"] == "false")]
    if (len(matched) != 1 or matched[0]["roman_match_status"] != "matched_unique"
            or matched[0]["roman_truncation_possible"] != "false" or not matched[0][role + "_" + b]):
        return None
    row = matched[0]
    return row[role + "_" + b], ("romanized" if b == "roman" else "localized"), {
        "source_id": "jp-post-roman", "record_id": row["association_id"],
        "source_row": row["roman_row"], "source_as_of": "2025-06",
        "published_language": "ja-Latn" if b == "roman" else target,
        "source_url": "https://www.post.japanpost.jp/service/search/zipcode/download/roman-zip.html",
        "attribution": "Japan Post", "projection_sha256": _JP_HASH}


def _gazetteer(field, original, source, target):
    role = _JP_FIELDS.get(field)
    cols = {"ja": "kanji", "ja-Kana": "kana", "ja-Latn": "romanized", "en": "romanized"}
    if not role or source not in cols or target not in cols:
        return None
    viable = []
    for row in jp.lookup(original):
        if not row[cols[source]] or _key(row[cols[source]]) != _key(original) or not row[cols[target]]:
            continue
        suffix = (row["kanji"] or "")[-1:]
        is_pref = bool(suffix) and suffix in {"都", "道", "府", "県"}
        if (role == "prefecture" and row["classification"] == "Municipality" and is_pref
            or role == "municipality" and row["classification"] == "Municipality" and not is_pref
            or role == "town" and row["classification"] == "Populated area"):
            viable.append(row)
    if len(viable) != 1:
        return None
    row = viable[0]
    evidence = {k: row[k] for k in ("record_id", "source_id", "source_url", "source_as_of", "attribution", "terms_url")}
    if cols[target] == "romanized":
        evidence["published_language"] = "ja-Latn"
    return row[cols[target]], ("romanized" if cols[target] == "romanized" else "localized"), evidence


def _cmab(field, original, source, target, address):
    column = {"organization": "name", "address_line1": "address"}.get(field)
    if not column or {source, target} != {"en", "zh-Hant"}:
        return None
    rows = [r for r in cn.lookup(original) if _key(r[column][source]) == _key(original)
            and (not address.get("postcode") or address["postcode"] == r["postcode"])]
    if len(rows) != 1:
        return None
    row = rows[0]
    return row[column][target], "localized", {k: row[k] for k in (
        "record_id", "source_id", "source_url", "source_updated_on", "attribution", "terms_url")}


def _guangdong(field, original, source, target, address):
    # The bilingual/trilingual municipal pages explicitly identify their parent.
    # Require the same parent in the input; never infer it from a short city name.
    paths = {"en": "en", "zh-Hans": "sc", "zh-Hant": "tc"}
    if source not in paths or target not in paths or field not in {"state", "city", "municipality"}:
        return None
    province = {"en": ("Guangdong", "Guangdong Province"), "zh-Hans": ("广东省",),
                "zh-Hant": ("廣東省",)}
    code = address.get("state_code", "").upper()
    if code and code not in {"CN-GD", "GD"}:
        return None
    parent = address.get("state", "")
    if parent and _key(parent) not in {_key(p) for p in province[source]}:
        return None
    record = None
    if field == "state":
        if _key(original) in {_key(p) for p in province[source]}:
            record = ("overview", province[target][0])
    elif parent or code:
        for en, hans, hant in _GBA_CITIES:
            names = {"en": (en,), "zh-Hans": (hans + "市", hans), "zh-Hant": (hant + "市", hant)}
            if _key(original) in {_key(n) for n in names[source]}:
                record = (en.lower(), names[target][0])
                break
    if record:
        slug, rendered = record
        page = "https://www.bayarea.gov.hk/{}/about/" + slug + ".html"
        return rendered, "localized", {"source_id": "hk-gba-guangdong-municipalities",
                "record_id": "CN-GD:" + slug, "source_url": page.format(paths[source]),
                "target_url": page.format(paths[target]), "attribution": "Hong Kong SAR Government"}
    return None


def _check_same_script(text, locale):
    """Only used to detect obvious mixed-script residuals, never to infer language."""
    if locale in {"en", "ja-Latn"}:
        return all(not c.isalpha() or "LATIN" in unicodedata.name(c, "") for c in text)
    if locale == "ja-Kana":
        return all(not c.isalpha() or any(s in unicodedata.name(c, "")
                   for s in ("KATAKANA", "HIRAGANA")) for c in text)
    return True


def translate_address(country_code: str, components: Mapping[str, str], source_language: str,
                      target_language: str) -> dict:
    """Return original + display components, per-field receipts, and review state.

    A romanized address component is labelled as such, including when requested
    for English display. 'complete' concerns rendering only, never delivery.
    """
    if not isinstance(country_code, str) or not re.fullmatch("[A-Za-z]{2}", country_code):
        raise ValueError("invalid country code")
    if not isinstance(components, Mapping) or not 1 <= len(components) <= 40:
        raise ValueError("expected 1 to 40 address components")
    country = country_code.upper()
    original, address, canonical = dict(components), {}, {}
    for k, v in original.items():
        if (not isinstance(k, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_ -]{0,39}", k)
                or not isinstance(v, str) or not v.strip() or len(v) > 512
                or any(unicodedata.category(c) in {"Cc", "Cs", "Zl", "Zp"} or c in "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069" for c in v)):
            raise ValueError("invalid address component")
        key = normalize_key(k)
        if key in address:
            raise ValueError("duplicate canonical address component")
        canonical[k], address[key] = key, v
    if "country_code" in address and address["country_code"].upper() != country:
        raise ValueError("conflicting country codes")
    source, target = _locale(source_language), _locale(target_language)
    supported = bool(source and target and country in _labels()["countries"])
    different = supported and source != target
    rows = []
    if (different and country == "JP" and any(k in _JP_FIELDS for k in address)
            and source in {"ja", "ja-Kana", "ja-Latn", "en"} and target in {"ja", "ja-Kana", "ja-Latn", "en"}):
        rows = _jp_rows(address.get("postcode", ""))
        column = {"ja": "ja", "ja-Kana": "kana", "ja-Latn": "roman", "en": "roman"}[source]
        rows = [row for row in rows if all(_key(value) == _key(row[_JP_FIELDS[k] + "_" + column])
                   for k, value in address.items() if k in _JP_FIELDS)]
    output, fields = {}, {}
    for k, value in original.items():
        field = canonical[k]
        match = None
        if different:
            if country == "JP":
                match = _jp_label(field, value, source, target, rows)
                if not match and (not address.get("postcode") or field in {"state", "prefecture"}):
                    match = _gazetteer(field, value, source, target)
            elif country == "CN":
                match = _cmab(field, value, source, target, address) or _guangdong(
                    field, value, source, target, address)
            match = match or _cldr(country, field, value, source, target, address)
        # A translation may reorder but may never discard/change digit groups.
        if match and sorted(re.findall(r"\d+", value)) != sorted(re.findall(r"\d+", match[0])):
            match = None
        if match:
            rendered, status, evidence = match
        elif not supported:
            rendered, status, evidence = value, "unverified", None
        elif source == target and _check_same_script(value, target):
            rendered, status, evidence = value, "unchanged", None
        elif field in _ID_FIELDS and _check_same_script(value, target):
            rendered, status, evidence = value, "preserved_identifier", None
        elif field in _PRIVATE and _check_same_script(value, target):
            rendered, status, evidence = value, "preserved_proper_name", None
        else:
            rendered, status, evidence = value, "unverified", None
        fields[k] = {"status": status, "provenance": evidence}
        output[k] = rendered
    missing = [k for k, v in fields.items() if v["status"] == "unverified"]
    changed_by_reference = any(v["provenance"] for v in fields.values())
    order = _NATIVE_ORDER if target in {"ja", "ja-Kana", "zh-Hans", "zh-Hant"} else _ORDER
    ordered = sorted(output, key=lambda k: (order.index(canonical[k]) if canonical[k] in order else len(order), k))
    return {"country": country, "source_language": source_language, "target_language": target_language,
            "original_components": original, "components": output, "fields": fields,
            "lines": [output[k] for k in ordered], "needs_review": bool(missing),
            "unverified_fields": missing,
            "status": ("partial" if changed_by_reference else "needs_review") if missing else "complete",
            "delivery_verified": False}
