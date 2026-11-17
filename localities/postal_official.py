"""Replay named official postal sources without executing embedded page code.

Source hashes and shared country/code checks are handled by ``localities.postal``.
These adapters identify specific table, JSON and PDF layouts and retain locators.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import re

from .postal_source_io import read_source_bytes, read_source_text


def _text(value: str) -> str:
    return " ".join(value.split())


class _Tables(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[dict[str, object]]] = []
        self.table: list[dict[str, object]] | None = None
        self.row: dict[str, object] | None = None
        self.cell: dict[str, object] | None = None
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            if self.table is not None:
                raise ValueError("nested official postal tables are unsupported")
            self.table = []
        elif self.table is not None and tag == "tr":
            if self.row is not None:
                raise ValueError("unclosed official postal table row")
            self.row = {"line": self.getpos()[0], "cells": []}
        elif self.row is not None and tag in {"th", "td"}:
            if self.cell is not None:
                raise ValueError("unclosed official postal table cell")
            self.cell = {"tag": tag, "colspan": dict(attrs).get("colspan", "1")}
            self.parts = []
        elif self.cell is not None and tag == "br":
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self.row is not None:
            if self.cell is None or self.cell["tag"] != tag:
                raise ValueError("mismatched official postal table cell")
            self.cell["text"] = _text("".join(self.parts))
            self.row["cells"].append(self.cell)
            self.cell = None
        elif tag == "tr" and self.table is not None:
            if self.row is None or self.cell is not None:
                raise ValueError("incomplete official postal table row")
            self.table.append(self.row)
            self.row = None
        elif tag == "table":
            if self.table is None or self.row is not None or self.cell is not None:
                raise ValueError("incomplete official postal table")
            self.tables.append(self.table)
            self.table = None

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.parts.append(data)


class _Scripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[str] = []
        self.parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            if self.parts is not None:
                raise ValueError("nested official script element")
            self.parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.parts is not None:
            self.scripts.append("".join(self.parts))
            self.parts = None

    def handle_data(self, data: str) -> None:
        if self.parts is not None:
            self.parts.append(data)


def _namibia(source: Mapping[str, object], path: Path) -> Iterator[dict[str, str]]:
    parser = _Tables()
    parser.feed(read_source_text(source, path, encoding="utf-8-sig"))
    parser.close()
    if len(parser.tables) != 1 or parser.table is not None:
        raise ValueError("NamPost source requires one complete postal table")
    region = ""
    count = 0
    for number, row in enumerate(parser.tables[0], 1):
        cells = row["cells"]
        if (len(cells) == 2 and all(cell["tag"] == "th" for cell in cells)
                and cells[1]["text"].casefold() == "post code"
                and cells[0]["text"]):
            region = cells[0]["text"]
            continue
        if (len(cells) == 1 and cells[0]["tag"] == "td"
                and cells[0]["colspan"] == "2" and cells[0]["text"] == "-"):
            continue
        if (len(cells) != 2 or not all(cell["tag"] == "td" for cell in cells)
                or any(cell["colspan"] != "1" for cell in cells)
                or not region or not cells[0]["text"]
                or not re.fullmatch(r"[0-9]{5}", cells[1]["text"])):
            raise ValueError(f"unrecognized NamPost postal row: {number}")
        count += 1
        yield {
            "country_code": "NA", "code": cells[1]["text"],
            "place_name": cells[0]["text"], "admin_name1": region,
            "source_locator": f"table:1/row:{number}/html_line:{row['line']}",
            "postal_use": "postal_infrastructure",
            "source_col_1": cells[0]["text"], "source_col_2": cells[1]["text"],
        }
    if not count:
        raise ValueError("NamPost postal table has no observations")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field in official embedded postal JSON")
        result[key] = value
    return result


def _kosovo(source: Mapping[str, object], path: Path) -> Iterator[dict[str, str]]:
    parser = _Scripts()
    parser.feed(read_source_text(source, path, encoding="utf-8-sig"))
    parser.close()
    if parser.parts is not None:
        raise ValueError("incomplete official script element")
    candidates = [
        (number, script, match.end())
        for number, script in enumerate(parser.scripts, 1)
        for match in re.finditer(r"\bconst\s+entries\s*=\s*", script)
    ]
    if len(candidates) != 1:
        raise ValueError("Kosovo source requires one embedded entries assignment")
    script_number, script, start = candidates[0]
    decoder = json.JSONDecoder(object_pairs_hook=_unique_object)
    try:
        entries, end = decoder.raw_decode(script[start:])
    except json.JSONDecodeError as error:
        raise ValueError("embedded postal entries must be literal JSON") from error
    if (not isinstance(entries, list) or not entries
            or not script[start + end:].lstrip().startswith(";")):
        raise ValueError("ambiguous embedded postal entries")
    for number, item in enumerate(entries, 1):
        if (not isinstance(item, dict) or set(item) != {"region", "subregion", "code"}
                or not all(isinstance(value, str) and value.strip() for value in item.values())
                or not re.fullmatch(r"[0-9]{5}", item["code"])):
            raise ValueError(f"invalid Kosovo postal entry: {number}")
        yield {
            "country_code": "XK", "code": item["code"],
            "place_name": item["subregion"], "admin_name1": item["region"],
            "source_locator": f"script:{script_number}/entries/index:{number}",
            "postal_use": "unspecified",
            "source_region": item["region"], "source_subregion": item["subregion"],
        }


def _read_pdf_pages(source: Mapping[str, object], path: Path) -> list[str]:
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise ValueError("the pinned pypdf dependency is required for postal PDF sources") from error
    try:
        reader = PdfReader(io.BytesIO(read_source_bytes(source, path)))
        if not 1 <= len(reader.pages) <= 64:
            raise ValueError("unsupported official postal PDF page count")
        pages = [page.extract_text() for page in reader.pages]
        if any(not isinstance(text, str) for text in pages) or sum(map(len, pages)) > 16 * 1024 * 1024:
            raise ValueError("official postal PDF has missing or excessive text")
        return pages
    except Exception as error:
        raise ValueError("cannot extract official postal PDF text") from error


def _bosnia(source: Mapping[str, object], path: Path) -> Iterator[dict[str, str]]:
    count = 0
    for page_number, text in enumerate(_read_pdf_pages(source, path), 1):
        footer = False
        for line_number, line in enumerate(text.splitlines(), 1):
            label = _text(line)
            if label.casefold() == "legenda" or label.casefold().startswith("izdavač"):
                footer = True
            if footer:
                continue
            match = re.fullmatch(r"([0-9]{5})\s+(.+?)\s+(BHP|HP|PS)\s*", line)
            if match:
                count += 1
                yield {
                    "country_code": "BA", "code": match[1], "place_name": _text(match[2]),
                    "postal_operator": match[3], "postal_use": "unspecified",
                    "operational_status": "unreviewed_from_pdf_text",
                    "source_locator": f"pdf:page={page_number}:line={line_number}",
                    "source_text_line": line, "source_place_name": match[2],
                }
            elif re.match(r"\s*[0-9]{4,6}\b", line):
                raise ValueError(f"unrecognized Bosnia postal PDF row: page {page_number}, line {line_number}")
    if not count:
        raise ValueError("Bosnia postal PDF has no observations")


ADAPTERS = {
    "na_nampost_html": ("NA", _namibia),
    "xk_postakosoves_entries": ("XK", _kosovo),
    "ba_postal_pdf": ("BA", _bosnia),
}


def iter_official_records(source: Mapping[str, object], path: Path) -> Iterator[dict[str, str]]:
    """Replay one whitelisted country/layout; never evaluate supplied JavaScript."""
    if not isinstance(source, Mapping) or source.get("format") != "official_postal_source":
        raise ValueError("official adapter requires official_postal_source format")
    adapter = source.get("adapter")
    if not isinstance(adapter, str) or adapter not in ADAPTERS:
        raise ValueError("unsupported official postal adapter")
    country, reader = ADAPTERS[adapter]
    if source.get("expected_country") != country:
        raise ValueError("official postal adapter country mismatch")
    kind = source.get("default_code_kind")
    if not isinstance(kind, str) or kind not in {"official_full", "partial_or_legacy"}:
        raise ValueError("unsupported official postal code kind")
    if adapter == "ba_postal_pdf" and kind != "partial_or_legacy":
        raise ValueError("Bosnia PDF must retain partial_or_legacy status")
    yield from reader(source, Path(path))
