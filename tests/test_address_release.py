"""Offline regressions for verified, non-destructive address release imports."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location("address_release", Path(__file__).resolve().parents[1] / "scripts/address_release.py")
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


def record(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


class AddressReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.code = self.root / "Code.zip"
        self.parts = self.root / "parts"
        self.parts.mkdir()
        self.target = self.root / "target"
        self.lock = self.root / "lock.json"
        self.code_data = b"# test fixture\n"
        self.raw_data = b"\x00binary\xff\x01"
        self.path = "address-points/query.py"
        self.raw_path = "address-points/sources/EASTASIA/XX/fixture.parquet"
        self.pack()

    def pack(self, mutate=None, mutate_archive=None, previous=None, data=True):
        archives = []
        payloads = [{"path": self.path, **record(self.code_data), "expected_previous_sha256": previous,
                     "storage": {"kind": "overlay", "path": "overlay/" + self.path}}]
        if data:
            part = self.parts / "Data_01.zip"
            member = "payload/" + self.raw_path
            with zipfile.ZipFile(part, "w") as archive:
                archive.writestr(member, self.raw_data)
            archives.append({"name": part.name, **record(part.read_bytes())})
            payloads.append({"path": self.raw_path, **record(self.raw_data), "expected_previous_sha256": None,
                             "storage": {"kind": "parts", "fragments": [{"archive": part.name, "member": member, **record(self.raw_data)}]}})
        manifest = {"schema_version": 1, "release": "fixture", "payloads": payloads, "data_archives": archives}
        if mutate:
            mutate(manifest)
        with zipfile.ZipFile(self.code, "w") as archive:
            archive.writestr("MANIFEST.json", json.dumps(manifest))
            archive.writestr("overlay/" + self.path, self.code_data)
            if mutate_archive:
                mutate_archive(archive)
        lock = {"schema_version": 1, "releases": [{"release": "fixture", "manifest": "MANIFEST.json",
                "code": {"name": self.code.name, **record(self.code.read_bytes())}, "data_archives": archives}]}
        self.lock.write_text(json.dumps(lock), encoding="utf-8")

    def verify(self, full=False):
        return M.verify(self.code, self.lock, self.parts if full else None)

    def apply(self):
        return M.apply(self.code, self.parts, self.target, self.lock)

    def test_code_only_reports_unverified_data_without_writes(self):
        result = self.verify()
        self.assertEqual(result["status"], "VERIFIED_CODE_ONLY")
        self.assertEqual(result["verified_payloads"], 1)
        self.assertEqual(result["unverified_data_payloads"], 1)
        self.assertFalse(result["delivery_verified"])
        self.assertFalse(self.target.exists())

    def test_full_verification_reads_fragments(self):
        result = self.verify(full=True)
        self.assertEqual(result["status"], "VERIFIED_PAYLOADS")
        self.assertEqual(result["verified_payloads"], 2)
        self.assertEqual(result["data_archives_verified"], 1)

    def test_binary_restore_and_idempotency(self):
        self.assertEqual(self.apply()["installed"], 2)
        self.assertEqual((self.target / self.raw_path).read_bytes(), self.raw_data)
        self.assertEqual(self.apply()["unchanged"], 2)
        self.assertFalse((self.target / ".address-release.lock").exists())

    def test_unknown_edit_refused_before_other_payload_writes(self):
        path = self.target / self.path
        path.parent.mkdir(parents=True)
        path.write_bytes(b"user edit")
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual(path.read_bytes(), b"user edit")
        self.assertFalse((self.target / self.raw_path).exists())

    def test_known_previous_version_can_be_updated(self):
        previous = b"previous version"
        self.pack(previous=record(previous)["sha256"])
        path = self.target / self.path
        path.parent.mkdir(parents=True)
        path.write_bytes(previous)
        result = self.apply()
        self.assertEqual(result["updated"], 1)
        self.assertEqual(path.read_bytes(), self.code_data)

    def test_code_archive_tampering_refused(self):
        with self.code.open("ab") as stream:
            stream.write(b"tamper")
        with self.assertRaises(ValueError):
            self.verify()

    def test_data_archive_tampering_refused(self):
        (self.parts / "Data_01.zip").write_bytes(b"tamper")
        with self.assertRaises(ValueError):
            self.apply()
        self.assertFalse(self.target.exists())

    def test_wrong_payload_digest_refused_before_install(self):
        def mutate(manifest):
            manifest["payloads"][1]["sha256"] = "0" * 64
        self.pack(mutate=mutate)
        with self.assertRaises(ValueError):
            self.apply()
        self.assertFalse((self.target / self.path).exists())

    def test_wrong_fragment_digest_refused(self):
        def mutate(manifest):
            manifest["payloads"][1]["storage"]["fragments"][0]["sha256"] = "0" * 64
        self.pack(mutate=mutate)
        with self.assertRaises(ValueError):
            self.verify(full=True)

    def test_unsafe_paths_are_rejected(self):
        for name in ("../x", "/x", "a/../x", "a\\x", "C:/x", "a//x", "a/./x", "a/CON.txt", "a/x.", "a/x ", "a/\x00"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                M.relative_name(name)

    def test_payload_scope_is_restricted(self):
        def mutate(manifest):
            manifest["payloads"][0]["path"] = ".github/workflows/unwanted.yml"
        self.pack(mutate=mutate)
        with self.assertRaises(ValueError):
            self.verify()

    def test_duplicate_destination_refused(self):
        self.pack(mutate=lambda m: m["payloads"].append(m["payloads"][0].copy()))
        with self.assertRaises(ValueError):
            self.verify()

    def test_duplicate_zip_member_refused(self):
        def extra(archive):
            archive.writestr("OVERLAY/address-points/query.py", b"duplicate")
        self.pack(mutate_archive=extra)
        with self.assertRaises(ValueError):
            self.verify()

    def test_symlink_zip_member_refused(self):
        def extra(archive):
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = 0o120777 << 16
            archive.writestr(info, "../outside")
        self.pack(mutate_archive=extra)
        with self.assertRaises(ValueError):
            self.verify()

    def test_symlink_target_refused(self):
        outside = self.root / "outside"
        outside.mkdir()
        self.target.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual(list(outside.iterdir()), [])

    def test_symlink_child_refused(self):
        self.target.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        (self.target / "address-points").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual(list(outside.iterdir()), [])

    def test_existing_lock_is_not_removed(self):
        self.target.mkdir()
        lock = self.target / ".address-release.lock"
        lock.write_text("other process")
        with self.assertRaises(FileExistsError):
            self.apply()
        self.assertEqual(lock.read_text(), "other process")

    def test_unknown_schema_refused(self):
        self.pack(mutate=lambda m: m.update(schema_version=2))
        with self.assertRaises(ValueError):
            self.verify()

    def test_missing_data_is_not_reported_as_verified(self):
        (self.parts / "Data_01.zip").unlink()
        with self.assertRaises(ValueError):
            self.verify(full=True)

    def test_unknown_storage_refused(self):
        self.pack(mutate=lambda m: m["payloads"][0]["storage"].update(kind="network"))
        with self.assertRaises(ValueError):
            self.verify()

    def test_empty_file_supported(self):
        self.code_data = b""
        self.pack(data=False)
        self.assertEqual(self.verify()["verified_payloads"], 1)
        self.assertEqual(self.apply()["installed"], 1)
        self.assertEqual((self.target / self.path).read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()
