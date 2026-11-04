"""Regression cases for unsafe administrative parent assignment."""
import unittest
from build import RAW, build_rows


def row(gid, code, a1='', a2='', a3='', cc='BZ'):
    r = dict.fromkeys(RAW, '')
    r.update(geonameid=str(gid), name='Same name', asciiname='Same name',
             feature_class='A' if code.startswith('ADM') else 'P', feature_code=code,
             country_code=cc, admin1_code=a1, admin2_code=a2, admin3_code=a3,
             latitude='0', longitude='0', population='0', modification_date='2026-09-26')
    return r


class ParentAssignment(unittest.TestCase):
    def test_duplicate_admin_codes_are_unresolved(self):
        data = build_rows([row(1, 'ADM1', '07'), row(2, 'ADM1', '07'), row(3, 'PPL', '07')], 'BZ')
        self.assertEqual(data[-1]['parent_id'], '')
        self.assertEqual(data[-1]['parent_relation'], 'ambiguous_code')
        self.assertEqual(data[-1]['parent_candidates_json'], '["gn:1","gn:2"]')

    def test_missing_district_does_not_become_direct_state_parent(self):
        data = build_rows([row(1, 'ADM1', '07'), row(3, 'PPL', '07', '099')], 'BZ')
        self.assertEqual(data[-1]['parent_id'], '')
        self.assertEqual(data[-1]['state_id'], 'gn:1')
        self.assertEqual(data[-1]['parent_relation'], 'missing_reference')

    def test_historic_admin_cannot_parent_current_settlement(self):
        data = build_rows([row(1, 'ADM1H', '07'), row(2, 'PPL', '07')], 'BZ')
        self.assertEqual(data[-1]['parent_id'], '')

    def test_zero_code_is_not_a_real_state(self):
        data = build_rows([row(1, 'ADM1', '00'), row(2, 'PPL', '00')], 'BZ')
        self.assertEqual(data[-1]['parent_relation'], 'country_scope_only')
        self.assertEqual(data[-1]['state_id'], '')

    def test_abandoned_place_is_retained_but_not_suggested(self):
        data = build_rows([row(1, 'PPLQ')], 'BZ')
        self.assertEqual(data[0]['address_candidate'], '0')
        self.assertEqual(data[0]['feature_code'], 'PPLQ')

    def test_same_names_under_different_states_keep_ids(self):
        data = build_rows([row(1, 'ADM1', '01'), row(2, 'ADM1', '02'),
                           row(3, 'PPL', '01'), row(4, 'PPL', '02')], 'BZ')
        self.assertEqual([r['parent_id'] for r in data[-2:]], ['gn:1', 'gn:2'])

    def test_gapped_hierarchy_is_not_guessed(self):
        data = build_rows([row(1, 'ADM1', '01'), row(2, 'PPL', '01', '', '005')], 'BZ')
        self.assertEqual(data[-1]['parent_relation'], 'missing_code')
        self.assertEqual(data[-1]['parent_id'], '')

    def test_cross_country_row_is_rejected(self):
        with self.assertRaises(ValueError):
            build_rows([row(1, 'PPL', cc='ZZ')], 'BZ')


class NamesAndPostcodes(unittest.TestCase):
    def test_postal_association_needs_exact_identity(self):
        from build_names import ALT, classify
        row=dict.fromkeys(ALT,'');row.update(alternate_name_id='10',geonameid='20',language='post',name='00123')
        names,postals,excluded=classify([(1,row)],{'21':'gn:21'},'BZ')
        self.assertEqual(postals,[])
        _,postals,_=classify([(1,row)],{'20':'gn:20'},'BZ')
        self.assertEqual(postals[0]['postal_code'],'00123')
        self.assertEqual(postals[0]['relation'],'source_direct_id')

    def test_ascii_and_untyped_alias_are_not_english(self):
        from build_names import ALT, classify
        from name_labels import select_label
        row=dict.fromkeys(ALT,'');row.update(alternate_name_id='10',geonameid='20',language='',name='English looking')
        names,_,_=classify([(1,row)],{'20':'gn:20'},'BZ')
        self.assertEqual(names,[])
        self.assertEqual(select_label('gn:20','Source name','en',names)['display_language'],'und')

    def test_historic_name_not_selected_as_current(self):
        from name_labels import select_label
        names=[{'entity_id':'gn:20','language':'en','name':'Old','is_historic':'1','valid_to':'','id':'geonames-alternate:1','alternate_name_id':'1','is_preferred':'1','is_colloquial':'','is_short':''}]
        self.assertEqual(select_label('gn:20','Source','en',names)['name_status'],'source_name_fallback')

    def test_language_variant_fallback_is_explicit(self):
        from name_labels import select_label
        names=[{'entity_id':'gn:20','language':'es','name':'Nombre','is_historic':'','valid_to':'','id':'geonames-alternate:1','alternate_name_id':'1','is_preferred':'1','is_colloquial':'','is_short':''}]
        result=select_label('gn:20','Source','es-GT',names)
        self.assertEqual(result['display_language'],'es')
        self.assertEqual(result['requested_language'],'es-GT')

    def test_locale_labels_never_join_equal_names(self):
        from name_labels import select_label
        names=[{'entity_id':'gn:21','language':'en','name':'English','is_historic':'','valid_to':'','id':'geonames-alternate:1','alternate_name_id':'1','is_preferred':'1','is_colloquial':'','is_short':''}]
        self.assertEqual(select_label('gn:20','Same','en',names)['name_status'],'source_name_fallback')

class PublicationScope(unittest.TestCase):
    def test_partial_scope_excludes_pending_country_payloads(self):
        import json
        from pathlib import Path
        root=Path(__file__).resolve().parent
        scope=json.loads((root/'scope.json').read_text())
        self.assertEqual({c['country'] for c in scope['countries']}, {'BZ','GT','HN','NI','PA','SV'})
        self.assertEqual(set(scope['full_m49_members']), {'BZ','CR','GT','HN','MX','NI','PA','SV'})
        self.assertFalse((root/'countries/CR').exists())
        self.assertFalse((root/'sources/CR.zip').exists())
        self.assertFalse((root/'sources/alternatenames/CR.zip').exists())
        self.assertFalse(any(line.startswith('CR\t') for line in (root/'sources/countryInfo.txt').read_text().splitlines()))

if __name__ == '__main__':
    unittest.main()
