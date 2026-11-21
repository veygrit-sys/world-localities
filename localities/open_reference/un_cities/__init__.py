"""Offline exact-name lookup of United Nations WUP 2025 urban centres."""

import base64
import csv
import gzip
import hashlib
import io
import json
import unicodedata
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path


_ROOT = Path(__file__).parent
SOURCE = json.loads((_ROOT / "source.json").read_text(encoding="utf-8"))
COUNTRIES = frozenset(SOURCE["country_counts"])


def _snapshot():
    encoded = (_ROOT / "cities.csv.gz.b64").read_bytes()
    data = gzip.decompress(base64.b64decode(b"".join(encoded.split()), validate=True))
    if (len(data) != SOURCE["projection_bytes"]
            or hashlib.sha256(data).hexdigest() != SOURCE["projection_sha256"]):
        raise ValueError("UN urban-centre projection has changed")
    return data


def _normalize(text):
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


@lru_cache(maxsize=1)
def _index():
    by_key = defaultdict(list)
    counts = Counter()
    with io.StringIO(_snapshot().decode("utf-8"), newline="") as text:
        for row in csv.DictReader(text):
            country = row["ISO2_Code"]
            record_id = "un-wup2025:" + row["City_Code"]
            keys = {_normalize(row["City_Name"]), record_id}
            for key in keys:
                by_key[(country, key)].append(row)
            counts[country] += 1
    if counts != SOURCE["country_counts"] or counts.total() != SOURCE["retained_rows"]:
        raise ValueError("UN urban-centre country inventory has changed")
    return by_key


def lookup(query: str, *, country: str) -> list[dict]:
    """Find source city labels or qualified record IDs only within the given country."""
    candidates = _index().get((country.upper(), _normalize(query)), ())
    return [
        {
            "record_id": "un-wup2025:" + row["City_Code"],
            "country": row["ISO2_Code"],
            "source_country_iso3": row["ISO3_Code"],
            "source_area_id": row["LocID"],
            "city_code": row["City_Code"],
            "name": row["City_Name"],
            "evidence_type": "statistical_urban_centre",
            "population_weighted_centroid": {
                "latitude": float(row["PWCent_Latitude"]),
                "longitude": float(row["PWCent_Longitude"]),
            },
            "source_year": 2025,
            "source_row": int(row["source_row"]),
            "source_id": SOURCE["source_id"],
            "source_url": SOURCE["url"],
            "terms_url": SOURCE["terms_url"],
            "attribution": SOURCE["attribution"],
        }
        for row in candidates
    ]
