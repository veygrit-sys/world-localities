"""Offline, source-qualified Sweden municipality and locality query/audit tools.

This module does NOT verify individual address existence, postcodes or delivery.
It keeps SCB (2026), Eurostat (2024-period LAU), and GeoNames source IDs
separate. Optionally imports independently approved, hash-pinned SCB WFS files.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import tempfile
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
SCB = ROOT / 'registries/official/SE/scb-municipalities-2026.csv'
PROVENANCE = ROOT / 'registries/official/SE/source-manifest.json'
GEO = ROOT / 'registries/europe/countries/SE'
LAU = ROOT / 'registries/europe/eurostat-lau/SE'
COUNTY_CODES = ('01', '03', '04', '05', '06', '07', '08', '09', '10', '12', '13',
                '14', '17', '18', '19', '20', '21', '22', '23', '24', '25')
SCB_HEADER = ['county_code', 'county_name', 'municipality_code', 'municipality_name']
GEO_TYPES = {'admin_subdivision', 'locality', 'other_admin_feature'}
MAX_IMPORT_BYTES = 500_000_000


def json_text(v):
    return json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def hash_file(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def name_key(name):
    """Case-insensitive NFC matching, without transliteration or name inference."""
    return unicodedata.normalize('NFC', name.strip()).casefold()


def load_counties(path=SCB, provenance=PROVENANCE):
    manifest = json.loads(Path(provenance).read_text(encoding='utf-8'))
    if manifest.get('schema_version') != 1 or manifest.get('country') != 'SE':
        raise ValueError('Invalid Swedish source metadata')
    if manifest.get('address_existence_verified') is not False or manifest.get('deliverability_verified') is not False:
        raise ValueError('No address or delivery assertions allowed')
    expected = manifest['scb_2026']['sha256']
    if hash_file(path) != expected or Path(path).stat().st_size != manifest['scb_2026']['bytes']:
        raise ValueError('SCB transcription changed: review against official publication')
    counties, municipalities = {}, {}
    with Path(path).open(encoding='utf-8', newline='') as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != SCB_HEADER:
            raise ValueError('SCB CSV headers changed')
        for row in reader:
            if None in row or any(x is None for x in row.values()):
                raise ValueError('Malformed SCB municipality row')
            cc, county, mc, name = (row[field] for field in SCB_HEADER)
            if not re.fullmatch('[0-9]{2}', cc) or cc not in COUNTY_CODES or not re.fullmatch('[0-9]{4}', mc):
                raise ValueError('Invalid Swedish municipality/county code')
            if mc[:2] != cc or not county.strip() or not name.strip():
                raise ValueError('Missing or inconsistent Swedish municipality data')
            if cc in counties and counties[cc] != county:
                raise ValueError('Conflicting Swedish county names')
            if mc in municipalities:
                raise ValueError('Duplicate Swedish municipality code')
            if any(v != v.strip() or '\x00' in v for v in (county, name)):
                raise ValueError('Unnormalized official name')
            counties[cc] = county
            municipalities[mc] = (name, cc)
    if set(counties) != set(COUNTY_CODES) or len(municipalities) != 290:
        raise ValueError('Expected 21 counties and 290 municipalities (2026)')
    return counties, municipalities


def verify_geonames(root=GEO):
    """Verify complete existing source-derived GeoNames parts, not physical addresses."""
    meta = json.loads((Path(root) / 'metadata.json').read_text(encoding='utf-8'))
    if meta['country']['country'] != 'SE' or meta.get('source') != 'GeoNames':
        raise ValueError('Unexpected GeoNames country/source')
    seen, counts = set(), {'rows': 0, 'locality_rows': 0, 'address_candidates': 0}
    for filename, spec in sorted(meta['files'].items()):
        if not re.fullmatch(r'entities-[0-9]{4}\.csv\.gz', filename):
            raise ValueError('Unexpected GeoNames part')
        path = Path(root) / filename
        if hash_file(path) != spec['sha256'] or path.stat().st_size != spec['bytes']:
            raise ValueError('GeoNames part checksum differs: ' + filename)
        with gzip.open(path, 'rt', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if None in row or not row.get('id', '').startswith('gn:') or row.get('country_code') != 'SE':
                    raise ValueError('Malformed Swedish GeoNames observation')
                if row['id'] in seen or row.get('kind') not in GEO_TYPES:
                    raise ValueError('GeoNames collision or unexpected kind')
                seen.add(row['id'])
                counts['rows'] += 1
                counts['locality_rows'] += row['kind'] == 'locality'
                counts['address_candidates'] += row.get('address_candidate') == '1'
    if counts['rows'] != sum(part['rows'] for part in meta['files'].values()):
        raise ValueError('GeoNames source counts differ')
    if counts['locality_rows'] != meta['counts']['locality_rows']:
        raise ValueError('GeoNames locality count differs')
    return counts


def iter_geonames(root=GEO):
    meta = json.loads((Path(root) / 'metadata.json').read_text(encoding='utf-8'))
    for filename in sorted(meta['files']):
        with gzip.open(Path(root) / filename, 'rt', newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                yield {'id': row['id'], 'country': 'SE', 'kind': row['kind'],
                       'name': row['name'], 'source': 'GeoNames', 'name_language': 'und',
                       'feature_code': row['feature_code'],
                       'parent_id': row.get('parent_id', ''),
                       'parent_relation': row.get('parent_relation', ''),
                       'latitude': row.get('latitude', ''), 'longitude': row.get('longitude', ''),
                       'is_address_candidate': row.get('address_candidate') == '1',
                       'is_current_address_verified': False,
                       'delivery_verified': False}


def iter_scb(counties, municipalities):
    for code, name in sorted(counties.items()):
        yield {'id': 'scb:county:2026:' + code, 'country': 'SE', 'kind': 'county',
               'name': name, 'source': 'SCB', 'source_period': '2026',
               'name_language': 'sv', 'parent_id': 'country:SE',
               'is_current_address_verified': False, 'delivery_verified': False}
    for code, (name, county) in sorted(municipalities.items()):
        yield {'id': 'scb:municipality:2026:' + code, 'country': 'SE', 'kind': 'municipality',
               'name': name, 'source': 'SCB', 'source_period': '2026',
               'name_language': 'sv', 'parent_id': 'scb:county:2026:' + county,
               'is_current_address_verified': False, 'delivery_verified': False}


def validate_postcode(value):
    """Swedish five-digit lexical pattern, never a live postcode lookup."""
    match = re.fullmatch(r'([1-9][0-9]{2}) ?([0-9]{2})', value)
    return {'country': 'SE', 'input': value, 'syntax_valid': bool(match),
            'normalized': ''.join(match.groups()) if match else None,
            'postcode_exists': None, 'postort_verified': False,
            'address_exists': None, 'deliverable': None}


def verify_lau(root=LAU, municipalities=None):
    path = Path(root) / 'units.csv.gz'
    spec = json.loads((Path(root) / 'metadata.json').read_text())
    pin = spec['files']['units.csv.gz']
    if hash_file(path) != pin['sha256'] or path.stat().st_size != pin['bytes']:
        raise ValueError('Eurostat LAU source checksum differs')
    codes, names = set(), {}
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        if 'lau_code' not in (reader.fieldnames or []) or 'name_national' not in reader.fieldnames:
            raise ValueError('Unexpected Eurostat LAU schema')
        for row in reader:
            code = row['lau_code']
            if not re.fullmatch(r'[0-9]{4}', code) or code in codes or row.get('country') != 'SE':
                raise ValueError('Invalid, duplicate or foreign LAU code')
            codes.add(code)
            names[code] = row['name_national']
    if len(codes) != pin['rows']:
        raise ValueError('Eurostat LAU count mismatch')
    result = {'source': 'Eurostat LAU 2025 label, source period 2024', 'rows': len(codes)}
    if municipalities is not None:
        result['scb_only_codes'] = sorted(set(municipalities) - codes)
        result['eurostat_only_codes'] = sorted(codes - set(municipalities))
        result['name_differences'] = [{'code': code, 'scb': municipalities[code][0], 'lau': names[code]}
                                      for code in sorted(codes & set(municipalities))
                                      if name_key(names[code]) != name_key(municipalities[code][0])]
    return result


def report(geo_root=GEO, lau_root=LAU, scb=SCB, provenance=PROVENANCE):
    counties, municipalities = load_counties(scb, provenance)
    geo_counts = verify_geonames(geo_root)
    lau = verify_lau(lau_root, municipalities)
    return {'country': 'SE', 'source_layers': {'SCB_2026': {'counties': len(counties), 'municipalities': len(municipalities)},
            'GeoNames_2026': geo_counts, 'Eurostat_LAU_2024': lau},
            'municipality_codes_match_lau': not lau['scb_only_codes'] and not lau['eurostat_only_codes'],
            'national_address_coverage_verified': False,
            'postcode_existence_verified': False, 'deliverability_verified': False,
            'not_a_delivery_address_register': True}


def lookup(query, kind=None, limit=20, geo_root=GEO, scb=SCB, provenance=PROVENANCE):
    if not query or len(query) > 256 or kind not in (None, 'county', 'municipality', 'locality', 'admin_subdivision'):
        raise ValueError('Invalid locality lookup query/type')
    if not 1 <= limit <= 200:
        raise ValueError('Lookup limit must be between 1 and 200')
    counties, municipalities = load_counties(scb, provenance)
    term = name_key(query)
    options = iter_scb(counties, municipalities)
    if kind is not None:
        options = (row for row in options if row['kind'] == kind)
    matches = [v for v in options if term in name_key(v['name']) or term in v['id'].casefold()]
    if kind in (None, 'locality', 'admin_subdivision'):
        for row in iter_geonames(geo_root):
            if row['kind'] not in (('locality', 'admin_subdivision') if kind is None else (kind,)):
                continue
            if term in name_key(row['name']) or term in row['id'].casefold():
                matches.append(row)
    matches.sort(key=lambda r: (name_key(r['name']) != term, r['kind'] != 'municipality',
                                name_key(r['name']), r['id']))
    return {'country': 'SE', 'query': query, 'matches': matches[:limit], 'has_more': len(matches) > limit,
            'is_address_verification': False}


def _safe_pin(pin, root):
    if pin.get('country') != 'SE' or pin.get('dataset') not in ('tatorter_2023', 'smaorter_2023'):
        raise ValueError('Unsupported official Swedish localities dataset')
    if pin.get('source_url', '').split('?', 1)[0] != 'https://geodata.scb.se/geoserver/stat/wfs':
        raise ValueError('Only official SCB WFS data are permitted')
    if pin.get('license') != 'CC0-1.0' or pin.get('rights_reviewed') is not True:
        raise ValueError('Use rights must be checked for this source')
    if pin.get('crs') not in ('EPSG:3006', 'EPSG:4258', 'EPSG:4326', 'unknown'):
        raise ValueError('Source CRS must be declared')
    if pin.get('format') not in ('geojson', 'gpkg'):
        raise ValueError('Unsupported source file format')
    fields = pin.get('fields')
    if not isinstance(fields, dict) or set(fields) != {'id', 'name', 'county', 'municipality'} or not all(
            isinstance(k, str) and re.fullmatch(r'[a-zA-Z0-9_]+', v or '') for k, v in fields.items()):
        raise ValueError('Explicit SCB source field mapping required')
    rel = Path(pin.get('path', ''))
    if rel.is_absolute() or '..' in rel.parts or rel == Path('.'):
        raise ValueError('Unsafe source path')
    root = Path(root).resolve()
    source = (root / rel).resolve()
    if not source.is_relative_to(root) or not source.is_file():
        raise ValueError('Source path escapes data root or does not exist')
    if (type(pin.get('bytes')) is not int or not 1 <= pin['bytes'] <= MAX_IMPORT_BYTES
            or source.stat().st_size != pin['bytes'] or not re.fullmatch('[a-f0-9]{64}', pin.get('sha256', ''))
            or hash_file(source) != pin['sha256']):
        raise ValueError('Original SCB bytes differ from accepted pin')
    return source


def _source_rows(pin, path):
    if pin['format'] == 'geojson':
        with path.open(encoding='utf-8') as f:
            data = json.load(f)
        if data.get('type') != 'FeatureCollection' or not isinstance(data.get('features'), list):
            raise ValueError('Expected GeoJSON FeatureCollection')
        for feature in data['features']:
            if feature.get('type') != 'Feature' or not isinstance(feature.get('properties'), dict):
                raise ValueError('Malformed SCB GeoJSON feature')
            yield feature['properties']
    else:
        table = pin.get('table', '')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', table):
            raise ValueError('Missing/unsafe GeoPackage table')
        # SQLite read-only, query-only; never write to the source database.
        db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
        try:
            db.execute('PRAGMA query_only=ON')
            tables = {r[0] for r in db.execute('SELECT name FROM sqlite_master WHERE type = ?', ('table',))}
            if table not in tables:
                raise ValueError('SCB GeoPackage table missing')
            cols = [v[1] for v in db.execute('PRAGMA table_info("' + table + '")')]
            wanted = list(pin['fields'].values())
            if not set(wanted) <= set(cols):
                raise ValueError('SCB columns missing or renamed')
            sql = 'SELECT ' + ','.join('"' + v + '"' for v in wanted) + ' FROM "' + table + '"'
            for record in db.execute(sql):
                yield dict(zip(wanted, record))
        finally:
            db.close()


def import_official(pin, data_root, output, scb=SCB, provenance=PROVENANCE):
    """Import a *locally available* pinned SCB WFS snapshot; never fetch unknown bytes."""
    path = _safe_pin(pin, data_root)
    counties, municipalities = load_counties(scb, provenance)
    expected = 2017 if pin['dataset'] == 'tatorter_2023' else 3097
    seen = set()
    rows = []
    fields = pin['fields']
    for props in _source_rows(pin, path):
        vals = {label: props.get(key) for label, key in fields.items()}
        uid = str(vals['id']).strip() if vals['id'] is not None else ''
        name = str(vals['name']).strip() if vals['name'] is not None else ''
        if not uid or not name or uid in seen or len(uid) > 128 or len(name) > 512:
            raise ValueError('Missing/duplicate SCB place code or name')
        seen.add(uid)
        county = str(vals['county']).strip() if vals['county'] is not None else ''
        municipality = str(vals['municipality']).strip() if vals['municipality'] is not None else ''
        # A SCB geographic locality may cover several municipalities; no guessed parent.
        direct_parent = 'scb:municipality:2026:' + municipality if municipality in municipalities else None
        if direct_parent and county and county != municipalities[municipality][1]:
            raise ValueError('SCB geographic place contradicts official county')
        if county and county not in counties and direct_parent:
            raise ValueError('Invalid county for an unambiguous municipality')
        rows.append({'id': 'scb:' + pin['dataset'] + ':' + uid, 'country': 'SE',
                     'kind': 'statistical_locality' if pin['dataset'] == 'tatorter_2023' else 'small_locality',
                     'name': name, 'source': 'SCB WFS', 'source_period': '2023',
                     'parent_id': direct_parent, 'original_county': county,
                     'original_municipality': municipality, 'source_crs': pin['crs'],
                     'geometry_role': 'settlement_area_not_address_entrance',
                     'is_current_address_verified': False, 'delivery_verified': False})
    if len(rows) != expected:
        raise ValueError('SCB reference count mismatch: expected ' + str(expected) + ', got ' + str(len(rows)))
    out = Path(output).resolve()
    if out.exists() or out.is_symlink():
        raise ValueError('Refusing to replace an existing output')
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', newline='', delete=False, dir=out.parent, prefix='.se-localities-') as f:
        temporary = Path(f.name)
        try:
            for row in sorted(rows, key=lambda v: v['id']):
                f.write(json_text(row) + '\n')
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        # Atomic no-clobber publication (same filesystem as the temporary file).
        out.hardlink_to(temporary)
    finally:
        temporary.unlink(missing_ok=True)
    return {'country': 'SE', 'dataset': pin['dataset'], 'rows': len(rows), 'output': str(out),
            'sha256': hash_file(out), 'source_sha256': pin['sha256'],
            'address_existence_verified': False, 'delivery_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest='command', required=True)
    command.add_parser('verify')
    look = command.add_parser('search')
    look.add_argument('query')
    look.add_argument('--kind', choices=('county', 'municipality', 'locality', 'admin_subdivision'))
    look.add_argument('--limit', type=int, default=20)
    check = command.add_parser('postcode')
    check.add_argument('value')
    imp = command.add_parser('import-scb')
    imp.add_argument('--pin', type=Path, required=True)
    imp.add_argument('--source-root', type=Path, required=True)
    imp.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'verify':
            result = report()
        elif args.command == 'search':
            result = lookup(args.query, args.kind, args.limit)
        elif args.command == 'postcode':
            result = validate_postcode(args.value)
        else:
            result = import_official(json.loads(args.pin.read_text(encoding='utf-8')),
                                     args.source_root, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, KeyError, OSError, UnicodeError, sqlite3.Error, json.JSONDecodeError) as e:
        parser.exit(2, 'SE: ' + str(e) + '\n')


if __name__ == '__main__':
    main()
