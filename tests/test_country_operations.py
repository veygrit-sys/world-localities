"""Country selection, honest result scope and isolated-output integrity regressions."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from localities import country

ROOT = Path(__file__).resolve().parents[1]


class CountryOperationTests(unittest.TestCase):
    def test_semantic_catalog_preserves_all_scope_codes_and_shared_records(self):
        report = country.validate_catalog(ROOT)
        self.assertEqual(report['countries'], 250)
        for code in ('BM', 'GL', 'PM'):
            result = country.inspect_country(code, ROOT)
            self.assertEqual(result['inventory_state'], 'partial_observations')
            observations = next(e for e in result['layers'] if e['kind'] == 'shared_records')
            self.assertGreater(observations['selected_observations'], 0)
            self.assertEqual(observations['selector']['value'], code)
            self.assertIn('curated_on', observations['source_dates'])

    def test_country_quality_keeps_source_counts_and_unknown_freshness(self):
        result = country.inspect_country('DE', ROOT)
        layer = next(e for e in result['layers'] if e['registry'] == 'europe')
        self.assertEqual(layer['counts']['unresolved_parents'], 191)
        self.assertIn('retrieved_at', layer['source_dates']['source_file'])
        self.assertIsNone(result['freshness_verified'])
        self.assertFalse(result['national_completeness_verified'])
        self.assertIn('do not sum', result['counts_policy'])

    def test_japan_runs_archive_replay_and_official_integrity_without_source_writes(self):
        path = ROOT / 'registries/asia/archives.json'
        original = path.read_bytes()
        report = country.verify_country('JP', ROOT)
        self.assertEqual(report['status'], 'passed', report)
        layers = {e['id']: e for e in report['layers']}
        self.assertEqual(layers['asia-gazetteer']['row_integrity'], 'passed')
        self.assertEqual(layers['official-overlay']['source_integrity'], 'passed')
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse((ROOT / 'registries/asia/countries/JP/verification.json').exists())

    def test_official_expansions_expose_country_specific_evidence(self):
        for code in ('HK', 'KR', 'MY', 'TW'):
            with self.subTest(country=code):
                report = country.inspect_country(code, ROOT)
                layer = next(e for e in report['layers'] if e['id'] == 'official-expansion')
                prefix = 'registries/official/expansions/' + code
                self.assertEqual(layer['data'], prefix)
                self.assertIn(prefix + '/sources.json', layer['source_refs'])
                self.assertIn(prefix + '/NOTICE.md', layer['notice_refs'])
                self.assertGreater(layer['counts']['source_observations'], 0)
                self.assertTrue(layer['source_dates'])
                self.assertIsNone(layer['freshness_verified'])
                self.assertFalse(layer['national_completeness_verified'])
                self.assertFalse(layer['deliverability_verified'])

    def test_official_adapter_rejects_another_country_folder(self):
        layer = {'verifier': 'official_expansion', 'id': 'bad-layer',
                 'data': 'registries/official/expansions/TW'}
        with self.assertRaisesRegex(ValueError, 'official expansion country path mismatch'):
            country._verify_layer(layer, 'MY', ROOT)

    def test_europe_original_replay_is_available_for_one_country(self):
        report = country.verify_country('AD', ROOT)
        self.assertEqual(report['status'], 'passed', report)
        self.assertEqual(next(e for e in report['layers'] if e['id'] == 'europe-gazetteer')['row_integrity'], 'passed')

    def test_format_only_country_does_not_claim_data_verification(self):
        report = country.verify_country('AQ', ROOT)
        self.assertEqual(report['status'], 'unsupported')
        self.assertTrue(all(e['source_integrity'] == 'not_checked' for e in report['layers']))

    def test_unknown_country_and_unsafe_paths_are_rejected(self):
        for code in ('ZZ', 'jp', '../JP'):
            with self.assertRaises(ValueError):
                country.inspect_country(code, ROOT)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'outside').symlink_to(root.parent, target_is_directory=True)
            for path in ('../outside', '/etc/passwd', 'outside/data'):
                with self.assertRaises(ValueError):
                    country._path(root, path)

    def test_corrupted_country_payload_is_a_failed_integrity_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'countries', root / 'countries')
            source = ROOT / 'registries/europe/countries/AD'
            destination = root / 'registries/europe/countries/AD'
            shutil.copytree(source, destination)
            payload = next(destination.glob('entities-*.csv.gz'))
            content = payload.read_bytes()
            payload.write_bytes(content[:-1] + bytes([content[-1] ^ 1]))
            report = country.verify_country('AD', root)
            self.assertEqual(report['status'], 'failed')
            self.assertIn('checksum mismatch', report['layers'][0]['error'])

    def test_restore_requires_new_external_output_and_preserves_original_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / 'restored'
            report = country.restore_country('BM', output, ROOT)
            self.assertEqual(report['status'], 'passed')
            relative = Path('registries/north-america/admin-seeds.json')
            self.assertEqual((output / relative).read_bytes(), (ROOT / relative).read_bytes())
            with self.assertRaises(ValueError):
                country.restore_country('BM', output, ROOT)
            with self.assertRaises(ValueError):
                country.restore_country('BM', ROOT / 'country-output-must-not-be-created', ROOT)
            alias = root / 'alias'
            alias.symlink_to(root, target_is_directory=True)
            with self.assertRaises(ValueError):
                country.restore_country('BM', alias / 'new', ROOT)

    def test_selector_cannot_relabel_shared_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = country.load_modules(ROOT)
            bm = next(e for e in data['countries'] if e['code'] == 'BM')
            next(e for e in bm['layers'] if e['kind'] == 'shared_records')['selector']['value'] = 'GL'
            (root / 'countries').mkdir()
            (root / 'countries/modules.json').write_text(json.dumps(data))
            shutil.copyfile(ROOT / 'countries/catalog.json', root / 'countries/catalog.json')
            directory = root / 'registries/north-america'
            directory.mkdir(parents=True)
            shutil.copyfile(ROOT / 'registries/north-america/admin-seeds.json', directory / 'admin-seeds.json')
            data['registries'] = {'north-america': {'path': 'registries/north-america',
                'source_refs': [], 'notice_refs': [], 'test_refs': []}}
            for entry in data['countries']:
                entry['layers'] = ([next(e for e in bm['layers'] if e['kind'] == 'shared_records')]
                    if entry['code'] == 'BM' else [])
            (root / 'countries/modules.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "country selector mismatch"):
                country.validate_catalog(root)


if __name__ == '__main__':
    unittest.main()
