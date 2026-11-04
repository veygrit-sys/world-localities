"""Regression cases for unsafe administrative parent assignment."""
import unittest
import tempfile
import zipfile
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from build import aliases
from localities.geonames import RAW, build_rows


def row(gid, code, a1='', a2='', a3='', cc='KE'):
    r = dict.fromkeys(RAW, '')
    r.update(geonameid=str(gid), name='Same name', asciiname='Same name',
             feature_class='A' if code.startswith('ADM') else 'P', feature_code=code,
             country_code=cc, admin1_code=a1, admin2_code=a2, admin3_code=a3,
             latitude='0', longitude='0', population='0', modification_date='2026-09-26')
    return r


class ParentAssignment(unittest.TestCase):
    def test_duplicate_admin_codes_are_unresolved(self):
        data = build_rows([row(1, 'ADM1', '07'), row(2, 'ADM1', '07'), row(3, 'PPL', '07')], 'KE')
        self.assertEqual(data[-1]['parent_id'], '')
        self.assertEqual(data[-1]['parent_relation'], 'ambiguous_code')
        self.assertEqual(data[-1]['parent_candidates_json'], '["gn:1","gn:2"]')

    def test_missing_district_does_not_become_direct_state_parent(self):
        data = build_rows([row(1, 'ADM1', '07'), row(3, 'PPL', '07', '099')], 'KE')
        self.assertEqual(data[-1]['parent_id'], '')
        self.assertEqual(data[-1]['state_id'], 'gn:1')
        self.assertEqual(data[-1]['parent_relation'], 'missing_reference')

    def test_historic_admin_cannot_parent_current_settlement(self):
        data = build_rows([row(1, 'ADM1H', '07'), row(2, 'PPL', '07')], 'KE')
        self.assertEqual(data[-1]['parent_id'], '')

    def test_zero_code_is_not_a_real_state(self):
        data = build_rows([row(1, 'ADM1', '00'), row(2, 'PPL', '00')], 'KE')
        self.assertEqual(data[-1]['parent_relation'], 'country_scope_only')
        self.assertEqual(data[-1]['state_id'], '')

    def test_abandoned_place_is_retained_but_not_suggested(self):
        data = build_rows([row(1, 'PPLQ')], 'KE')
        self.assertEqual(data[0]['address_candidate'], '0')
        self.assertEqual(data[0]['feature_code'], 'PPLQ')

    def test_same_names_under_different_states_keep_ids(self):
        data = build_rows([row(1, 'ADM1', '01'), row(2, 'ADM1', '02'),
                           row(3, 'PPL', '01'), row(4, 'PPL', '02')], 'KE')
        self.assertEqual([r['parent_id'] for r in data[-2:]], ['gn:1', 'gn:2'])

    def test_gapped_hierarchy_is_not_guessed(self):
        data = build_rows([row(1, 'ADM1', '01'), row(2, 'PPL', '01', '', '005')], 'KE')
        self.assertEqual(data[-1]['parent_relation'], 'missing_code')
        self.assertEqual(data[-1]['parent_id'], '')

    def test_cross_country_row_is_rejected(self):
        with self.assertRaises(ValueError):
            build_rows([row(1, 'PPL', cc='UG')], 'KE')


class AlternateValues(unittest.TestCase):
    def test_language_and_postal_values_keep_source_identity(self):
        lines = [
            ['10','1','en','Example English','1','','','','',''],
            ['11','1','es','Nombre español','','','','','',''],
            ['12','1','post','00001','','','','','',''],
            ['13','1','','Unknown language','','','','1','1800','1900'],
            ['14','999','en','Outside selected entity set','','','','','',''],
        ]
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'UY.zip'
            with zipfile.ZipFile(path,'w') as z:
                z.writestr('UY.txt','\n'.join('\t'.join(r) for r in lines)+'\n')
            rows,total=aliases(path,'UY',{'1'})
        self.assertEqual(total,5)
        self.assertEqual(len(rows),4)
        self.assertEqual(rows[0]['id'],'gn-alt:10')
        self.assertEqual(rows[0]['entity_id'],'gn:1')
        self.assertEqual(rows[1]['value'],'Nombre español')
        self.assertEqual(rows[2]['value_type'],'postal_code')
        self.assertEqual(rows[2]['value'],'00001')
        self.assertEqual(rows[3]['language'],'')
        self.assertEqual(rows[3]['value_type'],'untyped_name')
        self.assertEqual(rows[3]['to_period'],'1900')


if __name__ == '__main__':
    unittest.main()
