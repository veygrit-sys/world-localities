#!/usr/bin/env python3
"""Restore the pinned 2026-09-26 Nigeria original from an authenticated local git clone.

No remote GitHub credentials are accepted by this script. The old repository
and its recorded source commit must already be available as a local git clone.
Dry-run is default. --apply is explicit and changes only the current checkout.
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AFRICA = Path(__file__).resolve().parent
REPO_ROOT = AFRICA.parents[1]
ORIGINAL_PREFIX = "address-foundation/africa-registry/countries/NG/"
FILES = ("entities.csv.gz", "admin1.csv", "metadata.json")
EXPECTED_NG_ROWS = 65444
EXPECTED_RESTORED_ROWS = 453482


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git_blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def pinned_git_file(repo, source_commit, path):
    result = subprocess.run(["git", "-C", str(repo), "show", f"{source_commit}:{path}"],
                            capture_output=True, check=False)
    if result.returncode:
        raise ValueError("Cannot read pinned private source: " + path +
                         "; supply a clone containing the recorded commit")
    return result.stdout


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def verify_source(source_repo):
    migration = json.loads((AFRICA / "migration.json").read_text(encoding="utf-8"))
    snapshot = json.loads((AFRICA / "upstream/manifest.json").read_text(encoding="utf-8"))
    source_commit = migration["source_commit"]
    file_meta = next(x for x in migration["missing_source_files"]
                     if x["path"].endswith("/NG/entities.csv.gz"))
    expected_metadata = next(x["metadata_sha256"] for x in snapshot["countries"]
                             if x["country"] == "NG")
    original = {}
    for filename in FILES:
        raw = pinned_git_file(source_repo, source_commit, ORIGINAL_PREFIX + filename)
        if not raw:
            raise ValueError("Pinned source is empty: " + filename)
        original[filename] = raw
    gzip_data = original["entities.csv.gz"]
    if len(gzip_data) != file_meta["size"] or git_blob_sha(gzip_data) != file_meta["sha"]:
        raise ValueError("Original Nigeria gzip blob failed pinned Git SHA or size validation")
    if sha256(original["metadata.json"]) != expected_metadata:
        raise ValueError("Pinned source metadata differs from upstream Africa manifest")
    metadata = json.loads(original["metadata.json"])
    if metadata["country"]["country"] != "NG":
        raise ValueError("Pinned source metadata has wrong country")
    if metadata["files"]["entities.csv.gz"]["sha256"] != sha256(gzip_data):
        raise ValueError("Nigeria compressed CSV SHA256 differs from source metadata")
    if metadata["preview_files"]["admin1.csv"]["sha256"] != sha256(original["admin1.csv"]):
        raise ValueError("Nigeria ADM1 preview checksum differs from source metadata")
    if metadata["counts"]["admin_rows"] + metadata["counts"]["locality_rows"] + metadata["counts"]["other_admin_rows"] != EXPECTED_NG_ROWS:
        raise ValueError("Nigeria source row total differs from pinned upstream verification")
    if metadata["current_official_hierarchy_verified"] is not False:
        raise ValueError("Original source claims unverified official hierarchy as verified")
    return original, metadata, source_commit


def sync_country_inventory(root):
    modules_path = root / "countries/modules.json"
    catalog_path = root / "countries/catalog.json"
    modules = json.loads(modules_path.read_text(encoding="utf-8"))
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    module = next(x for x in modules["countries"] if x["code"] == "NG")
    if any(x["id"] == "africa-gazetteer" for x in module["layers"]):
        raise ValueError("NG africa-gazetteer inventory already registered")
    module["layers"].insert(0, {
        "id": "africa-gazetteer", "registry": "africa", "kind": "gazetteer_directory",
        "data": "registries/africa/countries/NG",
        "metadata": "registries/africa/countries/NG/metadata.json",
        "verifier": "metadata_integrity", "selector": {"country": "NG"}
    })
    module["inventory_state"] = "source_layers_available"
    module["next_action"] = "review_recorded_parent_gaps_and_source_vintages"
    item = next(x for x in catalog["countries"] if x["code"] == "NG")
    item["paths"] = [
        "registries/africa/countries/NG/entities.csv.gz",
        "registries/africa/countries/NG/admin1.csv",
        "registries/africa/countries/NG/metadata.json",
    ]
    item["inventory_status"] = "source_layers_available"
    item["next_action"] = "review_recorded_parent_gaps_and_source_vintages"
    write_json(modules_path, modules)
    write_json(catalog_path, catalog)
    index = subprocess.run([sys.executable, "scripts/render_country_index.py"],
                           cwd=root, capture_output=True, text=True, check=True)
    (root / "countries/README.md").write_text(index.stdout, encoding="utf-8")


def stage_and_validate(original):
    import build
    with tempfile.TemporaryDirectory(prefix="ng-pinned-stage-") as td:
        staging = Path(td) / "africa"
        shutil.copytree(AFRICA, staging)
        country = staging / "countries/NG"
        if country.exists():
            raise ValueError("Nigeria directory already exists; no overwrite permitted")
        country.mkdir()
        for filename, raw in original.items():
            (country / filename).write_bytes(raw)
        scope_path = staging / "scope.json"
        current = json.loads(scope_path.read_text(encoding="utf-8"))
        upstream = json.loads((staging / "upstream/scope.json").read_text(encoding="utf-8"))
        ng = next(x for x in upstream["countries"] if x["country"] == "NG")
        if any(x["country"] == "NG" for x in current["countries"]):
            raise ValueError("NG already in current scope; do not migrate twice")
        current["countries"] = sorted(current["countries"] + [ng], key=lambda r: r["country"])
        write_json(scope_path, current)
        totals = build.summarize(staging)
        report = build.verify(staging)
        if report["countries"] != 57 or report["rows"] != EXPECTED_RESTORED_ROWS:
            raise ValueError("Restored Africa scope/row totals mismatch")
        ng_report = next(x for x in report["reports"] if x["country"] == "NG")
        if ng_report["rows"] != EXPECTED_NG_ROWS or ng_report["replay"] != "exact":
            raise ValueError("NG replay verification failed")
        yield_files = {
            f"countries/NG/{name}": (country / name).read_bytes() for name in FILES
        }
        for name in ("scope.json", "coverage.csv", "manifest.json", "verification.json"):
            yield_files[name] = (staging / name).read_bytes()
        return yield_files, report, totals


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-checkout", type=Path, required=True,
                   help="Local authenticated clone of rei-k/world-address with pinned commit available")
    p.add_argument("--apply", action="store_true", help="Apply source-preserving migration after all checks")
    args = p.parse_args()
    if (AFRICA / "countries/NG").exists():
        p.error("Nigeria data path already exists; investigate before restoring")
    original, metadata, source_commit = verify_source(args.source_checkout.resolve())
    staged, report, totals = stage_and_validate(original)
    result = {
        "country": "NG",
        "pinned_source_commit": source_commit,
        "verified_original_blob_sha": git_blob_sha(original["entities.csv.gz"]),
        "source_rows": EXPECTED_NG_ROWS,
        "all_africa_rows_after_restore": report["rows"],
        "all_africa_areas_after_restore": report["countries"],
        "source_identity_and_offline_replay": "verified",
        "official_administrative_hierarchy_verified": False,
        "changed_current_checkout": args.apply,
    }
    if args.apply:
        for rel, payload in staged.items():
            path = AFRICA / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and rel.startswith("countries/NG/"):
                raise ValueError("Refusing to replace an existing country file")
            path.write_bytes(payload)
        receipt = AFRICA / "restorations/NG-pinned-source.json"
        receipt.parent.mkdir(parents=True, exist_ok=True)
        write_json(receipt, result)
        sync_country_inventory(REPO_ROOT)
        print("Next: update Africa README, then run country module validator and full offline regression.")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
