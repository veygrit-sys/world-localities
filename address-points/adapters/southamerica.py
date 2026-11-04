#!/usr/bin/env python3
"""South America reference data CLI; Python 3.10+, standard library only."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import csv
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sqlite3
import sys
import unicodedata
import zipfile

import os as _hierarchy_os
ROOT = Path(_hierarchy_os.environ.get('WORLD_LOCALITIES_ADDRESS_ROOT', str(Path(__file__).resolve().parents[1]))).resolve()
SOURCES = ROOT / 'sources/SOUTHAMERICA'
DEFAULT_DB = ROOT / 'generated/south_america.sqlite'
GN_FIELDS = ['geonameid', 'name', 'asciiname', 'alternatenames', 'latitude', 'longitude',
             'feature_class', 'feature_code', 'country_code', 'cc2', 'admin1', 'admin2',
             'admin3', 'admin4', 'population', 'elevation', 'dem', 'timezone', 'modified_date']
NAME_FIELDS = ['alternate_name_id', 'geonameid', 'language', 'name', 'preferred',
               'short', 'colloquial', 'historic', 'from', 'to']
NON_NAME_TAGS = {'post', 'iata', 'icao', 'faac', 'link', 'wkdt', 'unlc', 'tcid'}
HISTORIC_FEATURES = {'PPLH', 'PPLCH', 'PPLQ', 'PPLW'}


def read_json(path):
    data = Path(path).read_bytes()
    if data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    return json.loads(data.decode('utf-8-sig'))


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def profiles():
    return read_json(ROOT / 'SOUTH_AMERICA_RULES.json')['profiles']


def country_code(value):
    cc = value.upper()
    if cc not in profiles():
        raise ValueError(f'Unsupported South America scope: {cc}')
    return cc


def lookup_key(value):
    """Lossy retrieval key only. Never an identity, transliteration or display name."""
    if not isinstance(value, str):
        raise ValueError('Names and address components must be strings')
    value = unicodedata.normalize('NFKD', value).casefold()
    return ' '.join(''.join(c for c in value if not unicodedata.combining(c)).split())


def postcode_review(cc, value):
    cc = country_code(cc)
    rule = profiles()[cc]['postcode']
    out = {'country': cc, 'raw': value, 'assignment_verified': False, 'delivery_verified': False}
    if value is not None and not isinstance(value, str):
        return {**out, 'status': 'invalid_input_type', 'reason': 'Provide a string to retain leading zeroes.'}
    if value is None or not value.strip():
        return {**out, 'status': 'missing' if rule['pattern'] else rule['presence']}
    stripped = value.strip()
    if not stripped.isascii():
        return {**out, 'status': 'review_required'}
    candidate = stripped.upper()
    if rule['presence'] == 'not_applicable':
        return {**out, 'status': 'not_applicable_scope_review_required'}
    if not rule['pattern']:
        return {**out, 'status': 'unverified_supplied_value'}
    if re.fullmatch(rule['pattern'], candidate):
        display = candidate
        if cc == 'BR':
            digits = candidate.replace('-', '')
            display = digits[:5] + '-' + digits[5:]
        if cc in ('FK', 'GS'):
            compact = candidate.replace(' ', '')
            display = compact[:4] + ' ' + compact[4:]
        return {**out, 'status': 'matches_syntax_only', 'display_candidate': display}
    for field, status in [('legacy_pattern', 'legacy_format_review_required'),
                          ('extended_reference_pattern', 'extended_format_review_required')]:
        if rule.get(field) and re.fullmatch(rule[field], candidate):
            return {**out, 'status': status}
    return {**out, 'status': 'review_required'}


def render_address(cc, fields, international=True):
    """Render explicit components without parsing or silently translating names."""
    cc = country_code(cc)
    if not isinstance(fields, dict) or any(v is not None and not isinstance(v, str) for v in fields.values()):
        raise ValueError('Every address component must be a string or null')
    profile = profiles()[cc]
    raw = fields.copy()
    clean = {k: unicodedata.normalize('NFC', v).strip() if v else '' for k, v in fields.items()}
    if any('\n' in v or '\r' in v or '\x00' in v for v in clean.values()):
        raise ValueError('Each field must contain one line without NUL characters')
    if cc == 'BV':
        return {'country': cc, 'raw': raw, 'status': 'no_ordinary_delivery_form', 'lines': []}
    get = lambda k: clean.get(k, '')
    join = lambda *xs: ' '.join(x for x in xs if x)
    first = get('po_box') or get('address_line1')
    if get('po_box') and get('address_line1'):
        raise ValueError('Select a PO-box route or a street route; do not silently combine them')
    lines = [get('organization'), get('recipient'), first, get('address_line2'),
             get('landmark'), get('sublocality')]
    pc, loc, admin = get('postcode'), get('locality'), get('admin1')
    template = profile['render_template']
    if template == 'uruguay':
        tail = (pc + ' - ' + loc) if pc and loc else join(pc, loc)
        if admin and lookup_key(admin) != lookup_key(loc):
            tail = (tail + ', ' + admin) if tail else admin
        lines += [tail]
    elif template == 'brazil':
        lines += [(loc + ' - ' + admin) if loc and admin else join(loc, admin), pc]
    elif template == 'postcode_own_line':
        lines += [pc, loc, admin]
    elif template == 'locality_then_postcode':
        lines += [loc, admin, pc]
    elif template.startswith('locality_postcode'):
        lines += [join(loc, pc), admin]
    elif template.startswith('postcode_locality'):
        lines += [join(pc, loc), admin]
    else:
        lines += [loc, admin]
        if pc:
            lines.append(pc)
    if international:
        lines.append(get('destination_label') or profile['name_en'].upper())
    missing = [key for key, value in [('primary_address_line', first), ('locality', loc)] if not value]
    return {'country': cc, 'raw': raw, 'lines': [v for v in lines if v],
            'status': 'reference_draft', 'missing_suggested_fields': missing,
            'postcode_review': postcode_review(cc, fields.get('postcode')),
            'unit_verified': False, 'delivery_verified': False,
            'unrendered_fields': {k:v for k,v in raw.items() if k not in {
                'organization','recipient','po_box','address_line1','address_line2','landmark',
                'sublocality','postcode','locality','admin1','destination_label'}},
            'note': 'Project-authored reference format. No S42 certification, translation or automatic component extraction.'}


def zip_rows(path, cc):
    with Path(path).open('rb') as f:
        wrapped = f.read(2) == b'\x1f\x8b'
    source = io.BytesIO(gzip.decompress(Path(path).read_bytes())) if wrapped else path
    with zipfile.ZipFile(source) as z:
        name = cc + '.txt'
        if name not in z.namelist():
            raise ValueError(f'Missing {name} in {path}')
        with z.open(name) as raw:
            yield from csv.reader(io.TextIOWrapper(raw, encoding='utf-8', newline=''), delimiter='\t', quoting=csv.QUOTE_NONE)


def coordinates(lat, lon):
    if lat in (None, '') or lon in (None, ''):
        return None, None
    lat, lon = float(lat), float(lon)
    if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f'Invalid source coordinates: {lat}, {lon}')
    return lat, lon


def historical_or_time_bounded_name(raw):
    # Use the release date, not execution time, for reproducible snapshot filtering.
    if raw.get('historic') == '1' or raw.get('to'):
        return True
    start = raw.get('from')
    if not start:
        return False
    as_of = date.fromisoformat(read_json(ROOT / 'SOUTH_AMERICA_RULES.json')['release_date'])
    if not re.fullmatch(r'[0-9]{4}(?:-[0-9]{2}(?:-[0-9]{2})?)?', start):
        return True
    bits = start.split('-')
    try:
        parsed = date(int(bits[0]), int(bits[1]) if len(bits)>1 else 1, int(bits[2]) if len(bits)>2 else 1)
    except ValueError:
        return True
    return parsed > as_of


def create_schema(db):
    db.executescript('''
    PRAGMA journal_mode=OFF;
    CREATE TABLE records (rid INTEGER PRIMARY KEY, record_key TEXT UNIQUE NOT NULL,
      source TEXT NOT NULL, country TEXT NOT NULL, source_id TEXT NOT NULL,
      layer TEXT NOT NULL, name TEXT NOT NULL, latitude REAL, longitude REAL,
      precision TEXT NOT NULL, source_country TEXT, feature_code TEXT,
      admin1 TEXT, admin2 TEXT, historic INTEGER NOT NULL, source_json TEXT NOT NULL);
    CREATE TABLE names (rid INTEGER NOT NULL REFERENCES records(rid),
      text TEXT NOT NULL, lookup TEXT NOT NULL, language TEXT, kind TEXT NOT NULL,
      historic INTEGER NOT NULL, preferred INTEGER NOT NULL, source_id TEXT, source_json TEXT);
    CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE INDEX records_geo ON records(country, layer, latitude, longitude);
    CREATE INDEX records_source ON records(source, source_id);
    CREATE INDEX names_record ON names(rid);
    CREATE INDEX names_lookup ON names(lookup);
    ''')


def insert_record(db, key, source, cc, sid, layer, name, lat, lon, precision,
                  raw, source_cc=None, code=None, admin1=None, admin2=None, historic=False, language=None):
    lat, lon = coordinates(lat, lon)
    cur = db.execute('INSERT INTO records VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
      (key, source, cc, str(sid), layer, name, lat, lon, precision, source_cc, code,
       admin1, admin2, int(historic), dump(raw)))
    rid = cur.lastrowid
    db.execute('INSERT INTO names VALUES(?,?,?,?,?,?,?,?,?)',
      (rid, name, lookup_key(name), language, 'source_name', int(historic), 0, None, None))
    return rid


def verify_sources():
    manifest = read_json(ROOT / 'SOUTH_AMERICA_SOURCES.json')
    expected = set(profiles())
    sources = manifest['sources']
    if manifest.get('failures'):
        raise ValueError('Source acquisition has unresolved failures')
    for kind in ('geonames', 'names'):
        if {s['country'] for s in sources if s['kind'] == kind} != expected:
            raise ValueError(f'{kind} does not cover all 16 collection scopes')
    for s in sources:
        path = (SOURCES / s['path']).resolve()
        if not path.is_relative_to(SOURCES.resolve()):
            raise ValueError('Source path leaves package')
        if not path.is_file() or path.stat().st_size != s['bytes'] or file_hash(path) != s['sha256']:
            raise ValueError(f'Source integrity mismatch: {s["id"]}')
    return manifest


def build_database(destination=DEFAULT_DB):
    manifest = verify_sources()
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_name(destination.name + '.building')
    if tmp.exists():
        tmp.unlink()
    db = sqlite3.connect(tmp)
    create_schema(db)
    reports = []
    try:
        for s in manifest['sources']:
            if s['kind'] != 'geonames':
                continue
            cc, path, source = s['country'], SOURCES / s['path'], s['id']
            counts = Counter()
            for row in zip_rows(path, cc):
                if len(row) != 19:
                    raise ValueError(f'Unexpected GeoNames column count: {source}')
                r = dict(zip(GN_FIELDS, row))
                layer = 'place' if r['feature_class'] == 'P' else ('admin' if r['feature_class'] == 'A' else 'feature')
                historic = r['feature_code'] in HISTORIC_FEATURES
                rid = insert_record(db, source + ':' + r['geonameid'], source, cc, r['geonameid'], layer,
                    r['name'], r['latitude'], r['longitude'], 'geographic_reference_point', r,
                    r['country_code'], r['feature_code'], r['admin1'], r['admin2'], historic)
                if r['asciiname']:
                    db.execute('INSERT INTO names VALUES(?,?,?,?,?,?,?,?,?)',
                        (rid, r['asciiname'], lookup_key(r['asciiname']), None, 'source_ascii', int(historic), 0, None, None))
                counts['rows'] += 1
                counts[layer] += 1
                counts['historic_or_abandoned_features'] += int(historic)
                counts['country_code_mismatches'] += int(r['country_code'] != cc)
            reports.append({'source': source, 'kind': s['kind'], 'country': cc, **counts})
            db.commit()
        for s in manifest['sources']:
            if s['kind'] != 'names':
                continue
            cc, path = s['country'], SOURCES / s['path']
            source = cc.lower() + '-geonames-geonames'
            ids = dict(db.execute('SELECT source_id, rid FROM records WHERE source=?', (source,)))
            counts = Counter()
            examples = []
            for row in zip_rows(path, cc):
                if len(row) != 10:
                    raise ValueError(f'Unexpected alternate-name schema: {s["id"]}')
                r = dict(zip(NAME_FIELDS, row))
                counts['rows'] += 1
                rid = ids.get(r['geonameid'])
                if rid is None:
                    counts['unresolved_feature_ids'] += 1
                    if len(examples) < 8:
                        examples.append(r['geonameid'])
                    continue
                historic = historical_or_time_bounded_name(r)
                kind = 'identifier_or_link' if r['language'] in NON_NAME_TAGS else 'source_alias'
                db.execute('INSERT INTO names VALUES(?,?,?,?,?,?,?,?,?)',
                   (rid, r['name'], lookup_key(r['name']), r['language'] or None, kind,
                    int(historic), int(r['preferred'] == '1'), r['alternate_name_id'], dump(r)))
                counts['linked_rows'] += 1
                counts['historic_or_time_bounded_aliases'] += int(historic)
                counts['english_tagged_rows'] += int(r['language'] == 'en' or r['language'].startswith('en-'))
                counts['domestic_english_tagged_rows'] += int(r['language'].lower() == 'en-' + cc.lower())
            reports.append({'source': s['id'], 'kind': s['kind'], 'country': cc, **counts,
                            'unresolved_feature_id_examples': examples})
            db.commit()
        for s in manifest['sources']:
            source, cc, path = s['id'], s['country'], SOURCES / s['path']
            counts = Counter()
            if s['kind'] == 'georef':
                obj = read_json(path)
                field = 'provincias' if source.endswith('provincias') else 'localidades'
                rows = obj[field]
                if obj['total'] != len(rows) or obj['cantidad'] != len(rows) or obj['inicio'] != 0:
                    raise ValueError('Georef snapshot is paginated or incomplete')
                province_ids = {r['id'] for r in read_json(SOURCES / 'AR/provincias.json')['provincias']}
                for r in rows:
                    parent = r.get('provincia', {}).get('id')
                    if parent and parent not in province_ids:
                        raise ValueError(f'Unknown official province reference: {parent}')
                    insert_record(db, source + ':' + r['id'], source, cc, r['id'],
                      'admin' if field == 'provincias' else 'place', r['nombre'],
                      r.get('centroide', {}).get('lat'), r.get('centroide', {}).get('lon'),
                      'administrative_or_locality_centroid', r, cc,
                      r.get('categoria') or 'province', parent, r.get('departamento', {}).get('id'), language='es')
                    counts['rows'] += 1
                    counts['parent_province_ids_verified'] += int(bool(parent))
            elif s['kind'] == 'ban':
                ids = Counter()
                with gzip.open(path, 'rt', encoding='utf-8-sig', newline='') as f:
                    reader = csv.DictReader(f, delimiter=';')
                    for observation_no, r in enumerate(reader, 1):
                        if not r['code_insee'].startswith('973'):
                            raise ValueError('GF BAN source contains a different department')
                        if not re.fullmatch(r'973[0-9]{2}', r['code_postal']):
                            counts['postcode_syntax_review'] += 1
                        name = ' '.join(x for x in [r['numero'], r['rep'], r['nom_voie'], r['code_postal'], r['nom_commune']] if x)
                        # A legacy BAN ID can repeat for distinct source observations/positions.
                        # Preserve every row; keys identify observations within the pinned snapshot.
                        insert_record(db, source + ':' + r['id'] + ':row:' + str(observation_no), source, cc, r['id'], 'address', name,
                          r['lat'], r['lon'], 'ban:' + r['type_position'], r, cc, 'BAN_ADDRESS', '973', r['code_insee'], language='fr')
                        counts['rows'] += 1
                        ids[r['id']] += 1
                        counts['municipality_certified_rows'] += int(r['certification_commune'] == '1')
                        counts['position:' + r['type_position']] += 1
                counts['unique_source_ids'] = len(ids)
                counts['repeated_source_id_groups'] = sum(v>1 for v in ids.values())
                counts['additional_observations_for_repeated_ids'] = sum(v-1 for v in ids.values())
            else:
                continue
            reports.append({'source': source, 'kind': s['kind'], 'country': cc, **counts})
            db.commit()
        summary = {'status': 'PASS', 'schema_version': 1, 'built_at': datetime.now(timezone.utc).isoformat(),
          'scope_count': len(profiles()), 'sources': reports,
          'country_count': len(read_json(ROOT/'SOUTH_AMERICA_SCOPE.json')['country_codes']),
          'supplementary_area_count': len(read_json(ROOT/'SOUTH_AMERICA_SCOPE.json')['supplementary_area_codes']),
          'record_rows': db.execute('SELECT count(*) FROM records').fetchone()[0],
          'name_rows': db.execute('SELECT count(*) FROM names').fetchone()[0],
          'input_manifest_sha256': file_hash(ROOT / 'SOUTH_AMERICA_SOURCES.json'),
          'rules_sha256': file_hash(ROOT / 'SOUTH_AMERICA_RULES.json'),
          'full_national_address_coverage_claimed': False, 'delivery_verified_rows': 0, 'generated_units': 0}
        for k, v in summary.items():
            db.execute('INSERT INTO metadata VALUES(?,?)', (k, dump(v)))
        db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity check failed')
        db.close()
        tmp.replace(destination)
        return summary
    except BaseException:
        db.close()
        tmp.unlink(missing_ok=True)
        raise


def open_database(path=DEFAULT_DB):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('Run the build command first to create the local search index')
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    saved = {r['key']: json.loads(r['value']) for r in db.execute('SELECT * FROM metadata')}
    if saved.get('input_manifest_sha256') != file_hash(ROOT / 'SOUTH_AMERICA_SOURCES.json') or saved.get('rules_sha256') != file_hash(ROOT / 'SOUTH_AMERICA_RULES.json'):
        db.close()
        raise ValueError('Index metadata is stale; rebuild the index after changing source manifests or rules')
    return db


def result_record(row, include_raw=False):
    out = {k: row[k] for k in row.keys() if k not in {'rid', 'source_json'}}
    raw = json.loads(row['source_json'])
    out.update({'evidence_class': 'gazetteer_observation' if 'geonames' in row['source'] else
                ('official_address_reference' if row['layer'] == 'address' else 'official_administrative_reference'),
                'unit_verified': False, 'delivery_verified': False, 'premise_verified': False})
    if row['layer'] == 'address':
        out['source_observation_key'] = True
        out['components'] = {k:raw.get(k) for k in ['numero','rep','nom_voie','code_postal','code_insee','nom_commune','certification_commune','type_position']}
        out['municipality_certified_in_source'] = raw.get('certification_commune') == '1'
    if include_raw:
        out['raw'] = raw
    return out


def search(db, cc, text, layer='place', language=None, limit=10, include_historic=False, name_view='any', admin1=None):
    cc = country_code(cc)
    if not 1 <= limit <= 100:
        raise ValueError('limit must be between 1 and 100')
    if layer not in ('place', 'admin', 'feature', 'address'):
        raise ValueError('Invalid layer')
    tokens = lookup_key(text).split()
    if not tokens or len(tokens) > 20:
        raise ValueError('Provide between 1 and 20 search tokens')
    where = ['r.country=?', 'r.layer=?', '(r.source_country IS NULL OR r.source_country=r.country)',
             "n.kind <> 'identifier_or_link'"]
    values = [cc, layer]
    if not include_historic:
        where += ['r.historic=0', 'n.historic=0']
    if language:
        where.append('lower(n.language)=lower(?)'); values.append(language)
    if admin1 is not None:
        where.append('r.admin1=?'); values.append(admin1)
    if name_view == 'english_domestic':
        where.append('lower(n.language)=?'); values.append('en-' + cc.lower())
    elif name_view == 'english_international':
        where.append("n.language='en'")
    elif name_view == 'ascii':
        where.append("n.kind='source_ascii'")
    elif name_view == 'source':
        where.append("n.kind='source_name'")
    elif name_view != 'any':
        raise ValueError('Invalid name_view')
    for token in tokens:
        escaped = token.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        where.append("n.lookup LIKE ? ESCAPE '\\'")
        values.append('%' + escaped + '%')
    sql = 'SELECT r.* FROM records r WHERE r.rid IN (SELECT r.rid FROM records r JOIN names n ON r.rid=n.rid WHERE ' + ' AND '.join(where) + ') ORDER BY r.name,r.record_key LIMIT ?'
    rows = db.execute(sql, values + [limit]).fetchall()
    results = []
    for row in rows:
        out = result_record(row)
        match_rows = db.execute('SELECT n.text,n.language,n.kind,n.historic,n.preferred FROM names n JOIN records r ON r.rid=n.rid WHERE r.rid=? AND ' + ' AND '.join(where) + ' LIMIT 5', [row['rid']] + values).fetchall()
        out['matched_names'] = [dict(x) for x in match_rows]
        results.append(out)
    return {'status': 'candidate_matches_only' if results else 'no_match_in_loaded_sources',
            'country': cc, 'layer': layer, 'name_view': name_view, 'results': results,
            'matching_method': 'All query tokens in one source name; lossy accent/case-insensitive key. No entity merging or official-name assertion.',
            'truncated_at_limit': len(results) == limit}


def distance_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(lon2-lon1)/2)**2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, max(0, a))))


def reverse(db, cc, lat, lon, layer='place', radius_m=5000, limit=5):
    cc = country_code(cc)
    lat, lon = coordinates(lat, lon)
    if lat is None or lon is None or not math.isfinite(radius_m) or not 0 < radius_m <= 100000:
        raise ValueError('Finite coordinates and radius in (0, 100000] metres are required')
    if layer not in ('place', 'admin', 'feature', 'address') or not 1 <= limit <= 100:
        raise ValueError('Invalid layer or limit')
    delta = math.degrees(radius_m/6371008.8)
    # Latitude prefilter has no antimeridian or polar wrap error. Exact spherical distance follows.
    rows = db.execute('SELECT * FROM records WHERE country=? AND layer=? AND historic=0 AND '
        '(source_country IS NULL OR source_country=country) AND latitude BETWEEN ? AND ?',
        (cc, layer, max(-90, lat-delta), min(90, lat+delta)))
    candidates = []
    for row in rows:
        if row['longitude'] is None:
            continue
        d = distance_m(lat, lon, row['latitude'], row['longitude'])
        if d <= radius_m:
            candidates.append((d, row['record_key'], result_record(row)))
    candidates.sort(key=lambda t: (t[0], t[1]))
    out = [{**r, 'distance_m': round(d, 3)} for d, _, r in candidates[:limit]]
    return {'status': 'nearby_reference_candidates' if out else 'no_reference_within_radius',
            'country': cc, 'layer': layer, 'radius_m': radius_m, 'results': out,
            'contains_point_verified': False, 'delivery_verified': False,
            'note': 'Nearest known source points only. No region containment, rooftop, entrance, house number or delivery inference.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', type=Path, default=DEFAULT_DB)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('build')
    sub.add_parser('verify-sources')
    sub.add_parser('summary')
    q = sub.add_parser('profile'); q.add_argument('--country', required=True)
    q = sub.add_parser('postcode'); q.add_argument('--country', required=True); q.add_argument('--value')
    q = sub.add_parser('render'); q.add_argument('--country', required=True); q.add_argument('--input', required=True, type=Path); q.add_argument('--domestic', action='store_true')
    q = sub.add_parser('search'); q.add_argument('--country', required=True); q.add_argument('--text', required=True)
    q.add_argument('--layer', choices=['place','admin','feature','address'], default='place')
    q.add_argument('--language'); q.add_argument('--admin1'); q.add_argument('--limit', type=int, default=10)
    q.add_argument('--include-historic', action='store_true')
    q.add_argument('--name-view', choices=['any','source','ascii','english_domestic','english_international'], default='any')
    q = sub.add_parser('reverse'); q.add_argument('--country', required=True); q.add_argument('--lat', type=float, required=True); q.add_argument('--lon', type=float, required=True)
    q.add_argument('--layer', required=True, choices=['place','admin','feature','address']); q.add_argument('--radius-m', type=float, default=5000); q.add_argument('--limit', type=int, default=5)
    q = sub.add_parser('record'); q.add_argument('--key', required=True)
    args = p.parse_args()
    try:
        if args.command == 'build':
            out = build_database(args.db)
        elif args.command == 'verify-sources':
            m = verify_sources(); scopes = read_json(ROOT/'SOUTH_AMERICA_SCOPE.json')
            out = {'status':'PASS','source_objects':len(m['sources']),'scope_count':len(m['scope_codes']),
                   'country_count':len(scopes['country_codes']),'supplementary_area_count':len(scopes['supplementary_area_codes'])}
        elif args.command == 'profile':
            cc = country_code(args.country)
            out = {**profiles()[cc], 'scope_type':'country' if cc in read_json(ROOT/'SOUTH_AMERICA_SCOPE.json')['country_codes'] else 'supplementary_area'}
        elif args.command == 'postcode':
            out = postcode_review(args.country, args.value)
        elif args.command == 'render':
            out = render_address(args.country, read_json(args.input), not args.domestic)
        else:
            with open_database(args.db) as db:
                if args.command == 'summary':
                    out = {r['key']: json.loads(r['value']) for r in db.execute('SELECT * FROM metadata')}
                elif args.command == 'search':
                    out = search(db, args.country, args.text, args.layer, args.language, args.limit, args.include_historic, args.name_view, args.admin1)
                elif args.command == 'reverse':
                    out = reverse(db, args.country, args.lat, args.lon, args.layer, args.radius_m, args.limit)
                else:
                    row = db.execute('SELECT * FROM records WHERE record_key=?', (args.key,)).fetchone()
                    out = result_record(row, True) if row else {'status':'not_found'}
        print(json.dumps(out, ensure_ascii=False, indent=2))
    except (ValueError, OSError, sqlite3.Error, KeyError, json.JSONDecodeError) as e:
        print(json.dumps({'status':'error','message':str(e)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(2)


if __name__ == '__main__':
    main()
