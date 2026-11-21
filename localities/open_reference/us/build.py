"""Build a candidate DC MAR projection from the city CSV and two independent API queries."""

import argparse
import csv
from datetime import datetime, timezone
import gzip
from hashlib import sha256
import io
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from urllib.parse import urlencode
from urllib.request import urlopen

from .schema import FIELDS, _id_set_hash

QUERY = "https://maps2.dcgis.dc.gov/dcgis/rest/services/DCGIS_DATA/Location_WebMercator/FeatureServer/0/query?"
WHERE = "STATUS = 'ACTIVE' AND ADDRESS_TYPE = 'ADDRESS'"
URLS = {
    "all.csv": "https://opendata.dc.gov/api/download/v1/items/aa514416aaf74fdc94748f1e56e7cc8a/csv?layers=0",
    "oids.json": QUERY + urlencode({"where": WHERE, "returnIdsOnly": "true", "f": "json"}),
    "all-count.json": QUERY + urlencode({"where": WHERE, "returnCountOnly": "true", "f": "json"}),
}
SHARD_ROWS = 20000


def _file_hash(path: Path) -> str:
    with path.open("rb") as handle:
        fingerprint = sha256()
        for block in iter(lambda: handle.read(1 << 20), b""):
            fingerprint.update(block)
        return fingerprint.hexdigest()


def download(directory: Path) -> None:
    for name, url in URLS.items():
        with urlopen(url, timeout=120) as response, (directory / name).open("wb") as target:
            shutil.copyfileobj(response, target)


def build(inputs: Path, output: Path, *, retrieved_utc: str) -> dict:
    """Build a complete candidate or reject incompatible data before writing any shard."""
    selection = []
    object_ids = set()
    mar_ids = set()
    source_rows = 0
    with (inputs / "all.csv").open(encoding="utf-8-sig", newline="") as data:
        table = csv.DictReader(data)
        if not set((*FIELDS, "ADDRESS_TYPE", "STATUS")).issubset(table.fieldnames or []):
            raise ValueError("Missing fields in DC MAR catalog export")
        for row in table:
            source_rows += 1
            if row["STATUS"] != "ACTIVE" or row["ADDRESS_TYPE"] != "ADDRESS":
                continue
            oid, mar_id = int(row["OBJECTID"]), row["MAR_ID"]
            if oid in object_ids or mar_id in mar_ids or not mar_id.isascii() or not mar_id.isdecimal():
                raise ValueError("Duplicate or invalid source identifier")
            object_ids.add(oid)
            mar_ids.add(mar_id)
            if not row["ADDRESS"] or row["STATE"] != "DC":
                raise ValueError(f"Unexpected DC MAR record {mar_id}")
            if row["ZIPCODE"] and (len(row["ZIPCODE"]) != 5 or not row["ZIPCODE"].isascii()
                                   or not row["ZIPCODE"].isdecimal()):
                raise ValueError(f"Invalid ZIP field on MAR record {mar_id}")
            selection.append(tuple(row[field] for field in FIELDS))

    ids_response = json.loads((inputs / "oids.json").read_bytes())
    published_ids = ids_response["objectIds"]
    count = json.loads((inputs / "all-count.json").read_bytes())["count"]
    if (ids_response["objectIdFieldName"] != "OBJECTID" or not selection or count != len(selection)
            or len(published_ids) != count or set(published_ids) != object_ids):
        raise ValueError("Bulk CSV and the independent count / object-ID query disagree")

    selection.sort(key=lambda row: int(row[0]))
    output.mkdir(parents=True, exist_ok=False)
    shards = []
    for i in range(0, len(selection), SHARD_ROWS):
        part = selection[i:i + SHARD_ROWS]
        writer = io.StringIO(newline="")
        csv_out = csv.writer(writer, lineterminator="\n")
        csv_out.writerow(FIELDS)
        csv_out.writerows(part)
        plain = writer.getvalue().encode("utf-8")
        filename = f"points-{i // SHARD_ROWS + 1:02d}.csv.gz"
        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, filename="", mode="wb", mtime=0) as stream:
            stream.write(plain)
        packed = buffer.getvalue()
        (output / filename).write_bytes(packed)
        shards.append({"file": filename, "rows": len(part), "bytes": len(packed),
                       "sha256": sha256(packed).hexdigest(), "csv_sha256": sha256(plain).hexdigest(),
                       "first_mar_id": part[0][0], "last_mar_id": part[-1][0]})
    manifest = {
        "source_id": "us-dc-mar",
        "title": "Address Points, Master Address Repository",
        "publisher": "District of Columbia, Office of the Chief Technology Officer (OCTO)",
        "catalog_url": "https://opendata.dc.gov/datasets/DCGIS::address-points",
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "license_evidence": "https://www.arcgis.com/sharing/rest/content/items/aa514416aaf74fdc94748f1e56e7cc8a?f=json",
        "retrieved_utc": retrieved_utc,
        "sources": {name: {"url": url, "sha256": _file_hash(inputs / name),
                           "bytes": (inputs / name).stat().st_size} for name, url in URLS.items()},
        "scope": WHERE,
        "total_export_rows": source_rows, "selected_address_points": count,
        "distinct_nonempty_zip_values": len({row[5] for row in selection if row[5]}),
        "independent_object_id_set_sha256": _id_set_hash(published_ids),
        "shards": shards,
    }
    (output / "citywide.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="new candidate directory")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("--output must be a new directory")
    with TemporaryDirectory() as temp:
        inputs = Path(temp)
        download(inputs)
        result = build(inputs, args.output, retrieved_utc=datetime.now(timezone.utc).date().isoformat())
    print(json.dumps({"export_rows": result["total_export_rows"], "address_points": result["selected_address_points"]}))


if __name__ == "__main__":
    main()
