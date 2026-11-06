"""Offline contract tests using only synthetic GeoNames / OSM address candidates."""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import europe_microstates as m

WORK=Path(__file__).resolve().parents[1]


class MicrostatesTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        base=self.root/'registries/europe/microstates'
        base.mkdir(parents=True)
        for name in ('catalog.json','official-reference.csv'):
            shutil.copyfile(WORK/'registries/europe/microstates'/name,base/name)
        self.doc=m.load_catalog(base/'catalog.json')
        self.folder=self.root/'original'
        self.folder.mkdir()
        self.pin=None
        self.make_gazetteer()

    def make_gazetteer(self):
        for code in m.CODES:
            base=self.root/'registries/europe/countries'/code
            base.mkdir(parents=True,exist_ok=True)
            records=[dict(id='gn:1',country_code=code,kind='admin_subdivision',name='Named district',
                          parent_id='country:'+code,feature_code='ADM1',latitude='45',longitude='10',
                          parent_relation='source_country',alternatenames='',modification_date='2026-01-01'),
                     dict(id='gn:2',country_code=code,kind='locality',name='Syntetisk Área',
                          parent_id='gn:1',feature_code='PPL',latitude='45.1',longitude='10.1',
                          parent_relation='source_admin_code',alternatenames='Area',modification_date='2026-01-01')]
            raw=io.StringIO(newline='')
            writer=csv.DictWriter(raw,fieldnames=list(records[0]),lineterminator='\n')
            writer.writeheader();writer.writerows(records)
            data=raw.getvalue().encode()
            path=base/'entities-0001.csv.gz'
            with path.open('wb') as output:
                with gzip.GzipFile(fileobj=output,mode='wb',mtime=0,filename='') as gz:gz.write(data)
            pin={'bytes':path.stat().st_size,'sha256':m.sha256(path),
                 'uncompressed_sha256':hashlib.sha256(data).hexdigest(),'rows':2}
            (base/'metadata.json').write_text(json.dumps({'country':{'country':code},
              'files':{path.name:pin},'counts':{'admin_rows':1,'locality_rows':1,'other_admin_rows':0}}))

    def test_catalog_six_jurisdictions_and_non_completion(self):
        self.assertEqual(tuple(self.doc['countries']),m.CODES)
        self.assertFalse(self.doc['national_address_completeness_verified'])
        self.assertFalse(self.doc['deliverability_verified'])
        self.assertEqual(self.doc['excluded_crown_dependencies'],['GG','JE','IM','GI'])

    def test_pinned_official_names_by_country(self):
        seeds=list(m.official_rows(self.root))
        self.assertEqual(len(seeds),28)
        self.assertEqual({code:sum(r['country']==code for r in seeds) for code in m.CODES},
                         {code:self.doc['countries'][code]['official_reference_count'] for code in m.CODES})
        self.assertFalse(any(r['authority_code_verified'] != 'false' for r in seeds))

    def test_licensing_and_source_isolation(self):
        self.assertEqual(self.doc['countries']['VA']['extract_provider'],'osmfr')
        self.assertEqual(self.doc['countries']['SM']['extract_provider'],'osmfr')
        self.assertEqual(self.doc['countries']['AD']['extract_provider'],'geofabrik')
        self.assertEqual(m.LICENSE,'ODbL-1.0')

    def test_ref_hash_tamper_detected(self):
        csvp=self.root/'registries/europe/microstates/official-reference.csv'
        csvp.write_bytes(csvp.read_bytes()+b'\n')
        with self.assertRaisesRegex(ValueError,'bytes changed'):list(m.official_rows(self.root))

    def test_country_source_out_of_scope_rejected(self):
        self.doc['countries']['AD']['source']='http://unsafe.example/a-latest.osm.pbf'
        new=self.root/'bad.json';new.write_text(json.dumps(self.doc))
        with self.assertRaises(ValueError):m.load_catalog(new)

    def test_country_manifest_invalid_complete_flag_rejected(self):
        self.doc['deliverability_verified']=True
        new=self.root/'bad.json';new.write_text(json.dumps(self.doc))
        with self.assertRaises(ValueError):m.load_catalog(new)

    def test_all_six_synthetic_source_audits(self):
        for code in m.CODES:
            result=m.audit_one(code,self.root)
            self.assertEqual(result['geonames_observations'],2)
            self.assertFalse(result['postal_existence_verified'])
        self.assertEqual(m.audit_one('SM',self.root)['official_name_observations'],9)
        self.assertEqual(m.audit_one('VA',self.root)['official_name_observations'],1)

    def test_original_compressed_hash_tampering(self):
        p=self.root/'registries/europe/countries/AD/entities-0001.csv.gz'
        p.write_bytes(p.read_bytes()+b'X')
        with self.assertRaises(ValueError):m.audit_one('AD',self.root)

    def test_country_identity_rejection(self):
        p=self.root/'registries/europe/countries/LI/metadata.json'
        d=json.loads(p.read_text());d['country']['country']='CH';p.write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,'metadata mismatch'):m.audit_one('LI',self.root)

    def test_postcodes_are_syntax_only(self):
        examples=[('AD','AD500','AD50'),('LI','9490','949'),('MC','98000','98-000'),
                  ('SM','47890','47500'),('VA','SCV-00120','99999'),('MT','VLT 1117','VLT11')]
        for code,yes,no in examples:
            self.assertTrue(m.postal_syntax(code,yes))
            self.assertFalse(m.postal_syntax(code,no))
        self.assertFalse(m.postal_syntax('GB','SW1A 0AA'))

    def test_country_all_42_observations_gazetteer_plus_official(self):
        out=self.root/'microstate.sqlite'
        summary=m.build(out,self.root)
        self.assertEqual(summary['records'],40) # 12 GeoNames + 28 reference names
        verified=m.verify(out)
        self.assertEqual(verified['status'],'PASS')
        self.assertEqual(sum(verified['counts'].values()),40)
        self.assertFalse(verified['deliverability_verified'])

    def test_unicode_lookup_and_separate_identifiers(self):
        path=self.root/'index.sqlite';m.build(path,self.root)
        sm=m.search(path,'SM','CITTÀ',kind='official_name')
        self.assertEqual(sm['results'][0]['id'],'SM:castello:citta-di-san-marino')
        self.assertTrue(m.search(path,'LI','Vaduz',kind='official_name')['results'])
        self.assertEqual(len(m.search(path,'MC',kind='official_name')['results']),0)
        self.assertEqual(m.search(path,'VA','00120',kind='postal_reference')['results'][0]['name'],'SCV-00120')

    def test_nonoverwriting_build(self):
        path=self.root/'index.sqlite';m.build(path,self.root)
        with self.assertRaisesRegex(ValueError,'target exists'):m.build(path,self.root)

    def test_integrity_digest_detects_modified_sqlite_name(self):
        path=self.root/'index.sqlite';m.build(path,self.root)
        with sqlite3.connect(path) as db:db.execute("UPDATE records SET name='fabricated' WHERE source_id='geonames' AND record_id='gn:2'")
        with self.assertRaisesRegex(ValueError,'hash differs'):m.verify(path)

    def test_index_report_rejects_completeness_assertion(self):
        path=self.root/'index.sqlite';m.build(path,self.root)
        with sqlite3.connect(path) as db:
            data=json.loads(db.execute("SELECT value FROM metadata WHERE key='report'").fetchone()[0])
            data['deliverability_verified']=True
            db.execute("UPDATE metadata SET value=? WHERE key='report'",(m.canonical(data),))
        with self.assertRaisesRegex(ValueError,'certified'):m.verify(path)

    def test_osm_candidate_classification_without_parent_guess(self):
        rows=list(m.osm_rows('AD','node',123,{'addr:housenumber':'01A','addr:street':'Carrer Major',
                   'addr:postcode':'AD500','addr:country':'AD','contact:phone':'+376111222'},42.5,1.5))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][3],'osm_address_candidate')
        self.assertEqual(rows[0][8],'01A')
        self.assertTrue(json.loads(rows[0][-1])['postcode_syntax_valid'])
        self.assertNotIn('contact:phone',rows[0][-1])

    def test_no_way_centroid_invented(self):
        rows=list(m.osm_rows('MT','way',77,{'highway':'residential','name':'Triq Ħaż-Żebbuġ'},35.9,14.4))
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][3],'osm_named_road_segment')
        self.assertIsNone(rows[0][10]);self.assertIsNone(rows[0][11])

    def test_flag_country_mismatch_and_status(self):
        row=list(m.osm_rows('LI','node',9,{'addr:housenumber':'4','addr:country':'CH'}))[0]
        self.assertTrue(json.loads(row[-1])['address_tag_country_conflict'])
        self.assertFalse(json.loads(row[-1])['postcode_existence_verified'])

    def test_source_pin_rejects_wrong_url_and_hash(self):
        code='AD'
        p=self.folder/'ad-microstate.osm.pbf';p.write_bytes(b'no real bytes')
        rec={'schema_version':1,'source_kind':'osm-community-extract','country':code,
             'source_url':self.doc['countries'][code]['source'],'filename':p.name,
             'acquired_at':'2026-11-06T10:00:00Z','bytes':p.stat().st_size,
             'sha256':m.sha256(p),'license':m.LICENSE,'attribution':m.ATTRIBUTION,'rights_reviewed':True,'fixture':False}
        self.assertEqual(m.check_receipt(rec,code,self.folder,self.doc),p)
        with self.assertRaises(ValueError):m.check_receipt(dict(rec,source_url='https://evil.example/'),code,self.folder,self.doc)
        with self.assertRaises(ValueError):m.check_receipt(dict(rec,sha256='0'*64),code,self.folder,self.doc)
        with self.assertRaises(ValueError):m.check_receipt(dict(rec,rights_reviewed=False),code,self.folder,self.doc)

    def test_duplicate_osm_category_has_same_id(self):
        a=list(m.osm_rows('MC','node',1,{'name':'Monte-Carlo','place':'suburb','addr:housenumber':'7'}))
        self.assertEqual({r[3] for r in a},{'osm_named_place','osm_address_candidate'})
        self.assertEqual({r[2] for r in a},{'osm:node:1'})

    def test_untrusted_country_and_identity_rejected(self):
        for bad in (0,-1):
            with self.assertRaises(ValueError):list(m.osm_rows('MT','node',bad,{'place':'city','name':'Valletta'}))
        with self.assertRaises(ValueError):list(m.osm_rows('JE','node',1,{'place':'town','name':'Example'}))

    def test_strict_query_scope_and_limit(self):
        p=self.root/'index.sqlite';m.build(p,self.root)
        with self.assertRaises(ValueError):m.search(p,'GB')
        with self.assertRaises(ValueError):m.search(p,'AD',limit=101)


if __name__=='__main__':unittest.main()
