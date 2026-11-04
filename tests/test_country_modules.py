"""Country isolation, integrity and future release contract regression tests."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location(
    "country_modules", Path(__file__).resolve().parents[1] / "scripts/country_modules.py")
modules = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(modules)


class CountryModulesTests(unittest.TestCase):
    def test_scope_preserves_namibia_and_unmapped_areas(self):
        entries = {e["code"]: e for e in modules.catalog()["countries"]}
        self.assertEqual(250, len(entries))
        self.assertEqual("Namibia", entries["NA"]["name"])
        self.assertIn("XK", entries)
        self.assertTrue(any(not e["paths"] for e in entries.values()))

    def test_one_country_does_not_validate_other_country_files(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "countries").mkdir()
            (root / "scope.csv").write_text("code\nJP\nNA\n")
            base = {"storage": {"kind": "monorepo", "repository": "example/repo"},
                    "release_manifests": [], "quality": {"national_completeness_verified": False,
                    "coverage_fraction": None, "deliverability_verified": False}}
            jp, na = copy.deepcopy(base), copy.deepcopy(base)
            jp.update(code="JP", paths=["jp.txt"])
            na.update(code="NA", paths=["missing.txt"])
            (root / "jp.txt").write_text("ok")
            (root / "countries/catalog.json").write_text(json.dumps({"schema_version": 1,
                "scope_source": "scope.csv", "countries": [jp, na]}))
            self.assertEqual(1, modules.validate(root, "JP")["countries"])
            with self.assertRaisesRegex(ValueError, "missing inventoried"):
                modules.validate(root)
            with self.assertRaisesRegex(ValueError, "unknown country"):
                modules.validate(root, "ZZ")

    def test_paths_reject_escape_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("../secret", "/etc/passwd", "a/../../b", "a\\b"):
                with self.assertRaises(ValueError):
                    modules.safe_path(root, name)
            (root / "outside").symlink_to(root.parent, target_is_directory=True)
            with self.assertRaises(ValueError):
                modules.safe_path(root, "outside/secret")

    def test_release_requires_pinned_commit_and_integrity(self):
        valid = {"schema_version": 1, "country": "JP", "version": "1",
                 "data_schema_version": "1", "source_commit": "a" * 40,
                 "notice_path": "NOTICE.md", "quality_report": "quality.json",
                 "artifacts": [{"path": "JP.json.gz", "url": "https://example.org/JP.json.gz",
                                "size": 10, "sha256": "b" * 64}]}
        modules.validate_release(valid, "JP")
        changes = [("source_commit", "main"), ("country", "NA"), ("artifacts", []),
                   ("notice_path", "../NOTICE.md")]
        for field, value in changes:
            changed = copy.deepcopy(valid)
            changed[field] = value
            with self.assertRaises(ValueError):
                modules.validate_release(changed, "JP")
        for field, value in [("sha256", "bad"), ("size", -1), ("size", True),
                             ("url", "http://example.org/a"), ("path", "../a")]:
            changed = copy.deepcopy(valid)
            changed["artifacts"][0][field] = value
            with self.assertRaises(ValueError):
                modules.validate_release(changed, "JP")


if __name__ == "__main__":
    unittest.main()
