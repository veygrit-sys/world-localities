"""Read the explicit ward-code column in TCRA's fixed regional PDF tables."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from typing import Iterator, Mapping

from .postal_source_io import read_source_bytes


class _Spans(list):
    verified_space_spans: set[int]

    def __init__(self):
        super().__init__()
        self.verified_space_spans = set()


def _spans(page) -> list[tuple[str, float, float, int]]:
    # Kigoma's pages carry /Rotate=90. Transform a parsed page in memory only;
    # the saved PDF byte image is never changed.
    if page.rotation:
        page.transfer_rotation_to_content()
    spans = _Spans()
    font_spaces = {}

    def visit(text, cm, tm, _font, _size):
        if text.strip():
            x = tm[4] * cm[0] + tm[5] * cm[2] + cm[4]
            y = tm[4] * cm[1] + tm[5] * cm[3] + cm[5]
            spans.append((text, x, y, len(spans) + 1))
            if "\x03" in text:
                font_key = id(_font)
                if font_key not in font_spaces:
                    cmap = _font.get("/ToUnicode") if _font is not None else None
                    data = cmap.get_object().get_data() if cmap is not None else b""
                    font_spaces[font_key] = bool(re.search(rb"<0003>\s*<00a0>", data, re.I))
                if font_spaces[font_key]:
                    spans.verified_space_spans.add(len(spans))

    page.extract_text(visitor_text=visit)
    return spans


def _columns(spans: list[tuple[str, float, float, int]]) -> tuple[float, float, float]:
    headers = [(text.strip(), x) for text, x, _y, _number in spans
               if text.strip() in {"WARD", "POSTCODE", "MTAA/VILLAGE"}]
    wards = [x for text, x in headers if text == "WARD"]
    if len(wards) != 1:
        raise ValueError("TCRA PDF requires one explicit WARD header on the first page")
    ward_x = wards[0]
    codes = sorted(x for text, x in headers if text == "POSTCODE" and x > ward_x)
    if not codes:
        raise ValueError("TCRA PDF lacks the ward POSTCODE column")
    code_x = codes[0]
    following = [x for _text, x in headers if x > code_x]
    if not following:
        raise ValueError("TCRA PDF lacks a boundary after the ward POSTCODE column")
    end_x = min(following)
    if not ward_x < code_x - 20 or not 30 <= end_x - code_x <= 100:
        raise ValueError("TCRA PDF has an unreviewed ward/postcode column layout")
    return ward_x, code_x, end_x


def _label(spans, left: float, right: float, y: float, *, display: bool = False) -> str:
    parts = sorted((x, number, text.strip()) for text, x, sy, number in spans
                   if left - 3 <= x < right - 3 and abs(sy - y) <= 2)
    if display:
        mapped = getattr(spans, "verified_space_spans", set())
        return " ".join(" ".join((text.replace("\x03", "\xa0") if number in mapped else text).split())
                        for _x, number, text in parts).strip()
    return " ".join(text for _x, _number, text in parts)


def iter_tanzania_records(source: Mapping, path: Path) -> Iterator[dict[str, str]]:
    """Yield literal ward assignments; retain malformed values as anomalies.

    The column is selected from the published header, not by finding every
    number in a PDF. Region/district prefixes, old values, and the Kigoma title's
    full-length regional number remain in the original but are not ward rows.
    Ward labels are the same-baseline source cell text; no administrative
    hierarchy is inferred from merged or blank cells.
    """
    if (source.get("format") != "official_postal_source"
            or source.get("adapter") != "tz_tcra_ward_pdf"
            or source.get("expected_country") != "TZ"):
        raise ValueError("unsupported Tanzania postal adapter/country")
    region = source.get("region_name", "")
    if not isinstance(region, str):
        raise ValueError("TCRA region_name must be a string")
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(read_source_bytes(source, path)))
    if not reader.pages or len(reader.pages) > 150:
        raise ValueError("TCRA regional PDF has an unreviewed page count")
    first = _spans(reader.pages[0])
    ward_x, code_x, end_x = _columns(first)
    seen = set()
    for page_number, page in enumerate(reader.pages, 1):
        spans = first if page_number == 1 else _spans(page)
        for text, x, y, span_number in spans:
            # The OLD header is centred; some old values start six points left
            # of it. A reviewed 12-point inset excludes that adjacent column.
            if not code_x - 12 <= x < end_x - 12:
                continue
            code = text.strip()
            if not re.fullmatch(r"[0-9]+", code):
                continue
            name = _label(spans, ward_x, code_x, y)
            if not name or name in {"WARD", "POSTCODE"}:
                raise ValueError("TCRA ward code lacks a source ward label")
            if code in seen:
                raise ValueError("duplicate ward code in a TCRA regional PDF")
            seen.add(code)
            display_name = _label(spans, ward_x, code_x, y, display=True)
            fragments = name
            # Independently checked against the printed cell in the fixed
            # Katavi PDF: this one ward name wraps inside its merged cell.
            # Keep both raw fragments and refuse a changed layout/value.
            if region == "Katavi" and code == "50111":
                continuation = _label(spans, ward_x, code_x, y - 13.11)
                if page_number != 2 or display_name != "Uwanja wa" or continuation != "ndege":
                    raise ValueError("reviewed Katavi ward label wrap has changed")
                fragments += "\n" + continuation
                display_name += " " + _label(spans, ward_x, code_x, y - 13.11, display=True)
            raw_row = " ".join(t.strip() for _rx, _n, t in sorted(
                (sx, n, t) for t, sx, sy, n in spans if abs(sy - y) <= 2))
            record = {
                "country_code": "TZ", "code": code, "place_name": display_name,
                "admin_name1": region, "source_ward_label_line": name,
                "source_ward_label_fragments": fragments,
                "source_row_text": raw_row, "postal_use": "ward_directory",
                "source_locator": f"pdf:page:{page_number}/text_span:{span_number}",
            }
            if not re.fullmatch(r"[0-9]{5}", code):
                record["code_kind"] = "source_anomaly"
            yield record
    if not seen:
        raise ValueError("TCRA regional PDF yielded no ward assignments")
