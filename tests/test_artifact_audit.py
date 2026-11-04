"""Saved archive claims do not substitute for locally verified payloads."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location('artifact_audit', Path(__file__).resolve().parents[1] / 'scripts/artifact_audit.py')
audit_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit_module)


class ArtifactAuditTests(unittest.TestCase):
    def fixture(self, root, name='data.zip'):
        manifest = root / 'releases/hierarchy/demo/archive.json'
        manifest.parent.mkdir(parents=True)
        data = b'original'
        manifest.write_text(json.dumps({'archives': [{'name': name, 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}]}))
        return data, [manifest.relative_to(root).as_posix()]

    def test_reference_is_not_payload_or_external_loss_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, tracked = self.fixture(root)
            report = audit_module.audit(root, tracked_paths=tracked)
            self.assertEqual('referenced_not_local', report['archives'][0]['availability'])
            self.assertEqual('not_checked', report['archives'][0]['external_storage_status'])
            self.assertFalse(report['data_completeness_verified'])

    def test_payload_is_hashed_and_corruption_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data, tracked = self.fixture(root)
            (root / 'data.zip').write_bytes(data)
            tracked += ['data.zip']
            self.assertEqual('available_verified', audit_module.audit(root, tracked_paths=tracked)['archives'][0]['availability'])
            (root / 'data.zip').write_bytes(b'changed!')
            self.assertEqual('mismatch', audit_module.audit(root, tracked_paths=tracked)['status'])

    def test_untrusted_archive_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            _, tracked = self.fixture(root, '../data.zip')
            with self.assertRaises(ValueError):
                audit_module.audit(root, tracked_paths=tracked)


if __name__ == '__main__':
    unittest.main()
