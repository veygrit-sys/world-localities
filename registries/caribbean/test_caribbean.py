"""Regression cases for unsafe administrative parent assignment."""
import unittest
from build import RAW, build_rows


def row(gid, code, a1='', a2='', a3='', cc='AG'):
    r = dict.fromkeys(RAW, '')
    r.update(geonameid=str(gid), name='Same name', asciiname='Same name',
             feature_class='A' if code.startswith('ADM') else 'P', feature_code=code,
             country_code=cc, admin1_code=a1, admin2_code=a2, admin3_code=a3,
             latitude='0', longitude='0', population='0', modification_date='2026-09-26')
    return r


class ParentAssignment(unittest.TestCase):
    def test_duplicate_admin_codes_are_unresolved(self):
        data = build_rows([row(1, 'ADM1', '07'), row(2, 'ADM1', '07'), row(3, 'PPL', '07')], 'AG')
        self.assertEqual(data[-1]['parent_id'], '')
        self.assertEqual(data[-1]['parent_relation'], 'ambiguous_code')
        self.assertEqual(data[-1]['parent_candidates_json'], '["gn:1","gn:2"]')

    def test_missing_district_does_not_become_direct_state_parent(self):
        data = build_rows([row(1, 'ADM1', '07'), row(3, 'PPL', '07', '099')], 'AG')
        self.assertEqual(data[-1]['parent_id'], '')
        self.assertEqual(data[-1]['state_id'], 'gn:1')
        self.assertEqual(data[-1]['parent_relation'], 'missing_reference')

    def test_historic_admin_cannot_parent_current_settlement(self):
        data = build_rows([row(1, 'ADM1H', '07'), row(2, 'PPL', '07')], 'AG')
        self.assertEqual(data[-1]['parent_id'], '')

    def test_zero_code_is_not_a_real_state(self):
        data = build_rows([row(1, 'ADM1', '00'), row(2, 'PPL', '00')], 'AG')
        self.assertEqual(data[-1]['parent_relation'], 'country_scope_only')
        self.assertEqual(data[-1]['state_id'], '')

    def test_abandoned_place_is_retained_but_not_suggested(self):
        data = build_rows([row(1, 'PPLQ')], 'AG')
        self.assertEqual(data[0]['address_candidate'], '0')
        self.assertEqual(data[0]['feature_code'], 'PPLQ')

    def test_same_names_under_different_states_keep_ids(self):
        data = build_rows([row(1, 'ADM1', '01'), row(2, 'ADM1', '02'),
                           row(3, 'PPL', '01'), row(4, 'PPL', '02')], 'AG')
        self.assertEqual([r['parent_id'] for r in data[-2:]], ['gn:1', 'gn:2'])

    def test_gapped_hierarchy_is_not_guessed(self):
        data = build_rows([row(1, 'ADM1', '01'), row(2, 'PPL', '01', '', '005')], 'AG')
        self.assertEqual(data[-1]['parent_relation'], 'missing_code')
        self.assertEqual(data[-1]['parent_id'], '')

    def test_cross_country_row_is_rejected(self):
        with self.assertRaises(ValueError):
            build_rows([row(1, 'PPL', cc='GD')], 'AG')



class NameProvenance(unittest.TestCase):
    def test_special_tags_not_languages(self):
        from build import SPECIAL
        self.assertEqual(SPECIAL['post'], 'postal_code')
        self.assertEqual(SPECIAL['wkdt'], 'wikidata_id')
        self.assertEqual(SPECIAL['link'], 'link')
        self.assertEqual(SPECIAL['unlc'], 'unlocode')
        self.assertEqual(SPECIAL['tcid'], 'transport_canada_id')
        self.assertNotIn('en', SPECIAL)

    def test_ascii_is_not_english(self):
        r=row(1,'PPL'); r['name']='Café'; r['asciiname']='Cafe'
        result=build_rows([r], 'AG')[0]
        self.assertEqual(result['name'], 'Café')
        self.assertEqual(result['asciiname'], 'Cafe')
        self.assertNotIn('name_en', result)

    def test_source_ids_keep_same_names_separate(self):
        data=build_rows([row(1,'PPL'),row(2,'PPL')], 'AG')
        self.assertNotEqual(data[0]['id'],data[1]['id'])

    def test_alternate_name_id_link_filter(self):
        import tempfile, zipfile
        from pathlib import Path
        from build import alt_rows
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'AG.zip'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('AG.txt','1\t123\ten\tName\t1\t\t\t\t\t\n2\t999\tpost\t12345\t\t\t\t\t\t\n')
            rows,total,discarded=alt_rows(p,'AG',{'gn:123'})
        self.assertEqual((total,discarded,len(rows)),(2,1,1))
        self.assertEqual(rows[0]['id'],'gn-alt:1')
        self.assertEqual(rows[0]['entity_id'],'gn:123')
        self.assertEqual(rows[0]['language'],'en')

    def test_partial_frozen_scope(self):
        import json
        from build import ROOT, CODES
        sc=json.loads((ROOT/'scope.json').read_text())
        self.assertEqual(sorted(c['country'] for c in sc['countries']), CODES)
        self.assertEqual(len(CODES),27)
        self.assertNotIn('CU',CODES)
        self.assertEqual(sc['m49_scope_count'],28)
        self.assertEqual([x['country'] for x in sc['omitted_countries']],['CU'])
        self.assertIn('PR',CODES)
        self.assertIn('VI',CODES)
        self.assertNotIn('BM',CODES)

if __name__ == '__main__':
    unittest.main()
