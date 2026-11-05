#!/usr/bin/env python3
"""Build independent DK/SE ODbL evidence indexes from pinned Geofabrik OSM extracts.

Not an authoritative address register. No country membership, address existence,
currentness or carrier deliverability is inferred from community mapping.
Run on immutable raw PBF snapshots; test fixtures may use tiny OSM XML files.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

COUNTRIES = {"DK": "denmark", "SE": "sweden"}
SUPPORTED_INPUTS = {".osm.pbf", ".osm", ".osm.gz"}
ATTRIBUTION = "© OpenStreetMap contributors; Geofabrik regional extract"
LICENSE = "ODbL-1.0"
STREET_KEYS = ("addr:street", "addr:place")
SELECTED_TAGS = frozenset((
    "name", "name:sv", "name:da", "name:en", "official_name", "alt_name",
    "place", "highway", "boundary", "admin_level", "addr:housenumber",
    "addr:street", "addr:place", "addr:postcode", "addr:city",
    "addr:municipality", "addr:country", "addr:suburb", "addr:district",
))
PROPOSED_ROADS = frozenset(("proposed", "construction", "abandoned", "razed", "disused"))
SCHEMA_VERSION = 1


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def official_distribution_url(country):
    if country not in COUNTRIES:
        raise ValueError("Only Denmark (DK) and Sweden (SE) are supported")
    return f"https://download.geofabrik.de/europe/{COUNTRIES[country]}-latest.osm.pbf"


def checked_url(country, value):
    url = urlsplit(value)
    if (url.scheme != "https" or url.hostname != "download.geofabrik.de"
            or url.username is not None or url.password is not None or url.port is not None
            or url.query or url.fragment or not re.fullmatch(
                rf"/europe/{COUNTRIES[country]}-(?:latest|[0-9]{{6}})\.osm\.pbf", url.path)):
        raise ValueError("Unexpected extract origin or path")
    return value


def parse_time(timestamp):
    if not isinstance(timestamp, str):
        raise ValueError("Acquisition timestamp must be a string")
    d = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if d.tzinfo is None or d.utcoffset() is None:
        raise ValueError("Source acquisition timestamp must be offset-aware")
    return d


def safe_source(root, relative):
    root = Path(root).resolve()
    part = Path(relative)
    if part == Path(".") or part.is_absolute() or ".." in part.parts:
        raise ValueError("Unsafe relative input path")
    out = (root / part).resolve()
    if not out.is_relative_to(root) or not out.is_file():
        raise ValueError("Input missing or escapes its root")
    return out


def validated_pin(pin, root):
    if pin.get("schema_version") != SCHEMA_VERSION or pin.get("source_kind") != "community_osm_evidence":
        raise ValueError("Unexpected source manifest format")
    country = pin.get("country")
    if country not in COUNTRIES:
        raise ValueError("Unexpected country")
    checked_url(country, pin.get("source_url", ""))
    parse_time(pin.get("acquired_at"))
    if pin.get("license") != LICENSE or pin.get("attribution") != ATTRIBUTION:
        raise ValueError("ODbL / contributor attribution is mandatory")
    if pin.get("rights_reviewed") is not True:
        raise ValueError("License review must be explicit")
    if type(pin.get("bytes")) is not int or pin["bytes"] <= 0:
        raise ValueError("Invalid pinned file size")
    if not re.fullmatch(r"[0-9a-f]{64}", pin.get("sha256", "")):
        raise ValueError("Invalid SHA-256 value")
    source = safe_source(root, pin.get("filename", ""))
    if not any(source.name.endswith(suffix) for suffix in SUPPORTED_INPUTS):
        raise ValueError("Unsupported source file extension")
    if source.name.endswith((".osm", ".osm.gz")) and pin.get("fixture") is not True:
        raise ValueError("OSM XML sources are only accepted as explicitly marked test fixtures")
    if pin.get("fixture") not in (None, False, True):
        raise ValueError("Invalid fixture status")
    if source.stat().st_size != pin["bytes"] or sha256(source) != pin["sha256"]:
        raise ValueError("Pinned file size or SHA-256 differs")
    return source


def pin_local(country, source, acquired_at, fixture=False, source_url=None):
    if country not in COUNTRIES:
        raise ValueError("Unknown country")
    parse_time(acquired_at)
    checked_url(country, source_url or official_distribution_url(country))
    source = Path(source).resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError("Missing source file")
    if source.name.endswith((".osm", ".osm.gz")) and not fixture:
        raise ValueError("XML is reserved for test fixtures")
    if not any(source.name.endswith(suffix) for suffix in SUPPORTED_INPUTS):
        raise ValueError("Unknown source extension")
    return {"schema_version": SCHEMA_VERSION, "source_kind": "community_osm_evidence",
            "country": country, "source_url": source_url or official_distribution_url(country),
            "filename": source.name, "acquired_at": acquired_at, "bytes": source.stat().st_size,
            "sha256": sha256(source), "license": LICENSE, "attribution": ATTRIBUTION,
            "rights_reviewed": True, "fixture": bool(fixture),
            "declared_coverage": "regional extract only; no nationwide coverage certification"}


def download_source(country, directory):
    """Fetch a public OSM snapshot without credentials; save receipt and bytes atomically."""
    url = official_distribution_url(country)
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError("Output directory must exist")
    destination = directory / (COUNTRIES[country] + "-latest.osm.pbf")
    receipt = directory / (COUNTRIES[country] + "-source-pin.json")
    if destination.exists() or receipt.exists():
        raise ValueError("Do not overwrite a saved snapshot or receipt")
    partial = directory / (destination.name + ".partial")
    if partial.exists() or partial.is_symlink():
        raise ValueError("Existing partial download needs manual review")
    digest, total = hashlib.sha256(), 0
    try:
        with urlopen(Request(url, headers={"User-Agent": "Veygrit-Nordics-OSM/1.0"}), timeout=120) as response:
            checked_url(country, response.geturl())
            if response.status != 200:
                raise ValueError("Unexpected download status")
            with partial.open("xb") as f:
                for block in iter(lambda: response.read(1024 * 1024), b""):
                    total += len(block)
                    if total > 3_500_000_000:
                        raise ValueError("Unexpectedly large input file")
                    f.write(block)
                    digest.update(block)
        if total <= 0:
            raise ValueError("Empty extract")
        # Snapshot bytes and timestamp are pinned; no assertion of upstream freshness.
        stamp = datetime.now().astimezone().isoformat()
        doc = {"schema_version": 1, "source_kind": "community_osm_evidence",
               "country": country, "source_url": url, "filename": destination.name,
               "acquired_at": stamp, "bytes": total, "sha256": digest.hexdigest(),
               "license": LICENSE, "attribution": ATTRIBUTION, "rights_reviewed": True,
               "fixture": False, "declared_coverage": "regional extract; not official addresses"}
        # Hard-link creation fails atomically if a concurrent writer created the file.
        os.link(partial, destination)
        partial.unlink()
        with receipt.open("x", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except BaseException:
        partial.unlink(missing_ok=True)
        # Keep completed bytes on partial receipt write failures, for explicit recovery.
        raise
    return doc


def postcode_shape(country, value):
    if not isinstance(value, str):
        return False
    if country == "DK":
        return bool(re.fullmatch(r"[0-9]{4}", value))
    if country == "SE":
        return bool(re.fullmatch(r"[0-9]{3} ?[0-9]{2}", value))
    return False


def coordinates(lon, lat):
    if lon is None or lat is None:
        return None, None
    try:
        lon, lat = float(lon), float(lat)
    except (ValueError, TypeError):
        return None, None
    if not -180 <= lon <= 180 or not -90 <= lat <= 90:
        return None, None
    return lon, lat


def evidence_rows(country, kind, identifier, tags, lon=None, lat=None):
    """Project only non-personal OSM tags, never invent a parent or an address point."""
    if country not in COUNTRIES or kind not in {"node", "way", "relation"}:
        raise ValueError("Unexpected source identity")
    try:
        if int(identifier) <= 0:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("OSM identity must be positive integer") from None
    row_id = f"osm:{kind}:{int(identifier)}"
    clean = {k: v for k, v in tags.items() if k in SELECTED_TAGS and isinstance(v, str) and v}
    lon, lat = coordinates(lon, lat) if kind == "node" else (None, None)
    data = []
    categories = []
    search_blob = " ".join(clean.get(k, "") for k in ("name", "name:sv", "name:da", "name:en", "addr:street", "addr:place", "addr:city", "addr:municipality")).casefold()
    if clean.get("addr:housenumber"):
        categories.append("address_candidate")
    if clean.get("highway") and clean.get("name") and clean["highway"] not in PROPOSED_ROADS:
        categories.append("named_road_segment")
    if clean.get("place") and clean.get("name"):
        categories.append("named_place")
    if clean.get("boundary") == "administrative" and clean.get("name"):
        categories.append("administrative_boundary_label")
    tag_json = canonical(clean)
    for category in categories:
        postcode = clean.get("addr:postcode") if category == "address_candidate" else None
        status = "syntax_valid" if postcode and postcode_shape(country, postcode) else (
            "syntax_invalid" if postcode else "not_provided")
        data.append((category, row_id, clean.get("name", ""), clean.get("addr:street", ""),
                     clean.get("addr:place", ""), clean.get("addr:housenumber", ""),
                     postcode or "", clean.get("addr:city", ""), clean.get("addr:municipality", ""),
                     clean.get("addr:country", ""), status,
                     lon, lat, "mapped_node" if lon is not None else "not_asserted",
                     clean.get("highway", ""), clean.get("place", ""), clean.get("admin_level", ""), search_blob, tag_json))
    return data


def schema(db):
    db.executescript("""
        PRAGMA journal_mode=DELETE;
        PRAGMA synchronous=NORMAL;
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE features (
          category TEXT NOT NULL CHECK (category IN
            ('address_candidate','named_road_segment','named_place','administrative_boundary_label')),
          osm_ref TEXT NOT NULL, name TEXT NOT NULL, street TEXT NOT NULL,
          place TEXT NOT NULL, house_number TEXT NOT NULL, postcode TEXT NOT NULL,
          city TEXT NOT NULL, municipality TEXT NOT NULL, country_tag TEXT NOT NULL,
          postcode_shape TEXT NOT NULL, lon REAL, lat REAL, location_quality TEXT NOT NULL,
          highway TEXT NOT NULL, place_type TEXT NOT NULL, admin_level TEXT NOT NULL,
          search_blob TEXT NOT NULL, source_tags_json TEXT NOT NULL, PRIMARY KEY (category,osm_ref)
        ) WITHOUT ROWID;
    """)


def iter_xml(path):
    """Restricted XML fixture parser, not the production nationwide PBF parser."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rb") as stream:
        previous = b""
        for buf in iter(lambda: stream.read(1024 * 256), b""):
            upper = (previous + buf).upper()
            if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
                raise ValueError("DTD and entity declarations are prohibited")
            previous = upper[-16:]
    with opener(path, "rb") as stream:
        stack = []
        for evt, element in ET.iterparse(stream, events=("start", "end")):
            if evt == "start":
                stack.append(element)
                continue
            if element.tag in ("node", "way", "relation"):
                tags = {c.attrib.get("k", ""): c.attrib.get("v", "") for c in element if c.tag == "tag"}
                yield element.tag, element.attrib.get("id"), tags, element.attrib.get("lon"), element.attrib.get("lat")
                if len(stack) > 1:
                    stack[-2].remove(element)
                element.clear()
            stack.pop()


def stream_pbf(path, consume):
    try:
        import osmium
    except ImportError as exc:
        raise RuntimeError("PBF support needs pip install osmium") from exc
    class Importer(osmium.SimpleHandler):
        def _ingest(self, obj, kind):
            tags = {t.k: t.v for t in obj.tags}
            loc = getattr(obj, "location", None) if kind == "node" else None
            lon = loc.lon if loc is not None and loc.valid() else None
            lat = loc.lat if loc is not None and loc.valid() else None
            consume(kind, obj.id, tags, lon, lat)
        def node(self, obj): self._ingest(obj, "node")
        def way(self, obj): self._ingest(obj, "way")
        def relation(self, obj): self._ingest(obj, "relation")
    # Filter empty-tag objects early and avoid the massive disk-based node-location cache:
    # building/road ways are retained, but no invented way centroid is attached.
    Importer().apply_file(str(path), locations=False, filters=[osmium.filter.EmptyTagFilter()])


def projected_digest(db):
    """Hash every projected source row in deterministic key order for replay checks."""
    digest = hashlib.sha256()
    for values in db.execute("SELECT * FROM features ORDER BY category,osm_ref"):
        digest.update(canonical(values).encode("utf-8") + b"\n")
    return digest.hexdigest()


def import_data(pin, root, output):
    """Atomically create single-country evidence SQLite index; immutable input required."""
    raw = validated_pin(pin, root)
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Do not overwrite existing evidence database")
    output.parent.mkdir(parents=True, exist_ok=True)
    totals = Counter()
    staged = None
    with tempfile.TemporaryDirectory(prefix=".dk-se-open-", dir=output.parent) as tmp:
        staged = Path(tmp) / "evidence.sqlite"
        db = sqlite3.connect(staged)
        try:
            schema(db)
            insert = """INSERT INTO features VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
            count = 0
            def consume(kind, identifier, tags, lon=None, lat=None):
                nonlocal count
                rows = evidence_rows(pin["country"], kind, identifier, tags, lon, lat)
                if not rows:
                    return
                db.executemany(insert, rows)
                for row in rows:
                    totals[row[0]] += 1
                    if row[11] is not None:
                        totals["with_mapped_node_geometry"] += 1
                    if row[10] == "syntax_valid":
                        totals["postcode_syntax_valid"] += 1
                    if row[9] and row[9].upper() != pin["country"]:
                        totals["country_tag_conflict"] += 1
                count += len(rows)
                if count % 10000 < len(rows):
                    db.commit()
            if raw.name.endswith(".osm.pbf"):
                stream_pbf(raw, consume)
            else:
                for a in iter_xml(raw):
                    consume(*a)
            db.execute("CREATE INDEX ix_category_postcode ON features(category, postcode)")
            db.execute("CREATE INDEX ix_category_city ON features(category, city)")
            db.execute("CREATE INDEX ix_category_street ON features(category, street)")
            report = {"schema_version": SCHEMA_VERSION, "country": pin["country"],
                      "source_receipt": pin, "counts": dict(sorted(totals.items())),
                      "indexed_records": sum(v for k, v in totals.items() if k in
                                             ("address_candidate","named_road_segment","named_place","administrative_boundary_label")),
                      "projected_rows_sha256": projected_digest(db),
                      "index_type": "community_observations_not_official_address_registry",
                      "official_admin_parent_verified": False, "legal_country_membership_verified": False,
                      "postal_existence_verified": False, "street_number_relationship_verified": False,
                      "national_completeness_verified": False, "deliverability_verified": False,
                      "license": LICENSE, "attribution": ATTRIBUTION,
                      "way_relation_positions": "not inferred; only OSM node positions are stored",
                      "status": "FIXTURE_ONLY" if pin.get("fixture") else "COMMUNITY_EVIDENCE_INDEXED"}
            db.execute("INSERT INTO metadata VALUES (?,?)", ("report", canonical(report)))
            db.commit()
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite integrity check failed")
        finally:
            db.close()
        # Atomic publication on the same filesystem only, never overwrite a prior output.
        if output.exists() or output.is_symlink():
            raise ValueError("Target appeared during import")
        os.link(staged, output)  # never replace a concurrently created target
        staged.unlink()
    return report


def checked_database(path):
    p = Path(path).resolve()
    if not p.is_file():
        raise ValueError("Index not found")
    db = sqlite3.connect("file:" + quote(p.as_posix(), safe="/") + "?mode=ro", uri=True)
    try:
        report = json.loads(db.execute("SELECT value FROM metadata WHERE key='report'").fetchone()[0])
        if report.get("schema_version") != 1 or report.get("country") not in COUNTRIES:
            raise ValueError("Bad localities index schema")
        return db, report
    except BaseException:
        db.close()
        raise


def verify_index(path):
    db, report = checked_database(path)
    try:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Index integrity failure")
        actual = dict(db.execute("SELECT category,COUNT(*) FROM features GROUP BY category"))
        if report["indexed_records"] != sum(actual.values()):
            raise ValueError("Stored row totals differ")
        if any(report["counts"].get(cat, 0) != v for cat, v in actual.items()):
            raise ValueError("Counts differ from indexed features")
        if projected_digest(db) != report.get("projected_rows_sha256"):
            raise ValueError("Projected source evidence changed")
        return {"status": "PASS", "country": report["country"], "categories": actual,
                "fixture": report["status"] == "FIXTURE_ONLY", "certified_address_registry": False}
    finally:
        db.close()


def search(path, category, text="", postcode="", limit=20):
    if category not in ("address_candidate", "named_road_segment", "named_place", "administrative_boundary_label"):
        raise ValueError("Unknown category")
    if not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("Limit must be 1..100")
    db, report = checked_database(path)
    try:
        sql = "SELECT * FROM features WHERE category=?"
        params = [category]
        if postcode:
            sql += " AND REPLACE(postcode,' ','')=?"
            params.append(postcode.replace(" ", ""))
        if text:
            sql += " AND search_blob LIKE ? ESCAPE '\\'"
            literal = text.casefold().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append("%" + literal + "%")
        sql += " ORDER BY osm_ref LIMIT ?"
        params.append(limit)
        names = [c[1] for c in db.execute("PRAGMA table_info(features)")]
        rows = [dict(zip(names, row)) for row in db.execute(sql, params)]
        for r in rows:
            r["source_tags"] = json.loads(r.pop("source_tags_json"))
            r.pop("search_blob", None)
        return {"country": report["country"], "category": category, "results": rows,
                "national_completeness_verified": False, "deliverability_verified": False,
                "license": LICENSE, "attribution": ATTRIBUTION}
    finally:
        db.close()


def cli():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    a = commands.add_parser("download", help="Fetch an independent OSM extract and pin its exact bytes")
    a.add_argument("--country", choices=COUNTRIES, required=True)
    a.add_argument("--directory", type=Path, required=True)
    a = commands.add_parser("pin", help="Create a receipt for a separately downloaded Geofabrik file")
    a.add_argument("--country", choices=COUNTRIES, required=True)
    a.add_argument("--source", type=Path, required=True)
    a.add_argument("--acquired-at", required=True, help="Offset-aware ISO-8601 timestamp")
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--fixture", action="store_true", help="OSM XML test fixtures only")
    a.add_argument("--source-url", help="Exact approved Geofabrik snapshot URL, default latest")
    a = commands.add_parser("build")
    a.add_argument("--pin", type=Path, required=True)
    a.add_argument("--source-root", type=Path, required=True)
    a.add_argument("--output", type=Path, required=True)
    a = commands.add_parser("verify")
    a.add_argument("--db", type=Path, required=True)
    a = commands.add_parser("search")
    a.add_argument("--db", type=Path, required=True)
    a.add_argument("--category", required=True)
    a.add_argument("--text", default="")
    a.add_argument("--postcode", default="")
    a.add_argument("--limit", type=int, default=20)
    a = commands.add_parser("postcode")
    a.add_argument("--country", choices=COUNTRIES, required=True)
    a.add_argument("--value", required=True)
    args = p.parse_args()
    if args.command == "download":
        result = download_source(args.country, args.directory)
    elif args.command == "pin":
        result = pin_local(args.country, args.source, args.acquired_at, args.fixture, args.source_url)
        with args.output.open("x", encoding="utf-8") as f:
            f.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    elif args.command == "build":
        result = import_data(json.loads(args.pin.read_text(encoding="utf-8")), args.source_root, args.output)
    elif args.command == "verify":
        result = verify_index(args.db)
    elif args.command == "search":
        result = search(args.db, args.category, args.text, args.postcode, args.limit)
    else:
        result = {"country": args.country, "postcode": args.value,
                  "syntax_valid": postcode_shape(args.country, args.value),
                  "existence_verified": False, "deliverability_verified": False}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        cli()
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        sys.exit(str(exc))
