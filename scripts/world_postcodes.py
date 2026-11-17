"""Capture pinned sources and replay the staged worldwide postal inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from localities.postal import (
    MAX_ARCHIVE_BYTES,
    build_postal_catalog,
    load_sources,
    lookup_postcode,
    verify_postal_catalog,
)

JAPAN_POST_ARCHIVES = {
    "/service/search/zipcode/download/utf/zip/utf_ken_all.zip": "japanpost_utf_zip",
    "/service/search/zipcode/download/office/zip/jigyosyo.zip": "japanpost_business_zip",
}


def approved_archive_url(url: str, source_format: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.query or parsed.fragment:
        return False
    if parsed.netloc == "download.geonames.org":
        return source_format == "geonames_tsv_zip" and bool(re.fullmatch(
            r"/export/zip/(?:allCountries|[A-Z]{2}(?:_full\.csv)?)\.zip", parsed.path
        ))
    return (parsed.netloc == "www.post.japanpost.jp"
            and JAPAN_POST_ARCHIVES.get(parsed.path) == source_format)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile("w", dir=path.parent, encoding="utf-8",
                                         delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def capture_sources(root: Path = ROOT) -> list[dict[str, object]]:
    """Download only named, hash-pinned public files; retain existing snapshots."""
    results = []
    for source in load_sources(root)["sources"]:
        if "download_url" not in source:
            continue
        if PurePosixPath(source["path"]).parts[:2] != ("postal", "sources"):
            raise ValueError("capture destination must be inside postal/sources")
        url = source["download_url"]
        if not approved_archive_url(url, source["format"]):
            raise ValueError("capture URL is not an approved postal archive")
        relative = PurePosixPath(source["path"])
        target = (root / relative).resolve()
        if (relative.parts[:2] != ("postal", "sources")
                or not target.is_relative_to((root / "postal/sources").resolve())):
            raise ValueError("capture target must be under postal/sources")
        if target.exists():
            if (target.stat().st_size != source["bytes"]
                    or hashlib.sha256(target.read_bytes()).hexdigest() != source["sha256"].lower()):
                raise ValueError("existing immutable postal snapshot differs")
            results.append({"id": source["id"], "status": "reused_verified_snapshot"})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            digest = hashlib.sha256()
            size = 0
            with tempfile.NamedTemporaryFile("wb", dir=target.parent, delete=False) as stream:
                temporary = Path(stream.name)
                with urlopen(Request(url, headers={"User-Agent": "WorldLocalities-PostalCapture/1.0"}),
                             timeout=60) as response:
                    if response.geturl() != url:
                        raise ValueError("unapproved postal archive redirect")
                    while block := response.read(1024 * 1024):
                        size += len(block)
                        if size > min(source["bytes"], MAX_ARCHIVE_BYTES):
                            raise ValueError("postal download exceeds pinned size")
                        digest.update(block)
                        stream.write(block)
            if size != source["bytes"] or digest.hexdigest() != source["sha256"].lower():
                raise ValueError("download differs from pinned postal snapshot; review a new version")
            # A snapshot at this path is immutable. Never replace a different file.
            # Atomic creation fails if another process already published this path.
            # Both files are in the same directory/filesystem.
            os.link(temporary, target)
            results.append({"id": source["id"], "status": "captured_verified_bytes", "bytes": size})
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("capture", help="download missing pinned source archives")
    commands.add_parser("build", help="replay sources into the 250-code inventory")
    commands.add_parser("verify", help="replay and compare the complete saved inventory")
    commands.add_parser("status", help="show the stored stage summary")
    lookup = commands.add_parser("lookup", help="match literal stored source codes")
    lookup.add_argument("--country", required=True)
    lookup.add_argument("--code", required=True)
    lookup.add_argument("--limit", type=int, default=20)
    lookup.add_argument("--offset", type=int, default=0)
    lookup.add_argument("--include-partial", action="store_true")
    lookup.add_argument("--include-historical", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command == "capture":
            result = {"sources": capture_sources(root)}
        elif args.command == "build":
            catalog = build_postal_catalog(root)
            write_json(root / "postal/catalog.json", catalog)
            result = catalog["summary"]
        elif args.command == "verify":
            result = verify_postal_catalog(root)
        elif args.command == "status":
            result = json.loads((root / "postal/catalog.json").read_text(encoding="utf-8"))["summary"]
        else:
            result = lookup_postcode(args.country, args.code, root=root, limit=args.limit,
                                     offset=args.offset, include_partial=args.include_partial,
                                     include_historical=args.include_historical)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"postal operation failed: {error}\n")


if __name__ == "__main__":
    main()
