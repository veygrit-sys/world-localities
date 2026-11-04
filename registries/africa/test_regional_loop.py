"""Offline adversarial tests; fixtures are synthetic, never geographic evidence."""
import copy
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from datetime import date
import regional_loop as loop


def entity(eid='gn:1', name='Fixture', modified='2026-10-01'):
    return dict(id=eid, name=name, feature_code='PPL', admin1_code='01',
                admin2_code='', admin3_code='', admin4_code='', parent_id='gn:2',
                parent_relation='source_admin_code', modification_date=modified)


def alt(aid='1', gid='1', lang='ar', value='مدينة', historic='', width=10):
    return '\t'.join([aid,gid,lang,value,'1','','',historic,'',''][:width]) + '\n'


class RegionalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
    def tearDown(self):
        self.temporary.cleanup()
    def scope(self):
        countries = [dict(country=cc, region=name) for name,codes in loop.REGIONS.values() for cc in codes]
        loop.save_json(self.root/'upstream/scope.json', dict(countries=countries))
        return countries
    def test_all_sixty_once_north_first(self):
        self.scope()
        rows=loop.ordered_scope(self.root,list(reversed(loop.REGIONS)))
        self.assertEqual(len(rows),60)
        self.assertEqual([c['country'] for _,c in rows[:7]],'DZ EG LY MA SD TN EH'.split())
        self.assertEqual(rows[-1][0],'south')
    def test_ma_cd_mg_ng_included(self):
        self.scope()
        countries={c['country'] for _,c in loop.ordered_scope(self.root,list(loop.REGIONS))}
        self.assertTrue({'MA','CD','MG','NG'}<=countries)
    def test_scope_drift_rejected(self):
        countries=self.scope()[:-1]
        loop.save_json(self.root/'upstream/scope.json',dict(countries=countries))
        with self.assertRaises(ValueError):loop.ordered_scope(self.root,['north'])
    def test_duplicate_scope_rejected(self):
        countries=self.scope();countries.append(countries[0])
        loop.save_json(self.root/'upstream/scope.json',dict(countries=countries))
        with self.assertRaises(ValueError):loop.ordered_scope(self.root,['north'])
    def test_wrong_region_rejected(self):
        countries=self.scope();countries[0]['region']='Western Africa'
        loop.save_json(self.root/'upstream/scope.json',dict(countries=countries))
        with self.assertRaises(ValueError):loop.ordered_scope(self.root,['north'])
    def test_duplicate_request_rejected(self):
        self.scope()
        with self.assertRaises(ValueError):loop.ordered_scope(self.root,['north','north'])
    def test_names_eight_and_ten_columns_preserved(self):
        rows,stats=loop.collect_names([alt(width=8),alt(aid='2',lang='fr',value='École')],{'gn:1'})
        self.assertEqual(stats['source_formats'],{'8':1,'10':1})
        self.assertEqual(rows[0]['alternate_name'],'مدينة')
        self.assertEqual(rows[1]['alternate_name'],'École')
    def test_nonlanguage_not_translation(self):
        rows,stats=loop.collect_names([alt(lang='post',value='00123')],{'gn:1'})
        self.assertEqual(rows[0]['value_kind'],'external_identifier')
        self.assertEqual(rows[0]['alternate_name'],'00123')
        self.assertEqual(stats['language_names'],0)
    def test_historic_flag_not_lost(self):
        rows,stats=loop.collect_names([alt(historic='1')],{'gn:1'})
        self.assertEqual(rows[0]['isHistoric'],'1')
        self.assertEqual(stats['historical_names'],1)
    def test_missing_entity_not_linked_by_name(self):
        rows,stats=loop.collect_names([alt(gid='999')],{'gn:1'})
        self.assertEqual(rows,[]);self.assertEqual(stats['out_of_scope'],1)
    def test_duplicate_name_id_rejected(self):
        with self.assertRaises(ValueError):loop.collect_names([alt(),alt()],{'gn:1'})
    def test_invalid_flag_rejected(self):
        with self.assertRaises(ValueError):loop.collect_names([alt(historic='yes')],{'gn:1'})
    def test_schema_drift_rejected(self):
        with self.assertRaises(ValueError):loop.collect_names(['1\t2\t3\n'],{'gn:1'})
    def test_unicode_preserved_and_not_overmerged(self):
        self.assertEqual(loop.search_key(' E\u0301cole  '),'école')
        self.assertNotEqual(loop.search_key('Aïn'),loop.search_key('Ain'))
        self.assertNotEqual(loop.search_key('أ'),loop.search_key('ا'))
    def test_gzip_is_deterministic(self):
        self.assertEqual(loop.gzip_bytes(b'test'),loop.gzip_bytes(b'test'))
        self.assertEqual(gzip.decompress(loop.gzip_bytes(b'test')),b'test')
    def test_real_calendar_and_finite_coordinates(self):
        row=dict(country_code='DZ',geonameid='1',feature_class='P',name='Fixture',
                 latitude='1',longitude='2',modification_date='2026-10-01')
        loop.validate_raw([row],'DZ',date(2026,10,15))
        for key,value in [('latitude','nan'),('longitude','inf'),
                          ('modification_date','2026-02-30'),('modification_date','2027-01-01')]:
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):
                loop.validate_raw([dict(row,**{key:value})],'DZ',date(2026,10,15))
    def test_removed_id_is_review_not_deletion(self):
        old=[entity(),entity('gn:3')];new=[entity()]
        delta=loop.compare_baseline(old,new,True)
        self.assertEqual(delta['removed_ids'],['gn:3'])
        self.assertIn('source_ids_disappeared_review_before_removal',loop.release_blockers(delta,old,new))
        self.assertEqual(len(old),2)
    def test_older_source_is_blocked(self):
        old=[entity(modified='2026-10-02')];new=[entity(modified='2026-10-01')]
        delta=loop.compare_baseline(old,new,True)
        self.assertIn('candidate_is_older_than_baseline',loop.release_blockers(delta,old,new))
    def test_unchanged_replay_has_zero_delta(self):
        old=[entity()];delta=loop.compare_baseline(old,copy.deepcopy(old),True)
        self.assertEqual([delta[k] for k in ('added','removed','changed')],[0,0,0])
        self.assertEqual(loop.release_blockers(delta,old,old),[])
    def test_offline_never_downloads(self):
        with patch.object(loop,'urlopen') as request,self.assertRaises(ValueError):
            loop.fetch('DZ.zip',self.root,True)
        request.assert_not_called()
    def test_cache_tampering_rejected(self):
        (self.root/'DZ.zip').write_bytes(b'bad')
        loop.save_json(self.root/'DZ.source.json',dict(url=loop.DUMP+'DZ.zip',sha256='wrong'))
        with self.assertRaises(ValueError):loop.fetch('DZ.zip',self.root,True)
    def test_path_traversal_rejected(self):
        with self.assertRaises(ValueError):loop.fetch('../DZ.zip',self.root,True)
    def test_wrong_zip_member_rejected(self):
        archive=self.root/'bad.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('../DZ.txt','bad')
        with self.assertRaises(ValueError):list(loop.zip_lines(archive,'DZ'))
    def test_official_source_eleven_records(self):
        source=loop.read_json(Path(__file__).parent/'official-references/DZ-2026-wilayas.json')
        loop.validate_official_reference(source)
        self.assertEqual(source['records'][6]['name_fr'],'Aïn Ouessara')
    def test_invented_official_crosswalk_rejected(self):
        source=loop.read_json(Path(__file__).parent/'official-references/DZ-2026-wilayas.json')
        source['records'][0]['iso_3166_2']='DZ-59'
        with self.assertRaises(ValueError):loop.validate_official_reference(source)

    def test_output_and_cache_overlap_rejected(self):
        with self.assertRaisesRegex(ValueError, 'must not overlap'):
            loop.run(self.root/'baseline', self.root/'out', self.root/'out/cache', ['north'], True)
    def test_cache_without_receipt_rejected(self):
        (self.root/'DZ.zip').write_bytes(b'untrusted')
        with self.assertRaisesRegex(ValueError, 'missing provenance'):
            loop.fetch('DZ.zip',self.root,True)
    def test_unknown_region_rejected(self):
        self.scope()
        with self.assertRaisesRegex(ValueError, 'unknown region'):
            loop.ordered_scope(self.root,['antarctica'])


if __name__=='__main__':unittest.main()
