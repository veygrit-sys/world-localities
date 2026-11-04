"""Corruption, provenance and bounded-cycle regressions against real shipped data."""
import copy
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def imported(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


query = imported('hardened_northern_query', 'north-america-registry/query.py')
v = query.validation
cycle = imported('hardened_americas_cycle', 'americas-registry/quality_cycle.py')


class InputIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'north-america-registry', self.root / 'north-america-registry')
        shutil.copytree(ROOT / 'official-registry/CA', self.root / 'official-registry/CA')
        self.directory = self.root / 'official-registry/CA'

    def rewrite_json(self, relative, mutate):
        path = self.root / relative
        value = v.decode_json(path.read_bytes())
        mutate(value)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def repin(self, filename):
        self.rewrite_json('official-registry/CA/manifest.json',
                          lambda m: m['sha256'].update({filename: v.digest((self.directory / filename).read_bytes())}))

    def mutate_rows(self, mutate):
        path = self.directory / 'CA-NS.csv'
        with path.open(encoding='utf-8', newline='') as handle:
            reader = csv.DictReader(handle)
            columns, rows = reader.fieldnames, list(reader)
        mutate(rows)
        with path.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        self.repin('CA-NS.csv')

    def search(self, **kwargs):
        return query.search('CA', region='CA-NS', root=self.root, **kwargs)

    def test_real_source_hashes_and_unicode_search(self):
        result = self.search(text='Clark’s')
        self.assertEqual(result['rows_scanned'], 96)
        self.assertGreater(result['matches_found'], 0)
        self.assertEqual(result['integrity']['status'], 'passed')
        self.assertEqual(result['results'][0]['region_name'], 'Nova Scotia')

    def test_boolean_limit_is_rejected(self):
        with self.assertRaises(v.DataError):
            self.search(limit=True)

    def test_non_string_country_is_rejected(self):
        with self.assertRaises(v.DataError):
            query.search(123, root=self.root)

    def test_non_boolean_filter_is_rejected(self):
        with self.assertRaises(v.DataError):
            self.search(candidate_only='false')

    def test_duplicate_json_key_is_rejected(self):
        with self.assertRaises(v.DataError):
            v.decode_json('{"id":1,"id":2}')

    def test_non_finite_json_is_rejected(self):
        for token in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(token=token), self.assertRaises(v.DataError):
                v.decode_json('{"value":' + token + '}')

    def test_duplicate_csv_header_is_rejected(self):
        with self.assertRaises(v.DataError):
            v.csv_rows(b'id,id\na,b\n')

    def test_missing_or_extra_csv_fields_are_rejected(self):
        for data in (b'a,b\n1\n', b'a,b\n1,2,3\n'):
            with self.subTest(data=data), self.assertRaises(v.DataError):
                v.csv_rows(data)

    def test_modified_source_without_repin_is_rejected(self):
        with (self.directory / 'CA-NS.csv').open('ab') as handle:
            handle.write(b'corruption')
        with self.assertRaisesRegex(v.DataError, 'SHA-256 mismatch'):
            self.search()

    def test_truncated_source_with_repin_is_rejected(self):
        self.mutate_rows(lambda rows: rows.pop())
        with self.assertRaisesRegex(v.DataError, 'row count'):
            self.search()

    def test_duplicate_source_id_with_repin_is_rejected(self):
        self.mutate_rows(lambda rows: rows[1].update(id=rows[0]['id']))
        with self.assertRaisesRegex(v.DataError, 'duplicate'):
            self.search()

    def test_empty_name_with_repin_is_rejected(self):
        self.mutate_rows(lambda rows: rows[0].update(name=' '))
        with self.assertRaisesRegex(v.DataError, 'empty name'):
            self.search()

    def test_invalid_candidate_with_repin_is_rejected(self):
        self.mutate_rows(lambda rows: rows[0].update(address_candidate='true'))
        with self.assertRaisesRegex(v.DataError, 'candidate flag'):
            self.search()

    def test_wrong_address_country_with_repin_is_rejected(self):
        self.mutate_rows(lambda rows: rows[0].update(address_country='US'))
        with self.assertRaisesRegex(v.DataError, 'address country'):
            self.search()

    def test_missing_parent_with_repin_is_rejected(self):
        self.mutate_rows(lambda rows: rows[0].update(parent_id='missing:parent'))
        with self.assertRaisesRegex(v.DataError, 'unresolved locality parent'):
            self.search()

    def test_source_identifier_disagreement_is_rejected(self):
        self.mutate_rows(lambda rows: rows[0].update(code='9999999'))
        with self.assertRaisesRegex(v.DataError, 'source identifier'):
            self.search()

    def test_modified_index_is_rejected(self):
        self.rewrite_json('official-registry/CA/index.json', lambda x: x.update(vintage='2026'))
        with self.assertRaisesRegex(v.DataError, 'SHA-256 mismatch'):
            self.search()

    def test_empty_claims_do_not_vacuously_pass(self):
        self.rewrite_json('official-registry/CA/manifest.json', lambda x: x.update(claims={}))
        with self.assertRaisesRegex(v.DataError, 'completeness claims'):
            self.search()

    def test_duplicate_scope_country_is_rejected(self):
        self.rewrite_json('north-america-registry/scope.json', lambda x: x['countries'].append(x['countries'][0]))
        with self.assertRaisesRegex(v.DataError, 'duplicate'):
            self.search()

    def test_m49_country_code_swap_is_rejected(self):
        def swap(data):
            countries = {x['country']: x for x in data['countries']}
            countries['CA']['m49'], countries['BM']['m49'] = countries['BM']['m49'], countries['CA']['m49']
        self.rewrite_json('north-america-registry/scope.json', swap)
        with self.assertRaisesRegex(v.DataError, 'M49 code'):
            self.search()

    def test_traversal_in_source_index_is_rejected(self):
        def mutate(data):
            next(x for x in data['countries'] if x['country'] == 'CA')['source_index'] = '../outside.json'
        self.rewrite_json('north-america-registry/scope.json', mutate)
        with self.assertRaisesRegex(v.DataError, 'source path'):
            self.search()

    def test_windows_source_path_is_rejected(self):
        with self.assertRaises(v.DataError):
            v.safe_file(self.root, 'C:\\Windows\\file')

    def test_symlink_region_file_is_rejected(self):
        path = self.directory / 'CA-NS.csv'
        outside = self.root / 'outside.csv'
        path.rename(outside)
        path.symlink_to(outside)
        with self.assertRaisesRegex(v.DataError, 'symlink'):
            self.search()

    def test_seed_code_name_swap_is_rejected(self):
        def mutate(data):
            pm = [x for x in data['records'] if x['country'] == 'PM']
            pm[0]['official_code'], pm[1]['official_code'] = pm[1]['official_code'], pm[0]['official_code']
        self.rewrite_json('north-america-registry/admin-seeds.json', mutate)
        with self.assertRaisesRegex(v.DataError, 'PM code/name'):
            query.search('PM', root=self.root)

    def test_seed_false_string_is_rejected(self):
        self.rewrite_json('north-america-registry/admin-seeds.json',
                          lambda x: x['records'][0].update(can_validate_postal_or_street='false'))
        with self.assertRaisesRegex(v.DataError, 'unsafe seed claim'):
            query.search('BM', root=self.root)

    def test_seed_unexpected_publisher_is_rejected(self):
        self.rewrite_json('north-america-registry/admin-seeds.json',
                          lambda x: x['source_evidence']['bermuda_parish_profiles'].update(url='https://invalid.example/'))
        with self.assertRaisesRegex(v.DataError, 'publisher'):
            query.search('BM', root=self.root)

    def test_pending_source_does_not_ignore_candidate_filter(self):
        with self.assertRaisesRegex(v.DataError, 'requires a loaded locality source'):
            query.search('BM', candidate_only=True, root=self.root)


class QualityCycleTests(unittest.TestCase):
    @staticmethod
    def fake_inspector(root, area):
        return {'area': area, 'status': 'passed', 'input_sha256': area,
                'source_country_area_count': 1}

    def test_one_area_failure_does_not_hide_remaining_areas(self):
        called = []
        def inspector(root, area):
            called.append(area)
            if area == 'central-america':
                raise ValueError('intentional test corruption')
            return self.fake_inspector(root, area)
        result = cycle.run_cycle(inspector=inspector)
        self.assertEqual(called, cycle.ORDER)
        self.assertEqual(result['status'], 'failed')
        self.assertIsNone(result['source_country_area_count'])
        self.assertEqual(result['failed_areas'], ['central-america'])
        self.assertEqual(result['areas'][-1]['status'], 'passed')

    def test_unchanged_input_is_rechecked(self):
        first = cycle.run_cycle(inspector=self.fake_inspector)
        second = cycle.run_cycle(previous=first, inspector=self.fake_inspector)
        self.assertTrue(all(x['change_since_previous'] == 'unchanged' for x in second['areas']))

    def test_failed_previous_area_can_recover(self):
        first = cycle.run_cycle(inspector=self.fake_inspector)
        first['areas'][0]['status'] = 'failed'
        second = cycle.run_cycle(previous=first, inspector=self.fake_inspector)
        self.assertEqual(second['areas'][0]['change_since_previous'], 'recovered')

    def test_changed_content_not_just_count_is_detected(self):
        first = cycle.run_cycle(inspector=self.fake_inspector)
        first['areas'][0]['input_sha256'] = 'old-file-hash'
        second = cycle.run_cycle(previous=first, inspector=self.fake_inspector)
        self.assertEqual(second['areas'][0]['change_since_previous'], 'changed')

    def test_selected_areas_keep_north_first_order(self):
        result = cycle.run_cycle(areas=['south-america', 'northern-america'], inspector=self.fake_inspector)
        self.assertEqual(result['selected_areas'], ['northern-america', 'south-america'])
        self.assertFalse(result['is_all_americas_check'])

    def test_duplicate_area_selection_is_rejected(self):
        with self.assertRaises(ValueError):
            cycle.run_cycle(areas=['northern-america', 'northern-america'], inspector=self.fake_inspector)

    def test_country_metric_mismatch_is_not_hidden_by_continent_totals(self):
        coverage = dict.fromkeys(cycle.METRICS, '0')
        coverage['country'] = 'AG'
        metadata = {'country': {'country': 'AG'}, 'counts': dict.fromkeys(cycle.METRICS, 0)}
        coverage['unresolved_parents'] = '1'
        with self.assertRaisesRegex(ValueError, 'country metric mismatch'):
            cycle.check_country_metrics(coverage, metadata)

    def test_negative_country_metric_is_rejected(self):
        coverage = dict.fromkeys(cycle.METRICS, '0')
        coverage.update(country='AG', unresolved_parents='-1')
        metadata = {'country': {'country': 'AG'}, 'counts': dict.fromkeys(cycle.METRICS, 0)}
        with self.assertRaises(ValueError):
            cycle.check_country_metrics(coverage, metadata)

    def test_atomic_state_and_source_directory_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / 'state.json'
            cycle.atomic_state(state, {'schema_version': 1}, root=root)
            self.assertEqual(json.loads(state.read_text())['schema_version'], 1)
            with self.assertRaises(ValueError):
                cycle.atomic_state(root / 'official-registry/CA/manifest.json', {}, root=root)

    def test_failed_atomic_write_preserves_previous_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / 'state.json'
            state.write_text('previous')
            with patch.object(cycle.os, 'replace', side_effect=OSError('simulated failure')):
                with self.assertRaises(OSError):
                    cycle.atomic_state(state, {'new': True}, root=root)
            self.assertEqual(state.read_text(), 'previous')
            self.assertEqual(list(root.glob('.americas-state-*')), [])

    def test_full_real_area_cycle(self):
        result = cycle.run_cycle(ROOT)
        self.assertEqual(result['status'], 'passed', result)
        self.assertEqual(result['source_country_area_count'], 53)
        self.assertEqual(result['new_locality_records_added'], 0)
        self.assertTrue(all(x['checked_file_sha256'] for x in result['areas']))

    def test_cli_bounded_stop_and_saved_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / 'state.json'
            result = subprocess.run([sys.executable, str(ROOT / 'americas-registry/quality_cycle.py'),
                                     '--area', 'northern-america', '--rounds', '3', '--state-file', str(state)],
                                    text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            report = json.loads(result.stdout)
            self.assertEqual(report['audit_attempts'], 2)
            self.assertEqual(report['stopped_because'], 'no_validated_input_change')
            self.assertTrue(state.exists())


if __name__ == '__main__':
    unittest.main()
