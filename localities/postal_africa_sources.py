"""Replay captured Mauritius government CSVs without repairing source values."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import csv
import io
from pathlib import Path
import re
from typing import Any

from .postal_source_io import read_source_text


_CSV4_HEADERS = {
    ("Locality", "Sub_locality", "Street", "Code"),
    ("locality", "sublocality", "street", "code"),
}
_CSV3_HEADERS = {
    ("Locality", "Sublocality", "PostCode"),
    ("Island", "Sublocalities/Office", "Code"),
}
_ENCODINGS = {"utf-8-sig", "cp1252"}
_CODE_PROFILE = re.compile(r"(?:[0-9]{5}|[RA][0-9]{4})")


def iter_africa_records(source: Mapping[str, Any], path: Path) -> Iterator[dict[str, str]]:
    """Read an already verified snapshot; retain spelling, code length and duplicates.

    The three-column mainland publication contains an unassigned/blank PostCode
    cell. It may be omitted from observations only when its exact logical record
    number is explicitly declared in skip_blank_code_rows. Every declaration must
    match an actual blank cell. All original rows remain in the captured snapshot.
    CSV locators count logical records, including the header and omitted rows.
    """
    format_name = source.get("adapter")
    if source.get("format") != "official_postal_source" or format_name not in {"mu_postal_csv4", "mu_postal_csv3"}:
        raise ValueError("unsupported Africa postal source format")
    if source.get("expected_country") != "MU":
        raise ValueError("Mauritius CSV requires expected_country MU")
    encoding = source.get("encoding")
    if encoding not in _ENCODINGS:
        raise ValueError("Mauritius CSV requires utf-8-sig or cp1252 encoding")
    declared_blanks = source.get("skip_blank_code_rows", [])
    if (not isinstance(declared_blanks, list)
            or any(type(number) is not int or number < 2 for number in declared_blanks)
            or len(declared_blanks) != len(set(declared_blanks))):
        raise ValueError("invalid Mauritius skip_blank_code_rows declaration")
    expected_blanks = set(declared_blanks)
    observed_blanks: set[int] = set()

    expected_headers = _CSV4_HEADERS if format_name == "mu_postal_csv4" else _CSV3_HEADERS
    try:
        with io.StringIO(read_source_text(source, path, encoding=encoding), newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, None)
            if header is None or tuple(header) not in expected_headers:
                raise ValueError("invalid Mauritius postal CSV header")
            for number, row in enumerate(reader, 2):
                if len(row) != len(header):
                    raise ValueError(f"invalid Mauritius postal CSV row width: {number}")
                locality, sublocality = row[:2]
                code = row[-1]
                if not code.strip():
                    if number in expected_blanks:
                        observed_blanks.add(number)
                        continue
                    raise ValueError(f"empty Mauritius postal code: {number}")
                if number in expected_blanks:
                    raise ValueError(f"declared Mauritius blank code row is not blank: {number}")
                if not locality.strip():
                    raise ValueError(f"empty Mauritius postal locality: {number}")
                street = row[2] if format_name == "mu_postal_csv4" else ""
                fields = {
                    "country_code": "MU", "code": code,
                    "place_name": locality, "admin_name1": "",
                    "source_locator": f"csv:record:{number}",
                    "source_locality": locality,
                    "source_sublocality": sublocality,
                    "source_street": street,
                    "postal_use": "source_reported_postcode",
                    **{f"source_col_{index}": value for index, value in enumerate(row, 1)},
                }
                if format_name == "mu_postal_csv4" and not _CODE_PROFILE.fullmatch(code):
                    fields.update(code_kind="source_anomaly", observation_status="unreviewed_code_shape")
                yield fields
            if observed_blanks != expected_blanks:
                raise ValueError("declared Mauritius blank code row was not found")
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError("cannot replay Mauritius postal CSV") from error
