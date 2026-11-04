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
import northamerica as h
import northamerica_common as sa
import northamerica_fetch as fetch


class HierarchyBehavior(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;h.schema(self.db)
        self.b=h.Builder(self.db,{})
        for cc in ['MX','CA']:
            self.b.node('scope:'+cc,cc,'scope','country',0,cc,cc,'test',{})
        for id,cc,namespace,kind,rank,code,name in [
            ('mx-a','MX','official','state',10,'01','Estado A'),
            ('mx-b','MX','official','state',10,'02','Estado B'),
            ('ca-a','CA','official','department',10,'01','Estado A'),
            ('city-a','MX','official','municipality',20,'001','San José'),
            ('city-b','MX','official','municipality',20,'002','San José'),
            ('other-source','MX','gazetteer','municipality',20,'001','San José'),
            ('street','MX','official','street',50,'0001','Rua 100% _Sul')]:
            self.b.node(id,cc,namespace,kind,rank,code,name,'test',{'code':code})
        for child,parent in [('mx-a','scope:MX'),('mx-b','scope:MX'),('ca-a','scope:CA'),('city-a','mx-a'),('city-b','mx-b'),('street','city-a')]:
            self.b.ref(child,parent,'parent','test')
        self.b.resolve();self.b.pending=[]

    def tearDown(self):self.db.close()
    def test_three_countries(self):self.assertEqual(len(h.COUNTRIES),3)
    def test_supplements_not_countries(self):self.assertFalse(set(h.COUNTRIES)&set(h.TERRITORIES));self.assertEqual(len(h.TERRITORIES),3)
    def test_leading_zero_preserved(self):self.assertEqual(h.hierarchy(self.db,'city-a')['node']['code'],'001')
    def test_expected_path(self):self.assertEqual(h.validate_path(self.db,'MX',['scope:MX','mx-a','city-a','street'])['status'],'source_path_consistent')
    def test_wrong_branch_rejected(self):self.assertEqual(h.validate_path(self.db,'MX',['mx-b','city-a'])['status'],'review_required')
    def test_wrong_country_rejected(self):self.assertIn('country_mismatch',h.validate_path(self.db,'CA',['ca-a','city-a'])['problems'])
    def test_reverse_path_rejected(self):self.assertEqual(h.validate_path(self.db,'MX',['city-a','mx-a'])['status'],'review_required')
    def test_duplicate_path_rejected(self):self.assertIn('repeated_node',h.validate_path(self.db,'MX',['mx-a','mx-a'])['problems'])
    def test_unknown_path_rejected(self):self.assertIn('unknown_node',h.validate_path(self.db,'MX',['mx-a','absent'])['problems'])
    def test_single_node_is_not_path(self):
        with self.assertRaises(ValueError):h.validate_path(self.db,'MX',['mx-a'])
    def test_same_name_never_merges(self):self.assertEqual(len(h.search(self.db,'MX','San Jose')['results']),3)
    def test_parent_scoped_search(self):self.assertEqual([r['id'] for r in h.search(self.db,'MX','San Jose',parent='mx-a')['results']],['city-a'])
    def test_namespace_scoped_search(self):self.assertEqual(len(h.search(self.db,'MX','San Jose',namespace='official')['results']),2)
    def test_literal_percent_and_underscore(self):self.assertEqual([r['id'] for r in h.search(self.db,'MX','100% _Sul')['results']],['street'])
    def test_sql_input_bound(self):self.assertEqual(h.search(self.db,'MX',"' OR 1=1 --")['results'],[])
    def test_search_parent_wrong_country(self):
        with self.assertRaises(ValueError):h.search(self.db,'MX','San',parent='ca-a')
    def test_unknown_children_parent(self):
        with self.assertRaises(ValueError):h.children(self.db,'missing')
    def test_page_has_no_repeated_first_result(self):
        a=h.children(self.db,'scope:MX',limit=1);b=h.children(self.db,'scope:MX',limit=1,offset=a['next_offset'])
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
        self.b.node('city-a','MX','official','municipality',20,'001','Different name','test',{})
        self.assertEqual(h.hierarchy(self.db,'city-a')['node']['name'],'San José')
        self.assertEqual(h.hierarchy(self.db,'city-a')['status'],'review_required')
    def test_equal_codes_different_sources_unlinked(self):self.assertEqual(h.hierarchy(self.db,'other-source')['ancestors'],[])
    def test_never_claims_delivery_or_full_coverage(self):
        r=h.hierarchy(self.db,'street');self.assertFalse(r['address_verified']);self.assertFalse(r['delivery_verified']);self.assertFalse(r['national_coverage_verified'])
    def test_source_path_not_address_proof(self):self.assertFalse(h.validate_path(self.db,'MX',['mx-a','city-a'])['address_verified'])
    def test_multiple_observations_preserved(self):
        self.b.observation('sample',1,'street',{'position':'entrance'});self.b.observation('sample',2,'street',{'position':'building'})
        self.assertEqual(self.db.execute('SELECT count(*) FROM observations').fetchone()[0],2)

    def test_postal_is_exact_source_attribute(self):
        self.db.execute('INSERT INTO postal VALUES(?,?,?)',('street','00100','test'))
        self.assertEqual(len(h.postal_records(self.db,'MX','00100')['results']),1)
        self.assertEqual(h.postal_records(self.db,'MX','100')['results'],[])
        self.assertFalse(h.postal_records(self.db,'MX','00100')['delivery_verified'])

    def test_missing_english_is_not_inferred(self):
        self.assertEqual(h.names(self.db,'city-a','en')['results'],[])
    def test_french_source_tag_kept(self):
        self.b.name('city-a','Saint-Joseph','fr','test-fr')
        self.assertEqual(h.names(self.db,'city-a','fr')['results'][0]['name'],'Saint-Joseph')
    def test_original_observations_pagination(self):
        self.b.observation('sample',1,'street',{'code':'001'});self.b.observation('sample',2,'street',{'code':'002'})
        r=h.observations(self.db,'street',1);self.assertTrue(r['has_more'])
        self.assertEqual(h.observations(self.db,'street',1,r['next_offset'])['results'][0]['fields']['code'],'002')


class CountrySourceBehavior(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;h.schema(self.db)
        self.b=h.Builder(self.db,{})
        self.b.roots()
    def tearDown(self):self.db.close()
    def us_rows(self,source):
        return iter({'us-census-state':[{'USPS':'AL','GEOID':'01','NAME':'Alabama'},{'USPS':'PR','GEOID':'72','NAME':'Puerto Rico'}],
          'us-census-counties':[{'USPS':'AL','GEOID':'01001','NAME':'Autauga County'}],
          'us-census-cousubs':[{'USPS':'AL','GEOID':'0100190001','NAME':'Division A'}],
          'us-census-place':[{'USPS':'AL','GEOID':'0100100','NAME':'Town A'}]}[source])
    def load_us(self):
        self.b.rows=self.us_rows;self.b.us();self.b.resolve()
    def test_us_place_has_no_invented_county(self):
        self.load_us();ids={r['id'] for r in h.ancestors(self.db,'us-census-2026:place:0100100')}
        self.assertIn('us-census-2026:state:01',ids);self.assertNotIn('us-census-2026:county_equivalent:01001',ids)
    def test_us_county_subdivision_has_county(self):
        self.load_us();self.assertIn('us-census-2026:county_equivalent:01001',{r['id'] for r in h.ancestors(self.db,'us-census-2026:county_subdivision:0100190001')})
    def test_pr_excluded_from_us(self):
        self.load_us();self.assertIsNone(self.db.execute("SELECT 1 FROM nodes WHERE id='us-census-2026:state:72'").fetchone())
    def test_conflicting_census_state_code_flagged(self):
        def rows(source):
            rr=list(self.us_rows(source))
            if source=='us-census-counties':rr[0]['USPS']='CA'
            return iter(rr)
        self.b.rows=rows;self.b.us();self.b.resolve()
        self.assertEqual(h.hierarchy(self.db,'us-census-2026:county_equivalent:01001')['status'],'review_required')
    def ca_rows(self,source):
        names=['Quebec','Quebec','Division','Montreal'] if source.endswith('eng') else ['Québec','Québec','Division','Montréal']
        return iter([dict(zip(['Level','Structure','Code','Title'],[str(level),'type',code,name])) for (level,code),name in zip([(1,'2'),(2,'24'),(3,'2466'),(4,'2466023')],names)])
    def test_ca_bilingual_code_join(self):
        self.b.rows=self.ca_rows;self.b.ca();self.b.resolve()
        id='ca-sgc-2021:census_subdivision:2466023'
        self.assertEqual(h.names(self.db,id,'fr')['results'][0]['name'],'Montréal')
        self.assertIn('ca-sgc-2021:province_territory:24',{r['id'] for r in h.ancestors(self.db,id)})
    def test_ca_missing_language_rows_rejected(self):
        self.b.rows=lambda source:self.ca_rows(source) if source.endswith('eng') else iter([])
        with self.assertRaises(ValueError):self.b.ca()
    def test_mx_locality_requires_matching_code_components(self):
        def rows(source):
            if source.endswith('entidad'):return iter([{'CVEGEO':'01','CVE_ENT':'01','NOM_ENT':'State A'}])
            if source.endswith('municipio'):return iter([{'CVEGEO':'01001','CVE_ENT':'01','CVE_MUN':'001','NOM_MUN':'Town A'}])
            return iter([{'CVEGEO':'020010001','CVE_ENT':'01','CVE_MUN':'001','CVE_LOC':'0001','NOM_LOC':'Place A'}])
        self.b.rows=rows
        with self.assertRaises(ValueError):self.b.mx()


class SourceUtilities(unittest.TestCase):
    def test_gzip_json(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'raw';p.write_bytes(gzip.compress(b'{"code":"001"}'))
            self.assertEqual(sa.read_json(p)['code'],'001')
    def test_cp1252_preserves_accent(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'raw';p.write_bytes('Code,Name\n24,Québec\n'.encode('cp1252'))
            self.assertEqual(list(sa.csv_rows(p,encoding='cp1252'))[0]['Name'],'Québec')
    def test_malformed_csv_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'raw';p.write_text('Code,Name\n24\n')
            with self.assertRaises(ValueError):list(sa.csv_rows(p))
    def test_us_zip4_syntax_only(self):self.assertEqual(sa.postcode_review('US','00501-1234')['status'],'matches_syntax_only')
    def test_ca_forbidden_postal_letter(self):self.assertEqual(sa.postcode_review('CA','D1A 1A1')['status'],'review_required')
    def test_ca_lowercase_postal(self):self.assertEqual(sa.postcode_review('CA','k1a 0b1')['status'],'matches_syntax_only')
    def test_mx_leading_zero_postal(self):self.assertEqual(sa.postcode_review('MX','01000')['display_candidate'],'01000')
    def test_numeric_postal_rejected(self):self.assertEqual(sa.postcode_review('MX',1000)['status'],'invalid_input_type')
    def test_nonascii_postal_rejected(self):self.assertEqual(sa.postcode_review('US','１２３４５')['status'],'review_required')
    def test_historical_name_not_current(self):self.assertTrue(sa.historical_or_time_bounded_name({'historic':'1'}))
    def test_future_name_not_current(self):self.assertTrue(sa.historical_or_time_bounded_name({'from':'2099'}))
    def test_past_name_accepted(self):self.assertFalse(sa.historical_or_time_bounded_name({'from':'2000-01-01'}))
    def test_html_not_source(self):
        with self.assertRaises(ValueError):fetch.validate_payload({'id':'x','format':'csv'},b'<!DOCTYPE html><html>Error</html>')
    def test_missing_zip_member_rejected(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('wrong.txt','data')
        with self.assertRaises(ValueError):fetch.validate_payload({'id':'us-geonames-geonames','country':'US','format':'zip'},b.getvalue())
    def test_wrapped_zip_accepted(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('US.txt','data')
        fetch.validate_payload({'id':'us-geonames-geonames','country':'US','format':'zip'},gzip.compress(b.getvalue()))


if __name__=='__main__':unittest.main()


