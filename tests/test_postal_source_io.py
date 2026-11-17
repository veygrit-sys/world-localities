"""Fixed snapshots preserve original bytes and stop invalid expansion."""

import gzip
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from localities.postal_source_io import read_source_bytes, read_source_text


class PostalSourceSnapshot(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "source.gz"
        self.data = "原文\t00123\n".encode()
        self.path.write_bytes(gzip.compress(self.data, mtime=0))
        self.source = {"compression": "gzip", "uncompressed_bytes": len(self.data),
                       "uncompressed_sha256": hashlib.sha256(self.data).hexdigest()}

    def test_original_byte_image_and_text_are_preserved(self):
        self.assertEqual(read_source_bytes(self.source, self.path), self.data)
        self.assertEqual(read_source_text(self.source, self.path), self.data.decode())

    def test_wrong_original_digest_or_size_is_rejected(self):
        for changes in ({"uncompressed_sha256": "0" * 64}, {"uncompressed_bytes": 2}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                read_source_bytes({**self.source, **changes}, self.path)

    def test_missing_metadata_and_boolean_size_are_rejected(self):
        for source in ({"compression": "gzip"}, {**self.source, "uncompressed_bytes": True}):
            with self.subTest(source=source), self.assertRaises(ValueError):
                read_source_bytes(source, self.path)

    def test_declared_expansion_over_limit_is_rejected_before_reading(self):
        with patch("localities.postal_source_io.MAX_EXPANDED_BYTES", 2), self.assertRaises(ValueError):
            read_source_bytes(self.source, self.path)

    def test_corrupt_gzip_fails_without_a_partial_result(self):
        self.path.write_bytes(b"not gzip")
        with self.assertRaises(ValueError):
            read_source_bytes(self.source, self.path)

    def test_uncompressed_source_and_encoding_are_explicit(self):
        self.path.write_bytes(b"R251\n")
        self.assertEqual(read_source_text({}, self.path, "cp1252"), "R251\n")
        for source in ({"compression": "zip"},):
            with self.assertRaises(ValueError):
                read_source_bytes(source, self.path)
        with self.assertRaises(ValueError):
            read_source_text({}, self.path, "utf-16")
