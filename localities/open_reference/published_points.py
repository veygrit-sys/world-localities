"""Offline address-point projections, indexed by typed fields and publisher record ID."""

import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import unicodedata

ROOT = Path(__file__).parent
SOURCES = {
    "NL": ("benelux/NL", "nl-kadaster-bag-wadden"),
    "LU": ("benelux/LU", "lu-act-bd-adresses"),
    "FR": ("ban/FR", "fr-ban-48-90"),
    "PM": ("ban/PM", "pm-ban-975"),
    "UY": ("uy", "uy-ide-direcciones"),
}
FIELDS = ("postcode", "locality", "road", "number", "municipality", "record_id")


def key(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


def manifest(country):
    return json.loads((ROOT / SOURCES[country][0] / "source.json").read_text(encoding="utf-8"))


def point_rows(country, source):
    for shard in source["shards"]:
        data = (ROOT / SOURCES[country][0] / shard["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != shard["sha256"]:
            raise ValueError(f"{country}: address point projection checksum mismatch")
        with gzip.open(io.BytesIO(data), "rt", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            if next(reader, []) != list(FIELDS):
                raise ValueError("unexpected address point columns")
            count = 0
            for row in reader:
                if len(row) != len(FIELDS) or not all(row[:4]) or not row[-1]:
                    raise ValueError("incomplete address point")
                count += 1
                yield row
            if count != shard["rows"]:
                raise ValueError("address point projection row count mismatch")


def indexed_paths(db, countries):
    """Store the typed point and its picker path in the same temporary index."""
    selected = SOURCES.keys() if countries is None else SOURCES.keys() & countries
    if not selected:
        return
    db.execute("""CREATE TABLE official_points (
        country TEXT, postcode TEXT, road_key TEXT, number_key TEXT,
        locality TEXT, municipality TEXT, source TEXT, record_id TEXT,
        PRIMARY KEY(country, postcode, road_key, number_key, record_id)
    ) WITHOUT ROWID""")
    for country in sorted(selected):
        source = manifest(country)
        sid = source["source_id"]
        if "commune_links" in source:
            db.execute("""CREATE TABLE IF NOT EXISTS point_communes (
                source TEXT, postcode TEXT, locality TEXT, commune_code TEXT,
                PRIMARY KEY(source, postcode, locality)
            ) WITHOUT ROWID""")
            db.executemany("INSERT INTO point_communes VALUES (?,?,?,?)",
                           ((sid, *row) for row in source["commune_links"]))
        batch = []
        for postcode, locality, road, number, municipality, rid in point_rows(country, source):
            batch.append((country, postcode, key(road), key(number), locality, municipality, sid, rid))
            if len(batch) >= 2048:
                db.executemany("INSERT INTO official_points VALUES (?,?,?,?,?,?,?,?)", batch)
                batch.clear()
            yield country, postcode, (("area", locality), ("street", road), ("house_number", number)), sid
        db.executemany("INSERT INTO official_points VALUES (?,?,?,?,?,?,?,?)", batch)
