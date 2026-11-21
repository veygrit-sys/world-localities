"""Lookup of mainland public offices' self-published addresses (CMAB)."""

import base64
import gzip
import hashlib
import json
import unicodedata
from datetime import datetime
from pathlib import Path


_ROOT = Path(__file__).parent
_OFFICES = {"beijing", "guangdong", "shanghai", "chengdu", "wuhan"}


def _source():
    return json.loads((_ROOT / "source.json").read_text(encoding="utf-8"))


def _check_bytes(data, descriptor):
    if (len(data) != descriptor["bytes"]
            or hashlib.sha256(data).hexdigest() != descriptor["sha256"]):
        raise ValueError("CMAB source differs from the pinned version")


def _read_document(descriptor):
    encoded = b"".join((_ROOT / descriptor["archive"]).read_bytes().split())
    data = gzip.decompress(base64.b64decode(encoded, validate=True))
    _check_bytes(data, descriptor)
    return json.loads(data)


def _offices(source, language):
    document = _read_document(source["files"][language])
    updated = datetime.strptime(document["LastUpdateDate"], "%m/%d/%Y").date()
    if updated.isoformat() != source["source_updated_on"]:
        raise ValueError("CMAB publication date differs between snapshot and manifest")
    entries = document["Data"]["Offices"]
    offices = {entry["officeID"]: entry for entry in entries}
    if len(entries) != len(offices) or offices.keys() != _OFFICES | {"taiwan"}:
        raise ValueError("Unexpected CMAB office identifiers")
    return offices


def _unit_key(unit):
    return (unit["email"], unit["postalCode"])


def _units(office):
    entries = office["liaisonUnits"]
    units = {_unit_key(entry): entry for entry in entries}
    if len(units) != len(entries) or any(not all(key) for key in units):
        raise ValueError("Missing or ambiguous CMAB liaison unit key")
    return units


def _map_points(source):
    descriptor = source["map_source"]
    document = _read_document(descriptor)
    points = {}
    for feature in document["features"]:
        properties = feature["properties"]
        address = properties["Address"]
        geometry = feature["geometry"]
        longitude, latitude = geometry["coordinates"]
        if (document["type"] != "FeatureCollection" or geometry["type"] != "Point"
                or not (-180 <= longitude <= 180 and -90 <= latitude <= 90)
                or feature["id"] != properties["OBJECTID"] or address in points):
            raise ValueError("Unexpected or ambiguous CSDI map point")
        points[address] = {
            "source_id": descriptor["source_id"],
            "source_url": descriptor["layer_url"] + "/" + str(feature["id"]),
            "source_object_id": feature["id"],
            "source_address": address,
            "source_retrieved_on": descriptor["retrieved_on"],
            "crs": "EPSG:4326",
            "longitude": longitude,
            "latitude": latitude,
            "attribution": descriptor["attribution"],
            "terms_url": descriptor["terms_url"],
        }
    return points


def _record(source, points, identifier, kind, english, chinese):
    postcode = english["postalCode"]
    if (not postcode.isascii() or not postcode.isdigit() or len(postcode) != 6
            or postcode != chinese["postalCode"]):
        raise ValueError("Invalid or conflicting postcode in the CMAB publication")
    name_field = "officeName" if kind == "office" else "unitName"
    return {
        "record_id": f"hk-cmab:{identifier}",
        "country": "CN",
        "kind": kind,
        "evidence_type": "published_office_address",
        "name": {"en": english[name_field], "zh-Hant": chinese[name_field]},
        "address": {"en": english["address"], "zh-Hant": chinese["address"]},
        "postcode": postcode,
        "map_point": points.get(english["address"]),
        "source_id": source["source_id"],
        "source_updated_on": source["source_updated_on"],
        "source_url": source["catalog_url"],
        "attribution": source["attribution"],
        "terms_url": source["terms_url"],
    }


def _records():
    source = _source()
    english = _offices(source, "en")
    chinese = _offices(source, "zh-Hant")
    points = _map_points(source)
    for identifier in sorted(_OFFICES):
        en, zh = english[identifier], chinese[identifier]
        yield _record(source, points, identifier, "office", en, zh)
        en_units, zh_units = _units(en), _units(zh)
        if en_units.keys() != zh_units.keys():
            raise ValueError("CMAB unit keys differ between languages")
        for key, en_unit in en_units.items():
            unit_id = "-".join(en_unit["unitName"].lower().split())
            yield _record(source, points, f"{identifier}/{unit_id}", "liaison_unit",
                          en_unit, zh_units[key])


def _normalize(value):
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def lookup(query: str) -> list[dict]:
    """Return all directory entries with an exact name, whole address, ID or postcode."""
    key = _normalize(query)
    if not key:
        return []
    matches = []
    for row in _records():
        fields = (row["record_id"], row["postcode"], *row["name"].values(),
                  *row["address"].values())
        if any(_normalize(value) == key for value in fields):
            matches.append(row)
    return matches
