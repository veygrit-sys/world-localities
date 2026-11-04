import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import osm_evidence as evidence
import osm_stream


class StreamEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.raw = self.root / 'source.osm'
        self.raw.write_text('''<osm version="0.6" generator="test">
        <node id="1" version="1" lat="14" lon="-90"><tag k="addr:housenumber" v="0007B"/></node>
        <node id="2" version="1" lat="14.1" lon="-90.1"/>
        <way id="3" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/><tag k="name" v="Avenida Uno"/></way>
        <way id="4" version="1"><nd ref="1"/><nd ref="999"/><tag k="highway" v="track"/></way>
        <way id="5" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="construction"/></way>
        <relation id="6" version="1"><member type="way" ref="3" role="outer"/><tag k="boundary" v="administrative"/></relation>
        </osm>''')
        self.receipt = {'country_extract': 'GT', 'source_id': 'test', 'path': self.raw.name,
                        'bytes': self.raw.stat().st_size, 'sha256': evidence.file_hash(self.raw)}
        self.manifest = {'scope_codes': ['GT'], 'sources': [self.receipt]}
        self.exported = self.root / 'export'

    def test_export_preserves_full_geometry_numbers_and_missing_references(self):
        report = osm_stream.export(self.manifest, self.root, self.exported)
        self.assertEqual(report['observation_records'], 5)
        self.assertEqual(report['extracts'][0]['active_road_way_records'], 2)
        self.assertEqual(report['extracts'][0]['active_road_ways_with_missing_geometry'], 1)
        roads = osm_stream.query(self.exported, 'GT', 'roads')['results']
        self.assertEqual(roads[0]['geometry']['coordinates'], [[-90, 14], [-90.1, 14.1]])
        self.assertIsNone(roads[1]['geometry'])
        self.assertEqual(roads[1]['topology']['nodes'], ['1', '999'])
        address = osm_stream.query(self.exported, 'GT', 'address-numbers')['results'][0]
        self.assertEqual(address['tags']['addr:housenumber'], '0007B')
        self.assertFalse(report['interpolation_expanded'])

    def test_all_selected_source_features_replay(self):
        osm_stream.export(self.manifest, self.root, self.exported)
        report = osm_stream.verify(self.manifest, self.root, self.exported)
        self.assertEqual(report['matched_observations'], 5)
        self.assertEqual(report['source_tags_topology_node_and_way_coordinates'], 'PASS')

    def test_source_replay_rejects_changed_data_even_with_new_file_hash(self):
        index = osm_stream.export(self.manifest, self.root, self.exported)
        path = self.exported / index['extracts'][0]['file']
        with gzip.open(path, 'rt') as reader: rows = [json.loads(line) for line in reader]
        rows[1]['tags']['addr:housenumber'] = 'invented'
        with gzip.open(path, 'wt') as writer:
            for row in rows: writer.write(json.dumps(row) + '\n')
        index['extracts'][0].update(bytes=path.stat().st_size, sha256=evidence.file_hash(path))
        (self.exported / 'index.json').write_text(json.dumps(index))
        with self.assertRaisesRegex(ValueError, 'replay mismatch'):
            osm_stream.verify(self.manifest, self.root, self.exported)

    def test_extract_memberships_keep_the_same_original_identity(self):
        self.manifest['scope_codes'].append('BZ')
        self.manifest['sources'].append({**self.receipt, 'country_extract': 'BZ', 'source_id': 'other-extract'})
        report = osm_stream.export(self.manifest, self.root, self.exported)
        self.assertEqual(report['observation_records'], 10)
        first = osm_stream.query(self.exported, 'GT', 'all', limit=1)['results'][0]
        second = osm_stream.query(self.exported, 'BZ', 'all', limit=1)['results'][0]
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(first['variant_sha256'], second['variant_sha256'])
        self.assertFalse(report['extract_membership_is_legal_country_membership'])

    def test_existing_export_and_untrusted_paths_are_rejected(self):
        osm_stream.export(self.manifest, self.root, self.exported)
        with self.assertRaisesRegex(ValueError, 'new export'):
            osm_stream.export(self.manifest, self.root, self.exported)
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            osm_stream.checked_file(self.exported, {'file': '../elsewhere'})

    def test_search_literal_text_and_unknown_extract(self):
        osm_stream.export(self.manifest, self.root, self.exported)
        self.assertEqual(len(osm_stream.query(self.exported, 'GT', 'roads', text='avenida')['results']), 1)
        with self.assertRaises(ValueError): osm_stream.query(self.exported, 'ZZ', 'all')


if __name__ == '__main__': unittest.main()
