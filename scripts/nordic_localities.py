#!/usr/bin/env python3
"""Source-qualified Nordic place/address foundation; no national deliverability claims.

Works from existing immutable GeoNames/Eurostat country bundles, and accepts strictly
pinned, rights-reviewed official exports. No network calls or implicit source joins.
Python 3.11+, standard library only.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse
import zipfile

REPO = Path(__file__).resolve().parents[1]
CATALOG = 'registries/nordics/catalog.json'
EUROPE_CODES = ('AX', 'DK', 'FI', 'FO', 'IS', 'NO', 'SE', 'SJ')
ALL_CODES = ('DK', 'FI', 'IS', 'NO', 'SE', 'AX', 'FO', 'GL', 'SJ')
TYPES = ('locality', 'admin_subdivision', 'other_admin_feature', 'seed_municipality')
KINDS = ('address', 'street', 'locality', 'administrative', 'postal_area')
FORMATS = ('csv', 'csv_gz', 'zip_csv', 'jsonl', 'geojson')
EXPOSED_FIELDS = ('name', 'street', 'number', 'suffix', 'postcode', 'municipality_code',
                  'parent_id', 'status', 'latitude', 'longitude', 'language')
PATTERNS = {
    'DK': r'[0-9]{4}', 'FI': r'[0-9]{5}', 'IS': r'[0-9]{3}',
    'NO': r'[0-9]{4}', 'SE': r'[0-9]{3} ?[0-9]{2}',
    'AX': r'(?:AX-)?[0-9]{5}', 'FO': r'(?:FO-)?[0-9]{3}',
    'GL': r'[0-9]{4}', 'SJ': r'[0-9]{4}',
}


def load_catalog(root=REPO):
    path = Path(root) / CATALOG
    doc = json.loads(path.read_text(encoding='utf-8'))
    if doc.get('schema_version') != 1 or tuple(doc.get('country_codes', [])) != ALL_CODES:
        raise ValueError('Unexpected Nordic country scope')
    if set(doc['territories']) != {'AX', 'FO', 'GL', 'SJ'}:
        raise ValueError('Unexpected Nordic territories')
    if set(doc['countries']) != set(ALL_CODES):
        raise ValueError('Missing Nordic country records')
    for code, item in doc['countries'].items():
        if (item['code'] != code or item['national_address_completeness_verified'] is not False
                or item['deliverability_verified'] is not False
                or item['source_access'] not in ('public', 'registration', 'legal_review', 'mixed', 'limited')
                or not item['official_sources']):
            raise ValueError('Invalid source scope/claim for ' + code)
        for source in item['official_sources']:
            url = urlparse(source['url'])
            if url.scheme != 'https' or not url.hostname or not source['authority']:
                raise ValueError('Invalid official source URL for ' + code)
    return doc


def safe_path(root, rel):
    relative = Path(rel)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts or relative == Path('.'):
        raise ValueError('Unsafe relative path')
    base = Path(root).resolve()
    value = (base / relative).resolve()
    if not value.is_relative_to(base) or not value.is_file():
        raise ValueError('Source file missing or unsafe')
    return value


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def european_country_path(root, country):
    if country not in EUROPE_CODES:
        raise ValueError('GeoNames European country bundle unavailable for ' + country)
    return Path(root) / 'registries/europe/countries' / country


def inspect_country(root, code):
    if code not in ALL_CODES:
        raise ValueError('Country not in Nordic scope')
    if code == 'GL':
        seeds = json.loads(safe_path(root, 'registries/north-america/admin-seeds.json').read_text(encoding='utf-8'))
        rows = [r for r in seeds['records'] if r['country'] == 'GL']
        return {'country': 'GL', 'source': 'curated_government_name_seeds', 'observations': len(rows),
                'official_municipality_codes_verified': False, 'national_address_completeness_verified': False,
                'deliverability_verified': False}
    folder = european_country_path(root, code)
    m = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
    counts = m['counts']
    actual = sum(file['rows'] for file in m['files'].values())
    return {'country': code, 'source': 'GeoNames', 'observations': actual,
            'administrative_rows': counts['admin_rows'], 'locality_rows': counts['locality_rows'],
            'other_admin_rows': counts['other_admin_rows'], 'unresolved_parents': counts['unresolved_parents'],
            'official_hierarchy_verified': m['current_official_hierarchy_verified'],
            'official_postal_relation': m['postal_relation_status'],
            'national_address_completeness_verified': False, 'deliverability_verified': False}


def raw_rows(root, country, validate=False):
    """Yield GeoNames rows. admin1.csv is a duplicate view, never appended."""
    folder = european_country_path(root, country)
    meta = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
    count = 0
    ids = set() if validate else None
    for filename, info in sorted(meta['files'].items()):
        if not re.fullmatch(r'entities-[0-9]{4}\.csv\.gz', filename):
            raise ValueError('Unexpected non-entity source')
        path = safe_path(folder, filename)
        if validate and (path.stat().st_size != info['bytes'] or digest(path) != info['sha256']):
            raise ValueError('GeoNames source pin differs: ' + filename)
        local_h = hashlib.sha256()
        observed = 0
        with gzip.open(path, 'rb') as stream:
            class HashingReader(io.RawIOBase):
                def readable(self): return True
                def readinto(self, b):
                    data = stream.read(len(b))
                    b[:len(data)] = data
                    local_h.update(data)
                    return len(data)
            with io.TextIOWrapper(io.BufferedReader(HashingReader()), encoding='utf-8', newline='') as text:
                reader = csv.DictReader(text)
                if not reader.fieldnames or not {'id', 'name', 'country_code', 'kind', 'parent_id'} <= set(reader.fieldnames):
                    raise ValueError('Unexpected GeoNames schema')
                for row in reader:
                    if None in row or row.get('country_code') != country:
                        raise ValueError('Broken or cross-country GeoNames row')
                    if validate:
                        if not row['id'].startswith('gn:') or row['id'] in ids:
                            raise ValueError('Duplicate or invalid GeoNames identity')
                        ids.add(row['id'])
                    observed += 1
                    count += 1
                    yield row
        if validate and (observed != info['rows'] or local_h.hexdigest() != info['uncompressed_sha256']):
            raise ValueError('GeoNames decompressed source differs: ' + filename)
    counts = meta['counts']
    if validate and (count != sum(info['rows'] for info in meta['files'].values())
                     or count != counts['admin_rows'] + counts['locality_rows'] + counts['other_admin_rows']):
        raise ValueError('GeoNames manifest row count differs')


def verify(root, country):
    base = Path(root)
    if country == 'GL':
        result = inspect_country(root, country)
        # Curated Greenland names are evidence, not verified municipality IDs/addresses.
        result['integrity'] = 'seed_records_loaded'
        return result
    meta = inspect_country(root, country)
    length = sum(1 for _ in raw_rows(root, country, validate=True))
    meta['integrity'] = 'verified_bundled_files_and_rows'
    meta['observations'] = length
    if country in ('DK', 'FI', 'NO', 'SE'):
        lau_dir = base / 'registries/europe/eurostat-lau' / country
        if (lau_dir / 'metadata.json').is_file():
            lau = json.loads((lau_dir / 'metadata.json').read_text(encoding='utf-8'))
            for filename, fi in lau['files'].items():
                p = safe_path(lau_dir, filename)
                if p.stat().st_size != fi['bytes'] or digest(p) != fi['sha256']:
                    raise ValueError('Eurostat LAU file changed')
            meta['statistical_lau_rows'] = lau['rows']
            meta['statistical_lau_period'] = lau['source_period_counts']
            meta['statistical_lau_separate_from_legal_administration'] = True
    return meta


def records(root, code):
    if code == 'GL':
        d = json.loads(safe_path(root, 'registries/north-america/admin-seeds.json').read_text(encoding='utf-8'))
        for r in d['records']:
            if r['country'] == code:
                yield {'country': code, 'id': r['provisional_id'], 'kind': 'seed_municipality',
                       'name': r['source_name'], 'parent_id': None, 'state_id': None,
                       'feature_code': None, 'source': r['evidence_id'], 'identity_is_provisional': True,
                       'address_verified': False}
        return
    for r in raw_rows(root, code):
        yield {'country': code, 'id': r['id'], 'kind': r['kind'], 'name': r['name'],
               'asciiname': r.get('asciiname', ''), 'alternatenames': r.get('alternatenames', ''),
               'parent_id': r['parent_id'] or None, 'parent_relation': r.get('parent_relation'),
               'state_id': r.get('state_id') or None, 'feature_code': r.get('feature_code'),
               'latitude': r.get('latitude'), 'longitude': r.get('longitude'),
               'address_candidate': r.get('address_candidate') == '1',
               'source': 'GeoNames', 'address_verified': False}


def search(root, country, query, kind=None, limit=20, offset=0):
    if country not in ALL_CODES or not query or not 1 <= limit <= 200 or offset < 0:
        raise ValueError('Invalid country/search/limit')
    query = query.casefold()
    hits, total = [], 0
    for r in records(root, country):
        if kind and r['kind'] != kind:
            continue
        labels = [r['name'], r.get('asciiname', ''), *r.get('alternatenames', '').split(',')]
        if not any(query in value.casefold() for value in labels if value):
            continue
        if offset <= total < offset + limit:
            hits.append({k: v for k, v in r.items() if k not in ('alternatenames', 'asciiname')})
        total += 1
    return {'country': country, 'query': query, 'total': total, 'results': hits,
            'national_address_completeness_verified': False, 'deliverability_verified': False}


def check_postcode(code, value):
    if code not in ALL_CODES or not isinstance(value, str):
        raise ValueError('Invalid code/postcode')
    valid = re.fullmatch(PATTERNS[code], value, flags=re.IGNORECASE) is not None
    return {'country': code, 'postcode': value, 'syntax_valid': valid,
            'postcode_exists': None, 'address_exists': None, 'deliverable': None,
            'note': 'Syntax only. No postal registry or carrier validation.'}


def _write_unreplaceable(path, writer):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise FileExistsError('Never overwrite an existing output')
    with tempfile.NamedTemporaryFile(prefix='.nordics-', dir=target.parent, delete=False) as f:
        tmp = Path(f.name)
        try:
            writer(f)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    try:
        os.link(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def compile_baseline(root, out, codes=ALL_CODES):
    if not codes or any(c not in ALL_CODES for c in codes) or len(set(codes)) != len(codes):
        raise ValueError('Invalid country selection')
    counts = {}
    def write(stream):
        with gzip.GzipFile(filename='', mode='wb', fileobj=stream, mtime=0) as zipper:
            for code in codes:
                count = 0
                for row in records(root, code):
                    zipper.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8'))
                    count += 1
                counts[code] = count
    final = _write_unreplaceable(out, write)
    return {'output': str(final), 'sha256': digest(final), 'source_observations': counts,
            'note': 'Observations may overlap or be historical; not unique valid delivery addresses.',
            'national_address_completeness_verified': False, 'deliverability_verified': False}


def verify_official_pin(pin, data_root, catalog=None):
    catalog = catalog or load_catalog()
    code = pin.get('country')
    if code not in ALL_CODES:
        raise ValueError('Unknown country')
    if pin.get('schema_version') != 1 or pin.get('format') not in FORMATS:
        raise ValueError('Unsupported format')
    if pin.get('kind') not in KINDS:
        raise ValueError('Source type must be explicit')
    for flag in ('national_address_completeness_verified', 'deliverability_verified'):
        if pin.get(flag) is not False:
            raise ValueError('Do not assert unsupported address quality')
    if pin.get('rights_reviewed') is not True:
        raise ValueError('Explicit commercial reuse/redistribution review required')
    if catalog['countries'][code]['source_access'] in ('registration', 'legal_review', 'mixed') and pin.get('access_authorized') is not True:
        raise ValueError('Access authorization required for controlled source')
    source = urlparse(pin.get('source_url', ''))
    hosts = {urlparse(x['url']).hostname for x in catalog['countries'][code]['official_sources']}
    if source.scheme != 'https' or source.hostname not in hosts:
        raise ValueError('Unregistered official source host')
    if not pin.get('source_id') or not pin.get('license') or not pin.get('retrieved_at'):
        raise ValueError('Missing source provenance/license')
    try:
        datetime.fromisoformat(pin['retrieved_at'].replace('Z', '+00:00'))
    except (TypeError, ValueError) as e:
        raise ValueError('Invalid acquisition time') from e
    fields = pin.get('fields')
    if not isinstance(fields, dict) or 'id' not in fields or not set(fields) <= set(EXPOSED_FIELDS) | {'id'}:
        raise ValueError('Field mapping missing or contains unexpected target')
    if len(set(fields.values())) != len(fields) or any(not isinstance(v, str) or not v for v in fields.values()):
        raise ValueError('Duplicate or invalid source columns')
    if pin.get('coordinate_crs') is None:
        raise ValueError('Coordinate reference system must be explicit')
    if pin.get('format') == 'zip_csv' and not pin.get('member'):
        raise ValueError('Explicit member required')
    p = safe_path(data_root, pin['path'])
    if (type(pin.get('bytes')) is not int or pin['bytes'] <= 0 or p.stat().st_size != pin['bytes']
            or not re.fullmatch('[0-9a-f]{64}', pin.get('sha256', '')) or digest(p) != pin['sha256']):
        raise ValueError('Source size/hash differs')
    return p


def _tabular(stream, pin):
    delimiter = pin.get('delimiter', ',')
    encoding = pin.get('encoding', 'utf-8-sig')
    if delimiter not in (',', ';', '\t') or encoding not in ('utf-8-sig', 'utf-8', 'cp1250'):
        raise ValueError('Undeclared/unsupported CSV encoding or separator')
    with io.TextIOWrapper(stream, encoding=encoding, newline='') as text:
        reader = csv.DictReader(text, delimiter=delimiter)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('CSV headers missing or duplicate')
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('Malformed CSV row')
            yield row


def _source_records(path, pin):
    fmt = pin['format']
    if fmt == 'csv':
        with path.open('rb') as stream:
            yield from _tabular(stream, pin)
    elif fmt == 'csv_gz':
        with gzip.open(path, 'rb') as stream:
            yield from _tabular(stream, pin)
    elif fmt == 'zip_csv':
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if (len(names) != len(set(names)) or pin['member'] not in names
                    or any(n.startswith('/') or '..' in Path(n).parts or '\\' in n for n in names)):
                raise ValueError('Unsafe/changed ZIP members')
            with archive.open(pin['member']) as stream:
                yield from _tabular(stream, pin)
            if archive.testzip() is not None:
                raise ValueError('ZIP CRC failure')
    elif fmt == 'jsonl':
        with path.open('r', encoding='utf-8') as stream:
            for raw in stream:
                row = json.loads(raw)
                if not isinstance(row, dict):
                    raise ValueError('JSONL record must be an object')
                yield row
    else:
        with path.open('r', encoding='utf-8') as f:
            value = json.load(f)
        if not isinstance(value, dict) or value.get('type') != 'FeatureCollection':
            raise ValueError('GeoJSON FeatureCollection required')
        for feature in value.get('features', []):
            if feature.get('type') != 'Feature' or not isinstance(feature.get('properties'), dict):
                raise ValueError('Invalid GeoJSON feature')
            yield feature['properties']


def ingest_official(pin, source_root, output, catalog=None):
    cat = catalog or load_catalog()
    path = verify_official_pin(pin, source_root, cat)
    count, identities = 0, set()
    field_map = pin['fields']
    code = pin['country']
    def write(stream):
        nonlocal count
        for row in _source_records(path, pin):
            if any(key not in row for key in field_map.values()):
                raise ValueError('Actual source headers do not match approved mapping')
            data = {field: str(row[source]) if row[source] is not None else ''
                    for field, source in field_map.items()}
            identity = data.pop('id').strip()
            if not identity or identity in identities:
                raise ValueError('Missing/duplicate source identity')
            identities.add(identity)
            if (pin['kind'] == 'address' and not any(data.get(x) for x in ('name', 'street'))
                    and not data.get('number')):
                raise ValueError('Address record missing its identifying fields')
            if data.get('postcode'):
                data['postcode_syntax_valid'] = check_postcode(code, data['postcode'])['syntax_valid']
            result = {'country': code, 'kind': pin['kind'], 'source_id': identity,
                      'source_qualified_id': pin['source_id'] + ':' + identity,
                      'source_sha256': pin['sha256'], 'source_retrieved_at': pin['retrieved_at'],
                      'coordinate_crs': pin['coordinate_crs'], 'fields': data,
                      'official_source_observation': True, 'address_exists': None,
                      'deliverability_verified': False}
            stream.write((json.dumps(result, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8'))
            count += 1
    final = _write_unreplaceable(output, write)
    return {'country': code, 'kind': pin['kind'], 'records': count, 'output': str(final),
            'sha256': digest(final), 'official_snapshot_integrity': 'pinned',
            'national_address_completeness_verified': False, 'deliverability_verified': False}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=REPO)
    sub = p.add_subparsers(dest='cmd', required=True)
    inv = sub.add_parser('inventory')
    inv.add_argument('--country', choices=['all', *ALL_CODES], default='all')
    chk = sub.add_parser('verify')
    chk.add_argument('--country', choices=['all', *ALL_CODES], default='all')
    sr = sub.add_parser('search')
    sr.add_argument('--country', choices=ALL_CODES, required=True)
    sr.add_argument('--text', required=True)
    sr.add_argument('--kind', choices=TYPES)
    sr.add_argument('--limit', type=int, default=20)
    sr.add_argument('--offset', type=int, default=0)
    post = sub.add_parser('postcode')
    post.add_argument('--country', choices=ALL_CODES, required=True)
    post.add_argument('--value', required=True)
    comp = sub.add_parser('compile')
    comp.add_argument('--country', choices=['all', *ALL_CODES], default='all')
    comp.add_argument('--output', type=Path, required=True)
    imp = sub.add_parser('ingest')
    imp.add_argument('--pin', type=Path, required=True)
    imp.add_argument('--source-root', type=Path, required=True)
    imp.add_argument('--output', type=Path, required=True)
    args = p.parse_args(argv)
    cat = load_catalog(args.root)
    codes = ALL_CODES if getattr(args, 'country', 'all') == 'all' else (args.country,)
    if args.cmd == 'inventory':
        result = {'countries': [inspect_country(args.root, code) for code in codes],
                  'country_count': len(codes), 'national_address_completeness_verified': False}
    elif args.cmd == 'verify':
        result = {'countries': [verify(args.root, code) for code in codes],
                  'country_count': len(codes), 'national_address_completeness_verified': False}
    elif args.cmd == 'search':
        result = search(args.root, args.country, args.text, args.kind, args.limit, args.offset)
    elif args.cmd == 'postcode':
        result = check_postcode(args.country, args.value)
    elif args.cmd == 'compile':
        result = compile_baseline(args.root, args.output, codes)
    else:
        pin = json.loads(args.pin.read_text(encoding='utf-8'))
        result = ingest_official(pin, args.source_root, args.output, cat)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return result


if __name__ == '__main__':
    main()
