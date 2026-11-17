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
from scripts.world_postcodes import approved_archive_url, capture_sources


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

    def test_only_reviewed_japan_post_paths_and_formats_are_allowed(self):
        urls = {
            "https://www.post.japanpost.jp/service/search/zipcode/download/utf/zip/utf_ken_all.zip": "japanpost_utf_zip",
            "https://www.post.japanpost.jp/service/search/zipcode/download/office/zip/jigyosyo.zip": "japanpost_business_zip",
        }
        for url, format_name in urls.items():
            with self.subTest(url=url):
                self.assertTrue(approved_archive_url(url, format_name))
                self.assertFalse(approved_archive_url(url, "geonames_tsv_zip"))
                self.assertFalse(approved_archive_url(url + "?latest=1", format_name))
                self.assertFalse(approved_archive_url(url.replace("https:", "http:"), format_name))
                self.assertFalse(approved_archive_url(url.replace("www.post.japanpost.jp", "www.post.japanpost.jp.example.invalid"), format_name))

    def test_full_geonames_archives_are_allowed_without_broadening_hosts(self):
        for country in ("CA", "GB", "NL"):
            url = f"https://download.geonames.org/export/zip/{country}_full.csv.zip"
            self.assertTrue(approved_archive_url(url, "geonames_tsv_zip"))
            self.assertFalse(approved_archive_url(url, "japanpost_utf_zip"))

    def test_same_host_redirect_to_a_different_archive_is_rejected(self):
        self.manifest()
        redirected = "https://download.geonames.org/export/zip/CA_full.csv.zip"
        with patch("scripts.world_postcodes.urlopen", return_value=Response(self.payload, redirected)):
            with self.assertRaisesRegex(ValueError, "redirect"):
                capture_sources(self.root)
        self.assertFalse(self.target.exists())


if __name__ == "__main__":
    unittest.main()
