"""Exact component lookup in Washington, DC's published Master Address Repository."""

import csv
from functools import cache
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path

from .schema import FIELDS, _id_set_hash

_DIRECTORY = Path(__file__).resolve().parent
_CITYWIDE = _DIRECTORY / "citywide"
_ID_PREFIX = "US-DC-MAR:"
_SUFFIXES = {"ave": "avenue", "st": "street", "rd": "road", "pl": "place",
             "blvd": "boulevard", "dr": "drive", "ct": "court", "ln": "lane",
             "ter": "terrace", "cir": "circle"}


def _key(text: str) -> str:
    parts = text.casefold().split()
    # Common USPS Publication 28 suffixes in the slot immediately before the quadrant.
    if len(parts) >= 4 and parts[-1] in {"nw", "ne", "sw", "se"}:
        abbreviation = parts[-2].removesuffix(".")
        parts[-2] = _SUFFIXES.get(abbreviation, parts[-2])
    return " ".join(parts)


@cache
def _index():
    manifest = json.loads((_CITYWIDE / "citywide.json").read_bytes())
    records = {}
    postings = {}
    object_ids = set()
    for shard in manifest["shards"]:
        packed = (_CITYWIDE / shard["file"]).read_bytes()
        if len(packed) != shard["bytes"] or sha256(packed).hexdigest() != shard["sha256"]:
            raise ValueError(f"DC MAR shard differs from manifest: {shard['file']}")
        plain = gzip.decompress(packed)
        if sha256(plain).hexdigest() != shard["csv_sha256"]:
            raise ValueError("DC MAR projection does not match its uncompressed pin")
        reader = csv.reader(io.StringIO(plain.decode("utf-8"), newline=""))
        if tuple(next(reader)) != FIELDS:
            raise ValueError("Unexpected DC MAR projection schema")
        initial = len(records)
        for mar_id, oid, address, city, state, postal, lat, lon in reader:
            rid = _ID_PREFIX + mar_id
            if rid in records or int(oid) in object_ids:
                raise ValueError("Duplicate DC MAR source ID")
            object_ids.add(int(oid))
            records[rid] = (oid, address, city, state, postal, lat, lon)
            for key in {_key(term) for term in (address, city, state, postal) if term}:
                postings.setdefault(key, []).append(rid)
        if len(records) - initial != shard["rows"]:
            raise ValueError("DC MAR shard count mismatch")
    if (len(records) != manifest["selected_address_points"]
            or _id_set_hash(object_ids) != manifest["independent_object_id_set_sha256"]):
        raise ValueError("DC MAR records differ from the publisher's independent object-ID set")
    return records, {key: tuple(ids) for key, ids in postings.items()}


def lookup_ids(query: str) -> tuple[str, ...]:
    """List IDs matching a full address, ZIP, city, state or namespaced MAR ID."""
    key = _key(query)
    if not key:
        return ()
    records, postings = _index()
    if key.startswith(_ID_PREFIX.lower()):
        rid = key.upper()
        return (rid,) if rid in records else ()
    return postings.get(key, ())


def get_record(record_id: str) -> dict:
    """Materialize a fresh result only after the caller's filters have run."""
    records, _ = _index()
    oid, address, city, state, postal, lat, lon = records[record_id]
    return {
        "record_id": record_id,
        "object_id": oid,
        "source_id": "us-dc-mar",
        "evidence_kind": "published_address_point",
        "address": address,
        "city": city,
        "state": state,
        "postal_code": postal or None,
        "latitude": float(lat) if lat else None,
        "longitude": float(lon) if lon else None,
        "source_status": "ACTIVE",
        "license": "CC-BY-4.0",
        "attribution": "Open Data DC, Office of the Chief Technology Officer (OCTO)",
    }


def lookup(query: str) -> list[dict]:
    return [get_record(record_id) for record_id in lookup_ids(query)]
