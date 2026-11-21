"""Reproject the pinned United Nations WUP file and compare all retained rows."""

import argparse
import csv
import gzip
import hashlib
import io
import math
import re
from pathlib import Path
from urllib.request import urlopen


FIELDS = ("ISO2_Code", "ISO3_Code", "LocID", "City_Code", "City_Name",
          "PWCent_Latitude", "PWCent_Longitude")
HEADER = (*FIELDS, "source_row")


def project(raw: bytes) -> tuple[bytes, int]:
    cities = []
    seen_ids = set()
    source_rows = 0
    stream = gzip.GzipFile(fileobj=io.BytesIO(raw))
    with io.TextIOWrapper(stream, encoding="utf-8-sig", newline="") as text:
        reader = csv.DictReader(text)
        if not set((*FIELDS, "Year")).issubset(reader.fieldnames or ()):
            raise ValueError("UN WUP source schema changed")
        for source_row, row in enumerate(reader, start=2):
            source_rows += 1
            if row["Year"] != "2025":
                continue
            city_id = row["City_Code"]
            coords = (float(row["PWCent_Latitude"]), float(row["PWCent_Longitude"]))
            if (not re.fullmatch("[0-9]+", city_id) or city_id in seen_ids
                    or not re.fullmatch("[A-Z]{2}", row["ISO2_Code"])
                    or not row["City_Name"].strip() or not all(map(math.isfinite, coords))
                    or abs(coords[0]) > 90 or abs(coords[1]) > 180):
                raise ValueError(f"Invalid or duplicate UN WUP city on row {source_row}")
            seen_ids.add(city_id)
            cities.append((*[row[field] for field in FIELDS], str(source_row)))

    cities.sort(key=lambda values: (values[0], int(values[3])))
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(cities)
    return output.getvalue().encode("utf-8"), source_rows


def main():
    from . import SOURCE, _snapshot

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-file", type=Path, help="use a local copy of the UN gzip")
    args = parser.parse_args()
    if args.source_file:
        raw = args.source_file.read_bytes()
    else:
        with urlopen(SOURCE["url"], timeout=90) as response:
            raw = response.read(SOURCE["bytes"] + 1)
    if len(raw) != SOURCE["bytes"] or hashlib.sha256(raw).hexdigest() != SOURCE["sha256"]:
        raise ValueError("UN WUP source differs from the pinned version")
    derived, source_rows = project(raw)
    if source_rows != SOURCE["source_rows"] or derived != _snapshot():
        raise ValueError("UN WUP 2025 projection differs from the packaged records")
    print(f"{source_rows} source rows; {SOURCE['retained_rows']} matching 2025 rows.")


if __name__ == "__main__":
    main()
