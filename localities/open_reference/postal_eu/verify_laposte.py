"""Verify bundled files and optionally replay both publishers' public downloads."""

import argparse
import hashlib
import lzma
from urllib.request import urlopen

from . import DIRECTORY, SOURCE, _index, verified_bytes
from .cog import project


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refetch", action="store_true", help="Replay the pinned public downloads")
    args = parser.parse_args()
    bundled = verified_bytes(lzma.decompress((DIRECTORY / SOURCE["stored_file"]).read_bytes()))
    _index(DIRECTORY)
    if args.refetch:
        with urlopen(SOURCE["download_url"], timeout=60) as response:
            verified_bytes(response.read(len(bundled) + 1))
        files = {}
        cog = SOURCE["territory_reference"]
        for name, spec in cog["inputs"].items():
            with urlopen(spec["url"], timeout=120) as response:
                raw = response.read(spec["bytes"] + 1)
            if len(raw) != spec["bytes"] or hashlib.sha256(raw).hexdigest() != spec["sha256"]:
                raise ValueError(f"Unexpected INSEE input: {name}")
            files[name] = raw
        if project(files) != (DIRECTORY / cog["projection_file"]).read_bytes():
            raise ValueError("INSEE inputs differ from the packaged territorial crosswalk")
    print(f"{SOURCE['source_id']}: {len(bundled)} bytes, SHA-256 {SOURCE['raw_sha256']}")


if __name__ == "__main__":
    main()
