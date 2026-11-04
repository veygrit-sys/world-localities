import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('asia_package', Path(__file__).resolve().parents[1] / 'asia-registry/package.py')
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


class AsiaPackageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        country = self.root / 'countries' / 'XX'
        country.mkdir(parents=True)
        payload = bytes(range(256)) * 3
        (country / 'entities.csv.gz').write_bytes(payload)
        (country / 'admin1.csv').write_text('id,name\n1,Example\n')
        (country / 'metadata.json').write_text(json.dumps({'files': {'entities.csv.gz': {'sha256': PACKAGE.digest(payload), 'rows': 1}}}))
        (self.root / 'NOTICE.md').write_text('Synthetic fixture, not geographic evidence.\n')

    def test_split_roundtrip_preserves_exact_bytes(self):
        row = PACKAGE.pack_country('XX', root=self.root, volume_bytes=256)
        self.assertGreater(len(row['parts']), 1)
        self.assertTrue(all(p['bytes'] <= 256 for p in row['parts']))
        destination = PACKAGE.unpack_record(row, root=self.root, destination_root=self.root / 'restored')
        for name in PACKAGE.COUNTRY_FILES:
            self.assertEqual((destination / name).read_bytes(), (self.root / 'countries/XX' / name).read_bytes())

    def test_changed_volume_is_rejected(self):
        row = PACKAGE.pack_country('XX', root=self.root, volume_bytes=256)
        (self.root / row['parts'][0]['path']).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            PACKAGE.unpack_record(row, root=self.root)

    def test_reordered_or_traversal_volumes_are_rejected(self):
        row = PACKAGE.pack_country('XX', root=self.root, volume_bytes=256)
        for altered in [list(reversed(row['parts'])), [dict(row['parts'][0], path='../escape')]]:
            bad = copy.deepcopy(row)
            bad['parts'] = altered
            with self.assertRaisesRegex(ValueError, 'path'):
                PACKAGE.unpack_record(bad, root=self.root)

    def test_existing_different_local_data_is_preserved(self):
        row = PACKAGE.pack_country('XX', root=self.root)
        path = self.root / 'countries/XX/admin1.csv'
        path.write_text('User changes\n')
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            PACKAGE.unpack_record(row, root=self.root)
        self.assertEqual(path.read_text(), 'User changes\n')

    def test_legacy_single_zip_manifest_is_supported(self):
        row = PACKAGE.pack_country('XX', root=self.root)
        del row['parts']
        self.assertEqual(PACKAGE.unpack_record(row, root=self.root).name, 'XX')


if __name__ == '__main__':
    unittest.main()
