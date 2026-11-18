"""Validate a locality name and optional state/code against preserved US, CA, MX and BR roles."""

import argparse
import csv
from importlib import import_module
import json
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

# This reader validates the manifest, index, anchors, state membership and shard
# hashes for all four snapshots, including the two outside Northern America.
snapshot = import_module('registries.north-america.validation')
COUNTRIES = ('BR', 'CA', 'MX', 'US')


def _label(text):
    # Keep ligatures and long s distinct from the letters in a source name.
    return unicodedata.normalize('NFC', text.strip()).lower()


def validate_locality(country, locality, *, region=None, source_code=None, limit=20, root=ROOT):
    """Return exact source-label matches among selectable roles for the address country."""
    if not isinstance(country, str) or not country.isascii() or country.strip().upper() not in COUNTRIES:
        raise ValueError('country must be BR, CA, MX or US')
    if not isinstance(locality, str) or not locality.strip():
        raise ValueError('locality must be a nonempty source name')
    if source_code is not None and (not isinstance(source_code, str)
                                    or not re.fullmatch(r'[0-9]+', source_code)):
        raise ValueError('source_code must be an ASCII digit string; retain leading zeroes')
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('limit must be an integer between 1 and 500')
    country = country.strip().upper()
    index, manifest, anchors, manifest_hash = snapshot.official_index(root, country)
    # Puerto Rico has PR as its address country in the US source collection.
    states = {entry['code']: entry for entry in index['regions'] if entry['code'] != 'US-PR'}
    if region is not None:
        if not isinstance(region, str) or not region.isascii() or not region.strip():
            raise ValueError('region must be a nonempty state code')
        region = region.strip().upper()
        if '-' not in region:
            region = f'{country}-{region}'
        if region not in states:
            raise ValueError(f'unknown region for address country {country}: {region}')
    sought_name = _label(locality)
    candidates = []
    matches = 0
    alternatives = []
    # First resolve the requested state. Only inspect other states to distinguish
    # a known name outside the requested state from an unobserved combination.
    ordered_codes = list(states)
    if region:
        ordered_codes.remove(region)
        ordered_codes.insert(0, region)
    for state_code in ordered_codes:
        outside_region = region is not None and state_code != region
        if outside_region and matches:
            break
        state = states[state_code]
        rows, shard_hash = snapshot.region_rows(root, country, index, manifest, anchors, state)
        for row in rows:
            if (row['address_candidate'] != '1' or _label(row['name']) != sought_name
                    or (source_code is not None and source_code != row['code'])):
                continue
            if outside_region:
                alternatives.append(state_code)
                break
            matches += 1
            if len(candidates) < limit:
                candidates.append({
                    'id': row['id'], 'name': row['name'], 'source_code': row['code'],
                    'state_code': row['state_code'], 'parent_id': row['parent_id'],
                    'source_type': row['source_type'], 'category': row['category'],
                    'reference': f"registries/official/{country}/{state['file']}",
                    'shard_sha256': shard_hash,
                })
    if matches:
        status = 'matched' if matches == 1 else 'ambiguous'
    else:
        status = 'outside_requested_region' if alternatives else 'no_match_in_snapshot'
    return {
        'country': country, 'locality': locality, 'region': region, 'source_code': source_code,
        'status': status, 'match_count': matches, 'truncated': matches > limit,
        'candidates': candidates, 'alternative_region_codes': alternatives,
        'source_vintage': index['vintage'], 'source_observed_at': manifest['observed_at'],
        'manifest_sha256': manifest_hash,
        'scope': 'exact selectable source locality role in address country and requested region',
        'postal_assignment_verified': False, 'premise_verified': False, 'deliverability_verified': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--country', required=True)
    parser.add_argument('--locality', required=True, help='full source name, including any Census role suffix')
    parser.add_argument('--region', help='source region code, e.g. CA-ON or ON')
    parser.add_argument('--source-code', help='optional exact source locality code')
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    try:
        result = validate_locality(**vars(args))
    except (ValueError, OSError, csv.Error) as exc:
        parser.exit(2, f'error: {exc}\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
