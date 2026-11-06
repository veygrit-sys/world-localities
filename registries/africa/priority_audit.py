#!/usr/bin/env python3
"""Audit the two priority Africa waves using pinned local evidence only.

No network calls, inferred parent relationships, official-match claims or
postcode/deliverability certifications are made by this tool.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def audit(root=ROOT):
    config = load_json(root / "priority_sources.json")
    manifest = load_json(root / "manifest.json")
    migration = load_json(root / "migration.json")
    verification = load_json(root / "verification.json")
    with (root / "coverage.csv").open(encoding="utf-8", newline="") as stream:
        coverage_rows = list(csv.DictReader(stream))
    coverage = {row["country"]: row for row in coverage_rows}
    registered = {row["country"]: row for row in manifest["countries"]}
    reports = {row["country"]: row for row in verification["reports"]}
    missing = {
        Path(row["path"]).parts[-2]: row
        for row in migration["missing_source_files"]
        if row["path"].endswith("/entities.csv.gz")
    }
    errors = []
    if len(coverage) != len(coverage_rows):
        errors.append("duplicate country in coverage.csv")
    if len(registered) != len(manifest["countries"]):
        errors.append("duplicate country in manifest.json")
    if set(coverage) != set(registered) or set(reports) != set(registered):
        errors.append("coverage/manifest/verification have different country sets")
    if len(registered) != manifest["scope_count"]:
        errors.append("manifest scope_count differs from country entries")
    if sum(int(r["rows"]) for r in reports.values()) != verification["rows"]:
        errors.append("verification row total mismatch")
    if verification["rows"] != migration["records"]:
        errors.append("migration and verification source totals disagree")

    waves = []
    seen = set()
    for wave in config["waves"]:
        countries = []
        for code in wave["countries"]:
            if code in seen:
                errors.append("duplicate priority country " + code)
            seen.add(code)
            info = config["countries"].get(code)
            if not info or not info.get("sources"):
                errors.append("priority country has no source leads: " + code)
            source_leads = info.get("sources", []) if info else []
            for source in source_leads:
                if source.get("status") != "discovered_not_ingested" or source.get("reuse_rights") != "not_yet_cleared":
                    errors.append("source status requires a dedicated evidence review: " + code)
            result = dict(
                country=code,
                name=info.get("name", "") if info else "",
                official_reference_count=len(source_leads),
                official_hierarchy_verified=False,
                postal_address_validated=False,
                deliverability_validated=False,
            )
            if code not in registered:
                prior = missing.get(code)
                result["status"] = "not_migrated_from_pinned_source" if prior else "source_not_registered"
                if prior:
                    result["source_blob_sha"] = prior["sha"]
                    result["source_blob_bytes"] = prior["size"]
                else:
                    errors.append("missing provenance for " + code)
                countries.append(result)
                continue

            result["status"] = "source_snapshot_present"
            meta_path = root / "countries" / code / "metadata.json"
            if not meta_path.exists():
                errors.append(code + ": country metadata missing")
                countries.append(result)
                continue
            recorded = registered[code]["metadata_sha256"]
            if file_sha256(meta_path) != recorded:
                errors.append(code + ": metadata SHA256 mismatch")
            meta = load_json(meta_path)
            if meta.get("country", {}).get("country") != code:
                errors.append(code + ": metadata country mismatch")
            if meta.get("current_official_hierarchy_verified") is not False:
                errors.append(code + ": official hierarchy claim needs independent review")
            raw_stats = meta["counts"]
            for key in ("address_candidates", "admin_rows", "ambiguous_parents",
                        "country_scope_only", "localities_without_adm1",
                        "locality_rows", "other_admin_rows", "unresolved_parents"):
                if int(coverage[code][key]) != raw_stats[key]:
                    errors.append(code + ": coverage count mismatch: " + key)
            total = raw_stats["admin_rows"] + raw_stats["locality_rows"] + raw_stats["other_admin_rows"]
            if reports[code]["rows"] != total:
                errors.append(code + ": verification row count mismatch")
            for filename, recorded_details in meta.get("files", {}).items():
                target = root / "countries" / code / filename
                if not target.is_file():
                    errors.append(code + ": missing " + filename)
                elif file_sha256(target) != recorded_details["sha256"]:
                    errors.append(code + ": " + filename + " SHA256 mismatch")
            result.update(
                source_rows=total,
                address_candidates=raw_stats["address_candidates"],
                unresolved_parents=raw_stats["unresolved_parents"],
                localities_without_adm1=raw_stats["localities_without_adm1"],
                source_retrieved_on=meta["source_file"]["retrieved_on"],
                source_name=meta["source"],
            )
            countries.append(result)
        waves.append({"wave": wave["wave"], "gate": wave["gate"], "countries": countries})
    if set(config["countries"]) != seen:
        errors.append("country source records and priority waves do not match")

    return {
        "as_of": config["reviewed_on"],
        "source_integrity_checked": True,
        "official_sources_ingested_by_this_change": 0,
        "postcode_or_delivery_claim": False,
        "waves": waves,
        "integrity_errors": sorted(set(errors)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wave", type=int, choices=(1, 2), help="Only display one wave")
    parser.add_argument("--check", action="store_true", help="Exit nonzero on integrity errors")
    args = parser.parse_args()
    report = audit()
    if args.wave:
        report["waves"] = [w for w in report["waves"] if w["wave"] == args.wave]
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.check and report["integrity_errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
