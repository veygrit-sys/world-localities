"""SE official SCB/GeoNames/LAU contracts; offline and network-free."""
from pathlib import Path
import csv
import gzip
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import sweden_localities as se


def dump(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False), encoding='utf-8')
    return p


class SwedenLocalitiesContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.orig = Path(__file__).resolve().parents[1]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.groot = self.root / 'geonames'
        self.groot.mkdir()
        self.lroot = self.root / 'lau'
        self.lroot.mkdir()

    def make_geo(self, rows):
        path = self.groot / 'entities-0001.csv.gz'
        with gzip.open(path, 'wt', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['id', 'kind', 'country_code', 'name', 'feature_code',
                                              'parent_id', 'parent_relation', 'latitude', 'longitude', 'address_candidate'])
            w.writeheader()
            w.writerows(rows)
        dump(self.groot / 'metadata.json', {'source': 'GeoNames', 'country': {'country': 'SE'},
            'files': {'entities-0001.csv.gz': {'sha256': se.hash_file(path), 'bytes': path.stat().st_size,
                                             'rows': len(rows)}},
            'counts': {'locality_rows': sum(r['kind'] == 'locality' for r in rows)}})
        return path

    def geo_row(self, gid='gn:1', kind='locality', name='Älvsjö'):
        return {'id': gid, 'kind': kind, 'country_code': 'SE', 'name': name,
                'feature_code': 'PPL', 'parent_id': '', 'parent_relation': '',
                'latitude': '59.28', 'longitude': '18.02', 'address_candidate': '1'}

    def test_official_scb_2026_is_exactly_21_counties_and_290_municipalities(self):
        counties, municipalities = se.load_counties()
        self.assertEqual(len(counties), 21)
        self.assertEqual(len(municipalities), 290)
        self.assertEqual(municipalities['0180'], ('Stockholm', '01'))
        self.assertEqual(municipalities['1480'], ('Göteborg', '14'))
        self.assertEqual(municipalities['1280'], ('Malmö', '12'))
        self.assertEqual(municipalities['2584'], ('Kiruna', '25'))
        self.assertEqual(counties['14'], 'Västra Götalands län')

    def test_sha_pin_prevents_undocumented_edits(self):
        path = self.root/'municipalities.csv'
        path.write_bytes(se.SCB.read_bytes().replace(b'Stockholm', b'Stockhulm', 1))
        with self.assertRaisesRegex(ValueError, 'transcription changed'):
            se.load_counties(path=path)

    def test_duplicate_official_code_rejected_even_when_pin_matches(self):
        path = self.root/'municipalities.csv'
        raw = se.SCB.read_text(encoding='utf-8')
        raw += '01,Stockholms län,0180,Stockholm\n'
        path.write_text(raw, encoding='utf-8')
        pin = json.loads(se.PROVENANCE.read_text())
        pin['scb_2026'].update(bytes=path.stat().st_size, sha256=se.hash_file(path))
        provenance = dump(self.root/'source.json', pin)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            se.load_counties(path, provenance)

    def test_mismatched_county_prefix_rejected(self):
        path = self.root/'municipalities.csv'
        raw = se.SCB.read_text(encoding='utf-8')
        raw = raw.replace('01,Stockholms län,0180,Stockholm', '03,Stockholms län,0180,Stockholm')
        path.write_text(raw, encoding='utf-8')
        pin = json.loads(se.PROVENANCE.read_text())
        pin['scb_2026'].update(bytes=path.stat().st_size, sha256=se.hash_file(path))
        with self.assertRaisesRegex(ValueError, 'inconsistent'):
            se.load_counties(path, dump(self.root/'source.json', pin))

    def test_swedish_postcode_is_syntax_only(self):
        for candidate in ('12345', '123 45', '98100'):
            self.assertTrue(se.validate_postcode(candidate)['syntax_valid'])
        for candidate in ('01234', '1234', '123456', '123-45', '123  45', '１２３４５'):
            self.assertFalse(se.validate_postcode(candidate)['syntax_valid'])
        self.assertIsNone(se.validate_postcode('123 45')['postcode_exists'])
        self.assertIsNone(se.validate_postcode('123 45')['deliverable'])

    def test_source_ids_and_county_parents_not_joined_by_names(self):
        counties, municipalities = se.load_counties()
        rows = list(se.iter_scb(counties, municipalities))
        self.assertEqual(len(rows), 311)
        code = next(r for r in rows if r['id'] == 'scb:municipality:2026:0180')
        self.assertEqual(code['parent_id'], 'scb:county:2026:01')
        self.assertFalse(code['delivery_verified'])

    def test_geonames_replay_counts_and_search(self):
        self.make_geo([self.geo_row(), self.geo_row('gn:2', 'admin_subdivision', 'Stockholms län')])
        self.assertEqual(se.verify_geonames(self.groot)['rows'], 2)
        found = se.lookup('Älvsjö', 'locality', 10, geo_root=self.groot)
        self.assertEqual([row['id'] for row in found['matches']], ['gn:1'])
        self.assertFalse(found['is_address_verification'])
        found = se.lookup('Stockholm', 'municipality', 5, geo_root=self.groot)
        self.assertEqual(found['matches'][0]['id'], 'scb:municipality:2026:0180')
        self.assertEqual(se.lookup('0180', 'municipality', 5, geo_root=self.groot)['matches'][0]['id'],
                         'scb:municipality:2026:0180')

    def test_geonames_tamper_rejected(self):
        path = self.make_geo([self.geo_row()])
        with path.open('ab') as f:
            f.write(b'bad')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            se.verify_geonames(self.groot)

    def test_geonames_duplicate_stable_id_rejected(self):
        self.make_geo([self.geo_row(), self.geo_row()])
        with self.assertRaisesRegex(ValueError, 'collision'):
            se.verify_geonames(self.groot)

    def make_lau(self, rows):
        path = self.lroot/'units.csv.gz'
        with gzip.open(path, 'wt', encoding='utf-8', newline='') as f:
            w = csv.DictWriter(f, fieldnames=['country', 'lau_code', 'name_national'])
            w.writeheader()
            w.writerows(rows)
        dump(self.lroot/'metadata.json', {'files': {'units.csv.gz': {
            'sha256': se.hash_file(path), 'bytes': path.stat().st_size, 'rows': len(rows)}}})
        return path

    def test_eurostat_2024_source_retains_namespace_and_reports_differences(self):
        self.make_lau([{'country': 'SE', 'lau_code': '0180', 'name_national': 'Stockholm'},
                       {'country': 'SE', 'lau_code': '1480', 'name_national': 'Goteborg'}])
        result = se.verify_lau(self.lroot, {'0180': ('Stockholm', '01'), '1480': ('Göteborg', '14')})
        self.assertEqual(len(result['name_differences']), 1)
        self.assertEqual(result['name_differences'][0]['code'], '1480')
        self.assertEqual(result['source'], 'Eurostat LAU 2025 label, source period 2024')

    def test_eurostat_duplicate_and_cross_country_rejected(self):
        self.make_lau([{'country': 'SE', 'lau_code': '0180', 'name_national': 'Stockholm'},
                       {'country': 'SE', 'lau_code': '0180', 'name_national': 'Duplicate'}])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            se.verify_lau(self.lroot)
        self.make_lau([{'country': 'DK', 'lau_code': '0180', 'name_national': 'Stockholm'}])
        with self.assertRaisesRegex(ValueError, 'foreign'):
            se.verify_lau(self.lroot)

    def make_scb_pin(self, fmt='geojson', dataset='tatorter_2023', count=2017):
        fields = {'id': 'tatortskod', 'name': 'tatort', 'county': 'lan', 'municipality': 'kommun'}
        if fmt == 'geojson':
            source = self.root/'sample.geojson'
            feats = [{'type': 'Feature', 'properties': {'tatortskod': str(i), 'tatort': 'Ort ' + str(i),
                         'lan': '01', 'kommun': '0180'}, 'geometry': None} for i in range(count)]
            dump(source, {'type': 'FeatureCollection', 'features': feats})
        else:
            source = self.root/'sample.gpkg'
            con = sqlite3.connect(source)
            con.execute('CREATE TABLE Tatorter_2023 (tatortskod TEXT, tatort TEXT, lan TEXT, kommun TEXT)')
            con.executemany('INSERT INTO Tatorter_2023 VALUES (?,?,?,?)',
                            [(str(i), 'Ort ' + str(i), '01', '0180') for i in range(count)])
            con.commit()
            con.close()
        pin = {'country': 'SE', 'dataset': dataset, 'format': fmt, 'path': source.name,
               'license': 'CC0-1.0', 'rights_reviewed': True,
               'source_url': 'https://geodata.scb.se/geoserver/stat/wfs?service=WFS',
               'bytes': source.stat().st_size, 'sha256': se.hash_file(source), 'crs': 'EPSG:3006',
               'fields': fields}
        if fmt == 'gpkg':
            pin['table'] = 'Tatorter_2023'
        return pin

    def test_geojson_full_reference_count_and_atomic_output(self):
        pin = self.make_scb_pin()
        output = self.root/'normalized.jsonl'
        result = se.import_official(pin, self.root, output)
        self.assertEqual(result['rows'], 2017)
        self.assertFalse(result['delivery_verified'])
        first = json.loads(output.read_text().splitlines()[0])
        self.assertEqual(first['parent_id'], 'scb:municipality:2026:0180')
        self.assertFalse(first['is_current_address_verified'])
        with self.assertRaisesRegex(ValueError, 'replace'):
            se.import_official(pin, self.root, output)

    def test_geopackage_readonly_path_and_row_count(self):
        pin = self.make_scb_pin(fmt='gpkg')
        output = self.root/'normalized.jsonl'
        self.assertEqual(se.import_official(pin, self.root, output)['rows'], 2017)
        self.assertEqual(len(output.read_text().splitlines()), 2017)

    def test_malformed_or_unlicensed_source_rejected(self):
        pin = self.make_scb_pin(count=3)
        with self.assertRaisesRegex(ValueError, 'count mismatch'):
            se.import_official(pin, self.root, self.root/'out.jsonl')
        self.assertFalse((self.root/'out.jsonl').exists())
        pin['rights_reviewed'] = False
        with self.assertRaisesRegex(ValueError, 'rights'):
            se.import_official(pin, self.root, self.root/'out.jsonl')
        pin['rights_reviewed'] = True
        pin['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'differ'):
            se.import_official(pin, self.root, self.root/'out.jsonl')

    def test_ambiguous_geographic_parent_does_not_guess(self):
        pin = self.make_scb_pin()
        source = self.root/'sample.geojson'
        data = json.loads(source.read_text())
        data['features'][0]['properties']['kommun'] = '0180;0181'
        dump(source, data)
        pin.update(bytes=source.stat().st_size, sha256=se.hash_file(source))
        output = self.root/'out.jsonl'
        se.import_official(pin, self.root, output)
        rows = [json.loads(line) for line in output.read_text().splitlines()]
        ambiguous = next(row for row in rows if row['id'] == 'scb:tatorter_2023:0')
        self.assertIsNone(ambiguous['parent_id'])
        self.assertEqual(ambiguous['original_municipality'], '0180;0181')

    def test_gpkg_table_injection_and_path_traversal_rejected(self):
        pin = self.make_scb_pin(fmt='gpkg')
        pin['table'] = 'Tatorter_2023;DROP TABLE x'
        with self.assertRaisesRegex(ValueError, 'table'):
            se.import_official(pin, self.root, self.root/'out.jsonl')
        pin['table'] = 'Tatorter_2023'
        pin['path'] = '../wrong.gpkg'
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            se.import_official(pin, self.root, self.root/'out.jsonl')

    def test_output_is_deterministic(self):
        pin = self.make_scb_pin()
        a, b = self.root/'one.jsonl', self.root/'two.jsonl'
        first = se.import_official(pin, self.root, a)
        second = se.import_official(pin, self.root, b)
        self.assertEqual(first['sha256'], second['sha256'])


if __name__ == '__main__':
    unittest.main()
