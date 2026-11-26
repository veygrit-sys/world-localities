"""Rebuild the Wakayama projection using the pinned Geolonia copy of ABR data."""
import csv
import gzip
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOWNS = {"0023002", "0023003", "0058000", "0304000"}


def project(cache_dir, destination):
    manifest = json.loads((ROOT / "sources.json").read_text())
    result = []
    for kind, source in manifest["abr"].items():
        archive = (cache_dir / source["cache_file"]).read_bytes()
        if hashlib.sha256(archive).hexdigest() != source["cache_sha256"]:
            raise ValueError("unexpected ABR cache archive")
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            with zipped.open(source["csv"]) as raw:
                for row in csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig")):
                    if row["lg_code"] != "302015" or row["machiaza_id"] not in TOWNS or row["ablt_date"]:
                        continue
                    if kind == "frontage":
                        if (row["basic_rsdt_div"], row["status_flg"]) != ("0", "0"):
                            raise ValueError("review newly assigned residential numbers before importing")
                        numbers = [row["blk_num"], row["rsdt_num"], row["rsdt_num2"]]
                        ids = [row["blk_id"], row["rsdt_id"], row["rsdt2_id"]]
                    else:
                        numbers = [row["prc_num1"], row["prc_num2"], row["prc_num3"]]
                        ids = [row["prc_id"]]
                    if not numbers[0] or not all(v.isascii() and v.isdigit() for v in numbers if v):
                        raise ValueError("unexpected number syntax")
                    result.append((row["machiaza_id"], kind, "-".join(v for v in numbers if v), ":".join(v for v in ids if v)))
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["machiaza_id", "kind", "number", "official_key"])
    writer.writerows(sorted(result))
    # Empty filename and zero mtime keep the gzip header deterministic.
    with destination.open("wb") as stream, gzip.GzipFile(fileobj=stream, filename="", mode="wb", mtime=0) as archived:
        archived.write(output.getvalue().encode())


if __name__ == "__main__":
    project(Path(sys.argv[1]), Path(sys.argv[2]))
