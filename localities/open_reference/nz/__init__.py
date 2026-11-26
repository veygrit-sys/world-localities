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
    """Search supplied authority or explicit locality across all covered LINZ districts."""
    authority = _key(values.get("municipality", ""))
    places = {"city", "town", "suburb", "hamlet"} & values.keys()
    if not authority and not places:
        return None
    line = values.get("address_line1", "")
    road, number = values.get("road"), values.get("house_number")
    if not road or not number:
        # Use this division only to look up a publisher row. Compare the entire
        # original line and all supplied components on that row before confirming.
        first, separator, rest = line.partition(" ")
        if not separator:
            return None
        road = road or rest
        number = number or first.rsplit("/", 1)[-1]
    src = _source()
    shards = [s for s in src["shards"] if not authority or _key(s["authority"]) == authority]
    if not shards:
        return None
    evidence, unit_candidates = {}, {}
    inline_units = set()
    matched_authorities = set()
    checked = {"municipality", "road", "house_number"} & values.keys()
    for shard in shards:
        rows = _district(shard["file"], shard["csv_sha256"]).get((_key(road), _key(number)), ())
        for row in rows:
            location = {"city": row["town_city"], "town": row["town_city"], "suburb": row["suburb_locality"],
                        "hamlet": row["suburb_locality"], "unit": row["unit"]}
            if any(_key(values[k]) != _key(location[k]) for k in location.keys() & values.keys()):
                continue
            primary = _key(row["full_address_number"] + " " + row["full_road_name"])
            civic = _key(number + " " + row["full_road_name"])
            if line and _key(line) not in {primary, civic}:
                continue
            unit_in_line = bool(line and row["unit"] and _key(line) == primary)
            missing_unit = bool(row["unit"] and not values.get("unit") and not unit_in_line)
            rid = row["address_id"]
            matched_authorities.add(shard["authority"])
            if unit_in_line:
                inline_units.add(rid)
            checked.update((location.keys() | {"address_line1"}) & values.keys())
            receipts = unit_candidates if missing_unit else evidence
            receipts[rid] = {"source_id": src["source_id"], "record_id": rid, "url": src["dataset_url"],
                             "snapshot": src["data_last_edited"], "sha256": shard["csv_sha256"],
                             "attribution": src["attribution"], "license": src["license"],
                             "terms_url": src["terms_url"], "changes": src["changes"]}
    if evidence and len(matched_authorities) > 1:
        unit_candidates.update(evidence)
        return result("ambiguous", scope="published_district_street", checked=checked - {"house_number", "address_line1", "unit"},
                      candidate_count=len(unit_candidates), evidence=list(unit_candidates.values()),
                      issues=["territorial_authority_required_to_distinguish_address"])
    if evidence:
        return result("matched" if len(evidence) == 1 else "ambiguous",
                      scope="published_address_point", checked=checked, candidate_count=len(evidence),
                      matched_unit=bool(len(evidence) == 1 and inline_units & evidence.keys()),
                      evidence=list(evidence.values()))
    if unit_candidates:
        # A property number shared by published units does not select a unit.
        # A single published unit alone is not a unitless parent address either.
        shared = checked - {"house_number", "address_line1", "unit"}
        return result("ambiguous" if len(unit_candidates) > 1 else "partial",
                      scope="published_district_street", checked=shared, candidate_count=len(unit_candidates),
                      issues=["unit_required_to_distinguish_address"], evidence=list(unit_candidates.values()))
    if values.get("postcode") or not authority:
        return None
    return result("not_observed", candidate_count=0, issues=["address_point_not_observed_in_linz_district"])
