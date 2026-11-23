"""Offline lookup of complete Taipei City doorplate labels within one district."""

from bisect import bisect_left
from functools import cache, lru_cache
import hashlib
import json
import lzma
from pathlib import Path
import unicodedata

DIRECTORY = Path(__file__).resolve().parent
DISTRICTS = {
    "63000010": "松山區", "63000020": "信義區", "63000030": "大安區", "63000040": "中山區",
    "63000050": "中正區", "63000060": "大同區", "63000070": "萬華區", "63000080": "文山區",
    "63000090": "南港區", "63000100": "內湖區", "63000110": "士林區", "63000120": "北投區",
}


def normalized(value):
    return unicodedata.normalize("NFKC", value).strip()


@cache
def source():
    return json.loads((DIRECTORY / "source.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=2)
def district_rows(code):
    spec = source()["districts"][code]
    data = (DIRECTORY / (code + ".tsv.xz")).read_bytes()
    if hashlib.sha256(data).hexdigest() != spec["sha256"]:
        raise ValueError("Taipei district archive differs from its source manifest")
    rows = []
    for line in lzma.decompress(data).decode("utf-8").splitlines():
        label, village, count = line.split("\t")
        rows.append((normalized(label), label, village, int(count)))
    if len(rows) != spec["labels"]:
        raise ValueError("Taipei district row count differs from its source manifest")
    return rows


def lookup(query):
    """Accept the district followed by the exact doorplate, optionally prefixed with Taipei City."""
    text = normalized(query)
    for prefix in ("臺北市", "台北市"):
        if text.startswith(prefix):
            text = text[len(prefix):].lstrip()
            break
    for code, district in DISTRICTS.items():
        if text.startswith(district):
            break
    else:
        return []
    key = text[len(district):].strip()
    if not key:
        return []
    rows = district_rows(code)
    pos = bisect_left(rows, (key,))
    hits = []
    meta = source()
    while pos < len(rows) and rows[pos][0] == key:
        _, label, village, count = rows[pos]
        identity = hashlib.sha256(f"{code}\t{label}\t{village}".encode()).hexdigest()
        hits.append({"record_id": f"taipei:{identity}", "source_id": meta["source_id"], "country": "TW",
                     "district_code": code, "district": district, "village": village,
                     "label": "臺北市" + district + label, "scope": "municipal_doorplate",
                     "source_rows": count, "source_as_of": meta["source_as_of"], "source_url": meta["source_url"],
                     "terms_url": meta["terms_url"], "attribution": meta["attribution"]})
        pos += 1
    return hits
