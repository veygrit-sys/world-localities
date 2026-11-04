"""Behavior tests. In-memory records below are explicitly synthetic fixtures."""
import importlib.util
import math
from pathlib import Path
import sqlite3
import unittest

import os as _hierarchy_os
ROOT = Path(_hierarchy_os.environ.get('WORLD_LOCALITIES_ADDRESS_ROOT', str(Path(__file__).resolve().parents[1]))).resolve()
spec = importlib.util.spec_from_file_location('sa', ROOT/'address-points/adapters/southamerica.py')
sa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sa)


class ProfileTests(unittest.TestCase):
    def test_all_16_scopes(self):
        self.assertEqual(set('AR BO BV BR CL CO EC FK GF GY PY PE GS SR UY VE'.split()),set(sa.profiles()))

    def test_source_references_exist_for_all_profiles(self):
        for cc,p in sa.profiles().items():
            self.assertTrue(p['sources'],cc)
            self.assertTrue(all(s['url'].startswith('https://') for s in p['sources']),cc)

    def test_postcode_patterns(self):
        examples={'AR':'C1000AAA','BR':'01001000','CL':'8320000','CO':'110111','EC':'090306',
                  'FK':'FIQQ1ZZ','GF':'97300','GY':'4130105','PY':'001218','PE':'01001','GS':'SIQQ 1ZZ','UY':'11000','VE':'1010'}
        for cc,v in examples.items():
            with self.subTest(cc=cc):
                r=sa.postcode_review(cc,v)
                self.assertEqual('matches_syntax_only',r['status'])
                self.assertEqual(v,r['raw'])
                self.assertFalse(r['assignment_verified'])
                self.assertFalse(r['delivery_verified'])

    def test_numeric_input_is_rejected_without_losing_zeroes(self):
        self.assertEqual('invalid_input_type',sa.postcode_review('PY',1218)['status'])

    def test_guyana_six_digit_source_inconsistency_is_not_corrected(self):
        r=sa.postcode_review('GY','413018')
        self.assertEqual('review_required',r['status'])
        self.assertEqual('413018',r['raw'])

    def test_legacy_postcode_not_promoted(self):
        for cc in ['AR','PY']:
            self.assertEqual('legacy_format_review_required',sa.postcode_review(cc,'1000')['status'])

    def test_uruguay_extended_code_is_separate(self):
        self.assertEqual('extended_format_review_required',sa.postcode_review('UY','11000-00001')['status'])

    def test_non_ascii_digits_and_case_expansion_not_accepted(self):
        self.assertEqual('review_required',sa.postcode_review('CO','１１０１１１')['status'])
        self.assertEqual('review_required',sa.postcode_review('AR','C1000aß')['status'])

    def test_no_postcode_placeholder_generation(self):
        for cc in ['BO','SR']:
            self.assertEqual('not_required_by_reference',sa.postcode_review(cc,None)['status'])
            self.assertEqual('unverified_supplied_value',sa.postcode_review(cc,'0000')['status'])

    def test_different_territory_code_is_not_accepted(self):
        self.assertEqual('review_required',sa.postcode_review('GF','97500')['status'])
        self.assertEqual('review_required',sa.postcode_review('FK','SIQQ 1ZZ')['status'])

    def test_unknown_country_fails(self):
        with self.assertRaises(ValueError): sa.postcode_review('FR','97300')

    def test_bouvet_no_ordinary_form(self):
        self.assertEqual([],sa.render_address('BV',{'locality':'test'})['lines'])

    def test_composite_number_and_unit_preserved(self):
        f={'address_line1':'Carrera 15A # 93B-05','address_line2':'Apto. 02-B','locality':'Bogotá','postcode':'110111'}
        r=sa.render_address('CO',f)
        self.assertIn(f['address_line1'],r['lines'])
        self.assertIn(f['address_line2'],r['lines'])
        self.assertEqual(f,r['raw'])
        self.assertFalse(r['unit_verified'])

    def test_brasilia_components_not_reparsed(self):
        f={'address_line1':'SQS 308 Bloco B','locality':'Brasília','admin1':'DF','postcode':'70355-020'}
        self.assertIn('SQS 308 Bloco B',sa.render_address('BR',f)['lines'])

    def test_uruguay_output_line(self):
        r=sa.render_address('UY',{'address_line1':'Calle de prueba s/n','postcode':'70200','locality':'Rosario','admin1':'Colonia'})
        self.assertIn('70200 - Rosario, Colonia',r['lines'])

    def test_field_input_order_does_not_change_lines(self):
        f={'address_line1':'Synthetic 001A','postcode':'001218','locality':'Asunción'}
        self.assertEqual(sa.render_address('PY',f)['lines'],sa.render_address('PY',dict(reversed(list(f.items()))))['lines'])

    def test_unknown_fields_preserved(self):
        r=sa.render_address('PE',{'address_line1':'Synthetic','house_number':'001/A'})
        self.assertEqual('001/A',r['unrendered_fields']['house_number'])

    def test_multiline_fields_rejected(self):
        with self.assertRaises(ValueError):sa.render_address('AR',{'address_line1':'A\nB'})

    def test_box_and_street_require_explicit_route(self):
        with self.assertRaises(ValueError):sa.render_address('AR',{'address_line1':'test','po_box':'box'})

    def test_lookup_keys_are_lossy_only(self):
        self.assertEqual(sa.lookup_key('Ñuñez'),sa.lookup_key('Nunez'))
        r=sa.render_address('PY',{'address_line1':'Ñuñez 001'})
        self.assertEqual('Ñuñez 001',r['lines'][0])

    def test_time_bounded_alias_filter(self):
        self.assertTrue(sa.historical_or_time_bounded_name({'historic':'1'}))
        self.assertTrue(sa.historical_or_time_bounded_name({'from':'2099-01'}))
        self.assertTrue(sa.historical_or_time_bounded_name({'from':'2026-12'}))
        self.assertTrue(sa.historical_or_time_bounded_name({'to':'2000'}))
        self.assertTrue(sa.historical_or_time_bounded_name({'from':'not-a-date'}))
        self.assertFalse(sa.historical_or_time_bounded_name({'from':'2000'}))


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;sa.create_schema(self.db)
        # Synthetic points exercise filtering and geography without being presented as real addresses.
        self.rid=sa.insert_record(self.db,'synthetic:1','synthetic','BR','1','place','São Exemplo',0,179.999,'synthetic',{},'BR','PPL','01')
        sa.insert_record(self.db,'synthetic:2','synthetic','BR','2','place','São Exemplo',0,-179.999,'synthetic',{},'BR','PPL','02')
        sa.insert_record(self.db,'synthetic:3','synthetic','BR','3','place','Historic Test',0,0,'synthetic',{},'BR','PPLH',historic=True)
        sa.insert_record(self.db,'synthetic:4','synthetic','BR','4','place','Wrong Country',0,0,'synthetic',{},'AR','PPL')
        self.db.execute('INSERT INTO names VALUES(?,?,?,?,?,?,?,?,?)',(self.rid,'Example Town','example town','en','source_alias',0,1,'n1',None))
        self.db.execute('INSERT INTO names VALUES(?,?,?,?,?,?,?,?,?)',(self.rid,'Old Example','old example','en','source_alias',1,0,'n2',None))
        self.db.execute('INSERT INTO names VALUES(?,?,?,?,?,?,?,?,?)',(self.rid,'Q1234','q1234','wkdt','identifier_or_link',0,0,'n3',None))
        self.db.execute('INSERT INTO names VALUES(?,?,?,?,?,?,?,?,?)',(self.rid,'Sao Exemplo','sao exemplo',None,'source_ascii',0,0,None,None))

    def tearDown(self):self.db.close()

    def test_accents_and_token_order_find_candidates(self):
        r=sa.search(self.db,'BR','Exemplo Sao')
        self.assertEqual(2,len(r['results']))
        self.assertEqual('São Exemplo',r['results'][0]['name'])

    def test_homonyms_not_merged(self):
        self.assertEqual(2,len(sa.search(self.db,'BR','Sao')['results']))
        self.assertEqual(1,len(sa.search(self.db,'BR','Sao',admin1='02')['results']))

    def test_ascii_is_not_english(self):
        self.assertEqual([],sa.search(self.db,'BR','Sao',name_view='english_international')['results'])
        self.assertEqual(1,len(sa.search(self.db,'BR','Example',name_view='english_international')['results']))
        self.assertEqual([],sa.search(self.db,'BR','Example',name_view='english_domestic')['results'])

    def test_unlabelled_names_not_inferred_as_portuguese(self):
        self.assertEqual([],sa.search(self.db,'BR','Sao',language='pt')['results'])

    def test_historic_names_opt_in(self):
        self.assertEqual([],sa.search(self.db,'BR','Old')['results'])
        self.assertEqual(1,len(sa.search(self.db,'BR','Old',include_historic=True)['results']))
        self.assertEqual([],sa.search(self.db,'BR','Historic')['results'])

    def test_identifier_tags_not_names(self):
        self.assertEqual([],sa.search(self.db,'BR','Q1234')['results'])

    def test_country_mismatch_excluded(self):
        self.assertEqual([],sa.search(self.db,'BR','Wrong')['results'])

    def test_literal_wildcards_and_sql_injection(self):
        self.assertEqual([],sa.search(self.db,'BR','%')['results'])
        self.assertEqual([],sa.search(self.db,'BR',"x' OR 1=1 --")['results'])

    def test_layers_not_conflated(self):
        self.assertEqual([],sa.search(self.db,'BR','Sao',layer='address')['results'])

    def test_antimeridian_reverse_search(self):
        r=sa.reverse(self.db,'BR',0,180,layer='place',radius_m=500)
        self.assertEqual(2,len(r['results']))
        self.assertFalse(r['contains_point_verified'])
        self.assertTrue(all(abs(x['distance_m']-111.195)<1 for x in r['results']))

    def test_radius_prevents_distant_fallback(self):
        self.assertEqual('no_reference_within_radius',sa.reverse(self.db,'BR',50,0,radius_m=100)['status'])

    def test_invalid_spatial_input(self):
        for lat,lon,radius in [(math.nan,0,100),(91,0,100),(0,181,100),(0,0,-1),(0,0,math.inf)]:
            with self.subTest(lat=lat,lon=lon,radius=radius):
                with self.assertRaises(ValueError):sa.reverse(self.db,'BR',lat,lon,radius_m=radius)

    def test_no_verification_upgrade_on_match(self):
        r=sa.search(self.db,'BR','Sao')['results'][0]
        for k in ['premise_verified','unit_verified','delivery_verified']:self.assertFalse(r[k])

    def test_limit_validation(self):
        with self.assertRaises(ValueError):sa.search(self.db,'BR','Sao',limit=101)


if __name__ == '__main__': unittest.main()
