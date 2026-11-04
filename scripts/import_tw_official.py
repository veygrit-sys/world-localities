#!/usr/bin/env python3
"""Replay Taiwan MOI ODRP049 road names without inferring address validity."""
from __future__ import annotations

import argparse
import collections
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = ROOT / 'registries/official/expansions/TW'
POSTAL_ROOT = ROOT / 'registries/official/TW'
SOURCE_REF = 'tw-moi-odrp049-115'
SOURCE_URL = 'https://opdadm.moi.gov.tw/api/v1/no-auth/resource/api/dataset/E2EDC47D-2D3F-4EB1-878A-4DEB6160FD4C/resource/EB1B8C49-5C2A-42E0-8CC3-6B69B37DA66F/download'
API_URL = 'https://www.ris.gov.tw/rs-opendata/api/v1/datastore/ODRP049/115'
SEARCH_FIELDS = ['city', 'site_id', 'road', 'postal_area_name_en', 'postal_prefixes']
FIELDS = ['record_id', 'country', 'source_ref', 'source_row', 'source_year', 'city', 'site_id', 'road', 'road_en', 'road_en_status', 'postal_area_id', 'postal_area_link_status', 'postal_prefixes', 'postal_code_scope', 'postal_area_name_en', 'postal_area_name_en_status']
CLAIMS = {'national_completeness': False, 'currentness': False, 'house_number_coverage': False, 'full_postcode_coverage': False, 'delivery_coverage': False, 'legal_admin_equivalence': False}
RAW_FILE = 'sources/national-roads-115.csv.gz'
PROBE_FILE = 'sources/api-probe-115-page1.json.gz'
POSTAL_FILES = ['entities.csv', 'names.csv', 'postal_links.csv', 'sources.json']


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_bytes(path):
    data = Path(path).read_bytes()
    return gzip.decompress(data) if data[:2] == b'\x1f\x8b' else data


def load_csv(data, fields=None):
    reader = csv.DictReader(io.StringIO(data.decode('utf-8-sig'), newline=''))
    if fields is not None and reader.fieldnames != fields:
        raise ValueError(f'Unexpected CSV fields/delimiter: {reader.fieldnames!r}')
    rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError('Malformed CSV row')
    return rows


def parse_source(data):
    rows = load_csv(data, ['city', 'site_id', 'road'])
    seen = set()
    for row in rows:
        key = (row['city'], row['site_id'], row['road'])
        if any(not value.strip() for value in key):
            raise ValueError('Empty source identity')
        if not row['site_id'].startswith(row['city']):
            raise ValueError('site_id must retain its source city parent')
        if key in seen:
            raise ValueError('Duplicate source identity')
        seen.add(key)
    if not rows:
        raise ValueError('Empty road-name source')
    return rows


def fold_whitespace(text):
    return ''.join(text.split())


def postal_context(folder, snapshot=False):
    def filename(name):
        return folder / ('sources/postal-' + name if snapshot else name)
    entities = load_csv(filename('entities.csv').read_bytes())
    names = load_csv(filename('names.csv').read_bytes())
    links = load_csv(filename('postal_links.csv').read_bytes())
    exact = collections.defaultdict(set)
    folded = collections.defaultdict(set)
    english = collections.defaultdict(set)
    prefixes = collections.defaultdict(set)
    for row in entities:
        if row['country'] == 'TW' and row['kind'] == 'postal_area':
            exact[row['native_name']].add(row['entity_id'])
            folded[fold_whitespace(row['native_name'])].add(row['entity_id'])
    for row in names:
        if row['language'] == 'en':
            english[row['entity_id']].add(row['text'])
    for row in links:
        if row['country'] == 'TW' and row['code_kind'] == 'prefix' and row['prefix_length'] == '3' and row['complete_code_length'] == '6':
            if len(row['code']) != 3 or not row['code'].isdigit():
                raise ValueError('Invalid three-digit postal prefix')
            prefixes[row['entity_id']].add(row['code'])
    return exact, folded, english, prefixes


def record_id(row):
    identity = json.dumps([row['city'], row['site_id'], row['road']], ensure_ascii=False, separators=(',', ':'))
    return 'tw-road:odrp049:' + sha256(identity.encode('utf-8'))[:24]


def normalize(rows, context):
    exact, folded, english, prefixes = context
    output = []
    for number, source in enumerate(rows, 1):
        candidates = exact.get(source['site_id'], set())
        status = 'unique_exact_label'
        if not candidates:
            candidates = folded.get(fold_whitespace(source['site_id']), set())
            status = 'unique_whitespace_fold_label'
        entity = next(iter(candidates)) if len(candidates) == 1 else ''
        if not entity:
            status = 'ambiguous_label' if candidates else 'unmatched_label'
        en_values = english.get(entity, set())
        en = next(iter(en_values)) if len(en_values) == 1 else ''
        codes = sorted(prefixes.get(entity, set()))
        output.append({
            'record_id': record_id(source), 'country': 'TW', 'source_ref': SOURCE_REF,
            'source_row': str(number), 'source_year': '115', **source,
            'road_en': '', 'road_en_status': 'not_provided',
            'postal_area_id': entity, 'postal_area_link_status': status,
            'postal_prefixes': '|'.join(codes),
            'postal_code_scope': 'three_digit_prefix_only' if codes else 'not_provided',
            'postal_area_name_en': en,
            'postal_area_name_en_status': 'official_postal_area_label' if en else 'not_provided',
        })
    if len({row['record_id'] for row in output}) != len(output):
        raise ValueError('Duplicate normalized record IDs')
    return output


def csv_bytes(rows):
    target = io.StringIO(newline='')
    writer = csv.DictWriter(target, fieldnames=FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return target.getvalue().encode('utf-8')


def receipt(path, rows=None, columns=None, raw=False):
    data = path.read_bytes()
    value = {'bytes': len(data), 'sha256': sha256(data)}
    if rows is not None:
        value['rows'] = rows
    if columns is not None:
        value['columns'] = columns
    if raw:
        unpacked = read_bytes(path)
        value['uncompressed_bytes'] = len(unpacked)
        value['uncompressed_sha256'] = sha256(unpacked)
    return value


def statistics(rows):
    return {
        'cities': len({row['city'] for row in rows}),
        'administrative_areas': len({row['site_id'] for row in rows}),
        'city_rows': dict(sorted(collections.Counter(row['city'] for row in rows).items())),
        'postal_area_link_status': dict(sorted(collections.Counter(row['postal_area_link_status'] for row in rows).items())),
    }


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def metadata(folder, rows, has_probe):
    files = {'records.csv.gz': receipt(folder / 'records.csv.gz', len(rows), FIELDS, True), RAW_FILE: receipt(folder / RAW_FILE, len(rows), ['city', 'site_id', 'road'], True)}
    for name in POSTAL_FILES:
        relative = 'sources/postal-' + name
        files[relative] = receipt(folder / relative)
    api_count = None
    if has_probe:
        files[PROBE_FILE] = receipt(folder / PROBE_FILE, raw=True)
        api_count = int(json.loads(read_bytes(folder / PROBE_FILE))['totalDataSize'])
    coverage = {
        'schema_version': 1, 'country': 'TW', 'layer_kind': 'official_national_road_name',
        'record_file': 'records.csv.gz', 'rows': len(rows), 'files': files,
        'search_fields': SEARCH_FIELDS, 'searchable_fields': SEARCH_FIELDS,
        **statistics(rows), 'claims': CLAIMS,
        'scope': 'Source-listed road names and postal-area label candidates only; no house-number, six-digit postcode, delivery or legal administrative-boundary inference.',
    }
    links = {'registries/official/TW/' + name: receipt(folder / ('sources/postal-' + name)) for name in POSTAL_FILES}
    sources = {
        'schema_version': 1, 'country': 'TW', 'observed_on': '2026-11-04', 'retrieved_at': '2026-11-04',
        'sources': {
            SOURCE_REF: {
                'provider': 'Ministry of the Interior, Department of Household Registration (Taiwan)',
                'title': '全國路名資料', 'url': SOURCE_URL, 'catalogue': 'https://data.gov.tw/dataset/35321',
                'source_year': '115 (2026)', 'catalogue_updated_at': '2026-08-20 10:01',
                'source_effective_date': None, 'retrieved_at': '2026-11-04',
                'licence': 'Open Government Data License, version 1.0 (Taiwan)',
                'terms': 'https://data.gov.tw/license',
                'canonical_source': RAW_FILE,
                'note': 'Canonical download CSV; original city/site_id/road strings retained, including source whitespace. Listing is not evidence of address or delivery validity.',
            },
            'tw-moi-odrp049-115-api-probe': {
                'provider': 'Ministry of the Interior (Taiwan)', 'url': API_URL,
                'retrieved_at': '2026-11-04', 'role': 'audit_only_first_page',
                'licence': 'Open Government Data License, version 1.0 (Taiwan)', 'terms': 'https://data.gov.tw/license',
                'note': 'First-page API observation only, not merged into canonical CSV and not an atomic national API snapshot.',
            },
            'tw-chunghwa-postal-context': {
                'provider': 'Chunghwa Post', 'catalogue': 'https://data.gov.tw/dataset/5949',
                'url': 'https://www.post.gov.tw/post/download/County_h_10906.xml',
                'licence': 'Open Government Data License, version 1.0 (Taiwan)', 'terms': 'https://data.gov.tw/license',
                'note': 'Existing official/TW registry snapshots; English applies to postal-area labels only, three digits are prefixes only.',
            },
        },
        'bundled_files': {name: {key: value for key, value in details.items() if key in ('bytes', 'sha256', 'uncompressed_bytes', 'uncompressed_sha256')} for name, details in files.items() if name != 'records.csv.gz'},
        'linkage_sources': links,
        'api_count_discrepancy': {'canonical_csv_rows': len(rows), 'api_advertised_total': api_count, 'difference_csv_minus_api': len(rows) - api_count if api_count is not None else None, 'selection': 'Explicit canonical CSV selection; no automatic count-based source selection or union.'},
    }
    return coverage, sources


def build(source, output, postal_root=POSTAL_ROOT, api_probe=None):
    output = Path(output)
    if output.exists():
        raise ValueError('Output must be a new directory')
    raw = read_bytes(source)
    rows = normalize(parse_source(raw), postal_context(Path(postal_root)))
    output.mkdir(parents=True)
    (output / 'sources').mkdir()
    (output / RAW_FILE).write_bytes(gzip.compress(raw, mtime=0))
    (output / 'records.csv.gz').write_bytes(gzip.compress(csv_bytes(rows), mtime=0))
    for name in POSTAL_FILES:
        shutil.copyfile(Path(postal_root) / name, output / ('sources/postal-' + name))
    if api_probe is not None:
        probe = read_bytes(api_probe)
        json.loads(probe)
        (output / PROBE_FILE).write_bytes(gzip.compress(probe, mtime=0))
    coverage, sources = metadata(output, rows, api_probe is not None)
    write_json(output / 'coverage.json', coverage)
    write_json(output / 'sources.json', sources)
    return verify(output)


def verify(folder=DEFAULT):
    folder = Path(folder)
    coverage = json.loads((folder / 'coverage.json').read_text('utf-8'))
    sources = json.loads((folder / 'sources.json').read_text('utf-8'))
    if coverage['country'] != 'TW' or coverage['record_file'] != 'records.csv.gz':
        raise ValueError('Incorrect country or normalized record file')
    if coverage.get('claims') != CLAIMS:
        raise ValueError('Unsupported coverage claims')
    for name, details in coverage['files'].items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Unsafe bundled path')
        actual = receipt(folder / name, raw='uncompressed_sha256' in details)
        for key in ['bytes', 'sha256', 'uncompressed_bytes', 'uncompressed_sha256']:
            if key in details and actual[key] != details[key]:
                raise ValueError(f'File receipt mismatch: {name}:{key}')
    expected = normalize(parse_source(read_bytes(folder / RAW_FILE)), postal_context(folder, snapshot=True))
    actual = load_csv(read_bytes(folder / 'records.csv.gz'), FIELDS)
    if actual != expected or read_bytes(folder / 'records.csv.gz') != csv_bytes(expected):
        raise ValueError('Normalized rows differ from complete raw-source replay')
    if coverage['rows'] != len(expected):
        raise ValueError('Coverage count mismatch')
    for key, value in statistics(expected).items():
        if coverage.get(key) != value:
            raise ValueError(f'Coverage category mismatch: {key}')
    if coverage.get('search_fields') != SEARCH_FIELDS or coverage.get('searchable_fields') != SEARCH_FIELDS:
        raise ValueError('Unsupported search fields')
    for name, details in sources['bundled_files'].items():
        if any(coverage['files'][name].get(key) != value for key, value in details.items()):
            raise ValueError('Source receipt differs from coverage')
    for name in POSTAL_FILES:
        origin = 'registries/official/TW/' + name
        if sources['linkage_sources'][origin] != receipt(folder / ('sources/postal-' + name)):
            raise ValueError('Postal context source receipt mismatch')
    if (folder / PROBE_FILE).exists():
        count = int(json.loads(read_bytes(folder / PROBE_FILE))['totalDataSize'])
        discrepancy = sources['api_count_discrepancy']
        if discrepancy['canonical_csv_rows'] != len(expected) or discrepancy['api_advertised_total'] != count or discrepancy['difference_csv_minus_api'] != len(expected) - count:
            raise ValueError('API/CSV discrepancy receipt mismatch')
    return {'country': 'TW', 'status': 'passed', 'rows': len(expected), 'source_integrity': 'passed', 'row_integrity': 'passed_all_canonical_csv_rows', 'scope': coverage['scope']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    importer = sub.add_parser('build')
    importer.add_argument('--source', required=True, type=Path)
    importer.add_argument('--output', required=True, type=Path)
    importer.add_argument('--postal-root', type=Path, default=POSTAL_ROOT)
    importer.add_argument('--api-probe', type=Path)
    checker = sub.add_parser('verify')
    checker.add_argument('folder', nargs='?', type=Path, default=DEFAULT)
    args = parser.parse_args()
    report = build(args.source, args.output, args.postal_root, args.api_probe) if args.command == 'build' else verify(args.folder)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
