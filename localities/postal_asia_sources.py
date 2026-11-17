"""Replay pinned Asian postal lists without generating postal assignments."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any

from .postal_source_io import read_source_text


COUNTRIES = {"kh_mef_bundle": "KH", "la_postcode_api": "LA", "uz_postal_html": "UZ"}
KH_FIELDS = (
    "provincial_postalarea_kh", "provincial_postalarea_en", "provincial_postal_code",
    "district_postalarea_kh", "district_postalarea_en", "district_postal_code",
    "commune_postalarea_kh", "commune_postalarea_en", "commune_postal_code",
)


def _text(value: object, label: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ValueError(f"invalid postal source {label}")
    return value


def _integer(value: object, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"invalid postal source {label}")
    return value


def _json(source: Mapping[str, Any], path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(read_source_text(source, path, encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("cannot read Asian postal source") from error
    if not isinstance(payload, dict):
        raise ValueError("Asian postal source must be an object")
    return payload


def _pages(source: Mapping[str, Any], path: Path) -> list[tuple[dict[str, Any], str]]:
    """Check each original UTF-8 response, which is retained verbatim in the bundle."""
    payload = _json(source, path)
    pages = payload.get("pages")
    if payload.get("schema_version") != 1 or not isinstance(pages, list) or not pages:
        raise ValueError("invalid Asian postal response bundle")
    checked = []
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("receipt"), dict):
            raise ValueError("postal response requires a receipt")
        receipt = page["receipt"]
        raw = _text(page.get("raw_utf8"), "raw response").encode("utf-8")
        digest = receipt.get("sha256")
        if (not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)
                or len(raw) != _integer(receipt.get("bytes"), "response bytes")
                or hashlib.sha256(raw).hexdigest() != digest):
            raise ValueError("postal response receipt mismatch")
        url = _text(receipt.get("url"), "response URL")
        if not url.startswith("https://"):
            raise ValueError("postal response requires an HTTPS URL")
        try:
            response = json.loads(raw)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("invalid original postal JSON response") from error
        if not isinstance(response, dict) or (
            "response" in page and page["response"] != response
        ):
            raise ValueError("postal response differs from retained original")
        checked.append((response, url))
    return checked


def _kh(source: Mapping[str, Any], path: Path) -> Iterator[dict[str, str]]:
    pages = _pages(source, path)
    rows: list[dict[str, str]] = []
    total: int | None = None
    page_size: int | None = None
    for number, (response, url) in enumerate(pages, 1):
        count = _integer(response.get("total_items"), "Cambodia item count", 1)
        size = _integer(response.get("page_size"), "Cambodia page size", 1)
        if total is None:
            total, page_size = count, size
        if (_integer(response.get("page"), "Cambodia page", 1) != number
                or _integer(response.get("total_pages"), "Cambodia pages", 1) != len(pages)
                or total != count or page_size != size
                or len(pages) != (count + size - 1) // size):
            raise ValueError("inconsistent Cambodia postal pagination")
        items = response.get("items")
        expected_size = min(size, count - (number - 1) * size)
        if not isinstance(items, list) or len(items) != expected_size:
            raise ValueError("incomplete Cambodia postal page")
        for item_number, item in enumerate(items, 1):
            if not isinstance(item, dict):
                raise ValueError("invalid Cambodia postal row")
            fields = {key: _text(item.get(key), key) for key in KH_FIELDS}
            if any(not re.fullmatch(r"[0-9]{6}", fields[key]) for key in (
                "provincial_postal_code", "district_postal_code", "commune_postal_code"
            )):
                raise ValueError("Cambodia postal row requires six-digit source codes")
            rows.append({
                "country_code": "KH", "code": fields["commune_postal_code"],
                "place_name": fields["commune_postalarea_kh"],
                "place_name_en": fields["commune_postalarea_en"],
                "admin_name1": fields["provincial_postalarea_kh"],
                "admin_name1_en": fields["provincial_postalarea_en"],
                "admin_name2": fields["district_postalarea_kh"],
                "admin_name2_en": fields["district_postalarea_en"],
                "source_locator": f"page[{number}]/items[{item_number - 1}]",
                "source_url": url,
                **{f"source_{key}": value for key, value in fields.items()},
            })
    if len(rows) != total:
        raise ValueError("Cambodia postal source is incomplete")
    yield from rows


def _la(source: Mapping[str, Any], path: Path) -> Iterator[dict[str, str]]:
    pages = _pages(source, path)
    rows: list[dict[str, str]] = []
    total: int | None = None
    identifiers: set[int] = set()
    for number, (response, url) in enumerate(pages, 1):
        data = response.get("data")
        if response.get("success") is not True or not isinstance(data, dict):
            raise ValueError("unsuccessful Laos postal response")
        count = _integer(data.get("records"), "Laos item count", 1)
        if total is None:
            total = count
        if (_integer(data.get("currentPage"), "Laos page", 1) != number
                or _integer(data.get("pages"), "Laos pages", 1) != len(pages)
                or total != count
                or _integer(data.get("previousPage"), "Laos previous page") != number - 1
                or _integer(data.get("nextPage"), "Laos next page")
                != (number + 1 if number < len(pages) else 0)):
            raise ValueError("inconsistent Laos postal pagination")
        items = data.get("rows")
        if not isinstance(items, list) or not items:
            raise ValueError("empty Laos postal page")
        for item_number, item in enumerate(items, 1):
            if not isinstance(item, dict):
                raise ValueError("invalid Laos postal row")
            identifier = _integer(item.get("id"), "Laos row ID", 1)
            if identifier in identifiers:
                raise ValueError("duplicate Laos postal source row ID")
            identifiers.add(identifier)
            fields = {key: _text(item.get(key), key, empty=key == "remark")
                      for key in ("postcode", "province", "district", "village", "remark")}
            if not re.fullmatch(r"[0-9]{5}", fields["postcode"]):
                raise ValueError("Laos postal row requires a five-digit source code")
            if item.get("deletedAt") is not None:
                raise ValueError("Laos postal listing contains a deleted row")
            for key in ("createdAt", "updatedAt"):
                fields[key] = _text(item.get(key), key)
            rows.append({
                "country_code": "LA", "code": fields["postcode"],
                "place_name": fields["village"], "admin_name1": fields["province"],
                "admin_name2": fields["district"], "source_record_id": str(identifier),
                "source_locator": f"page[{number}]/data/rows[{item_number - 1}]/id[{identifier}]",
                "source_url": url,
                **{f"source_{key}": value for key, value in fields.items()},
            })
    if len(rows) != total:
        raise ValueError("Laos postal source is incomplete")
    yield from rows


class _Tables(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[list[str]]]] = []
        self.stack: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            table: list[list[list[str]]] = []
            self.tables.append(table)
            self.stack.append({"table": table, "row": None, "cell": None})
        elif self.stack:
            state = self.stack[-1]
            if tag == "tr":
                state["row"] = []
                state["table"].append(state["row"])
                state["cell"] = None
            elif tag in {"td", "th"} and state["row"] is not None:
                state["cell"] = []
                state["row"].append(state["cell"])
            elif tag in {"br", "p", "div"} and state["cell"] is not None:
                state["cell"].append("\n")

    def handle_endtag(self, tag: str) -> None:
        if not self.stack:
            return
        if tag == "table":
            self.stack.pop()
        elif tag in {"td", "th"}:
            self.stack[-1]["cell"] = None
        elif tag == "tr":
            self.stack[-1]["row"] = None
            self.stack[-1]["cell"] = None
        elif tag in {"p", "div"} and self.stack[-1]["cell"] is not None:
            self.stack[-1]["cell"].append("\n")

    def handle_data(self, data: str) -> None:
        if self.stack and self.stack[-1]["cell"] is not None:
            self.stack[-1]["cell"].append(data)


def _uz(source: Mapping[str, Any], path: Path) -> Iterator[dict[str, str]]:
    parser = _Tables()
    try:
        parser.feed(read_source_text(source, path, encoding="utf-8-sig"))
        parser.close()
    except (OSError, UnicodeError) as error:
        raise ValueError("cannot read Uzbekistan postal HTML") from error
    tables = [[[" ".join("".join(cell).split()) for cell in row] for row in table]
              for table in parser.tables]
    # The same law contains Russian and Uzbek lists. Only the Russian 14-region
    # annex is replayed; the routing patterns and second language are excluded.
    if len(tables) != 31 or len(tables[1]) != 16 or tables[1][0] != [
        "Наименование филиала", "Почтовый индекс"
    ]:
        raise ValueError("unexpected Uzbekistan postal annex structure")
    branches = tables[1][1:15]
    if any(len(row) != 2 or not row[0] or not re.fullmatch(r"[0-9ХX]{6}", row[1])
           for row in branches):
        raise ValueError("unexpected Uzbekistan postal branch list")
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    for table_index, table in enumerate(tables[2:16], 2):
        if (len(table) < 2 or len(table[0]) != 4
                or table[0][-2:] != ["Отделение почтовой связи", "Почтовый индекс"]):
            raise ValueError("unexpected Russian Uzbekistan postal table header")
        postal_node = ""
        node_locator = ""
        for row_index, row in enumerate(table[1:], 1):
            if len(row) not in {3, 4} or not re.fullmatch(r"[0-9]{6}", row[-1]):
                raise ValueError("unexpected Uzbekistan postal row")
            locator = f"table[{table_index}]/tr[{row_index}]"
            if len(row) == 4 and row[0]:
                postal_node, node_locator = row[0], locator
            if (not postal_node or not row[-2] or not re.fullmatch(r"[0-9]+", row[-3])
                    or row[-1] in seen):
                raise ValueError("invalid or duplicate Uzbekistan postal row")
            seen.add(row[-1])
            records.append({
                "country_code": "UZ", "code": row[-1], "place_name": row[-2],
                "admin_name1": "", "postal_branch": branches[table_index - 2][0],
                "postal_node": postal_node, "postal_node_locator": node_locator,
                "source_language": "ru", "source_locator": locator,
                "source_cells_json": json.dumps(row, ensure_ascii=False, separators=(",", ":")),
                **{f"source_col_{index}": value for index, value in enumerate(row, 1)},
            })
    yield from records


def iter_asia_records(source: Mapping[str, Any], path: Path) -> Iterator[dict[str, str]]:
    """Yield source strings and locators; callers verify the pinned outer bytes."""
    adapter = source.get("adapter")
    if (not isinstance(adapter, str) or adapter not in COUNTRIES
            or source.get("expected_country") != COUNTRIES[adapter]):
        raise ValueError("Asian postal adapter and expected_country must agree")
    readers = {"kh_mef_bundle": _kh, "la_postcode_api": _la, "uz_postal_html": _uz}
    yield from readers[adapter](source, Path(path))
