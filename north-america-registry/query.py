#!/usr/bin/env python3
"""Search preserved US/CA localities; reject corrupt inputs before returning results."""
import argparse
import importlib.util
import json
from pathlib import Path
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('northern_input_validation', REGISTRY / 'validation.py')
validation = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(validation)
QueryError = validation.DataError


def load_json(path):
    return validation.decode_json(path.read_bytes())


def normalized(value):
    value = value.translate(str.maketrans({'’': "'", '‘': "'", '‐': '-', '‑': '-'}))
    value = unicodedata.normalize('NFKD', value.casefold())
    return ''.join(ch for ch in value if not unicodedata.combining(ch))


def _metadata(registry):
    scope = validation.load_json(registry, 'scope.json')
    corrections = validation.load_json(registry, 'name-overrides.json')
    countries = validation.unique_rows(scope['countries'], 'country', 'Northern scope')
    expected = {'BM': '060', 'CA': '124', 'GL': '304', 'PM': '666', 'US': '840'}
    validation.require(scope['region_m49'] == '021' and set(countries) == set(expected),
                       'Northern America M49 country catalogue changed')
    for cc, row in countries.items():
        validation.require(row['m49'] == expected[cc], 'country M49 code mismatch')
        if row['status'] == 'preserved_official_snapshot':
            validation.require(cc in ('US', 'CA') and row['source_index'] == f'official-registry/{cc}/index.json',
                               'unexpected official source path')
        exclusions = row.get('excluded_state_codes_for_m49', [])
        validation.require(exclusions == (['US-PR'] if cc == 'US' else []), 'invalid M49 exclusion')
    overrides = {}
    for row in corrections['entries']:
        key = (row['country'], row['state_code'])
        validation.require(key not in overrides, 'duplicate presentation override')
        validation.require(row['country'] in countries, 'override country outside scope')
        overrides[key] = row
    return scope, countries, overrides


def administrative_seeds(registry, country, text=None, limit=20):
    data = validation.load_json(registry, 'admin-seeds.json')
    validation.validate_seed_data(data)
    records = []
    for row in data['records']:
        if row['country'] != country or (text and normalized(text) not in normalized(row['source_name'])):
            continue
        evidence = data['source_evidence'][row['evidence_id']]
        records.append({
            'provisional_id': row['provisional_id'], 'name': row['source_name'],
            'language': row['language'], 'kind': row['kind'], 'official_code': row['official_code'],
            'evidence_url': evidence['url'], 'source_vintage': evidence['source_vintage'],
            'license_status': evidence['license_status'],
            'locality_status': 'administrative_seed_only', 'postal_or_street_verified': False
        })
    return records[:limit], len(records)


def display_region_name(country, region, overrides):
    change = overrides.get((country, region['code']))
    if change is None:
        return region['name']
    if region['name'] != change['snapshot_name']:
        raise QueryError('source region name changed; review display override')
    validation.require(change['status'] == 'verified_presentation_correction' and
                       bool(change['display_name_en'].strip()), 'unverified display correction')
    validation.https_evidence(change['evidence_url'])
    return change['display_name_en']


def search(country, *, region=None, text=None, limit=20, candidate_only=False,
           include_cross_region_pr=False, root=ROOT):
    """Only the selected files are validated; no live postal or source-freshness check."""
    validation.require(isinstance(country, str) and country.strip(), 'country must be a string')
    validation.require(region is None or isinstance(region, str), 'region must be a string')
    validation.require(text is None or isinstance(text, str), 'text must be a string')
    validation.require(type(limit) is int and 1 <= limit <= 500, 'limit must be an integer from 1 to 500')
    validation.require(type(candidate_only) is bool and type(include_cross_region_pr) is bool,
                       'query flags must be booleans')
    country, region = country.strip().upper(), region.strip().upper() if region else None
    root = Path(root).resolve()
    _, countries, overrides = _metadata(root / 'north-america-registry')
    profile = countries.get(country)
    if profile is None:
        raise QueryError(f'{country}: country is outside M49 Northern America (021)')
    if include_cross_region_pr and country != 'US':
        raise QueryError('the Puerto Rico source exception is only valid for US')
    if profile['status'] == 'pending_locality_source':
        if region or candidate_only:
            raise QueryError(f'{country}: region/candidate filtering requires a loaded locality source')
        seeds, count = administrative_seeds(root / 'north-america-registry', country, text, limit)
        return {
            'country': country, 'm49_region': '021', 'status': 'not_loaded',
            'source_layer': None, 'source_locality_rows': None,
            'rows_scanned': None, 'matches_found': None, 'results': [],
            'administrative_seeds': seeds, 'administrative_seed_matches': count,
            'administrative_seeds_truncated': count > limit,
            'limitations': ['Administrative seeds are not a full locality source or verified addresses.']
        }
    validation.require(profile['status'] == 'preserved_official_snapshot', 'unknown source status')
    index, manifest, anchors, manifest_hash = validation.official_index(root, country)
    regions = {r['code']: r for r in index['regions']}
    if region and region not in regions:
        raise QueryError(f'{region}: unknown source region')
    exclusions = set(profile.get('excluded_state_codes_for_m49', []))
    if region in exclusions and not include_cross_region_pr:
        raise QueryError(f'{region}: outside M49 021; use explicit --include-cross-region-pr')
    selected = [r for r in index['regions'] if (not region or r['code'] == region) and
                (r['code'] not in exclusions or include_cross_region_pr)]
    output, scanned, matched, seen, hashes = [], 0, 0, set(), {}
    needle = normalized(text) if text else None
    for state in selected:
        display = display_region_name(country, state, overrides)
        rows, file_hash = validation.region_rows(root, country, index, manifest, anchors, state)
        hashes[state['file']] = file_hash
        for row in rows:
            validation.require(row['id'] not in seen, 'duplicate ID across source regions')
            seen.add(row['id'])
            scanned += 1
            if candidate_only and row['address_candidate'] != '1':
                continue
            if needle and needle not in normalized(row['name']):
                continue
            matched += 1
            if len(output) < limit:
                output.append({
                    'id': row['id'], 'source_code': row['code'], 'name': row['name'],
                    'language': row['lang'], 'source_type': row['source_type'], 'category': row['category'],
                    'parent_id': row['parent_id'], 'region_code': state['code'], 'region_name': display,
                    'region_name_in_snapshot': state['name'], 'address_country': row['address_country'],
                    'address_candidate_flag': row['address_candidate'] == '1',
                    'postal_assignment_verified': False, 'delivery_verified': False
                })
    return {
        'country': country, 'm49_region': '021', 'status': 'source_snapshot_available',
        'source_layer': profile['source_index'], 'source_vintage': index['vintage'],
        'source_observed_at': manifest['observed_at'],
        'source_reference_date': manifest['source_manifest'].get('source_reference_date'),
        'source_locality_rows': index['counts']['source_localities'],
        'excluded_source_region_codes': sorted(exclusions) if not include_cross_region_pr else [],
        'cross_region_override_used': any(r['code'] in exclusions for r in selected),
        'rows_scanned': scanned, 'matches_found': matched, 'results_truncated': matched > limit,
        'results': output,
        'integrity': {'status': 'passed', 'scope': 'index, anchors and selected region files',
                      'manifest_sha256': manifest_hash, 'selected_file_sha256': hashes},
        'limitations': [
            'Source/statistical roles are not all independent municipalities.',
            'Integrity checks do not establish source freshness or source correctness.',
            'No verified postal assignments, street numbers, unit numbers or delivery coverage.'
        ]
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--country', required=True)
    parser.add_argument('--region')
    parser.add_argument('--text')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--candidate-only', action='store_true')
    parser.add_argument('--include-cross-region-pr', action='store_true')
    args = parser.parse_args()
    try:
        report = search(**vars(args))
    except (ValueError, OSError, KeyError, TypeError, validation.csv.Error) as exc:
        parser.exit(2, f'error: {exc}\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
