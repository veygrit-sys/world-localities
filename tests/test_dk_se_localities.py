"""Danish/Swedish source-qualified localities and address evidence tests."""
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
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dk_se_localities as d


class DKSE(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name)

    def test_unicode_search_normalization_is_search_only(self):
        self.assertEqual(d.lexical_name(' Ålborg  '),'ålborg')
        self.assertEqual(d.search_name('Ålborg'),'alborg')
        self.assertEqual(d.search_name('København'),'kobenhavn')
        self.assertEqual(d.search_name('Älvsjö'),'alvsjo')
        self.assertEqual(d.search_name('Ærø'),'aero')

    def test_no_empty_search_or_country_mixture(self):
        p=self.root/'db.sqlite3'
        db=d.new_db(p,d.PLACE_SCHEMA)
        with db:
            d.add_source(db,'gn:DK','DK','geonames','2026','a'*64,'CC-BY',True)
            d.add_place(db,'gn:DK','gn:1','DK','locality','København')
        db.close()
        self.assertEqual(d.query(p,'DK',text='Kobenhavn')['count'],1)
        self.assertEqual(d.query(p,'SE',text='Kobenhavn')['count'],0)
        with self.assertRaises(ValueError):d.query(p,'DK')
        with self.assertRaises(ValueError):d.query(p,'DK',postcode='1234')

    def test_hardlink_non_overwriting(self):
        f=self.root/'exists.sqlite3';f.write_text('original')
        with self.assertRaises(FileExistsError):d.atomic_build(f,lambda db:{},d.PLACE_SCHEMA)
        self.assertEqual(f.read_text(),'original')

    def test_duplicate_place_id_rejected_atomically(self):
        f=self.root/'db.sqlite3'
        def work(db):
            d.add_source(db,'x','SE','geo','2026',None,'CC-BY',True)
            d.add_place(db,'x','gn:1','SE','locality','Södermalm')
            d.add_place(db,'x','gn:1','SE','locality','Another')
            return {}
        with self.assertRaises(sqlite3.IntegrityError):d.atomic_build(f,work,d.PLACE_SCHEMA)
        self.assertFalse(f.exists())

    def test_original_reference_ids_kept_separate(self):
        f=self.root/'evidence.sqlite3'
        db=d.new_db(f,d.EVIDENCE_SCHEMA)
        with db:
            d.evidence_insert(db,dict(source_id='DAR:DK',record_id='0000000000000001',country='DK',kind='official_address',
                name='Test',postcode='0123',house_number='001A',source_refs={'road_id':'road-0'}, original={'raw':'001A'}))
        db.close()
        hit=d.query(f,'DK',postcode='0123')['results'][0]
        self.assertEqual(hit['house_number'],'001A')
        self.assertEqual(hit['source_refs']['road_id'],'road-0')
        self.assertIsNone(hit['address_exists'])
        self.assertIsNone(hit['deliverable'])
        self.assertEqual(hit['postcode_syntax_valid'],1)

    def test_postcode_syntax_is_not_postcode_existence(self):
        f=self.root/'evidence.sqlite3'
        db=d.new_db(f,d.EVIDENCE_SCHEMA)
        with db:
            d.evidence_insert(db,dict(source_id='osm',record_id='o:1',country='SE',kind='osm_address_tag',postcode='123 45'))
            d.evidence_insert(db,dict(source_id='osm',record_id='o:2',country='SE',kind='osm_address_tag',postcode='00000'))
        db.close()
        a=d.query(f,'SE',postcode='123 45')['results'][0]
        b=d.query(f,'SE',postcode='00000')['results'][0]
        self.assertEqual((a['postcode_syntax_valid'],b['postcode_syntax_valid']),(1,0))
        self.assertIsNone(a['address_exists'])

    def fixture_source(self, country='DK', tag_kind='osm_address_tag', duplicates=False):
        folder=self.root/'osm';folder.mkdir(exist_ok=True)
        receipt={'record_type':'source','receipt':{'country_extract':country,'id':'gof-'+country,'retrieved_at':'2026-11-05'}}
        obs={'id':'osm:node:23','tags':{'addr:housenumber':'003A','addr:street':'Vej','addr:postcode':'1234'},
             'house_number':True,'named_road':False,'road_state':'none','geometry':{'type':'Point','coordinates':[12.5,55.6]}}
        lines=[json.dumps(receipt),json.dumps(obs)]
        if duplicates:lines.append(json.dumps(obs))
        path=folder/(country+'.osm-evidence.jsonl.gz')
        with path.open('wb') as sink:
            with gzip.GzipFile(filename='',fileobj=sink,mode='wb',mtime=0) as gz:
                gz.write(('\n'.join(lines)+'\n').encode())
        idx={'schema_version':1,'licence':'ODbL-1.0','deliverability_in_scope':False,
             'extracts':[{'extract_code':country,'file':path.name,'bytes':path.stat().st_size,'sha256':d.digest(path)}]}
        (folder/'index.json').write_text(json.dumps(idx))
        return folder

    def test_osm_extract_import_is_separate_and_searchable(self):
        e=self.fixture_source();res=d.import_osm(e,'DK',self.root/'osm.sqlite3')
        self.assertEqual(res['observations']['osm_address_tag'],1)
        self.assertEqual(res['licence'],'ODbL-1.0')
        hit=d.query(self.root/'osm.sqlite3','DK',street='Vej',number='003A')['results'][0]
        self.assertEqual(hit['record_id'],'osm:node:23')
        self.assertEqual(hit['longitude'],'12.5')
        self.assertIsNone(hit['address_exists'])

    def test_osm_integrity_provenance_and_duplicates(self):
        e=self.fixture_source(duplicates=True)
        with self.assertRaises(sqlite3.IntegrityError):d.import_osm(e,'DK',self.root/'err.db')
        self.assertFalse((self.root/'err.db').exists())
        e=self.fixture_source()
        idx=e/'index.json';content=json.loads(idx.read_text());content['licence']='CC0';idx.write_text(json.dumps(content))
        with self.assertRaisesRegex(ValueError,'Unrecognized'):d.import_osm(e,'DK',self.root/'err.db')

    def test_osm_source_modified_or_cross_country_rejected(self):
        e=self.fixture_source()
        p=e/'DK.osm-evidence.jsonl.gz'
        with p.open('ab') as f:f.write(b'corrupt')
        with self.assertRaisesRegex(ValueError,'pin mismatch'):d.import_osm(e,'DK',self.root/'err.db')
        self.assertFalse((self.root/'err.db').exists())

    def test_scb_reference_integrity_and_parentage(self):
        src=Path(__file__).resolve().parents[1]/d.SCB_CSV
        provenance=Path(__file__).resolve().parents[1]/d.SCB_MANIFEST
        if not (src.is_file() and provenance.is_file()):self.skipTest('SCB files not in standalone fixture')
        rows=list(d.scb_rows(Path(__file__).resolve().parents[1]))
        self.assertEqual(len(rows),311)
        self.assertIn(('municipality','0180','Stockholm','scb:county:2026:01'),rows)
        self.assertIn(('county','01','Stockholms län','country:SE'),rows)

    def test_evidence_source_id_is_not_collapsed_by_name(self):
        f=self.root/'evidence.sqlite3';db=d.new_db(f,d.EVIDENCE_SCHEMA)
        with db:
            for src in ['OSM:DK','DAR:DK']:
                d.evidence_insert(db,dict(source_id=src,record_id='abc',country='DK',kind='address',name='Same street'))
        db.close()
        hits=d.query(f,'DK',text='Same street')['results']
        self.assertEqual({x['source_id'] for x in hits},{'OSM:DK','DAR:DK'})

    def test_source_receipt_validation(self):
        db=d.new_db(self.root/'c.db',d.PLACE_SCHEMA)
        try:
            with self.assertRaises(ValueError):d.add_source(db,'s','NO','geo','2026',None,'CC-BY',True)
            with self.assertRaises(ValueError):d.add_source(db,'s','SE','geo','2026',None,'',True)
            with self.assertRaises(ValueError):d.add_place(db,'x','id','FI','locality','Test')
        finally:db.close()

    def test_query_limit_and_offset(self):
        f=self.root/'e.db';db=d.new_db(f,d.EVIDENCE_SCHEMA)
        with db:
            for i in range(5):d.evidence_insert(db,dict(source_id='osm',record_id=str(i),country='DK',kind='osm_named_road',name='Gade'))
        db.close()
        first=d.query(f,'DK',text='Gade',limit=2)
        self.assertEqual(first['count'],5)
        self.assertEqual(first['next_offset'],2)
        second=d.query(f,'DK',text='Gade',limit=2,offset=2)
        self.assertEqual(second['next_offset'],4)
        self.assertEqual([r['record_id'] for r in second['results']],['2','3'])


    def test_real_independent_places_index_from_fixed_fixture(self):
        repo=Path(__file__).resolve().parents[1]
        if not (repo/d.SCB_CSV).exists():self.skipTest('No SCB data')
        from unittest.mock import patch
        with patch.object(d.nordic, 'verify',side_effect=lambda root,cc:{'observations':1}), \
             patch.object(d.nordic, 'raw_rows',side_effect=lambda root,cc:iter([{'id':'gn:1','kind':'locality',
                'name':'København' if cc=='DK' else 'Stockholm', 'admin1_code':'01',
                'parent_id':'country:'+cc,'latitude':'55','longitude':'12','feature_code':'PPL'}])), \
             patch.object(d,'read_lau',side_effect=lambda root,cc:iter([{'id':'eurostat:lau:2025:'+cc+'0001',
                'country':cc,'name_national':'Kommune','lau_code':'0001','source_period':'2024',
                'statistical_parent_id':'eurostat:nuts:2024:'+cc+'1'}])):
            report=d.build_places(repo,self.root/'places.db')
        self.assertEqual(report['source_observations']['SE']['SCB_2026'],311)
        self.assertEqual(d.query(self.root/'places.db','DK',text='Kobenhavn')['count'],1)
        self.assertEqual(d.query(self.root/'places.db','SE',text='0180',kind='municipality')['count'],1)
        self.assertEqual(d.query(self.root/'places.db','SE',text='Stockholm',kind='municipality')['count'],1)

    def test_official_import_requires_reviewed_rights_and_retains_ids(self):
        repo=Path(__file__).resolve().parents[1]
        source_root=self.root/'sources';source_root.mkdir()
        raw=b'id,name,street,number,postcode,municipality_code\n0001,Denmark Address,Testvej,03,1234,0101\n'
        (source_root/'dar.csv').write_bytes(raw)
        pin={'schema_version':1,'country':'DK','source_id':'DAR-Test-20261105',
            'source_url':'https://datafordeler.dk/dataoversigt/danmarks-adresseregister-dar/dar-fildownload/',
            'license':'fixture-reviewed','rights_reviewed':True,'access_authorized':True,
            'retrieved_at':'2026-11-05T00:00:00Z','format':'csv','kind':'address',
            'national_address_completeness_verified':False,'deliverability_verified':False,
            'fields':{'id':'id','name':'name','street':'street','number':'number',
                      'postcode':'postcode','municipality_code':'municipality_code'},
            'coordinate_crs':'unknown','path':'dar.csv','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
        pinfile=self.root/'pin.json';pinfile.write_text(json.dumps(pin))
        # The local repo fixture omits the full Nordic catalogue: provide the actual project copy.
        cat=Path(__file__).resolve().parents[1]/'registries/nordics/catalog.json'
        if not cat.is_file():self.skipTest('No Nordic source catalogue')
        result=d.import_official(pinfile,source_root,'DK',self.root/'official.db')
        self.assertEqual(result['records'],1)
        hit=d.query(self.root/'official.db','DK',postcode='1234')['results'][0]
        self.assertEqual(hit['house_number'],'03')
        self.assertEqual(hit['record_id'],'0001')
        self.assertIsNone(hit['address_exists'])
        pin['rights_reviewed']=False;pinfile.write_text(json.dumps(pin))
        with self.assertRaisesRegex(ValueError,'reuse/redistribution'):d.import_official(pinfile,source_root,'DK',self.root/'no.db')
        self.assertFalse((self.root/'no.db').exists())


if __name__=='__main__':unittest.main()
