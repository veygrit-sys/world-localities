from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from localities.postal_cv_bt_sources import (
    BHUTAN_HEADERS, BHUTAN_REGIONS, BHUTAN_URL, iter_cv_bt_records,
)


def _receipt(region: str, html: str) -> dict:
    raw = html.encode("utf-8")
    return {"url": BHUTAN_URL, "method": "POST",
            "form": {"dzongkhag": region, "submit": "Search"},
            "raw_utf8": html, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _html(region: str, code: str = "00123", duplicate: bool = False) -> str:
    # Missing opening tr after the first record matches the original PHP output.
    head = "<table><tr>" + "".join(f"<th>{h}</th>" for h in BHUTAN_HEADERS) + "</tr>"
    row = f"<td>{region}</td><td>Original Area</td><td>Original PO</td><td>{code}</td></tr>"
    return head + "<tr>" + row + (row if duplicate else "") + "</table>"


def _bundle() -> dict:
    return {"schema_version": 1, "published_region_options": list(BHUTAN_REGIONS),
            "responses": [_receipt(r, _html(r, duplicate=i == 0))
                          for i, r in enumerate(BHUTAN_REGIONS)]}


class BhutanPostalSourcesTests(unittest.TestCase):
    def replay(self, bundle: dict, compressed: bool = False) -> list[dict[str, str]]:
        raw = (json.dumps(bundle, ensure_ascii=False) + "\n").encode()
        source = {"adapter": "bt_postcode_regions"}
        data = raw
        if compressed:
            source.update(compression="gzip", uncompressed_bytes=len(raw),
                          uncompressed_sha256=hashlib.sha256(raw).hexdigest())
            data = gzip.compress(raw, mtime=0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "source"
            path.write_bytes(data)
            return list(iter_cv_bt_records(source, path))

    def test_preserves_duplicate_observations_and_leading_zero(self):
        rows = self.replay(_bundle())
        self.assertEqual(len(rows), 21)
        self.assertEqual(rows[0]["code"], "00123")
        self.assertEqual(rows[0]["place_name"], "Original PO")
        self.assertEqual(rows[0]["admin_name1"], "Bumthang")
        self.assertEqual(rows[0]["code"], rows[1]["code"])
        self.assertNotEqual(rows[0]["source_locator"], rows[1]["source_locator"])
        self.assertIn("response:1/form:dzongkhag:Bumthang/table:1/row:1", rows[0]["source_locator"])

    def test_compressed_bundle_replays_exactly(self):
        bundle = _bundle()
        self.assertEqual(self.replay(bundle), self.replay(bundle, compressed=True))

    def test_response_hash_or_bytes_tampering_rejected(self):
        for key, value in [("sha256", "0" * 64), ("bytes", 0), ("bytes", True)]:
            with self.subTest(key=key):
                bundle = _bundle()
                bundle["responses"][0][key] = value
                with self.assertRaises(ValueError):
                    self.replay(bundle)

    def test_missing_or_duplicate_region_response_rejected(self):
        for responses in [_bundle()["responses"][:-1], [_bundle()["responses"][0]] * 20]:
            bundle = _bundle()
            bundle["responses"] = responses
            with self.assertRaises(ValueError):
                self.replay(bundle)

    def test_unpublished_region_option_rejected(self):
        bundle = _bundle()
        bundle["published_region_options"][0] = "Guessed"
        with self.assertRaises(ValueError):
            self.replay(bundle)

    def test_cross_region_rows_rejected(self):
        bundle = _bundle()
        bundle["responses"][0] = _receipt("Bumthang", _html("Thimphu"))
        with self.assertRaisesRegex(ValueError, "cross-region"):
            self.replay(bundle)

    def test_malformed_code_rejected_without_padding(self):
        for code in ["1234", "123456", "12 34", "ABCDE"]:
            with self.subTest(code=code):
                bundle = _bundle()
                bundle["responses"][0] = _receipt("Bumthang", _html("Bumthang", code))
                with self.assertRaises(ValueError):
                    self.replay(bundle)

    def test_empty_or_ambiguous_table_rejected(self):
        for html in ["<table><tr><th>Postal Code</th></tr></table>",
                     _html("Bumthang") + _html("Bumthang")]:
            bundle = _bundle()
            bundle["responses"][0] = _receipt("Bumthang", html)
            with self.assertRaises(ValueError):
                self.replay(bundle)

    def test_request_receipt_is_specific_to_public_directory(self):
        for key, value in [("url", "https://example.invalid/"), ("method", "DELETE"),
                           ("form", {"dzongkhag": "Bumthang"})]:
            bundle = _bundle()
            bundle["responses"][0][key] = value
            with self.assertRaises(ValueError):
                self.replay(bundle)

    def test_unknown_adapter_rejected(self):
        with self.assertRaises(ValueError):
            list(iter_cv_bt_records({"adapter": "unknown"}, Path("unused")))


if __name__ == "__main__":
    unittest.main()
