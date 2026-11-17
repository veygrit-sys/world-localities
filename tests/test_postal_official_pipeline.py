"""Official snapshots retain anomalies without silently claiming full support."""
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from localities.postal import build_postal_catalog, load_sources, lookup_postcode


class OfficialPostalPipeline(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "countries").mkdir()
        (self.root / "postal/sources").mkdir(parents=True)
        (self.root / "countries/catalog.json").write_text(json.dumps({
            "schema_version": 1, "countries": [{"code": "MU", "name": "Mauritius"}],
        }))
        raw = b"Locality,Sub_locality,Street,Code\nTest,Area,,00123\nTest,Area,,712547\n"
        compressed = gzip.compress(raw, mtime=0)
        (self.root / "postal/sources/test.csv.gz").write_bytes(compressed)
        self.source = {
            "id": "test-only", "format": "official_postal_source", "adapter": "mu_postal_csv4",
            "path": "postal/sources/test.csv.gz", "sha256": hashlib.sha256(compressed).hexdigest(),
            "bytes": len(compressed), "licence": "test-only", "default_code_kind": "official_full",
            "expected_country": "MU", "encoding": "utf-8-sig", "compression": "gzip",
            "uncompressed_bytes": len(raw), "uncompressed_sha256": hashlib.sha256(raw).hexdigest(),
            "expected_record_count": 2,
        }
        self.save()

    def save(self):
        (self.root / "postal/sources.json").write_text(json.dumps({"schema_version": 1, "sources": [self.source]}))

    def test_original_anomaly_is_saved_but_excluded_from_standard_lookup(self):
        catalog = build_postal_catalog(self.root)
        self.assertEqual(catalog["countries"][0]["code_kinds"], {"official_full": 1, "source_anomaly": 1})
        self.assertEqual(lookup_postcode("MU", "712547", self.root)["total"], 0)
        rows = lookup_postcode("MU", "712547", self.root, include_partial=True)["rows"]
        self.assertEqual(rows[0]["code"], "712547")
        self.assertEqual(rows[0]["observation_status"], "unreviewed_code_shape")
        self.assertEqual(rows[0]["source_locator"], "csv:record:3")

    def test_reviewed_record_count_must_match_source_replay(self):
        self.source["expected_record_count"] = 1
        self.save()
        with self.assertRaisesRegex(ValueError, "reviewed count"):
            build_postal_catalog(self.root)

    def test_adapter_country_and_kind_cannot_be_changed_implicitly(self):
        for changes in ({"adapter": "untrusted_python"}, {"expected_country": "NA"},
                        {"default_code_kind": "source_reported"}, {"expected_record_count": True}):
            with self.subTest(changes=changes):
                before = self.source.copy()
                self.source.update(changes)
                self.save()
                with self.assertRaises(ValueError):
                    load_sources(self.root)
                self.source = before

    def test_legacy_adapter_cannot_promote_a_row_to_full(self):
        self.source["default_code_kind"] = "partial_or_legacy"
        self.save()
        row = {"country_code": "MU", "code": "00123", "source_locator": "csv:record:2",
               "code_kind": "official_full"}
        with patch("localities.postal_africa_sources.iter_africa_records", return_value=iter([row])):
            with self.assertRaisesRegex(ValueError, "only demote"):
                build_postal_catalog(self.root)


if __name__ == "__main__":
    unittest.main()
