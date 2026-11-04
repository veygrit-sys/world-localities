"""Central America enrichment acceptance and corruption regressions, fully offline."""
import copy
import gzip
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def imported(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


supplement = imported('test_cr_supplement', 'central-america-registry/supplement.py')
quality = imported('test_central_quality', 'central-america-registry/quality.py')
query = imported('test_central_query', 'central-america-registry/query_enriched.py')
government = imported('test_cr_government', 'central-america-registry/government_codes.py')


class CentralAmericaAcceptanceTests(unittest.TestCase):
    def test_costa_rica_all_retained_rows_replay_from_raw_archives(self):
        report = supplement.verify(ROOT)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['raw_source_replay'], 'exact')
        self.assertEqual(report['entities'], 6465)
        self.assertEqual(report['locality_rows'], 5900)
        self.assertEqual(report['language_tagged_names'], 6182)
        self.assertEqual(report['postal_links'], 0)

    def test_all_eight_countries_validate_actual_payloads(self):
        report = quality.verify_all(ROOT)
        self.assertEqual(report['status'], 'passed', report)
        self.assertEqual(report['country_source_coverage'], '8/8')
        self.assertEqual([r['country'] for r in report['countries']], list(quality.COUNTRIES))
        self.assertIsNone(report['unique_real_world_locality_count'])

    def test_legacy_six_country_snapshot_is_not_reclassified(self):
        manifest = json.loads((ROOT / 'central-america-registry/manifest.json').read_text())
        self.assertEqual({r['country'] for r in manifest['countries']}, set(quality.BASE))
        self.assertEqual(manifest['totals']['locality_rows'], 51263)

    def test_mexico_remains_a_separate_inegi_source(self):
        rows, names, report = quality.load_country('MX', ROOT)
        self.assertEqual(len(rows), 2478)
        self.assertEqual(names, [])
        self.assertEqual(report['source_format'], 'official_inegi_snapshot')
        self.assertFalse(report['delivery_verified'])

    def test_exact_government_code_source_replay(self):
        report = government.verify(ROOT)
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['cantons'], 84)
        self.assertIn('source_date', report)

    def test_new_canton_codes_do_not_forge_geonames_identity(self):
        result = query.search('CR', layer='government-cantons', text='Monteverde')
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['results'][0]['code'], '612')
        self.assertIsNone(result['results'][0]['geonames_id'])
        jimenez = query.search('CR', layer='government-cantons', text='Puerto Jimenez')
        self.assertEqual(jimenez['results'][0]['code'], '613')

    def test_source_82_cantons_and_government_84_are_not_silently_merged(self):
        source = query.search('CR', level=2, limit=100)
        government_view = query.search('CR', layer='government-cantons', limit=100)
        self.assertEqual(source['total'], 82)
        self.assertEqual(government_view['total'], 84)
        self.assertTrue(all(r['id'].startswith('gn:') for r in source['results']))
        self.assertTrue(all(r['id'].startswith('admin:cr:minsa:') for r in government_view['results']))

    def test_default_search_excludes_abandoned_source_places(self):
        result = query.search('CR', limit=1)
        self.assertEqual(result['total'], 5781)
        self.assertEqual(result['results'][0]['address_candidate'], '1')
        all_places = query.search('CR', kind='locality', limit=1)
        self.assertEqual(all_places['total'], 5900)

    def test_unicode_search_and_missing_language_fallback(self):
        result = query.search(' cr ', text='San Jose', language='zz', limit=5)
        self.assertTrue(result['results'])
        for row in result['results']:
            self.assertTrue(row['fallback_used'])
            self.assertEqual(row['label_language'], 'und')
            self.assertEqual(row['display_name'], row['name'])
            self.assertFalse(row['delivery_verified'])

    def test_language_selection_does_not_change_entity_ids(self):
        original = query.search('CR', text='San Jose', limit=5)
        translated = query.search('CR', text='San Jose', language='es', limit=5)
        self.assertEqual([r['id'] for r in original['results']], [r['id'] for r in translated['results']])

    def test_pagination_has_no_overlap(self):
        first = query.search('CR', limit=3)
        next_page = query.search('CR', limit=3, offset=3)
        self.assertEqual(first['total'], next_page['total'])
        self.assertFalse({r['id'] for r in first['results']} & {r['id'] for r in next_page['results']})

    def test_import_is_create_only_and_reuses_pinned_snapshot(self):
        with patch.object(supplement, 'download_sources', side_effect=AssertionError('network forbidden')):
            self.assertEqual(supplement.import_once(ROOT)['status'], 'passed')

    def test_query_rejects_boolean_limit_and_wrong_scope(self):
        with self.assertRaises(ValueError):
            query.search('CR', limit=True)
        with self.assertRaises(ValueError):
            query.search('CU')
        with self.assertRaises(ValueError):
            query.search('MX', layer='government-cantons')

    def test_mexico_rejects_geonames_only_filters(self):
        with self.assertRaises(ValueError):
            query.search('MX', level=2)

    def test_government_code_name_swap_is_rejected(self):
        source = government.v.load_json(ROOT / government.DIRECTORY, 'source.json')
        source = copy.deepcopy(source)
        for concept in source['concept']:
            if concept['code'] == '612':
                concept['display'] = 'Puerto Jiménez'
        with self.assertRaises(ValueError):
            government.parsed_codes(source)

    def test_government_duplicate_code_is_rejected(self):
        source = government.v.load_json(ROOT / government.DIRECTORY, 'source.json')
        source['concept'].append(copy.deepcopy(source['concept'][0]))
        with self.assertRaises(ValueError):
            government.parsed_codes(source)

    def test_eight_country_roster_reaches_53_of_57_americas_sources(self):
        audit = imported('central_final_audit', 'americas-registry/audit.py')
        report = audit.audit(ROOT)
        self.assertEqual(report['source_country_area_count'], 53)
        central = next(r for r in report['areas'] if r['key'] == 'central-america')
        self.assertEqual(central['source_country_area_count'], 8)
        self.assertEqual(central['pending_country_area_codes'], [])


class CostaRicaCorruptionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = self.root / supplement.RELATIVE
        shutil.copytree(ROOT / supplement.RELATIVE, self.data)

    def repin(self, relative):
        path = self.data / 'manifest.json'
        manifest = json.loads(path.read_text())
        data = (self.data / relative).read_bytes()
        manifest['files'][relative] = {'bytes': len(data), 'sha256': supplement.sha(data)}
        path.write_text(json.dumps(manifest), encoding='utf-8')

    def test_modified_compressed_data_is_rejected(self):
        with (self.data / 'countries/CR/entities.csv.gz').open('ab') as handle:
            handle.write(b'corruption')
        with self.assertRaises(ValueError):
            supplement.verify(self.root)

    def test_rehashed_fabricated_name_still_fails_raw_replay(self):
        b, _, v = supplement.libraries()
        path = self.data / 'countries/CR/entities.csv.gz'
        rows = v.csv_rows(gzip.decompress(path.read_bytes()), b.FIELDS)
        rows[0]['name'] = 'Not an attested source name'
        path.write_bytes(b.compressed(b.csv_bytes(rows)))
        self.repin('countries/CR/entities.csv.gz')
        with self.assertRaisesRegex(ValueError, 'source replay'):
            supplement.verify(self.root)

    def test_rehashed_country_metrics_are_replayed(self):
        path = self.data / 'countries/CR/metadata.json'
        meta = json.loads(path.read_text())
        meta['counts']['locality_rows'] += 1
        path.write_text(json.dumps(meta), encoding='utf-8')
        self.repin('countries/CR/metadata.json')
        with self.assertRaisesRegex(ValueError, 'count mismatch'):
            supplement.verify(self.root)

    def test_rehashed_aggregate_summary_is_rejected(self):
        path = self.data / 'summary.json'
        meta = json.loads(path.read_text())
        meta['unresolved_parents'] = 0
        path.write_text(json.dumps(meta), encoding='utf-8')
        self.repin('summary.json')
        with self.assertRaisesRegex(ValueError, 'summary replay'):
            supplement.verify(self.root)

    def test_deliverability_claim_is_rejected(self):
        path = self.data / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['claims']['postal_delivery_verified'] = True
        path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'unsafe supplement claims'):
            supplement.verify(self.root)

    def test_extra_untracked_source_is_rejected(self):
        (self.data / 'untracked.csv').write_text('unexpected')
        with self.assertRaisesRegex(ValueError, 'unexpected supplement files'):
            supplement.verify(self.root)

    def test_zip_traversal_member_is_never_extracted(self):
        archive = self.root / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as handle:
            handle.writestr('../CR.txt', 'bad')
        with self.assertRaisesRegex(ValueError, 'source ZIP member'):
            supplement.bounded_zip(archive, 'CR.txt')
        self.assertFalse((self.root.parent / 'CR.txt').exists())

    def test_duplicate_zip_member_is_rejected(self):
        archive = self.root / 'duplicate.zip'
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(archive, 'w') as handle:
                handle.writestr('CR.txt', 'one')
                handle.writestr('CR.txt', 'two')
        with self.assertRaises(ValueError):
            supplement.bounded_zip(archive, 'CR.txt')

    def test_source_symlink_is_rejected(self):
        path = self.data / 'sources/CR.zip'
        outside = self.root / 'outside.zip'
        path.rename(outside)
        path.symlink_to(outside)
        with self.assertRaises(ValueError):
            supplement.verify(self.root)


if __name__ == '__main__':
    unittest.main()
