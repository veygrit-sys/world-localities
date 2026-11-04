"""Offline bundle corruption, path and no-overwrite regression tests."""
import importlib.util
import json
from pathlib import Path
import stat
import tempfile
import unittest
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("country_bundle", ROOT / "scripts/country_bundle.py")
bundle = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bundle)


def fixture_manifest(payloads):
    return {"schema_version": 1, "country": "JP", "bundle_type": "source_qualified_data_snapshot",
            "source_commit": "a" * 40,
            "quality": {"national_completeness_verified": False, "upstream_freshness_verified": False,
                        "deliverability_verified": False},
            "notice_paths": ["NOTICE.md"], "dependency_paths": ["data.json"],
            "files": [{"path": name, "size": len(data), "sha256": bundle.sha256(data),
                       "git_blob_sha1": bundle.git_blob(data)} for name, data in sorted(payloads.items())]}


def write_fixture(path, payloads=None, manifest=None, extra=None):
    payloads = payloads or {"NOTICE.md": b"source attribution", "data.json": b'{"country":"JP"}'}
    manifest = manifest or fixture_manifest(payloads)
    with zipfile.ZipFile(path, "w") as archive:
        bundle.write_member(archive, bundle.MANIFEST, bundle.json_bytes(manifest))
        for name, data in payloads.items():
            bundle.write_member(archive, "payload/" + name, data)
        if extra:
            for name, data, mode in extra:
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = mode << 16
                archive.writestr(info, data)
    return manifest


class BundleTests(unittest.TestCase):
    def test_jp_build_is_deterministic_and_restores_pinned_source_bytes(self):
        with tempfile.TemporaryDirectory(prefix="jp-bundle-regression-") as directory:
            root = Path(directory)
            first = bundle.build(root / "first.zip")
            second = bundle.build(root / "second.zip")
            self.assertEqual(first["sha256"], second["sha256"])
            output = root / "restored"
            bundle.restore(root / "first.zip", output)
            manifest = json.loads((output / bundle.MANIFEST).read_text())
            self.assertEqual(22, len(manifest["files"]))
            for entry in manifest["files"]:
                self.assertEqual((ROOT / entry["path"]).read_bytes(), (output / entry["path"]).read_bytes())

    def test_verify_restore_byte_identical_and_never_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "data.zip"
            manifest = write_fixture(source)
            self.assertEqual(2, bundle.verify(source)["file_count"])
            output = root / "restore"
            bundle.restore(source, output)
            for entry in manifest["files"]:
                self.assertEqual(entry["sha256"], bundle.sha256((output / entry["path"]).read_bytes()))
            with self.assertRaisesRegex(ValueError, "already exists"):
                bundle.restore(source, output)

    def test_content_corruption_is_rejected_before_restore_creates_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = {"NOTICE.md": b"source attribution", "data.json": b"expected"}
            manifest = fixture_manifest(data)
            data["data.json"] = b"tampered"
            path = root / "bad.zip"
            write_fixture(path, data, manifest)
            output = root / "restore"
            with self.assertRaisesRegex(ValueError, "payload hash mismatch"):
                bundle.restore(path, output)
            self.assertFalse(output.exists())

    def test_path_traversal_and_windows_paths_are_rejected(self):
        for name in ("../escape", "/absolute", "a/../../b", "C:/drive", "a\\b", "a//b", "./file", "nul\0file"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                bundle.safe_relative(name)

    def test_duplicate_archive_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.zip"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                write_fixture(path, extra=[("payload/data.json", b"duplicate", stat.S_IFREG | 0o644)])
            with self.assertRaisesRegex(ValueError, "duplicate bundle member"):
                bundle.verify(path)

    def test_symlink_member_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "symlink.zip"
            write_fixture(path, extra=[("payload/symlink", b"../../escape", stat.S_IFLNK | 0o777)])
            with self.assertRaisesRegex(ValueError, "nonregular bundle member"):
                bundle.verify(path)

    def test_missing_notice_and_unpinned_source_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for mutation in (lambda x: x.update(notice_paths=["missing.md"]),
                             lambda x: x.update(source_commit="main"),
                             lambda x: x["quality"].update(deliverability_verified=True)):
                manifest = fixture_manifest({"NOTICE.md": b"source attribution", "data.json": b'{"country":"JP"}'})
                mutation(manifest)
                path = root / "invalid.zip"
                write_fixture(path, manifest=manifest)
                with self.assertRaises(ValueError):
                    bundle.verify(path)

    def test_file_directory_collision_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collision.zip"
            write_fixture(path, payloads={"NOTICE.md": b"notice", "data.json": b"a", "a": b"one", "a/b": b"two"})
            with self.assertRaisesRegex(ValueError, "path collision"):
                bundle.verify(path)

    def test_output_inside_repository_and_preexisting_output_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            bundle.outside_repository(ROOT / "uncreated-pilot-output.zip")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "existing"
            path.write_text("retain")
            with self.assertRaisesRegex(ValueError, "already exists"):
                bundle.outside_repository(path)
            self.assertEqual("retain", path.read_text())


if __name__ == "__main__":
    unittest.main()
