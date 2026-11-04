"""Build, verify and restore a pinned, source-qualified JP data bundle offline."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "bundle-manifest.json"
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_ENTRIES = 10000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def safe_relative(name):
    require(isinstance(name, str) and bool(name), "empty or invalid bundle path")
    path = PurePosixPath(name)
    require(not path.is_absolute() and ".." not in path.parts and "\\" not in name
            and ":" not in name and "\0" not in name and path.as_posix() == name and name != ".",
            "unsafe or noncanonical bundle path: " + name)
    return path


def outside_repository(path, root=ROOT):
    path = Path(path).absolute()
    require(not path.resolve().is_relative_to(root.resolve()), "output must be outside the repository")
    require(not path.exists() and not path.is_symlink(), "output already exists")
    require(path.parent.is_dir(), "output parent must already exist")
    return path


def checked_file(root, name):
    relative = safe_relative(name)
    path = root / relative
    require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(root.resolve()),
            "missing or unsafe source file: " + name)
    return path


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def source_paths(root):
    """Explicit source-qualified components; this is not every JP layer in the repo."""
    shared = ["registries/asia/country-archives/JP.zip", "registries/asia/archives.json",
              "registries/asia/manifest.json", "registries/asia/NOTICE.md",
              "registries/asia/DATA_LICENSES.md", "registries/asia/LICENSE",
              "registries/asia/SCHEMA.md", "registries/official/README.md",
              "registries/official/romanize.py"]
    shared.extend(path.relative_to(root).as_posix()
                  for path in (root / "registries/official/JP").rglob("*") if path.is_file())
    return sorted(shared)


def verify_selected_sources(root):
    archives = read_json(root / "registries/asia/archives.json")
    entry = next(e for e in archives["archives"] if e["country"] == "JP")
    require(entry["path"] == "country-archives/JP.zip", "unsupported JP archive layout")
    path = checked_file(root, "registries/asia/" + entry["path"])
    raw = path.read_bytes()
    require(len(raw) == entry["bytes"] and sha256(raw) == entry["sha256"], "JP archive integrity mismatch")
    with zipfile.ZipFile(path) as archive:
        require(len(archive.namelist()) == len(set(archive.namelist())), "duplicate JP source member")
        require(set(archive.namelist()) == set(entry["members"]), "JP source member set mismatch")
        for name, expected in entry["members"].items():
            safe_relative(name)
            data = archive.read(name)
            require(len(data) == expected["bytes"] and sha256(data) == expected["sha256"],
                    "JP source member integrity mismatch: " + name)
    official = read_json(root / "registries/official/JP/sources.json")
    for name, expected in official["bundled_files"].items():
        raw = checked_file(root, "registries/official/JP/" + name).read_bytes()
        require(len(raw) == expected["bytes"] and sha256(raw) == expected["sha256"],
                "JP official source integrity mismatch: " + name)
    require(sha256(checked_file(root, "registries/official/romanize.py").read_bytes())
            == official["romanization"]["code_sha256"], "romanization dependency hash mismatch")
    return {"asia_jp_archive_and_members": "passed", "official_source_inputs": "passed",
            "romanization_dependency": "passed"}


def source_commit(root, requested=None):
    commit = requested or subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    require(bool(re.fullmatch(r"[0-9a-f]{40}", commit)), "source commit must be 40 hex characters")
    return commit


def make_manifest(root=ROOT, commit=None):
    root = Path(root).resolve()
    commit = source_commit(root, commit)
    checks = verify_selected_sources(root)
    files = []
    for name in source_paths(root):
        data = checked_file(root, name).read_bytes()
        pinned_blob = subprocess.check_output(["git", "-C", str(root), "rev-parse", commit + ":" + name],
                                              text=True, stderr=subprocess.DEVNULL).strip()
        require(git_blob(data) == pinned_blob, "source differs from pinned commit: " + name)
        files.append({"path": name, "size": len(data), "sha256": sha256(data), "git_blob_sha1": pinned_blob})
    return {"schema_version": 1, "country": "JP", "bundle_type": "source_qualified_data_snapshot",
            "source_repository": "veygrit-sys/world-localities", "source_commit": commit,
            "scope": ["preserved_asia_jp_gazetteer_archive", "official_jp_codes_names_postal_overlay"],
            "excluded_scope": ["other_jp_source_layers", "standalone_service", "model_artifacts"],
            "quality": {"national_completeness_verified": False, "upstream_freshness_verified": False,
                        "deliverability_verified": False},
            "notice_paths": ["registries/asia/NOTICE.md", "registries/asia/DATA_LICENSES.md",
                             "registries/asia/LICENSE", "registries/official/README.md",
                             "registries/official/JP/README.md", "registries/official/JP/ODbL-1.0.txt",
                             "registries/official/JP/sources.json"],
            "dependency_paths": ["registries/official/romanize.py", "registries/asia/archives.json"],
            "source_checks": checks, "files": files}


def json_bytes(data):
    return (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def write_member(archive, name, data):
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, data, compresslevel=9)


def build(output, country="JP", root=ROOT, commit=None):
    require(country == "JP", "bundle pilot supports JP only")
    root = Path(root).resolve()
    output = outside_repository(output, root)
    manifest = make_manifest(root, commit)
    handle, temporary = tempfile.mkstemp(prefix=".country-bundle-", suffix=".zip", dir=output.parent)
    os.close(handle)
    try:
        with zipfile.ZipFile(temporary, "w") as archive:
            write_member(archive, MANIFEST, json_bytes(manifest))
            for entry in manifest["files"]:
                data = checked_file(root, entry["path"]).read_bytes()
                require(sha256(data) == entry["sha256"], "source changed during build")
                write_member(archive, "payload/" + entry["path"], data)
        verify(temporary)
        # An exclusive link cannot overwrite a concurrently created destination.
        os.link(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return {"status": "passed", "scope": "offline data bundle build", "bundle": str(output),
            "size": output.stat().st_size, "sha256": sha256(output.read_bytes()),
            "source_commit": manifest["source_commit"], "file_count": len(manifest["files"])}


def validated_archive(path):
    archive = zipfile.ZipFile(path)
    try:
        entries = archive.infolist()
        require(0 < len(entries) <= MAX_ENTRIES, "bundle entry limit exceeded")
        names = [item.filename for item in entries]
        require(len(names) == len(set(names)), "duplicate bundle member")
        require(MANIFEST in names, "missing bundle manifest")
        require(sum(item.file_size for item in entries) <= MAX_TOTAL_BYTES, "bundle size limit exceeded")
        for item in entries:
            require(item.orig_filename == item.filename, "noncanonical ZIP filename")
            safe_relative(item.filename)
            mode = item.external_attr >> 16
            require(not item.is_dir() and not stat.S_ISLNK(mode)
                    and (stat.S_IFMT(mode) in {0, stat.S_IFREG}), "nonregular bundle member")
            require(not item.flag_bits & 1 and item.file_size <= MAX_FILE_BYTES,
                    "encrypted or oversized bundle member")
        require(archive.getinfo(MANIFEST).file_size <= 1024 * 1024, "manifest too large")
        manifest = json.loads(archive.read(MANIFEST))
        require(isinstance(manifest, dict), "manifest must be an object")
        require(manifest.get("schema_version") == 1 and manifest.get("country") == "JP"
                and manifest.get("bundle_type") == "source_qualified_data_snapshot", "unsupported bundle manifest")
        require(bool(re.fullmatch(r"[0-9a-f]{40}", manifest.get("source_commit", ""))), "invalid source pin")
        files = manifest.get("files")
        require(isinstance(files, list) and bool(files), "empty bundle payload")
        declared = set()
        for entry in files:
            require(isinstance(entry, dict), "payload declaration must be an object")
            name = entry["path"]
            safe_relative(name)
            require(name not in declared, "duplicate declared payload")
            declared.add(name)
            require(type(entry["size"]) is int and entry["size"] >= 0
                    and re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
                    and re.fullmatch(r"[0-9a-f]{40}", entry["git_blob_sha1"]), "invalid payload integrity fields")
            info = archive.getinfo("payload/" + name)
            require(info.file_size == entry["size"], "payload size mismatch: " + name)
            data = archive.read(info)
            require(sha256(data) == entry["sha256"] and git_blob(data) == entry["git_blob_sha1"],
                    "payload hash mismatch: " + name)
        require(MANIFEST not in declared, "reserved manifest payload path")
        require(all(not any(parent.as_posix() in declared for parent in PurePosixPath(name).parents
                            if parent.as_posix() != ".") for name in declared), "payload path collision")
        require(set(names) == {MANIFEST} | {"payload/" + name for name in declared}, "undeclared bundle members")
        for field in ("notice_paths", "dependency_paths"):
            require(isinstance(manifest.get(field), list) and bool(manifest[field]), "missing " + field)
            require(all(name in declared for name in manifest[field]), "missing bundled notice or dependency")
        require(manifest.get("quality") == {"national_completeness_verified": False,
                "upstream_freshness_verified": False, "deliverability_verified": False}, "unexpected quality claim")
        return archive, manifest
    except Exception:
        archive.close()
        raise


def verify(bundle):
    archive, manifest = validated_archive(bundle)
    archive.close()
    return {"status": "passed", "scope": "bundle bytes, source pin, dependency and notice inclusion",
            "country": "JP", "source_commit": manifest["source_commit"],
            "file_count": len(manifest["files"]), "source_authenticity": "requires trusted external bundle checksum"}


def restore(bundle, output, root=ROOT):
    output = outside_repository(output, Path(root))
    archive, manifest = validated_archive(bundle)
    try:
        # Verify all bytes before creating the user-visible output directory.
        output.mkdir(exist_ok=False)
        for entry in manifest["files"]:
            destination = output / safe_relative(entry["path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as stream:
                stream.write(archive.read("payload/" + entry["path"]))
        with (output / MANIFEST).open("xb") as stream:
            stream.write(json_bytes(manifest))
    finally:
        archive.close()
    return {"status": "passed", "scope": "offline data snapshot restore", "output": str(output),
            "country": "JP", "source_commit": manifest["source_commit"], "file_count": len(manifest["files"])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("build")
    create.add_argument("--country", required=True)
    create.add_argument("--output", required=True, type=Path)
    create.add_argument("--source-commit")
    check = commands.add_parser("verify")
    check.add_argument("--bundle", required=True, type=Path)
    unpack = commands.add_parser("restore")
    unpack.add_argument("--bundle", required=True, type=Path)
    unpack.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == "build":
            report = build(args.output, args.country, commit=args.source_commit)
        elif args.command == "verify":
            report = verify(args.bundle)
        else:
            report = restore(args.bundle, args.output)
        print(json.dumps(report, ensure_ascii=False))
    except (ValueError, KeyError, OSError, TypeError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        parser.exit(1, f"country bundle failed: {error}\n")


if __name__ == "__main__":
    main()
