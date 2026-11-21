"""Search a pinned OpenStreetMap extract of libraries and museums in D.C."""
from functools import cache
import hashlib
import json
from pathlib import Path
import unicodedata

_DATA = Path(__file__).resolve().parent
_ADDRESS_FIELDS = {"addr:postcode", "addr:city", "addr:state", "addr:street"}


def _key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


@cache
def _snapshot() -> tuple[bytes, tuple[bytes, ...]]:
    metadata = (_DATA / "source.json").read_bytes()
    projection = (_DATA / "records.jsonl").read_bytes()
    expected = json.loads(metadata)["projection_sha256"]
    if hashlib.sha256(projection).hexdigest() != expected:
        raise ValueError("OSM record projection SHA-256 differs from the source manifest")
    return metadata, tuple(projection.splitlines())


def lookup(query: str) -> list[dict]:
    """Find a name, explicit address component, house number + street, or OSM ID."""
    key = _key(query)
    if not key:
        return []
    metadata, records = _snapshot()
    source = json.loads(metadata)
    found = []
    for line in records:
        record = json.loads(line)
        tags = record["tags"]
        kind, osm_id = record["osm_type"], record["osm_id"]
        record_id = f"osm:{kind}:{osm_id}"
        terms = {k: v for k, v in tags.items()
                 if v and (k in _ADDRESS_FIELDS or k == "name" or k.startswith("name:"))}
        terms["addr:housenumber+addr:street"] = tags["addr:housenumber"] + " " + tags["addr:street"]
        terms["record_id"] = record_id
        matched = [field for field, value in terms.items() if _key(value) == key]
        if matched:
            found.append({
                **record,
                "record_id": record_id,
                "country_code": "US",
                "source_id": source["source_id"],
                "source_url": source["url"],
                "source_sha256": source["source_sha256"],
                "replication_timestamp": source["replication_timestamp"],
                "object_url": f"https://www.openstreetmap.org/{kind}/{osm_id}",
                "object_version_url":
                    f"https://api.openstreetmap.org/api/0.6/{kind}/{osm_id}/{record['osm_version']}",
                "name": tags["name"],
                "matched_fields": matched,
                "evidence_scope": "map_feature_with_explicit_address_tags",
                "attribution": source["attribution"],
                "license": source["license"],
                "attribution_url": source["attribution_url"],
            })
    return found
