"""Sejong source replay, exact official code/date values and corruption regressions."""
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
SPEC = importlib.util.spec_from_file_location('kr_official_expansion', ROOT / 'scripts/import_kr_official.py')
kr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(kr)
FOLDER = ROOT / 'registries/official/expansions/KR'


def sample(**changes):
    row = dict(zip(kr.SOURCE_COLUMNS, ['36110101200000200181100000', '3611010100', '세종특별자치시',
        '', '반곡동', '', '0', '0899', '0000', '361102000002', '한누리대로', '0', '01811', '00000',
        '3611055600', '반곡동', '00123', '', '20240229', '0', '', '', '원문 건물명', '']))
    row.update(changes)
    return row


def source(rows):
    return ''.join('|'.join(row[c] for c in kr.SOURCE_COLUMNS) + '\r\n' for row in rows).encode('cp949')


def read_records(plain):
    return list(csv.DictReader(io.StringIO(plain.decode('utf-8'))))


class KoreaOfficialExpansionTests(unittest.TestCase):
    def test_actual_snapshot_all_rows_replay_and_explicit_pilot(self):
        raw = gzip.decompress((FOLDER / kr.RAW_NAME).read_bytes())
        self.assertEqual(kr.MEMBER_RECEIPT['sha256'], hashlib.sha256(raw).hexdigest())
        result = kr.verify(FOLDER)
        self.assertEqual('passed', result['status'])
        self.assertEqual(27966, result['rows'])
        self.assertEqual(1139, result['counts']['unique_road_codes'])
        self.assertEqual(153, result['counts']['unique_postcodes'])
        self.assertFalse(result['national_completeness_verified'])
        self.assertFalse(result['deliverability_verified'])
        self.assertIsNone(result['freshness_verified'])
        self.assertIn('Sejong', result['scope'])

    def test_all_24_fields_and_leading_zero_numbers_remain_source_strings(self):
        original = sample()
        plain, counts = kr.transform(source([original]))
        row = read_records(plain)[0]
        self.assertEqual(original, {c: row[c] for c in kr.SOURCE_COLUMNS})
        self.assertEqual('kr:sejong-address:36110101200000200181100000', row['record_id'])
        self.assertEqual('00123', row['postcode'])
        self.assertEqual('01811', row['building_main_number'])
        self.assertEqual('00000', row['building_sub_number'])
        self.assertEqual('0899', row['lot_main_number'])
        self.assertEqual('0000', row['lot_sub_number'])
        self.assertEqual(1, counts['source_observations'])

    def test_missing_english_and_deletion_date_are_not_invented(self):
        plain, counts = kr.transform(source([sample(effective_date='')]))
        row = read_records(plain)[0]
        self.assertNotIn('road_name_en', row)
        self.assertNotIn('abolition_date', row)
        self.assertEqual('', row['effective_date'])
        self.assertEqual(1, counts['rows_without_effective_date'])
        self.assertNotEqual(row['building_register_name'], row['local_building_name'])

    def test_multiple_addresses_same_road_and_duplicate_official_id_semantics(self):
        plain, counts = kr.transform(source([sample(), sample(address_id='36110101200000200182000000',
                                                              building_main_number='1820')]))
        rows = read_records(plain)
        self.assertEqual(2, len({row['record_id'] for row in rows}))
        self.assertEqual(1, counts['unique_road_codes'])
        self.assertEqual(['1', '2'], [row['source_row'] for row in rows])
        with self.assertRaisesRegex(ValueError, 'duplicate official'):
            kr.transform(source([sample(), sample()]))

    def test_official_air_water_and_deletion_change_values_are_preserved(self):
        for flag in ['2', '3']:
            original = sample(basement_flag=flag, change_reason='63', effective_date='20241001',
                              previous_road_address='이전주소 원문')
            plain, counts = kr.transform(source([original]))
            row = read_records(plain)[0]
            self.assertEqual(original, {c: row[c] for c in kr.SOURCE_COLUMNS})
            self.assertEqual(1, counts['rows_with_deletion_change_reason'])

    def test_wrong_region_dates_code_width_and_schema_are_rejected(self):
        for changes in ({'effective_date': '20230229'}, {'effective_date': '2024-10-01'},
                        {'address_id': '36110'}, {'postcode': '1234'}, {'road_code': '3.61102e11'},
                        {'province_ko': '서울특별시'}, {'change_reason': '99'}, {'basement_flag': '4'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                kr.transform(source([sample(**changes)]))
        with self.assertRaisesRegex(ValueError, '24 fields'):
            kr.transform(source([sample(remarks='unexpected|delimiter')]))

    def build_fixture(self, root):
        raw = root / 'source.txt.gz'
        raw.write_bytes(gzip.compress(source([sample()]), mtime=0))
        output = root / 'result'
        kr.build(raw, output, retrieved_at='2026-11-04T19:37:03Z')
        return raw, output

    def test_tampered_payload_is_rejected_even_after_rehashing_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, folder = self.build_fixture(Path(temporary))
            plain = gzip.decompress((folder / 'records.csv.gz').read_bytes())
            changed = plain.replace(b'00123', b'00124')
            payload = gzip.compress(changed, mtime=0)
            (folder / 'records.csv.gz').write_bytes(payload)
            coverage = json.loads((folder / 'coverage.json').read_text())
            coverage['files']['records.csv.gz'].update(bytes=len(payload),
                sha256=kr.digest(payload), uncompressed_sha256=kr.digest(changed))
            (folder / 'coverage.json').write_text(json.dumps(coverage))
            with self.assertRaisesRegex(ValueError, 'source row replay mismatch'):
                kr.verify(folder)

    def test_raw_corruption_quality_claim_and_wrong_license_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            raw, folder = self.build_fixture(Path(temporary))
            (folder / kr.RAW_NAME).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                kr.verify(folder)
            (folder / kr.RAW_NAME).write_bytes(raw.read_bytes())
            sources = json.loads((folder / 'sources.json').read_text())
            original = (folder / 'sources.json').read_bytes()
            sources['sources'][kr.SOURCE_ID]['license'] = 'fabricated license'
            (folder / 'sources.json').write_text(json.dumps(sources))
            with self.assertRaisesRegex(ValueError, 'terms changed'):
                kr.verify(folder)
            (folder / 'sources.json').write_bytes(original)
            coverage = json.loads((folder / 'coverage.json').read_text())
            coverage['claims']['deliverability_verified'] = True
            (folder / 'coverage.json').write_text(json.dumps(coverage))
            with self.assertRaisesRegex(ValueError, 'quality claim'):
                kr.verify(folder)

    def test_repeat_build_is_deterministic_and_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw, folder = self.build_fixture(root)
            other = root / 'other'
            kr.build(raw, other, retrieved_at='2026-11-04T19:37:03Z')
            for name in ['records.csv.gz', 'coverage.json', 'sources.json', kr.RAW_NAME]:
                self.assertEqual((folder / name).read_bytes(), (other / name).read_bytes())
            with self.assertRaisesRegex(ValueError, 'new directory'):
                kr.build(raw, folder)


if __name__ == '__main__':
    unittest.main()
