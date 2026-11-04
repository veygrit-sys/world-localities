import json
import gzip
import io
import tempfile
import zipfile
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'address-points/adapters'))
import southamerica_hierarchy as h
import southamerica_fetch as fetch
import southamerica as sa


class HierarchyBehavior(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.db.row_factory=sqlite3.Row;h.schema(self.db)
        self.b=h.Builder(self.db,{})
        for cc in ['BR','PE']:
            self.b.node('scope:'+cc,cc,'scope','country',0,cc,cc,'test',{})
        for id,cc,namespace,kind,rank,code,name in [
            ('br-a','BR','official','state',10,'01','Estado A'),
            ('br-b','BR','official','state',10,'02','Estado B'),
            ('pe-a','PE','official','department',10,'01','Estado A'),
            ('city-a','BR','official','municipality',20,'001','San José'),
            ('city-b','BR','official','municipality',20,'002','San José'),
            ('other-source','BR','gazetteer','municipality',20,'001','San José'),
            ('street','BR','official','street',50,'0001','Rua 100% _Sul')]:
            self.b.node(id,cc,namespace,kind,rank,code,name,'test',{'code':code})
        for child,parent in [('br-a','scope:BR'),('br-b','scope:BR'),('pe-a','scope:PE'),('city-a','br-a'),('city-b','br-b'),('street','city-a')]:
            self.b.ref(child,parent,'parent','test')
        self.b.resolve();self.b.pending=[]

    def tearDown(self):self.db.close()
    def test_twelve_countries(self):self.assertEqual(len(h.COUNTRIES),12)
    def test_supplements_not_countries(self):self.assertFalse(set(h.COUNTRIES)&set(h.TERRITORIES));self.assertEqual(len(h.TERRITORIES),4)
    def test_leading_zero_preserved(self):self.assertEqual(h.hierarchy(self.db,'city-a')['node']['code'],'001')
    def test_expected_path(self):self.assertEqual(h.validate_path(self.db,'BR',['scope:BR','br-a','city-a','street'])['status'],'source_path_consistent')
    def test_wrong_branch_rejected(self):self.assertEqual(h.validate_path(self.db,'BR',['br-b','city-a'])['status'],'review_required')
    def test_wrong_country_rejected(self):self.assertIn('country_mismatch',h.validate_path(self.db,'PE',['pe-a','city-a'])['problems'])
    def test_reverse_path_rejected(self):self.assertEqual(h.validate_path(self.db,'BR',['city-a','br-a'])['status'],'review_required')
    def test_duplicate_path_rejected(self):self.assertIn('repeated_node',h.validate_path(self.db,'BR',['br-a','br-a'])['problems'])
    def test_unknown_path_rejected(self):self.assertIn('unknown_node',h.validate_path(self.db,'BR',['br-a','absent'])['problems'])
    def test_single_node_is_not_path(self):
        with self.assertRaises(ValueError):h.validate_path(self.db,'BR',['br-a'])
    def test_same_name_never_merges(self):self.assertEqual(len(h.search(self.db,'BR','San Jose')['results']),3)
    def test_parent_scoped_search(self):self.assertEqual([r['id'] for r in h.search(self.db,'BR','San Jose',parent='br-a')['results']],['city-a'])
    def test_namespace_scoped_search(self):self.assertEqual(len(h.search(self.db,'BR','San Jose',namespace='official')['results']),2)
    def test_literal_percent_and_underscore(self):self.assertEqual([r['id'] for r in h.search(self.db,'BR','100% _Sul')['results']],['street'])
    def test_sql_input_bound(self):self.assertEqual(h.search(self.db,'BR',"' OR 1=1 --")['results'],[])
    def test_search_parent_wrong_country(self):
        with self.assertRaises(ValueError):h.search(self.db,'BR','San',parent='pe-a')
    def test_unknown_children_parent(self):
        with self.assertRaises(ValueError):h.children(self.db,'missing')
    def test_page_has_no_repeated_first_result(self):
        a=h.children(self.db,'scope:BR',limit=1);b=h.children(self.db,'scope:BR',limit=1,offset=a['next_offset'])
        self.assertNotEqual(a['results'][0]['id'],b['results'][0]['id']);self.assertFalse(b['has_more'])
    def test_missing_parent_not_fabricated(self):
        self.b.ref('other-source','absent','parent','test');self.b.resolve()
        self.assertEqual(h.hierarchy(self.db,'other-source')['status'],'review_required')
        self.assertIsNone(self.db.execute("SELECT 1 FROM nodes WHERE id='absent'").fetchone())
    def test_cross_country_link_blocked(self):
        self.b.ref('city-a','pe-a','parent','test');self.b.resolve()
        self.assertIsNone(self.db.execute("SELECT 1 FROM links WHERE child='city-a' AND parent='pe-a'").fetchone())
    def test_cycles_blocked_by_rank(self):
        self.b.ref('br-a','city-a','parent','test');self.b.resolve();self.assertEqual(h.structural_checks(self.db)['acyclic_rank_order'],'PASS')
    def test_issue_propagates_to_descendant(self):
        self.b.issue('br-a','source_identity_conflict','name','A',[])
        self.assertEqual(h.hierarchy(self.db,'street')['status'],'review_required')
    def test_conflicting_identity_retains_first_and_flags(self):
        self.b.node('city-a','BR','official','municipality',20,'001','Different name','test',{})
        self.assertEqual(h.hierarchy(self.db,'city-a')['node']['name'],'San José')
        self.assertEqual(h.hierarchy(self.db,'city-a')['status'],'review_required')
    def test_equal_codes_different_sources_unlinked(self):self.assertEqual(h.hierarchy(self.db,'other-source')['ancestors'],[])
    def test_never_claims_delivery_or_full_coverage(self):
        r=h.hierarchy(self.db,'street');self.assertFalse(r['address_verified']);self.assertFalse(r['delivery_verified']);self.assertFalse(r['national_coverage_verified'])
    def test_source_path_not_address_proof(self):self.assertFalse(h.validate_path(self.db,'BR',['br-a','city-a'])['address_verified'])
    def test_multiple_observations_preserved(self):
        self.b.observation('sample',1,'street',{'position':'entrance'});self.b.observation('sample',2,'street',{'position':'building'})
        self.assertEqual(self.db.execute('SELECT count(*) FROM observations').fetchone()[0],2)


class RefreshBehavior(unittest.TestCase):
    def test_compressed_json_transport(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'source.json';p.write_bytes(gzip.compress(b'{"id":"001"}'))
            self.assertEqual(sa.read_json(p)['id'],'001')
    def test_compressed_country_zip_transport(self):
        with tempfile.TemporaryDirectory() as t:
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,'w') as z:z.writestr('BR.txt','001\tName\n')
            p=Path(t)/'BR.zip';p.write_bytes(gzip.compress(buf.getvalue()))
            self.assertEqual(list(sa.zip_rows(p,'BR')),[['001','Name']])
    def test_partial_wfs_rejected(self):
        with self.assertRaises(ValueError):fetch.validate_payload({'kind':'py-barloc'},b'{"numberMatched":2,"features":[{}]}')
    def test_partial_georef_rejected(self):
        with self.assertRaises(ValueError):fetch.validate_payload({'kind':'georef-extra'},b'{"cantidad":10,"total":20,"inicio":0}')
    def test_csv_replaced_by_html_rejected(self):
        with self.assertRaises(ValueError):fetch.validate_payload({'kind':'uy-streets'},b'<!doctype html><html>Moved</html>')
    def test_gzip_ibge_accepted(self):fetch.validate_payload({'kind':'ibge'},gzip.compress(b'[{"id":11,"nome":"Rondonia"}]'))


if __name__=='__main__':unittest.main()
