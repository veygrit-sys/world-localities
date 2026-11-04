#!/usr/bin/env python3
"""Verify and restore pinned address-point release ZIPs without dependencies.

Code and data stay separate. No download, Git operation, or delivery verification
is performed. Installation is atomic per file, not across the whole release.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import zipfile

DEFAULT_LOCK = Path(__file__).resolve().parents[1] / "releases/address-points/20261015.json"
CHUNK = 1024 * 1024


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def relative_name(value: str) -> str:
    if not isinstance(value, str) or not value or any(c in value for c in ("\\", ":", "\x00")):
        raise ValueError("Unsafe relative path")
    parts = value.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}
    if any(p in ("", ".", "..") or p.endswith((".", " ")) or p.split(".")[0].upper() in reserved for p in parts):
        raise ValueError("Unsafe relative path: " + value)
    return value


def destination(root: Path, value: str) -> Path:
    path = root
    for part in relative_name(value).split("/"):
        path = path / part
        if path.is_symlink():
            raise ValueError("Symlink destination refused: " + value)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Destination escapes target")
    if path.exists() and not path.is_file():
        raise ValueError("Destination is not a regular file: " + value)
    return path


def check_record(item: dict) -> None:
    if type(item.get("bytes")) is not int or item["bytes"] < 0:
        raise ValueError("Invalid expected byte count")
    if not isinstance(item.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
        raise ValueError("Invalid SHA-256")


def check_file(path: Path, item: dict) -> None:
    check_record(item)
    if not path.is_file() or path.stat().st_size != item["bytes"] or digest(path) != item["sha256"]:
        raise ValueError("File integrity check failed: " + path.name)


def zip_members(archive: zipfile.ZipFile) -> dict:
    result = {}
    folded = set()
    for info in archive.infolist():
        name = relative_name(info.filename.rstrip("/") if info.is_dir() else info.filename)
        if name.casefold() in folded or stat.S_ISLNK(info.external_attr >> 16):
            raise ValueError("Duplicate or symlink ZIP member: " + name)
        folded.add(name.casefold())
        if not info.is_dir():
            result[name] = info
    return result


@contextmanager
def bundle(code: Path, lock_path: Path, parts: Path | None):
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    if lock.get("schema_version") != 1:
        raise ValueError("Unsupported lock schema")
    matches = [r for r in lock["releases"] if r["code"]["name"] == code.name]
    if len(matches) != 1:
        raise ValueError("Code ZIP is not uniquely pinned in lock")
    release = matches[0]
    check_file(code, release["code"])
    with ExitStack() as stack:
        archive = stack.enter_context(zipfile.ZipFile(code))
        members = zip_members(archive)
        manifest_name = relative_name(release["manifest"])
        manifest = json.loads(archive.read(members[manifest_name]))
        if manifest.get("schema_version") != 1 or manifest.get("release") != release["release"]:
            raise ValueError("Release manifest identity mismatch")
        if manifest["data_archives"] != release["data_archives"]:
            raise ValueError("Data archive pins differ from lock")
        archives = {}
        for item in manifest["data_archives"]:
            name = relative_name(item["name"])
            if "/" in name or name in archives:
                raise ValueError("Invalid or duplicate data archive name")
            check_record(item)
            archives[name] = None
            if parts is not None:
                check_file(parts / name, item)
                data = stack.enter_context(zipfile.ZipFile(parts / name))
                archives[name] = (data, zip_members(data))
        destinations = set()
        for item in manifest["payloads"]:
            name = relative_name(item["path"])
            if not (name.startswith("address-points/") or name.startswith("tests/") or name == "official-registry/JP/entities.csv.gz"):
                raise ValueError("Payload outside address release scope: " + name)
            if name.casefold() in destinations:
                raise ValueError("Duplicate payload destination")
            destinations.add(name.casefold())
            check_record(item)
            previous = item.get("expected_previous_sha256")
            if previous is not None and (not isinstance(previous, str) or not re.fullmatch(r"[0-9a-f]{64}", previous)):
                raise ValueError("Invalid previous SHA-256")
            store = item["storage"]
            if store["kind"] == "overlay":
                key = relative_name(store["path"])
                if not key.startswith("overlay/") or key not in members:
                    raise ValueError("Missing or invalid overlay member")
                if members[key].file_size != item["bytes"]:
                    raise ValueError("Overlay size mismatch")
            elif store["kind"] == "parts":
                for fragment in store["fragments"]:
                    check_record(fragment)
                    relative_name(fragment["member"])
                    if fragment["archive"] not in archives:
                        raise ValueError("Unpinned data archive")
                if sum(f["bytes"] for f in store["fragments"]) != item["bytes"]:
                    raise ValueError("Fragment size total mismatch")
            else:
                raise ValueError("Unknown payload storage")
        yield manifest, archive, members, archives


def copy_payload(item: dict, code, members: dict, archives: dict, output) -> None:
    store = item["storage"]
    if store["kind"] == "overlay":
        pieces = [(code, members[store["path"]], item)]
    else:
        pieces = []
        for fragment in store["fragments"]:
            pair = archives[fragment["archive"]]
            if pair is None:
                raise ValueError("Data ZIPs are required")
            archive, entries = pair
            info = entries[fragment["member"]]
            if info.file_size != fragment["bytes"]:
                raise ValueError("Fragment ZIP size mismatch")
            pieces.append((archive, info, fragment))
    whole, total = hashlib.sha256(), 0
    for archive, info, expected in pieces:
        part, size = hashlib.sha256(), 0
        with archive.open(info) as stream:
            while block := stream.read(CHUNK):
                size += len(block)
                total += len(block)
                if size > expected["bytes"] or total > item["bytes"]:
                    raise ValueError("Payload exceeds declared size")
                part.update(block)
                whole.update(block)
                if output is not None:
                    output.write(block)
        if size != expected["bytes"] or part.hexdigest() != expected["sha256"]:
            raise ValueError("Fragment or overlay checksum mismatch")
    if total != item["bytes"] or whole.hexdigest() != item["sha256"]:
        raise ValueError("Payload checksum mismatch")


def verify(code: Path, lock_path: Path = DEFAULT_LOCK, parts: Path | None = None) -> dict:
    with bundle(code, lock_path, parts) as (manifest, archive, members, archives):
        checked = skipped = 0
        for item in manifest["payloads"]:
            if parts is None and item["storage"]["kind"] == "parts":
                skipped += 1
                continue
            copy_payload(item, archive, members, archives, None)
            checked += 1
        return {"release": manifest["release"], "status": "VERIFIED_CODE_ONLY" if skipped else "VERIFIED_PAYLOADS",
                "verified_payloads": checked, "unverified_data_payloads": skipped,
                "data_archives_verified": len(archives) if parts is not None else 0,
                "delivery_verified": False}


def existing_state(root: Path, item: dict) -> str:
    path = destination(root, item["path"])
    if not path.exists():
        return "absent"
    actual = digest(path)
    if actual == item["sha256"]:
        return "same"
    if actual == item.get("expected_previous_sha256"):
        return "previous"
    raise ValueError("Unrecognized existing edit; refused: " + item["path"])


def apply(code: Path, parts: Path, target: Path, lock_path: Path = DEFAULT_LOCK) -> dict:
    if any(p.is_symlink() for p in (target, *target.parents)):
        raise ValueError("Symlink target refused")
    with bundle(code, lock_path, parts) as (manifest, archive, members, archives):
        target.mkdir(parents=True, exist_ok=True)
        lockfile = target / ".address-release.lock"
        fd = os.open(lockfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            states = {i["path"]: existing_state(target, i) for i in manifest["payloads"]}
            with tempfile.TemporaryDirectory(prefix=".address-release-", dir=target) as temporary:
                stage = Path(temporary)
                for item in manifest["payloads"]:
                    path = destination(stage, item["path"])
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("xb") as stream:
                        copy_payload(item, archive, members, archives, stream)
                        stream.flush()
                        os.fsync(stream.fileno())
                result = {"release": manifest["release"], "status": "APPLIED", "installed": 0, "updated": 0, "unchanged": 0}
                for item in manifest["payloads"]:
                    state = existing_state(target, item)
                    if state != states[item["path"]]:
                        raise ValueError("Target changed during installation")
                    path = destination(target, item["path"])
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if state == "same":
                        result["unchanged"] += 1
                    elif state == "previous":
                        os.replace(stage / item["path"], path)
                        result["updated"] += 1
                    else:
                        os.link(stage / item["path"], path)
                        result["installed"] += 1
                return result
        finally:
            os.close(fd)
            lockfile.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify", "apply"))
    parser.add_argument("--code", type=Path, required=True)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--parts", type=Path)
    parser.add_argument("--target", type=Path)
    args = parser.parse_args()
    if args.command == "apply" and (args.parts is None or args.target is None):
        parser.error("apply requires --parts and --target")
    try:
        result = (verify(args.code, args.lock, args.parts) if args.command == "verify"
                  else apply(args.code, args.parts, args.target, args.lock))
    except (ValueError, OSError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Address release failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
