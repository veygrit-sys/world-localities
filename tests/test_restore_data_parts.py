import hashlib
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import restore_data_parts as parts


class RestoreDataPartsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); self.payload = b'original-source\x00\n' * 1000
        self.manifest = {'format': 'zip-wrapped-byte-parts-v1', 'archive_bytes': len(self.payload),
                         'archive_sha256': hashlib.sha256(self.payload).hexdigest(), 'parts': []}
        for number, chunk in enumerate([self.payload[:7000], self.payload[7000:]], 1):
            name = str(number) + '.zip'; member = 'source.' + str(number); path = self.root / name
            with ZipFile(path, 'w') as archive: archive.writestr(member, chunk)
            self.manifest['parts'].append({'file': name, 'bytes': path.stat().st_size, 'sha256': parts.digest(path),
                                          'member': member, 'member_bytes': len(chunk)})

    def test_byte_exact_reconstruction(self):
        report = parts.restore(self.manifest, self.root, self.root / 'restored')
        self.assertEqual((self.root / 'restored').read_bytes(), self.payload)
        self.assertEqual(report['status'], 'RESTORED_HASH_VERIFIED')

    def test_changed_or_reordered_parts_never_publish_output(self):
        self.manifest['parts'].reverse()
        with self.assertRaisesRegex(ValueError, 'Restored file'):
            parts.restore(self.manifest, self.root, self.root / 'restored')
        self.assertFalse((self.root / 'restored').exists())
        self.manifest['parts'].reverse(); (self.root / '1.zip').write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'Part byte count'):
            parts.restore(self.manifest, self.root, self.root / 'restored')

    def test_paths_and_existing_outputs_are_protected(self):
        (self.root / 'restored').write_bytes(b'keep')
        with self.assertRaisesRegex(ValueError, 'new restored'):
            parts.restore(self.manifest, self.root, self.root / 'restored')
        self.assertEqual((self.root / 'restored').read_bytes(), b'keep')
        self.manifest['parts'][0]['file'] = '../elsewhere'
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            parts.restore(self.manifest, self.root, self.root / 'another')


if __name__ == '__main__': unittest.main()
