#!/usr/bin/env python3
"""Unified Central America search without mixing source IDs or inventing translations."""
import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = Path(__file__).resolve().parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, DIRECTORY / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


quality = module('enriched_central_quality', 'quality.py')
require = quality.supplement.require


def normalized(value):
    text = unicodedata.normalize('NFKD', value.casefold())
    return ''.join(c for c in text if not unicodedata.combining(c)).translate(str.maketrans({'’': "'", '‐': '-', '‑': '-'}))


def label(row, language, names):
    original_language = row.get('lang', 'und')
    eligible = [r for r in names if r['language'] == language and r['is_historic'] != '1' and not r['valid_to']]
    eligible.sort(key=lambda r: (r['is_preferred'] != '1', int(r['alternate_name_id'])))
    if language and eligible:
        chosen = eligible[0]
        return {'display_name': chosen['name'], 'label_language': chosen['language'],
                'label_source_id': chosen['id'], 'fallback_used': False,
                'label_status': 'language_tagged_source_name_not_independently_official'}
    return {'display_name': row['name'], 'label_language': original_language,
            'label_source_id': row['id'], 'fallback_used': bool(language and language != original_language),
            'label_status': 'preserved_source_name'}


def search(country, *, text=None, language=None, kind=None, level=None, region=None,
           parent=None, include_other=False, limit=20, offset=0, layer='source', root=ROOT):
    require(isinstance(country, str), 'country must be a string')
    country = country.strip().upper()
    require(country in quality.COUNTRIES, 'country is outside M49 Central America')
    require(type(limit) is int and 1 <= limit <= 500 and type(offset) is int and offset >= 0,
            'limit must be 1..500 and offset a nonnegative integer')
    require(type(include_other) is bool, 'include_other must be a boolean')
    require(all(value is None or isinstance(value, str) for value in (text, language, kind, region, parent)),
            'query filters must be strings')
    require(level is None or (type(level) is int and 1 <= level <= 5), 'level must be 1..5')
    require(kind is None or kind in ('locality', 'admin_subdivision', 'other_admin_feature'), 'invalid kind')
    require(layer in ('source', 'government-cantons'), 'invalid layer')
    if layer == 'government-cantons':
        require(country == 'CR' and not any((kind, level, region, parent, language, include_other)),
                'government-cantons supports CR and text/pagination only')
        government = module('central_government_codes', 'government_codes.py')
        status = government.verify(root)
        rows = government.v.load_json(Path(root) / government.DIRECTORY, 'cantons.json')
        selected = [r for r in rows if not text or normalized(text) in normalized(r['name'])]
        return {'country': country, 'layer': layer, 'total': len(selected), 'offset': offset,
                'results': selected[offset:offset + limit], 'integrity': status,
                'limits': ['Government-published versioned CodeSystem, not current legal boundary verification or a GeoNames crosswalk.']}
    rows, names, status = quality.load_country(country, root)
    by_entity = defaultdict(list)
    for row in names:
        by_entity[row['entity_id']].append(row)
    if country == 'MX':
        require(not any((kind, level, parent)), 'Mexico retains the distinct official schema; use region/text filters')
    needle = normalized(text) if text else None
    matches, output = 0, []
    for row in rows:
        if kind and row.get('kind') != kind:
            continue
        if level and row.get('admin_level') != str(level):
            continue
        if region and region not in (row.get('state_id'), row.get('state_code'), row.get('admin1_code')):
            continue
        if parent and row['parent_id'] != parent:
            continue
        if not include_other and not kind and not level and row['address_candidate'] != '1':
            continue
        aliases = by_entity[row['id']]
        candidates = [row['name'], row.get('asciiname', '')] + row.get('alternatenames', '').split(',') + [r['name'] for r in aliases]
        if needle and not any(needle in normalized(value) for value in candidates):
            continue
        if offset <= matches < offset + limit:
            output.append(dict(row, **label(row, language, aliases), delivery_verified=False))
        matches += 1
    return {'country': country, 'region_m49': '013', 'layer': layer, 'total': matches,
            'offset': offset, 'results_truncated': matches > offset + limit, 'results': output,
            'integrity': status,
            'limits': ['Source IDs and source vintages are preserved across languages.',
                       'Missing requested-language labels return an explicit fallback, never generated official English.',
                       'Postal number, street, house and unit deliverability are not verified.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--country', required=True)
    parser.add_argument('--text')
    parser.add_argument('--language')
    parser.add_argument('--kind', choices=('locality', 'admin_subdivision', 'other_admin_feature'))
    parser.add_argument('--level', type=int, choices=range(1, 6))
    parser.add_argument('--region')
    parser.add_argument('--parent')
    parser.add_argument('--include-other', action='store_true')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--layer', choices=('source', 'government-cantons'), default='source')
    args = parser.parse_args()
    try:
        result = search(**vars(args))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f'error: {exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
