"""Offline DK/SE OSM address evidence contract tests; all source fixtures are synthetic."""
from pathlib import Path
import json
import importlib.util
import sqlite3
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import dk_se_open_osm as m


DK_XML = '''<?xml version="1.0" encoding="utf-8"?>
<osm version="0.6" generator="synthetic-tests">
  <node id="1" lat="55.6761" lon="12.5683">
    <tag k="addr:housenumber" v="003A"/><tag k="addr:street" v="Ågade"/>
    <tag k="addr:postcode" v="0100"/><tag k="addr:city" v="København"/>
    <tag k="contact:phone" v="DO-NOT-COPY"/><tag k="name" v="Syntetisk"/>
  </node>
  <way id="2"><nd ref="1"/><nd ref="1"/><tag k="highway" v="residential"/>
    <tag k="name" v="Ågade"/><tag k="name:da" v="Ågade"/></way>
  <relation id="3"><member type="way" ref="2" role="outer"/>
    <tag k="boundary" v="administrative"/><tag k="name" v="København"/>
    <tag k="admin_level" v="8"/></relation>
  <node id="4" lat="55.7" lon="12.4"><tag k="place" v="village"/><tag k="name" v="Mølleby"/></node>
  <node id="5" lat="55.5" lon="12.3"><tag k="highway" v="construction"/><tag k="name" v="Not current"/></node>
  <way id="6"><tag k="addr:housenumber" v="4b"/><tag k="addr:place" v="Testplace"/></way>
  <node id="7" lat="55.5" lon="12.2"><tag k="addr:housenumber" v="8"/>
    <tag k="addr:postcode" v="bad"/><tag k="addr:country" v="SE"/></node>
</osm>
'''
SE_XML = '''<?xml version="1.0" encoding="utf-8"?>
<osm version="0.6" generator="synthetic-tests">
  <node id="10" lat="57.7089" lon="11.9746"><tag k="addr:housenumber" v="10B"/>
  <tag k="addr:street" v="Älvvägen"/><tag k="addr:postcode" v="411 03"/>
  <tag k="addr:city" v="Göteborg"/></node>
  <node id="11" lat="59.3293" lon="18.0686"><tag k="place" v="city"/>
    <tag k="name" v="Stockholm"/><tag k="name:sv" v="Stockholm"/></node>
</osm>
'''


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / 'synthetic.osm'
        self.src.write_text(DK_XML, encoding='utf-8')
        self.pin = m.pin_local('DK', self.src, '2026-11-05T13:30:00+09:00', fixture=True)
        self.dbpath = self.root / 'indexed.sqlite'

    def build(self):
        return m.import_data(self.pin, self.root, self.dbpath)

    def test_pin_uses_exact_source_hash_and_preserves_original(self):
        self.assertEqual(m.validated_pin(self.pin, self.root), self.src)
        self.assertEqual(self.pin['license'], 'ODbL-1.0')
        self.assertEqual(self.pin['sha256'], m.sha256(self.src))

    def test_rejects_source_byte_tampering(self):
        self.src.write_text(DK_XML + '<!-- changed -->', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'SHA-256 differs'):
            self.build()

    def test_rejects_unauthorized_country_and_origin(self):
        x = dict(self.pin, country='NO')
        with self.assertRaises(ValueError): m.validated_pin(x, self.root)
        x = dict(self.pin, source_url='https://evil.example/europe/denmark-latest.osm.pbf')
        with self.assertRaisesRegex(ValueError, 'Unexpected extract origin'): m.validated_pin(x, self.root)
        x = dict(self.pin, source_url='http://download.geofabrik.de/europe/denmark-latest.osm.pbf')
        with self.assertRaises(ValueError): m.validated_pin(x, self.root)

    def test_rejects_wrong_country_extract_url(self):
        x = dict(self.pin, source_url=m.official_distribution_url('SE'))
        with self.assertRaises(ValueError): m.validated_pin(x, self.root)

    def test_missing_license_review_refused(self):
        for field, bad in [('rights_reviewed', False), ('license','unknown'), ('attribution','')]:
            x = dict(self.pin, **{field: bad})
            with self.assertRaises(ValueError): m.validated_pin(x, self.root)

    def test_unsafe_paths_are_rejected(self):
        x = dict(self.pin,filename='../synthetic.osm')
        with self.assertRaisesRegex(ValueError, 'Unsafe'): m.validated_pin(x, self.root)
        x = dict(self.pin,filename='/tmp/elsewhere.osm')
        with self.assertRaises(ValueError): m.validated_pin(x, self.root)

    def test_fixture_flag_required_for_osm_xml(self):
        x = dict(self.pin,fixture=False)
        with self.assertRaisesRegex(ValueError, 'test fixtures'): m.validated_pin(x, self.root)

    def test_rejects_naive_timestamp_and_invalid_size(self):
        x = dict(self.pin,acquired_at='2026-11-05')
        with self.assertRaises(ValueError): m.validated_pin(x, self.root)
        x = dict(self.pin,bytes=True)
        with self.assertRaises(ValueError): m.validated_pin(x, self.root)

    def test_postcodes_are_syntax_only(self):
        for country,good,bad in [('DK','0100','01000'),('SE','123 45','12-345')]:
            self.assertTrue(m.postcode_shape(country, good))
            self.assertFalse(m.postcode_shape(country, bad))
        self.assertTrue(m.postcode_shape('SE','12345'))
        self.assertFalse(m.postcode_shape('NO','0000'))

    def test_basic_projection_keeps_number_and_scandi_letters(self):
        report = self.build()
        self.assertEqual(report['counts']['address_candidate'], 3)
        self.assertEqual(report['counts']['named_road_segment'], 1)
        self.assertEqual(report['counts']['named_place'], 1)
        self.assertEqual(report['counts']['administrative_boundary_label'], 1)
        self.assertTrue(report['source_receipt']['fixture'])
        self.assertFalse(report['national_completeness_verified'])
        self.assertFalse(report['deliverability_verified'])
        self.assertFalse(report['postal_existence_verified'])
        row=m.search(self.dbpath,'address_candidate',text='københavn')['results'][0]
        self.assertEqual(row['street'], 'Ågade')
        self.assertEqual(row['house_number'],'003A')
        self.assertEqual(row['postcode'],'0100')
        self.assertEqual((row['lon'],row['lat']),(12.5683,55.6761))
        self.assertNotIn('contact:phone',row['source_tags'])

    def test_unicode_casefold_and_postal_search(self):
        self.build()
        self.assertEqual(len(m.search(self.dbpath,'address_candidate',text='KØBENHAVN')['results']),1)
        self.assertEqual(len(m.search(self.dbpath,'address_candidate',postcode='0100')['results']),1)
        self.assertEqual(len(m.search(self.dbpath,'named_road_segment',text='ÅGADE')['results']),1)

    def test_no_way_or_relation_coordinate_invention(self):
        self.build()
        road=m.search(self.dbpath,'named_road_segment')['results'][0]
        self.assertIsNone(road['lat'])
        self.assertEqual(road['location_quality'],'not_asserted')
        boundary=m.search(self.dbpath,'administrative_boundary_label')['results'][0]
        self.assertIsNone(boundary['lon'])

    def test_country_conflict_flag_and_invalid_postcode_retained(self):
        report=self.build()
        self.assertEqual(report['counts']['country_tag_conflict'],1)
        rows=m.search(self.dbpath,'address_candidate')['results']
        self.assertTrue(any(x['postcode_shape']=='syntax_invalid' for x in rows))

    def test_proposed_road_not_included(self):
        self.build()
        self.assertEqual(m.search(self.dbpath,'named_road_segment',text='Not current')['results'],[])

    def test_no_overwrite(self):
        self.build()
        with self.assertRaisesRegex(ValueError,'overwrite'): self.build()
        self.assertEqual(m.verify_index(self.dbpath)['status'],'PASS')

    def test_rejects_tampered_report_counts(self):
        self.build()
        with sqlite3.connect(self.dbpath) as db:
            report=json.loads(db.execute("select value from metadata where key='report'").fetchone()[0])
            report['indexed_records'] += 1
            db.execute('update metadata set value=? where key=\'report\'',(m.canonical(report),))
        with self.assertRaises(ValueError): m.verify_index(self.dbpath)

    def test_mutating_projected_row_without_count_change_fails(self):
        self.build()
        with sqlite3.connect(self.dbpath) as db:
            db.execute("UPDATE features SET street='fake' WHERE category='address_candidate' AND osm_ref='osm:node:1'")
        with self.assertRaisesRegex(ValueError, 'Projected source evidence changed'):
            m.verify_index(self.dbpath)

    def test_query_wildcards_are_literals(self):
        self.build()
        self.assertEqual(m.search(self.dbpath,'named_road_segment',text='%')['results'],[])
        self.assertEqual(m.search(self.dbpath,'named_road_segment',text='_')['results'],[])

    def test_unsupported_queries_and_limit(self):
        self.build()
        with self.assertRaises(ValueError): m.search(self.dbpath,'officially_verified')
        with self.assertRaises(ValueError): m.search(self.dbpath,'address_candidate',limit=101)

    def test_duplicate_osm_identity_fails(self):
        self.src.write_text(DK_XML.replace('</osm>','<node id="1" lat="55" lon="13"><tag k="addr:housenumber" v="1"/></node></osm>'))
        self.pin=m.pin_local('DK',self.src,'2026-11-05T13:30:00+09:00',fixture=True)
        with self.assertRaises(sqlite3.IntegrityError): self.build()
        self.assertFalse(self.dbpath.exists())

    def test_dtd_rejected(self):
        self.src.write_bytes(b'<!DOCTYPE foo [<!ENTITY x "bad">]>' + DK_XML.encode())
        self.pin=m.pin_local('DK',self.src,'2026-11-05T13:30:00+09:00',fixture=True)
        with self.assertRaisesRegex(ValueError,'DTD'):self.build()
        self.assertFalse(self.dbpath.exists())

    def test_truncated_xml_fails_without_partial_publishing(self):
        self.src.write_text(DK_XML[:-7])
        self.pin=m.pin_local('DK',self.src,'2026-11-05T13:30:00+09:00',fixture=True)
        with self.assertRaises(ET.ParseError): self.build()
        self.assertFalse(self.dbpath.exists())

    def test_swedish_fixture_preserves_postal_lexeme(self):
        self.src.write_text(SE_XML,encoding='utf-8')
        self.pin=m.pin_local('SE',self.src,'2026-11-05T13:30:00+09:00',fixture=True)
        self.build()
        rows=m.search(self.dbpath,'address_candidate',text='göteborg')['results']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['postcode'],'411 03')
        self.assertEqual(rows[0]['house_number'],'10B')
        self.assertEqual(len(m.search(self.dbpath,'address_candidate',postcode='41103')['results']),1)

    @unittest.skipUnless(importlib.util.find_spec('osmium') is not None, 'pyosmium optional PBF reader not installed')
    def test_libosmium_xml_callback_contract(self):
        out = []
        m.stream_pbf(self.src, lambda *row: out.extend(m.evidence_rows('DK', *row)))
        self.assertEqual(len(out), 6)
        self.assertEqual(out[0][1], 'osm:node:1')

    @unittest.skipUnless(importlib.util.find_spec('osmium') is not None, 'pyosmium required for binary round trip')
    def test_real_pbf_binary_roundtrip_for_source_pipeline(self):
        import osmium
        binary = self.root / 'synthetic.osm.pbf'
        with osmium.SimpleWriter(str(binary)) as writer:
            writer.add_node(osmium.osm.mutable.Node(
                id=201, location=(12.5683, 55.6761),
                tags={'addr:street': 'Ågade', 'addr:housenumber': '0007', 'addr:postcode': '0100'}))
            writer.add_way(osmium.osm.mutable.Way(
                id=202, nodes=[201,201], tags={'highway': 'residential', 'name': 'Ågade'}))
        self.pin = m.pin_local('DK', binary, '2026-11-05T13:30:00+09:00', fixture=True)
        result = m.import_data(self.pin, self.root, self.dbpath)
        self.assertEqual(result['counts']['address_candidate'], 1)
        self.assertEqual(result['counts']['named_road_segment'], 1)
        self.assertEqual(m.verify_index(self.dbpath)['status'], 'PASS')
        self.assertEqual(m.search(self.dbpath,'address_candidate')['results'][0]['house_number'],'0007')

    def test_projection_drops_personal_tags_and_keeps_source_namespace(self):
        rows=m.evidence_rows('SE','node',10,{'addr:housenumber':'5','name:sv':'Åker', 'contact:email':'private@example.com'},11,57)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][1],'osm:node:10')
        self.assertNotIn('private@example.com',str(rows))

    def test_missing_number_is_not_a_complete_address(self):
        rows=m.evidence_rows('DK','way',22,{'addr:street':'Allé','highway':'residential','name':'Allé'})
        self.assertEqual({x[0] for x in rows},{'named_road_segment'})

    def test_nonpositive_identity_rejected(self):
        for value in (0,-1,'xxx',None):
            with self.assertRaises(ValueError): m.evidence_rows('DK','node',value,{'place':'town','name':'x'})

    def test_invalid_coordinate_is_not_recorded(self):
        self.assertIsNone(m.evidence_rows('SE','node',10,{'addr:housenumber':'1'},1000,250)[0][11])
        self.assertEqual(m.evidence_rows('SE','way',10,{'addr:housenumber':'1'},11,57)[0][13],'not_asserted')


if __name__=='__main__':
    unittest.main()
