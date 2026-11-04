"""Preserved ALS observations replay the selected 2D source, without inferred data."""
from __future__ import annotations

import copy
import csv
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('hk_official_test_importer', ROOT / 'scripts/import_hk_official.py')
hk = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hk)
MEMBER = 'ALS_GeoJSON_329/als_addresses_(central_&_western_district).geojson'
THREE_D = 'ALS_GeoJSON_329/als_addresses_3d_(public_rental_housing).geojson'
CSU_ID = '3019415502T20050430'


def feature():
    return {'type': 'Feature', 'geometry': {'type': 'Point', 'coordinates': [114.11794, 22.27837]},
            'properties': {'Easting': 830194, 'Northing': 815502, 'Address': {'PremisesAddress': {
                'BuildingCsuInformation': {'CsuId': CSU_ID}, 'GeoAddress': CSU_ID,
                'ChiPremisesAddress': {'Region': '香港', 'ChiDistrict': '中西區',
                    'ChiStreet': {'StreetName': '域多利道', 'BuildingNoFrom': '12A', 'BuildingNoTo': '14B'},
                    'BuildingName': '測試大廈'},
                'EngPremisesAddress': {'Region': 'HK', 'EngDistrict': 'CENTRAL & WESTERN DISTRICT',
                    'EngStreet': {'StreetName': 'VICTORIA ROAD', 'BuildingNoFrom': '12A', 'BuildingNoTo': '14B'},
                    'BuildingName': 'TEST BUILDING'}}}}}


def source_zip(path, features, extra=None):
    raw = json.dumps({'type': 'FeatureCollection', 'features': features}, ensure_ascii=False).encode()
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MEMBER, raw)
        for name, data in (extra or {}).items():
            archive.writestr(name, data)
    return path


def read_records(folder):
    with gzip.open(folder / 'records.csv.gz', 'rt', encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


class HongKongOfficialExpansionTests(unittest.TestCase):
    def build(self, root, features=None, name='layer', extra=None):
        source = source_zip(root / (name + '.zip'), features or [feature()], extra)
        folder = root / name
        hk.build(source, folder, retrieved_at='2026-11-04T00:00:00Z')
        return folder, source

    def test_source_replay_preserves_repeated_building_ids_and_number_strings(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            other = feature()
            other['geometry']['coordinates'] = [114.118, 22.279]
            folder, source = self.build(root, [feature(), other])
            records = read_records(folder)
            self.assertEqual([CSU_ID, CSU_ID], [row['csu_id'] for row in records])
            self.assertEqual(2, len({row['observation_id'] for row in records}))
            for index, row in enumerate(records, 1):
                expected = 'hk:als:obs:' + hashlib.sha256((MEMBER + '\0' + str(index)).encode()).hexdigest()
                self.assertEqual(expected, row['observation_id'])
                original = json.loads(row['feature_json'])
                street = original['properties']['Address']['PremisesAddress']['ChiPremisesAddress']['ChiStreet']
                self.assertEqual(('12A', '14B'), (street['BuildingNoFrom'], street['BuildingNoTo']))
            report = hk.verify(folder, source_path=source)
            self.assertEqual('passed', report['status'])
            self.assertEqual('passed_all_selected_district_2d_source_rows', report['source_replay'])

    def test_missing_english_street_is_not_replaced_with_native_street(self):
        raw = feature()
        del raw['properties']['Address']['PremisesAddress']['EngPremisesAddress']['EngStreet']
        row = hk.normalize_feature(raw, MEMBER, 1)
        self.assertEqual('域多利道', row['native_street'])
        self.assertEqual('', row['english_street'])
        self.assertEqual(raw, json.loads(row['feature_json']))

    def test_source_missing_coordinates_remain_empty(self):
        raw = feature()
        raw['geometry'] = {}
        del raw['properties']['Easting']
        del raw['properties']['Northing']
        row = hk.normalize_feature(raw, MEMBER, 1)
        self.assertEqual('not_supplied_by_source', row['coordinate_status'])
        self.assertEqual(['', '', '', ''], [row[k] for k in
            ('longitude', 'latitude', 'hk1980_easting', 'hk1980_northing')])
        self.assertEqual(raw, json.loads(row['feature_json']))

    def test_supplied_invalid_ids_numbers_and_coordinates_are_rejected(self):
        mutations = []
        raw = feature(); raw['properties']['Address']['PremisesAddress']['BuildingCsuInformation']['CsuId'] = 'bad'; mutations.append(raw)
        raw = feature(); raw['properties']['Address']['PremisesAddress']['ChiPremisesAddress']['ChiStreet']['BuildingNoFrom'] = 12; mutations.append(raw)
        raw = feature(); raw['geometry']['coordinates'] = [114.0, 1000]; mutations.append(raw)
        raw = feature(); raw['geometry']['coordinates'] = [float('nan'), 22.0]; mutations.append(raw)
        for raw in mutations:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                hk.normalize_feature(raw, MEMBER, 1)

    def test_payload_tampering_is_detected_even_after_manifest_hash_is_reset(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder, _ = self.build(Path(temporary))
            records = read_records(folder)
            records[0]['native_street'] = 'changed'
            stream = io.StringIO(newline='')
            writer = csv.DictWriter(stream, fieldnames=hk.COLUMNS, lineterminator='\n')
            writer.writeheader(); writer.writerows(records)
            plain = stream.getvalue().encode()
            compressed = gzip.compress(plain, mtime=0)
            (folder / 'records.csv.gz').write_bytes(compressed)
            coverage_path = folder / 'coverage.json'
            coverage = json.loads(coverage_path.read_text())
            info = coverage['files']['records.csv.gz']
            info.update(bytes=len(compressed), sha256=hashlib.sha256(compressed).hexdigest())
            if 'uncompressed_sha256' in info:
                info['uncompressed_sha256'] = hashlib.sha256(plain).hexdigest()
            coverage_path.write_text(json.dumps(coverage))
            with self.assertRaises(ValueError):
                hk.verify(folder)

    def test_bundled_source_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder, _ = self.build(Path(temporary))
            sources = json.loads((folder / 'sources.json').read_text())
            raw_name = next(name for name in sources['bundled_files'] if name.lower().endswith('.zip'))
            source = folder / raw_name
            source.write_bytes(source.read_bytes() + b'tamper')
            with self.assertRaises(ValueError):
                hk.verify(folder)

    def test_optional_3d_member_is_not_parsed_and_unsafe_zip_members_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            # Invalid JSON here proves that excluded 3D data is not parsed as an address layer.
            folder, _ = self.build(root, extra={THREE_D: b'not parsed as GeoJSON'})
            self.assertEqual(1, len(read_records(folder)))
            self.assertEqual('passed', hk.verify(folder)['status'])
            invalid = root / 'duplicate.zip'
            raw = json.dumps({'type': 'FeatureCollection', 'features': [feature()]}).encode()
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', UserWarning)
                with zipfile.ZipFile(invalid, 'w') as archive:
                    archive.writestr(MEMBER, raw)
                    archive.writestr(MEMBER, raw)
            with self.assertRaises(ValueError):
                hk.build(invalid, root / 'duplicate')
            traversal = source_zip(root / 'traversal.zip', [feature()], {'../outside': b'data'})
            with self.assertRaises(ValueError):
                hk.build(traversal, root / 'traversal')

    def test_build_is_deterministic_and_existing_output_is_never_replaced(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first, source = self.build(root, name='first')
            second = root / 'second'
            hk.build(source, second, retrieved_at='2026-11-04T00:00:00Z')
            self.assertEqual((first / 'records.csv.gz').read_bytes(), (second / 'records.csv.gz').read_bytes())
            before = (first / 'records.csv.gz').read_bytes()
            with self.assertRaises((ValueError, FileExistsError)):
                hk.build(source, first)
            self.assertEqual(before, (first / 'records.csv.gz').read_bytes())


if __name__ == '__main__':
    unittest.main()
