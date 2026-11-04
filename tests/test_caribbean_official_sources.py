import csv
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import struct
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location('caribbean_official', Path(__file__).resolve().parents[1] / 'scripts/caribbean_official.py')
official = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(official)


class OfficialSources(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'raw').mkdir()
        self.db = self.root / 'index.sqlite'

    def row(self, **changes):
        return {'id': '97101_0001_00007', 'numero': '0007', 'rep': 'bis', 'nom_voie': 'Rue 100% _Nord',
                'code_insee': '97101', 'lon': '-61.5', 'lat': '16.2', 'certification_commune': '0', **changes}

    def ban(self, rows=None, country='GP'):
        rows = rows if rows is not None else [self.row()]
        name = 'adresses-' + official.DEPARTMENTS[country] + '.csv.gz'
        stream = io.StringIO(newline='')
        writer = csv.DictWriter(stream, fieldnames=list(self.row()), delimiter=';')
        writer.writeheader()
        writer.writerows(rows)
        path = self.root / 'raw' / name
        path.write_bytes(gzip.compress(stream.getvalue().encode(), mtime=0))
        return self.pin(path, country, 'ban_csv_gz')

    def pin(self, path, country, format_, **extras):
        return {'id': path.stem, 'path': 'raw/' + path.name, 'country': country, 'format': format_,
                'bytes': path.stat().st_size, 'sha256': official.sha256(path), **extras}

    def manifest(self, sources):
        return {'schema_version': 1, 'region': 'caribbean', 'scope_codes': list(official.SCOPE),
                'sources': sources, 'required_source_ids': [s['id'] for s in sources],
                'failures': [], 'complete': False, 'deliverability_in_scope': False}

    def test_duplicate_address_positions_and_leading_zeroes_preserved(self):
        source = self.ban([self.row(), self.row(lon='-61.51', certification_commune='1')])
        official.build(self.manifest([source]), self.root, self.db)
        report = official.search(self.db, 'GP', number='0007')
        self.assertEqual(len(report['results']), 2)
        self.assertEqual(report['results'][0]['suffix'], 'bis')
        self.assertEqual(report['results'][0]['raw']['numero'], '0007')
        self.assertEqual(report['results'][1]['assignment_status'], 'municipality_certified_source_record')
        self.assertFalse(report['complete'])
        self.assertFalse(report['deliverability_in_scope'])
        self.assertEqual(official.search(self.db, 'GP', number='7')['results'], [])

    def test_coverage_does_not_count_duplicate_positions_as_unique_addresses(self):
        source = self.ban([self.row(), self.row()])
        official.build(self.manifest([source]), self.root, self.db)
        report = official.coverage(self.db)
        self.assertEqual(len(report['countries']), 28)
        gp = next(c for c in report['countries'] if c['country'] == 'GP')
        self.assertEqual(gp['ban_position_observations'], 2)
        self.assertEqual(gp['ban_numbered_source_ids'], 1)
        self.assertFalse(gp['assigned_numbers_complete'])
        self.assertIsNone(gp['independent_national_denominators'])

    def test_country_scope_and_query_escaping(self):
        source = self.ban()
        official.build(self.manifest([source]), self.root, self.db)
        self.assertEqual(len(official.search(self.db, 'GP', text='100% _Nord')['results']), 1)
        self.assertEqual(official.search(self.db, 'MF')['results'], [])
        self.assertEqual(official.search(self.db, 'GP', text="' OR 1=1 --")['results'], [])
        with self.assertRaises(ValueError): official.search(self.db, 'SX', limit=0)

    def test_pagination_preserves_repeated_source_ids(self):
        source = self.ban([self.row(), self.row()])
        official.build(self.manifest([source]), self.root, self.db)
        first = official.search(self.db, 'GP', limit=1)
        second = official.search(self.db, 'GP', limit=1, offset=first['next_offset'])
        self.assertNotEqual(first['results'][0]['ordinal'], second['results'][0]['ordinal'])
        self.assertFalse(second['has_more'])

    def test_wrong_territory_is_rejected_without_installed_output(self):
        source = self.ban([self.row(code_insee='97801')])
        with self.assertRaisesRegex(ValueError, 'jurisdiction'):
            official.build(self.manifest([source]), self.root, self.db)
        self.assertFalse(self.db.exists())

    def test_number_ranges_are_not_expanded(self):
        source = self.ban([self.row(numero='1-99')])
        with self.assertRaises(ValueError): official.build(self.manifest([source]), self.root, self.db)
        self.assertFalse(self.db.exists())

    def test_nonfinite_or_half_coordinates_are_rejected(self):
        for changes in ({'lon': 'NaN'}, {'lat': '91'}, {'lon': ''}):
            with self.subTest(changes=changes):
                source = self.ban([self.row(**changes)])
                with self.assertRaises(ValueError): official.build(self.manifest([source]), self.root, self.db)
                self.assertFalse(self.db.exists())

    def test_source_corruption_blocks_build(self):
        source = self.ban()
        (self.root / source['path']).write_bytes(b'corrupted')
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            official.build(self.manifest([source]), self.root, self.db)
        self.assertFalse(self.db.exists())

    def test_empty_response_cannot_be_accepted_as_coverage(self):
        source = self.ban([])
        with self.assertRaisesRegex(ValueError, 'Empty official source'):
            official.build(self.manifest([source]), self.root, self.db)
        self.assertFalse(self.db.exists())

    def test_replay_detects_database_edits_and_preserves_previous_output(self):
        source = self.ban()
        manifest = self.manifest([source])
        official.build(manifest, self.root, self.db)
        self.assertEqual(official.replay(manifest, self.root, self.db)['status'], 'PASS')
        digest = official.sha256(self.db)
        with self.assertRaises(ValueError): official.build(manifest, self.root, self.db)
        self.assertEqual(digest, official.sha256(self.db))
        with sqlite3.connect(self.db) as db:
            db.execute("UPDATE observations SET number='999'")
        with self.assertRaisesRegex(ValueError, 'Stored source row differs'):
            official.replay(manifest, self.root, self.db)

    def test_manifest_missing_duplicate_and_wrong_country_pins(self):
        source = self.ban()
        for edit in ('missing', 'duplicate', 'wrong_country'):
            with self.subTest(edit=edit):
                manifest = self.manifest([dict(source)])
                if edit == 'missing': manifest['required_source_ids'].append('missing')
                elif edit == 'duplicate': manifest['sources'].append(dict(source))
                else: manifest['sources'][0]['country'] = 'MF'
                path = self.root / 'manifest.json'
                path.write_text(json.dumps(manifest))
                with self.assertRaises(ValueError): official.load_manifest(path)

    def dbf(self, rows):
        fields = [('LINEARID', 22), ('FULLNAME', 100), ('RTTYP', 1), ('MTFCC', 5)]
        header = bytearray(32)
        header[0] = 3
        struct.pack_into('<IHH', header, 4, len(rows), 33 + 32 * len(fields), 1 + sum(w for _, w in fields))
        for name, width in fields:
            descriptor = bytearray(32)
            descriptor[:len(name)] = name.encode()
            descriptor[11] = ord('C')
            descriptor[16] = width
            header += descriptor
        header += b'\r'
        for row in rows:
            header += b' ' + b''.join(row[name].encode().ljust(width, b' ') for name, width in fields)
        return bytes(header) + b'\x1a'

    def shapes(self, count):
        header = bytearray(100)
        struct.pack_into('>i', header, 0, 9994)
        struct.pack_into('<ii', header, 28, 1000, 3)
        body = struct.pack('<iddddiii', 3, -66.1, 18.1, -66.0, 18.2, 1, 2, 0)
        body += struct.pack('<dddd', -66.1, 18.1, -66.0, 18.2)
        data = header + b''.join(struct.pack('>ii', i + 1, len(body) // 2) + body for i in range(count))
        struct.pack_into('>i', data, 24, len(data) // 2)
        return bytes(data)

    def road(self, row_count=2, shape_count=None):
        path = self.root / 'raw/tl_2025_72001_roads.zip'
        stem = path.stem
        rows = [{'LINEARID': '00001', 'FULLNAME': '' if i else 'Calle Uno', 'RTTYP': 'M', 'MTFCC': 'S1400'} for i in range(row_count)]
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr(stem + '.dbf', self.dbf(rows))
            z.writestr(stem + '.shp', self.shapes(row_count if shape_count is None else shape_count))
            z.writestr(stem + '.prj', 'GEOGCS["GCS_North_American_1983",UNIT["Degree",0.017453292519943295]]')
            z.writestr(stem + '.shx', b'fixture index retained')
        return self.pin(path, 'PR', 'tiger_roads', county='72001')

    def test_road_shapes_overlap_and_unnamed_features_are_preserved(self):
        source = self.road()
        manifest = self.manifest([source])
        official.build(manifest, self.root, self.db)
        rows = official.search(self.db, 'PR')['results']
        self.assertEqual([r['source_id'] for r in rows], ['00001', '00001'])
        self.assertTrue(all(r['number'] == '' for r in rows))
        self.assertEqual(rows[1]['street'], '')
        self.assertEqual(rows[0]['geometry_reference']['points'], 2)
        self.assertEqual(official.replay(manifest, self.root, self.db)['status'], 'PASS')

    def test_road_attribute_geometry_count_mismatch_blocks_publication(self):
        source = self.road(row_count=2, shape_count=1)
        with self.assertRaisesRegex(ValueError, 'counts differ'):
            official.build(self.manifest([source]), self.root, self.db)
        self.assertFalse(self.db.exists())

    def test_truncated_dbf_and_shape_headers_rejected(self):
        with self.assertRaises(ValueError): list(official.dbf_records(b'bad', 'utf-8'))
        with self.assertRaises(ValueError): list(official.shape_records(self.shapes(1)[:-1]))

    def test_administrative_code_join_does_not_use_matching_names(self):
        source = self.ban()
        official.build(self.manifest([source]), self.root, self.db)
        hierarchy = self.root / 'hierarchy.sqlite'
        with sqlite3.connect(hierarchy) as db:
            db.execute('CREATE TABLE nodes (id TEXT,country TEXT,namespace TEXT,code TEXT,kind TEXT)')
            db.execute('INSERT INTO nodes VALUES (?,?,?,?,?)', ('correct', 'GP', 'insee-2026', '97101', 'commune'))
        report = official.crosscheck_admin(self.db, hierarchy)
        self.assertEqual(report['reference_count'], 1)
        with sqlite3.connect(hierarchy) as db:
            db.execute("UPDATE nodes SET country='MF'")
        with self.assertRaises(ValueError): official.crosscheck_admin(self.db, hierarchy)

    def test_collectivity_alias_requires_the_explicit_insee_observation(self):
        source = self.ban([self.row(code_insee='97701', id='97701_0001_00007')], country='BL')
        official.build(self.manifest([source]), self.root, self.db)
        hierarchy = self.root / 'hierarchy.sqlite'
        raw = {'member': 'v_commune_comer_2026.csv', 'fields': {'COM_COMER': '97701', 'COMER': '977', 'NATURE_ZONAGE': 'COM'}}
        with sqlite3.connect(hierarchy) as db:
            db.execute('CREATE TABLE nodes (id TEXT,country TEXT,namespace TEXT,code TEXT,kind TEXT)')
            db.execute('CREATE TABLE observations (node TEXT,source TEXT,raw_json TEXT)')
            db.execute('INSERT INTO nodes VALUES (?,?,?,?,?)', ('bl', 'BL', 'insee-2026', '977', 'collectivity'))
            db.execute('INSERT INTO observations VALUES (?,?,?)', ('bl', 'fr-insee-cog-2026', json.dumps(raw)))
        report = official.crosscheck_admin(self.db, hierarchy)
        self.assertEqual(report['insee_code_references'][0]['join'], 'explicit_insee_code_alias')
        with sqlite3.connect(hierarchy) as db:
            db.execute('DELETE FROM observations')
        with self.assertRaises(ValueError): official.crosscheck_admin(self.db, hierarchy)


if __name__ == '__main__':
    unittest.main()
