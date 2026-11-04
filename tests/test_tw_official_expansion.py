"""Taiwan expansion: exact-source replay and bounded postal label linkage."""
import copy
import csv
import gzip
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('import_tw_official', ROOT / 'scripts/import_tw_official.py')
tw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tw)
FOLDER = ROOT / 'registries/official/expansions/TW'


class TaiwanOfficialExpansionTests(unittest.TestCase):
    def test_actual_canonical_source_replay(self):
        result = tw.verify(FOLDER)
        self.assertEqual(result['rows'], 35798)
        self.assertEqual(result['row_integrity'], 'passed_all_canonical_csv_rows')
        self.assertEqual(tw.sha256((FOLDER / 'records.csv.gz').read_bytes()), 'f2d4eaad86ab52ba75f80b4537fd92f7d7dd3d2f6719ca4568d3f34df9eeae7e')

    def test_bom_and_ideographic_space_are_preserved(self):
        data = tw.read_bytes(FOLDER / tw.RAW_FILE)
        self.assertTrue(data.startswith(b'\xef\xbb\xbf'))
        self.assertIn(b'\r\n', data)
        raw = tw.parse_source(data)
        spaced = [row for row in raw if '\u3000' in row['site_id']]
        self.assertEqual(len(spaced), 1952)
        records = tw.load_csv(tw.read_bytes(FOLDER / 'records.csv.gz'), tw.FIELDS)
        self.assertEqual([row['site_id'] for row in records], [row['site_id'] for row in raw])

    def test_source_scoped_city_and_area_identity(self):
        a = {'city': '臺北市', 'site_id': '臺北市中正區', 'road': '中山路'}
        b = {'city': '新北市', 'site_id': '新北市中和區', 'road': '中山路'}
        self.assertNotEqual(tw.record_id(a), tw.record_id(b))
        self.assertEqual(tw.record_id(a), tw.record_id(dict(a)))

    def test_invalid_delimiter_duplicate_and_parent_are_rejected(self):
        for raw in [b'city;site_id;road\na;b;c\n', 'city,site_id,road\n臺北市,臺北市中正區,中山路\n臺北市,臺北市中正區,中山路\n'.encode(), 'city,site_id,road\n臺北市,新北市中和區,中山路\n'.encode()]:
            with self.assertRaises(ValueError):
                tw.parse_source(raw)

    def test_ambiguous_postal_label_is_not_linked(self):
        source = [{'city': '臺北市', 'site_id': '臺北市中正區', 'road': '中山路'}]
        context = ({'臺北市中正區': {'a', 'b'}}, {}, {'a': {'English'}}, {'a': {'100'}})
        row = tw.normalize(source, context)[0]
        self.assertEqual(row['postal_area_link_status'], 'ambiguous_label')
        self.assertEqual(row['postal_area_id'], '')
        self.assertEqual(row['postal_prefixes'], '')
        self.assertEqual(row['road_en'], '')

    def test_rehashed_fabricated_record_fails_raw_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'TW'
            shutil.copytree(FOLDER, folder)
            records = tw.load_csv(tw.read_bytes(folder / 'records.csv.gz'), tw.FIELDS)
            records[0]['road'] = 'invented'
            path = folder / 'records.csv.gz'
            path.write_bytes(gzip.compress(tw.csv_bytes(records), mtime=0))
            coverage = json.loads((folder / 'coverage.json').read_text())
            coverage['files']['records.csv.gz'] = tw.receipt(path, len(records), tw.FIELDS, True)
            tw.write_json(folder / 'coverage.json', coverage)
            with self.assertRaisesRegex(ValueError, 'replay'):
                tw.verify(folder)

    def test_inflated_coverage_categories_fail(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'TW'
            shutil.copytree(FOLDER, folder)
            coverage = json.loads((folder / 'coverage.json').read_text())
            coverage['cities'] += 1
            tw.write_json(folder / 'coverage.json', coverage)
            with self.assertRaisesRegex(ValueError, 'category'):
                tw.verify(folder)


if __name__ == '__main__':
    unittest.main()
