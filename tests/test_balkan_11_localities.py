"""Isolated contract tests for the 11-country source reconciliation layer."""
from __future__ import annotations

from pathlib import Path
import copy
import csv
import gzip
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import balkan_11_localities as m


class LocalityContracts(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.gn=self.root/'registries/europe/countries/RS'
        self.gn.mkdir(parents=True)
        c=self.root/'registries/europe/balkan-11'
        c.mkdir(parents=True)
        c.joinpath('sources.json').write_bytes(m.CATALOG.read_bytes())
        self.raw=[
            {'id':'gn:1','country_code':'RS','kind':'admin_subdivision','name':'Округ','parent_id':'country:RS','parent_relation':'source_country','feature_code':'ADM1','latitude':'44.8','longitude':'20.5','alternatenames':'Okrug','modification_date':'2026-10-01'},
            {'id':'gn:2','country_code':'RS','kind':'locality','name':'Нови Сад','parent_id':'gn:1','parent_relation':'source_admin_code','feature_code':'PPL','latitude':'45.2','longitude':'19.8','alternatenames':'Novi Sad','modification_date':'2026-10-01'},
            {'id':'gn:3','country_code':'RS','kind':'locality','name':'Неодлучен','parent_id':'','parent_relation':'missing_reference','feature_code':'PPL','latitude':'','longitude':'','alternatenames':'','modification_date':'2026-10-01'}]
        self.make_gn()
        self.source=self.root/'new.csv'
        self.source.write_text('code,label,cc\nA01,Ulica Železnička,RS\nA02,Šumadija,RS\n',encoding='utf-8')
        self.pin=self.make_pin()

    def make_gn(self):
        with io.StringIO(newline='') as io_out:
            writer=csv.DictWriter(io_out,fieldnames=list(self.raw[0]),lineterminator='\n')
            writer.writeheader();writer.writerows(self.raw)
            raw=io_out.getvalue().encode('utf-8')
        filename='entities-0001.csv.gz'
        with (self.gn/filename).open('wb') as f:
            with gzip.GzipFile(fileobj=f,mode='wb',mtime=0,filename='') as gz: gz.write(raw)
        pin={'bytes':(self.gn/filename).stat().st_size,'sha256':m.file_hash(self.gn/filename),
             'uncompressed_sha256':hashlib.sha256(raw).hexdigest(),'rows':len(self.raw)}
        metadata={'country':{'country':'RS'},'files':{filename:pin},'counts':{'admin_rows':1,'locality_rows':2,'other_admin_rows':0}}
        (self.gn/'metadata.json').write_text(json.dumps(metadata),encoding='utf-8')

    def make_pin(self):
        return {'schema_version':1,'country':'RS','kind':'street','format':'csv',
          'source_id':'fixture-streets','source_version':'2026-11-06','official_url':'https://www.rgz.gov.rs/address-regisrer',
          'acquired_at':'2026-11-06T10:00:00Z','rights_reviewed':True,'commercial_reuse_reviewed':True,
          'license':'synthetic fixture','filename':self.source.name,'bytes':self.source.stat().st_size,
          'sha256':m.file_hash(self.source),'coordinate_crs':'not_provided',
          'fields':{'id':'code','name':'label','country':'cc'}}

    def make_build(self,pin=None):
        pins=[]
        if pin:
            pin_file=self.root/'source-pin.json'
            pin_file.write_text(json.dumps(pin),encoding='utf-8')
            pins=[pin_file]
        db=self.root/'index.sqlite'
        return m.build(db,root=self.root,countries=('RS',),pins=pins,data_root=self.root,include_ro=False),db

    def test_catalog_scope_and_completion_protection(self):
        p=m.load_catalog(self.root/'registries/europe/balkan-11/sources.json')
        self.assertEqual(len(p['countries']),11)
        self.assertEqual(p['priority_codes'],list(m.NEW))
        self.assertEqual(p['continuation_codes'],list(m.CONTINUE))
        p['countries']['XK']['delivery_verified']=True
        f=self.root/'bad-catalog.json';f.write_text(json.dumps(p))
        with self.assertRaises(ValueError):m.load_catalog(f)

    def test_realistic_geonames_checks_and_missing_parent_stays_unresolved(self):
        result=m.audit_geonames('RS',self.root)
        self.assertEqual(result['records'],3)
        self.assertEqual(result['kinds'],{'admin_subdivision':1,'locality':2})
        self.assertEqual(result['parent_relation_counts']['missing_reference'],1)
        self.assertFalse(result['address_existence_verified'])

    def test_original_binary_hash_failure(self):
        with (self.gn/'entities-0001.csv.gz').open('ab') as f:f.write(b'changed')
        with self.assertRaises(ValueError):m.audit_geonames('RS',self.root)

    def test_source_country_cross_check(self):
        self.raw[1]['country_code']='XK'
        self.make_gn()
        with self.assertRaises(ValueError):m.audit_geonames('RS',self.root)

    def test_duplicate_original_id(self):
        self.raw[1]['id']='gn:1'
        self.make_gn()
        with self.assertRaises(ValueError):m.audit_geonames('RS',self.root)

    def test_nonexistent_asserted_parent_cannot_be_inferred_by_name(self):
        self.raw[1]['parent_id']='gn:9999'
        self.make_gn()
        with self.assertRaisesRegex(ValueError,'Unresolved asserted parent'):
            m.audit_geonames('RS',self.root)

    def test_index_build_query_unicode_no_auto_join(self):
        summary,db=self.make_build(self.pin)
        self.assertEqual(summary['indexed_records'],5)
        self.assertEqual(summary['counts']['RS:geonames'],3)
        self.assertTrue(m.verify_index(db)['status']=='PASS')
        result=m.query_index(db,'RS','НОВИ')
        self.assertEqual(result['matches'][0]['id'],'gn:2')
        name=m.query_index(db,'RS','želez',kind='street')
        self.assertEqual(name['matches'][0]['source_id'],'fixture-streets')
        self.assertEqual(name['matches'][0]['id'],'A01')
        self.assertEqual(m.query_index(db,'RS','any',kind='address')['matches'],[])

    def test_database_modified_content_detected_without_count_delta(self):
        _,db=self.make_build()
        with sqlite3.connect(db) as s:s.execute("UPDATE features SET name='altered' WHERE feature_id='gn:2'")
        with self.assertRaisesRegex(ValueError,'rows changed'):m.verify_index(db)

    def test_no_clobber_index(self):
        self.make_build()
        with self.assertRaisesRegex(ValueError,'already exists'):self.make_build()

    def test_source_pin_rights_and_hash(self):
        self.assertEqual(m.checked_pin(self.pin,self.root),self.source)
        for k,v in [('rights_reviewed',False),('commercial_reuse_reviewed',False),('license','')]:
            changed=dict(self.pin,**{k:v})
            with self.assertRaises(ValueError):m.checked_pin(changed,self.root)
        self.source.write_bytes(b'wrong')
        with self.assertRaisesRegex(ValueError,'receipt differs'):m.checked_pin(self.pin,self.root)

    def test_path_traversal_and_origin_rejected(self):
        for name in ('../secret.csv','/tmp/secret.csv'):
            with self.assertRaises(ValueError):m.checked_pin(dict(self.pin,filename=name),self.root)
        with self.assertRaises(ValueError):m.checked_pin(dict(self.pin,official_url='http://example.com/'),self.root)

    def test_cross_country_official_rows(self):
        self.source.write_text('code,label,cc\nA01,Ulica,AL\n',encoding='utf-8')
        self.pin=self.make_pin()
        with self.assertRaises(ValueError):self.make_build(self.pin)
        self.assertFalse((self.root/'index.sqlite').exists())

    def test_missing_source_field_does_not_silently_empty(self):
        self.pin['fields']={'id':'bad-column','name':'label'}
        with self.assertRaisesRegex(ValueError,'columns changed'):self.make_build(self.pin)

    def test_duplicate_ids_fail_closed(self):
        self.source.write_text('code,label,cc\nA01,Ulica,RS\nA01,Other,RS\n',encoding='utf-8')
        self.pin=self.make_pin()
        with self.assertRaisesRegex(ValueError,'Repeated source-qualified'):self.make_build(self.pin)
        self.assertFalse((self.root/'index.sqlite').exists())

    def test_zip_csv_and_json_array_can_be_reviewed_offline(self):
        zpath=self.root/'source.zip'
        with zipfile.ZipFile(zpath,'w') as z:z.write(self.source,arcname='subset.csv')
        pin=dict(self.pin,filename=zpath.name,sha256=m.file_hash(zpath),bytes=zpath.stat().st_size,
                 format='zip_csv',member='subset.csv')
        rows=list(m.source_iter(m.checked_pin(pin,self.root),pin))
        self.assertEqual(len(rows),2)
        jpath=self.root/'source.json';jpath.write_text(json.dumps({'results':[{'code':'Z1','label':'Test'}]}))
        pin=dict(self.pin,filename=jpath.name,sha256=m.file_hash(jpath),bytes=jpath.stat().st_size,
                 format='json_array',records_path=['results'],fields={'id':'code','name':'label'})
        self.assertEqual(len(list(m.source_iter(m.checked_pin(pin,self.root),pin))),1)

    def test_unknown_coordinate_crs_fails(self):
        with self.assertRaisesRegex(ValueError,'coordinate system'):
            m.checked_pin(dict(self.pin,coordinate_crs='EPSG:3765'),self.root)

    def test_source_data_never_certifies_deliverability(self):
        p=m.project_source(self.pin,{'code':'A01','label':'Ulica','cc':'RS'})
        self.assertEqual(p[0],'RS')
        self.assertEqual(p[2],'A01')
        self.assertNotIn('delivery_verified',p)

    def test_no_iso_assertion_for_kosovo(self):
        catalog=m.load_catalog(self.root/'registries/europe/balkan-11/sources.json')
        self.assertIn('ISO 3166-1',catalog['countries']['XK']['access_and_license'])

if __name__=='__main__':unittest.main()
