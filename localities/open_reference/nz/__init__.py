"""Match typed, non-postal fields on one published LINZ address in a covered district."""

from collections import defaultdict
import csv
from functools import lru_cache
import gzip
import hashlib
import io
import json
from pathlib import Path
import unicodedata

DIRECTORY = Path(__file__).parent / "snapshot"


def _key(value):
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


@lru_cache(maxsize=1)
def _source():
    return json.loads((DIRECTORY / "source.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=5)
def _district(filename, digest):
    raw = gzip.decompress((DIRECTORY / filename).read_bytes())
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("LINZ address projection checksum mismatch")
    streets = defaultdict(list)
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")):
        full_number = row["full_address_number"]
        number = full_number
        if row["unit"]:
            # A published unit/number must reproduce both components without guessing.
            unit_prefix = row["unit"] + "/"
            if not full_number.startswith(unit_prefix):
                continue
            number = full_number[len(unit_prefix):]
        streets[(_key(row["full_road_name"]), _key(number))].append(row)
    return streets


def validate_point(values, result):
    """Require explicit territorial authority, road and number within the same LINZ row."""
    if not all(values.get(k) for k in ("municipality", "road", "house_number")):
        return None
    src = _source()
    authority = _key(values["municipality"])
    shard = next((s for s in src["shards"] if _key(s["authority"]) == authority), None)
    if shard is None:
        return None
    rows = _district(shard["file"], shard["csv_sha256"]).get(
        (_key(values["road"]), _key(values["house_number"])), ()
    )
    checked = {"municipality", "road", "house_number"}
    evidence = []
    for row in rows:
        # Without a unit, only a unitless publisher address qualifies as a point.
        if _key(values.get("unit", "")) != _key(row["unit"]):
            continue
        location = {"city": row["town_city"], "town": row["town_city"], "suburb": row["suburb_locality"],
                    "hamlet": row["suburb_locality"], "unit": row["unit"],
                    "address_line1": row["full_address_number"] + " " + row["full_road_name"]}
        if any(_key(values[k]) != _key(location[k]) for k in location.keys() & values.keys()):
            continue
        checked.update(location.keys() & values.keys())
        evidence.append({"source_id": src["source_id"], "record_id": row["address_id"],
                         "url": src["dataset_url"], "snapshot": src["data_last_edited"],
                         "sha256": shard["csv_sha256"], "attribution": src["attribution"],
                         "license": src["license"], "terms_url": src["terms_url"], "changes": src["changes"]})
    if evidence:
        return result("matched" if len(evidence) == 1 else "ambiguous",
                      scope="published_address_point", checked=checked, evidence=evidence)
    # Other postcode evidence remains available through the caller's existing index.
    if values.get("postcode"):
        return None
    return result("not_observed", issues=["address_point_not_observed_in_linz_district"])
