#!/usr/bin/env python3
"""Source-aware Americas audit and bounded area-by-area quality improvement queue.

All four UN M49 subregions are indexed without duplicating or silently
converting source-specific locality rows into official/postal addresses.
Run after each upstream data change; --mode cycle stops if the inputs do not
change instead of pretending to enrich data by repeating a read.
"""
import argparse
import importlib.util
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AREAS = (
    ("northern-america", "021", "Northern America"),
    ("central-america", "013", "Central America"),
    ("caribbean", "029", "Caribbean"),
    ("south-america", "005", "South America"),
)


class AuditError(ValueError):
    pass


def require(test, message):
    if not test:
        raise AuditError(message)


def load_json(root, relative):
    return json.loads((root / relative).read_text(encoding="utf-8"))


def read_coverage(root, directory, manifest):
    path = root / directory / "coverage.csv"
    content = path.read_bytes()
    claimed_hash = manifest.get("coverage_sha256")
    if claimed_hash:
        require(hashlib.sha256(content).hexdigest() == claimed_hash,
                f"{directory}: coverage file hash mismatch")
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = {}
    for row in rows:
        country = row["country"]
        require(country not in result and len(country) == 2,
                f"{directory}: duplicate/bad country in coverage")
        count = int(row["locality_rows"])
        require(count >= 0, f"{country}: negative locality rows")
        result[country] = {
            "source_locality_rows": count,
            "source_address_candidates": int(row["address_candidates"]),
            "unresolved_parents": int(row["unresolved_parents"])
        }
        require(0 <= result[country]["source_address_candidates"] <= count,
                f"{country}: invalid address candidate count")
    return result


def official_snapshot(root, country, excluded_regions=()):
    index = load_json(root, f"official-registry/{country}/index.json")
    manifest = load_json(root, f"official-registry/{country}/manifest.json")
    require(index["country"] == manifest["country"] == country, f"{country}: wrong official index")
    require(all(value is False for value in manifest["claims"].values()),
            f"{country}: official completeness claims unexpectedly changed")
    regions = index["regions"]
    require(len({x["code"] for x in regions}) == len(regions), f"{country}: repeated region")
    declared = int(index["counts"]["source_localities"])
    require(sum(int(x["localities"]) for x in regions) == declared,
            f"{country}: index region totals disagree")
    actual_codes = {r["code"] for r in regions}
    require(set(excluded_regions).issubset(actual_codes), f"{country}: missing exclusion")
    excluded = sum(int(x["localities"]) for x in regions if x["code"] in excluded_regions)
    return {
        "country": country, "status": "published_source_layer",
        "layer": f"official-registry/{country}",
        "source_locality_rows": declared,
        "in_m49_area_locality_rows": declared - excluded,
        "excluded_source_locality_rows": excluded,
        "excluded_source_regions": list(excluded_regions),
        "source_vintage": index["vintage"],
        "quality": "official_source_roles_not_postal_or_street_verified"
    }


def regional_source(country, directory, coverage):
    info = coverage[country]
    return {
        "country": country, "status": "published_source_layer",
        "layer": directory, "source_locality_rows": info["source_locality_rows"],
        "in_m49_area_locality_rows": info["source_locality_rows"],
        "excluded_source_locality_rows": 0,
        "unresolved_parents": info["unresolved_parents"],
        "quality": "geonames_source_gazetteer_not_official_postal_coverage"
    }


def pending(country):
    return {
        "country": country, "status": "pending_source", "layer": None,
        "source_locality_rows": None, "in_m49_area_locality_rows": None,
        "quality": "unavailable_not_a_zero_locality_claim"
    }


def verify_administrative_seeds(root):
    data = load_json(root, "north-america-registry/admin-seeds.json")
    require(data["schema_version"] == 1, "unsupported administrative seed version")
    sources, records = data["source_evidence"], data["records"]
    seen, counts = set(), {"BM": 0, "GL": 0, "PM": 0}
    for row in records:
        cc, identity = row["country"], row["provisional_id"]
        require(cc in counts and identity.startswith(f"seed:{cc}:"),
                "invalid Northern seed country or provisional ID")
        require(identity not in seen, f"duplicate seed {identity}")
        seen.add(identity)
        require(row["kind"] in ("parish", "municipality", "commune"),
                "unsupported administrative unit type")
        require(row["source_name"] and row["status"] == "source_attested_administrative_name",
                "administrative seed is not source-attested")
        require(row["evidence_id"] in sources and sources[row["evidence_id"]]["url"].startswith("https://"),
                "missing administrative seed evidence")
        require(not row["can_validate_postal_or_street"],
                "administrative seed cannot be used for postal/street verification")
        if cc == "PM":
            require(row["kind"] == "commune" and row["official_code"] in ("97501", "97502")
                    and row["authority_code_scheme"] == "FR-INSEE-COG-COM",
                    "PM INSEE code mismatch")
        else:
            require(row["official_code"] is None and row["authority_code_scheme"] is None,
                    "unverified BM/GL official code")
        counts[cc] += 1
    require(counts == {"BM": 11, "GL": 5, "PM": 2},
            "Northern administration seed inventory unexpectedly changed")
    return counts


def _northern(root):
    scope = load_json(root, "north-america-registry/scope.json")
    require(scope["region_m49"] == "021", "Northern M49 mismatch")
    countries = scope["countries"]
    require(len(countries) == 5, "Northern M49 must have five areas")
    roster = {c["country"] for c in countries}
    require(roster == {"BM", "CA", "GL", "PM", "US"}, "Northern roster mismatch")
    require(len({c["m49"] for c in countries}) == 5, "Northern M49 country code duplicate")
    sources = {}
    for entry in countries:
        cc = entry["country"]
        if entry["status"] == "preserved_official_snapshot":
            exclusions = entry.get("excluded_state_codes_for_m49", [])
            sources[cc] = official_snapshot(root, cc, exclusions)
        elif entry["status"] == "pending_locality_source":
            sources[cc] = pending(cc)
        else:
            raise AuditError(f"{cc}: unsupported Northern status")
    require(sources["US"]["excluded_source_regions"] == ["US-PR"],
            "US Puerto Rico must be accounted for in Caribbean, not Northern America")
    for cc, count in verify_administrative_seeds(root).items():
        sources[cc]["administrative_name_seed_rows"] = count
    corrections = load_json(root, "north-america-registry/name-overrides.json")
    require(any(x["state_code"] == "CA-NS" and x["snapshot_name"] == "New Scotia"
                and x["display_name_en"] == "Nova Scotia" and x["evidence_url"]
                for x in corrections["entries"]), "Canada's Nova Scotia presentation fix is missing")
    return sources, [
        "CA-NS: Nova Scotia verified display correction; source snapshots remain immutable",
        "BM/GL/PM: 18 government-attested administrative names recorded separately, not a locality source"
    ]


def _central(root):
    scope = load_json(root, "central-america-registry/scope.json")
    manifest = load_json(root, "central-america-registry/manifest.json")
    roster = set(scope["full_m49_members"])
    published = {c["country"] for c in scope["countries"]}
    require(scope["region_m49"] == "013" and len(roster) == 8,
            "Central America M49 roster mismatch")
    require(published == {x["country"] for x in manifest["countries"]},
            "Central America manifest/scope mismatch")
    coverage = read_coverage(root, "central-america-registry", manifest)
    require(set(coverage) == published, "Central America coverage country mismatch")
    require(sum(x["source_locality_rows"] for x in coverage.values()) ==
            manifest["totals"]["locality_rows"], "Central America source total mismatch")
    require("MX" in roster and "MX" not in published and "CR" in roster,
            "Expected separate MX / additive CR scope has changed")
    sources = {cc: regional_source(cc, "central-america-registry", coverage)
               for cc in published}
    sources["MX"] = official_snapshot(root, "MX")
    # The preserved six-country publication remains unchanged. CR is additive.
    module_path = Path(__file__).resolve().parents[1] / "central-america-registry/supplement.py"
    spec = importlib.util.spec_from_file_location("central_cr_snapshot", module_path)
    supplement = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(supplement)
    cr = supplement.verify(root)
    sources["CR"] = {
        "country": "CR", "status": "published_source_layer",
        "layer": "central-america-registry/enrichment/countries/CR",
        "source_locality_rows": cr["locality_rows"],
        "in_m49_area_locality_rows": cr["locality_rows"],
        "excluded_source_locality_rows": 0,
        "unresolved_parents": cr["unresolved_parents"],
        "quality": "geonames_source_gazetteer_raw_replayed_not_official_postal_coverage"
    }
    for cc in roster - set(sources):
        sources[cc] = pending(cc)
    return sources, [
        "MX: separate INEGI official snapshot; not part of 6-country GeoNames package",
        "CR: additive source gazetteer with raw replay; original six-country snapshot is unchanged",
        "CR: source ADM2 count is 82; separate government CodeSystem has 84 entries and is not a verified GeoNames crosswalk"
    ]


def _caribbean(root):
    scope = load_json(root, "caribbean-registry/scope.json")
    manifest = load_json(root, "caribbean-registry/manifest.json")
    published = {c["country"] for c in scope["countries"]}
    omitted = {c["country"] for c in scope["omitted_countries"]}
    roster = published | omitted
    require(scope["region_m49"] == "029" and len(roster) == 28,
            "Caribbean M49 roster mismatch")
    require(omitted == {"CU"} and published.isdisjoint(omitted),
            "Caribbean pending country scope changed")
    require(published == {x["country"] for x in manifest["countries"]},
            "Caribbean manifest/scope mismatch")
    coverage = read_coverage(root, "caribbean-registry", manifest)
    require(set(coverage) == published, "Caribbean coverage country mismatch")
    require(sum(x["source_locality_rows"] for x in coverage.values()) ==
            manifest["totals"]["locality_rows"], "Caribbean source total mismatch")
    sources = {cc: regional_source(cc, "caribbean-registry", coverage)
               for cc in published}
    sources["CU"] = pending("CU")
    return sources, ["PR: Caribbean GeoNames scope; do not add the overlapping US Census US-PR source rows"]


def _south(root):
    scope = load_json(root, "south-america-registry/scope.json")
    manifest = load_json(root, "south-america-registry/manifest.json")
    roster = {c["country"] for c in scope["countries"]}
    published = {x["country"] for x in manifest["countries"]}
    require(scope["scope_m49"] == manifest["scope_m49"] == "005"
            and len(roster) == 16 and roster == published, "South America scope mismatch")
    coverage = read_coverage(root, "south-america-registry", manifest)
    require(set(coverage) == published, "South America coverage mismatch")
    require(sum(x["source_locality_rows"] for x in coverage.values()) ==
            sum(x["locality_rows"] for x in manifest["counts"]["reports"]),
            "South America source totals mismatch")
    sources = {cc: regional_source(cc, "south-america-registry", coverage)
               for cc in published}
    return sources, ["BR: separate IBGE official layer exists; not added to GeoNames count"]


BUILDERS = {
    "northern-america": _northern,
    "central-america": _central,
    "caribbean": _caribbean,
    "south-america": _south,
}


def audit(root=ROOT):
    areas, unique_countries = [], set()
    for key, m49, title in AREAS:
        sources, notes = BUILDERS[key](root)
        countries = set(sources)
        require(unique_countries.isdisjoint(countries),
                f"{key}: country appears in multiple M49 regions")
        unique_countries.update(countries)
        loaded = sorted(cc for cc, row in sources.items()
                        if row["status"] == "published_source_layer")
        missing = sorted(countries - set(loaded))
        region_rows = sum(sources[cc]["in_m49_area_locality_rows"] for cc in loaded)
        areas.append({
            "key": key, "region": title, "m49": m49,
            "m49_country_area_count": len(countries),
            "source_country_area_count": len(loaded),
            "pending_country_area_codes": missing,
            "source_locality_rows_in_m49_area": region_rows,
            "countries": [sources[cc] for cc in sorted(countries)],
            "quality_notes": notes
        })
    require(len(unique_countries) == 57, "Americas M49 roster must be 57 country/areas")
    return {
        "status": "source_catalogue_consistent",
        "scope_m49": "019",
        "geographic_note": "M49 North America (003) includes Northern America (021), Central America (013), and Caribbean (029). South America (005) is separate.",
        "source_country_area_count": sum(a["source_country_area_count"] for a in areas),
        "m49_country_area_count": len(unique_countries),
        "areas": areas,
        "postal_street_delivery_verified": False,
        "official_municipality_completeness_verified": False,
        "cross_source_deduplication_verified": False
    }


def quality_queue(report):
    queue = []
    for area in report["areas"]:
        for cc in area["pending_country_area_codes"]:
            queue.append({
                "area": area["key"], "country": cc, "priority": 1,
                "task": "Acquire and legally verify a country-specific locality source; pin license, vintage, IDs and hashes; do not synthesize missing localities."
            })
        if area["key"] == "northern-america":
            queue.append({
                "area": area["key"], "country": "CA", "priority": 2,
                "task": "Audit province names including Nova Scotia, bilingual name evidence, and Indigenous/statistical CSD distinctions without altering preserved source files."
            })
            queue.append({
                "area": area["key"], "country": "US", "priority": 2,
                "task": "Review address candidate roles, Puerto Rico cross-region routing, and USPS-vs-Census postal limitations."
            })
        unresolved = sum(x.get("unresolved_parents", 0) for x in area["countries"])
        if unresolved:
            queue.append({
                "area": area["key"], "priority": 2,
                "task": f"Investigate {unresolved} reported unresolved GeoNames parent links; keep them unverified until cross-checked."
            })
        queue.append({
            "area": area["key"], "priority": 3,
            "task": "Source verified multilingual names and postal crosswalks; do not infer Address1, road numbers or deliverability."
        })
    return queue


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("audit", "plan", "cycle"), default="audit")
    parser.add_argument("--rounds", type=int, default=2,
                        help="Maximum bounded audit passes for --mode cycle")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    if args.rounds < 1 or args.rounds > 20:
        parser.error("--rounds must be 1..20")
    try:
        report = audit(args.root.resolve())
        if args.mode == "audit":
            result = report
        elif args.mode == "plan":
            result = {"summary": {
                "source_country_area_count": report["source_country_area_count"],
                "m49_country_area_count": report["m49_country_area_count"]
            }, "quality_queue": quality_queue(report)}
        else:
            # A no-change cycle is successful but must not pretend to enrich data.
            snapshots, reason = [report], "max_rounds"
            for _ in range(1, args.rounds):
                candidate = audit(args.root.resolve())
                if candidate == snapshots[-1]:
                    reason = "no_upstream_change"
                    break
                snapshots.append(candidate)
            result = {"passes_completed": len(snapshots), "stopped_because": reason,
                      "latest": snapshots[-1], "quality_queue": quality_queue(snapshots[-1])}
    except (AuditError, ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        parser.exit(2, f"error: {exc}\n")
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
