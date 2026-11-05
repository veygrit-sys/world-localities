"""Purely synthetic tests: these do not claim official national source ingestion."""
from pathlib import Path
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import europe_six_official as official


class EuropeanSixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.payload = 'ID;Street;House;Post;X\n0007;Žalių g.;02A;01234;499000.1\n'
        self.file = self.root / 'example.csv'
        self.file.write_text(self.payload, encoding='utf-8')
        self.pin = {'country': 'LT', 'source_id': 'synthetic-test', 'snapshot_date': '2026-11-05',
                    'rights_reviewed': True, 'bytes': self.file.stat().st_size,
                    'sha256': hashlib.sha256(self.file.read_bytes()).hexdigest(),
                    'path': self.file.name, 'format': 'csv', 'kind': 'address',
                    'delimiter': ';', 'coordinate_crs': 'unknown',
                    'fields': {'id': 'ID', 'street': 'Street', 'number': 'House',
                               'postcode': 'Post', 'x': 'X'}}

    def test_catalog_all_six_and_no_false_completion(self):
        item = official.catalog()
        self.assertEqual(set(item['countries']), official.COUNTRIES)
        self.assertTrue(all(not c['national_completeness_verified'] for c in item['countries'].values()))
        self.assertTrue(all(not c['deliverability_verified'] for c in item['countries'].values()))

    def test_csv_preserves_leading_zeros_and_unicode(self):
        output = self.root / 'normalized.jsonl'
        report = official.normalize(self.pin, self.root, output)
        row = json.loads(output.read_text())
        self.assertEqual(row['source_record_id'], '0007')
        self.assertEqual(row['properties']['number'], '02A')
        self.assertEqual(row['properties']['postcode'], '01234')
        self.assertEqual(row['properties']['street'], 'Žalių g.')
        self.assertEqual(report['records'], 1)
        self.assertFalse(report['deliverability_verified'])

    def test_rejects_tampered_bytes(self):
        self.file.write_bytes(self.file.read_bytes() + b'X')
        with self.assertRaises(ValueError):
            official.normalize(self.pin, self.root, self.root / 'out.jsonl')

    def test_rejects_unreviewed_licence(self):
        self.pin['rights_reviewed'] = False
        with self.assertRaisesRegex(ValueError, 'Usage rights'):
            official.verify_pin(self.pin, self.root)

    def test_rejects_path_escape(self):
        self.pin['path'] = '../example.csv'
        with self.assertRaises(ValueError):
            official.verify_pin(self.pin, self.root)

    def test_duplicate_id_fails_without_output(self):
        self.file.write_text(self.payload + '0007;Other;4;99999;1\n', encoding='utf-8')
        self.pin['bytes'] = self.file.stat().st_size
        self.pin['sha256'] = hashlib.sha256(self.file.read_bytes()).hexdigest()
        output = self.root / 'out.jsonl'
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            official.normalize(self.pin, self.root, output)
        self.assertFalse(output.exists())
        self.assertFalse((self.root / 'out.jsonl.partial').exists())

    def test_missing_approved_mapping_fails(self):
        self.pin['fields']['locality'] = 'MISSING'
        with self.assertRaisesRegex(ValueError, 'Missing approved source'):
            official.normalize(self.pin, self.root, self.root / 'out.jsonl')

    def test_zip_csv_selected_member(self):
        package = self.root / 'a.zip'
        with zipfile.ZipFile(package, 'w') as z:
            z.writestr('data/address.csv', self.payload)
        self.pin.update({'path': package.name, 'format': 'csv_zip', 'member': 'data/address.csv',
                         'bytes': package.stat().st_size,
                         'sha256': hashlib.sha256(package.read_bytes()).hexdigest()})
        self.assertEqual(official.normalize(self.pin, self.root, self.root / 'zip.jsonl')['records'], 1)

    def test_jsonl(self):
        self.file.write_text(json.dumps({'ID': '007', 'Street': 'Ąžuolų', 'House': '6',
                                         'Post': '01000', 'X': '1'}, ensure_ascii=False) + '\n')
        self.pin.update({'format': 'jsonl', 'bytes': self.file.stat().st_size,
                         'sha256': hashlib.sha256(self.file.read_bytes()).hexdigest()})
        self.assertEqual(official.normalize(self.pin, self.root, self.root/'j.jsonl')['records'], 1)

    def test_gml_explicit_selector_and_leaf_fields(self):
        self.file.write_text('<root xmlns:a="urn:test"><a:Address><a:ID>0003</a:ID>'
                             '<a:Street>Zagreb</a:Street><a:House>1</a:House>'
                             '<a:Post>00100</a:Post><a:X>4</a:X></a:Address></root>')
        self.pin.update({'country': 'HR', 'format': 'gml', 'record_selector': 'Address',
                         'bytes': self.file.stat().st_size,
                         'sha256': hashlib.sha256(self.file.read_bytes()).hexdigest()})
        self.assertEqual(official.normalize(self.pin, self.root, self.root/'g.jsonl')['records'], 1)

    def test_gpkg_preserves_identifiers_not_geometries(self):
        database = self.root / 'addresses.gpkg'
        db = sqlite3.connect(database)
        db.execute('CREATE TABLE gpkg_contents (table_name TEXT)')
        db.execute('INSERT INTO gpkg_contents VALUES (\'address\')')
        db.execute('CREATE TABLE address (ID TEXT, Street TEXT, House TEXT, Post TEXT, X TEXT)')
        db.execute('INSERT INTO address VALUES (\'0002\', \'Åvägen\', \'9\', \'03456\', \'1\')')
        db.commit(); db.close()
        self.pin.update({'country': 'SE', 'path': database.name, 'format': 'gpkg',
                         'record_selector': 'address', 'bytes': database.stat().st_size,
                         'sha256': hashlib.sha256(database.read_bytes()).hexdigest()})
        self.assertEqual(official.normalize(self.pin, self.root, self.root/'p.jsonl')['records'], 1)

    def test_refuse_to_overwrite_output(self):
        out = self.root / 'out.jsonl'; out.write_text('original')
        with self.assertRaisesRegex(ValueError, 'Output exists'):
            official.normalize(self.pin, self.root, out)
        self.assertEqual(out.read_text(), 'original')


if __name__ == '__main__':
    unittest.main()
