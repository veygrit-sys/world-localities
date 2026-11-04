import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from localities import materialize
from localities.__main__ import materialization_roots
from localities.layout import load_catalog, validate_catalog


class RepositoryLayout(unittest.TestCase):
    def test_catalog_matches_existing_registry_boundaries(self):
        report = validate_catalog(ROOT)
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["registry_count"], 10)
        self.assertEqual(report["shared_component_count"], 3)
        self.assertEqual(report["exact_duplicate_python_files"], 0)
        self.assertEqual(
            report["duplicate_python_basenames"],
            ["__init__.py", "__main__.py", "build.py", "query.py"],
        )

    def test_catalog_paths_are_unique(self):
        catalog = load_catalog()
        paths = [entry["path"] for entry in catalog["registries"]]
        self.assertEqual(len(paths), len(set(paths)))

    def test_registries_have_one_root_and_no_flat_legacy_copies(self):
        for entry in load_catalog()["registries"]:
            self.assertEqual(Path(entry["path"]).parts[0], "registries")
            self.assertFalse((ROOT / (entry["id"] + "-registry")).exists())

    def test_obsolete_duplicate_adapters_are_removed(self):
        obsolete = [
            "registries/caribbean/geonames_core.py",
            "registries/south-america/geonames_core.py",
            "registries/caribbean/materialize.py",
            "registries/central-america/materialize.py",
            "registries/south-america/materialize.py",
        ]
        self.assertTrue(all(not (ROOT / relative).exists() for relative in obsolete))

    def test_unified_cli_exposes_only_split_registries(self):
        self.assertEqual(
            materialization_roots(),
            {
                "caribbean": "registries/caribbean",
                "central-america": "registries/central-america",
                "south-america": "registries/south-america",
            },
        )

    def test_ensure_file_validates_existing_managed_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = b"verified bytes"
            target = root / "countries" / "XX" / "entities.csv.gz"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"corrupt bytes")
            manifest = {
                "files": [
                    {
                        "country": "XX",
                        "path": "countries/XX/entities.csv.gz",
                        "bytes": len(expected),
                        "sha256": hashlib.sha256(expected).hexdigest(),
                        "parts": [],
                    }
                ]
            }
            (root / "split_manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "existing output differs"):
                materialize.ensure_file(target, root)


if __name__ == "__main__":
    unittest.main()
