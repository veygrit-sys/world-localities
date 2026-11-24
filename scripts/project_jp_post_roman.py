"""Join two pinned Japan Post CSVs using postcode and complete Japanese address fields."""
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import zipfile

NATIVE_SHA = "db92fcf624bb7280e6f51900aebe03adeafbd168796e59412dbc22a80abb85b9"
ROMAN_SHA = "21bcdd0557e07202f4a65a9aef22daf1f9b74a98be6121b28f9675b7c82fc9a7"
FIELDS = ["code", "native_row", "roman_row", "prefecture_ja", "municipality_ja", "town_ja",
          "prefecture_kana", "municipality_kana", "town_kana",
          "prefecture_roman", "municipality_roman", "town_roman"]


def load(path, expected, member, encoding, width):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"unexpected source bytes for {member}")
    with zipfile.ZipFile(io.BytesIO(data)) as z, z.open(member) as f:
        rows = list(csv.reader(io.TextIOWrapper(f, encoding=encoding, newline="")))
    if any(len(r) != width for r in rows):
        raise ValueError("unexpected source columns")
    return rows


def identity(code, labels):
    return (code, *("".join(v.split()) for v in labels))


def project(native_zip, roman_zip, target):
    native = load(native_zip, NATIVE_SHA, "utf_ken_all.csv", "utf-8-sig", 15)
    roman = load(roman_zip, ROMAN_SHA, "KEN_ALL_ROME.CSV", "cp932", 7)
    candidates = defaultdict(list)
    for i, row in enumerate(roman, 1):
        candidates[identity(row[0], row[1:4])].append((i, row))
    native_keys = Counter(identity(row[2], row[6:9]) for row in native)
    stats = Counter()
    records = []
    for i, row in enumerate(native, 1):
        key = identity(row[2], row[6:9])
        matches = candidates.get(key, [])
        if not matches:
            stats["no_exact_match"] += 1
            continue
        if len(matches) != 1 or native_keys[key] != 1:
            stats["ambiguous"] += 1
            continue
        j, rr = matches[0]
        # Japan Post's capped fields may be a cut-off prefix. Reuse the existing
        # registry's conservative widths, including rows exactly at the limit.
        if any(len(v) >= 17 for v in rr[2:4]) or any(len(v) >= 35 for v in rr[5:7]):
            stats["possibly_truncated"] += 1
            continue
        records.append([row[2], i, j, *row[6:9], *row[3:6], *rr[4:7]])
    records.sort()
    target.mkdir(exist_ok=False, parents=True)
    shards = []
    for offset in range(0, len(records), 6000):
        part = records[offset:offset+6000]
        buf = io.StringIO(newline="")
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(FIELDS)
        writer.writerows(part)
        bufzip = io.BytesIO()
        with gzip.GzipFile(fileobj=bufzip, mode="wb", mtime=0) as f:
            f.write(buf.getvalue().encode())
        data = bufzip.getvalue()
        filename = f"labels-{len(shards) + 1:02}.csv.gz"
        (target / filename).write_bytes(data)
        shards.append(dict(file=filename, first=part[0][0], last=part[-1][0], rows=len(part),
                           sha256=hashlib.sha256(data).hexdigest()))
    manifest = dict(source_id="japanpost-roman-20261109", published_on="2026-11-09", retrieved_on="2026-11-24",
                    url="https://www.post.japanpost.jp/service/search/zipcode/download/roman/KEN_ALL_ROME.zip",
                    catalog="https://www.post.japanpost.jp/service/search/zipcode/download/roman-zip.html",
                    terms_url="https://www.post.japanpost.jp/service/search/zipcode/download/readme_ro.html",
                    native_source_id="japanpost-postal-20261030", native_sha256=NATIVE_SHA, sha256=ROMAN_SHA,
                    roman_rows=len(roman), native_rows=len(native), retained=len(records),
                    postcodes=len({r[0] for r in records}), excluded=dict(stats), shards=shards)
    (target / "source.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("native_zip", "roman_zip", "target"):
        p.add_argument(name, type=Path)
    args = p.parse_args()
    project(args.native_zip, args.roman_zip, args.target)
