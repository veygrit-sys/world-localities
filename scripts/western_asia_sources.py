#!/usr/bin/env python3
"""Replay, audit and search pinned Western Asia source layers without merging IDs.

All commands work offline. Official postal assignments, humanitarian P-codes,
statistical units and GeoNames entities retain independent namespaces and dates.
Only the Python standard library is needed, including for XLSX source replay.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timedelta
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "registries/official/western-asia/imports"
COUNTRIES = tuple("AE AM AZ BH CY GE IL IQ JO KW LB OM PS QA SA SY TR YE".split())
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
XML_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def text(value) -> str:
    return str(value).strip() if value is not None else ""


def key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def safe_path(base: Path, relative: str) -> Path:
    rel = PurePosixPath(relative)
    if not relative or rel.is_absolute() or ".." in rel.parts or "\\" in relative:
        raise ValueError("Unsafe source path")
    path = (base / relative).resolve()
    if not path.is_relative_to(base.resolve()):
        raise ValueError("Source path escapes registry")
    return path


def read_pinned(base: Path, item: dict) -> bytes:
    packed = safe_path(base, item["path"]).read_bytes()
    if len(packed) != item["bytes"] or sha(packed) != item["sha256"]:
        raise ValueError("Stored source checksum mismatch: " + item["path"])
    raw = gzip.decompress(packed) if item.get("compression") == "gzip" else packed
    if len(raw) != item["original_bytes"] or sha(raw) != item["original_sha256"]:
        raise ValueError("Original source checksum mismatch: " + item["path"])
    return raw


def xlsx_rows(raw: bytes):
    """Read strings/numeric source values, preserving textual codes and row numbers.

    Does not trust worksheet dimensions (several COD files omit them), evaluate
    formulas, extract paths, fetch external links, or coerce codes through floats.
    """
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if sum(i.file_size for i in z.infolist()) > 150_000_000:
            raise ValueError("XLSX expanded size exceeds source contract")
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in n.findall(".//s:t", NS))
                      for n in root.findall("s:si", NS)]
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        targets = {r.attrib["Id"]: r.attrib["Target"] for r in rels}
        book = ET.fromstring(z.read("xl/workbook.xml"))
        for sheet in book.findall("s:sheets/s:sheet", NS):
            target = targets[sheet.attrib[XML_REL]]
            path = target.lstrip("/") if target.startswith("/") else "xl/" + target
            if ".." in PurePosixPath(path).parts:
                raise ValueError("Unsafe workbook relationship")
            for event, row in ET.iterparse(io.BytesIO(z.read(path)), events=("end",)):
                if row.tag != "{" + NS["s"] + "}row":
                    continue
                cells = {}
                for c in row.findall("s:c", NS):
                    address = c.attrib.get("r", "")
                    match = re.fullmatch(r"([A-Z]+)[0-9]+", address)
                    if not match:
                        raise ValueError("Cell address absent in source XLSX")
                    col = 0
                    for char in match[1]:
                        col = col * 26 + ord(char) - 64
                    if col > 2000:
                        raise ValueError("Unexpected source column count")
                    v = c.find("s:v", NS)
                    typ = c.attrib.get("t")
                    if c.find("s:f", NS) is not None:
                        # Formula text is not an official computed value.
                        value = ""
                    elif typ == "s":
                        value = shared[int(v.text)] if v is not None else ""
                    elif typ == "inlineStr":
                        value = "".join(n.text or "" for n in c.findall("s:is//s:t", NS))
                    else:
                        value = v.text or "" if v is not None else ""
                    cells[col - 1] = value
                values = [cells.get(i, "") for i in range(max(cells, default=-1) + 1)]
                yield sheet.attrib["name"], int(row.attrib["r"]), values
                row.clear()


def source_record(spec: dict, position: str, grain: str, *, names=None,
                  source_code="", postcode="", postal_kind="", parents=None,
                  payload=None, **extra) -> dict:
    return {
        "record_id": spec["id"] + ":" + position,
        "source_id": spec["id"], "catalogue_country": spec["country"],
        "source_position": position, "grain": grain,
        "names": {lang: text(name) for lang, name in (names or {}).items() if text(name)},
        "source_code": text(source_code), "postcode": text(postcode),
        "postal_kind": postal_kind, "parents": parents or {},
        "source_payload": payload or {},
        "government_geonames_identity_verified": False,
        "carrier_deliverability_verified": False, **extra,
    }


def parse_hdx(spec: dict, raw: bytes):
    headers = {}
    count = 0
    for sheet, number, values in xlsx_rows(raw):
        match = re.fullmatch(r"[a-z]{3}_admin([0-3])", sheet)
        if not match:
            continue  # Ignore duplicated _em geometries, adminpoints and boundary lines.
        if number == 1:
            headers[sheet] = values
            continue
        if not any(values):
            continue
        row = dict(zip(headers[sheet], values))
        level = int(match[1])
        prefix = "adm" + str(level)
        if not row.get(prefix + "_pcode") or not row.get(prefix + "_name"):
            raise ValueError("COD source lacks its explicit administrative code/name")
        names = {}
        for suffix, langfield in (("", "lang"), ("1", "lang1"), ("2", "lang2"), ("3", "lang3")):
            language = row.get(langfield)
            value = row.get(prefix + "_name" + suffix)
            if language and value:
                names[language] = value
        if not names:
            names["und"] = row[prefix + "_name"]
        parents = {"admin" + str(i): row["adm" + str(i) + "_pcode"]
                   for i in range(level) if row.get("adm" + str(i) + "_pcode")}
        date = row.get("valid_on", "")
        if re.fullmatch(r"[0-9]+(?:\.0+)?", date):
            date = (datetime(1899, 12, 30) + timedelta(days=int(float(date)))).date().isoformat()
        count += 1
        yield source_record(spec, sheet + ":" + str(number), "admin" + str(level),
                            names=names, source_code=row[prefix + "_pcode"], parents=parents,
                            payload=row, code_scheme="humanitarian_pcode_not_postcode",
                            valid_on=date, valid_to=row.get("valid_to", ""))
    if not count:
        raise ValueError("No supported COD administrative tables")


def parse_cy_directory(spec: dict, raw: bytes):
    maps = {
        "Δρόμοι ΕΛ_Streets ENG": ("street", 1, 2, 4, 5, 6, 7, 8),
        "Κοινότητες_Communities": ("postal_area", 1, 2, 3, 1, 2, 4, 5),
        "Κυβερνητικές Αρχές_Gov. Author.": ("government_address", 1, 2, 7, 5, 6, 8, 9),
        "Ι.Τ.Θυρίδες_P.O.Boxes": ("po_box", 1, 2, 4, 5, 6, 7, 8),
    }
    count = 0
    for sheet, number, v in xlsx_rows(raw):
        if sheet in {"Parcel 24", "Ταχυδρ. Γραφεία_Post Offices"} and number != 1 and any(v):
            v += [""] * max(0, 12 - len(v))
            if not v[0]:
                continue
            is_office = sheet != "Parcel 24"
            yield source_record(spec, sheet + ":" + str(number),
                                "post_office" if is_office else "parcel_locker",
                                names={"el": v[1], "en": v[6] if is_office else v[5]},
                                source_code=v[0], payload={"cells": v},
                                code_scheme="directory_row_not_postcode")
            count += 1
            continue
        if sheet not in maps or number == 1 or not any(v):
            continue
        grain, gr, en, pc, mgr, men, dgr, den = maps[sheet]
        v += [""] * max(0, 14 - len(v))
        if not v[0] or not (v[gr] or v[en]):
            raise ValueError("Cyprus directory contains a malformed source row")
        code = v[pc]
        assigned = bool(re.fullmatch(r"[0-9]{4}", code))
        payload = {"cells": v, "municipality_gr": v[mgr], "municipality_en": v[men],
                   "district_gr": v[dgr], "district_en": v[den]}
        count += 1
        yield source_record(spec, sheet + ":" + str(number), grain,
                            names={"el": v[gr], "en": v[en]}, source_code=v[0],
                            postcode=code if assigned else "",
                            postal_kind="po_box" if grain == "po_box" else grain,
                            payload=payload,
                            source_postal_value_published=assigned,
                            postal_value_issue="" if assigned else "non_code_source_value",
                            municipality_names={"el": v[mgr], "en": v[men]})
    if count < 1000:
        raise ValueError("Cyprus directory unexpectedly small")


def parse_cy_areas(spec: dict, raw: bytes):
    rows = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    if not {"Postal Code", "Municipality_Community_EN", "District_EN"}.issubset(rows.fieldnames or []):
        raise ValueError("Cyprus municipality CSV schema changed")
    for number, row in enumerate(rows, 2):
        if not re.fullmatch(r"[0-9]{4}", row["Postal Code"]):
            raise ValueError("Invalid original Cyprus postcode")
        yield source_record(spec, str(number), "postal_area",
                            names={"el": row["Municipality_Community_GR"], "en": row["Municipality_Community_EN"]},
                            postcode=row["Postal Code"], postal_kind="postal_area", payload=row,
                            source_postal_value_published=True)


def parse_il_cities(spec: dict, raw: bytes):
    data = json.loads(raw)
    result = data.get("result", {})
    records = result.get("records", [])
    if data.get("success") is not True or len(records) != result.get("total"):
        raise ValueError("Israel locality API capture is unsuccessful or truncated")
    for row in records:
        required = {"_id", "city_code", "city_name_he", "city_name_en", "region_code"}
        if not required.issubset(row):
            raise ValueError("Israel locality schema changed")
        yield source_record(spec, str(row["_id"]), "locality",
                            names={"he": row["city_name_he"], "en": row["city_name_en"]},
                            source_code=row["city_code"], payload=row,
                            parents={"publisher_region": text(row["region_code"])},
                            code_scheme="PIBA_locality_not_postcode",
                            jurisdiction_scope="publisher_table_no_territorial_reclassification")


def parse_jo_offices(spec: dict, raw: bytes):
    values = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline="")))
    header = next((i for i, r in enumerate(values) if "الرمز البريدي" in r and "اسم مكتب البريد" in r), None)
    if header is None:
        raise ValueError("Jordan file is not the postcode-bearing office directory")
    count = 0
    for number, v in enumerate(values[header + 1:], header + 2):
        if not any(text(x) for x in v):
            continue
        row = dict(zip(values[header], v))
        name = text(row.get("اسم مكتب البريد"))
        code = text(row.get("الرمز البريدي"))
        if not name:
            raise ValueError("Jordan office name absent")
        assigned = bool(re.fullmatch(r"[0-9]{5}", code))
        count += 1
        yield source_record(spec, str(number), "post_office", names={"ar": name},
                            postcode=code if assigned else "", postal_kind="post_office",
                            payload=row, source_postal_value_published=assigned,
                            postal_value_issue="" if assigned else "missing_or_invalid_postcode",
                            source_governorate=text(row.get("المحافظة")))
    if count < 100:
        raise ValueError("Jordan office directory unexpectedly small")


def parse_lb(spec: dict, raw: bytes):
    data = json.loads(raw)
    if data.get("error") or data.get("exceededTransferLimit") or not data.get("features"):
        raise ValueError("Lebanon source query failed or was truncated")
    level = spec["admin_level"]
    codefield = "ADM" + str(level) + "_CODE"
    for i, feature in enumerate(data["features"], 1):
        row = feature["attributes"]
        yield source_record(spec, str(i), "admin" + str(level),
                            names={"ar": row.get("NAME_AR"), "en": row.get("NAME_EN")},
                            source_code=row.get(codefield), payload=row,
                            parents={"admin" + str(j): text(row.get("ADM" + str(j) + "_CODE"))
                                     for j in range(level)},
                            code_scheme="CDR_OCHA_administrative_not_postcode")


def parse_ge(spec: dict, raw: bytes):
    headers = {}
    for sheet, number, v in xlsx_rows(raw):
        if number == 4:
            headers[sheet] = v
            continue
        if number <= 4 or not v or not v[0] or len(v) < 2:
            continue
        if not any(re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", x) for x in v[1:] if x):
            continue  # Footnotes never become locality rows.
        name = v[0]
        grain = "statistical_unit" if spec["parser"] == "ge_units" else "statistical_settlement"
        if "Municipality" in name:
            grain = "municipality_statistic"
        elif name.startswith("C. ") or name.startswith("Borough "):
            grain = "locality"
        payload = dict(zip(headers[sheet], v))
        search = re.sub(r"^(?:C\. |Borough )", "", name)
        search = re.sub(r" Municipality(?:\*+)?$", "", search)
        yield source_record(spec, sheet + ":" + str(number), grain,
                            names={"en": name}, payload=payload,
                            search_name=search, source_code_is_not_supplied=True,
                            latest_year_with_value=max((int(y) for y, value in payload.items()
                                if re.fullmatch(r"20[0-9]{2}", y) and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value)), default=None))


def parse_bh(spec: dict, raw: bytes):
    rows = json.loads(raw)
    if not isinstance(rows, list) or not rows:
        raise ValueError("Bahrain statistics export is empty")
    latest = max(text(r["year"]) for r in rows)
    for i, row in enumerate(rows, 1):
        if not {"year", "governorate", "lmhfz", "value"}.issubset(row):
            raise ValueError("Bahrain statistics schema changed")
        yield source_record(spec, str(i), "governorate_statistic",
                            names={"en": row["governorate"], "ar": row["lmhfz"]},
                            payload=row, source_code_is_not_supplied=True,
                            reference_year=text(row["year"]),
                            latest_period_governorate=(text(row["year"]) == latest and row["governorate"] != "Total"))


def parse_syria_reference(spec: dict, raw: bytes):
    """Reuse the existing community projection, retaining its original local IDs."""
    files = json.loads(raw)
    for path, document in sorted(files.items()):
        if path.endswith("admin-levels.json"):
            for row in document["records"]:
                level = {"governorate": 1, "district": 2, "subdistrict": 3}[row["kind"]]
                yield source_record(spec, row["id"], "admin" + str(level),
                                    names=row["name"], source_code=row["id"], payload=row,
                                    code_scheme="OpenSyria_community_id_not_postcode",
                                    parents={k: v for k, v in row.items() if k in {"governorate_id", "district_id"} and v},
                                    upstream_geonames_id_is_unreviewed=True)
        elif "/localities/" in path:
            for values in document["rows"]:
                row = dict(zip(document["fields"], values))
                yield source_record(spec, row["id"], "locality",
                                    names={"en": row["en"], "ar": row["ar"]},
                                    source_code=row["id"], payload=row,
                                    parents={k: row[k] for k in ("district_id", "subdistrict_id")},
                                    code_scheme="OpenSyria_community_id_not_postcode",
                                    upstream_geonames_id_is_unreviewed=True)


PARSERS = {"hdx_xlsx": parse_hdx, "cy_directory": parse_cy_directory,
           "cy_areas": parse_cy_areas, "il_cities": parse_il_cities,
           "jo_offices": parse_jo_offices, "lb_attributes": parse_lb,
           "ge_units": parse_ge, "ge_cities": parse_ge, "bh_statistics": parse_bh,
           "sy_reference": parse_syria_reference}


def load_manifest(base: Path = DATA) -> dict:
    data = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or set(data.get("country_scope", [])) != set(COUNTRIES):
        raise ValueError("Western Asia source manifest scope changed")
    ids = [s["id"] for s in data["sources"]]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate source ID")
    for spec in data["sources"]:
        if spec["country"] not in COUNTRIES or spec["parser"] not in PARSERS:
            raise ValueError("Unsupported source country/parser")
        if not spec["url"].startswith("https://") or not spec.get("rights"):
            raise ValueError("Source origin or rights evidence missing")
    return data


def replay(spec: dict, base: Path = DATA):
    if spec["parser"] == "sy_reference":
        documents = {}
        for item in spec["repository_files"]:
            raw = safe_path(base.resolve().parents[3], item["path"]).read_bytes()
            if sha(raw) != item["sha256"] or len(raw) != item["bytes"]:
                raise ValueError("Reused Syria projection checksum mismatch")
            documents[item["path"]] = json.loads(raw)
        return parse_syria_reference(spec, canonical(documents))
    raw = read_pinned(base, spec["original"])
    return PARSERS[spec["parser"]](spec, raw)


def write_records(path: Path, rows) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    count, h = 0, hashlib.sha256()
    with path.open("wb") as f, gzip.GzipFile(fileobj=f, mode="wb", mtime=0, filename="") as g:
        for row in rows:
            raw = canonical(row)
            h.update(raw)
            g.write(raw)
            count += 1
    raw = path.read_bytes()
    return {"path": "records/" + path.name, "sha256": sha(raw), "bytes": len(raw),
            "record_stream_sha256": h.hexdigest(), "records": count}


def normalized(spec: dict, base: Path = DATA):
    item = spec["normalized"]
    packed = safe_path(base, item["path"]).read_bytes()
    if len(packed) != item["bytes"] or sha(packed) != item["sha256"]:
        raise ValueError("Normalized source checksum mismatch: " + spec["id"])
    raw = gzip.decompress(packed)
    if sha(raw) != item["record_stream_sha256"]:
        raise ValueError("Normalized record-stream checksum mismatch")
    for line in raw.splitlines():
        yield json.loads(line)


def verify_sources(base: Path = DATA, *, replay_originals: bool = True, country: str | None = None) -> dict:
    manifest = load_manifest(base)
    if country is not None and country not in COUNTRIES:
        raise ValueError("Unsupported Western Asia country")
    if replay_originals and country is None:
        for item in manifest.get("supporting_evidence", []):
            read_pinned(base, item)
    summaries = []
    selected = [s for s in manifest["sources"] if country is None or s["country"] == country]
    for spec in selected:
        if replay_originals and spec.get("catalogue_evidence"):
            read_pinned(base, spec["catalogue_evidence"])
        rows = list(normalized(spec, base))
        if len(rows) != spec["normalized"]["records"] or len({r["record_id"] for r in rows}) != len(rows):
            raise ValueError("Source normalized count/record IDs changed")
        if any(r["source_id"] != spec["id"] or r["catalogue_country"] != spec["country"] for r in rows):
            raise ValueError("Source record provenance mismatch")
        if any(r["government_geonames_identity_verified"] or r["carrier_deliverability_verified"] for r in rows):
            raise ValueError("Unreviewed source claims verified identity/delivery")
        if replay_originals:
            h = hashlib.sha256()
            replay_count = 0
            for record in replay(spec, base):
                h.update(canonical(record))
                replay_count += 1
            if h.hexdigest() != spec["normalized"]["record_stream_sha256"] or replay_count != len(rows):
                raise ValueError("Source replay differs from normalized data: " + spec["id"])
        summaries.append({"source_id": spec["id"], "country": spec["country"], "records": len(rows),
                          "grain_counts": dict(sorted(Counter(r["grain"] for r in rows).items())),
                          "source_postal_rows": sum(bool(r["postcode"]) for r in rows)})
    return {"status": "passed", "source_originals_replayed": replay_originals,
            "country": country,
            "acquired_original_files": sum(s["parser"] != "sy_reference" for s in selected),
            "reused_community_snapshots": sum(s["parser"] == "sy_reference" for s in selected),
            "sources": summaries, "records": sum(r["records"] for r in summaries),
            "national_completeness_verified": False, "deliverability_verified": False}


def gazetteer(country: str):
    inv = json.loads((ROOT / "registries/asia/archives.json").read_text(encoding="utf-8"))
    spec = next(x for x in inv["archives"] if x["country"] == country)
    pieces = []
    for part in spec["parts"]:
        raw = safe_path(ROOT / "registries/asia", part["path"]).read_bytes()
        if len(raw) != part["bytes"] or sha(raw) != part["sha256"]:
            raise ValueError("GeoNames archive part mismatch")
        pieces.append(raw)
    packed = b"".join(pieces)
    if sha(packed) != spec["sha256"]:
        raise ValueError("GeoNames archive checksum mismatch")
    member = country + "/entities.csv.gz"
    with zipfile.ZipFile(io.BytesIO(packed)) as z:
        data = z.read(member)
    if sha(data) != spec["members"][member]["sha256"]:
        raise ValueError("GeoNames entity checksum mismatch")
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(data).decode("utf-8"))))
    if len(rows) != spec["rows"] or len({r["id"] for r in rows}) != len(rows):
        raise ValueError("GeoNames count/duplicate ID failure")
    if any(r["country_code"] != country or not re.fullmatch(r"gn:[1-9][0-9]*", r["id"]) for r in rows):
        raise ValueError("GeoNames country/ID failure")
    return rows, spec


class CandidateIndex:
    def __init__(self, rows):
        self.rows = {r["id"]: r for r in rows}
        self.levels = {r["feature_code"] for r in rows if r["kind"] == "admin_subdivision"}
        self.names = defaultdict(set)
        for r in rows:
            if r["kind"] not in ("locality", "admin_subdivision"):
                continue
            for n in (r["name"], r["asciiname"], *(r.get("alternatenames") or "").split(",")):
                if n:
                    self.names[key(n)].add(r["id"])

    def match(self, record):
        grain = record["grain"]
        if grain in {"po_box", "street", "government_address", "post_office", "parcel_locker", "admin0"} or (
                grain == "governorate_statistic" and not record.get("latest_period_governorate")):
            # A street, office or P.O. box cannot be identified with a town.
            return {"status": "different_grain", "candidate_geonames_ids": [],
                    "government_identity_verified": False}
        level = grain[-1] if re.fullmatch(r"admin[0-3]", grain) else None
        if level is not None and "ADM" + level not in self.levels:
            return {"status": "grain_unavailable_in_gazetteer", "candidate_geonames_ids": [],
                    "government_identity_verified": False}
        names = list(record["names"].values()) + ([record["search_name"]] if record.get("search_name") else [])
        ids = set().union(*(self.names.get(key(n), set()) for n in names)) if names else set()
        if level is not None:
            ids = {gid for gid in ids if self.rows[gid]["feature_code"] == "ADM" + level}
        elif grain == "governorate_statistic":
            ids = {gid for gid in ids if self.rows[gid]["feature_code"] == "ADM1"}
        elif grain == "municipality_statistic":
            ids = {gid for gid in ids if self.rows[gid]["feature_code"] in {"ADM1", "ADM2"}}
        elif grain in {"locality", "postal_area", "statistical_settlement"}:
            ids = {gid for gid in ids if self.rows[gid]["kind"] == "locality" and self.rows[gid].get("address_candidate") == "1"}
        # Retain ambiguous evidence. No automatic fuzzy/coordinate/prefix match.
        matches = sorted(ids)
        return {"status": "unmatched" if not matches else "unique_unreviewed" if len(matches) == 1 else "ambiguous_unreviewed",
                "candidate_geonames_ids": matches, "government_identity_verified": False}


def audit(base: Path = DATA) -> dict:
    manifest = load_manifest(base)
    source_report = verify_sources(base)
    countries = []
    details = []
    for country in COUNTRIES:
        rows, spec = gazetteer(country)
        known = {r["id"] for r in rows}
        missing = Counter()
        for row in rows:
            for field in ("state_id", "parent_id"):
                if row.get(field) and row[field] not in known and row[field] != "country:" + country:
                    missing[field] += 1
        idx = CandidateIndex(rows)
        counts = Counter()
        source_ids = []
        source_rows = 0
        for source in manifest["sources"]:
            if source["country"] != country:
                continue
            source_ids.append(source["id"])
            records = list(normalized(source, base))
            source_rows += len(records)
            code_counts = Counter((r["grain"], r["source_code"]) for r in records if r["source_code"])
            by_level = defaultdict(set)
            for r in records:
                if re.fullmatch(r"admin[0-3]", r["grain"]):
                    by_level[r["grain"]].add(r["source_code"])
            # Lebanon administrative levels are three distinct endpoint captures.
            if source["parser"] == "lb_attributes":
                for other in manifest["sources"]:
                    if other["country"] == "LB" and other["parser"] == "lb_attributes":
                        for r in normalized(other, base):
                            by_level[r["grain"]].add(r["source_code"])
            duplicate_codes = {pair: n for pair, n in code_counts.items() if n > 1}
            dangling = []
            match_counts = Counter()
            for r in records:
                match = idx.match(r)
                match_counts[match["status"]] += 1
                counts[match["status"]] += 1
                for level, parent in r["parents"].items():
                    if level != "admin0" and level.startswith("admin") and parent and parent not in by_level[level]:
                        dangling.append({"record_id": r["record_id"], "parent_level": level, "parent_code": parent})
            details.append({"source_id": source["id"], "country": country,
                            "records": len(records), "candidate_counts": dict(sorted(match_counts.items())),
                            "distinct_source_codes_by_grain": dict(sorted(Counter(grain for grain, code in code_counts).items())),
                            "duplicate_source_codes": [{"grain": k[0], "code": k[1], "rows": v} for k, v in duplicate_codes.items()],
                            "unresolved_source_parents": dangling,
                            "source_postal_rows": sum(bool(r["postcode"]) for r in records),
                            "records_without_names": sum(not r["names"] for r in records)})
        countries.append({"country": country, "gazetteer_rows": len(rows),
                          "gazetteer_archive_sha256": spec["sha256"],
                          "source_ids": source_ids, "imported_source_rows": source_rows,
                          "candidate_counts": dict(sorted(counts.items())),
                          "gazetteer_dangling_parent_ids": dict(sorted(missing.items())),
                          "localities_without_state": sum(r["kind"] == "locality" and not r["state_id"] for r in rows),
                          "national_completeness_verified": False,
                          "official_to_geonames_identity_verified": 0,
                          "deliverability_verified": False})
    return {"schema_version": 1, "reviewed_at": manifest["reviewed_at"],
            "manifest_sha256": sha((base / "manifest.json").read_bytes()),
            "status": "sources_replayed_gaps_explicit", "countries": countries,
            "gazetteer_records": sum(c["gazetteer_rows"] for c in countries),
            "imported_source_records": source_report["records"], "source_audits": details,
            "source_originals_replayed": True,
            "complete_current_official_national_address_database": False}


def build_index(output: Path, base: Path = DATA) -> dict:
    if output.exists():
        raise ValueError("Choose a new output path; existing database is not overwritten")
    manifest = load_manifest(base)
    verify_sources(base, replay_originals=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(output)
    try:
        conn.executescript("""
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE entities (country TEXT NOT NULL, id TEXT NOT NULL, kind TEXT NOT NULL,
              name TEXT NOT NULL, state_id TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(country,id));
            CREATE TABLE source_records (country TEXT NOT NULL, id TEXT PRIMARY KEY, source_id TEXT NOT NULL,
              grain TEXT NOT NULL, source_code TEXT NOT NULL, postcode TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE names (country TEXT NOT NULL, layer TEXT NOT NULL, id TEXT NOT NULL,
              name_key TEXT NOT NULL, PRIMARY KEY(country,layer,id,name_key));
            CREATE INDEX names_lookup ON names(country,name_key);
            CREATE INDEX source_codes ON source_records(country,source_code);
            CREATE INDEX postcodes ON source_records(country,postcode);
        """)
        conn.execute("INSERT INTO metadata VALUES(?,?)", ("manifest_sha256", sha((base / "manifest.json").read_bytes())))
        for country in COUNTRIES:
            rows, _ = gazetteer(country)
            conn.executemany("INSERT INTO entities VALUES(?,?,?,?,?,?)", ((country, r["id"], r["kind"], r["name"], r["state_id"], canonical(r).decode()) for r in rows))
            conn.executemany("INSERT OR IGNORE INTO names VALUES(?,?,?,?)", ((country, "gazetteer", r["id"], key(n)) for r in rows for n in (r["name"], r["asciiname"], *(r.get("alternatenames") or "").split(",")) if n))
        for source in manifest["sources"]:
            rows = list(normalized(source, base))
            conn.executemany("INSERT INTO source_records VALUES(?,?,?,?,?,?,?)", ((r["catalogue_country"], r["record_id"], r["source_id"], r["grain"], r["source_code"], r["postcode"], canonical(r).decode()) for r in rows))
            conn.executemany("INSERT OR IGNORE INTO names VALUES(?,?,?,?)", ((r["catalogue_country"], "source", r["record_id"], key(n)) for r in rows for n in r["names"].values() if n))
        conn.commit()
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed")
        return {"status": "built", "gazetteer_records": conn.execute("SELECT count(*) FROM entities").fetchone()[0],
                "source_records": conn.execute("SELECT count(*) FROM source_records").fetchone()[0],
                "output": str(output), "deliverability_verified": False}
    except Exception:
        conn.close()
        output.unlink(missing_ok=True)
        raise
    finally:
        conn.close()


def query(db: Path, country: str, *, name=None, postcode=None, source_code=None, limit=20) -> dict:
    if country not in COUNTRIES or not 1 <= limit <= 100 or sum(v is not None for v in (name, postcode, source_code)) != 1:
        raise ValueError("Choose one name/postcode/source-code and a limit from 1 to 100")
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        expected = sha((DATA / "manifest.json").read_bytes())
        if conn.execute("SELECT value FROM metadata WHERE key='manifest_sha256'").fetchone()[0] != expected:
            raise ValueError("Database is stale; rebuild from the current manifest")
        if name is not None:
            hits = conn.execute("SELECT layer,id FROM names WHERE country=? AND name_key=? ORDER BY layer,id LIMIT ?", (country, key(name), limit + 1)).fetchall()
            results = []
            for layer, rid in hits[:limit]:
                table = "entities" if layer == "gazetteer" else "source_records"
                row = conn.execute("SELECT payload FROM " + table + " WHERE country=? AND id=?", (country, rid)).fetchone()
                results.append({"layer": layer, "record": json.loads(row[0])})
        else:
            column, value = ("postcode", postcode) if postcode is not None else ("source_code", source_code)
            hits = conn.execute("SELECT payload FROM source_records WHERE country=? AND " + column + "=? ORDER BY id LIMIT ?", (country, value, limit + 1)).fetchall()
            results = [{"layer": "source", "record": json.loads(r[0])} for r in hits[:limit]]
        used_sources = {r["record"]["source_id"] for r in results if r["layer"] == "source"}
        provenance = [{k: spec.get(k) for k in ("id", "publisher", "source_role", "url", "edition", "rights")}
                      for spec in load_manifest()["sources"] if spec["id"] in used_sources]
        return {"country": country, "results": results, "source_provenance": provenance,
                "has_more": len(hits) > limit,
                "different_sources_are_not_verified_same_entity": True,
                "national_completeness_verified": False, "deliverability_verified": False}
    finally:
        conn.close()


def verify_index(db: Path, base: Path = DATA) -> dict:
    """Compare indexed payloads AND lookup columns with pinned source streams."""
    manifest = load_manifest(base)
    conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Index integrity failure")
        if conn.execute("SELECT value FROM metadata WHERE key='manifest_sha256'").fetchone()[0] != sha((base / "manifest.json").read_bytes()):
            raise ValueError("Index manifest differs")
        expected_entities = expected_sources = expected_names = 0
        for country in COUNTRIES:
            rows, _ = gazetteer(country)
            expected_entities += len(rows)
            for r in rows:
                actual = conn.execute("SELECT kind,name,state_id,payload FROM entities WHERE country=? AND id=?", (country, r["id"])).fetchone()
                if actual != (r["kind"], r["name"], r["state_id"], canonical(r).decode()):
                    raise ValueError("Gazetteer index differs: " + r["id"])
                names = {key(n) for n in (r["name"], r["asciiname"], *(r.get("alternatenames") or "").split(",")) if n}
                indexed = {n[0] for n in conn.execute("SELECT name_key FROM names WHERE country=? AND layer='gazetteer' AND id=?", (country, r["id"]))}
                if indexed != names:
                    raise ValueError("Gazetteer search names differ: " + r["id"])
                expected_names += len(names)
        for source in manifest["sources"]:
            for r in normalized(source, base):
                expected_sources += 1
                actual = conn.execute("SELECT country,source_id,grain,source_code,postcode,payload FROM source_records WHERE id=?", (r["record_id"],)).fetchone()
                if actual != (r["catalogue_country"], r["source_id"], r["grain"], r["source_code"], r["postcode"], canonical(r).decode()):
                    raise ValueError("Source index differs: " + r["record_id"])
                names = {key(n) for n in r["names"].values() if n}
                indexed = {n[0] for n in conn.execute("SELECT name_key FROM names WHERE country=? AND layer='source' AND id=?", (r["catalogue_country"], r["record_id"]))}
                if indexed != names:
                    raise ValueError("Source search names differ: " + r["record_id"])
                expected_names += len(names)
        if conn.execute("SELECT count(*) FROM entities").fetchone()[0] != expected_entities or conn.execute("SELECT count(*) FROM source_records").fetchone()[0] != expected_sources:
            raise ValueError("Index contains extra or missing records")
        if conn.execute("SELECT count(*) FROM names").fetchone()[0] != expected_names:
            raise ValueError("Index contains extra or missing search names")
        return {"status": "passed", "gazetteer_records_verified": expected_entities,
                "source_records_verified": expected_sources, "search_names_verified": expected_names,
                "deliverability_verified": False}
    finally:
        conn.close()


def cli(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("inventory")
    sub.add_parser("verify")
    v = sub.add_parser("verify-index")
    v.add_argument("--db", type=Path, required=True)
    a = sub.add_parser("audit")
    a.add_argument("--output", type=Path)
    b = sub.add_parser("build")
    b.add_argument("--output", type=Path, required=True)
    q = sub.add_parser("query")
    q.add_argument("--db", type=Path, required=True)
    q.add_argument("--country", choices=COUNTRIES, required=True)
    group = q.add_mutually_exclusive_group(required=True)
    group.add_argument("--name")
    group.add_argument("--postcode")
    group.add_argument("--source-code")
    q.add_argument("--limit", type=int, default=20)
    args = p.parse_args(argv)
    if args.command == "inventory":
        result = load_manifest()
    elif args.command == "verify":
        result = verify_sources()
    elif args.command == "verify-index":
        result = verify_index(args.db)
    elif args.command == "audit":
        result = audit()
    elif args.command == "build":
        result = build_index(args.output)
    else:
        result = query(args.db, args.country, name=args.name, postcode=args.postcode,
                       source_code=args.source_code, limit=args.limit)
    dump = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if getattr(args, "output", None) and args.command == "audit":
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(dump, encoding="utf-8")
    else:
        print(dump, end="")


if __name__ == "__main__":
    cli()
