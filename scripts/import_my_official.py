"""Import the official Malaysia postcode/city/state snapshot without numeric coercion."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata

SOURCE_ID = 'my-datagov-postcodes'
SOURCE_URL = 'https://storage.data.gov.my/dictionaries/postcodes.csv'
CATALOGUE_URL = 'https://data.gov.my/data-catalogue/poskod'
LICENSE_URL = 'https://creativecommons.org/licenses/by/4.0/'
SOURCE_COLUMNS = ['state', 'city', 'postcode']
COLUMNS = ['observation_id', 'association_id', 'country', 'postcode', 'city', 'state',
           'city_normalized', 'state_normalized', 'source_ref', 'source_row']
CLAIMS = {'national_address_completeness_verified': False, 'upstream_freshness_verified': False,
          'street_verified': False, 'premise_verified': False, 'deliverability_verified': False}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def normalize_name(value):
    """Comparison key only: original names remain in independent columns."""
    return ' '.join(unicodedata.normalize('NFC', value).split())


def transform(raw):
    require(len(raw) <= 20_000_000, 'postcode CSV exceeds supported size')
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''))
    require(reader.fieldnames == SOURCE_COLUMNS, 'source CSV columns changed')
    snapshot = digest(raw)
    rows = []
    for number, item in enumerate(reader, 1):
        require(set(item) == set(SOURCE_COLUMNS) and all(isinstance(v, str) for v in item.values()),
                'source CSV field count changed')
        state, city, code = item['state'], item['city'], item['postcode']
        require(bool(re.fullmatch(r'[0-9]{5}', code)), 'postcode must retain exactly five digits')
        require(normalize_name(state) and normalize_name(city), 'empty source state or city')
        require(not any('\x00' in value for value in (state, city)), 'NUL in source name')
        association = digest(json.dumps([state, city, code], ensure_ascii=False,
                                       separators=(',', ':')).encode())[:24]
        rows.append({'observation_id': f'my:postcode-observation:{snapshot[:16]}:{number}',
                     'association_id': 'my:postcode-association:' + association,
                     'country': 'MY', 'postcode': code, 'city': city, 'state': state,
                     'city_normalized': normalize_name(city), 'state_normalized': normalize_name(state),
                     'source_ref': SOURCE_ID, 'source_row': str(number)})
    require(bool(rows), 'source postcode CSV is empty')
    return rows


def csv_bytes(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, COLUMNS, lineterminator='\n', extrasaction='raise')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8')


def counts(rows):
    raw_links = defaultdict(set)
    normalized_links = defaultdict(set)
    for row in rows:
        raw_links[row['postcode']].add((row['state'], row['city']))
        normalized_links[row['postcode']].add((row['state_normalized'], row['city_normalized']))
    return {'source_observations': len(rows), 'unique_postcodes': len(raw_links),
            'unique_raw_associations': len({r['association_id'] for r in rows}),
            'unique_normalized_associations': len({(r['postcode'], r['state_normalized'], r['city_normalized']) for r in rows}),
            'raw_state_labels': len({r['state'] for r in rows}),
            'normalized_state_labels': len({r['state_normalized'] for r in rows}),
            'rows_with_whitespace_name_changes': sum(r['state'] != r['state_normalized'] or r['city'] != r['city_normalized'] for r in rows),
            'postcodes_with_multiple_raw_associations': sum(len(v) > 1 for v in raw_links.values()),
            'postcodes_with_multiple_normalized_associations': sum(len(v) > 1 for v in normalized_links.values())}


def file_spec(content, **extra):
    return {'bytes': len(content), 'sha256': digest(content), **extra}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def build(source, output, retrieved_at=None, source_date='2026-06', source_last_modified=None):
    source, output = Path(source), Path(output)
    require(source.is_file() and not source.is_symlink(), 'source CSV missing or symlink')
    require(not output.exists() and not output.is_symlink(), 'output must be a new directory')
    raw = source.read_bytes()
    rows = transform(raw)
    plain = csv_bytes(rows)
    compressed = gzip.compress(plain, mtime=0)
    observed = retrieved_at or datetime.now(timezone.utc).isoformat()
    output.mkdir(parents=True)
    (output / 'sources').mkdir()
    (output / 'sources/postcodes.csv').write_bytes(raw)
    (output / 'records.csv.gz').write_bytes(compressed)
    source_info = {'provider': 'Government of Malaysia / data.gov.my',
                   'original_data_source': 'Malaysian Communications and Multimedia Commission',
                   'url': SOURCE_URL, 'catalogue': CATALOGUE_URL, 'retrieved_at': observed,
                   'source_date': source_date, 'as_of': source_date, 'source_date_precision': 'month',
                   'catalogue_last_updated': '2026-08-02T12:00:00+08:00',
                   'update_frequency': 'annual', 'license': 'CC-BY-4.0', 'terms': LICENSE_URL,
                   'source_last_modified': source_last_modified,
                   'source_bytes': len(raw), 'source_sha256': digest(raw),
                   'scope': 'published postcode/city/state associations; not street or premise addresses'}
    write_json(output / 'sources.json', {'schema_version': 1, 'country': 'MY',
        'sources': {SOURCE_ID: source_info},
        'bundled_files': {'sources/postcodes.csv': file_spec(raw)}})
    write_json(output / 'coverage.json', {'schema_version': 1, 'country': 'MY',
        'layer_kind': 'postcode_city_state', 'rows': len(rows), 'counts': counts(rows),
        'source_date': source_date, 'retrieved_at': observed,
        'record_file': 'records.csv.gz',
        'search_fields': ['postcode', 'city', 'state', 'city_normalized', 'state_normalized'],
        'files': {'records.csv.gz': file_spec(compressed, rows=len(rows), columns=COLUMNS,
                                            uncompressed_sha256=digest(plain))},
        'claims': CLAIMS,
        'limitations': ['Source is an annually compiled postcode/city/state list, not a building or street register.',
                        'Every source row remains; multiple associations and raw whitespace variants are not collapsed.',
                        'Names are source text; no language or translation attestation is inferred from Latin script.']})
    return verify(output)


def verify(folder):
    folder = Path(folder)
    coverage = json.loads((folder / 'coverage.json').read_text())
    sources = json.loads((folder / 'sources.json').read_text())
    require(coverage['country'] == sources['country'] == 'MY', 'country differs from MY')
    require(coverage['layer_kind'] == 'postcode_city_state', 'unsupported source layer')
    require(coverage['claims'] == CLAIMS, 'unsupported address quality claim')
    for name, spec in {**coverage['files'], **sources['bundled_files']}.items():
        require(name in {'records.csv.gz', 'sources/postcodes.csv'}, 'unexpected managed path')
        path = folder / name
        require(path.is_file() and not path.is_symlink(), 'missing or symlink managed file')
        content = path.read_bytes()
        require(len(content) == spec['bytes'] and digest(content) == spec['sha256'],
                'checksum mismatch: ' + name)
    raw = (folder / 'sources/postcodes.csv').read_bytes()
    source = sources['sources'][SOURCE_ID]
    require(len(raw) == source['source_bytes'] and digest(raw) == source['source_sha256'],
            'source receipt mismatch')
    expected = transform(raw)
    plain = gzip.decompress((folder / 'records.csv.gz').read_bytes())
    require(plain == csv_bytes(expected), 'source row replay mismatch')
    spec = coverage['files']['records.csv.gz']
    require(spec['columns'] == COLUMNS and digest(plain) == spec['uncompressed_sha256'],
            'derived schema or uncompressed checksum mismatch')
    require(spec['rows'] == coverage['rows'] == len(expected), 'row count mismatch')
    require(coverage['counts'] == counts(expected), 'source association counts mismatch')
    require(len({r['observation_id'] for r in expected}) == len(expected), 'duplicate observation IDs')
    return {'country': 'MY', 'status': 'passed', 'source_integrity': 'passed', 'row_integrity': 'passed',
            'rows': len(expected), 'counts': coverage['counts'],
            'scope': 'exact saved source replay of postcode/city/state associations only',
            'freshness_verified': None, 'national_completeness_verified': False,
            'deliverability_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    create = commands.add_parser('build')
    create.add_argument('--source', type=Path, required=True)
    create.add_argument('--output', type=Path, required=True)
    create.add_argument('--retrieved-at')
    create.add_argument('--source-date', default='2026-06')
    create.add_argument('--source-last-modified')
    check = commands.add_parser('verify')
    check.add_argument('--folder', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = (build(args.source, args.output, args.retrieved_at, args.source_date, args.source_last_modified)
                  if args.action == 'build' else verify(args.folder))
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, UnicodeError, csv.Error) as error:
        parser.exit(1, 'Malaysia import failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
