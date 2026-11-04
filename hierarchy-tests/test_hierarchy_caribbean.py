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
import caribbean_hierarchy as h
import caribbean_common as sa
import caribbean_fetch as fetch


class HierarchyBehavior(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;h.schema(self.db)
        self.b=h.Builder(self.db,{})
        for cc in ['DO','DM']:
            self.b.node('scope:'+cc,cc,'scope','country',0,cc,cc,'test',{})
        for id,cc,namespace,kind,rank,code,name in [
            ('mx-a','DO','official','state',10,'01','Estado A'),
            ('mx-b','DO','official','state',10,'02','Estado B'),
            ('ca-a','DM','official','department',10,'01','Estado A'),
            ('city-a','DO','official','municipality',20,'001','San José'),
            ('city-b','DO','official','municipality',20,'002','San José'),
            ('other-source','DO','gazetteer','municipality',20,'001','San José'),
            ('street','DO','official','street',50,'0001','Rua 100% _Sul')]:
            self.b.node(id,cc,namespace,kind,rank,code,name,'test',{'code':code})
        for child,parent in [('mx-a','scope:DO'),('mx-b','scope:DO'),('ca-a','scope:DM'),('city-a','mx-a'),('city-b','mx-b'),('street','city-a')]:
            self.b.ref(child,parent,'parent','test')
        self.b.resolve();self.b.pending=[]

    def tearDown(self):self.db.close()
    def test_thirteen_countries(self):self.assertEqual(len(h.COUNTRIES),13)
    def test_supplements_not_countries(self):self.assertFalse(set(h.COUNTRIES)&set(h.TERRITORIES));self.assertEqual(len(h.TERRITORIES),15)
    def test_leading_zero_preserved(self):self.assertEqual(h.hierarchy(self.db,'city-a')['node']['code'],'001')
    def test_expected_path(self):self.assertEqual(h.validate_path(self.db,'DO',['scope:DO','mx-a','city-a','street'])['status'],'source_path_consistent')
    def test_wrong_branch_rejected(self):self.assertEqual(h.validate_path(self.db,'DO',['mx-b','city-a'])['status'],'review_required')
    def test_wrong_country_rejected(self):self.assertIn('country_mismatch',h.validate_path(self.db,'DM',['ca-a','city-a'])['problems'])
    def test_reverse_path_rejected(self):self.assertEqual(h.validate_path(self.db,'DO',['city-a','mx-a'])['status'],'review_required')
    def test_duplicate_path_rejected(self):self.assertIn('repeated_node',h.validate_path(self.db,'DO',['mx-a','mx-a'])['problems'])
    def test_unknown_path_rejected(self):self.assertIn('unknown_node',h.validate_path(self.db,'DO',['mx-a','absent'])['problems'])
    def test_single_node_is_not_path(self):
        with self.assertRaises(ValueError):h.validate_path(self.db,'DO',['mx-a'])
    def test_same_name_never_merges(self):self.assertEqual(len(h.search(self.db,'DO','San Jose')['results']),3)
    def test_parent_scoped_search(self):self.assertEqual([r['id'] for r in h.search(self.db,'DO','San Jose',parent='mx-a')['results']],['city-a'])
    def test_namespace_scoped_search(self):self.assertEqual(len(h.search(self.db,'DO','San Jose',namespace='official')['results']),2)
    def test_literal_percent_and_underscore(self):self.assertEqual([r['id'] for r in h.search(self.db,'DO','100% _Sul')['results']],['street'])
    def test_sql_input_bound(self):self.assertEqual(h.search(self.db,'DO',"' OR 1=1 --")['results'],[])
    def test_search_parent_wrong_country(self):
        with self.assertRaises(ValueError):h.search(self.db,'DO','San',parent='ca-a')
    def test_unknown_children_parent(self):
        with self.assertRaises(ValueError):h.children(self.db,'missing')
    def test_page_has_no_repeated_first_result(self):
        a=h.children(self.db,'scope:DO',limit=1);b=h.children(self.db,'scope:DO',limit=1,offset=a['next_offset'])
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
        self.b.node('city-a','DO','official','municipality',20,'001','Different name','test',{})
        self.assertEqual(h.hierarchy(self.db,'city-a')['node']['name'],'San José')
        self.assertEqual(h.hierarchy(self.db,'city-a')['status'],'review_required')
    def test_equal_codes_different_sources_unlinked(self):self.assertEqual(h.hierarchy(self.db,'other-source')['ancestors'],[])
    def test_never_claims_delivery_or_full_coverage(self):
        r=h.hierarchy(self.db,'street');self.assertFalse(r['address_verified']);self.assertFalse(r['delivery_verified']);self.assertFalse(r['national_coverage_verified'])
    def test_source_path_not_address_proof(self):self.assertFalse(h.validate_path(self.db,'DO',['mx-a','city-a'])['address_verified'])
    def test_multiple_observations_preserved(self):
        self.b.observation('sample',1,'street',{'position':'entrance'});self.b.observation('sample',2,'street',{'position':'building'})
        self.assertEqual(self.db.execute('SELECT count(*) FROM observations').fetchone()[0],2)

    def test_postal_is_exact_source_attribute(self):
        self.db.execute('INSERT INTO postal VALUES(?,?,?)',('street','00100','test'))
        self.assertEqual(len(h.postal_records(self.db,'DO','00100')['results']),1)
        self.assertEqual(h.postal_records(self.db,'DO','100')['results'],[])
        self.assertFalse(h.postal_records(self.db,'DO','00100')['delivery_verified'])

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
        one={'sheet':'adm1','level':1,'kind':'parish','expected_rows':2,'code_field':'c1','name_field':'name','country_field':'cc','country_value':'GD','code_pattern':r'GD[0-9]+','parent_fields':[],'version_field':'version','language':'en'}
        two={**one,'sheet':'adm2','level':2,'kind':'district','expected_rows':1,'code_field':'c2','parent_fields':['c1']}
        self.source={'country':'GD','namespace':'fixture','version':'v01','local_path':'unused','layers':[one,two]}
        self.rows={'adm1':[(2,{'cc':'GD','version':'v01','c1':'GD01','name':'A'}),(3,{'cc':'GD','version':'v01','c1':'GD02','name':'B'})],
          'adm2':[(2,{'cc':'GD','version':'v01','c1':'GD01','c2':'GD0101','name':'Town'})]}
        self.b=h.Builder(self.db,{'gd-test':self.source});self.b.roots()
    def tearDown(self):self.db.close()
    def load(self):
        with patch.object(sa,'xlsx_rows',side_effect=lambda p,s:iter(self.rows[s])):self.b.administrative()
        self.b.resolve()
    def test_original_code_and_parent(self):
        self.load();self.assertEqual(h.validate_path(self.db,'GD',['scope:GD','fixture:adm1:GD01','fixture:adm2:GD0101'])['status'],'source_path_consistent')
        self.assertEqual(h.observations(self.db,'fixture:adm2:GD0101')['results'][0]['fields']['fields'],self.rows['adm2'][0][1])
    def test_wrong_branch_rejected(self):
        self.load();self.assertEqual(h.validate_path(self.db,'GD',['fixture:adm1:GD02','fixture:adm2:GD0101'])['status'],'review_required')
    def test_version_change_requires_review(self):
        self.rows['adm1'][0][1]['version']='v02'
        with self.assertRaises(ValueError):self.load()
    def test_country_change_requires_review(self):
        self.rows['adm2'][0][1]['cc']='DM'
        with self.assertRaises(ValueError):self.load()
    def test_count_change_requires_review(self):
        self.rows['adm2'].clear()
        with self.assertRaises(ValueError):self.load()
    def test_duplicate_admin_code_requires_review(self):
        self.rows['adm1'][1][1]['c1']='GD01'
        with self.assertRaises(ValueError):self.load()
    def test_invalid_code_requires_review(self):
        self.rows['adm2'][0][1]['c2']='DM01'
        with self.assertRaises(ValueError):self.load()
    def test_full_parent_tuple_required(self):
        third={**self.source['layers'][1],'sheet':'adm3','level':3,'code_field':'c3','parent_fields':['c1','c2']}
        self.source['layers'].append(third)
        self.rows['adm3']=[(2,{'cc':'GD','version':'v01','c1':'GD02','c2':'GD0101','c3':'GD010101','name':'X'})]
        self.load();self.assertNotIn('fixture:adm2:GD0101',{r['id'] for r in h.ancestors(self.db,'fixture:adm3:GD010101')})
        self.assertEqual(h.hierarchy(self.db,'fixture:adm3:GD010101')['status'],'review_required')
    def test_non_geographic_category_separate(self):
        self.source['layers'][0]['non_geographic_codes']={'-':'Homeless respondents'}
        self.rows['adm1'][1][1].update(c1='-',name='Homeless respondents')
        self.load();r=h.hierarchy(self.db,'fixture:adm1:-')
        self.assertEqual(r['node']['kind'],'non_geographic_reporting_category');self.assertEqual(r['status'],'review_required')
    def test_non_geographic_category_name_change_blocked(self):
        self.source['layers'][0]['non_geographic_codes']={'GD02':'Homeless respondents'}
        with self.assertRaises(ValueError):self.load()
    def test_source_language_tag_preserved(self):
        self.load();self.assertEqual(h.names(self.db,'fixture:adm2:GD0101','en')['results'][0]['name'],'Town')

class SourceUtilities(unittest.TestCase):
    def test_all_scope_codes_unique(self):self.assertEqual(len(set(h.ALL_SCOPES)),28)
    def test_caribbean_netherlands_counted_once(self):self.assertEqual(h.TERRITORIES.count('BQ'),1)
    def test_french_and_dutch_sides_separate(self):self.assertTrue({'MF','SX'}<=set(h.TERRITORIES))
    def test_dominica_and_dominican_republic_separate(self):self.assertTrue({'DM','DO'}<=set(h.COUNTRIES))
    def test_previous_region_not_duplicated(self):
        for cc in ['MX','BM','GL','PM','BZ','GT','SV','HN','NI','CR','PA']:
            with self.assertRaises(ValueError):sa.country_code(cc)
    def test_leading_zero_postcode_preserved(self):self.assertEqual(sa.postcode_review('PR','00901')['display_candidate'],'00901')
    def test_unverified_postcode_kept_for_review(self):self.assertEqual(sa.postcode_review('TT','110608')['status'],'review_required')
    def test_optional_empty_postcode(self):self.assertEqual(sa.postcode_review('AW','')['status'],'missing')
    def test_numeric_postcode_invalid_type(self):self.assertEqual(sa.postcode_review('PR',901)['status'],'invalid_input_type')
    def test_no_postal_assignment_claim(self):self.assertFalse(sa.postcode_review('PR','00901')['assignment_verified'])
    def test_nonascii_postcode_not_silently_transliterated(self):self.assertEqual(sa.postcode_review('PR','００９０１')['status'],'review_required')
    def test_historical_alias_not_current(self):self.assertTrue(sa.historical_or_time_bounded_name({'historic':'1'}))
    def test_future_alias_not_current(self):self.assertTrue(sa.historical_or_time_bounded_name({'from':'2099'}))
    def test_ended_alias_not_current(self):self.assertTrue(sa.historical_or_time_bounded_name({'to':'2020'}))
    def test_active_alias_allowed(self):self.assertFalse(sa.historical_or_time_bounded_name({'from':'2000-01-01'}))
    def test_html_instead_of_data_rejected(self):
        with self.assertRaises(ValueError):fetch.validate_payload({'id':'x','format':'csv'},b'<!DOCTYPE html><html>Error</html>')
    def test_missing_country_archive_member_rejected(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('wrong.txt','data')
        with self.assertRaises(ValueError):fetch.validate_payload({'id':'do-geonames-geonames','country':'DO','format':'zip'},b.getvalue())
    def test_changed_publisher_licence_requires_review(self):
        with self.assertRaises(ValueError):fetch.validate_payload({'id':'do-codab-metadata','format':'json'},b'{"success":true,"result":{"license_id":"other"}}')

class WorkbookSafety(unittest.TestCase):
    def workbook(self,value):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup);p=Path(tmp.name)/'sample.xlsx'
        with zipfile.ZipFile(p,'w') as z:
            z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Test" sheetId="1" r:id="rId1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>code</t></is></c></row><row r="2"><c r="A2" t="inlineStr"><is><t>001</t></is></c><c r="H2">'+value+'</c></row></sheetData></worksheet>')
        return p
    def test_formatting_only_trailing_cell_allowed(self):self.assertEqual(list(sa.xlsx_rows(self.workbook(''),'Test')),[(2,{'code':'001'})])
    def test_unheaded_value_not_discarded(self):
        with self.assertRaises(ValueError):list(sa.xlsx_rows(self.workbook('<v>9</v>'),'Test'))
    def test_unheaded_formula_rejected(self):
        with self.assertRaises(ValueError):list(sa.xlsx_rows(self.workbook('<f>1+1</f><v>2</v>'),'Test'))

if __name__=='__main__':unittest.main()
