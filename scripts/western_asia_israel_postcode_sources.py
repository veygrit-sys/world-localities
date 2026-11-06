#!/usr/bin/env python3
"""Audit Israeli house-level historical ZIP7 XLSX and official street-code CSV.

Offline import of explicitly supplied raw files with required SHA256 pins.
The 2020 ZIP7 data is a third-party collection, NOT a current Israel Post
delivery certification. Government street IDs are NOT postal codes and must
not be joined to ZIP7 LocationID/StreetID without reviewed ID provenance.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "registries/official/western-asia/caucasus-levant/original-source-acquisition.json"
XLSX_SOURCE = "IL-ODATA-ZIP7-2020"
STREETS_SOURCE = "IL-STREETS-2026"
LIMIT_PER_XML_FILE = 400 * 1024 * 1024
LIMIT_TOTAL_UNCOMPRESSED = 1024 * 1024 * 1024
OOXML_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REQUIRED_HOUSE = frozenset({"locationid", "streetid", "housenumber", "zip7"})
REQUIRED_STREET = frozenset({"city_code", "street_code", "street_name", "official_code"})
DISALLOWED_BIDI = re.compile(r"[\u202a-\u202e\u2066-\u2069]")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_catalogue(path: Path = CATALOGUE) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("status") != "source_catalogue_only_original_files_not_acquired":
        raise ValueError("Source catalogue may not claim an imported official original")
    by_id = {r["id"]: r for r in data["entries"]}
    if len(by_id) != len(data["entries"]) or set((XLSX_SOURCE, STREETS_SOURCE)) - set(by_id):
        raise ValueError("Missing/duplicate Israel source catalogue entries")
    for source in data["entries"]:
        if source.get("downloaded") is not False or source.get("sha256") is not None:
            raise ValueError("Unacquired official originals must remain marked absent")
    if by_id[XLSX_SOURCE].get("authoritative_current_postal_operator_dataset") is not False:
        raise ValueError("OData 2020 is third-party historical postal evidence")
    return by_id


def verified_bytes(path: Path, expected_sha256: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Exact lower-case SHA256 pin required")
    if not path.is_file():
        raise ValueError("Source file missing")
    raw = path.read_bytes()
    if digest(raw) != expected_sha256:
        raise ValueError("Source input differs from SHA256 pin")
    return raw


def header_key(text: str) -> str:
    return re.sub(r"[\s_-]+", "", unicodedata.normalize("NFKC", text).casefold())


def clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text.strip())
    if DISALLOWED_BIDI.search(text):
        raise ValueError("Potentially unsafe bidirectional control in raw source field")
    return text


def _xlsx_headers(first: list[str]) -> dict[str, int]:
    mapping = {header_key(v): i for i, v in enumerate(first) if v.strip()}
    if not REQUIRED_HOUSE.issubset(mapping) or len(mapping) != sum(bool(v.strip()) for v in first):
        raise ValueError("Missing/duplicated mandatory XLSX source headers")
    return mapping


def _spreadsheet_rows(raw: bytes):
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        raise ValueError("Input is not a valid XLSX ZIP container")
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        files = {info.filename: info for info in archive.infolist()}
        if len(files) != len(archive.infolist()):
            raise ValueError("Duplicate OOXML member names")
        if any(info.file_size > LIMIT_PER_XML_FILE and info.filename.endswith(".xml")
               for info in files.values()):
            raise ValueError("Unusually large uncompressed XML component")
        if sum(info.file_size for info in files.values()) > LIMIT_TOTAL_UNCOMPRESSED:
            raise ValueError("Unusually large source workbook")
        sheets = sorted(name for name in files if re.fullmatch(r"xl/worksheets/sheet[0-9]+\.xml", name))
        if not sheets:
            raise ValueError("No worksheet XML found")
        strings = []
        if "xl/sharedStrings.xml" in files:
            with archive.open("xl/sharedStrings.xml") as file:
                for event, el in ET.iterparse(file, events=("end",)):
                    if el.tag == OOXML_MAIN + "si":
                        strings.append("".join(t.text or "" for t in el.iter(OOXML_MAIN + "t")))
                        el.clear()
        # Historical source uses the first worksheet. Future multi-sheet files
        # must be inspected independently; this importer never merges sheets.
        with archive.open(sheets[0]) as file:
            for event, el in ET.iterparse(file, events=("end",)):
                if el.tag != OOXML_MAIN + "row":
                    continue
                values = {}
                for cell in el.findall(OOXML_MAIN + "c"):
                    match = re.fullmatch(r"([A-Z]+)[0-9]+", cell.attrib.get("r", ""))
                    if not match:
                        raise ValueError("Malformed OOXML cell reference")
                    index = 0
                    for letter in match.group(1):
                        index = index * 26 + ord(letter) - 64
                    index -= 1
                    kind = cell.attrib.get("t")
                    if kind == "inlineStr":
                        inline = cell.find(OOXML_MAIN + "is")
                        value = "" if inline is None else "".join(
                            v.text or "" for v in inline.iter(OOXML_MAIN + "t"))
                    else:
                        v = cell.find(OOXML_MAIN + "v")
                        value = v.text if v is not None and v.text is not None else ""
                        if kind == "s" and value:
                            pos = int(value)
                            if pos < 0 or pos >= len(strings):
                                raise ValueError("Shared string index out of bounds")
                            value = strings[pos]
                    if index in values:
                        raise ValueError("Duplicate source cell column")
                    values[index] = clean(value)
                if values:
                    yield [values.get(i, "") for i in range(max(values) + 1)]
                el.clear()


def audit_house_workbook(raw: bytes) -> dict:
    items = _spreadsheet_rows(raw)
    try:
        header = next(items)
    except StopIteration:
        raise ValueError("Empty historic ZIP7 workbook")
    key = _xlsx_headers(header)
    counters = Counter()
    seen_addresses: dict[tuple[str, str, str, str], str] = {}
    distinct_zip7: set[str] = set()
    city_codes: set[str] = set()
    for row in items:
        counters["rows"] += 1
        def field(name):
            pos = key[name]
            return row[pos] if pos < len(row) else ""
        loc, street, house, entrance = (field("locationid"), field("streetid"),
                                       field("housenumber"),
                                       row[key["entrance"]] if "entrance" in key and key["entrance"] < len(row) else "")
        zip7 = field("zip7")
        if not loc or not street or not house:
            counters["incomplete_address_key"] += 1
            continue
        city_codes.add(loc)
        if not re.fullmatch(r"[0-9]{7}", zip7):
            if zip7:
                counters["invalid_zip7_length_or_encoding"] += 1
                if re.fullmatch(r"[0-9]{1,6}", zip7):
                    counters["may_have_lost_leading_zero_in_excel"] += 1
            else:
                counters["missing_zip7"] += 1
            continue
        distinct_zip7.add(zip7)
        key_tuple = (loc, street, house, entrance)
        if key_tuple in seen_addresses:
            counters["repeat_address_key"] += 1
            if seen_addresses[key_tuple] != zip7:
                counters["conflicting_zip7_for_same_address_key"] += 1
        else:
            seen_addresses[key_tuple] = zip7
        counters["valid_zip7_shape"] += 1
    return {"source_grain": "historical_address_building_entrance",
            "source_rows": counters["rows"], "columns": [s for s in header if s],
            "counts": dict(sorted(counters.items())),
            "distinct_valid_zip7": len(distinct_zip7),
            "distinct_location_id": len(city_codes),
            "unique_source_address_keys": len(seen_addresses),
            "address_key_source_is_2020_third_party": True,
            "current_israel_post_official_verification": False,
            "postal_to_geonames_verified": False,
            "delivery_verified": False,
            "raw_address_rows_exported": 0}


def audit_street_csv(raw: bytes) -> dict:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Official streets CSV must use UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames or not REQUIRED_STREET.issubset(reader.fieldnames):
        raise ValueError("Required government streets columns missing")
    counters = Counter()
    city_keys = set()
    code_keys = set()
    official_seen = set()
    synonyms = []
    for row in reader:
        counters["rows"] += 1
        city = clean(row["city_code"])
        street = clean(row["street_code"])
        official = clean(row["official_code"])
        name = clean(row["street_name"])
        status = clean(row.get("street_name_status") or "")
        if not city or not street or not name or not official:
            counters["missing_primary_fields"] += 1
            continue
        city_keys.add(city)
        key = (city, street)
        if key in code_keys:
            counters["duplicate_city_street_key"] += 1
        code_keys.add(key)
        if status == "official":
            official_seen.add((city, official))
            counters["official_name_rows"] += 1
        elif status.startswith("synonym"):
            synonyms.append((city, official))
            counters["synonym_rows"] += 1
        else:
            counters["other_status_rows"] += 1
    counters["synonym_missing_canonical_in_csv"] = sum(k not in official_seen for k in synonyms)
    return {"source_grain": "government_city_street_code_and_alias",
            "source_rows": counters["rows"], "columns": list(reader.fieldnames),
            "distinct_city_codes": len(city_keys),
            "distinct_city_street_codes": len(code_keys),
            "counts": dict(sorted(counters.items())),
            "street_code_is_not_postcode": True,
            "location_id_equivalent_to_2020_zip_source_verified": False,
            "postal_to_geonames_verified": False,
            "building_address_verified": False,
            "raw_street_rows_exported": 0}


def audit_file(path: Path, expected_sha256: str, source_id: str,
               *, catalogue: dict | None = None) -> dict:
    sources = catalogue or read_catalogue()
    if source_id not in (XLSX_SOURCE, STREETS_SOURCE) or source_id not in sources:
        raise ValueError("Unsupported Israel original-data source identifier")
    raw = verified_bytes(path, expected_sha256)
    result = (audit_house_workbook(raw) if source_id == XLSX_SOURCE
              else audit_street_csv(raw))
    return {"country": "IL", "source_id": source_id, "input_sha256": expected_sha256,
            "input_bytes": len(raw), "source_url": sources[source_id]["url"],
            "publisher": sources[source_id]["publisher"],
            "source_last_updated": sources[source_id]["last_updated"],
            "source_format": sources[source_id]["format"],
            "audit_only": True, "original_bytes_stored_in_repo": False,
            **result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("catalogue", "audit"))
    parser.add_argument("--source-id", choices=(XLSX_SOURCE, STREETS_SOURCE))
    parser.add_argument("--file", type=Path)
    parser.add_argument("--sha256")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "catalogue":
        data = {"country": "IL", "available_originals": False,
                "source_entries": [read_catalogue()[k] for k in (XLSX_SOURCE, STREETS_SOURCE)]}
    else:
        if not args.source_id or not args.file or not args.sha256:
            parser.error("Audit requires --source-id, --file, --sha256")
        data = audit_file(args.file, args.sha256, args.source_id)
    text = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(exist_ok=True, parents=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
