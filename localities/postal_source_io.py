"""Read lossless fixed postal-source snapshots without unbounded expansion."""

from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
import re
from typing import Mapping

MAX_EXPANDED_BYTES = 32 * 1024 * 1024


def read_source_bytes(source: Mapping, path: Path) -> bytes:
    """The caller verifies stored bytes; gzip also verifies the original byte image."""
    compression = source.get("compression", "none")
    if not isinstance(compression, str) or compression not in {"none", "gzip"}:
        raise ValueError("unsupported official postal source compression")
    if compression == "gzip":
        expected_size = source.get("uncompressed_bytes")
        expected_hash = source.get("uncompressed_sha256")
        if (type(expected_size) is not int or not 0 <= expected_size <= MAX_EXPANDED_BYTES
                or not isinstance(expected_hash, str)
                or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)):
            raise ValueError("compressed postal source requires original byte size and SHA-256")
        try:
            with gzip.open(path, "rb") as stream:
                data = stream.read(expected_size + 1)
        except (OSError, EOFError) as error:
            raise ValueError("cannot expand compressed postal source") from error
        if len(data) != expected_size or hashlib.sha256(data).hexdigest() != expected_hash:
            raise ValueError("expanded postal source differs from its original byte image")
        return data
    if path.stat().st_size > MAX_EXPANDED_BYTES:
        raise ValueError("official postal source exceeds the read limit")
    with path.open("rb") as stream:
        data = stream.read(MAX_EXPANDED_BYTES + 1)
    if len(data) > MAX_EXPANDED_BYTES:
        raise ValueError("official postal source exceeds the read limit")
    return data


def read_source_text(source: Mapping, path: Path, encoding: str = "utf-8-sig") -> str:
    if encoding not in {"utf-8", "utf-8-sig", "cp1252", "cp932"}:
        raise ValueError("unsupported official postal source encoding")
    return read_source_bytes(source, path).decode(encoding)
