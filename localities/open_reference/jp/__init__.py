"""Exact locality-label lookup in the Japanese government's 2021 gazetteer."""
import csv
from hashlib import sha256
import io
from functools import lru_cache
import json
from pathlib import Path
import unicodedata


_DIRECTORY = Path(__file__).resolve().parent


def _key(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split())


@lru_cache(maxsize=1)
def _index() -> dict[str, list[dict]]:
    source = json.loads((_DIRECTORY / "source.json").read_text(encoding="utf-8"))
    data = (_DIRECTORY / "names.csv").read_bytes()
    if sha256(data).hexdigest() != source["projection"]["sha256"]:
        raise ValueError("Japanese gazetteer projection SHA-256 mismatch")
    names = {}
    for row in csv.DictReader(io.StringIO(data.decode("utf-8"), newline="")):
        record_id = f"{source['source_id']}-{row['source_row']}"
        record = {
            "country": "JP",
            "record_id": record_id,
            "source_id": source["source_id"],
            "attribution": source["attribution"],
            "terms_url": source["terms"],
            "source_as_of": source["source_as_of"],
            "source_row": int(row["source_row"]),
            "source_url": f"{source['gazetteer']['url']}#page={row['pdf_page']}",
            "source_grid": row["grid"],
            "classification": row["classification"],
            "kanji": row["kanji"] or None,
            "kana": row["kana"],
            "romanized": row["romanized"],
        }
        for label in {record_id, row["kanji"], row["kana"], row["romanized"]} - {""}:
            names.setdefault(_key(label), []).append(record)
    return names


def lookup(query: str) -> list[dict]:
    """Return every entry sharing this exact name, reading, romanization or record ID."""
    return [row.copy() for row in _index().get(_key(query), ())]
