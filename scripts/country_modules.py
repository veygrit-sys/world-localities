"""Offline inventory checks for independently managed country modules."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def safe_path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if not name or relative.is_absolute() or ".." in relative.parts or "\\" in name:
        raise ValueError(f"unsafe path: {name}")
    target = root / relative
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"path escapes repository: {name}")
    return target


def catalog(root: Path = ROOT) -> dict:
    data = read_json(root / "countries/catalog.json")
    if data.get("schema_version") != 1:
        raise ValueError("unsupported country catalog version")
    codes = [entry["code"] for entry in data["countries"]]
    if len(codes) != len(set(codes)) or not all(re.fullmatch(r"[A-Z]{2}", c) for c in codes):
        raise ValueError("invalid or duplicate country code")
    import csv
    with safe_path(root, data["scope_source"]).open(encoding="utf-8-sig", newline="") as stream:
        expected = {row["code"] for row in csv.DictReader(stream)}
    if set(codes) != expected:
        raise ValueError("catalog and scope source differ")
    return data


def validate_release(data: dict, country: str) -> None:
    if data.get("schema_version") != 1 or data.get("country") != country:
        raise ValueError("release schema or country mismatch")
    for field in ("version", "data_schema_version", "source_commit", "notice_path", "quality_report"):
        if not isinstance(data.get(field), str) or not data[field]:
            raise ValueError(f"release missing {field}")
    if not re.fullmatch(r"[0-9a-f]{40}", data["source_commit"]):
        raise ValueError("release must pin a full source commit")
    for field in ("notice_path", "quality_report"):
        safe_path(Path("/bundle"), data[field])
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("release needs artifacts")
    names = set()
    for artifact in artifacts:
        name = artifact["path"]
        safe_path(Path("/bundle"), name)
        if name in names:
            raise ValueError("duplicate release artifact")
        names.add(name)
        uri = urlparse(artifact["url"])
        if uri.scheme != "https" or not uri.hostname or uri.username or uri.password:
            raise ValueError("artifact URL must be HTTPS without credentials")
        if not re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]):
            raise ValueError("invalid artifact checksum")
        if type(artifact["size"]) is not int or artifact["size"] < 0:
            raise ValueError("invalid artifact size")


def validate(root: Path = ROOT, country: str | None = None) -> dict:
    data = catalog(root)
    entries = data["countries"]
    if country:
        entries = [entry for entry in entries if entry["code"] == country]
        if not entries:
            raise ValueError(f"unknown country: {country}")
    checked = 0
    for entry in entries:
        storage = entry["storage"]
        if storage["kind"] not in {"monorepo", "external"}:
            raise ValueError("unknown storage kind")
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", storage["repository"]):
            raise ValueError("invalid repository name")
        if storage["kind"] == "external":
            if not re.fullmatch(r"[0-9a-f]{40}", storage.get("ref") or ""):
                raise ValueError("external module must pin a commit")
            if not entry["release_manifests"]:
                raise ValueError("external module needs a release manifest")
        if len(entry["paths"]) != len(set(entry["paths"])):
            raise ValueError("duplicate country path")
        for name in entry["paths"]:
            if not safe_path(root, name).is_file():
                raise ValueError(f"missing inventoried file: {name}")
            checked += 1
        for name in entry["release_manifests"]:
            validate_release(read_json(safe_path(root, name)), entry["code"])
        quality = entry["quality"]
        if quality != {"national_completeness_verified": False, "coverage_fraction": None,
                       "deliverability_verified": False}:
            raise ValueError("inventory catalog must not assert data quality; use a separate quality report")
    return {"status": "passed", "countries": len(entries), "path_references": checked,
            "scope": "inventory integrity only; not address accuracy or completeness"}


def verify_migration(root: Path = ROOT) -> dict:
    data = read_json(root / "docs/migration/source-manifest.json")
    files = data["files"]
    if data["source_file_count"] != len(files) or len({f["path"] for f in files}) != len(files):
        raise ValueError("invalid migration inventory")
    for entry in files:
        path = (root / "docs/migration/source-root-readme.md" if entry["path"] == "README.md"
                else safe_path(root, entry["path"]))
        content = path.read_bytes()
        if len(content) != entry["size"] or hashlib.sha256(content).hexdigest() != entry["sha256"]:
            raise ValueError(f"migration bytes differ: {entry['path']}")
        blob = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if blob != entry["git_blob_sha"]:
            raise ValueError(f"migration Git blob differs: {entry['path']}")
    return {"status": "passed", "files": len(files), "source_commit": data["source_commit"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    check = commands.add_parser("validate")
    check.add_argument("--country")
    commands.add_parser("verify-migration")
    release = commands.add_parser("validate-release")
    release.add_argument("--country", required=True)
    release.add_argument("--manifest", required=True)
    args = parser.parse_args()
    try:
        if args.command == "list":
            for entry in catalog()["countries"]:
                print(f"{entry['code']}\t{entry['name']}\t{len(entry['paths'])}\t{entry['inventory_status']}")
            return
        if args.command == "verify-migration":
            result = verify_migration()
        elif args.command == "validate-release":
            if args.country not in {e["code"] for e in catalog()["countries"]}:
                raise ValueError("unknown country")
            validate_release(read_json(safe_path(ROOT, args.manifest)), args.country)
            result = {"status": "passed", "scope": "release metadata only; artifact download not performed"}
        else:
            result = validate(country=args.country)
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, KeyError, OSError, TypeError) as error:
        parser.exit(1, f"country module check failed: {error}\n")


if __name__ == "__main__":
    main()
