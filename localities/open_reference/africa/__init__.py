"""Offline Mauritius government post-office directory lookups."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

DIRECTORY = Path(__file__).resolve().parent


def _key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


@lru_cache(maxsize=1)
def _records() -> tuple[dict, ...]:
    manifest = json.loads((DIRECTORY / "sources.json").read_text(encoding="utf-8"))
    records = []
    for source in manifest["sources"]:
        data = (DIRECTORY / source["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != source["file_sha256"]:
            raise ValueError(f"Changed Mauritius snapshot: {source['file']}")
        rows = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""))
        for row in rows:
            # Office labels are unique within each pinned directory. Keep the two
            # sources separate even if a postcode, street and office all agree.
            record_id = f"{source['id']}:{quote(_key(row['office_name']), safe='')}"
            records.append(dict(
                row,
                record_id=record_id,
                country="MU",
                source_id=source["id"],
                source_row=int(row["source_row"]),
                source_url=source["url"],
                source_sha256=source["sha256"],
                attribution=f"{manifest['publisher']} — {source['title']}",
                license=manifest["license"],
                license_url=manifest["license_url"],
                evidence_level="published_post_office_listing",
            ))
    return tuple(records)


def lookup(query: str) -> list[dict]:
    """Match complete source office names, published addresses or postcodes."""
    key = _key(query)
    if not key:
        return []
    return [
        row.copy() for row in _records()
        if any(key == _key(row[field]) for field in ("office_name", "address", "postcode"))
    ]
