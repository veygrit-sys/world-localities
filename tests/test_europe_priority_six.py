"""Network-free contracts for six-country official source intake."""
import csv
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
import europe_priority_six as m


class SixCountryTests(unittest.TestCase):
    def setUp(self):
        self.context=tempfile.TemporaryDirectory()
        self.addCleanup(self.context.cleanup)
        self.root=Path(self.context.name)
        self.csv=self.root/'rs.csv'
        self.csv.write_text('uid;street;number;name;postcode\n0007;Тестна улица;12А;Београд;11000\n0008;Другa;24;Београд;11001\n',encoding='utf-8')
        self.pin=self.make_pin('RS','address',self.csv,{'id':'uid','street':'street','house_number':'number','name':'name','postcode':'postcode'})
        self.index=self.root/'output.sqlite'

    def make_pin(self,country,kind,path,fields,fmt='csv',**extra):
        pin={'schema_version':1,'country':country,'kind':kind,'format':fmt,
             'source':'test-'+country,'source_version':'fixture-1',
             'official_url':'https://data.gov.rs/sr/datasets/adresni-registar/',
             'downloaded_at':'2026-11-05T00:00:00Z','rights_reviewed':True,'license_name':'CC-BY-4.0',
             'filename':path.name,'bytes':path.stat().st_size,'sha256':m.file_hash(path),
             'fields':fields,'coordinate_crs':'not_provided','delimiter':';'}
        return pin|extra

    def test_registry_has_exact_six_codes(self):
        self.assertEqual(set(m.load_catalog()['countries']),set(m.COUNTRIES))

    def test_unknown_country_refused(self):
        self.pin['country']='DE'
        with self.assertRaises(ValueError):m.index_official(self.pin,self.root,self.index)

    def test_csv_source_replay_and_identity(self):
        result=m.index_official(self.pin,self.root,self.index)
        self.assertEqual(result['records'],2)
        self.assertEqual(result['kind_counts'],{'address':2})
        self.assertFalse(result['deliverability_verified'])
        rows=m.query(self.index,'Београд')['results']
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['house_number'],'12А')
        self.assertEqual(rows[0]['source_id'],'0007')

    def test_index_non_overwrite(self):
        m.index_official(self.pin,self.root,self.index)
        with self.assertRaisesRegex(ValueError,'overwrite'):m.index_official(self.pin,self.root,self.index)

    def test_source_mutation_fails(self):
        self.csv.write_text(self.csv.read_text()+'\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'byte pin'):m.index_official(self.pin,self.root,self.index)
        self.assertFalse(self.index.exists())

    def test_casefold_search_hungarian_and_serbian(self):
        self.pin['country']='HU'
        m.index_official(self.pin,self.root,self.index)
        self.assertEqual(len(m.query(self.index,'БЕОГРАД')['results']),2)
        self.assertFalse(m.query(self.index,'NEPOSTOJEĆE')['results'])

    def test_duplicate_ids_fail_and_no_index_published(self):
        self.csv.write_text('uid;street;number;name;postcode\n0007;A;1;City;1234\n0007;B;2;City;1234\n',encoding='utf-8')
        self.pin=self.make_pin('RS','address',self.csv,self.pin['fields'])
        with self.assertRaisesRegex(ValueError,'Duplicate source ID'):m.index_official(self.pin,self.root,self.index)
        self.assertFalse(self.index.exists())

    def test_missing_mapped_header_fails(self):
        self.pin['fields']['id']='not_a_column'
        with self.assertRaisesRegex(ValueError,'Source schema changed'):m.index_official(self.pin,self.root,self.index)

    def test_explicit_license_review_mandatory(self):
        self.pin['rights_reviewed']=False
        with self.assertRaisesRegex(ValueError,'rights'):m.index_official(self.pin,self.root,self.index)

    def test_invalid_paths_and_symlink_escape_fail(self):
        for name in ('../rs.csv','/tmp/rs.csv'):
            self.pin['filename']=name
            with self.assertRaises(ValueError):m.index_official(self.pin,self.root,self.index)

    def test_european_encoding_cyrillic_and_greek(self):
        data=m.project(self.pin,{'uid':'0001','street':'Αθήνα','number':'4β','name':'Αθήνα','postcode':'12345'},1)
        self.assertEqual(data[3],'0001')
        self.assertEqual(data[10],'4β')
        self.assertEqual(data[9],'Αθήνα')

    def test_ro_postal_zero_is_missing(self):
        pin=self.pin|{'country':'RO'}
        row=m.project(pin,{'uid':'0001','street':'str','number':'7','name':'City','postcode':'0'},1)
        self.assertEqual(row[11],'')

    def test_italian_snc_number_kept_if_provided(self):
        pin=self.pin|{'country':'IT'}
        row=m.project(pin,{'uid':'0003','street':'Via Roma','number':'SNC','name':'Roma','postcode':'00100'},1)
        self.assertEqual(row[10],'SNC')
        self.assertEqual(row[11],'00100')

    def test_partial_coordinate_rejected(self):
        pin=self.pin|{'coordinate_crs':'EPSG:4326','fields':self.pin['fields']|{'latitude':'lat'}}
        with self.assertRaisesRegex(ValueError,'Partial coordinate'):m.project(pin,{'uid':'2','street':'S','number':'3','name':'X','postcode':'1234','lat':'50'},1)

    def test_injected_column_rejected(self):
        pin=self.pin|{'fields':{'id':'uid','house_number':'number','password':'password'}}
        with self.assertRaises(ValueError):m.index_official(pin,self.root,self.index)

    def test_zip_csv_and_unicode(self):
        with zipfile.ZipFile(self.root/'source.zip','w') as z:z.writestr('data.csv',self.csv.read_bytes())
        pin=self.make_pin('RS','address',self.root/'source.zip',self.pin['fields'],'zip_csv',member='data.csv')
        result=m.index_official(pin,self.root,self.index)
        self.assertEqual(result['records'],2)

    def test_zip_member_path_traversal_refused(self):
        with zipfile.ZipFile(self.root/'source.zip','w') as z:z.writestr('../data.csv',self.csv.read_bytes())
        pin=self.make_pin('RS','address',self.root/'source.zip',self.pin['fields'],'zip_csv',member='../data.csv')
        with self.assertRaisesRegex(ValueError,'Unsafe'):m.index_official(pin,self.root,self.index)

    def test_json_array_with_explicit_nested_path(self):
        f=self.root/'records.json'
        f.write_text(json.dumps({'data':{'items':[{'ekatte':'00001','name':'София','parent':'SOF46'}]}}),encoding='utf-8')
        pin=self.make_pin('BG','locality',f,{'id':'ekatte','name':'name','parent_id':'parent'},'json_array',records_path=['data','items'])
        result=m.index_official(pin,self.root,self.index)
        self.assertEqual(result['records'],1)
        self.assertEqual(m.query(self.index,'София')['results'][0]['parent_id'],'SOF46')

    def test_json_non_array_rejected(self):
        f=self.root/'records.json'
        f.write_text(json.dumps({'data':{'other':{}}}))
        pin=self.make_pin('BG','locality',f,{'id':'ekatte','name':'name'},'json_array',records_path=['data','other'])
        with self.assertRaises(ValueError):m.index_official(pin,self.root,self.index)

    def test_geopackage_metadata_rows_without_geometry(self):
        source=self.root/'sample.gpkg'
        db=sqlite3.connect(source)
        db.execute('CREATE TABLE addresses (id TEXT, name TEXT, number TEXT, geom BLOB)')
        db.execute('INSERT INTO addresses VALUES (?,?,?,?)',('0001','Belgrade','12',b'no-geometry-extraction'))
        db.commit();db.close()
        pin=self.make_pin('RS','address',source,{'id':'id','name':'name','house_number':'number'},'gpkg',table='addresses')
        result=m.index_official(pin,self.root,self.index)
        self.assertEqual(result['records'],1)
        self.assertEqual(m.query(self.index,'Belgrade')['results'][0]['source_id'],'0001')

    def test_reject_unsafe_sqlite_table_name(self):
        self.pin['format']='gpkg';self.pin['table']='addresses; DROP TABLE features'
        with self.assertRaisesRegex(ValueError,'table'):m.index_official(self.pin,self.root,self.index)

    def test_siruta_parent_and_levels_with_synthetic_example(self):
        f=self.root/'ro.csv'
        f.write_text(','.join(m.RO_FIELDS)+'\n'+'10,JUDEȚUL ALBA,0,1,1,40,1,0,7,1,RO121,\n'
                     +'100,ORAȘ,51000,1,10,2,2,1,7,1,RO121,RO_100\n'
                     +'1001,SAT,0,1,100,3,3,3,7,1,RO121,\n',encoding='utf-8')
        report=m.audit_ro(f,strict=False)
        self.assertEqual(report['classification']['total'],3)
        self.assertEqual(report['classification']['county'],1)
        self.assertEqual(report['classification']['locality'],1)

    def test_missing_siruta_parent_rejected(self):
        f=self.root/'ro.csv'
        f.write_text(','.join(m.RO_FIELDS)+'\n'+'10,JUDEȚUL ALBA,0,1,1,40,1,0,7,1,RO121,\n'
                     +'100,ORAȘ,51000,1,999,2,2,1,7,1,RO121,RO_100\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Missing/self Romanian parent'):m.audit_ro(f,strict=False)

    def test_source_parent_is_unverified_unless_ro_source(self):
        r=m.index_official(self.pin,self.root,self.index)
        self.assertTrue(r['unverified_parent_refs'])

    def test_percent_query_not_sql_wildcard(self):
        m.index_official(self.pin,self.root,self.index)
        self.assertFalse(m.query(self.index,'%')['results'])


if __name__=='__main__':unittest.main()
