import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('osm_evidence',ROOT/'scripts/osm_evidence.py')
evidence=importlib.util.module_from_spec(spec);spec.loader.exec_module(evidence)


class EvidenceSemantics(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');evidence.schema(self.db)
        for code in ['GT','BZ']:
            self.db.execute('INSERT INTO sources VALUES(?,?,?,?)',(code,'test-'+code,'{}','{}'))
    def tearDown(self):self.db.close()
    def put(self,cc='GT',version=1,tags=None,geometry_status='complete'):
        return evidence.store_object(self.db,cc,'way','1',version,'2026-10-20T00:00:00Z',tags or {'highway':'residential','name':'Calle 100%_A'}, {'nodes':['1','2']}, {'type':'LineString','coordinates':[[0,0],[1,1]]},geometry_status)
    def test_cross_extract_identity_is_preserved(self):
        self.put();self.put('BZ')
        report=evidence.summarize(self.db)
        self.assertEqual(report['counts']['objects'],1)
        self.assertEqual(report['counts']['observations'],2)
        self.assertFalse(report['extract_membership_is_legal_country_membership'])
    def test_different_versions_are_not_overwritten(self):
        self.put();self.put('BZ',version=2)
        self.assertEqual(evidence.summarize(self.db)['counts']['ids_with_multiple_payloads'],1)
    def test_housenumber_is_not_expanded_or_officially_verified(self):
        self.put(tags={'addr:housenumber':'0001-0009','addr:unit':'B'})
        row=evidence.query(self.db,'GT','address-numbers')['results'][0]
        self.assertEqual(row['tags']['addr:housenumber'],'0001-0009')
        self.assertEqual(row['tags']['addr:unit'],'B')
        self.assertEqual(len(evidence.query(self.db,'GT','address-numbers')['results']),1)
        self.assertFalse(evidence.summarize(self.db)['house_numbers_are_issuing_authority_verified'])
    def test_interpolation_is_a_separate_feature(self):
        self.put(tags={'addr:interpolation':'even'})
        report=evidence.summarize(self.db)['extracts'][1]
        self.assertEqual(report['interpolation_features'],1)
        self.assertEqual(report['house_number_tag_observations'],0)
    def test_lifecycle_roads_are_not_current_roads(self):
        for tags in [{'highway':'construction'},{'highway':'residential','disused:highway':'residential'},{'proposed:highway':'primary'}]:
            flag=evidence.classify('way',tags)
            self.assertTrue(flag['selected']);self.assertNotEqual(flag['road_state'],'active_tag')
    def test_unnamed_road_is_retained(self):
        self.put(tags={'highway':'track'})
        report=evidence.summarize(self.db)['extracts'][1]
        self.assertEqual(report['active_road_way_records'],1)
        self.assertEqual(report['named_road_way_records'],0)
    def test_traffic_signal_node_is_not_counted_as_road(self):
        self.assertFalse(evidence.classify('node',{'highway':'traffic_signals'})['selected'])
    def test_incomplete_geometry_does_not_drop_feature(self):
        self.put(geometry_status='missing_node_locations_or_short_way')
        report=evidence.summarize(self.db)['extracts'][1]
        self.assertEqual(report['active_road_way_records'],1)
        self.assertEqual(report['active_road_ways_with_missing_geometry'],1)
    def test_query_treats_wildcards_as_literal(self):
        self.put()
        self.assertEqual(len(evidence.query(self.db,'GT','roads',text='100%_A')['results']),1)
        self.assertEqual(evidence.query(self.db,'GT','roads',text="' OR 1=1 --")['results'],[])
    def test_unknown_extract_is_rejected(self):
        with self.assertRaises(ValueError):evidence.query(self.db,'MX','all')


class SourceIntegrity(unittest.TestCase):
    def test_corruption_blocks_import(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'raw').write_bytes(b'changed')
            manifest={'scope_codes':['GT'],'sources':[{'country_extract':'GT','path':'raw','bytes':7,'sha256':hashlib.sha256(b'correct').hexdigest()}]}
            with self.assertRaises(ValueError):list(evidence.verified_sources(manifest,root))
    def test_source_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest={'scope_codes':['GT'],'sources':[{'country_extract':'GT','path':'../outside','bytes':0,'sha256':'0'*64}]}
            with self.assertRaises(ValueError):list(evidence.verified_sources(manifest,directory))
    def test_existing_database_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'accepted.sqlite';path.write_bytes(b'accepted')
            with self.assertRaises(ValueError):evidence.build({},directory,path)
            self.assertEqual(path.read_bytes(),b'accepted')
    def test_real_xml_geometry_and_relation_members(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'test.osm'
            source.write_text('''<osm version="0.6" generator="test">
            <node id="1" version="1" lat="14.0" lon="-90.0"><tag k="addr:housenumber" v="0007"/></node>
            <node id="2" version="1" lat="14.1" lon="-90.1"/>
            <way id="3" version="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way>
            <way id="4" version="1"><nd ref="1"/><nd ref="999"/><tag k="highway" v="track"/></way>
            <relation id="5" version="1"><member type="way" ref="3" role="outer"/><tag k="boundary" v="administrative"/><tag k="admin_level" v="6"/></relation>
            </osm>''')
            receipt={'country_extract':'GT','source_id':'test','path':source.name,'bytes':source.stat().st_size,'sha256':evidence.file_hash(source)}
            report=evidence.build({'scope_codes':['GT'],'sources':[receipt]},root,root/'new.sqlite')
            self.assertEqual(report['counts']['objects'],4)
            self.assertEqual(report['extracts'][0]['active_road_ways_with_missing_geometry'],1)
            with sqlite3.connect(root/'new.sqlite') as db:
                road=evidence.query(db,'GT','roads',identifier='osm:way:3')['results'][0]
                self.assertEqual(road['topology']['nodes'],['1','2'])
                self.assertEqual(road['geometry']['coordinates'],[[-90.0,14.0],[-90.1,14.1]])
                rel=evidence.query(db,'GT','administrative')['results'][0]
                self.assertEqual(rel['topology']['members'],[{'type':'w','ref':'3','role':'outer'}])
                self.assertIsNone(rel['geometry'])
            sys.path.insert(0,str(ROOT/'scripts'))
            import verify_osm_evidence
            replay=verify_osm_evidence.verify({'scope_codes':['GT'],'sources':[receipt]},root,root/'new.sqlite')
            self.assertEqual(replay['matched_observations'],4)
            import zlib
            with sqlite3.connect(root/'new.sqlite') as db:
                original_geometry=db.execute("SELECT geometry_zlib FROM objects WHERE id='osm:way:3'").fetchone()[0]
                changed_geometry=zlib.compress(b'{"type":"LineString","coordinates":[[0,0],[1,1]]}')
                db.execute("UPDATE objects SET geometry_zlib=? WHERE id='osm:way:3'",(changed_geometry,))
            with self.assertRaisesRegex(ValueError,'payload hash'):
                verify_osm_evidence.verify({'scope_codes':['GT'],'sources':[receipt]},root,root/'new.sqlite')
            with sqlite3.connect(root/'new.sqlite') as db:
                db.execute("UPDATE objects SET geometry_zlib=? WHERE id='osm:way:3'",(original_geometry,))
                db.execute("UPDATE objects SET tags_json='{}' WHERE id='osm:way:3'")
            with self.assertRaises(ValueError):
                verify_osm_evidence.verify({'scope_codes':['GT'],'sources':[receipt]},root,root/'new.sqlite')


if __name__=='__main__':unittest.main()
