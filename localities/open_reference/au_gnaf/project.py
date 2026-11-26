"""Rebuild the two bounded G-NAF extracts with PyArrow from manifest-pinned Parquets."""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path


COLUMNS = ("gnaf_pid locality_pid street_locality_pid state locality_name address number_first number_last "
           "flat_number level_number street_name street_type street_suffix alias_principal primary_secondary "
           "latitude longitude geocode_type reliability confidence").split()
EDGE_COLUMNS = ["primary_pid", "secondary_pid", "join_type"]


def write_csv(rows, columns, target):
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(sorted(rows, key=lambda row: tuple(str(row[k] or "") for k in columns)))
    with target.open("wb") as f, gzip.GzipFile(filename="", fileobj=f, mode="wb", mtime=0) as stream:
        stream.write(text.getvalue().encode("utf-8"))


def project(raw_dir, target):
    import pyarrow.parquet as pq  # Only needed to reproduce the source projection.
    manifest = json.loads(Path(__file__).with_name("source.json").read_bytes())

    def input_rows(table, columns):
        source = manifest["inputs"][table]
        path = raw_dir / source["file"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != source["sha256"]:
            raise ValueError("Pinned G-NAF input differs: " + source["file"])
        for batch in pq.ParquetFile(path).iter_batches(columns=columns):
            yield from batch.to_pylist()

    rows = [row for row in input_rows("principals", COLUMNS)
            if (row["state"], row["locality_name"]) in {("OT", "JERVIS BAY"), ("ACT", "BARTON"), ("ACT", "ACTON")}]
    ids = {row["gnaf_pid"] for row in rows}
    edges = [row for row in input_rows("secondary_links", EDGE_COLUMNS)
             if row["primary_pid"] in ids and row["secondary_pid"] in ids]
    target.mkdir(exist_ok=True, parents=True)
    write_csv(rows, COLUMNS, target / "points.csv.gz")
    write_csv(edges, EDGE_COLUMNS, target / "links.csv.gz")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("raw_dir", type=Path)
    p.add_argument("target", type=Path)
    args = p.parse_args()
    project(args.raw_dir, args.target)
