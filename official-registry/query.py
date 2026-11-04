"""Postal candidates with explicit language and full-code/prefix scope."""
import argparse
import csv
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path
from romanize import METHOD, convert

ROOT = Path(__file__).resolve().parent


def read_csv(path):
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8', newline='') as stream:
        yield from csv.DictReader(stream)


def expand_roman(row):
    row = dict(row)
    if row['roman_method'] != METHOD:
        raise ValueError('Unsupported romanization version')
    modes = row['roman_storage_modes'].split('|')
    if len(modes) != 3:
        raise ValueError('Invalid romanization modes')
    for role, mode in zip(['prefecture', 'municipality', 'town'], modes):
        if mode == 'algorithm':
            value = convert(row[role + '_kana'], row[role + '_ja'], role)
            if not value:
                raise ValueError('Cannot reproduce source romanization')
            row[role + '_roman'] = value
        elif mode not in {'literal', 'unavailable'}:
            raise ValueError('Unknown storage mode')
    return row


def lookup(country, code, language, include_prefix=False, root=ROOT):
    if country not in {'JP', 'TW'}:
        raise ValueError('Official postal layer unavailable for this profile')
    folder = Path(root) / country
    if country == 'JP':
        if re.fullmatch('[0-9]{3}-[0-9]{4}', code):
            code = code.replace('-', '')
        if not re.fullmatch('[0-9]{7}', code):
            raise ValueError('JP requires a complete 7-digit postal code')
        matching = [expand_roman(r) for r in read_csv(folder / 'postal_rows.csv.gz') if r['code'] == code]
        scope = 'full'
    else:
        if not include_prefix:
            raise ValueError('TW currently has prefix data only; explicitly enable --include-prefix')
        if not re.fullmatch('(?:[0-9]{3}|[0-9]{6})', code):
            raise ValueError('TW expects 3 prefix digits or a 6-digit code')
        matching = [r for r in read_csv(folder / 'postal_links.csv') if r['code'] == code[:3]]
        scope = 'prefix'
    ids = {r['entity_id'] for r in matching}
    names = defaultdict(list)
    for r in read_csv(folder / ('names.csv.gz' if country == 'JP' else 'names.csv')):
        if r['entity_id'] in ids and r['language'] == language:
            names[r['entity_id']].append(r)
    candidates = [{'entity_id': eid, 'requested_language': language, 'names': names[eid],
                   'name_status': 'available' if names[eid] else 'missing_requested_language'} for eid in sorted(ids)]
    return {'country': country, 'input_code': code, 'match_scope': scope,
            'complete_postcode_verified': scope == 'full' and bool(matching), 'delivery_verified': False,
            'candidates': candidates, 'postal_source_rows': len(matching), 'postal_rows': matching}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--country', choices=['JP', 'TW'], required=True)
    p.add_argument('--postal-code', required=True)
    p.add_argument('--language', default='en')
    p.add_argument('--include-prefix', action='store_true')
    p.add_argument('--limit', type=int, default=20, help='Postal rows only; all candidate IDs remain')
    args = p.parse_args()
    if args.limit < 0:
        p.error('--limit must be nonnegative')
    try:
        result = lookup(args.country, args.postal_code, args.language, args.include_prefix)
    except ValueError as error:
        p.error(str(error))
    result['postal_rows'] = result['postal_rows'][:args.limit]
    result['rows_truncated'] = result['postal_source_rows'] > len(result['postal_rows'])
    print(json.dumps(result, ensure_ascii=False, indent=2))
