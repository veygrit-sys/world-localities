"""Replay Bhutan Post's published regional directory responses as fixed data.

The empty form publishes twenty named regions. These are finite directory filters,
not generated postal-code queries. Duplicate source observations remain separate.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re

from .postal_source_io import read_source_text


BHUTAN_URL = "https://bhutanpost.bt/postcode/searchpostcode-exec.php"
BHUTAN_REGIONS = (
    "Bumthang", "Chukha", "Dagana", "Gasa", "Haa", "Lhuntse", "Mongar",
    "Paro", "Pemagatshel", "Punakha", "Samdrupjongkhar", "Samtse", "Sarpang",
    "Thimphu", "Trashigang", "Trashiyangtse", "Trongsa", "Tsirang",
    "Wangdue Phodrang", "Zhemgang",
)
BHUTAN_HEADERS = ("Dzongkhag", "Gewog", "Post Office", "Postal Code")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field in Bhutan postal bundle")
        result[key] = value
    return result


class _DirectoryTables(HTMLParser):
    """The original directory omits several opening tr tags; recover only those."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[tuple[int, tuple[str, ...]]]] = []
        self.table: list[tuple[int, tuple[str, ...]]] | None = None
        self.cells: list[str] = []
        self.cell: list[str] | None = None
        self.row_line = 0

    def _end_row(self) -> None:
        if self.cell is not None:
            raise ValueError("unclosed Bhutan postal table cell")
        if self.cells:
            assert self.table is not None
            self.table.append((self.row_line, tuple(self.cells)))
            self.cells = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            if self.table is not None:
                raise ValueError("nested Bhutan postal table")
            self.table = []
        elif tag == "tr" and self.table is not None:
            self._end_row()
            self.row_line = self.getpos()[0]
        elif tag in {"td", "th"} and self.table is not None:
            if self.cell is not None:
                raise ValueError("nested Bhutan postal table cell")
            if not self.cells:
                self.row_line = self.getpos()[0]
            self.cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.table is not None:
            if self.cell is None:
                raise ValueError("unexpected Bhutan postal table cell end")
            self.cells.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.table is not None:
            self._end_row()
        elif tag == "table" and self.table is not None:
            self._end_row()
            self.tables.append(self.table)
            self.table = None

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)


def _bhutan_regions(source: Mapping[str, object], path: Path) -> Iterator[dict[str, str]]:
    try:
        bundle = json.loads(read_source_text(source, path), object_pairs_hook=_unique_object)
    except json.JSONDecodeError as error:
        raise ValueError("invalid Bhutan postal response bundle") from error
    if (not isinstance(bundle, dict) or bundle.get("schema_version") != 1
            or bundle.get("published_region_options") != list(BHUTAN_REGIONS)
            or not isinstance(bundle.get("responses"), list)
            or len(bundle["responses"]) != len(BHUTAN_REGIONS)):
        raise ValueError("Bhutan bundle requires all twenty published region filters")
    for response_number, (region, response) in enumerate(
        zip(BHUTAN_REGIONS, bundle["responses"]), 1
    ):
        if (not isinstance(response, dict) or response.get("url") != BHUTAN_URL
                or response.get("method") != "POST"
                or response.get("form") != {"dzongkhag": region, "submit": "Search"}
                or not isinstance(response.get("raw_utf8"), str)
                or type(response.get("bytes")) is not int
                or not isinstance(response.get("sha256"), str)):
            raise ValueError("invalid Bhutan postal response receipt")
        raw = response["raw_utf8"].encode("utf-8")
        if (len(raw) != response["bytes"]
                or hashlib.sha256(raw).hexdigest() != response["sha256"]):
            raise ValueError("Bhutan postal response differs from original bytes")
        parser = _DirectoryTables()
        parser.feed(response["raw_utf8"])
        parser.close()
        if parser.table is not None or parser.cell is not None:
            raise ValueError("incomplete Bhutan postal table")
        candidates = [
            (table_number, rows)
            for table_number, rows in enumerate(parser.tables, 1)
            if rows and rows[0][1] == BHUTAN_HEADERS
        ]
        if len(candidates) != 1 or len(candidates[0][1]) < 2:
            raise ValueError("Bhutan region requires one nonempty postal-code table")
        table_number, rows = candidates[0]
        for row_number, (line, cells) in enumerate(rows[1:], 1):
            if (len(cells) != 4 or any(not value for value in cells)
                    or cells[0] != region or not re.fullmatch(r"[0-9]{5}", cells[3])):
                raise ValueError("invalid or cross-region Bhutan postal row")
            yield {
                "country_code": "BT", "code": cells[3], "place_name": cells[2],
                "admin_name1": cells[0], "admin_name2": cells[1],
                "source_dzongkhag": cells[0], "source_gewog": cells[1],
                "source_post_office": cells[2], "postal_use": "post_office",
                "source_locator": (
                    f"response:{response_number}/form:dzongkhag:{region}/"
                    f"table:{table_number}/row:{row_number}/html_line:{line}"
                ),
            }


def iter_cv_bt_records(source: Mapping[str, object], path: Path) -> Iterator[dict[str, str]]:
    if source.get("adapter") != "bt_postcode_regions":
        raise ValueError("unsupported CV/BT official postal source adapter")
    yield from _bhutan_regions(source, path)
