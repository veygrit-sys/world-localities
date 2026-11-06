"""Source-isolated Eastern Europe integrity, rights and candidate ingestion contracts."""
from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import eastern_four_localities as m


class EastFourTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        catalog=self.root/'registries/europe/eastern-four'
        catalog.mkdir(parents=True)
        catalog.joinpath('sources.json').write_bytes(m.CATALOG.read_bytes())
        self.folder=self.root/'registries/europe/countries/MD'
        self.folder.mkdir(parents=True)
        self.gn=[
            {'id':'gn:11','country_code':'MD','kind':'admin_subdivision','name':'Raion','alternatenames':'Район',
             'parent_id':'country:MD','parent_relation':'source_country','latitude':'47','longitude':'28',
             'feature_code':'ADM1','modification_date':'2025-01-01','state_id':'gn:11'},
            {'id':'gn:12','country_code':'MD','kind':'locality','name':'Chișinău','alternatenames':'Кишинёв,Chisinau',
             'parent_id':'gn:11','parent_relation':'source_admin_code','latitude':'47.02','longitude':'28.8',
             'feature_code':'PPLC','modification_date':'2025-01-01','state_id':'gn:11'},
            {'id':'gn:13','country_code':'MD','kind':'locality','name':'Găgăuzia','alternatenames':'',
             'parent_id':'','parent_relation':'missing_code','latitude':'','longitude':'',
             'feature_code':'PPL','modification_date':'2024-01-01','state_id':''}
        ]
        self.make_gn()
        self.off=self.root/'cuatm.csv'
        self.off.write_text('id,name,code,postcode\n001234,Bălți,MD,MD-3100\n001235,Orhei,MD,MD-3500\n',encoding='utf-8')
        self.pin=self.make_pin()

    def make_gn(self):
        b=io.StringIO(newline='')
        writer=csv.DictWriter(b,fieldnames=list(self.gn[0]),lineterminator='\n')
        writer.writeheader();writer.writerows(self.gn)
        csvblob=b.getvalue().encode('utf-8')
        path=self.folder/'entities-0001.csv.gz'
        with path.open('wb') as f:
            with gzip.GzipFile(fileobj=f,mode='wb',filename='',mtime=0) as z:z.write(csvblob)
        meta={'country':{'country':'MD'},'files':{'entities-0001.csv.gz':
               {'rows':len(self.gn),'bytes':path.stat().st_size,'sha256':m.sha256(path),
                'uncompressed_sha256':hashlib.sha256(csvblob).hexdigest()}},
              'counts':{'admin_rows':1,'locality_rows':2,'other_admin_rows':0}}
        self.folder.joinpath('metadata.json').write_text(json.dumps(meta),encoding='utf-8')

    def make_pin(self):
        return {'schema_version':1,'country':'MD','kind':'locality','format':'csv',
                'source_id':'md-bns-cuatm-fixture','snapshot_version':'2025',
                'acquired_at':'2026-11-06T11:00:00Z','source_url':'https://statistica.gov.md/example/cuatm.csv',
                'code_scheme':'CUATM','rights_reviewed':True,'commercial_reuse_reviewed':True,
                'license':'synthetic-only-test','filename':self.off.name,'bytes':self.off.stat().st_size,
                'sha256':m.sha256(self.off),'coordinate_crs':'not_provided',
                'field_map':{'id':'id','name':'name','country':'code','postcode':'postcode'}}

    def make_build(self,pin=None):
        pins=[]
        if pin:
            f=self.root/'pin.json';f.write_text(json.dumps(pin),encoding='utf-8');pins=[f]
        out=self.root/'output.sqlite'
        return m.build(('MD',),out,root=self.root,pins=pins,source_root=self.root),out

    def test_catalog_has_exact_scope_and_no_completion(self):
        cat=m.load_catalog(self.root/'registries/europe/eastern-four/sources.json')
        self.assertEqual(list(cat['countries']),list(m.CODES))
        cat['countries']['RU']['deliverability_verified']=True
        bad=self.root/'bad.json';bad.write_text(json.dumps(cat),encoding='utf-8')
        with self.assertRaises(ValueError):m.load_catalog(bad)

    def test_full_geo_audit_preserves_unresolved_without_guessing(self):
        result=m.audit_country('MD',self.root)
        self.assertEqual(result['rows'],3)
        self.assertEqual(result['parent_relations']['missing_code'],1)
        self.assertFalse(result['official_country_hierarchy_verified'])

    def test_original_gzip_hash_mismatch(self):
        with (self.folder/'entities-0001.csv.gz').open('ab') as out:out.write(b'tamper')
        with self.assertRaisesRegex(ValueError,'Original GeoNames bytes changed'):
            m.audit_country('MD',self.root)

    def test_cross_country_geo_row_rejected(self):
        self.gn[1]['country_code']='UA';self.make_gn()
        with self.assertRaisesRegex(ValueError,'Cross-country'):
            m.audit_country('MD',self.root)

    def test_duplicate_geo_id_rejected(self):
        self.gn[1]['id']='gn:11';self.make_gn()
        with self.assertRaisesRegex(ValueError,'Duplicate GeoNames'):
            m.audit_country('MD',self.root)

    def test_invalid_asserted_parent_rejected(self):
        self.gn[1]['parent_id']='gn:999';self.make_gn()
        with self.assertRaisesRegex(ValueError,'Asserted GeoNames parent'):
            m.audit_country('MD',self.root)

    def test_build_index_and_search_unicode(self):
        summary,p=self.make_build(self.pin)
        self.assertEqual(summary['counts'],{'MD:geonames':3,'MD:md-bns-cuatm-fixture':2})
        self.assertEqual(m.verify(p)['indexed_records'],5)
        res=m.query(p,'MD',text='CHIȘ')['matches']
        self.assertEqual(res[0]['feature_id'],'gn:12')
        src=m.query(p,'MD',text='BĂLȚI',source='md-bns-cuatm-fixture')['matches']
        self.assertEqual(src[0]['feature_id'],'001234')
        self.assertEqual(src[0]['postcode'],'MD-3100')
        self.assertEqual(src[0]['postal_shape'],'syntax_valid')

    def test_source_not_automatically_joined_by_name(self):
        _,p=self.make_build(self.pin)
        with sqlite3.connect(p) as db:
            pairs=list(db.execute('SELECT source_id,feature_id FROM features WHERE country="MD"'))
        self.assertEqual(len(pairs),5)
        self.assertIn(('geonames','gn:12'),pairs)
        self.assertIn(('md-bns-cuatm-fixture','001235'),pairs)

    def test_sqlite_tamper_digest_fails(self):
        _,p=self.make_build()
        with sqlite3.connect(p) as db:
            db.execute('UPDATE features SET name="replaced" WHERE feature_id="gn:12"')
        with self.assertRaisesRegex(ValueError,'Indexed source observations changed'):
            m.verify(p)

    def test_build_immutable_and_failed_build_no_publish(self):
        self.make_build()
        with self.assertRaisesRegex(ValueError,'already exists'):self.make_build()
        self.off.write_text('id,name,code,postcode\n001234,A,UA,MD-3100\n',encoding='utf-8')
        self.pin=self.make_pin()
        self.root.joinpath('output.sqlite').unlink()
        with self.assertRaisesRegex(ValueError,'Official country code differs'):
            self.make_build(self.pin)
        self.assertFalse(self.root.joinpath('output.sqlite').exists())

    def test_pin_rights_hash_domain_path(self):
        self.assertEqual(m.validate_pin(self.pin,self.root),self.off)
        for field,value in [('rights_reviewed',False),('commercial_reuse_reviewed',False),('license','')]:
            with self.assertRaises(ValueError):m.validate_pin(dict(self.pin,**{field:value}),self.root)
        for url in ('http://statistica.gov.md/x.csv','https://evil.example/x.csv','https://user:pass@statistica.gov.md/x'):
            with self.assertRaises(ValueError):m.validate_pin(dict(self.pin,source_url=url),self.root)
        for filename in ('../private.csv','/tmp/private.csv'):
            with self.assertRaises(ValueError):m.validate_pin(dict(self.pin,filename=filename),self.root)
        self.off.write_text(self.off.read_text()+'extra')
        with self.assertRaisesRegex(ValueError,'bytes differ'):
            m.validate_pin(self.pin,self.root)

    def test_native_code_formats_preserve_zeros(self):
        for scheme,codes in [('CUATM',['001234']),('KATOTTG',['UA01000000000013043']),('SOATO',['0101000000']),('GAR_OBJECTID',['001']),('OKATO',['01000000000'])]:
            for value in codes:self.assertEqual(m.validate_id_scheme(scheme,value),value)
        for scheme,bad in [('KATOTTG','UA01000'),('SOATO','1001'),('GAR_OBJECTID','x-12')]:
            with self.assertRaises(ValueError):m.validate_id_scheme(scheme,bad)

    def test_katottg_cannot_be_tagged_russia(self):
        sample=dict(self.pin,country='RU',code_scheme='KATOTTG',source_url='https://www.nalog.gov.ru/test.csv')
        with self.assertRaises(ValueError):m.validate_pin(sample,self.root)

    def test_zip_csv_and_bad_zip_path(self):
        archive=self.root/'part.zip'
        with zipfile.ZipFile(archive,'w') as z:z.write(self.off,arcname='region.csv')
        pin=dict(self.pin,filename=archive.name,bytes=archive.stat().st_size,sha256=m.sha256(archive),format='zip_csv',member='region.csv')
        self.assertEqual(len(list(m.source_rows(m.validate_pin(pin,self.root),pin))),2)
        bad=dict(pin,member='../secret.csv')
        with self.assertRaises(ValueError):list(m.source_rows(m.validate_pin(bad,self.root),bad))

    def test_gar_xml_regions_stream_and_do_not_certify_address(self):
        x=self.root/'gar.zip'
        with zipfile.ZipFile(x,'w') as z:z.writestr('01/AS_ADDR_OBJ.XML',
            '<ADDRESSOBJECTS><OBJECT OBJECTID="001" NAME="улица Ленина" STATUS="1" />'
            '<OBJECT OBJECTID="002" NAME="Новая улица" STATUS="0" /></ADDRESSOBJECTS>')
        pin=dict(self.pin,country='RU',kind='street',code_scheme='GAR_OBJECTID',source_url='https://www.nalog.gov.ru/gar/',
                 source_id='FNS-regional-fixture',filename=x.name,bytes=x.stat().st_size,sha256=m.sha256(x),
                 format='zip_xml',member='01/AS_ADDR_OBJ.XML',record_tag='OBJECT',
                 field_map={'id':'OBJECTID','name':'NAME','status':'STATUS'})
        rows=list(m.source_rows(m.validate_pin(pin,self.root),pin))
        self.assertEqual(len(rows),2)
        projection=m.official_projection(pin,rows[0])
        self.assertEqual(projection[2],'001')
        self.assertFalse(m.postal_shape('RU','invalid'))
        self.assertEqual(projection[13],'1')
        bad=dict(pin,record_tag='DOCTYPE')
        with self.assertRaises(ValueError):m.validate_pin(dict(bad,record_tag='0Bad'),self.root)

    def test_xml_dtd_prohibited(self):
        p=self.root/'entity.zip'
        with zipfile.ZipFile(p,'w') as z:z.writestr('a.xml','<!DOCTYPE root [<!ENTITY x "bad">]><root/>')
        pin=dict(self.pin,country='RU',code_scheme='GAR_OBJECTID',source_url='https://www.nalog.gov.ru/',kind='street',
                 filename=p.name,bytes=p.stat().st_size,sha256=m.sha256(p),format='zip_xml',member='a.xml',
                 record_tag='OBJECT',field_map={'id':'OBJECTID','name':'NAME'})
        with self.assertRaisesRegex(ValueError,'DTD'):
            list(m.source_rows(m.validate_pin(pin,self.root),pin))

    def test_json_records_path_explicit(self):
        src=self.root/'a.json'
        src.write_text('{"results":[{"id":"12345","name":"Test"}]}',encoding='utf-8')
        pin=dict(self.pin,filename=src.name,bytes=src.stat().st_size,sha256=m.sha256(src),format='json_array',records_path=['results'],
                 field_map={'id':'id','name':'name'})
        self.assertEqual(len(list(m.source_rows(m.validate_pin(pin,self.root),pin))),1)

    def test_xlsx_numeric_code_refused(self):
        try:from openpyxl import Workbook
        except ImportError:self.skipTest('optional workbook parser not installed')
        path=self.root/'test.xlsx'
        book=Workbook();sheet=book.active;sheet.title='Codes'
        sheet.append(['id','name'])
        sheet.append([101,'Kyiv'])
        book.save(path)
        pin=dict(self.pin,country='UA',source_url='https://data.gov.ua/dataset/katottg',code_scheme='KATOTTG',
                 format='xlsx',filename=path.name,bytes=path.stat().st_size,sha256=m.sha256(path),sheet='Codes',
                 field_map={'id':'id','name':'name'})
        with self.assertRaisesRegex(ValueError,'numeric'):
            list(m.source_rows(m.validate_pin(pin,self.root),pin))

    def test_xlsx_text_code_preserves_ua_identifier(self):
        try:from openpyxl import Workbook
        except ImportError:self.skipTest('optional workbook parser not installed')
        path=self.root/'official-fixture.xlsx'
        book=Workbook();sheet=book.active;sheet.title='KATOTTG'
        sheet.append(['code','native_name'])
        sheet.append(['UA01000000000013043','Автономна Республіка Крим'])
        book.save(path)
        pin=dict(self.pin,country='UA',source_url='https://data.gov.ua/dataset/katottg',code_scheme='KATOTTG',
                 kind='administrative',format='xlsx',filename=path.name,bytes=path.stat().st_size,sha256=m.sha256(path),
                 sheet='KATOTTG',field_map={'id':'code','name':'native_name'})
        rows=list(m.source_rows(m.validate_pin(pin,self.root),pin))
        self.assertEqual(rows[0]['code'],'UA01000000000013043')
        self.assertEqual(m.official_projection(pin,rows[0])[2],'UA01000000000013043')

    def test_duplicate_official_code_refuses_immutable_publication(self):
        self.off.write_text('id,name,code,postcode\n001234,Bălți,MD,MD-3100\n001234,Repeated,MD,MD-3500\n',encoding='utf-8')
        pin=self.make_pin()
        with self.assertRaisesRegex(ValueError,'Duplicate source-qualified official identifier'):
            self.make_build(pin)
        self.assertFalse((self.root/'output.sqlite').exists())

    def test_postcode_format_is_not_existence(self):
        self.assertTrue(m.postal_shape('MD','MD-2001'))
        self.assertTrue(m.postal_shape('UA','01001'))
        self.assertTrue(m.postal_shape('BY','220000'))
        self.assertTrue(m.postal_shape('RU','101000'))
        self.assertFalse(m.postal_shape('RU','MD-2001'))
        _,p=self.make_build()
        self.assertFalse(m.query(p,'MD')['deliverability_verified'])

    def test_cross_country_query_rejected(self):
        _,p=self.make_build()
        with self.assertRaises(ValueError):m.query(p,'ZZ')
        with self.assertRaises(ValueError):m.build(('MD','MD'),self.root/'extra.sqlite',root=self.root)
        self.assertEqual(m.query(p,'MD',text='%')['matches'],[])


if __name__=='__main__':unittest.main()
