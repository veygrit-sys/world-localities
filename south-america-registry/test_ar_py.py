"""AR/PY source-byte, language, hierarchy and publication regression tests.

ZIP expectations are read independently from the retained upstream members;
no synthetic place names or translations become publication data.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from build import ALIAS_RAW, PUBLISHED_SCOPE, ROOT, build
from localities.geonames import RAW, build_rows, read_csv
from localities.materialize import materialize_country, safe_path


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


class ArPySources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data={}
        for cc in ['AR','PY']:
            materialize_country(ROOT,cc)
            d=ROOT/'countries'/cc
            meta=load_json(d/'metadata.json')
            with zipfile.ZipFile(ROOT/'sources'/(cc+'.zip')) as z:
                raw=list(csv.DictReader(io.StringIO(z.read(cc+'.txt').decode('utf-8')),fieldnames=RAW,delimiter='\t'))
            with zipfile.ZipFile(ROOT/'sources'/(cc+'-alternatenames.zip')) as z:
                aliases=list(csv.DictReader(io.StringIO(z.read(cc+'.txt').decode('utf-8')),fieldnames=ALIAS_RAW,delimiter='\t'))
            cls.data[cc]=(meta,raw,aliases,list(read_csv(d/'entities.csv.gz')),list(read_csv(d/'alternate-values.csv.gz')))

    def test_zip_bytes_match_recorded_upstream_snapshots(self):
        for cc,(meta,raw,aliases,rows,values) in self.data.items():
            for name,key in [(cc+'.zip','source_file'),(cc+'-alternatenames.zip','alternate_values_source')]:
                with self.subTest(country=cc,archive=name):
                    data=(ROOT/'sources'/name).read_bytes()
                    self.assertEqual(len(data),meta[key]['bytes'])
                    self.assertEqual(hashlib.sha256(data).hexdigest(),meta[key]['sha256'])

    def test_all_ap_source_columns_survive_without_population_cutoff(self):
        for cc,(meta,raw,aliases,rows,values) in self.data.items():
            with self.subTest(country=cc):
                expected=sorted([r for r in raw if r['feature_class'] in ('A','P')],key=lambda r:int(r['geonameid']))
                self.assertEqual([{k:r[k] for k in RAW} for r in rows],expected)
                self.assertTrue(any(r['population']=='0' for r in expected))
                self.assertEqual(len(raw),meta['source_file']['source_rows'])

    def test_all_ten_alias_columns_flags_dates_and_ids_survive(self):
        for cc,(meta,raw,aliases,rows,values) in self.data.items():
            with self.subTest(country=cc):
                ids={r['geonameid'] for r in rows}
                expected=sorted([a for a in aliases if a['geonameid'] in ids],key=lambda a:int(a['alternate_name_id']))
                self.assertEqual([{k:a[k] for k in ALIAS_RAW} for a in values],expected)
                self.assertEqual(len(aliases),meta['alternate_values_source']['source_rows'])
                for a in values:
                    self.assertEqual(a['id'],'gn-alt:'+a['alternate_name_id'])
                    self.assertEqual(a['entity_id'],'gn:'+a['geonameid'])

    def test_capital_identity_accents_and_paraguay_leading_zeroes(self):
        ar={r['id']:r for r in self.data['AR'][3]}
        py={r['id']:r for r in self.data['PY'][3]}
        self.assertEqual(ar['gn:3435910']['name'],'Buenos Aires')
        self.assertEqual(py['gn:3439389']['name'],'Asunción')
        self.assertEqual(py['gn:3439389']['asciiname'],'Asuncion')
        self.assertEqual(py['gn:3439389']['admin2_code'],'0000')
        self.assertEqual(py['gn:3439389']['admin3_code'],'00001005')

    def test_historical_or_abandoned_places_are_retained_but_not_suggested(self):
        for cc,(_,raw,aliases,rows,values) in self.data.items():
            with self.subTest(country=cc):
                historical=[r for r in rows if r['feature_code'] in ('PPLH','PPLQ')]
                self.assertTrue(historical)
                self.assertTrue(all(r['address_candidate']=='0' for r in historical))

    def test_country_language_and_english_coverage_is_source_tagged(self):
        for cc,(meta,raw,aliases,rows,values) in self.data.items():
            with self.subTest(country=cc):
                langs={l.split('-')[0] for l in meta['country']['source_country_languages']}
                current=[a for a in values if a['historic']!='1' and not a['to_period']]
                english={a['entity_id'] for a in current if a['language']=='en'}
                native={a['entity_id'] for a in current if a['language'].split('-')[0] in langs}
                self.assertEqual(len(english),meta['label_coverage']['current_english_name_entities'])
                self.assertEqual(len(native),meta['label_coverage']['current_country_language_name_entities'])
                self.assertGreater(meta['label_coverage']['missing_english_name_entities'],0)
                self.assertGreater(meta['label_coverage']['missing_country_language_name_entities'],0)
                self.assertIn('gn',langs)

    def test_ar_py_exact_code_parents_do_not_guess_missing_districts(self):
        # Synthetic hierarchy fixtures stay in the test and never enter output.
        for cc in ['AR','PY']:
            with self.subTest(country=cc):
                parent=dict.fromkeys(RAW,'')
                parent.update(geonameid='1',name='Fixture ADM1',feature_class='A',feature_code='ADM1',country_code=cc,admin1_code='07',latitude='0',longitude='0',modification_date='2026-10-02')
                child=dict(parent,geonameid='2',name='Fixture place',feature_class='P',feature_code='PPL',admin2_code='0001')
                result=build_rows([parent,child],cc)[1]
                self.assertEqual(result['parent_id'],'')
                self.assertEqual(result['parent_relation'],'missing_reference')
                self.assertEqual(result['state_id'],'gn:1')

    def test_missing_source_bytes_are_named_before_writing(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);inputs=base/'inputs';inputs.mkdir();output=base/'output'
            with self.assertRaisesRegex(FileNotFoundError,'AR.zip.*AR-alternatenames.zip.*PY.zip.*PY-alternatenames.zip'):
                build(inputs,output,'2026-10-02',['AR','PY'],ROOT/'scope.json')
            self.assertFalse(output.exists())


class PublicationConsistency(unittest.TestCase):
    def test_every_country_inventory_and_report_agrees(self):
        scope=load_json(ROOT/'scope.json');manifest=load_json(ROOT/'manifest.json');verification=load_json(ROOT/'verification.json');summary=load_json(ROOT/'summary.json')
        inventory=load_json(ROOT/'sources/source-inventory.json')
        for records in [scope['countries'],manifest['countries'],verification['reports'],list(read_csv(ROOT/'coverage.csv'))]:
            self.assertEqual(len(records),16)
            self.assertEqual({r['country'] for r in records},PUBLISHED_SCOPE)
        for item in [manifest,verification,summary,inventory['publication_scope']]:self.assertEqual(item['pending_country_codes'],[])
        self.assertEqual(scope['pending_countries'],[])
        self.assertEqual(summary['entity_rows'],verification['rows'])
        self.assertEqual(summary['alternate_value_rows'],verification['alternate_values'])
        self.assertEqual(manifest['counts'],verification)
        sources={e['input']:e for e in inventory['inputs']}
        for entry in manifest['countries']:
            cc=entry['country'];path=ROOT/'countries'/cc/'metadata.json';meta=load_json(path)
            self.assertEqual(entry['metadata_sha256'],hashlib.sha256(path.read_bytes()).hexdigest())
            for name,key in [(cc+'.zip','source_file'),(cc+'-alternatenames.zip','alternate_values_source')]:
                self.assertEqual(sources[name]['sha256'],meta[key]['sha256'])
                self.assertEqual(sources[name]['bytes'],meta[key]['bytes'])

    def test_complete_pack_does_not_assert_official_or_postal_completeness(self):
        manifest=load_json(ROOT/'manifest.json')
        self.assertTrue(manifest['complete_pack'])
        self.assertFalse(manifest['complete_official_country_coverage'])
        for cc in sorted(PUBLISHED_SCOPE):
            meta=load_json(ROOT/'countries'/cc/'metadata.json')
            self.assertFalse(meta['current_official_hierarchy_verified'])
            self.assertFalse(meta['postal_coverage']['postal_validation'])
            self.assertFalse(meta['postal_coverage']['postal_deliverability_verified'])

    def test_previous_fourteen_payloads_and_split_parts_are_unchanged(self):
        baseline=load_json(ROOT/'sources/baseline-14-publication.json')
        self.assertEqual(baseline['base_commit'],'a7439bc1c89ad2ea1d2405031b7d33be667c3b2e')
        self.assertEqual(len(baseline['countries']),14)
        for entry in baseline['files']:
            path=safe_path(ROOT,entry['path']);data=path.read_bytes()
            actual=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
            self.assertEqual(actual,entry['git_blob_sha'],entry['path'])


if __name__=='__main__':unittest.main()
