"""Offline synthetic contract tests for ES/PT/MT high-precision source intake."""
from __future__ import annotations
import csv
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import es_pt_mt_precision as m

class AddressPrecisionContracts(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)
        self.repo=self.root/'repo';self.repo.mkdir()
        self.input=self.root/'raw';self.input.mkdir()
        self.output=self.root/'out.sqlite'
        for c in m.COUNTRIES:
            folder=self.repo/'registries'/'europe'/'countries'/c;folder.mkdir(parents=True)
            rows=['id,name,country_code,kind,latitude,longitude,parent_id,admin_level,admin2_code\n',
                  f'gn:{dict(ES=2,PT=3,MT=4)[c]},Å Coruña,{c},locality,40.2,-3.7,country:{c},,01\n']
            raw=''.join(rows).encode()
            with gzip.open(folder/'entities-0001.csv.gz','wb') as z:z.write(raw)
            (folder/'metadata.json').write_text(json.dumps({'source':'GeoNames','country':{'country':c},
                'files':{'entities-0001.csv.gz':{'bytes':(folder/'entities-0001.csv.gz').stat().st_size,
                'sha256':m.file_sha(folder/'entities-0001.csv.gz'),
                'uncompressed_sha256':hashlib.sha256(raw).hexdigest(),'rows':1}}}))

    def receipt(self,c='ES',kind='address',format='csv',path='sample.csv',fields=None,**overrides):
        source=self.input/path
        doc={'schema_version':1,'country':c,'kind':kind,'dataset':'cartociudad-2026',
             'publisher_url':'https://www.cartociudad.es/web/portal','rights_reviewed':True,
             'license':'CC-BY-4.0 compatible','attribution':'Source: CNIG CartoCiudad',
             'source_date':'2026-04-01','crs':'EPSG:4326','format':format,'path':path,
             'bytes':source.stat().st_size,'sha256':m.file_sha(source),
             'fields':fields or {'id':'id','street':'street','house_number':'num','postcode':'pc','locality':'locality'}}
        doc.update(overrides)
        return doc

    def csv(self,text='id,street,num,pc,locality\n0001,Calle Niño,0007,28001,Madrid\n0002,Rúa do Sol,3A,15001,A Coruña\n'):
        (self.input/'sample.csv').write_text(text,encoding='utf-8')

    def test_postcodes_lexical_and_syntax_only(self):
        for c,good,bad in [('ES','01001','0100'),('PT','1000-001','1000-1'),('MT','VLT 1117','VLT111')]:
            self.assertTrue(m.raw_postcode(c,good)['syntax_valid'])
            self.assertFalse(m.raw_postcode(c,bad)['syntax_valid'])
            self.assertIsNone(m.raw_postcode(c,good)['exists'])
        self.assertTrue(m.raw_postcode('MT','VLT1117')['syntax_valid'])
        self.assertFalse(m.raw_postcode('ES','28001 ')['syntax_valid'])

    def test_existing_all_countries_are_audited_and_indexed(self):
        report=m.build(self.repo,self.output)
        self.assertEqual(report['total_observations'],3)
        self.assertEqual(m.verify(self.output)['status'],'PASS')
        self.assertEqual(len(m.search(self.output,'PT','Å Coruña')['results']),1)
        self.assertFalse(report['national_address_completeness_verified'])
        self.assertEqual(m.search(self.output,'ES')['results'][0]['postcode'],'')

    def test_official_csv_id_and_strings_not_coerced(self):
        self.csv()
        r=self.receipt()
        receipt=self.input/'receipt.json';receipt.write_text(json.dumps(r))
        result=m.build(self.repo,self.output,receipts=[receipt],source_root=self.input)
        self.assertEqual(result['total_observations'],5)
        rows=m.search(self.output,'ES',kind='address',postcode='28001')['results']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['house_number'],'0007')
        self.assertEqual(rows[0]['source_ref'],'official:ES:cartociudad-2026:0001')
        self.assertEqual(rows[0]['street'],'Calle Niño')
        self.assertEqual(rows[0]['postcode_syntax'],'valid_shape')
        self.assertEqual(m.verify(self.output)['status'],'PASS')

    def test_duplicate_source_identity_fails_no_output(self):
        self.csv('id,street,num,pc,locality\n1,A,2,28001,Madrid\n1,B,3,28001,Madrid\n')
        r=self.receipt();rc=self.input/'receipt.json';rc.write_text(json.dumps(r))
        with self.assertRaises(sqlite3.IntegrityError):m.build(self.repo,self.output,receipts=[rc],source_root=self.input)
        self.assertFalse(self.output.exists())

    def test_source_modification_and_license_fail_closed(self):
        self.csv();r=self.receipt()
        (self.input/'sample.csv').write_text('changed')
        with self.assertRaises(ValueError):m._validate_receipt(r,self.input)
        self.csv();r=self.receipt(rights_reviewed=False)
        with self.assertRaisesRegex(ValueError,'license'):m._validate_receipt(r,self.input)

    def test_malformed_source_and_unsafe_path(self):
        self.csv();r=self.receipt()
        for bad in ('../sample.csv','/tmp/secrets.csv'):
            with self.assertRaises(ValueError):m._validate_receipt(dict(r,path=bad),self.input)
        with self.assertRaisesRegex(ValueError,'mapping'):m._validate_receipt(dict(r,fields={}),self.input)
        with self.assertRaisesRegex(ValueError,'HTTPS'):m._validate_receipt(dict(r,publisher_url='http://illegal.test'),self.input)
        with self.assertRaisesRegex(ValueError,'CRS'):m._validate_receipt(dict(r,crs='unknown'),self.input)

    def test_zip_csv_and_malformed_zip(self):
        self.csv();raw=(self.input/'sample.csv').read_bytes()
        zipfile=self.input/'sample.zip'
        with zipfile_open(zipfile) as z:z.writestr('actual.csv',raw)
        r=self.receipt(format='zip-csv',path='sample.zip',member='actual.csv')
        self.assertEqual(len(list(m.source_rows(zipfile,r))),2)
        with self.assertRaises(ValueError):m._validate_receipt(dict(r,member='../actual.csv'),self.input)

    def test_jsonl_reading(self):
        p=self.input/'rows.jsonl';p.write_text('{"id":"0009","name":"Il-Belt Valletta"}\n')
        r=self.receipt(c='MT',kind='locality',format='jsonl',path='rows.jsonl',fields={'id':'id','name':'name'})
        r['dataset']='malta-address-registrar'
        self.assertEqual(m._official_row(r,list(m.source_rows(p,r))[0])[4],'Il-Belt Valletta')

    def test_geojson_point_preserves_geometry_no_assumed_building(self):
        p=self.input/'pt.geojson';p.write_text(json.dumps({'type':'FeatureCollection','features':[{'type':'Feature','properties':{'key':'x','street':'Rua da Lua','door':'5'},'geometry':{'type':'Point','coordinates':[-9.11,38.7]}}]}))
        r=self.receipt(c='PT',format='geojson',path='pt.geojson',fields={'id':'key','street':'street','house_number':'door'})
        record=next(m.source_rows(p,r))
        row=m._official_row(r,record)
        self.assertEqual(row[14:16],(-9.11,38.7))

    def test_gpkg_read_only_and_nonnative_crs(self):
        gpkg=self.input/'sample.gpkg';d=sqlite3.connect(gpkg)
        d.execute('CREATE TABLE gpkg_contents (table_name TEXT,srs_id INTEGER)')
        d.execute('CREATE TABLE gpkg_geometry_columns (table_name TEXT,column_name TEXT,srs_id INTEGER)')
        d.execute('CREATE TABLE cont_freguesias(dtmnfr TEXT,freguesia TEXT,geom BLOB)')
        d.execute('INSERT INTO gpkg_contents VALUES(?,?)',('cont_freguesias',3763))
        d.execute('INSERT INTO gpkg_geometry_columns VALUES(?,?,?)',('cont_freguesias','geom',3763))
        point=b'GP'+bytes([0,1])+struct.pack('<i',3763)+bytes([1])+struct.pack('<I',1)+struct.pack('<dd',-90745.5,-102350.25)
        d.execute('INSERT INTO cont_freguesias VALUES(?,?,?)',('010101','Freguesia de Teste',point));d.commit();d.close()
        r=self.receipt(c='PT',kind='administrative',format='gpkg',path='sample.gpkg',dataset='caop-2025',table='cont_freguesias',
                       crs='EPSG:3763',fields={'id':'dtmnfr','name':'freguesia'})
        row=next(m.source_rows(gpkg,r))
        actual=m._official_row(r,row)
        self.assertEqual(actual[14:17],(-90745.5,-102350.25,'EPSG:3763'))
        self.assertEqual(actual[0],'official:PT:caop-2025:010101')
        with self.assertRaises(ValueError):list(m.source_rows(gpkg,dict(r,crs='EPSG:4326')))

    def test_gpkg_rejects_identifier_injection(self):
        self.csv();r=self.receipt(format='gpkg',table='table; DROP TABLE anything')
        with self.assertRaises(ValueError):m._validate_receipt(r,self.input)

    def test_verify_detects_tampered_counts(self):
        m.build(self.repo,self.output)
        with sqlite3.connect(self.output) as db:
            old=json.loads(db.execute('SELECT value FROM metadata WHERE key="report"').fetchone()[0])
            old['total_observations']+=1
            db.execute('UPDATE metadata SET value=? WHERE key="report"',(m.canonical(old),))
        with self.assertRaisesRegex(ValueError,'count'):m.verify(self.output)

    def test_baseline_hash_mismatch_refused(self):
        bad=self.repo/'registries'/'europe'/'countries'/'MT'/'entities-0001.csv.gz'
        with bad.open('ab') as f:f.write(b'x')
        with self.assertRaises(ValueError):m.build(self.repo,self.output)
        self.assertFalse(self.output.exists())

    def test_source_namespace_not_merged_with_geonames(self):
        self.csv('id,street,num,pc,locality\ngn:2,Calle Uno,11,28001,Madrid\n')
        r=self.receipt();p=self.input/'r.json';p.write_text(json.dumps(r))
        m.build(self.repo,self.output,receipts=[p],source_root=self.input)
        a=m.search(self.output,'ES',kind='address')['results']
        b=m.search(self.output,'ES',kind='locality')['results']
        self.assertEqual(a[0]['source_ref'],'official:ES:cartociudad-2026:gn:2')
        self.assertTrue(b[0]['source_ref'].startswith('gn:'))

    def test_no_overwrite(self):
        m.build(self.repo,self.output)
        with self.assertRaisesRegex(ValueError,'already exists'):m.build(self.repo,self.output)

    def test_missing_address_components_refused(self):
        self.csv('id,street,num,pc,locality\n1,,,28001,\n')
        r=self.receipt();p=self.input/'receipt.json';p.write_text(json.dumps(r))
        with self.assertRaisesRegex(ValueError,'components'):m.build(self.repo,self.output,receipts=[p],source_root=self.input)

    def test_invalid_coordinate_refused(self):
        self.csv('id,street,num,pc,locality,x,y\n1,Rua A,1,1000-001,Lisboa,NaN,20\n')
        r=self.receipt(c='PT',fields={'id':'id','street':'street','house_number':'num','x':'x','y':'y'})
        with self.assertRaisesRegex(ValueError,'Nonfinite'):list(m._official_row(r,row) for row in m.source_rows(self.input/'sample.csv',r))

    def test_rejects_numeric_ids_or_postcodes_that_could_lose_zeroes(self):
        r={'country':'ES','dataset':'cartociudad-test','kind':'address','crs':'EPSG:4326',
           'fields':{'id':'id','street':'street','house_number':'num','postcode':'pc'}}
        for bad in ({'id':123,'street':'Calle','num':'2','pc':'01001'},
                    {'id':'001','street':'Calle','num':'2','pc':1001},
                    {'id':'001','street':'Calle','num':2,'pc':'01001'}):
            with self.assertRaisesRegex(ValueError,'lexical'):m._official_row(r,bad)

    def test_tampering_same_row_count_detected_by_digest(self):
        m.build(self.repo,self.output)
        with sqlite3.connect(self.output) as db:
            db.execute("UPDATE observations SET name='Forgered' WHERE source_ref='gn:2'")
        with self.assertRaisesRegex(ValueError,'digest'):m.verify(self.output)

    def test_like_wildcards_cannot_match_everything(self):
        m.build(self.repo,self.output)
        self.assertEqual(m.search(self.output,'MT',phrase='%')['results'],[])
        self.assertEqual(m.search(self.output,'PT',phrase='_')['results'],[])

    def test_gpkg_geometry_that_is_not_point_never_gets_coords(self):
        data=b'GP'+bytes([0,1])+struct.pack('<i',4326)+bytes([1])+struct.pack('<I',3)+b'000000000000000000000000'
        self.assertIsNone(m._read_point(data))


def zipfile_open(path):
    return zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED)

if __name__=='__main__':unittest.main()
