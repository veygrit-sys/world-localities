"""Offline acceptance and corruption regressions for the preserved country snapshots."""
import csv
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('americas_validator', ROOT/'scripts/verify_americas_snapshots.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class AmericasSnapshotTests(unittest.TestCase):
    def test_complete_preserved_snapshots(self):
        report = validator.verify(ROOT)
        self.assertEqual(report['total_locality_rows'], 81847)
        self.assertEqual(report['total_anchor_rows'], 3640)

    def test_byte_corruption_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mapping = validator.read_json(ROOT/'official-registry/americas-provenance/source-map.json')
            first = mapping['files'][0]
            metadata = root/'official-registry/americas-provenance/source-map.json'
            metadata.parent.mkdir(parents=True)
            metadata.write_text(json.dumps(mapping), encoding='utf-8')
            path = root/first['destination_path']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT/first['destination_path']).read_bytes()+b'corrupt')
            with self.assertRaisesRegex(ValueError, 'byte length mismatch'):
                validator.verify_source_map(root)

    def test_incorrect_parent_rejected_even_with_updated_file_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp)/'official-registry'
            shutil.copytree(ROOT/'official-registry/BR', registry/'BR')
            path = registry/'BR/BR-DF.csv'
            with path.open(encoding='utf-8', newline='') as handle:
                reader = csv.DictReader(handle)
                columns, rows = reader.fieldnames, list(reader)
            rows[0]['parent_id'] = 'country:BR'
            with path.open('w', encoding='utf-8', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=columns, lineterminator='\n')
                writer.writeheader(); writer.writerows(rows)
            manifest_path = registry/'BR/manifest.json'
            manifest = validator.read_json(manifest_path)
            manifest['sha256']['BR-DF.csv'] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest_path.write_text(json.dumps(manifest), encoding='utf-8')
            schema = validator.read_json(ROOT/'official-registry/americas-snapshot-schema.json')
            with self.assertRaisesRegex(ValueError, 'BR: wrong parent'):
                validator.verify_country(registry, 'BR', schema)

    def test_completeness_claim_regression_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = Path(tmp)/'official-registry'
            shutil.copytree(ROOT/'official-registry/CA', registry/'CA')
            path = registry/'CA/manifest.json'
            manifest = validator.read_json(path)
            manifest['claims']['deliverability_verified'] = True
            path.write_text(json.dumps(manifest), encoding='utf-8')
            schema = validator.read_json(ROOT/'official-registry/americas-snapshot-schema.json')
            with self.assertRaisesRegex(ValueError, 'unexpected completeness claim'):
                validator.verify_country(registry, 'CA', schema)


if __name__ == '__main__':
    unittest.main()
