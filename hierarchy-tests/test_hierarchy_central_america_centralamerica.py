import json
import gzip
import io
import tempfile
import zipfile
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'address-points/adapters'))
import centralamerica as h
import centralamerica_common as sa
import centralamerica_fetch as fetch


class RepositoryCandidateIsolation(unittest.TestCase):
    def test_candidate_contains_only_regional_inputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'candidate'
            fetch.stage_candidate(output)
            self.assertEqual({p.name for p in (output/'address-points/adapters').glob('*.py')},
                             {'centralamerica.py','centralamerica_common.py','centralamerica_fetch.py','centralamerica_validate.py'})
            self.assertTrue((output/'tests/test_centralamerica.py').is_file())
            self.assertFalse((output/'.git').exists())
            self.assertFalse((output/'official-registry').exists())
            self.assertFalse((output/'address-points/CENTRAL_AMERICA_VALIDATION.json').exists())
            self.assertFalse((output/'address-points/sources').exists())

    def test_refresh_does_not_require_old_raw_payloads(self):
        sources=sa.read_json(sa.ROOT/'CENTRAL_AMERICA_SOURCES.json')
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'candidate'
            def downloaded(source,root):
                return source,None
            with patch.object(sa,'verify_sources',side_effect=AssertionError('Old raw data must not be required')), \
                 patch.object(fetch,'fetch_one',side_effect=downloaded):
                result=fetch.refresh(output,workers=1)
            self.assertEqual(result['status'],'candidate_requires_validation')
            current=json.loads((output/'address-points/CENTRAL_AMERICA_SOURCES.json').read_text())
            self.assertTrue(current['validation_required'])
            self.assertEqual(len(current['sources']),len(sources['sources']))

    def test_refresh_preserves_existing_target(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)
            (output/'keep').write_text('accepted')
            with self.assertRaises(ValueError):fetch.refresh(output)
            self.assertEqual((output/'keep').read_text(),'accepted')


class HierarchyBehavior(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;h.schema(self.db)
        self.b=h.Builder(self.db,{})
        for cc in ['GT','CR']:
            self.b.node('scope:'+cc,cc,'scope','country',0,cc,cc,'test',{})
        for id,cc,namespace,kind,rank,code,name in [
            ('mx-a','GT','official','state',10,'01','Estado A'),
            ('mx-b','GT','official','state',10,'02','Estado B'),
            ('ca-a','CR','official','department',10,'01','Estado A'),
            ('city-a','GT','official','municipality',20,'001','San José'),
            ('city-b','GT','official','municipality',20,'002','San José'),
            ('other-source','GT','gazetteer','municipality',20,'001','San José'),
            ('street','GT','official','street',50,'0001','Rua 100% _Sul')]:
            self.b.node(id,cc,namespace,kind,rank,code,name,'test',{'code':code})
        for child,parent in [('mx-a','scope:GT'),('mx-b','scope:GT'),('ca-a','scope:CR'),('city-a','mx-a'),('city-b','mx-b'),('street','city-a')]:
            self.b.ref(child,parent,'parent','test')
        self.b.resolve();self.b.pending=[]

    def tearDown(self):self.db.close()
    def test_seven_countries(self):self.assertEqual(len(h.COUNTRIES),7)
    def test_supplements_not_countries(self):self.assertFalse(set(h.COUNTRIES)&set(h.TERRITORIES));self.assertEqual(len(h.TERRITORIES),0)
    def test_leading_zero_preserved(self):self.assertEqual(h.hierarchy(self.db,'city-a')['node']['code'],'001')
    def test_expected_path(self):self.assertEqual(h.validate_path(self.db,'GT',['scope:GT','mx-a','city-a','street'])['status'],'source_path_consistent')
    def test_wrong_branch_rejected(self):self.assertEqual(h.validate_path(self.db,'GT',['mx-b','city-a'])['status'],'review_required')
    def test_wrong_country_rejected(self):self.assertIn('country_mismatch',h.validate_path(self.db,'CR',['ca-a','city-a'])['problems'])
    def test_reverse_path_rejected(self):self.assertEqual(h.validate_path(self.db,'GT',['city-a','mx-a'])['status'],'review_required')
    def test_duplicate_path_rejected(self):self.assertIn('repeated_node',h.validate_path(self.db,'GT',['mx-a','mx-a'])['problems'])
    def test_unknown_path_rejected(self):self.assertIn('unknown_node',h.validate_path(self.db,'GT',['mx-a','absent'])['problems'])
    def test_single_node_is_not_path(self):
        with self.assertRaises(ValueError):h.validate_path(self.db,'GT',['mx-a'])
    def test_same_name_never_merges(self):self.assertEqual(len(h.search(self.db,'GT','San Jose')['results']),3)
    def test_parent_scoped_search(self):self.assertEqual([r['id'] for r in h.search(self.db,'GT','San Jose',parent='mx-a')['results']],['city-a'])
    def test_namespace_scoped_search(self):self.assertEqual(len(h.search(self.db,'GT','San Jose',namespace='official')['results']),2)
    def test_literal_percent_and_underscore(self):self.assertEqual([r['id'] for r in h.search(self.db,'GT','100% _Sul')['results']],['street'])
    def test_sql_input_bound(self):self.assertEqual(h.search(self.db,'GT',"' OR 1=1 --")['results'],[])
    def test_search_parent_wrong_country(self):
        with self.assertRaises(ValueError):h.search(self.db,'GT','San',parent='ca-a')
    def test_unknown_children_parent(self):
        with self.assertRaises(ValueError):h.children(self.db,'missing')
    def test_page_has_no_repeated_first_result(self):
        a=h.children(self.db,'scope:GT',limit=1);b=h.children(self.db,'scope:GT',limit=1,offset=a['next_offset'])
        self.assertNotEqual(a['results'][0]['id'],b['results'][0]['id']);self.assertFalse(b['has_more'])
    def test_missing_parent_not_fabricated(self):
        self.b.ref('other-source','absent','parent','test');self.b.resolve()
        self.assertEqual(h.hierarchy(self.db,'other-source')['status'],'review_required')
        self.assertIsNone(self.db.execute("SELECT 1 FROM nodes WHERE id='absent'").fetchone())
    def test_cross_country_link_blocked(self):
        self.b.ref('city-a','ca-a','parent','test');self.b.resolve()
        self.assertIsNone(self.db.execute("SELECT 1 FROM links WHERE child='city-a' AND parent='ca-a'").fetchone())
    def test_cycles_blocked_by_rank(self):
        self.b.ref('mx-a','city-a','parent','test');self.b.resolve();self.assertEqual(h.structural_checks(self.db)['acyclic_rank_order'],'PASS')
    def test_issue_propagates_to_descendant(self):
        self.b.issue('mx-a','source_identity_conflict','name','A',[])
        self.assertEqual(h.hierarchy(self.db,'street')['status'],'review_required')
    def test_conflicting_identity_retains_first_and_flags(self):
        self.b.node('city-a','GT','official','municipality',20,'001','Different name','test',{})
        self.assertEqual(h.hierarchy(self.db,'city-a')['node']['name'],'San José')
        self.assertEqual(h.hierarchy(self.db,'city-a')['status'],'review_required')
    def test_equal_codes_different_sources_unlinked(self):self.assertEqual(h.hierarchy(self.db,'other-source')['ancestors'],[])
    def test_never_claims_delivery_or_full_coverage(self):
        r=h.hierarchy(self.db,'street');self.assertFalse(r['address_verified']);self.assertFalse(r['delivery_verified']);self.assertFalse(r['national_coverage_verified'])
    def test_source_path_not_address_proof(self):self.assertFalse(h.validate_path(self.db,'GT',['mx-a','city-a'])['address_verified'])
    def test_multiple_observations_preserved(self):
        self.b.observation('sample',1,'street',{'position':'entrance'});self.b.observation('sample',2,'street',{'position':'building'})
        self.assertEqual(self.db.execute('SELECT count(*) FROM observations').fetchone()[0],2)

    def test_postal_is_exact_source_attribute(self):
        self.db.execute('INSERT INTO postal VALUES(?,?,?)',('street','00100','test'))
        self.assertEqual(len(h.postal_records(self.db,'GT','00100')['results']),1)
        self.assertEqual(h.postal_records(self.db,'GT','100')['results'],[])
        self.assertFalse(h.postal_records(self.db,'GT','00100')['delivery_verified'])

    def test_missing_english_is_not_inferred(self):
        self.assertEqual(h.names(self.db,'city-a','en')['results'],[])
    def test_french_source_tag_kept(self):
        self.b.name('city-a','Saint-Joseph','fr','test-fr')
        self.assertEqual(h.names(self.db,'city-a','fr')['results'][0]['name'],'Saint-Joseph')
    def test_original_observations_pagination(self):
        self.b.observation('sample',1,'street',{'code':'001'});self.b.observation('sample',2,'street',{'code':'002'})
        r=h.observations(self.db,'street',1);self.assertTrue(r['has_more'])
        self.assertEqual(h.observations(self.db,'street',1,r['next_offset'])['results'][0]['fields']['code'],'002')


class AdministrativeBehavior(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;h.schema(self.db)
        self.source={'id':'gt-test','country':'GT','namespace':'fixture','version':'v01','local_path':'unused',
          'layers':[{'sheet':'adm1','level':1,'kind':'department','expected_administrative_count':2},
                    {'sheet':'adm2','level':2,'kind':'municipality','expected_administrative_count':1,'non_administrative_codes':['GT0199']}]}
        self.rows={'adm1':[(2,{'adm0_pcode':'GT','version':'v01','adm1_pcode':'GT01','adm1_name':'A','lang':'es'}),(3,{'adm0_pcode':'GT','version':'v01','adm1_pcode':'GT02','adm1_name':'B','lang':'es'})],
          'adm2':[(2,{'adm0_pcode':'GT','version':'v01','adm1_pcode':'GT01','adm2_pcode':'GT0101','adm2_name':'La Laguna','lang':'es'}),(3,{'adm0_pcode':'GT','version':'v01','adm1_pcode':'GT01','adm2_pcode':'GT0199','adm2_name':'Lago','lang':'es'})]}
        self.b=h.Builder(self.db,{'gt-test':self.source});self.b.roots()
    def tearDown(self):self.db.close()
    def load(self):
        with patch.object(sa,'xlsx_rows',side_effect=lambda p,s:iter(self.rows[s])):self.b.administrative()
        self.b.resolve()
    def test_water_does_not_count_as_municipality(self):
        self.load();self.assertEqual(self.db.execute("SELECT count(*) FROM nodes WHERE kind='municipality'").fetchone()[0],1)
        self.assertEqual(h.hierarchy(self.db,'fixture:adm2:GT0199')['status'],'review_required')
    def test_laguna_named_town_remains_a_town(self):
        self.load();self.assertEqual(h.hierarchy(self.db,'fixture:adm2:GT0101')['node']['kind'],'municipality')
    def test_parent_path_and_raw_row_preserved(self):
        self.load();self.assertEqual(h.validate_path(self.db,'GT',['scope:GT','fixture:adm1:GT01','fixture:adm2:GT0101'])['status'],'source_path_consistent')
        self.assertEqual(h.observations(self.db,'fixture:adm2:GT0101')['results'][0]['fields']['fields'],self.rows['adm2'][0][1])
    def test_wrong_branch_rejected(self):
        self.load();self.assertEqual(h.validate_path(self.db,'GT',['fixture:adm1:GT02','fixture:adm2:GT0101'])['status'],'review_required')
    def test_version_change_requires_review(self):
        self.rows['adm1'][0][1]['version']='v02'
        with self.assertRaises(ValueError):self.load()
    def test_country_change_requires_review(self):
        self.rows['adm2'][0][1]['adm0_pcode']='SV'
        with self.assertRaises(ValueError):self.load()
    def test_unexpected_count_requires_review(self):
        self.rows['adm2'].pop()
        with self.assertRaises(ValueError):self.load()
    def test_duplicate_administrative_pcode_requires_review(self):
        self.rows['adm1'][1][1]['adm1_pcode']='GT01'
        with self.assertRaises(ValueError):self.load()
    def test_conflicting_parent_tuple_not_linked(self):
        self.source['layers'].append({'sheet':'adm3','level':3,'kind':'district','expected_administrative_count':1})
        self.rows['adm3']=[(2,{'adm0_pcode':'GT','version':'v01','adm1_pcode':'GT02','adm2_pcode':'GT0101','adm3_pcode':'GT010101','adm3_name':'District','lang':'es'})]
        self.load();anc={r['id'] for r in h.ancestors(self.db,'fixture:adm3:GT010101')}
        self.assertNotIn('fixture:adm2:GT0101',anc);self.assertEqual(h.hierarchy(self.db,'fixture:adm3:GT010101')['status'],'review_required')
    def test_duplicate_place_pcodes_do_not_merge(self):
        self.source['layers'].append({'sheet':'places','level':5,'kind':'populated_place','expected_source_rows':2})
        self.rows['places']=[(2,{'adm0_pcode':'GT','version':'v01','adm1_pcode':'GT01','adm2_pcode':'GT0101','pcode':'GT0101001','featurename_es':'Village A'}),(3,{'adm0_pcode':'GT','version':'v01','adm1_pcode':'GT01','adm2_pcode':'GT0101','pcode':'GT0101001','featurename_es':'Village B'})]
        self.load();rows=self.db.execute("SELECT id,name FROM nodes WHERE kind='populated_place' ORDER BY name").fetchall()
        self.assertEqual([r['name'] for r in rows],['Village A','Village B'])
        self.assertTrue(all(h.hierarchy(self.db,r['id'])['status']=='review_required' for r in rows))

class SourceUtilities(unittest.TestCase):
    def test_leading_zero_postcode_preserved(self):self.assertEqual(sa.postcode_review('GT','01001')['display_candidate'],'01001')
    def test_costa_rica_five_digits(self):self.assertEqual(sa.postcode_review('CR','10101')['status'],'matches_syntax_only')
    def test_nicaragua_old_seven_digit_rule_not_used(self):self.assertEqual(sa.postcode_review('NI','1234567')['status'],'review_required')
    def test_nicaragua_five_digits(self):self.assertEqual(sa.postcode_review('NI','12005')['status'],'matches_syntax_only')
    def test_salvador_cp_prefix(self):self.assertEqual(sa.postcode_review('SV','cp 1120')['status'],'matches_syntax_only')
    def test_salvador_repeated_prefix_not_allowed(self):self.assertEqual(sa.postcode_review('SV','CPCP1120')['status'],'review_required')
    def test_honduras_unsettled_syntax_not_rejected_as_invalid(self):self.assertEqual(sa.postcode_review('HN','11101')['status'],'review_required')
    def test_panama_new_system_not_falsely_validated(self):self.assertEqual(sa.postcode_review('PA','0801')['status'],'review_required')
    def test_belize_empty_postcode_allowed_as_missing(self):self.assertEqual(sa.postcode_review('BZ','')['status'],'missing')
    def test_numeric_postcode_invalid_type(self):self.assertEqual(sa.postcode_review('GT',1001)['status'],'invalid_input_type')
    def test_postcode_does_not_prove_assignment(self):self.assertFalse(sa.postcode_review('CR','10101')['assignment_verified'])
    def test_nonascii_postcode_not_silently_changed(self):self.assertEqual(sa.postcode_review('GT','０１００１')['status'],'review_required')
    def test_mexico_not_duplicated_in_scope(self):
        with self.assertRaises(ValueError):sa.country_code('MX')
    def test_historical_alias_not_current(self):self.assertTrue(sa.historical_or_time_bounded_name({'historic':'1'}))
    def test_future_alias_not_current(self):self.assertTrue(sa.historical_or_time_bounded_name({'from':'2099'}))
    def test_active_alias_accepted(self):self.assertFalse(sa.historical_or_time_bounded_name({'from':'2000-01-01'}))
    def test_html_instead_of_data_rejected(self):
        with self.assertRaises(ValueError):fetch.validate_payload({'id':'x','format':'csv'},b'<!DOCTYPE html><html>Error</html>')
    def test_missing_country_archive_member_rejected(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('wrong.txt','data')
        with self.assertRaises(ValueError):fetch.validate_payload({'id':'gt-geonames-geonames','country':'GT','format':'zip'},b.getvalue())
    def test_changed_publisher_licence_requires_review(self):
        with self.assertRaises(ValueError):fetch.validate_payload({'id':'gt-codab-metadata','format':'json'},b'{"success":true,"result":{"license_id":"other"}}')

if __name__=='__main__':unittest.main()
