"""Replay Eswatini and Senegal public postal publications without script execution."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import json
from pathlib import Path
import re

from .postal_official import _Tables
from .postal_source_io import read_source_text


_ADAPTER_COUNTRIES = {"sz_eswatinipost_html": "SZ", "sn_laposte_postal_js": "SN"}
_ESWATINI_REGIONS = (
    ("HHOHHO REGION", "H"), ("MANZINI REGION", "M"),
    ("SHISELWENI REGION", "S"), ("LUBOMBO REGION", "L"),
)


def _eswatini(source: Mapping, path: Path) -> Iterator[dict[str, str]]:
    parser = _Tables()
    parser.feed(read_source_text(source, path))
    parser.close()
    if (parser.table is not None or parser.row is not None or parser.cell is not None
            or len(parser.tables) != len(_ESWATINI_REGIONS)):
        raise ValueError("Eswatini postal publication requires four complete region tables")
    for table_number, (table, (region, letter)) in enumerate(
        zip(parser.tables, _ESWATINI_REGIONS), 1
    ):
        if not table:
            raise ValueError("empty Eswatini postal region table")
        header = table[0]["cells"]
        if (len(header) != 2 or any(cell["tag"] != "th" for cell in header)
                or [cell["text"] for cell in header] != [region, "CODE"]):
            raise ValueError("unrecognized Eswatini postal region header")
        if len(table) < 2:
            raise ValueError("Eswatini region table has no observations")
        for row_number, row in enumerate(table[1:], 2):
            cells = row["cells"]
            if (len(cells) != 2 or any(cell["tag"] != "td" for cell in cells)
                    or any(cell["colspan"] != "1" for cell in cells)
                    or not cells[0]["text"]
                    or not re.fullmatch(letter + r"[0-9]{3}", cells[1]["text"])):
                raise ValueError("invalid Eswatini postal assignment row")
            yield {
                "country_code": "SZ", "code": cells[1]["text"],
                "place_name": cells[0]["text"], "admin_name1": region,
                "source_locator": f"table:{table_number}/row:{row_number}/html_line:{row['line']}",
                "postal_use": "post_office_code",
                "source_col_1": cells[0]["text"], "source_col_2": cells[1]["text"],
            }


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate Senegal postal JSON field")
        result[key] = value
    return result


def _senegal(source: Mapping, path: Path) -> Iterator[dict[str, str]]:
    # The public site's external JS is a comment and one JSON-valued constant.
    # Parse only this data declaration, never JavaScript or function expressions.
    text = read_source_text(source, path)
    declaration = re.match(
        r"\A\s*(?://[^\r\n]*(?:\r\n|\n)\s*)*const\s+PE_ALL_POSTAL_CODES\s*=\s*", text
    )
    if declaration is None:
        raise ValueError("Senegal postal source requires its named data declaration")
    decoder = json.JSONDecoder(object_pairs_hook=_unique_object)
    try:
        records, end = decoder.raw_decode(text[declaration.end():])
    except json.JSONDecodeError as error:
        raise ValueError("invalid Senegal postal JSON array") from error
    if text[declaration.end() + end:].strip() != ";":
        raise ValueError("unexpected code after Senegal postal data declaration")
    if not isinstance(records, list) or not records or len(records) > 50000:
        raise ValueError("invalid Senegal postal data collection")
    for number, record in enumerate(records, 1):
        if (not isinstance(record, dict) or set(record) != {"name", "code"}
                or not all(isinstance(value, str) and value.strip() for value in record.values())
                or not re.fullmatch(r"[0-9]+", record["code"])):
            raise ValueError("invalid Senegal postal data record")
        fields = {
            "country_code": "SN", "code": record["code"],
            "place_name": record["name"], "admin_name1": "",
            "source_locator": f"json:PE_ALL_POSTAL_CODES/item:{number}",
            "postal_use": "source_reported_postcode",
            "source_name": record["name"], "source_code": record["code"],
        }
        if not re.fullmatch(r"[0-9]{5}", record["code"]):
            fields.update(code_kind="source_anomaly", observation_status="unreviewed_code_shape")
        yield fields


def iter_more_africa_records(source: Mapping, path: Path) -> Iterator[dict[str, str]]:
    """Retain source labels, duplicate assignments, literal codes and source locators."""
    adapter = source.get("adapter")
    if source.get("format") != "official_postal_source" or adapter not in _ADAPTER_COUNTRIES:
        raise ValueError("unsupported additional Africa postal source format")
    if source.get("expected_country") != _ADAPTER_COUNTRIES[adapter]:
        raise ValueError("additional Africa adapter and country must agree")
    try:
        yield from (_eswatini(source, path) if adapter == "sz_eswatinipost_html"
                    else _senegal(source, path))
    except (OSError, UnicodeError) as error:
        raise ValueError("cannot replay additional Africa postal publication") from error
