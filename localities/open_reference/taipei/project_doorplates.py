"""Rebuild the twelve district files from the reviewed municipal CSV into a new directory."""

import argparse
from collections import Counter
import csv
import hashlib
import json
import lzma
from pathlib import Path
from tempfile import TemporaryDirectory

from . import DISTRICTS, normalized, source

HEADER = "省市縣市代碼 鄉鎮市區代碼 村里 鄰 街路段 地區 巷 弄 號 橫座標 縱座標".split()


def project(csv_path, output, metadata):
    output = Path(output)
    if output.exists():
        raise ValueError("choose a new output directory")
    csv_path = Path(csv_path)
    with csv_path.open("rb") as src:
        if hashlib.file_digest(src, "sha256").hexdigest() != metadata["raw_sha256"]:
            raise ValueError("Taipei source hash mismatch")
    groups = {code: Counter() for code in DISTRICTS}
    skipped = total = 0
    with csv_path.open(encoding="utf-8-sig", newline="") as src:
        reader = csv.DictReader(src, strict=True)
        if reader.fieldnames != HEADER:
            raise ValueError("unexpected Taipei municipal CSV columns")
        for row in reader:
            total += 1
            code = row["鄉鎮市區代碼"]
            if row["省市縣市代碼"] != "63000" or code not in groups or None in row or None in row.values():
                raise ValueError(f"invalid source row {reader.line_num}")
            if not (row["街路段"] or row["地區"]) or not row["號"]:
                skipped += 1
                continue
            label = "".join(row[col] for col in ("街路段", "地區", "巷", "弄", "號"))
            village = row["村里"]
            if any(ch in label + village for ch in "\t\r\n\u0085\u2028\u2029"):
                raise ValueError(f"unexpected separator on source row {reader.line_num}")
            groups[code][label, village] += 1
    if total != metadata["source_rows"] or not all(groups.values()):
        raise ValueError("incomplete Taipei source table")
    districts = {}
    with TemporaryDirectory(dir=output.parent) as temp:
        stage = Path(temp) / "districts"
        stage.mkdir()
        for code, entries in groups.items():
            ordered = sorted(entries, key=lambda pair: (normalized(pair[0]), *pair))
            body = "".join(f"{label}\t{village}\t{entries[label, village]}\n" for label, village in ordered)
            data = lzma.compress(body.encode("utf-8"), preset=6)
            (stage / (code + ".tsv.xz")).write_bytes(data)
            districts[code] = {"labels": len(entries), "source_rows": sum(entries.values()),
                               "sha256": hashlib.sha256(data).hexdigest()}
        manifest = {**metadata, "excluded_incomplete_rows": skipped, "districts": districts}
        if "districts" in metadata and manifest != metadata:
            raise ValueError("Taipei projection differs from its reviewed manifest")
        (stage / "source.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        stage.rename(output)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(project(args.csv, args.output, source()), ensure_ascii=False))
