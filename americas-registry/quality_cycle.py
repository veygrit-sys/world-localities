#!/usr/bin/env python3
"""Bounded north-first QA with failure isolation, source fingerprints and state diffs.

This validates stored data; it never downloads, invents, merges or publishes
new locality records. Official snapshots receive full existing row/parent QA;
regional gazetteers receive pinned metadata and per-country metric checks.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def imported(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


v = imported('cycle_validation', ROOT / 'north-america-registry/validation.py')
catalog = imported('cycle_catalog', ROOT / 'americas-registry/audit.py')
snapshots = imported('cycle_snapshots', ROOT / 'scripts/verify_americas_snapshots.py')
ORDER = [item[0] for item in catalog.AREAS]
ROSTERS = {
    'northern-america': set('BM CA GL PM US'.split()),
    'central-america': set('BZ CR SV GT HN MX NI PA'.split()),
    'caribbean': set('AG AI AW BB BL BQ BS CU CW DM DO GD GP HT JM KN KY LC MF MQ MS PR SX TC TT VC VG VI'.split()),
    'south-america': set('AR BO BR BV CL CO EC FK GF GS GY PE PY SR UY VE'.split())
}
METRICS = ('address_candidates', 'admin_rows', 'other_admin_rows', 'ambiguous_parents',
           'country_scope_only', 'localities_without_adm1', 'locality_rows', 'unresolved_parents')


def check_country_metrics(coverage, metadata):
    v.require(coverage['country'] == metadata['country']['country'], 'metadata country mismatch')
    for field in METRICS:
        text = coverage[field]
        v.require(isinstance(text, str) and re.fullmatch(r'[0-9]+', text), f'invalid coverage metric: {field}')
        expected = v.count(metadata['counts'][field], field)
        v.require(int(text) == expected, f"{coverage['country']}: country metric mismatch: {field}")
    v.require(int(coverage['address_candidates']) <= int(coverage['locality_rows']),
              'address candidates exceed locality rows')


def fingerprint(files):
    return v.digest(json.dumps(files, sort_keys=True, separators=(',', ':')).encode())


def inspect_area(root, area):
    root = Path(root).resolve()
    directory = 'north-america-registry' if area == 'northern-america' else area + '-registry'
    paths = {}
    def record(relative):
        data = v.safe_file(root, relative).read_bytes()
        paths[relative] = v.digest(data)
        return data
    scope = v.decode_json(record(directory + '/scope.json'))
    published = v.unique_rows(scope['countries'], 'country', area + ' scope')
    extra = []
    if area == 'central-america':
        extra = scope['full_m49_members']
        v.require(len(extra) == len(set(extra)), 'duplicate full M49 member')
    elif area == 'caribbean':
        extra = list(v.unique_rows(scope['omitted_countries'], 'country', 'omitted countries'))
        v.require(set(extra).isdisjoint(published), 'published/omitted scope overlap')
    v.require(set(published) | set(extra) == ROSTERS[area], 'exact M49 country roster mismatch')
    if area == 'northern-america':
        expected = {'BM': '060', 'CA': '124', 'GL': '304', 'PM': '666', 'US': '840'}
        v.require(all(row['m49'] == expected[cc] for cc, row in published.items()), 'M49 country code mismatch')
        seeds = v.decode_json(record(directory + '/admin-seeds.json'))
        v.validate_seed_data(seeds)
        record(directory + '/name-overrides.json')
    else:
        manifest = v.decode_json(record(directory + '/manifest.json'))
        if 'scope_sha256' in manifest:
            v.require(paths[directory + '/scope.json'] == manifest['scope_sha256'], 'scope hash mismatch')
        entries = v.unique_rows(manifest['countries'], 'country', area + ' manifest')
        v.require(set(entries) == set(published), 'scope/manifest country mismatch')
        coverage_bytes = record(directory + '/coverage.csv')
        if 'coverage_sha256' in manifest:
            v.require(v.digest(coverage_bytes) == manifest['coverage_sha256'], 'coverage hash mismatch')
        coverage = v.unique_rows(v.csv_rows(coverage_bytes), 'country', area + ' coverage')
        v.require(set(coverage) == set(entries), 'coverage country mismatch')
        for cc, entry in entries.items():
            relative = f'{directory}/countries/{cc}/metadata.json'
            raw = record(relative)
            v.require(v.digest(raw) == entry['metadata_sha256'], f'{cc}: metadata hash mismatch')
            metadata = v.decode_json(raw)
            check_country_metrics(coverage[cc], metadata)
    sources, notes = catalog.BUILDERS[area](root)
    v.require(set(sources) == ROSTERS[area], 'reported M49 roster mismatch')
    checked_official = []
    for cc, source in sorted(sources.items()):
        if source['layer'] and source['layer'].startswith('official-registry/'):
            index, manifest, _, _ = v.official_index(root, cc)
            for filename, expected_hash in manifest['sha256'].items():
                relative = f'official-registry/{cc}/{filename}'
                raw = record(relative)
                v.require(v.digest(raw) == expected_hash, f'{cc}: official snapshot hash mismatch')
            record(f'official-registry/{cc}/manifest.json')
            schema = v.decode_json(record('official-registry/americas-snapshot-schema.json'))
            record(f'official-registry/americas-provenance/registry/countries/{cc}.json')
            snapshots.verify_country(root / 'official-registry', cc, schema)
            checked_official.append(cc)
    if area == 'central-america':
        central = imported('central_payload_quality', ROOT / 'central-america-registry/quality.py')
        payload_report = central.verify_all(root)
        v.require(payload_report['status'] == 'passed',
                  'Central America payload validation failed: ' + str(payload_report['failed_countries']))
        government = imported('central_canton_codes', ROOT / 'central-america-registry/government_codes.py')
        government.verify(root)
        # Record all new source and derived bytes actually validated by the runner.
        for folder in ('central-america-registry/enrichment', 'central-america-registry/government-reference/CR'):
            manifest = v.decode_json(record(folder + '/manifest.json'))
            for filename in sorted(manifest['files']):
                record(folder + '/' + filename)
        record('central-america-registry/locale_manifest.json')
        for cc in central.BASE:
            folder = 'central-america-registry/countries/' + cc
            for metadata_name in ('metadata.json', 'locale_metadata.json'):
                metadata = v.decode_json(record(folder + '/' + metadata_name))
                for filename in sorted(metadata['files']):
                    record(folder + '/' + filename)
    return {
        'area': area, 'status': 'passed', 'input_sha256': fingerprint(paths),
        'checked_file_sha256': paths, 'country_area_count': len(sources),
        'source_country_area_count': sum(x['status'] == 'published_source_layer' for x in sources.values()),
        'pending_country_area_codes': sorted(cc for cc, x in sources.items() if x['status'] == 'pending_source'),
        'unresolved_parent_links': sum(x.get('unresolved_parents', 0) for x in sources.values()),
        'official_full_row_and_parent_checks': checked_official,
        'regional_gazetteer_payload_checks': ('passed_hashes_and_derived_replay_CR_raw_replay' if area == 'central-america' else 'not_run' if area != 'northern-america' else 'not_applicable'),
        'regional_check_scope': ('Seven Central America gazetteer payloads: hashes, derived columns and ID references; CR raw ZIP replay and government CodeSystem replay. Legacy six-country raw ZIP replay is not run.' if area == 'central-america' else 'pinned country metadata and country-level metrics, not compressed payload contents'),
        'quality_notes': notes,
        'upstream_freshness_verified': False, 'postal_or_address_deliverability_verified': False
    }


def run_cycle(root=ROOT, areas=None, previous=None, inspector=inspect_area):
    selected = ORDER if areas is None else [x for x in ORDER if x in areas]
    v.require(selected and (areas is None or len(selected) == len(areas)), 'invalid or duplicate requested areas')
    old = {}
    if previous is not None:
        v.require(previous.get('schema_version') == 1, 'unsupported saved state schema')
        old = v.unique_rows(previous['areas'], 'area', 'saved area states')
    results = []
    for area in selected:
        try:
            result = inspector(Path(root), area)
            prior = old.get(area)
            result['change_since_previous'] = (
                'first_check' if prior is None else
                'recovered' if prior['status'] != 'passed' else
                'unchanged' if prior['input_sha256'] == result['input_sha256'] else 'changed')
        except (ValueError, OSError, KeyError, TypeError, v.csv.Error) as exc:
            result = {'area': area, 'status': 'failed', 'error': str(exc),
                      'change_since_previous': 'failed', 'source_country_area_count': None}
        results.append(result)
    failed = [x['area'] for x in results if x['status'] != 'passed']
    return {'schema_version': 1, 'generated_at': datetime.now(timezone.utc).isoformat(),
            'status': 'failed' if failed else 'passed', 'areas': results,
            'failed_areas': failed, 'selected_areas': selected,
            'source_country_area_count': None if failed else sum(x['source_country_area_count'] for x in results),
            'is_all_americas_check': selected == ORDER,
            'fingerprint_scope': 'listed validated local files only; no live upstream or omitted gazetteer payload checks',
            'new_locality_records_added': 0}


def atomic_state(path, report, root=ROOT):
    path, root = Path(path), Path(root).resolve()
    v.require(path.suffix == '.json' and not path.is_symlink(), 'state file must be a non-symlink JSON file')
    target = path.resolve()
    protected = [root / x for x in ('north-america-registry', 'americas-registry', 'official-registry',
                 'central-america-registry', 'caribbean-registry', 'south-america-registry', 'scripts', 'tests', '.github')]
    v.require(not any(target.is_relative_to(p) for p in protected), 'state must not overwrite source directories')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.americas-state-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--area', action='append', choices=ORDER)
    parser.add_argument('--rounds', type=int, default=1)
    parser.add_argument('--state-file', type=Path)
    args = parser.parse_args()
    if not 1 <= args.rounds <= 20:
        parser.error('--rounds must be 1..20')
    previous = None
    try:
        if args.state_file and args.state_file.exists():
            v.require(not args.state_file.is_symlink(), 'symlink state rejected')
            previous = v.decode_json(args.state_file.read_bytes())
        history, reason = [], 'max_rounds'
        for attempt in range(args.rounds):
            report = run_cycle(args.root, args.area, previous)
            history.append({'attempt': attempt + 1, 'status': report['status'],
                            'area_changes': {x['area']: x['change_since_previous'] for x in report['areas']}})
            if report['status'] != 'passed':
                reason = 'validation_failed'
                break
            if all(x['change_since_previous'] == 'unchanged' for x in report['areas']):
                reason = 'no_validated_input_change'
                break
            previous = report
        report['audit_attempts'] = len(history)
        report['attempt_history'] = history
        report['stopped_because'] = reason
        if args.state_file:
            atomic_state(args.state_file, report, args.root)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f'error: {exc}\n')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report['status'] != 'passed':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
