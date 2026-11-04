"""Source-preserving GeoNames transformations shared by regional registries."""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

RAW = (
    "geonameid name asciiname alternatenames latitude longitude feature_class "
    "feature_code country_code cc2 admin1_code admin2_code admin3_code admin4_code "
    "population elevation dem timezone modification_date"
).split()
DERIVED = (
    "id kind admin_level parent_id parent_relation parent_candidates_json "
    "state_id state_relation state_candidates_json address_candidate "
    "quality_flags_json"
).split()
FIELDS = DERIVED + RAW
CURRENT_PLACES = {
    "PPL",
    "PPLA",
    "PPLA2",
    "PPLA3",
    "PPLA4",
    "PPLA5",
    "PPLC",
    "PPLL",
    "PPLX",
    "PPLG",
}
SOURCE_URL = "https://download.geonames.org/export/dump/"
M49_URL = "https://unstats.un.org/unsd/methodology/m49/"


def jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def csv_bytes(rows: Iterable[dict[str, Any]], fields: list[str] = FIELDS) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def compressed(data: bytes) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(
        fileobj=output, mode="wb", filename="", mtime=0, compresslevel=9
    ) as archive:
        archive.write(data)
    return output.getvalue()


def read_csv(path: Path) -> Iterator[dict[str, str]]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", newline="") as source:
        yield from csv.DictReader(source)


def freshness_issues(
    country: str, adm1_count: int, registry_root: Path
) -> list[dict[str, Any]]:
    path = registry_root / "source_freshness.json"
    if not path.is_file():
        return []
    issue = json.loads(path.read_text(encoding="utf-8"))["countries"].get(country)
    if not issue:
        return []
    issue = dict(issue, geonames_adm1_count_in_this_snapshot=adm1_count)
    if adm1_count == issue["official_reference_adm1_count"]:
        issue["status"] = "count_matches_reference_hierarchy_not_verified"
    return [issue]


def source_rows(path: Path, country: str) -> Iterator[dict[str, str]]:
    """Read a named ZIP member without extracting archive paths."""
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo(country + ".txt")
        if info.file_size > 250_000_000:
            raise ValueError("unexpected country file size")
        with archive.open(info) as binary_source:
            for line in io.TextIOWrapper(binary_source, encoding="utf-8"):
                values = line.rstrip("\r\n").split("\t")
                if len(values) != 19:
                    raise ValueError("GeoNames schema changed")
                yield dict(zip(RAW, values))


def level(row: dict[str, str]) -> int | None:
    match = re.fullmatch(r"ADM([1-5])", row["feature_code"])
    return int(match[1]) if row["feature_class"] == "A" and match else None


def code_key(row: dict[str, str], level_number: int) -> tuple[str, ...] | None:
    codes = tuple(row[f"admin{index}_code"] for index in range(1, level_number + 1))
    if any(not code for code in codes) or (codes and codes[0] == "00"):
        return None
    return (row["country_code"],) + codes


def build_rows(raw_rows: Iterable[dict[str, str]], country: str) -> list[dict[str, Any]]:
    rows = sorted(raw_rows, key=lambda row: int(row["geonameid"]))
    indexes: dict[int, dict[tuple[str, ...], list[str]]] = {
        number: defaultdict(list) for number in range(1, 5)
    }
    seen: set[str] = set()
    for row in rows:
        if row["country_code"] != country or row["feature_class"] not in ("A", "P"):
            raise ValueError("unexpected row scope")
        if not re.fullmatch(r"[1-9][0-9]*", row["geonameid"]) or not row["name"]:
            raise ValueError("missing source identity or name")
        if row["geonameid"] in seen:
            raise ValueError("duplicate GeoNames identity")
        seen.add(row["geonameid"])
        if not (
            -90 <= float(row["latitude"]) <= 90
            and -180 <= float(row["longitude"]) <= 180
        ):
            raise ValueError("invalid source coordinate")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["modification_date"]):
            raise ValueError("invalid source modification date")
        admin_level = level(row)
        if admin_level and admin_level <= 4 and code_key(row, admin_level):
            indexes[admin_level][code_key(row, admin_level)].append(
                "gn:" + row["geonameid"]
            )

    def resolve(row: dict[str, str], number: int) -> tuple[str, str, list[str]]:
        key = code_key(row, number)
        if key is None:
            return "", "missing_code", []
        candidates = sorted(indexes[number].get(key, []))
        if len(candidates) == 1:
            return candidates[0], "source_admin_code", candidates
        return "", "ambiguous_code" if candidates else "missing_reference", candidates

    result: list[dict[str, Any]] = []
    for row in rows:
        admin_level = level(row)
        entity_id = "gn:" + row["geonameid"]
        flags = ["names_and_legal_status_not_independently_verified"]
        if row["cc2"]:
            flags.append("alternate_country_codes_retained")
        if admin_level == 1:
            parent_id, relation, candidates = "country:" + country, "source_country", []
        elif admin_level:
            parent_id, relation, candidates = resolve(row, admin_level - 1)
        elif row["feature_class"] == "P":
            populated = [
                index
                for index in range(1, 5)
                if row[f"admin{index}_code"]
                and not (index == 1 and row["admin1_code"] == "00")
            ]
            if populated:
                parent_id, relation, candidates = resolve(row, max(populated))
            else:
                parent_id, relation, candidates = (
                    "country:" + country,
                    "country_scope_only",
                    [],
                )
                flags.append("administrative_assignment_missing")
        else:
            parent_id, relation, candidates = "", "not_assigned_for_other_feature", []
        if relation in ("missing_code", "missing_reference", "ambiguous_code"):
            flags.append("parent_" + relation)
        if admin_level == 1:
            state_id, state_relation, state_candidates = (
                entity_id,
                "self_is_adm1",
                [entity_id],
            )
        elif admin_level or row["feature_class"] == "P":
            state_id, state_relation, state_candidates = resolve(row, 1)
        else:
            state_id, state_relation, state_candidates = "", "not_applicable", []
        if admin_level == 5:
            flags.append("admin5_code_not_in_standard_dump")
        kind = (
            "admin_subdivision"
            if admin_level
            else "locality"
            if row["feature_class"] == "P"
            else "other_admin_feature"
        )
        candidate = row["feature_class"] == "P" and row["feature_code"] in CURRENT_PLACES
        if row["feature_class"] == "P" and not candidate:
            flags.append("excluded_from_default_address_candidates")
        result.append(
            dict(
                id=entity_id,
                kind=kind,
                admin_level=str(admin_level or ""),
                parent_id=parent_id,
                parent_relation=relation,
                parent_candidates_json=jdump(candidates),
                state_id=state_id,
                state_relation=state_relation,
                state_candidates_json=jdump(state_candidates),
                address_candidate="1" if candidate else "0",
                quality_flags_json=jdump(sorted(flags)),
                **row,
            )
        )

    by_id = {row["id"]: row for row in result}
    for row in result:
        if not row["parent_id"] or row["parent_id"].startswith("country:"):
            continue
        parent = by_id[row["parent_id"]]
        if row["admin1_code"] != parent["admin1_code"]:
            raise ValueError("cross-state parent")
    return result


def write_country(
    rows: list[dict[str, Any]],
    country: str,
    output: Path,
    source_meta: dict[str, Any],
    country_meta: dict[str, Any],
    *,
    registry_root: Path | None = None,
    known_issues_factory: Callable[[str, Counter], list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    directory = output / "countries" / country
    directory.mkdir(parents=True, exist_ok=True)
    groups = {"entities.csv.gz": rows}
    files: dict[str, dict[str, Any]] = {}
    for filename, data_rows in groups.items():
        data = csv_bytes(data_rows)
        payload = compressed(data) if filename.endswith(".gz") else data
        (directory / filename).write_bytes(payload)
        files[filename] = {
            "rows": len(data_rows),
            "bytes": len(payload),
            "sha256": sha(payload),
            "uncompressed_sha256": sha(data),
        }
    preview = csv_bytes([row for row in rows if row["admin_level"] == "1"])
    (directory / "admin1.csv").write_bytes(preview)
    stats = dict(
        country=country,
        name_en=country_meta["name_en"],
        region=country_meta["region"],
        admin_rows=sum(row["kind"] == "admin_subdivision" for row in rows),
        locality_rows=sum(row["kind"] == "locality" for row in rows),
        other_admin_rows=sum(row["kind"] == "other_admin_feature" for row in rows),
        address_candidates=sum(row["address_candidate"] == "1" for row in rows),
        unresolved_parents=sum(
            row["parent_relation"] in ("missing_code", "missing_reference", "ambiguous_code")
            for row in rows
        ),
        ambiguous_parents=sum(row["parent_relation"] == "ambiguous_code" for row in rows),
        country_scope_only=sum(row["parent_relation"] == "country_scope_only" for row in rows),
        localities_without_adm1=sum(
            row["kind"] == "locality" and not row["state_id"] for row in rows
        ),
    )
    freshness_root = registry_root if registry_root is not None else output
    feature_counts = Counter(row["feature_code"] for row in rows)
    known_issues = (
        known_issues_factory(country, feature_counts)
        if known_issues_factory is not None
        else freshness_issues(
            country,
            sum(row["admin_level"] == "1" for row in rows),
            freshness_root,
        )
    )
    metadata = dict(
        schema_version=1,
        source="GeoNames",
        license="CC-BY-4.0",
        country=country_meta,
        source_file=source_meta,
        files=files,
        counts=stats,
        current_official_hierarchy_verified=False,
        known_issues=known_issues,
        preview_files={
            "admin1.csv": {
                "sha256": sha(preview),
                "rows": sum(row["admin_level"] == "1" for row in rows),
                "note": "Duplicate display projection; do not add to entity counts.",
            }
        },
        feature_counts=dict(sorted(feature_counts.items())),
        parent_relation_counts=dict(
            sorted(Counter(row["parent_relation"] for row in rows).items())
        ),
        completeness=(
            "all A/P records in this source country extract; "
            "official municipality completeness unverified"
        ),
        source_modified_min=min((row["modification_date"] for row in rows), default=None),
        source_modified_max=max((row["modification_date"] for row in rows), default=None),
    )
    write_json(directory / "metadata.json", metadata)
    return stats
