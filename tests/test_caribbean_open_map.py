import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('caribbean_open_map', ROOT / 'scripts/caribbean_osm.py')
osm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(osm)
HAS_GEOMETRY = importlib.util.find_spec('shapely') is not None
HAS_OSMIUM = importlib.util.find_spec('osmium') is not None


@unittest.skipUnless(HAS_GEOMETRY, 'optional shapely dependency is required')
class GeographicScope(unittest.TestCase):
    def setUp(self):
        from shapely.geometry import box
        self.lookup = osm.Classifier({'MF': [box(0, 0, 1, 1)], 'SX': [box(1, 0, 2, 1)]})

    def test_cross_border_road_is_reviewed_without_forced_country(self):
        from shapely.geometry import LineString
        cc, candidates, status = self.lookup.classify(LineString([(0.5, 0.5), (1.5, 0.5)]))
        self.assertIsNone(cc)
        self.assertEqual(candidates, ['MF', 'SX'])
        self.assertEqual(status, 'crosses_or_touches_country_boundary')

    def test_point_on_shared_border_remains_ambiguous(self):
        from shapely.geometry import Point
        self.assertIsNone(self.lookup.classify(Point(1, 0.5))[0])

    def test_outside_point_is_not_assigned_to_nearest_island(self):
        from shapely.geometry import Point
        self.assertEqual(self.lookup.classify(Point(5, 5))[:2], (None, []))

    def test_different_country_is_not_inferred_from_same_name(self):
        from shapely.geometry import Point
        self.assertEqual(self.lookup.classify(Point(0.5, 0.5))[0], 'MF')
        self.assertEqual(self.lookup.classify(Point(1.5, 0.5))[0], 'SX')

    def test_legal_BQ_grouping_is_not_an_administrative_government(self):
        self.assertEqual(osm.categories('relation', {'boundary': 'legal', 'ISO3166-1': 'BQ'}), ['legal_boundary'])


class NormalizedSources(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def fixture(self):
        doc = {'osm_key': 'osm:node:1', 'osm_type': 'node', 'osm_id': 1, 'osm_version': 1,
               'source_tags': {'addr:housenumber': '0007-A;9', 'addr:street': 'Fixture Street'},
               'country': 'GP', 'categories': ['explicit_number_observation'], 'license': 'ODbL-1.0',
               'assignment_verified': False, 'national_completeness_verified': False, 'deliverability_in_scope': False}
        line = osm.canonical(doc) + '\n'
        source = self.root / 'observations.jsonl.gz'
        source.write_bytes(gzip.compress(line.encode(), mtime=0))
        manifest = {'schema_version': 1, 'region': 'caribbean', 'scope_codes': list(osm.SCOPE), 'records': 1,
                    'license': 'ODbL-1.0', 'complete': False, 'deliverability_in_scope': False,
                    'normalized': {'path': source.name, 'bytes': source.stat().st_size,
                                   'sha256': osm.file_hash(source), 'uncompressed_row_sha256': hashlib.sha256(line.encode()).hexdigest()}}
        (self.root / 'manifest.json').write_text(json.dumps(manifest))
        return doc

    def test_type_is_part_of_the_source_identity(self):
        self.assertNotEqual(osm.osm_key('way', 1), osm.osm_key('node', 1))
        self.assertNotEqual(osm.osm_key('way', 1), osm.osm_key('relation', 1))

    def test_complex_explicit_number_is_a_literal_not_an_expanded_range(self):
        self.fixture()
        output = self.root / 'index.sqlite'
        osm.restore_index(self.root, output)
        result = osm.query(output, 'GP', '0007-A;9')
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(osm.query(output, 'GP', '7')['results'], [])
        self.assertFalse(result['complete'])
        self.assertFalse(result['deliverability_in_scope'])
        self.assertEqual(result['license'], 'ODbL-1.0')

    def test_interpolation_does_not_create_number_observations(self):
        self.assertEqual(osm.categories('way', {'addr:interpolation': 'even'}), ['interpolation_way_evidence'])

    def test_corrupt_stream_does_not_install_an_index(self):
        self.fixture()
        (self.root / 'observations.jsonl.gz').write_bytes(b'corrupt')
        output = self.root / 'index.sqlite'
        with self.assertRaises(ValueError): osm.restore_index(self.root, output)
        self.assertFalse(output.exists())

    def test_incomplete_snapshot_is_rejected(self):
        self.fixture()
        index = self.root / 'ready.sqlite'
        osm.restore_index(self.root, index)
        (self.root / 'INCOMPLETE.json').write_text('{}')
        with self.assertRaises(ValueError): osm.restore_index(self.root, self.root / 'index.sqlite')
        with self.assertRaises(ValueError): osm.query(index, 'GP')

    def test_existing_database_is_never_overwritten(self):
        self.fixture()
        output = self.root / 'keep.sqlite'
        output.write_bytes(b'keep')
        with self.assertRaises(ValueError): osm.restore_index(self.root, output)
        self.assertEqual(output.read_bytes(), b'keep')

    def test_explicit_parent_cycle_is_reported_without_repair(self):
        import sqlite3
        database = self.root/'parents.sqlite'
        with sqlite3.connect(database) as db:
            db.execute('CREATE TABLE records(osm_key TEXT,country TEXT,document BLOB)')
            for parent, child in [(1, 2), (2, 1)]:
                doc = {'categories': ['administrative_boundary'], 'source_tags': {'admin_level': '8'},
                       'source_members': [{'type': 'r', 'ref': child, 'role': 'subarea'}]}
                db.execute('INSERT INTO records VALUES(?,?,?)', (osm.osm_key('relation', parent), 'GP', osm.packed_document(osm.canonical(doc))))
        report = osm.audit_parent_references(database)
        self.assertEqual(len(report['cycles']), 1)
        self.assertFalse(report['complete'])

    def test_missing_subarea_is_not_fabricated(self):
        import sqlite3
        database = self.root/'parents.sqlite'
        doc = {'categories': ['administrative_boundary'], 'source_tags': {'admin_level': '4'},
               'source_members': [{'type': 'r', 'ref': 99, 'role': 'subarea'}]}
        with sqlite3.connect(database) as db:
            db.execute('CREATE TABLE records(osm_key TEXT,country TEXT,document BLOB)')
            db.execute('INSERT INTO records VALUES(?,?,?)', (osm.osm_key('relation', 1), 'GP', osm.packed_document(osm.canonical(doc))))
        report = osm.audit_parent_references(database)
        self.assertEqual(report['issues'][0]['issue'], 'child_not_in_selected_source_index')


@unittest.skipUnless(HAS_GEOMETRY and HAS_OSMIUM, 'optional PBF dependencies are required')
class SourceExtraction(unittest.TestCase):
    def test_all_28_scopes_and_relation_numbers_are_preserved(self):
        # Synthetic geometry exercises partitioning; it is not production geography.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            nodes, ways, relations = [], [], []
            for i, cc in enumerate(osm.SCOPE):
                x, y, start = -100 + i * 2, 10, 1 + 4 * i
                for j, (lon, lat) in enumerate([(x, y), (x+1, y), (x+1, y+1), (x, y+1)]):
                    nodes.append(f'<node id="{start+j}" version="1" lon="{lon}" lat="{lat}"/>')
                nodes.append(f'<node id="{1000+i}" version="1" lon="{x+0.5}" lat="{y+0.5}"><tag k="addr:housenumber" v="0007"/></node>')
                ways.append(f'<way id="{2000+i}" version="1">'+''.join(f'<nd ref="{n}"/>' for n in [start,start+1,start+2,start+3,start])+'</way>')
                ways.append(f'<way id="{1000+i}" version="1"><nd ref="{start}"/><nd ref="{start+1}"/><tag k="highway" v="residential"/><tag k="addr:interpolation" v="even"/></way>')
                boundary = 'legal' if cc == 'BQ' else 'administrative'
                relations.append(f'<relation id="{3000+i}" version="1"><member type="way" ref="{2000+i}" role="outer"/><tag k="type" v="boundary"/><tag k="boundary" v="{boundary}"/><tag k="ISO3166-1" v="{cc}"/></relation>')
            # A numbered relation has a member with no address or highway tags.
            nodes.extend(['<node id="9001" version="1" lon="-99.8" lat="10.2"/>',
                          '<node id="9002" version="1" lon="-99.6" lat="10.2"/>'])
            ways.append('<way id="9000" version="1"><nd ref="9001"/><nd ref="9002"/></way>')
            relations.append('<relation id="9000" version="1"><member type="way" ref="9000" role="outer"/><tag k="type" v="multipolygon"/><tag k="addr:housenumber" v="0099"/></relation>')
            from xml.etree.ElementTree import fromstring
            for objects in (nodes, ways, relations): objects.sort(key=lambda item: int(fromstring(item).attrib['id']))
            source = root / 'source.osm'
            source.write_text('<osm version="0.6">'+''.join(nodes+ways+relations)+'</osm>')
            receipt = {'bytes': source.stat().st_size, 'sha256': osm.file_hash(source)}
            target = root / 'extracted'
            report = osm.extract(source, receipt, target)
            self.assertEqual(report['country_polygon_count'], 28)
            self.assertEqual(report['category_counts']['explicit_number_observation'], 29)
            self.assertEqual(len(osm.query(target/'caribbean_osm.sqlite', 'AG', '0099')['results']), 1)
            self.assertEqual(report['country_counts']['BQ'].get('administrative_boundary', 0), 0)
            self.assertEqual(osm.replay(source, target)['source_objects_replayed'], report['records'])
            restored = root/'restored.sqlite'
            self.assertEqual(osm.restore_index(target, restored)['records'], report['records'])
            self.assertEqual(len(osm.query(restored, 'AG', '0007')['results']), 1)


if __name__ == '__main__':
    unittest.main()
