#!/usr/bin/env python3
"""Build a source-preserving Central America gazetteer. Stdlib only."""

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from localities import geonames as core
from localities.materialize import ensure_file, materialize_country

RAW = core.RAW
FIELDS = core.FIELDS
SOURCE_URL = core.SOURCE_URL
M49_URL = core.M49_URL
jdump = core.jdump
sha = core.sha
write_json = core.write_json
csv_bytes = core.csv_bytes
compressed = core.compressed
build_rows = core.build_rows
code_key = core.code_key


def read_csv(path):
    ensure_file(path, ROOT)
    yield from core.read_csv(path)


def freshness_issues(country, feature_counts):
    path = ROOT / "source_freshness.json"
    if not path.is_file():
        return []
    issue = json.loads(path.read_text(encoding="utf-8"))["countries"].get(country)
    if not issue:
        return []
    issue = dict(issue)
    issue["source_feature_counts"] = {
        code: feature_counts.get(code, 0)
        for code in issue["official_reference_counts"]
    }
    issue["status"] = (
        "count_matches_reference_hierarchy_not_verified"
        if issue["source_feature_counts"] == issue["official_reference_counts"]
        else "known_source_reference_count_mismatch"
    )
    return [issue]


def source_rows(path, country):
    ensure_file(path, ROOT)
    yield from core.source_rows(path, country)


def write_country(rows, country, output, source_meta, country_meta):
    return core.write_country(
        rows,
        country,
        output,
        source_meta,
        country_meta,
        registry_root=ROOT,
        known_issues_factory=freshness_issues,
    )


def scope(inputs):
    # UN M49 013 checked 2026-10-01. Mexico is kept in the declared region,
    # but belongs to the separate official-registry/MX snapshot.
    wanted = {
        "BZ": ("Belize", "084"),
        "SV": ("El Salvador", "222"),
        "GT": ("Guatemala", "320"),
        "HN": ("Honduras", "340"),
        "NI": ("Nicaragua", "558"),
        "PA": ("Panama", "591"),
    }
    selected = []
    for line in (inputs / "countryInfo.txt").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        row = line.split("\t")
        if row[0] not in wanted:
            continue
        name, m49 = wanted[row[0]]
        assert row[2] == m49
        selected.append(
            dict(
                country=row[0],
                alpha3=row[1],
                numeric=row[2],
                geonames_country_name=row[4],
                geonames_continent=row[8],
                geonames_id=row[16],
                reported_languages=row[15].split(","),
                name_en=name,
                m49=m49,
                region="Central America",
                id="country:" + row[0],
                status="source_country_or_area",
            )
        )
    if len(selected) != 6:
        raise ValueError("Central America countryInfo scope mismatch")
    source = [
        [country["name_en"], country["m49"], country["alpha3"]]
        for country in sorted(selected, key=lambda country: country["name_en"])
    ]
    source.insert(0, ["Central America", "013", ""])
    source.append(["Mexico", "484", "MEX"])
    source.append(["Costa Rica", "188", "CRI"])
    return sorted(selected, key=lambda country: country["country"]), source


def build(inputs, output, retrieved_on, only=None):
    selected, source = scope(inputs)
    output.mkdir(parents=True, exist_ok=True)
    write_json(
        output / "scope.json",
        dict(
            schema_version=1,
            source_url=M49_URL,
            retrieved_on=retrieved_on,
            source_rows=source,
            countries=selected,
            region_m49="013",
            full_m49_members=["BZ", "CR", "SV", "GT", "HN", "MX", "NI", "PA"],
            coverage_status="partial_6_of_8_m49_members",
            excluded_from_this_layer=[
                {
                    "country": "CR",
                    "reason": "Pending approval; no source or derived country records included",
                },
                {
                    "country": "MX",
                    "reason": "Separate source layers; not included in this six-country batch",
                    "path": "../official-registry/MX",
                },
            ],
        ),
    )
    selected = [country for country in selected if not only or country["country"] in only]
    result = []
    for country_meta in selected:
        country = country_meta["country"]
        path = inputs / (country + ".zip")
        raw = list(source_rows(path, country))
        rows = build_rows(
            [row for row in raw if row["feature_class"] in ("A", "P")], country
        )
        source_meta = dict(
            url=SOURCE_URL + country + ".zip",
            retrieved_on=retrieved_on,
            sha256=sha(path.read_bytes()),
            bytes=path.stat().st_size,
            source_rows=len(raw),
            retained_rows=len(rows),
            discarded_feature_classes=dict(
                Counter(
                    row["feature_class"]
                    for row in raw
                    if row["feature_class"] not in ("A", "P")
                )
            ),
        )
        stats = write_country(rows, country, output, source_meta, country_meta)
        result.append(stats)
        print(
            country,
            stats["admin_rows"],
            stats["locality_rows"],
            stats["unresolved_parents"],
            flush=True,
        )
    return result


def summarize(output):
    scope_data = json.loads((output / "scope.json").read_text(encoding="utf-8"))
    metadata = [
        json.loads(
            (output / "countries" / country["country"] / "metadata.json").read_text(
                encoding="utf-8"
            )
        )
        for country in scope_data["countries"]
    ]
    counts = [entry["counts"] for entry in metadata]
    (output / "coverage.csv").write_bytes(csv_bytes(counts, list(counts[0])))
    totals = {
        key: sum(count[key] for count in counts)
        for key in counts[0]
        if isinstance(counts[0][key], int)
    }
    write_json(
        output / "manifest.json",
        dict(
            schema_version=1,
            scope_count=len(counts),
            totals=totals,
            countries=[
                dict(
                    country=entry["country"]["country"],
                    metadata_sha256=sha(
                        (
                            output
                            / "countries"
                            / entry["country"]["country"]
                            / "metadata.json"
                        ).read_bytes()
                    ),
                )
                for entry in metadata
            ],
            license="CC-BY-4.0",
            source=SOURCE_URL,
            scope_source=M49_URL,
            scope_sha256=sha((output / "scope.json").read_bytes()),
            coverage_sha256=sha((output / "coverage.csv").read_bytes()),
        ),
    )
    return totals


def verify(output):
    scope_data = json.loads((output / "scope.json").read_text(encoding="utf-8"))
    seen, checks, reports = set(), 0, []
    for country_meta in scope_data["countries"]:
        country = country_meta["country"]
        materialize_country(output, country)
        directory = output / "countries" / country
        metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
        rows = []
        for filename, info in metadata["files"].items():
            payload = (directory / filename).read_bytes()
            assert sha(payload) == info["sha256"], (country, filename, "checksum")
            data = gzip.decompress(payload) if filename.endswith(".gz") else payload
            assert sha(data) == info["uncompressed_sha256"]
            part = list(read_csv(directory / filename))
            assert len(part) == info["rows"]
            rows.extend(part)
            checks += 3
        rows.sort(key=lambda row: int(row["geonameid"]))
        by_id = {row["id"]: row for row in rows}
        assert len(by_id) == len(rows)
        assert not seen.intersection(by_id), ("duplicate ID across countries", country)
        seen.update(by_id)
        for row in rows:
            assert row["country_code"] == country
            parent_id = row["parent_id"]
            assert not parent_id or parent_id == "country:" + country or parent_id in by_id
            if parent_id in by_id:
                parent = by_id[parent_id]
                assert parent["kind"] == "admin_subdivision"
                if row["admin_level"]:
                    assert int(parent["admin_level"]) == int(row["admin_level"]) - 1
                assert code_key(row, int(parent["admin_level"])) == code_key(
                    parent, int(parent["admin_level"])
                )
            visited = {row["id"]}
            node = parent_id
            while node in by_id:
                assert node not in visited, ("cycle", country, node)
                visited.add(node)
                node = by_id[node]["parent_id"]
            assert not row["state_id"] or (
                row["state_id"] in by_id
                and by_id[row["state_id"]]["admin_level"] == "1"
            )
            for field in ("parent_candidates_json", "state_candidates_json"):
                assert all(entity in by_id for entity in json.loads(row[field]))
        replay = build_rows([{key: row[key] for key in RAW} for row in rows], country)
        assert replay == rows, (country, "offline replay mismatch")
        preview = (directory / "admin1.csv").read_bytes()
        assert sha(preview) == metadata["preview_files"]["admin1.csv"]["sha256"]
        assert preview == csv_bytes([row for row in rows if row["admin_level"] == "1"])
        assert len(rows) == metadata["source_file"]["retained_rows"]
        checks += 10
        reports.append(
            dict(country=country, rows=len(rows), replay="exact", integrity="passed")
        )
    report = dict(
        schema_version=1,
        countries=len(reports),
        rows=len(seen),
        file_and_country_checks=checks,
        errors=0,
        reports=reports,
        limits=[
            "Integrity checks do not certify current legal administrative boundaries.",
            "Unresolved source references are retained and counted, not repaired by name matching.",
        ],
    )
    write_json(output / "verification.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["build", "summarize", "verify"])
    parser.add_argument("--inputs", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT)
    parser.add_argument("--retrieved-on", default="2026-10-01")
    parser.add_argument("--countries", nargs="+")
    args = parser.parse_args()
    if args.command == "build":
        if args.inputs is None:
            parser.error("--inputs is required")
        build(args.inputs, args.output, args.retrieved_on, args.countries)
    elif args.command == "summarize":
        print(jdump(summarize(args.output)))
    else:
        report = verify(args.output)
        print(jdump({key: value for key, value in report.items() if key not in ("reports", "limits")}))


if __name__ == "__main__":
    main()
