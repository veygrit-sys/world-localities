"""Network-free contract tests for Nordic gazetteer/official source boundaries."""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import nordic_localities as n


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source_root = self.root / 'data'
        self.source_root.mkdir()
        self.catalog = {
            'countries': {code: {'official_sources': [{'url': 'https://official.example.test/data',
                                                        'authority': 'fixture'}],
                                 'source_access': 'public'} for code in n.ALL_CODES}
        }

    def pin(self, payload, *, code='IS', fmt='csv', fields=None, kind='address', name='sample.csv'):
        path = self.source_root / name
        path.write_bytes(payload)
        return {'schema_version': 1, 'country': code, 'source_id': 'TEST-'+code,
                'source_url': 'https://official.example.test/data',
                'license': 'CC-BY-4.0', 'rights_reviewed': True, 'access_authorized': True,
                'retrieved_at': '2026-11-05T02:00:00Z', 'format': fmt, 'kind': kind,
                'national_address_completeness_verified': False, 'deliverability_verified': False,
                'fields': fields or {'id': 'id', 'name': 'name', 'postcode': 'postcode'},
                'coordinate_crs': 'EPSG:4326', 'path': name,
                'bytes': path.stat().st_size, 'sha256': hashlib.sha256(payload).hexdigest()}

    def address_file(self, rows=None):
        if rows is None:
            rows = [('0000001', 'Hafnarstræti', '101'), ('0000002', 'Austurstræti', '001')]
        output = io.StringIO(newline='')
        w = csv.writer(output)
        w.writerow(['id', 'name', 'postcode'])
        w.writerows(rows)
        return output.getvalue().encode('utf-8')


class CatalogAndPostcode(Base):
    def test_catalog_scope_and_9_codes(self):
        path = self.root / n.CATALOG
        path.parent.mkdir(parents=True)
        doc = {'schema_version': 1, 'country_codes': list(n.ALL_CODES),
               'territories': ['AX','FO','GL','SJ'],
               'countries': {x: {'code': x, 'source_access': 'public',
                                 'official_sources': [{'url': 'https://official.example.test/a', 'authority': 'agency'}],
                                 'national_address_completeness_verified': False,
                                 'deliverability_verified': False} for x in n.ALL_CODES}}
        path.write_text(json.dumps(doc))
        self.assertEqual(len(n.load_catalog(self.root)['countries']), 9)
        doc['countries']['SJ']['deliverability_verified'] = True
        path.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ValueError, 'scope/claim'):
            n.load_catalog(self.root)

    def test_all_postal_patterns_are_syntax_only(self):
        valid = {'DK':'0123','FI':'00100','IS':'101','NO':'0001','SE':'123 45',
                 'AX':'AX-22100','FO':'FO-100','GL':'3900','SJ':'9170'}
        for code, value in valid.items():
            with self.subTest(code=code):
                result = n.check_postcode(code,value)
                self.assertTrue(result['syntax_valid'])
                self.assertIsNone(result['postcode_exists'])
                self.assertIsNone(result['deliverable'])
        for c, value in [('DK','12345'),('FI','1234'),('SE','12345x'),('GL','FO-123')]:
            self.assertFalse(n.check_postcode(c,value)['syntax_valid'])

    def test_codes_are_not_automatically_promoted_to_country_states(self):
        self.assertEqual(n.ALL_CODES, ('DK','FI','IS','NO','SE','AX','FO','GL','SJ'))
        self.assertNotIn('EE', n.ALL_CODES)
        self.assertNotIn('GB', n.ALL_CODES)
        self.assertNotIn('IE', n.ALL_CODES)

    def test_no_untrusted_or_cross_country_pin(self):
        pin = self.pin(self.address_file())
        pin['country'] = 'GB'
        with self.assertRaisesRegex(ValueError,'Unknown country'):
            n.verify_official_pin(pin,self.source_root,self.catalog)
        pin['country']='IS';pin['source_url']='https://evil.example.test/data'
        with self.assertRaisesRegex(ValueError,'Unregistered'):
            n.verify_official_pin(pin,self.source_root,self.catalog)


class OfficialImport(Base):
    def test_official_utf8_leading_zero_and_addresses_not_claimed(self):
        pin=self.pin(self.address_file())
        out=self.root/'output.jsonl'
        result=n.ingest_official(pin,self.source_root,out,self.catalog)
        self.assertEqual(result['records'],2)
        rows=[json.loads(x) for x in out.read_text().splitlines()]
        self.assertEqual(rows[1]['fields']['postcode'],'001')
        self.assertEqual(rows[1]['fields']['name'],'Austurstræti')
        self.assertIsNone(rows[0]['address_exists'])
        self.assertEqual(rows[0]['source_qualified_id'],'TEST-IS:0000001')
        self.assertFalse(result['national_address_completeness_verified'])

    def test_modified_bytes_rejected(self):
        pin=self.pin(self.address_file())
        (self.source_root/'sample.csv').write_bytes(b'altered')
        with self.assertRaisesRegex(ValueError,'size/hash'):
            n.ingest_official(pin,self.source_root,self.root/'out.jsonl',self.catalog)
        self.assertFalse((self.root/'out.jsonl').exists())

    def test_rights_and_authorization_fail_closed(self):
        pin=self.pin(self.address_file(),code='SE')
        self.catalog['countries']['SE']['source_access']='legal_review'
        pin['access_authorized']=False
        with self.assertRaisesRegex(ValueError,'Access authorization'):
            n.verify_official_pin(pin,self.source_root,self.catalog)
        pin['access_authorized']=True;pin['rights_reviewed']=False
        with self.assertRaisesRegex(ValueError,'reuse/redistribution'):
            n.verify_official_pin(pin,self.source_root,self.catalog)

    def test_duplicate_id_refused_without_output(self):
        pin=self.pin(self.address_file([('same','A','101'),('same','B','102')]))
        out=self.root/'out.jsonl'
        with self.assertRaisesRegex(ValueError,'duplicate source'):
            n.ingest_official(pin,self.source_root,out,self.catalog)
        self.assertFalse(out.exists())

    def test_no_output_overwrite(self):
        pin=self.pin(self.address_file())
        out=self.root/'exists'
        out.write_text('original')
        with self.assertRaises(FileExistsError):
            n.ingest_official(pin,self.source_root,out,self.catalog)
        self.assertEqual(out.read_text(),'original')

    def test_unknown_schema_header_rejected(self):
        pin=self.pin(self.address_file())
        pin['fields']['number']='missing_real_header'
        out=self.root/'out'
        with self.assertRaisesRegex(ValueError,'Actual source headers'):
            n.ingest_official(pin,self.source_root,out,self.catalog)
        self.assertFalse(out.exists())

    def test_zip_and_gzip_rows(self):
        raw=self.address_file()
        zipbuf=io.BytesIO()
        with zipfile.ZipFile(zipbuf,'w') as z:
            z.writestr('data.csv',raw)
        pin=self.pin(zipbuf.getvalue(),fmt='zip_csv',name='a.zip');pin['member']='data.csv'
        result=n.ingest_official(pin,self.source_root,self.root/'zout',self.catalog)
        self.assertEqual(result['records'],2)
        pin2=self.pin(gzip.compress(raw),fmt='csv_gz',name='a.csv.gz')
        self.assertEqual(n.ingest_official(pin2,self.source_root,self.root/'gout',self.catalog)['records'],2)

    def test_traversal_zip_member_is_rejected(self):
        mem=io.BytesIO()
        with zipfile.ZipFile(mem,'w') as z:
            z.writestr('../escape.csv',self.address_file())
        pin=self.pin(mem.getvalue(),fmt='zip_csv',name='escape.zip');pin['member']='../escape.csv'
        with self.assertRaisesRegex(ValueError,'Unsafe/changed ZIP'):
            n.ingest_official(pin,self.source_root,self.root/'out',self.catalog)

    def test_jsonl_and_geojson(self):
        payload=b'{"uid":"a","title":"Torshavn","zip":"100"}\n'
        pin=self.pin(payload,code='FO',fmt='jsonl',kind='locality',name='a.jsonl',
                     fields={'id':'uid','name':'title','postcode':'zip'})
        self.assertEqual(n.ingest_official(pin,self.source_root,self.root/'out1',self.catalog)['records'],1)
        geo={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'uid':'g','title':'Nuuk','zip':'3900'},'geometry':{'type':'Point','coordinates':[-51,64]}}]}
        pin2=self.pin(json.dumps(geo).encode(),code='GL',fmt='geojson',kind='locality',name='g.geojson',
                      fields={'id':'uid','name':'title','postcode':'zip'})
        self.assertEqual(n.ingest_official(pin2,self.source_root,self.root/'out2',self.catalog)['records'],1)

    def test_source_field_with_person_info_not_leaked(self):
        payload=b'id,name,postcode,owner_name\n0001,Address,101,Sensitive Owner\n'
        pin=self.pin(payload)
        n.ingest_official(pin,self.source_root,self.root/'out',self.catalog)
        self.assertNotIn('Sensitive Owner',(self.root/'out').read_text())

    def test_null_or_false_quality_assertions_rejected(self):
        pin=self.pin(self.address_file())
        pin['deliverability_verified']=True
        with self.assertRaisesRegex(ValueError,'unsupported address quality'):
            n.verify_official_pin(pin,self.source_root,self.catalog)
        pin['deliverability_verified']=False;pin.pop('coordinate_crs')
        with self.assertRaisesRegex(ValueError,'Coordinate'):
            n.verify_official_pin(pin,self.source_root,self.catalog)

    def test_missing_zip_member_and_path_escape_rejected(self):
        pin=self.pin(self.address_file())
        pin['path']='../sample.csv'
        with self.assertRaisesRegex(ValueError,'Unsafe relative path'):
            n.verify_official_pin(pin,self.source_root,self.catalog)
        pin['path']='sample.csv';pin['format']='zip_csv'
        with self.assertRaisesRegex(ValueError,'Explicit member'):
            n.verify_official_pin(pin,self.source_root,self.catalog)

    def test_hms_column_names_can_be_explicitly_preserved(self):
        payload='HEINUM,HNITNUM,HEITI_NF,HUSNR,BOKST,POSTNR,SVFNR\n0000123,00000001,Ísafjörður,05,B,400,4200\n'.encode('utf-8')
        pin=self.pin(payload,fields={'id':'HNITNUM','name':'HEITI_NF','number':'HUSNR','suffix':'BOKST','postcode':'POSTNR','municipality_code':'SVFNR'})
        n.ingest_official(pin,self.source_root,self.root/'hms',self.catalog)
        row=json.loads((self.root/'hms').read_text())
        self.assertEqual(row['fields']['number'],'05')
        self.assertEqual(row['fields']['municipality_code'],'4200')


class Gazetteer(Base):
    def fixture(self, code='SE', *, broken=False):
        f=self.root/'registries/europe/countries'/code
        f.mkdir(parents=True)
        fields=['id','country_code','name','asciiname','alternatenames','kind','parent_id','state_id','feature_code','address_candidate','latitude','longitude']
        a=[{'id':'gn:1','country_code':code,'name':'Åre','asciiname':'Are','alternatenames':'Åre,Are','kind':'locality',
            'parent_id':'gn:2','state_id':'gn:2','feature_code':'PPL','address_candidate':'1','latitude':'63','longitude':'13'},
           {'id':'gn:2','country_code':code,'name':'Region','asciiname':'Region','alternatenames':'','kind':'admin_subdivision',
            'parent_id':'country:'+code,'state_id':'gn:2','feature_code':'ADM1','address_candidate':'0','latitude':'64','longitude':'14'}]
        if broken:a[1]['id']='gn:1'
        text=io.StringIO(newline='')
        writer=csv.DictWriter(text,fieldnames=fields);writer.writeheader();writer.writerows(a)
        raw=text.getvalue().encode()
        data=gzip.compress(raw)
        (f/'entities-0001.csv.gz').write_bytes(data)
        metadata={'files':{'entities-0001.csv.gz':{'bytes':len(data),'rows':2,
                         'sha256':hashlib.sha256(data).hexdigest(),'uncompressed_sha256':hashlib.sha256(raw).hexdigest()}},
                  'counts':{'admin_rows':1,'locality_rows':1,'other_admin_rows':0,'unresolved_parents':0},
                  'current_official_hierarchy_verified':False,'postal_relation_status':'not_loaded'}
        (f/'metadata.json').write_text(json.dumps(metadata))
        return f

    def test_verify_existing_gazetteer_hash_and_counts(self):
        self.fixture()
        result=n.verify(self.root,'SE')
        self.assertEqual(result['observations'],2)
        self.assertEqual(result['integrity'],'verified_bundled_files_and_rows')

    def test_same_name_not_made_official(self):
        self.fixture()
        result=n.search(self.root,'SE','Åre',kind='locality')
        self.assertEqual(result['total'],1)
        self.assertFalse(result['results'][0]['address_verified'])
        self.assertEqual(result['results'][0]['id'],'gn:1')

    def test_english_ascii_not_an_official_translation(self):
        self.fixture()
        result=n.search(self.root,'SE','Are')
        self.assertEqual(result['total'],1)
        self.assertEqual(result['results'][0]['name'],'Åre')

    def test_duplicate_ids_rejected(self):
        self.fixture(broken=True)
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            n.verify(self.root,'SE')

    def test_corrupted_gzip_pin_rejected(self):
        p=self.fixture()/'entities-0001.csv.gz'
        p.write_bytes(p.read_bytes() + b'x')
        with self.assertRaisesRegex(ValueError,'source pin differs'):
            n.verify(self.root,'SE')

    def test_greenland_seeds_are_provisional(self):
        f=self.root/'registries/north-america';f.mkdir(parents=True)
        (f/'admin-seeds.json').write_text(json.dumps({'records':[
            {'country':'GL','provisional_id':'seed:GL:nuuk','source_name':'Nuuk','evidence_id':'government2026'}]}))
        result=n.search(self.root,'GL','Nuuk')
        self.assertTrue(result['results'][0]['identity_is_provisional'])
        self.assertFalse(result['results'][0]['address_verified'])
        self.assertEqual(n.verify(self.root,'GL')['observations'],1)

    def test_baseline_compiles_reproducibly_no_overwrite(self):
        self.fixture()
        one=self.root/'gazetteer1.jsonl.gz';two=self.root/'gazetteer2.jsonl.gz'
        a=n.compile_baseline(self.root,one,('SE',))
        b=n.compile_baseline(self.root,two,('SE',))
        self.assertEqual(a['sha256'],b['sha256'])
        with gzip.open(one,'rt') as f:self.assertEqual(len(f.readlines()),2)
        with self.assertRaises(FileExistsError):n.compile_baseline(self.root,one,('SE',))

    def test_reject_invalid_country_and_search_limits(self):
        self.fixture()
        with self.assertRaises(ValueError):n.search(self.root,'EE','Tallinn')
        with self.assertRaises(ValueError):n.search(self.root,'SE','Åre',limit=201)


if __name__ == '__main__':
    unittest.main()
