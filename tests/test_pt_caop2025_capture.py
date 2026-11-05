"""Synthetic CAOP2025 acquisition and schema tests; no live network or false coverage."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import pt_caop2025_capture as m
import es_pt_mt_precision as precision

class CAOPCaptureTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)

    def fixture(self,path,n=22):
        db=sqlite3.connect(path)
        db.execute('CREATE TABLE gpkg_contents(table_name TEXT, srs_id INTEGER)')
        db.execute('CREATE TABLE gpkg_geometry_columns(table_name TEXT,column_name TEXT,srs_id INTEGER)')
        db.execute('CREATE TABLE cont_freguesias(dtmnfr TEXT NOT NULL,freguesia TEXT,municipio TEXT,geom BLOB)')
        db.execute('INSERT INTO gpkg_contents VALUES(?,?)',('cont_freguesias',3763))
        db.execute('INSERT INTO gpkg_geometry_columns VALUES(?,?,?)',('cont_freguesias','geom',3763))
        for i in range(n):db.execute('INSERT INTO cont_freguesias VALUES(?,?,?,?)',(f'{i+1:06d}','União de Freguesias','Municipio',None))
        db.commit();db.close()

    def test_published_source_whitelist_regions(self):
        self.assertEqual(set(m.SOURCES),{'continent','azores','madeira'})
        self.assertTrue(all(url.startswith('https://geo2.dgterritorio.gov.pt/caop/') for url in m.SOURCES.values()))

    def test_gpkg_schema_records_lexical_id_and_real_crs(self):
        p=self.root/'a.gpkg';self.fixture(p)
        schema=m._schema(p)
        self.assertEqual(schema['count'],22)
        self.assertEqual(schema['srs'],3763)
        self.assertEqual(schema['fields']['id'],'dtmnfr')

    def test_gpkg_numeric_identity_refused(self):
        p=self.root/'a.gpkg'
        db=sqlite3.connect(p)
        db.execute('CREATE TABLE gpkg_contents(table_name TEXT,srs_id INTEGER)')
        db.execute('CREATE TABLE gpkg_geometry_columns(table_name TEXT,column_name TEXT,srs_id INTEGER)')
        db.execute('CREATE TABLE cont_freguesias(dtmnfr INTEGER,freguesia TEXT,municipio TEXT)')
        db.execute('INSERT INTO gpkg_contents VALUES(?,?)',('cont_freguesias',3763))
        for n in range(22): db.execute('INSERT INTO cont_freguesias VALUES(?,?,?)',(n+1,'Test','Town'))
        db.commit();db.close()
        with self.assertRaisesRegex(ValueError,'string'):m._schema(p)

    def test_zip_safely_extract_and_hash(self):
        p=self.root/'a.gpkg';self.fixture(p)
        archive=self.root/'source.zip'
        with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.write(p,'a.gpkg')
        result=m._extract_region_gpkgs(archive,self.root,'continent')
        self.assertEqual(len(result),1)
        self.assertEqual(result[0][1]['sha256'],m.digest(result[0][0]))
        self.assertEqual(m._schema(result[0][0])['count'],22)

    def test_capture_with_three_mocked_official_archives(self):
        file=self.root/'g.gpkg';self.fixture(file)
        fixture_zip=self.root/'source.zip'
        with zipfile.ZipFile(fixture_zip,'w',compression=zipfile.ZIP_DEFLATED) as z:z.write(file,'source.gpkg')
        azores_zip=self.root/'azores.zip'
        with zipfile.ZipFile(azores_zip,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.write(file,'AcoresCentroOriental.gpkg');z.write(file,'AcoresOcidental.gpkg')
        def mock_download(region,folder):
            source=azores_zip if region=='azores' else fixture_zip
            (Path(folder)/(region+'-caop2025.zip')).write_bytes(source.read_bytes())
            return {'url':m.SOURCES[region],'region':region,'bytes':source.stat().st_size,'sha256':m.digest(source),
                    'source_date':'2025-12-31','publication_date':'2026-02-18'}
        with patch.object(m,'_source_download',side_effect=mock_download):
            report=m.capture(self.root/'run')
        self.assertEqual(report['status'],'DGT_SOURCE_ACQUIRED_AND_INSPECTED')
        self.assertEqual(len(report['region_files']),4)
        for region in m.SOURCES:
            for part in range(1,m.EXPECTED_GPKG_PARTS[region]+1):
                receipt=json.loads((self.root/'run'/'receipts'/(region+'-'+str(part)+'.json')).read_text())
                self.assertEqual(receipt['crs'],'EPSG:3763')
                precision._validate_receipt(receipt,self.root/'run'/'raw')
                self.assertEqual(len(list(precision.source_rows(self.root/'run'/'raw'/receipt['path'],receipt))),22)
        self.assertFalse(report['national_address_completeness_verified'])

if __name__=='__main__':unittest.main()
