"""Reproduce the retained contact-free projections from the pinned public CSVs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from urllib.request import urlopen

from . import DIRECTORY


def project(data: bytes, source: dict) -> bytes:
    if len(data) != source["bytes"] or hashlib.sha256(data).hexdigest() != source["sha256"]:
        raise ValueError(f"Source changed: {source['id']}")
    reader = csv.DictReader(io.StringIO(data.decode("cp1252"), newline=""))
    if reader.fieldnames != source["headers"]:
        raise ValueError("Unexpected source schema")
    out = io.StringIO(newline="")
    fields = source["columns"]
    writer = csv.DictWriter(out, fieldnames=["source_row", *fields], lineterminator="\n")
    writer.writeheader()
    seen = set()
    for line, raw in enumerate(reader, start=2):
        if None in raw or any(v is None for v in raw.values()):
            raise ValueError(f"Malformed source record {line}")
        if not any(raw.values()):
            continue
        row = {name: raw[original] for name, original in fields.items()}
        name = row["office_name"].strip().casefold()
        if not name or name in seen:
            raise ValueError(f"Missing or repeated name in row {line}")
        seen.add(name)
        if row["postcode"] and not re.fullmatch("[0-9]{5}", row["postcode"]):
            raise ValueError(f"Unexpected postal value in row {line}")
        if "longitude" in row:
            if not (-180 <= float(row["longitude"]) <= 180 and -90 <= float(row["latitude"]) <= 90):
                raise ValueError(f"Invalid coordinates in row {line}")
        writer.writerow({"source_row": line, **row})
    if len(seen) != source["records"]:
        raise ValueError("Unexpected office count")
    return out.getvalue().encode("utf-8")


def verify(download: bool = False) -> dict[str, int]:
    manifest = json.loads((DIRECTORY / "sources.json").read_text(encoding="utf-8"))
    counts = {}
    for source in manifest["sources"]:
        retained = (DIRECTORY / source["file"]).read_bytes()
        if hashlib.sha256(retained).hexdigest() != source["file_sha256"]:
            raise ValueError(f"Changed projection: {source['file']}")
        if download:
            with urlopen(source["url"], timeout=30) as response:
                raw = response.read(source["bytes"] + 1)
            if project(raw, source) != retained:
                raise ValueError(f"Projection differs for {source['id']}")
        counts[source["id"]] = source["records"]
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true", help="also replay both public downloads")
    print(json.dumps(verify(parser.parse_args().download), sort_keys=True))
