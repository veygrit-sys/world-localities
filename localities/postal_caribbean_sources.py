"""Replay fixed Caribbean/Atlantic postal publications, not address examples.

These narrow PDF adapters select labelled assignment tables or an explicit
single-code declaration. They preserve extracted source lines and page locators.
Stored bytes and expanded gzip hashes are checked by the shared input reader.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import io
from pathlib import Path
import re
from typing import Any

from .postal_source_io import read_source_bytes


_COUNTRIES = {
    "lc_gazette_postal_pdf": "LC",
    "ms_active_postcodes_pdf": "MS",
    "sh_upu_single_postcode_pdf": "SH",
}


def _pages(source: Mapping[str, Any], path: Path) -> list[list[str]]:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(read_source_bytes(source, path)), strict=True)
        if reader.is_encrypted or not 1 <= len(reader.pages) <= 32:
            raise ValueError("postal PDF requires 1..32 unencrypted pages")
        return [(page.extract_text() or "").splitlines() for page in reader.pages]
    except (OSError, PyPdfError, UnicodeError) as error:
        raise ValueError("cannot replay Caribbean postal PDF") from error


def _compact(text: str) -> str:
    return " ".join(text.split())


def _row(country: str, code: str, place: str, raw: str, page: int,
         line: int, postal_use: str) -> dict[str, str]:
    return {
        "country_code": country, "code": code, "place_name": place,
        "admin_name1": "", "postal_use": postal_use,
        "source_text_line": raw, "source_place": place,
        "source_locator": f"pdf:page={page}:line={line}",
    }


def _saint_lucia(pages: list[list[str]]) -> Iterator[dict[str, str]]:
    # The first table occupies printed Gazette pages 1501-1502 (PDF 13-14).
    # Other Gazette material and the subsequent address examples are not tables.
    if len(pages) != 20:
        raise ValueError("Saint Lucia Gazette requires its reviewed 20-page edition")
    first = "".join("".join(pages[12]).split()).upper()
    if ("SAINTLUCIAPOSTALSERVICE" not in first
            or "CUSTOMERNOTICE" not in first or "1501" not in first):
        raise ValueError("Saint Lucia Gazette postal notice header is missing")
    second = " ".join(_compact(line) for line in pages[13])
    if "Saint Lucia Government Gazette1502" not in second:
        raise ValueError("Saint Lucia Gazette continuation header is missing")
    count = 0
    ended = False
    for page_number in (13, 14):
        in_table = False
        headers = 0
        for line_number, raw in enumerate(pages[page_number - 1], 1):
            line = _compact(raw)
            if line == "DELIVERY POINT POSTCODE":
                headers += 1
                in_table = True
                continue
            if not in_table or not line:
                continue
            if page_number == 14 and re.match(r"2\.\s*The standard addressing format", line):
                ended = True
                break
            match = re.fullmatch(r"(?P<place>.+?)\s+(?P<code>LC[0-9]{2} [0-9]{3})", line)
            if match is None:
                raise ValueError(f"unrecognized Saint Lucia delivery-point row at page {page_number}, line {line_number}")
            place = match["place"]
            use = "private_letter_box" if "(private letter boxes)" in place.casefold() else "post_office"
            count += 1
            yield _row("LC", match["code"], place, raw, page_number, line_number, use)
        if headers != 2:
            raise ValueError("Saint Lucia postal table requires both column-group headers per page")
    if not ended or not count:
        raise ValueError("Saint Lucia postal table requires a complete end boundary and observations")


def _montserrat(pages: list[list[str]]) -> Iterator[dict[str, str]]:
    if len(pages) != 2 or not any("Montserrat Postal Service" in line for line in pages[0]):
        raise ValueError("Montserrat postal guide requires its reviewed two-page layout")
    starts = [i for i, line in enumerate(pages[0]) if _compact(line) == "Active Postcodes"]
    ends = [i for i, line in enumerate(pages[0]) if _compact(line) == "Interpreting Postcodes"]
    if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
        raise ValueError("Montserrat requires one complete Active Postcodes block")
    count = 0
    for i in range(starts[0] + 1, ends[0]):
        raw = pages[0][i]
        if not _compact(raw):
            continue
        match = re.fullmatch(r"(?P<place>.+?)\s+(?P<code>MSR[0-9]{4})", _compact(raw))
        if match is None:
            raise ValueError("unrecognized Montserrat active postcode row")
        count += 1
        yield _row("MS", match["code"], match["place"], raw, 1, i + 1,
                   "po_box_and_delivery_area")
    if not count:
        raise ValueError("Montserrat active-postcode block has no observations")


def _saint_helena(pages: list[list[str]]) -> Iterator[dict[str, str]]:
    if len(pages) != 2 or not any(_compact(line) == "Saint Helena" for line in pages[0]):
        raise ValueError("Saint Helena UPU publication requires its reviewed two-page layout")
    if not any(_compact(line) == "Single postcode for the whole territory" for line in pages[0]):
        raise ValueError("Saint Helena requires an explicit single-postcode declaration")
    # The declared postcode is printed again with a 'postcode' field label.
    # Do not treat the Royal Mail contact's PO1 1AF or spaced diagram as a record.
    candidates = [(i, raw, re.fullmatch(r"(STHL 1ZZ) postcode", _compact(raw)))
                  for i, raw in enumerate(pages[0], 1)]
    selected = [(i, raw, match) for i, raw, match in candidates if match is not None]
    if len(selected) != 1:
        raise ValueError("Saint Helena requires exactly one labelled assigned postcode")
    i, raw, match = selected[0]
    yield _row("SH", match[1], "Saint Helena", raw, 1, i, "single_code_island")


def iter_caribbean_records(source: Mapping[str, Any], path: Path) -> Iterator[dict[str, str]]:
    """Read only the named country-specific published layouts.

    LC covers the 2015 delivery-point publication, MS the 2014 active table,
    and SH St Helena island alone (not Ascension or Tristan da Cunha).
    Nationwide completeness and current validity are independent of extraction.
    """
    if not isinstance(source, Mapping) or source.get("format") != "official_postal_source":
        raise ValueError("unsupported Caribbean postal source format")
    adapter = source.get("adapter")
    if (not isinstance(adapter, str) or adapter not in _COUNTRIES
            or source.get("expected_country") != _COUNTRIES[adapter]):
        raise ValueError("Caribbean postal adapter and expected_country must agree")
    kind = source.get("default_code_kind")
    if not isinstance(kind, str) or kind not in {"official_full", "partial_or_legacy"}:
        raise ValueError("Caribbean postal source requires an explicit full/legacy kind")
    pages = _pages(source, Path(path))
    if adapter == "lc_gazette_postal_pdf":
        yield from _saint_lucia(pages)
    elif adapter == "ms_active_postcodes_pdf":
        yield from _montserrat(pages)
    else:
        yield from _saint_helena(pages)
