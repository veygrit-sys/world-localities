"""Japan Post's row-linked November 2026 romanized postal labels."""

from collections import namedtuple
import csv
from functools import cache
import gzip
import hashlib
import json
from pathlib import Path
import re

DATA = Path(__file__).with_name("data")
SOURCE = json.loads((DATA / "source.json").read_text(encoding="utf-8"))
Row = namedtuple("Row", "code native_row roman_row prefecture_ja municipality_ja town_ja "
                 "prefecture_kana municipality_kana town_kana prefecture_roman municipality_roman town_roman")


@cache
def _shard(file, digest, row_count):
    payload = (DATA / file).read_bytes()
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("Japan Post romanized label checksum mismatch")
    data = gzip.decompress(payload)
    if data[:data.index(b"\n")].decode().split(",") != list(Row._fields):
        raise ValueError("unexpected Japan Post romanized label columns")
    # The projection writer emits single-line records sorted by complete postcode.
    offsets = {}
    count = 0
    for match in re.finditer(rb"^([0-9]{7}),.*\n", data, re.MULTILINE):
        code = match[1]
        if code in offsets:
            offsets[code][1] = match.end()
        else:
            offsets[code] = [match.start(), match.end()]
        count += 1
    if count != row_count:
        raise ValueError("unexpected Japan Post romanized label row count")
    return data, offsets


def rows(postcode):
    if not re.fullmatch(r"[0-9]{3}-?[0-9]{4}", postcode):
        return []
    code = postcode.replace("-", "")
    found = []
    for shard in SOURCE["shards"]:
        if shard["first"] <= code <= shard["last"]:
            data, offsets = _shard(shard["file"], shard["sha256"], shard["rows"])
            bounds = offsets.get(code.encode())
            if bounds:
                start, end = bounds
                found.extend(Row(*r) for r in csv.reader(data[start:end].decode().splitlines()))
    return found


def receipt(row):
    return {"source_id": SOURCE["source_id"], "source_row": row.roman_row,
            "url": SOURCE["url"], "sha256": SOURCE["sha256"], "snapshot": SOURCE["published_on"],
            "attribution": "Japan Post", "terms_url": SOURCE["terms_url"],
            "native_record_id": SOURCE["native_source_id"] + ":" + row.native_row}
