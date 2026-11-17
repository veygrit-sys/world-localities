"""Hash-pinned acquisition must not overwrite or accept changed snapshots."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.world_postcodes import capture_sources


class Response(io.BytesIO):
    def __init__(self, payload, url="https://download.geonames.org/export/zip/allCountries.zip"):
        super().__init__(payload)
        self.url = url

    def geturl(self):
        return self.url


class PostalCapture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.target = self.root / "postal/sources/snapshot.zip"
        (self.root / "postal").mkdir()
        self.payload = b"pinned-source-bytes"
        self.source = {
            "id": "test-only", "format": "geonames_tsv_zip",
            "path": "postal/sources/snapshot.zip", "bytes": len(self.payload),
            "sha256": hashlib.sha256(self.payload).hexdigest(),
            "licence": "test-only", "default_code_kind": "source_reported",
            "download_url": "https://download.geonames.org/export/zip/allCountries.zip",
        }

    def manifest(self):
        (self.root / "postal/sources.json").write_text(json.dumps({"schema_version": 1, "sources": [self.source]}))

    def test_existing_correct_snapshot_needs_no_network(self):
        self.manifest()
        self.target.parent.mkdir()
        self.target.write_bytes(self.payload)
        with patch("scripts.world_postcodes.urlopen") as network:
            self.assertEqual(capture_sources(self.root)[0]["status"], "reused_verified_snapshot")
            network.assert_not_called()

    def test_existing_wrong_snapshot_is_never_overwritten(self):
        self.manifest()
        self.target.parent.mkdir()
        self.target.write_bytes(b"changed")
        with patch("scripts.world_postcodes.urlopen") as network:
            with self.assertRaisesRegex(ValueError, "immutable"):
                capture_sources(self.root)
            network.assert_not_called()
        self.assertEqual(self.target.read_bytes(), b"changed")

    def test_capture_publishes_only_matching_bytes(self):
        self.manifest()
        with patch("scripts.world_postcodes.urlopen", return_value=Response(self.payload)):
            self.assertEqual(capture_sources(self.root)[0]["status"], "captured_verified_bytes")
        self.assertEqual(self.target.read_bytes(), self.payload)

    def test_changed_or_oversized_download_leaves_no_partial_file(self):
        self.manifest()
        for payload in (b"x" * len(self.payload), self.payload + b"x"):
            with self.subTest(payload=payload):
                with patch("scripts.world_postcodes.urlopen", return_value=Response(payload)):
                    with self.assertRaises(ValueError):
                        capture_sources(self.root)
                self.assertFalse(self.target.exists())
                self.assertEqual(list(self.target.parent.iterdir()), [])

    def test_unapproved_url_or_redirect_is_rejected(self):
        self.source["download_url"] = "https://example.invalid/export/zip/allCountries.zip"
        self.manifest()
        with patch("scripts.world_postcodes.urlopen") as network:
            with self.assertRaisesRegex(ValueError, "approved"):
                capture_sources(self.root)
            network.assert_not_called()
        self.source["download_url"] = "https://download.geonames.org/export/zip/allCountries.zip"
        self.manifest()
        with patch("scripts.world_postcodes.urlopen", return_value=Response(self.payload, "https://example.invalid/")):
            with self.assertRaisesRegex(ValueError, "redirect"):
                capture_sources(self.root)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
