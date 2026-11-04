"""Security and fidelity tests for the single shared split-file materializer."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from localities.materialize import manifest, materialize_country, restore


class SplitMaterialization(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.data = b"original\x00bytes\xff"
        (self.root / "part.bin").write_bytes(self.data)
        digest = hashlib.sha256(self.data).hexdigest()
        self.entry = {
            "country": "XX",
            "path": "countries/XX/source.gz",
            "bytes": len(self.data),
            "sha256": digest,
            "parts": [
                {"path": "part.bin", "bytes": len(self.data), "sha256": digest}
            ],
        }

    def tearDown(self):
        self.temporary.cleanup()

    def write_manifest(self, entries=None):
        value = {"files": entries if entries is not None else [self.entry]}
        (self.root / "split_manifest.json").write_text(json.dumps(value))

    def test_roundtrip_is_idempotent(self):
        path = restore(self.root, self.entry)
        self.assertEqual(path.read_bytes(), self.data)
        self.assertEqual(restore(self.root, self.entry), path)

    def test_corrupt_or_oversized_part_is_rejected(self):
        (self.root / "part.bin").write_bytes(b"x")
        with self.assertRaises(ValueError):
            restore(self.root, self.entry)
        large = b"x" * (512 * 1024 + 1)
        (self.root / "part.bin").write_bytes(large)
        digest = hashlib.sha256(large).hexdigest()
        self.entry["parts"][0].update(bytes=len(large), sha256=digest)
        self.entry.update(bytes=len(large), sha256=digest)
        with self.assertRaises(ValueError):
            restore(self.root, self.entry)

    def test_target_traversal_and_absolute_paths_are_rejected(self):
        for value in ("../outside", "/tmp/outside-localities"):
            with self.subTest(value=value):
                self.entry["path"] = value
                with self.assertRaises(ValueError):
                    restore(self.root, self.entry)

    def test_part_traversal_and_symlinks_are_rejected(self):
        self.entry["parts"][0]["path"] = "../part.bin"
        with self.assertRaises(ValueError):
            restore(self.root, self.entry)
        self.entry["parts"][0]["path"] = "alias.bin"
        (self.root / "alias.bin").symlink_to(self.root / "part.bin")
        with self.assertRaises(ValueError):
            restore(self.root, self.entry)

    def test_target_symlink_is_rejected(self):
        (self.root / "countries").symlink_to("/tmp")
        with self.assertRaises(ValueError):
            restore(self.root, self.entry)

    def test_existing_different_output_is_never_overwritten(self):
        path = restore(self.root, self.entry)
        path.write_bytes(b"different")
        with self.assertRaises(ValueError):
            restore(self.root, self.entry)
        self.assertEqual(path.read_bytes(), b"different")

    def test_full_hash_mismatch_leaves_no_target(self):
        self.entry["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            restore(self.root, self.entry)
        self.assertFalse((self.root / self.entry["path"]).exists())

    def test_part_hash_mismatch_with_same_size_is_rejected(self):
        (self.root / "part.bin").write_bytes(b"x" * len(self.data))
        with self.assertRaises(ValueError):
            restore(self.root, self.entry)

    def test_wrong_aggregate_size_is_rejected(self):
        self.entry["bytes"] += 1
        with self.assertRaises(ValueError):
            restore(self.root, self.entry)

    def test_duplicate_manifest_target_is_rejected(self):
        self.write_manifest([self.entry, self.entry])
        with self.assertRaises(ValueError):
            manifest(self.root)

    def test_manifest_symlink_is_rejected(self):
        (self.root / "split_manifest.json").symlink_to(self.root / "part.bin")
        with self.assertRaises(ValueError):
            manifest(self.root)

    def test_country_validation_and_selection(self):
        self.write_manifest()
        self.assertEqual(materialize_country(self.root, "XX")[0].read_bytes(), self.data)
        with self.assertRaises(ValueError):
            materialize_country(self.root, "xx")


if __name__ == "__main__":
    unittest.main()
