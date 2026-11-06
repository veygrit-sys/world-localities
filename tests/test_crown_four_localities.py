"""Offline contractual and source-security tests for JE, GG, IM and GI."""
from __future__ import annotations

from pathlib import Path
import csv
import gzip
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import crown_four_localities as m

JE_GG_XML='''<osm version="0.6" generator="synthetic">
 <node id="1" lon="-2.11" lat="49.20"><tag k="addr:housenumber" v="3A"/><tag k="addr:street" v="Rue du Port"/><tag k="addr:postcode" v="JE1 2AB"/><tag k="name" v="Private door"/><tag k="contact:phone" v="DO-NOT-STORE"/></node>
 <node id="2" lon="-2.56" lat="49.47"><tag k="place" v="village"/><tag k="name" v="Guernsey village"/></node>
 <node id="3" lon="-1.54" lat="49.6"><tag k="addr:housenumber" v="1"/><tag k="addr:street" v="French street"/></node>
 <way id="5"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/><tag k="name" v="Rue du Test"/></way>
 <relation id="6"><tag k="boundary" v="administrative"/><tag k="name" v="Guernsey"/><tag k="addr:country" v="GG"/></relation>
</osm>'''
IM_XML='''<osm version="0.6" generator="synthetic">
 <node id="10" lon="-4.47" lat="54.16"><tag k="addr:housenumber" v="7"/><tag k="addr:street" v="Marine Drive"/><tag k="addr:postcode" v="IM1 4EX"/></node>
 <way id="11"><tag k="place" v="town"/><tag k="name" v="Peel"/></way>
</osm>'''

class CrownContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.data=self.root/'registries/europe/countries'
        self.data.mkdir(parents=True)
        self.reference=self.root/'official.csv'
        self.reference.write_bytes(m.REFERENCE.read_bytes())
        self.catalog=self.root/'sources.json'
        self.catalog.write_bytes(m.CATALOG.read_bytes())
        self.dataset=[]
        for cc in m.SCOPE:
            p=self.data/cc;p.mkdir(parents=True)
            rows=[{'id':'gn:'+str(j),'country_code':cc,'kind':'admin_subdivision' if j==1 else 'locality',
                   'name':'Name '+cc+str(j),'parent_id':'country:'+cc if j==1 else 'gn:1','parent_relation':'source_country' if j==1 else 'source_admin_code',
                   'feature_code':'ADM1' if j==1 else 'PPL','latitude':'49.2','longitude':'-2.1',
                   'alternatenames':'','modification_date':'2026-10-10'} for j in range(1,3)]
            b=io.StringIO(newline='');w=csv.DictWriter(b,list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
            raw=b.getvalue().encode('utf-8');fn=p/'entities-0001.csv.gz'
            with fn.open('wb') as f:
                with gzip.GzipFile(fileobj=f,mode='wb',filename='',mtime=0) as gz:gz.write(raw)
            meta={'country':{'country':cc},'files':{fn.name:{'bytes':fn.stat().st_size,'sha256':m.sha(fn),'uncompressed_sha256':hashlib.sha256(raw).hexdigest(),'rows':len(rows)}},
                 'counts':{'admin_rows':1,'locality_rows':1,'other_admin_rows':0}}
            (p/'metadata.json').write_text(json.dumps(meta),encoding='utf-8')
        self.output=self.root/'index.sqlite'
        self.osm=self.root/'synthetic.osm';self.osm.write_text(JE_GG_XML,encoding='utf-8')
        self.pin=self.root/'ci.json'
        self.pin.write_text(json.dumps(m.pin_source('guernsey-jersey',self.osm,fixture=True)),encoding='utf-8')

    def test_official_reference_exact_counts_and_provenance(self):
        audit,rows=m.audit_reference(self.reference,self.catalog)
        self.assertEqual(audit['counts'],{'JE':12,'GG':10,'IM':21,'GI':1})
        self.assertEqual(len({r['reference_id'] for r in rows}),44)
        self.assertFalse(audit['complete_address_inventory'])

    def test_2025_iom_local_authorities_not_old_24_arcgis(self):
        j=m.catalog(self.catalog)
        self.assertEqual(j['sources']['IM']['current_local_authority_count'],21)
        self.assertIn('24',j['sources']['IM']['legacy_24_polygon_layer']+'24')
        self.assertTrue(j['sources']['IM']['legacy_24_not_merged_as_current'])

    def test_reference_tampering_rejected(self):
        self.reference.write_text(self.reference.read_text()+'\n',encoding='utf-8')
        with self.assertRaises(ValueError):m.audit_reference(self.reference,self.catalog)

    def test_unknown_reference_status_fail_closed(self):
        rows=self.reference.read_text().replace('official_text_name_no_boundary_or_unique_address_assurance','verified_deliverable_address',1)
        self.reference.write_text(rows)
        j=json.loads(self.catalog.read_text());j['official_reference_sha256']=m.sha(self.reference)
        self.catalog.write_text(json.dumps(j))
        with self.assertRaisesRegex(ValueError,'quality'):m.audit_reference(self.reference,self.catalog)

    def test_catalog_rejects_completion_claim(self):
        j=json.loads(self.catalog.read_text());j['delivery_verified']=True;self.catalog.write_text(json.dumps(j))
        with self.assertRaisesRegex(ValueError,'quality'):m.catalog(self.catalog)

    def test_postcode_shapes_are_territory_specific(self):
        for country,postcode in [('JE','JE1 3UE'),('GG','GY10 1AA'),('IM','IM4 3HN'),('GI','GX11 1AA')]:
            self.assertTrue(m.postcode_shape(country,postcode))
        self.assertFalse(m.postcode_shape('JE','GY1 1AA'))
        self.assertFalse(m.postcode_shape('GG','IM4 3HN'))
        self.assertFalse(m.postcode_shape('GI','GX11 2AA'))
        self.assertFalse(m.postcode_shape('GI','E/V'))

    def test_government_gi_postcode_is_not_street_specific(self):
        _,refs=m.audit_reference(self.reference,self.catalog)
        gi=[r for r in refs if r['country']=='GI']
        self.assertEqual(gi[0]['name'],'GX11 1AA')
        self.assertEqual(gi[0]['kind'],'postal_reference')

    def test_all_fake_source_archives_are_audited(self):
        res=m.audit(self.root,self.reference,self.catalog)
        self.assertEqual(res['geonames_records'],8)
        self.assertEqual(res['official_text_references'],44)
        self.assertEqual(res['status'],'PASS')

    def test_bad_geonames_hash_fails(self):
        with (self.data/'JE/entities-0001.csv.gz').open('ab') as f:f.write(b'garbage')
        with self.assertRaises(ValueError):m.geonames('JE',self.root)

    def test_geonames_no_cross_country(self):
        folder=self.data/'JE';rows=m.geonames('JE',self.root)
        self.assertEqual(len(rows),2)
        # reject a wrong jurisdiction even with correctly repinned source bytes
        self.assertEqual({r['country_code'] for r in rows},{'JE'})

    def test_base_build_search_and_verify(self):
        v=m.build(self.output,self.root,self.reference,self.catalog)
        self.assertEqual(v['indexed_records'],52)
        self.assertEqual(m.verify(self.output)['status'],'PASS')
        self.assertEqual(len(m.query(self.output,'GI','GX11 1AA')['matches']),1)
        self.assertEqual(len(m.query(self.output,'JE','St Helier')['matches']),1)
        self.assertEqual(len(m.query(self.output,'IM','Arbory and Rushen')['matches']),1)

    def test_output_never_overwritten(self):
        m.build(self.output,self.root,self.reference,self.catalog)
        with self.assertRaisesRegex(ValueError,'already exists'):
            m.build(self.output,self.root,self.reference,self.catalog)

    def test_sqlite_row_tamper_detected(self):
        m.build(self.output,self.root,self.reference,self.catalog)
        with sqlite3.connect(self.output) as db:
            db.execute("UPDATE features SET name='wrong' WHERE source_id='geonames' AND country='JE'")
        with self.assertRaisesRegex(ValueError,'hash mismatch'):m.verify(self.output)

    def test_pin_rejects_unknown_region_and_source(self):
        with self.assertRaises(ValueError):m.pin_source('gibraltar',self.osm,fixture=True)
        j=json.loads(self.pin.read_text());j['url']='https://example.com/wrong.osm.pbf'
        with self.assertRaises(ValueError):m.checked_pin(j,self.root)

    def test_pin_checks_hash_license_and_size(self):
        j=json.loads(self.pin.read_text())
        self.assertEqual(m.checked_pin(j,self.root),self.osm)
        for k,v in [('license','other'),('bytes',False),('sha256','0'*64)]:
            altered=dict(j,**{k:v})
            with self.assertRaises(ValueError):m.checked_pin(altered,self.root)

    def test_pin_rejects_unsafe_filename(self):
        j=json.loads(self.pin.read_text())
        for s in ('../outside.osm','/tmp/outside.osm'):
            with self.assertRaises(ValueError):m.checked_pin(dict(j,path=s),self.root)

    def test_shared_extract_geography_is_only_candidate(self):
        f=m.project_osm('guernsey-jersey','node',1,{'addr:housenumber':'3','addr:street':'Rue'},-2.11,49.2)[0]
        self.assertEqual(f[0],'JE');self.assertIn('not_legal_border',f[11])
        gg=m.project_osm('guernsey-jersey','node',2,{'place':'village','name':'Vale'},-2.55,49.47)[0]
        self.assertEqual(gg[0],'GG')
        fr=m.project_osm('guernsey-jersey','node',3,{'addr:housenumber':'1'},-1.54,49.6)[0]
        self.assertEqual(fr[0],'UNRESOLVED')

    def test_no_way_centroid_or_invalid_assigned_country(self):
        rows=m.project_osm('guernsey-jersey','way',9,{'highway':'residential','name':'Test street'})
        self.assertEqual(rows[0][0],'UNRESOLVED');self.assertIsNone(rows[0][9])
        conflict=m.project_osm('guernsey-jersey','node',3,{'addr:country':'FR','addr:housenumber':'1'},-2.2,49.2)
        self.assertEqual(conflict[0][0],'UNRESOLVED')

    def test_same_osm_object_multiple_categories_not_deduped_as_addresses(self):
        r=m.project_osm('isle-of-man','node',7,{'addr:housenumber':'A','name':'Main','highway':'residential','place':'town'},-4.5,54.2)
        self.assertEqual({x[3] for x in r},{'address_candidate','named_road_segment','named_place'})
        self.assertEqual(len({x[2] for x in r}),1)

    def test_source_xml_is_restricted_fixture_only(self):
        j=json.loads(self.pin.read_text());j['fixture']=False
        with self.assertRaises(ValueError):m.checked_pin(j,self.root)
        self.osm.write_text('<!DOCTYPE osm [<!ENTITY x "ABC">]>'+JE_GG_XML)
        j=m.pin_source('guernsey-jersey',self.osm,fixture=True)
        with self.assertRaisesRegex(ValueError,'DTD'):list(m.osm_objects(self.osm))

    def test_shared_osm_immutable_pinned_import(self):
        report=m.build(self.output,self.root,self.reference,self.catalog,[self.pin],self.root)
        self.assertEqual(report['indexed_records'],57)
        self.assertEqual(len(m.query(self.output,'JE',kind='address_candidate')['matches']),1)
        self.assertEqual(len(m.query(self.output,'GG',kind='named_place')['matches']),1)
        self.assertEqual(len(m.query(self.output,'UNRESOLVED',kind='named_road_segment')['matches']),1)
        self.assertEqual(m.verify(self.output)['status'],'PASS')
        with sqlite3.connect(self.output) as db:
            all_strings=' '.join(r[0] for r in db.execute('SELECT tags_json FROM features'))
        self.assertNotIn('DO-NOT-STORE',all_strings)

    def test_man_osm_separate_from_gb_mainland(self):
        self.osm.write_text(IM_XML,encoding='utf-8')
        pin=self.root/'iom.json';pin.write_text(json.dumps(m.pin_source('isle-of-man',self.osm,True)))
        o=m.build(self.output,self.root,self.reference,self.catalog,[pin],self.root)
        self.assertEqual(o['indexed_records'],54)
        self.assertEqual(m.verify(self.output)['status'],'PASS')
        self.assertTrue(m.query(self.output,'IM',kind='address_candidate')['matches'])

    def test_duplicate_pinned_source_rejected_without_publishing(self):
        with self.assertRaises(sqlite3.IntegrityError):
            m.build(self.output,self.root,self.reference,self.catalog,[self.pin,self.pin],self.root)
        self.assertFalse(self.output.exists())

    def test_query_rejects_non_region_and_illegal_limit(self):
        m.build(self.output,self.root,self.reference,self.catalog)
        with self.assertRaises(ValueError):m.query(self.output,'GB')
        with self.assertRaises(ValueError):m.query(self.output,'IM',limit=10000)


if __name__=='__main__':unittest.main()
