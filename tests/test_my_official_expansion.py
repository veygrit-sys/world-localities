"""Malaysia source replay, ambiguity preservation and corruption regressions."""
import csv
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('my_official_expansion', ROOT / 'scripts/import_my_official.py')
my = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(my)
FOLDER = ROOT / 'registries/official/expansions/MY'


class MalaysiaOfficialExpansionTests(unittest.TestCase):
    def test_actual_snapshot_all_rows_replay(self):
        result = my.verify(FOLDER)
        self.assertEqual('passed', result['status'])
        self.assertEqual(2932, result['rows'])
        self.assertEqual(2930, result['counts']['unique_postcodes'])
        self.assertEqual(2, result['counts']['postcodes_with_multiple_raw_associations'])
        self.assertFalse(result['national_completeness_verified'])
        self.assertFalse(result['deliverability_verified'])

    def test_real_leading_zero_and_multiple_city_postcode_survive(self):
        rows = my.transform((FOLDER / 'sources/postcodes.csv').read_bytes())
        self.assertTrue(any(r['postcode'] == '01000' for r in rows))
        self.assertEqual({'Shah Alam', 'Sungai Buloh'},
                         {r['city'] for r in rows if r['postcode'] == '40160'})
        self.assertEqual({'Negeri Sembilan', 'Negeri Sembilan  '},
                         {r['state'] for r in rows if r['postcode'] == '71000'})
        self.assertEqual(2932, len({r['observation_id'] for r in rows}))

    def test_synthetic_fixture_retains_duplicate_source_rows(self):
        rows = my.transform(b'state,city,postcode\nExample,Alpha,00001\nExample,Alpha,00001\nExample,Beta,00001\n')
        self.assertEqual(3, len(rows))
        self.assertEqual(2, len({r['association_id'] for r in rows}))
        self.assertEqual(3, len({r['observation_id'] for r in rows}))
        self.assertEqual('00001', rows[0]['postcode'])
        self.assertEqual(['1', '2', '3'], [r['source_row'] for r in rows])

    def test_invalid_postcodes_headers_and_empty_names_fail(self):
        for raw in (b'state,city,postcode\nExample,Alpha,1000\n',
                    b'state,city,postcode\nExample,Alpha,100000\n',
                    b'city,state,postcode\nAlpha,Example,00001\n',
                    b'state,city,postcode\nExample,,00001\n',
                    b'state,city,postcode\nExample,Alpha,00001,extra\n'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                my.transform(raw)

    def test_changed_payload_rejected_even_after_rehashing_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.csv'
            source.write_bytes(b'state,city,postcode\nExample,Alpha,00001\n')
            output = root / 'result'
            my.build(source, output, retrieved_at='2026-11-04T00:00:00+00:00')
            rows = list(csv.DictReader(io.StringIO(gzip.decompress((output / 'records.csv.gz').read_bytes()).decode())))
            rows[0]['city'] = 'Fabricated'
            plain = my.csv_bytes(rows)
            compressed = gzip.compress(plain, mtime=0)
            (output / 'records.csv.gz').write_bytes(compressed)
            coverage = json.loads((output / 'coverage.json').read_text())
            coverage['files']['records.csv.gz'].update(bytes=len(compressed),
                sha256=hashlib.sha256(compressed).hexdigest(), uncompressed_sha256=hashlib.sha256(plain).hexdigest())
            (output / 'coverage.json').write_text(json.dumps(coverage))
            with self.assertRaisesRegex(ValueError, 'source row replay mismatch'):
                my.verify(output)

    def test_corrupted_raw_source_and_quality_inflation_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.csv'
            source.write_bytes(b'state,city,postcode\nExample,Alpha,00001\n')
            output = root / 'result'
            my.build(source, output)
            raw_path = output / 'sources/postcodes.csv'
            original = raw_path.read_bytes()
            raw_path.write_bytes(original + b'bad')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                my.verify(output)
            raw_path.write_bytes(original)
            coverage = json.loads((output / 'coverage.json').read_text())
            coverage['claims']['deliverability_verified'] = True
            (output / 'coverage.json').write_text(json.dumps(coverage))
            with self.assertRaisesRegex(ValueError, 'quality claim'):
                my.verify(output)

    def test_repeat_builds_same_source_produce_same_payload_and_do_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.csv'
            source.write_bytes(b'state,city,postcode\nExample,Alpha,00001\n')
            a, b = root / 'a', root / 'b'
            my.build(source, a, retrieved_at='2026-11-04T00:00:00+00:00')
            my.build(source, b, retrieved_at='2026-11-04T00:00:00+00:00')
            self.assertEqual((a / 'records.csv.gz').read_bytes(), (b / 'records.csv.gz').read_bytes())
            self.assertEqual(source.read_bytes(), (a / 'sources/postcodes.csv').read_bytes())
            with self.assertRaisesRegex(ValueError, 'new directory'):
                my.build(source, a)


if __name__ == '__main__':
    unittest.main()
