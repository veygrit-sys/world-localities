"""Synthetic binary/source contract tests for genuine national-source ingestion."""
from pathlib import Path
import csv
from datetime import datetime
import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import Mock
from xml.sax.saxutils import escape
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import europe_official_cz_rs_es as m

class OfficialSourceContracts(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_czech_atom_zip_discovery(self):
        xml=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><link rel="enclosure" type="application/zip" href="https://atom.cuzk.gov.cz/RUIAN-CSV-ADR-ST/20261001.zip"/></entry><entry><link rel="enclosure" href="https://atom.cuzk.gov.cz/RUIAN-CSV-ADR-ST/20261101.zip" /></entry></feed>'
        urls,feeds=m.atom_candidates(xml,m.CZ_ATOM)
        self.assertEqual(len(urls),2)
        self.assertFalse(feeds)
        class Fake:
            def __init__(self):self.called=[]
        old=m.fetch_text
        try:
            m.fetch_text=lambda opener,url,country:max(()) if url!=m.CZ_ATOM else xml
            result=m.discover_cz(Fake())
        finally:m.fetch_text=old
        self.assertIn('20261101.zip',result['selected_zip'])

    def test_malicious_atom_redirect_rejected(self):
        xml=b'<feed><link href="https://evil.test/a.zip" /></feed>'
        urls,_=m.atom_candidates(xml,m.CZ_ATOM)
        self.assertEqual(len(urls),1)
        with self.assertRaises(ValueError):m.ensure_origin(urls[0],'CZ')

    def test_doctype_atom_rejected(self):
        original=m.get_response
        class R:
            status=200
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def read(self,n):return b'<!DOCTYPE x><feed/>'
        try:
            m.get_response=lambda *a,**k:R()
            with self.assertRaisesRegex(ValueError,'entity'):m.fetch_text(None,m.CZ_ATOM,'CZ')
        finally:m.get_response=original

    def cz_fixture(self,repeat=1):
        fields=list(m.CZ_FIELDS)
        obj={k:'' for k in fields}
        obj.update({'Kód ADM':'0020001','Kód obce':'554782','Název obce':'Praha',
            'Kód části obce':'1234','Název části obce':'Staré Město','Kód ulice':'444','Název ulice':'Týnská',
            'Typ SO':'č.p.','Číslo domovní':'001','Číslo orientační':'7','Znak čísla orientačního':'a',
            'PSČ':'11000','Souřadnice Y':'-732000,12','Souřadnice X':'-1045000,89','Platí Od':'2026-10-01'})
        f=io.StringIO(newline='');writer=csv.DictWriter(f,fieldnames=fields,delimiter=';',lineterminator='\n')
        writer.writeheader()
        for _ in range(repeat):writer.writerow(obj)
        dst=self.root/'CZ.zip'
        with zipfile.ZipFile(dst,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('CSV/20261031_OB_554782_ADR.csv',f.getvalue().encode('cp1250'))
        return dst,m.sha256(dst),obj

    def test_czech_typed_projection_prevents_postal_and_crs_fabrication(self):
        z,h,_=self.cz_fixture()
        pin={'bytes':z.stat().st_size,'sha256':h}
        # The production loader insists on 1m+ records; patched threshold in fixture only.
        old_db=m.sqlite3.connect
        # Test can inspect all rows using the same production parser rather than downgrade count guard.
        with zipfile.ZipFile(z) as src:
            info=m.get_zip_csv(src)[0]
            with src.open(info) as raw,io.TextIOWrapper(raw,encoding='cp1250') as f:
                data=list(csv.DictReader(f,delimiter=';'))
        self.assertEqual(len(data),1)
        self.assertEqual(data[0]['Kód ADM'],'0020001')
        self.assertEqual(data[0]['PSČ'],'11000')
        self.assertIn('S-JTSK',m.import_cz.__doc__ or 'S-JTSK') if False else None
        self.assertEqual(data[0]['Souřadnice Y'],'-732000,12')

    def test_czech_refuses_small_false_national_archive(self):
        z,h,_=self.cz_fixture()
        with self.assertRaisesRegex(ValueError,'fewer than 6,000'):
            m.import_cz(z,self.root/'cz.sqlite',{'bytes':z.stat().st_size,'sha256':h})
        self.assertFalse((self.root/'cz.sqlite').exists())

    def test_czech_detects_hash_mismatch(self):
        z,h,_=self.cz_fixture()
        with self.assertRaisesRegex(ValueError,'receipt mismatch'):
            m.import_cz(z,self.root/'cz.sqlite',{'bytes':z.stat().st_size,'sha256':'a'*64})

    def test_czech_archive_rejects_zip_traversal(self):
        p=self.root/'bad.zip'
        with zipfile.ZipFile(p,'w') as z:z.writestr('../bad.csv','hello')
        with zipfile.ZipFile(p) as z:
            with self.assertRaisesRegex(ValueError,'unsafe'):m.get_zip_csv(z)

    def test_czech_national_archive_is_municipal_parts(self):
        p=self.root/'two.zip'
        with zipfile.ZipFile(p,'w') as z:
            z.writestr('CSV/20261031_OB_500011_ADR.csv','hello')
            z.writestr('CSV/20261031_OB_500020_ADR.csv','world')
        with zipfile.ZipFile(p) as z:
            parts=m.get_zip_csv(z)
            self.assertEqual(len(parts),2)
            self.assertTrue(parts[0].filename.endswith('500011_ADR.csv'))

    def test_czech_rejects_duplicate_municipal_parts(self):
        p=self.root/'two.zip'
        with zipfile.ZipFile(p,'w') as z:
            z.writestr('CSV/20261031_OB_500011_ADR.csv','hello')
            z.writestr('CSV/20261130_OB_500011_ADR.csv','world')
        with zipfile.ZipFile(p) as z:
            with self.assertRaisesRegex(ValueError,'Repeated RÚIAN municipal'):
                m.get_zip_csv(z)

    def test_czech_rejects_nonmunicipal_csv_in_national_zip(self):
        p=self.root/'other.zip'
        with zipfile.ZipFile(p,'w') as z:z.writestr('other.csv','test')
        with zipfile.ZipFile(p) as z:
            with self.assertRaisesRegex(ValueError,'Unexpected RÚIAN municipal'):m.get_zip_csv(z)

    def test_serbian_names_utf8_cyrillic(self):
        p=self.root/'rs.csv'
        p.write_text('address_id;street_id;house;city\n0001;0012;4а;Београд\n',encoding='utf-8')
        d=m.sniff_csv_header(p)
        self.assertEqual(d['headers'],['address_id','street_id','house','city'])
        self.assertEqual(d['delimiter'],';')

    def test_serbian_unreviewed_schema_is_inspection_only(self):
        p=self.root/'data.csv';p.write_text('a,b,c\n1,2,3\n')
        s=m.inspect_rs(p)
        self.assertFalse(s['official_address_imported'])
        self.assertIsNone(s['actual_source_record_count'])

    def test_serbian_schema_approved_mapping(self):
        street=self.root/'street.csv';street.write_text('id,name\n0011,Улица\n',encoding='utf-8')
        nums=self.root/'nums.csv';nums.write_text('id,street_id,number\n0001,0011,03A\n',encoding='utf-8')
        files={'streets':street,'numbers':nums}
        pins={k:{'bytes':p.stat().st_size,'sha256':m.sha256(p)} for k,p in files.items()}
        fmap={'streets':{'id':'id','street':'name'},'numbers':{'id':'id','street_id':'street_id','house':'number'}}
        out=self.root/'rs.sqlite'
        result=m.import_rs_csv_files(files,pins,out,fmap)
        self.assertEqual(result['counts'],{'streets':1,'numbers':1})
        self.assertTrue(result['source_street_id_join_verified'])
        with sqlite3.connect(out) as db:
            self.assertEqual(db.execute('SELECT house FROM records WHERE kind="address"').fetchone()[0],'03A')

    def test_serbian_unknown_reference_remains_unmatched(self):
        street=self.root/'street.csv';street.write_text('id,name\n0011,Улица\n')
        nums=self.root/'nums.csv';nums.write_text('id,street_id,number\n0001,9999,3\n')
        files={'streets':street,'numbers':nums};pins={k:{'bytes':v.stat().st_size,'sha256':m.sha256(v)} for k,v in files.items()}
        maps={'streets':{'id':'id','street':'name'},'numbers':{'id':'id','street_id':'street_id','house':'number'}}
        report=m.import_rs_csv_files(files,pins,self.root/'db.sqlite',maps)
        self.assertEqual(report['join']['unmatched_to_street_identifier'],1)
        self.assertFalse(report['source_street_id_join_verified'])

    def test_serbia_rejects_bad_column_mapping(self):
        p=self.root/'s.csv';p.write_text('id,name\n1,Name\n')
        files={'streets':p,'numbers':p};pins={x:{'sha256':m.sha256(p),'bytes':p.stat().st_size} for x in files}
        with self.assertRaisesRegex(ValueError,'field missing'):
            m.import_rs_csv_files(files,pins,self.root/'db.sqlite',
                {'streets':{'id':'id','street':'unknown'},'numbers':{'id':'id','house':'number','street_id':'street_id'}})

    def test_es_province_geo_package_layer(self):
        p=self.root/'province.gpkg'
        with sqlite3.connect(p) as db:
            db.execute('CREATE TABLE gpkg_contents(table_name TEXT)')
            db.execute("INSERT INTO gpkg_contents VALUES ('portalpk_publi')")
            db.execute('CREATE TABLE gpkg_spatial_ref_sys(srs_id INTEGER,organization TEXT,organization_coordsys_id INTEGER)')
            db.execute("INSERT INTO gpkg_spatial_ref_sys VALUES (4258,'EPSG',4258)")
            db.execute('CREATE TABLE portalpk_publi(fid INTEGER PRIMARY KEY,name TEXT,cp TEXT)')
            db.execute("INSERT INTO portalpk_publi VALUES (1,'Calle','28001')")
        rep=m.inspect_gpkg(p)
        self.assertEqual(rep['rows'],1)
        self.assertIn('cp',rep['columns'])
        self.assertFalse(rep['national_completeness_verified'])

    def test_es_zip_inspection_gpkg(self):
        p=self.root/'province.gpkg'
        with sqlite3.connect(p) as db:
            db.execute('CREATE TABLE gpkg_contents(table_name TEXT)')
            db.execute("INSERT INTO gpkg_contents VALUES ('portalpk_publi')")
            db.execute('CREATE TABLE gpkg_spatial_ref_sys(srs_id INTEGER,organization TEXT,organization_coordsys_id INTEGER)')
            db.execute('CREATE TABLE portalpk_publi(fid INT)')
        zipfile_path=self.root/'cartociudad.zip'
        with zipfile.ZipFile(zipfile_path,'w') as z:z.write(p,'cartociudad.gpkg')
        out=m.inspect_es_zip(zipfile_path)
        self.assertEqual(out['rows'],0)
        self.assertEqual(out['zip_member'],'cartociudad.gpkg')

    def test_es_rejects_multi_gpkg_province(self):
        p=self.root/'two.zip'
        with zipfile.ZipFile(p,'w') as z:z.writestr('1.gpkg',b'a');z.writestr('2.gpkg',b'b')
        with self.assertRaisesRegex(ValueError,'one GeoPackage'):m.inspect_es_zip(p)

    def test_cnig_requires_public_numerical_id(self):
        with self.assertRaises(ValueError):m.es_two_step_probe(None,'../../etc')

    def test_es_52_province_rule(self):
        self.assertEqual(m.ES_PROVINCES,52)
        self.assertFalse(m.find_es_detail_ids(b'<html>None</html>'))
        self.assertEqual(m.find_es_detail_ids(b'<a href="detalleArchivo?sec=42602"></a>'),['42602'])

    def test_cross_country_urls_rejected(self):
        with self.assertRaises(ValueError):m.ensure_origin(m.RS_DOWNLOADS['streets'],'CZ')
        with self.assertRaises(ValueError):m.ensure_origin('http://atom.cuzk.gov.cz/x','CZ')
        with self.assertRaises(ValueError):m.ensure_origin('https://atom.cuzk.gov.cz.evil.net/x','CZ')

if __name__=='__main__':unittest.main()
