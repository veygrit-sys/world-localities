"""Replay the projection from the pinned public Geofabrik extract."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
NAME_LANGUAGE = re.compile(r"name:[a-z]{2,3}(?:-[a-zA-Z0-9]{2,8})*")
ADDRESS_TAGS = ("addr:country", "addr:state", "addr:city", "addr:postcode",
                "addr:street", "addr:housenumber", "addr:unit")
OSM_TYPES = {"n": "node", "w": "way", "r": "relation"}


def project(obj):
    tags = obj.tags
    if tags.get("amenity") != "library" and tags.get("tourism") != "museum":
        return None
    if tags.get("addr:state") != "DC" or tags.get("addr:country", "US") != "US":
        return None
    if not all(tags.get(k) for k in ("name", "addr:housenumber", "addr:street")):
        return None

    selected = {k: v for k, v in tags if k in ADDRESS_TAGS or k == "name"
                or NAME_LANGUAGE.fullmatch(k)}
    if tags.get("amenity") == "library":
        selected["amenity"] = "library"
    if tags.get("tourism") == "museum":
        selected["tourism"] = "museum"
    row = {
        "osm_type": OSM_TYPES[obj.type_str()],
        "osm_id": obj.id,
        "osm_version": obj.version,
        "osm_timestamp": obj.timestamp.isoformat().replace("+00:00", "Z"),
        "tags": selected,
    }
    if row["osm_type"] == "node":
        row["position"] = {"lat": obj.location.lat, "lon": obj.location.lon}
    return row


def project_file(path, source):
    import osmium  # Only replay requires the repository's optional PBF reader.

    if path.stat().st_size != source["source_size_bytes"]:
        raise ValueError("source size differs from the pinned snapshot")
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != source["source_sha256"]:
            raise ValueError("source SHA-256 differs from the pinned snapshot")
    with osmium.io.Reader(str(path)) as reader:
        if reader.header().get("osmosis_replication_timestamp") != source["replication_timestamp"]:
            raise ValueError("replication timestamp differs from the pinned snapshot")

    rows = []
    for obj in osmium.FileProcessor(str(path)):
        row = project(obj)
        if row is not None:
            rows.append(row)
    rows.sort(key=lambda row: (row["osm_type"], row["osm_id"]))
    if len(rows) != source["record_count"]:
        raise ValueError("projection count differs from the pinned snapshot")
    return "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", type=Path, help="local copy; otherwise download the pinned public PBF")
    args = parser.parse_args()
    source = json.loads((HERE / "source.json").read_text())
    with TemporaryDirectory() as directory:
        path = args.pbf
        if path is None:
            path = Path(directory) / "dc.osm.pbf"
            with urlopen(source["url"], timeout=90) as response:
                data = response.read(source["source_size_bytes"] + 1)
            path.write_bytes(data)
        projection = project_file(path, source)
    if projection != (HERE / "records.jsonl").read_bytes():
        raise SystemExit("projection differs from records.jsonl")
    print(f'{source["record_count"]} source objects reproduced')


if __name__ == "__main__":
    main()
