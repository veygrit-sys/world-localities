"""Compare place components on a single postal observation from JP or TW."""

import gzip
import hashlib
import json
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET

from localities.postal import iter_postal_records, load_sources

ROOT = Path(__file__).resolve().parents[2]
JP_FIELDS = {"prefecture", "municipality", "city_district", "town", "organization"}
TW_FIELDS = {"postal_area", "city_or_county", "postal_locality"}
# The fixed ordinary source contains plain, ranged, and "number onward"
# instructions, sometimes followed by a bank-of-river qualifier.
JP_NUMBER_INSTRUCTION = re.compile(
    r".+[市区町村]の次に(?:[０-９]+(?:〜[０-９]+)?)?番地(?:以降)?がくる場合(?:（[^（）]+）)?"
)


def _code(country, value):
    if not isinstance(value, str):
        raise ValueError("postal codes must be strings")
    if country == "JP" and re.fullmatch(r"[0-9]{3}-?[0-9]{4}", value):
        return value.replace("-", "")
    if country == "TW" and re.fullmatch(r"(?:[0-9]{3}|[0-9]{6})", value):
        return value
    return None


def _label(value):
    return unicodedata.normalize("NFC", value.strip())


def _jp_wards(root):
    folder = root / "registries/official/JP"
    metadata = json.loads((folder / "sources.json").read_text(encoding="utf-8"))
    filename = "sources/registry.json.gz"
    pin = metadata["bundled_files"][filename]
    raw = (folder / filename).read_bytes()
    if len(raw) != pin["bytes"] or hashlib.sha256(raw).hexdigest() != pin["sha256"]:
        raise ValueError("Japan ABR ward source checksum mismatch")
    wards = {}
    for prefecture in json.loads(gzip.decompress(raw))["prefectures"]:
        for place in prefecture["localities"]:
            if place["category"] in {"designated_city_ward", "special_ward"}:
                wards[place["jis_code"]] = (place, prefecture["path"])
    return wards, {**metadata["sources"]["jp-abr-snapshot"], "sha256": pin["sha256"]}


def _jp_ward_labels(ward_entry, row, fields):
    if ward_entry is None:
        return None
    place, path = ward_entry
    abr = place["source_row"]
    # Verify the actual postal spelling on the same JIS code before splitting.
    if (abr["ablt_date"] or abr["pref"] != row["admin_name1"]
            or abr["city"] + abr["ward"] != row["admin_name2"]):
        return None
    if place["category"] == "designated_city_ward" and abr["city"] and abr["ward"]:
        fields["municipality"].extend([abr["city"], abr["city_kana"]])
        fields["city_district"] = [abr["ward"], abr["ward_kana"]]
    elif place["category"] == "special_ward" and abr["city"] and not abr["ward"]:
        # Tokyo's special ward is itself the municipality.
        fields["city_district"] = [abr["city"], abr["city_kana"]]
    else:
        return None
    return {"source_id": "jp-abr-snapshot", "source_row": path + "#lg_code=" + place["lg_code"],
            "category": place["category"]}


def _jp_sources(root, code):
    sources = [s for s in load_sources(root)["sources"]
               if s["format"] in {"japanpost_utf_zip", "japanpost_business_zip"}
               and s.get("active_for_lookup", True)]
    if {s["format"] for s in sources} != {"japanpost_utf_zip", "japanpost_business_zip"}:
        raise ValueError("missing active Japan Post source")
    wards, ward_source = _jp_wards(root)
    candidates = []
    receipts = {}
    for source in sources:
        receipts[source["id"]] = {"published_on": source["published_on"],
                                  "sha256": source["sha256"], "url": source["download_url"]}
        for row in iter_postal_records(source, root):
            if row["code"] != code:
                continue
            town = row["place_name"]
            use = row.get("postal_use", "ordinary")
            fields = {"prefecture": [row["admin_name1"]], "municipality": [row["admin_name2"]]}
            candidate = {"source_id": source["id"], "source_row": row["source_row"],
                         "source_code": code, "postal_use": use, "labels": fields}
            if use == "ordinary":
                fields["prefecture"].append(row["source_col_4"])
                fields["municipality"].append(row["source_col_5"])
                # General delivery instructions cannot prove an individual town.
                whole_area = town.removesuffix("一円")
                whole_municipality = (whole_area != town and bool(whole_area)
                                      and row["admin_name2"].endswith(whole_area))
                if town == "以下に掲載がない場合" or whole_municipality or JP_NUMBER_INSTRUCTION.fullmatch(town):
                    candidate["postal_instruction"] = {"ja": town, "ja-Kana": row["source_col_6"]}
                else:
                    fields["town"] = [town, row["source_col_6"]]
            else:
                fields["organization"] = [row["organization"]]
                if town:
                    fields["town"] = [town]
            ward_link = _jp_ward_labels(wards.get(row["admin_code2"]), row, fields)
            if ward_link:
                candidate["ward_evidence"] = ward_link
                receipts["jp-abr-snapshot"] = ward_source
            candidates.append(candidate)
    return candidates, receipts


def _tw_source(root, code):
    folder = root / "registries/official/TW"
    source_id = "tw-chunghwa-names"
    source = json.loads((folder / "sources.json").read_text(encoding="utf-8"))["sources"][source_id]
    raw = (folder / "sources/names.xml").read_bytes()
    if len(raw) != source["bytes"] or hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise ValueError("Chunghwa Post source checksum mismatch")
    candidates = []
    for number, row in enumerate(ET.fromstring(raw), 1):
        if row.findtext("欄位1") != code[:3]:
            continue
        zh, en = row.findtext("欄位2"), row.findtext("欄位3")
        labels = {"postal_area": [zh, en]}
        # Ordinary rows provide a city/county followed by its postal locality
        # in Chinese and a comma-separated locality and parent in English.
        # Keep island and other exceptional labels whole.
        zh_parts = re.fullmatch(r"([^市縣]+([市縣]))(.+)", zh)
        en_parts = en.split(", ")
        if zh_parts and len(en_parts) == 2:
            suffix = " City" if zh_parts[2] == "市" else " County"
            if en_parts[1].endswith(suffix):
                labels["city_or_county"] = [zh_parts[1], en_parts[1]]
                labels["postal_locality"] = [zh_parts[3], en_parts[0]]
        candidates.append({"source_id": source_id, "source_row": str(number),
                           "source_code": code[:3], "postal_use": "area_prefix", "labels": labels})
    return candidates, {source_id: {key: source[key] for key in ("published_on", "sha256", "url")}}


def validate_postal_address(country, code, components, *, include_prefix=False, root=ROOT):
    """Check only supplied place labels and the postal use captured in a fixed source."""
    if country not in {"JP", "TW"}:
        raise ValueError("postal address comparison supports JP and TW")
    if country == "TW" and not include_prefix:
        raise ValueError("TW comparison requires --include-prefix")
    if not isinstance(components, dict) or not all(
        isinstance(k, str) and k.strip() and isinstance(v, str) and v.strip()
        for k, v in components.items()
    ):
        raise ValueError("components must be an object with nonempty string keys and values")

    normalized = _code(country, code)
    if "country_code" in components and components["country_code"].upper() != country:
        raise ValueError("component country_code differs from country")
    for name in ("postcode", "postal_code"):
        if name in components and (normalized is None or _code(country, components[name]) != normalized):
            raise ValueError("component postal code differs from postal code")
    if country == "JP":
        aliases = {"state": "prefecture", "city": "municipality", "ward": "city_district",
                   "district": "city_district"}
    else:
        aliases = {"city": "city_or_county", "county": "city_or_county",
                   "city_district": "postal_locality", "district": "postal_locality"}
    allowed = JP_FIELDS if country == "JP" else TW_FIELDS
    query = {}
    unchecked = []
    for name, value in components.items():
        if name in {"country_code", "postcode", "postal_code"}:
            continue
        field = aliases.get(name, name)
        if field not in allowed:
            unchecked.append(name)
        elif field in query and query[field] != _label(value):
            raise ValueError(f"conflicting values for {field}")
        else:
            query[field] = _label(value)

    result = {"country": country, "input_code": code, "input_components": dict(components),
              "normalized_code": normalized, "match_scope": "full" if country == "JP" else "prefix",
              "status": "invalid_format", "complete_postcode_observed": False,
              "delivery_verified": False, "checked_scope": "postcode_and_source_place_labels",
              "requested_fields": sorted(query), "unchecked_fields": sorted(unchecked),
              "postal_source_rows": 0, "matching_rows": 0, "candidates": [], "sources": {}}
    if normalized is None:
        return result
    candidates, sources = (_jp_sources(Path(root), normalized) if country == "JP"
                           else _tw_source(Path(root), normalized))
    matched = unresolved = 0
    for row in candidates:
        missing = []
        conflicting = []
        for field, value in query.items():
            labels = row["labels"].get(field)
            if not labels:
                missing.append(field)
            elif value not in {_label(label) for label in labels}:
                # A town shared by several chome, number ranges or buildings
                # is compatible with the base label, but its qualifier matters.
                if (field == "municipality" and "city_district" in query
                        and "city_district" not in row["labels"]
                        and any(label.startswith(value) for label in labels)):
                    missing.append(field)
                elif field == "town" and any(
                    label.endswith("）") and "（" in label and _label(label.split("（", 1)[0]) == value
                    for label in labels
                ):
                    missing.append(field)
                else:
                    conflicting.append(field)
        if row["postal_use"] in {"business", "po_box"} and "organization" not in query:
            missing.append("organization")
        row["unverified_fields"] = sorted(missing)
        row["conflicting_fields"] = sorted(conflicting)
        if conflicting:
            row["status"] = "no_match_in_source"
        elif missing or not query:
            row["status"] = "insufficient_evidence"
            unresolved += 1
        else:
            row["status"] = "matched"
            matched += 1
    if not candidates:
        status = "postcode_not_observed"
    elif matched:
        status = "matched" if matched + unresolved == 1 else "ambiguous"
    elif unresolved:
        status = "insufficient_evidence"
    else:
        status = "no_match_in_source"
    result.update(status=status, complete_postcode_observed=country == "JP" and bool(candidates),
                  postal_source_rows=len(candidates), matching_rows=matched,
                  candidates=candidates, sources=sources)
    return result
