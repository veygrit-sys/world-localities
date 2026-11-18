"""Read the pinned mainland Chinese statistical reference tables offline."""

from functools import cache
import hashlib
import json
from pathlib import Path
from types import MappingProxyType


REFERENCE = Path(__file__).resolve().parent
MANIFEST = REFERENCE.parents[1] / "releases" / "hierarchy" / "east-asia" / "sources.json"
TABLES = {"province": "provinces", "city": "cities", "area": "areas"}


@cache
def _sources():
    return {source["id"]: source for source in json.loads(MANIFEST.read_bytes())["sources"]}


@cache
def load_statistical_table(level):
    table = TABLES[level]
    source = _sources()["CN-statistical-" + table]
    raw = (REFERENCE / "tables" / (table + ".json")).read_bytes()
    if len(raw) != source["bytes"] or hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise ValueError("China reference checksum mismatch: " + table)
    rows = {row["code"]: MappingProxyType(row) for row in json.loads(raw)}
    receipt = {
        "source_id": source["id"],
        "url": source["url"],
        "sha256": source["sha256"],
        "source_date": source["source_date"],
        "upstream_commit": source["upstream_commit"],
    }
    return MappingProxyType(rows), MappingProxyType(receipt)


def load_statistical_provinces():
    """Return immutable source rows keyed by the two-digit statistical code."""
    provinces, _ = load_statistical_table("province")
    return provinces
