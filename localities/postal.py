"""Pinned postal-code observations, never generated assignments or delivery proof."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterator, Mapping
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_MEMBER_BYTES = 1024 * 1024 * 1024
MAX_ZIP_MEMBERS = 1024
FORMATS = {
    "geonames_tsv_zip", "japanpost_utf_zip", "japanpost_business_zip",
    "taiwan_prefix_csv", "official_postal_source",
}
OFFICIAL_SOURCE_COUNTRIES = {
    "na_nampost_html": "NA",
    "xk_postakosoves_entries": "XK",
    "ba_postal_pdf": "BA",
    "kh_mef_bundle": "KH",
    "la_postcode_api": "LA",
    "uz_postal_html": "UZ",
    "mu_postal_csv4": "MU",
    "mu_postal_csv3": "MU",
    "me_postacg_offices": "ME",
    "lc_gazette_postal_pdf": "LC",
    "ms_active_postcodes_pdf": "MS",
    "sh_upu_single_postcode_pdf": "SH",
    "sz_eswatinipost_html": "SZ",
    "sn_laposte_postal_js": "SN",
    "bt_postcode_regions": "BT",
    "tz_tcra_ward_pdf": "TZ",
}
CODE_KINDS = {
    "source_reported", "source_full", "official_full", "prefix", "aggregated",
    "partial", "partial_or_legacy", "routing_or_unreviewed", "source_anomaly",
}
STANDARD_CODE_KINDS = {"source_reported", "source_full", "official_full"}
# These checks identify complete-length source strings. They neither certify an
# assigned/current postcode nor establish that a source covers an entire country.
FULL_CODE_PATTERNS = {
    "CA": re.compile(r"[A-Z][0-9][A-Z] [0-9][A-Z][0-9]"),
    "GB": re.compile(r"[A-Z0-9]{2,4} [0-9][A-Z]{2}"),
    "NL": re.compile(r"[0-9]{4} [A-Z]{2}"),
}


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _relative_path(root: Path, supplied: object) -> Path:
    if not _nonempty(supplied):
        raise ValueError("source path must be a nonempty repository-relative path")
    path = PurePosixPath(supplied)
    if path.is_absolute() or ".." in path.parts or "\\" in supplied:
        raise ValueError("unsafe source path")
    resolved_root = Path(root).resolve()
    resolved = resolved_root.joinpath(*path.parts).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise ValueError("source path escapes repository root")
    return resolved


def _validate_source(source: object, root: Path) -> None:
    if not isinstance(source, Mapping):
        raise ValueError("postal source must be an object")
    if not _nonempty(source.get("id")):
        raise ValueError("postal source requires a nonempty id")
    if not isinstance(source.get("format"), str) or source["format"] not in FORMATS:
        raise ValueError("unsupported postal source format")
    _relative_path(root, source.get("path"))
    sha = source.get("sha256")
    if not isinstance(sha, str) or not re.fullmatch("[0-9a-fA-F]{64}", sha):
        raise ValueError("postal source requires SHA-256")
    size = source.get("bytes")
    if type(size) is not int or not 0 <= size <= MAX_ARCHIVE_BYTES:
        raise ValueError("invalid or excessive postal source bytes")
    if "expected_record_count" in source and (
        type(source["expected_record_count"]) is not int or source["expected_record_count"] < 0
    ):
        raise ValueError("expected_record_count must be a nonnegative integer")
    if not _nonempty(source.get("licence")):
        raise ValueError("postal source requires its licence declaration")
    if (not isinstance(source.get("default_code_kind"), str)
            or source["default_code_kind"] not in CODE_KINDS):
        raise ValueError("unsupported default postal code kind")
    overrides = source.get("country_code_kinds", {})
    if not isinstance(overrides, Mapping) or not all(
        isinstance(country, str) and re.fullmatch("[A-Z]{2}", country)
        and isinstance(kind, str) and kind in CODE_KINDS
        for country, kind in overrides.items()
    ):
        raise ValueError("invalid country-specific postal code kinds")
    if "active_for_lookup" in source and type(source["active_for_lookup"]) is not bool:
        raise ValueError("active_for_lookup must be boolean")
    expected = source.get("expected_country")
    if "expected_country" in source and (
        not isinstance(expected, str) or not re.fullmatch("[A-Z]{2}", expected)
    ):
        raise ValueError("expected_country must be an uppercase two-letter code")
    if "source_full" in overrides.values():
        raise ValueError("source_full cannot be introduced by a country override")
    if source["default_code_kind"] == "source_full":
        if source["format"] != "geonames_tsv_zip" or expected not in FULL_CODE_PATTERNS:
            raise ValueError("source_full requires a supported GeoNames full-code country")
        if overrides:
            raise ValueError("source_full does not allow country-specific overrides")
    if source["format"] == "official_postal_source":
        adapter = source.get("adapter")
        if (not isinstance(adapter, str) or adapter not in OFFICIAL_SOURCE_COUNTRIES
                or expected != OFFICIAL_SOURCE_COUNTRIES[adapter]):
            raise ValueError("official postal adapter and expected_country must agree")
        if (source["default_code_kind"] not in {"official_full", "partial_or_legacy"}
                or overrides):
            raise ValueError("official postal sources require explicit full/legacy kind without overrides")
        if (not isinstance(source.get("compression", "none"), str)
                or source.get("compression", "none") not in {"none", "gzip"}):
            raise ValueError("unsupported official postal snapshot compression")
    if "member" in source:
        member = source["member"]
        if not _nonempty(member):
            raise ValueError("source ZIP member must be nonempty")
        path = PurePosixPath(member)
        if path.is_absolute() or ".." in path.parts or "\\" in member:
            raise ValueError("unsafe source ZIP member")


def load_sources(root: Path = ROOT) -> dict[str, Any]:
    """Load source declarations; each iterator also checks its stored bytes."""
    root = Path(root)
    try:
        payload = json.loads((root / "postal/sources.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("cannot read postal sources manifest") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("unsupported postal sources schema")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError("postal sources must be a list")
    identifiers: set[str] = set()
    for source in sources:
        _validate_source(source, root)
        if source["id"] in identifiers:
            raise ValueError("duplicate postal source id")
        identifiers.add(source["id"])
    return payload


def _countries(root: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads((Path(root) / "countries/catalog.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("cannot read country collection catalog") from error
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("unsupported country collection catalog")
    countries = payload.get("countries")
    if not isinstance(countries, list):
        raise ValueError("country collection catalog requires countries")
    seen: set[str] = set()
    for item in countries:
        if (not isinstance(item, dict) or not isinstance(item.get("code"), str)
                or not re.fullmatch("[A-Z]{2}", item["code"])
                or not _nonempty(item.get("name")) or item["code"] in seen):
            raise ValueError("invalid or duplicate country collection code")
        seen.add(item["code"])
    return countries


def _verify_source_bytes(source: Mapping[str, Any], root: Path) -> Path:
    _validate_source(source, root)
    path = _relative_path(root, source["path"])
    try:
        size = path.stat().st_size
        if not path.is_file() or size != source["bytes"] or size > MAX_ARCHIVE_BYTES:
            raise ValueError(f"source size mismatch: {source['id']}")
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise ValueError(f"cannot read postal source: {source['id']}") from error
    if digest.hexdigest() != source["sha256"].lower():
        raise ValueError(f"source SHA-256 mismatch: {source['id']}")
    return path


def _zip_member(source: Mapping[str, Any], archive: zipfile.ZipFile) -> zipfile.ZipInfo:
    members = archive.infolist()
    if len(members) > MAX_ZIP_MEMBERS:
        raise ValueError("excessive number of postal ZIP members")
    requested = source.get("member")
    if requested is not None:
        candidates = [item for item in members if item.filename == requested]
    else:
        suffix = ".txt" if source["format"] == "geonames_tsv_zip" else ".csv"
        candidates = [item for item in members if not item.is_dir() and item.filename.lower().endswith(suffix)]
    if len(candidates) != 1:
        raise ValueError("postal ZIP requires exactly one selected data member")
    member = candidates[0]
    path = PurePosixPath(member.filename)
    if (member.is_dir() or path.is_absolute() or ".." in path.parts
            or "\\" in member.filename or member.flag_bits & 1):
        raise ValueError("unsafe or encrypted postal ZIP member")
    if member.file_size > MAX_MEMBER_BYTES:
        raise ValueError("postal ZIP member exceeds uncompressed size limit")
    return member


def _record(source: Mapping[str, Any], row_number: int, country: str, code: str,
            fields: Mapping[str, str], allowed_countries: set[str]) -> dict[str, str]:
    if country not in allowed_countries:
        raise ValueError(f"source country is outside collection catalog: {source['id']} row {row_number}")
    if not _nonempty(code):
        raise ValueError(f"empty postal code: {source['id']} row {row_number}")
    expected = source.get("expected_country")
    if expected is not None and country != expected:
        raise ValueError(f"postal source country differs from expected_country: {source['id']} row {row_number}")
    kind = source.get("country_code_kinds", {}).get(country, source["default_code_kind"])
    if "code_kind" in fields:
        if fields["code_kind"] == "source_anomaly":
            kind = "source_anomaly"
        elif fields["code_kind"] != kind:
            raise ValueError("a postal adapter may only demote a source code to source_anomaly")
    if kind == "source_full" and not FULL_CODE_PATTERNS[expected].fullmatch(code):
        raise ValueError(f"incomplete or malformed source_full postcode: {source['id']} row {row_number}")
    result = dict.fromkeys((
        "source_id", "source_row", "country_code", "code", "code_kind", "place_name",
        "admin_name1", "admin_code1", "admin_name2", "admin_code2", "admin_name3",
        "admin_code3", "latitude", "longitude", "accuracy", "entity_id",
    ), "")
    result.update(fields)
    result.update(source_id=source["id"], source_row=str(row_number),
                  country_code=country, code=code, code_kind=kind)
    return result


def iter_postal_records(source: Mapping[str, Any], root: Path = ROOT) -> Iterator[dict[str, str]]:
    """Replay one verified source, preserving rows and many-to-many observations."""
    root = Path(root)
    path = _verify_source_bytes(source, root)
    allowed_countries = {item["code"] for item in _countries(root)}
    overrides = source.get("country_code_kinds", {})
    if not set(overrides).issubset(allowed_countries):
        raise ValueError("source code-kind override is outside country collection catalog")
    if source.get("expected_country") is not None and source["expected_country"] not in allowed_countries:
        raise ValueError("expected_country is outside country collection catalog")
    try:
        if source["format"] == "official_postal_source":
            adapter = source["adapter"]
            if adapter in {"na_nampost_html", "xk_postakosoves_entries", "ba_postal_pdf"}:
                from .postal_official import iter_official_records as read_records
            elif adapter in {"kh_mef_bundle", "la_postcode_api", "uz_postal_html"}:
                from .postal_asia_sources import iter_asia_records as read_records
            elif adapter in {"mu_postal_csv4", "mu_postal_csv3"}:
                from .postal_africa_sources import iter_africa_records as read_records
            elif adapter in {"lc_gazette_postal_pdf", "ms_active_postcodes_pdf", "sh_upu_single_postcode_pdf"}:
                from .postal_caribbean_sources import iter_caribbean_records as read_records
            elif adapter in {"sz_eswatinipost_html", "sn_laposte_postal_js"}:
                from .postal_more_africa_sources import iter_more_africa_records as read_records
            elif adapter == "bt_postcode_regions":
                from .postal_cv_bt_sources import iter_cv_bt_records as read_records
            elif adapter == "tz_tcra_ward_pdf":
                from .postal_tanzania_sources import iter_tanzania_records as read_records
            else:
                from .postal_europe_sources import iter_europe_records as read_records
            for number, fields in enumerate(read_records(source, path), 1):
                if (not isinstance(fields, Mapping)
                        or not all(isinstance(k, str) and isinstance(v, str) for k, v in fields.items())
                        or not _nonempty(fields.get("source_locator"))):
                    raise ValueError("official postal records require string fields and a source locator")
                yield _record(source, number, fields.get("country_code", ""),
                              fields.get("code", ""), fields, allowed_countries)
            return
        if source["format"] == "taiwan_prefix_csv":
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                headers = reader.fieldnames
                if (not headers or len(headers) != len(set(headers))
                        or not {"country", "code", "entity_id"}.issubset(headers)):
                    raise ValueError("invalid Taiwan prefix CSV header")
                for number, row in enumerate(reader, 1):
                    if None in row or any(value is None for value in row.values()):
                        raise ValueError(f"invalid Taiwan prefix CSV row width: {number}")
                    if row["country"] != "TW":
                        raise ValueError(f"unexpected Taiwan prefix CSV country: {number}")
                    yield _record(source, number, row["country"], row["code"],
                                  {"entity_id": row["entity_id"]}, allowed_countries)
            return
        with zipfile.ZipFile(path) as archive:
            member = _zip_member(source, archive)
            with archive.open(member) as binary:
                encoding = "cp932" if source["format"] == "japanpost_business_zip" else "utf-8-sig"
                with io.TextIOWrapper(binary, encoding=encoding, newline="") as stream:
                    if source["format"] == "geonames_tsv_zip":
                        reader = csv.reader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
                        for number, row in enumerate(reader, 1):
                            if len(row) != 12:
                                raise ValueError(f"GeoNames postal row must have 12 columns: {number}")
                            fields = dict(zip((
                                "place_name", "admin_name1", "admin_code1", "admin_name2",
                                "admin_code2", "admin_name3", "admin_code3", "latitude",
                                "longitude", "accuracy",
                            ), row[2:]))
                            yield _record(source, number, row[0], row[1], fields, allowed_countries)
                    elif source["format"] == "japanpost_business_zip":
                        reader = csv.reader(stream)
                        for number, row in enumerate(reader, 1):
                            if len(row) != 13:
                                raise ValueError(f"Japan Post business row must have 13 columns: {number}")
                            if not re.fullmatch(r"[0-9]{7}", row[7]):
                                raise ValueError(f"Japan Post business row requires a 7-digit postcode: {number}")
                            uses = {"0": "business", "1": "po_box"}
                            if row[10] not in uses:
                                raise ValueError(f"unknown Japan Post business postal use: {number}")
                            fields = {
                                "place_name": row[5], "admin_name1": row[3],
                                "admin_name2": row[4], "admin_code2": row[0],
                                "organization": row[2], "postal_office": row[9],
                                "postal_use": uses[row[10]],
                                **{f"source_col_{i}": value for i, value in enumerate(row, 1)},
                            }
                            yield _record(source, number, "JP", row[7], fields, allowed_countries)
                    else:
                        reader = csv.reader(stream)
                        for number, row in enumerate(reader, 1):
                            if len(row) != 15:
                                raise ValueError(f"Japan Post postal row must have 15 columns: {number}")
                            fields = {
                                "place_name": row[8], "admin_name1": row[6],
                                "admin_name2": row[7], "admin_code2": row[0],
                                **{f"source_col_{i}": value for i, value in enumerate(row, 1)},
                            }
                            yield _record(source, number, "JP", row[2], fields, allowed_countries)
    except (OSError, UnicodeError, csv.Error, zipfile.BadZipFile, RuntimeError) as error:
        raise ValueError(f"cannot replay postal source: {source['id']}") from error


def build_postal_catalog(root: Path = ROOT) -> dict[str, Any]:
    """Count stored observations for every managed country, without upgrading claims."""
    root = Path(root)
    manifest = load_sources(root)
    countries = _countries(root)
    codes = {item["code"]: set() for item in countries}
    counts = {item["code"]: Counter() for item in countries}
    kinds = {item["code"]: Counter() for item in countries}
    codes_by_kind = {item["code"]: defaultdict(set) for item in countries}
    lookup_rows: Counter[str] = Counter()
    reports = []
    for source in manifest["sources"]:
        source_counts: Counter[str] = Counter()
        kind_counts: Counter[str] = Counter()
        source_codes: set[tuple[str, str]] = set()
        source_codes_by_kind: dict[str, set[tuple[str, str]]] = defaultdict(set)
        active = source.get("active_for_lookup", True)
        for record in iter_postal_records(source, root):
            country = record["country_code"]
            code, kind = record["code"], record["code_kind"]
            codes[country].add(code)
            codes_by_kind[country][kind].add(code)
            counts[country][source["id"]] += 1
            kinds[country][kind] += 1
            source_counts[country] += 1
            kind_counts[kind] += 1
            pair = (country, code)
            source_codes.add(pair)
            source_codes_by_kind[kind].add(pair)
            if active:
                lookup_rows[country] += 1
        if ("expected_record_count" in source
                and sum(source_counts.values()) != source["expected_record_count"]):
            raise ValueError(f"postal source record count differs from the reviewed count: {source['id']}")
        reports.append({
            "id": source["id"], "format": source["format"], "path": source["path"],
            "sha256": source["sha256"], "bytes": source["bytes"],
            "licence": source["licence"],
            "status": "verified_source_bytes_and_records",
            "active_for_lookup": active,
            "source_rows": sum(source_counts.values()),
            "distinct_codes": len(source_codes),
            "distinct_codes_by_kind": {
                kind: len(values) for kind, values in sorted(source_codes_by_kind.items())
            },
            "countries": dict(sorted(source_counts.items())),
            "code_kinds": dict(sorted(kind_counts.items())),
            **({"adapter": source["adapter"]} if "adapter" in source else {}),
            **({"coverage_scope": source["coverage_scope"]} if "coverage_scope" in source else {}),
        })
    output = []
    for item in countries:
        country = item["code"]
        row_count = sum(counts[country].values())
        output.append({
            "country_code": country, "name": item["name"],
            "postal_system_status": "unreviewed",
            "collection_status": "stored_source_observations" if row_count else "pending_source",
            "source_rows": row_count, "distinct_codes": len(codes[country]),
            "lookup_source_rows": lookup_rows[country],
            "code_kinds": dict(sorted(kinds[country].items())),
            "distinct_codes_by_kind": {
                kind: len(values) for kind, values in sorted(codes_by_kind[country].items())
            },
            "source_counts": dict(sorted(counts[country].items())),
            "national_completeness_verified": False,
        })
    source_countries = sum(bool(item["source_rows"]) for item in output)
    return {
        "schema_version": 1, "snapshot_label": manifest.get("snapshot_label"),
        "countries": output,
        "summary": {
            "total_countries": len(output), "source_countries": source_countries,
            "countries_pending": len(output) - source_countries,
            "source_rows": sum(item["source_rows"] for item in output),
            "lookup_source_rows": sum(lookup_rows.values()),
            "country_code_pairs": sum(item["distinct_codes"] for item in output),
        },
        "sources": reports,
    }


def lookup_postcode(country: str, code: str, root: Path = ROOT, limit: int = 20,
                    offset: int = 0, include_partial: bool = False,
                    include_historical: bool = False) -> dict[str, Any]:
    """Match literal observed code values; partial inclusion does not expand prefixes."""
    root = Path(root)
    if not isinstance(country, str) or country not in {item["code"] for item in _countries(root)}:
        raise ValueError("unknown country collection code")
    if not _nonempty(code):
        raise ValueError("postcode must be a nonempty string")
    if type(limit) is not int or not 1 <= limit <= 10_000:
        raise ValueError("limit must be an integer between 1 and 10000")
    if type(offset) is not int or offset < 0:
        raise ValueError("offset must be a nonnegative integer")
    if type(include_partial) is not bool:
        raise ValueError("include_partial must be boolean")
    if type(include_historical) is not bool:
        raise ValueError("include_historical must be boolean")
    total = 0
    selected = []
    for source in load_sources(root)["sources"]:
        if not include_historical and not source.get("active_for_lookup", True):
            continue
        if source.get("expected_country") is not None and source["expected_country"] != country:
            continue
        for record in iter_postal_records(source, root):
            if record["country_code"] != country or record["code"] != code:
                continue
            if not include_partial and record["code_kind"] not in STANDARD_CODE_KINDS:
                continue
            if offset <= total < offset + limit:
                selected.append(record)
            total += 1
    return {
        "country_code": country, "code": code, "include_partial": include_partial,
        "include_historical": include_historical,
        "total": total, "rows": selected, "limit": limit, "offset": offset,
        "has_more": total > offset + len(selected),
        "complete_postcode_verified": False, "deliverability_verified": False,
    }


def verify_postal_catalog(root: Path = ROOT) -> dict[str, Any]:
    """Replay all stored sources and compare the complete saved catalog."""
    root = Path(root)
    try:
        saved = json.loads((root / "postal/catalog.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("cannot read stored postal catalog") from error
    computed = build_postal_catalog(root)
    if saved != computed:
        raise ValueError("stored postal catalog differs from source replay")
    return {
        "status": "passed", "countries": len(computed["countries"]),
        "source_rows": computed["summary"]["source_rows"],
        "country_code_pairs": computed["summary"]["country_code_pairs"],
    }
