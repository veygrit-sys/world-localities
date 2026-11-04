import hashlib
import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('hierarchy_snapshot', Path(__file__).resolve().parents[1] / 'scripts/hierarchy_snapshot.py')
snapshot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot)


class SnapshotIntegrity(unittest.TestCase):
    def pin(self, root, members, name='source.zip'):
        p = root / name
        with zipfile.ZipFile(p, 'w') as z:
            for member, value in members:
                z.writestr(member, value)
        return {'name': name, 'bytes': p.stat().st_size,
                'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                'files': len(members), 'roots': ['snapshot']}

    def test_restore_preserves_bytes_and_zeroes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); pin = self.pin(root, [('snapshot/row', b'0001-A\n')])
            report = snapshot.restore({'archives': [pin]}, root, root / 'new')
            self.assertEqual((root / 'new/snapshot/row').read_bytes(), b'0001-A\n')
            self.assertFalse(report['world_complete'])

    def test_corruption_rejected_before_target_created(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); pin = self.pin(root, [('snapshot/row', 'valid')])
            (root / pin['name']).write_bytes(b'bad')
            with self.assertRaises(ValueError): snapshot.restore({'archives': [pin]}, root, root / 'new')
            self.assertFalse((root / 'new').exists())

    def test_existing_target_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); marker = root / 'keep'; marker.write_text('keep')
            with self.assertRaises(ValueError): snapshot.restore({'archives': []}, root, root)
            self.assertEqual(marker.read_text(), 'keep')

    def test_traversal_absolute_windows_and_repeated_separators_rejected(self):
        for name in ['snapshot/../../outside', '/snapshot/file', 'snapshot\\file', 'snapshot/C:/file', 'snapshot//file']:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp); pin = self.pin(root, [(name, 'bad')])
                with self.assertRaises(ValueError): snapshot.restore({'archives': [pin]}, root, root / 'new')
                self.assertFalse((root / 'new').exists())

    def test_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); info = zipfile.ZipInfo('snapshot/link'); info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            pin = self.pin(root, [(info, '../../outside')])
            with self.assertRaises(ValueError): snapshot.verify({'archives': [pin]}, root)

    def test_cross_archive_duplicate_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); a = self.pin(root, [('snapshot/row', 'one')], 'a.zip'); b = self.pin(root, [('snapshot/row', 'two')], 'b.zip')
            with self.assertRaises(ValueError): snapshot.restore({'archives': [a, b]}, root, root / 'new')
            self.assertFalse((root / 'new').exists())

    def test_missing_part_blocks_entire_restore(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); a = self.pin(root, [('snapshot/one', 'one')], 'a.zip'); b = self.pin(root, [('snapshot/two', 'two')], 'b.zip')
            (root / 'b.zip').unlink()
            with self.assertRaises(ValueError): snapshot.restore({'archives': [a, b]}, root, root / 'new')
            self.assertFalse((root / 'new').exists())


if __name__ == '__main__': unittest.main()
