"""Restore exact large-file bytes from bounded local parts, without network access."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any

MAX_OUTPUT_BYTES = 256 * 1024 * 1024
MAX_PART_BYTES = 512 * 1024


def safe_path(root: Path, name: str) -> Path:
    """Resolve a manifest path below *root* and reject traversal and symlinks."""
    relative = PurePosixPath(name)
    if (
        relative.is_absolute()
        or not name
        or "\\" in name
        or any(part in ("", ".", "..") for part in name.split("/"))
    ):
        raise ValueError("unsafe package path")

    root = root.resolve()
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlink package path")
    return root.joinpath(*relative.parts)


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def restore(root: Path, entry: dict[str, Any]) -> Path:
    """Validate or atomically reconstruct one manifest entry."""
    target = safe_path(root, entry["path"])
    output_bytes = entry["bytes"]
    if not isinstance(output_bytes, int) or not 0 <= output_bytes <= MAX_OUTPUT_BYTES:
        raise ValueError("unexpected reconstructed size")

    if target.exists():
        if (
            not target.is_file()
            or target.stat().st_size != output_bytes
            or sha_file(target) != entry["sha256"]
        ):
            raise ValueError("existing output differs; refusing to overwrite")
        return target

    parts: list[Path] = []
    total = 0
    for part in entry["parts"]:
        path = safe_path(root, part["path"])
        if (
            not path.is_file()
            or path.stat().st_size != part["bytes"]
            or sha_file(path) != part["sha256"]
        ):
            raise ValueError("part size/checksum mismatch")
        if not 0 < part["bytes"] <= MAX_PART_BYTES:
            raise ValueError("unexpected part size")
        total += part["bytes"]
        parts.append(path)
    if total != output_bytes:
        raise ValueError("part aggregate size mismatch")

    target.parent.mkdir(parents=True, exist_ok=True)
    # Re-check the path after creating its parent, before writing.
    safe_path(root, entry["path"])
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=f".{target.name}.", delete=False
        ) as destination:
            temporary = Path(destination.name)
            for path in parts:
                with path.open("rb") as source:
                    for block in iter(lambda: source.read(1024 * 1024), b""):
                        destination.write(block)
        if temporary.stat().st_size != output_bytes or sha_file(temporary) != entry["sha256"]:
            raise ValueError("reconstructed checksum mismatch")
        # Linking is atomic and cannot overwrite an independently created file.
        os.link(temporary, target)
        temporary.unlink()
        temporary = None
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def manifest(root: Path) -> list[dict[str, Any]]:
    path = safe_path(root, "split_manifest.json")
    if not path.exists():
        return []
    entries = json.loads(path.read_text(encoding="utf-8"))["files"]
    if len({entry["path"] for entry in entries}) != len(entries):
        raise ValueError("duplicate file path")
    return entries


def materialize_country(root: Path, country: str) -> list[Path]:
    if not re.fullmatch(r"[A-Z]{2}", country):
        raise ValueError("invalid country")
    return [
        restore(root, entry)
        for entry in manifest(root)
        if entry.get("country") == country
    ]


def ensure_file(path: Path, root: Path) -> Path:
    """Validate a managed file if present, or reconstruct it if absent."""
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path
    for entry in manifest(root):
        if entry["path"] == relative:
            return restore(root, entry)
    return path


def main(default_root: Path | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", required=True)
    parser.add_argument("--root", type=Path, default=default_root)
    args = parser.parse_args()
    if args.root is None:
        parser.error("--root is required")
    for path in materialize_country(args.root, args.country):
        print(path.relative_to(args.root))


if __name__ == "__main__":
    main()
