"""Pinned Caribbean BAN address observations and Census road features.

No address-range expansion, cross-source deduplication or delivery inference.
Uses Python 3.11+ standard library. Raw files remain outside ordinary Git.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import csv
import gzip
import hashlib
import io
import itertools
import json
import math
from pathlib import Path
import re
import sqlite3
import struct
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ('AG', 'BS', 'BB', 'CU', 'DM', 'DO', 'GD', 'HT', 'JM', 'KN', 'LC', 'VC', 'TT',
         'AI', 'AW', 'BQ', 'VG', 'KY', 'CW', 'GP', 'MQ', 'MS', 'PR', 'BL', 'MF', 'SX', 'TC', 'VI')
DEPARTMENTS = {'GP': '971', 'MQ': '972', 'BL': '977', 'MF': '978'}
STATES = {'PR': '72', 'VI': '78'}
FIELDS = ('source', 'ordinal', 'country', 'kind', 'source_id', 'admin_code', 'street',
          'number', 'suffix', 'municipality_certified', 'longitude', 'latitude', 'raw_json', 'geometry_json')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def load_manifest(path):
    manifest = json.loads(Path(path).read_text(encoding='utf-8'))
    if (manifest.get('schema_version') != 1 or manifest.get('region') != 'caribbean'
            or manifest.get('failures') or manifest.get('deliverability_in_scope') is not False
            or manifest.get('complete') is not False
            or sorted(manifest.get('scope_codes', [])) != sorted(SCOPE)):
        raise ValueError('Invalid or incomplete Caribbean source manifest')
    ids = [s['id'] for s in manifest['sources']]
    paths = [s['path'] for s in manifest['sources']]
    if (not ids or len(ids) != len(set(ids)) or len(paths) != len(set(paths))
            or set(ids) != set(manifest['required_source_ids'])):
        raise ValueError('Missing or duplicate source inventory')
    for source in manifest['sources']:
        if (source['country'] not in SCOPE or not re.fullmatch(r'[0-9a-f]{64}', source['sha256'])
                or type(source['bytes']) is not int or source['bytes'] <= 0):
            raise ValueError('Invalid source pin')
        cc = source['country']
        if source['format'] == 'ban_csv_gz':
            expected = 'adresses-' + DEPARTMENTS.get(cc, 'unsupported') + '.csv.gz'
        elif source['format'] == 'tiger_roads':
            county = source.get('county', '')
            if not re.fullmatch(STATES.get(cc, 'unsupported') + r'[0-9]{3}', county):
                raise ValueError('County does not belong to the selected country')
            expected = 'tl_2025_' + county + '_roads.zip'
        else:
            raise ValueError('Unsupported official source format')
        if source['path'] != 'raw/' + expected:
            raise ValueError('Source path does not match its declared jurisdiction')
    return manifest


def source_path(root, source):
    root = Path(root).resolve()
    path = (root / source['path']).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Source path escapes its root')
    return path


def verify_pins(manifest, root):
    for source in manifest['sources']:
        path = source_path(root, source)
        if not path.is_file() or path.stat().st_size != source['bytes'] or sha256(path) != source['sha256']:
            raise ValueError('Source bytes differ: ' + source['id'])


def coordinate(value, low, high):
    if value == '':
        return None
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ValueError('Invalid geographic coordinate')
    return number


def ban_records(source, path):
    required = {'id', 'numero', 'rep', 'nom_voie', 'code_insee', 'lon', 'lat', 'certification_commune'}
    with gzip.open(path, 'rt', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, delimiter=';')
        if (not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames)
                or not required <= set(reader.fieldnames)):
            raise ValueError('BAN schema changed')
        for ordinal, row in enumerate(reader, 1):
            if None in row or any(v is None for v in row.values()):
                raise ValueError('Malformed BAN row')
            if not re.fullmatch(DEPARTMENTS[source['country']] + r'[0-9]{2}', row['code_insee']):
                raise ValueError('BAN row belongs to another jurisdiction')
            if not row['id'] or not row['nom_voie'] or row['certification_commune'] not in ('0', '1', ''):
                raise ValueError('Missing identity, street or invalid certification flag')
            if row['numero'] and not re.fullmatch(r'[0-9]+', row['numero']):
                raise ValueError('Unexpected BAN number syntax; inspect rather than coerce')
            lon = coordinate(row['lon'], -180, 180)
            lat = coordinate(row['lat'], -90, 90)
            if (lon is None) != (lat is None):
                raise ValueError('Only one geographic coordinate is present')
            yield (source['id'], ordinal, source['country'], 'ban_address', row['id'], row['code_insee'],
                   row['nom_voie'], row['numero'], row['rep'], row['certification_commune'],
                   lon, lat, canonical(row), None)


def dbf_records(data, encoding):
    if len(data) < 33:
        raise ValueError('Truncated DBF header')
    count, header_size, record_size = struct.unpack_from('<IHH', data, 4)
    if header_size < 33 or (header_size - 33) % 32 or len(data) < header_size + count * record_size:
        raise ValueError('Truncated DBF records')
    fields = []
    for offset in range(32, header_size - 1, 32):
        descriptor = data[offset:offset + 32]
        fields.append((descriptor[:11].split(b'\0')[0].decode('ascii'), descriptor[16]))
    if (data[header_size - 1] != 13 or record_size != 1 + sum(width for _, width in fields)
            or len({name for name, _ in fields}) != len(fields)):
        raise ValueError('Invalid DBF field layout')
    for index in range(count):
        record = data[header_size + index * record_size:header_size + (index + 1) * record_size]
        if record[:1] != b' ':
            raise ValueError('Deleted or invalid DBF row needs review')
        result = {}
        cursor = 1
        for name, width in fields:
            result[name] = record[cursor:cursor + width].decode(encoding).strip()
            cursor += width
        yield result


def shape_records(data):
    if (len(data) < 100 or struct.unpack_from('>i', data, 0)[0] != 9994
            or struct.unpack_from('>i', data, 24)[0] * 2 != len(data)
            or struct.unpack_from('<i', data, 28)[0] != 1000
            or struct.unpack_from('<i', data, 32)[0] != 3):
        raise ValueError('Invalid or unsupported PolyLine shapefile')
    offset = 100
    ordinal = 0
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError('Truncated shape record')
        number, words = struct.unpack_from('>ii', data, offset)
        size = words * 2
        body = data[offset + 8:offset + 8 + size]
        ordinal += 1
        if number != ordinal or size < 44 or len(body) != size or struct.unpack_from('<i', body, 0)[0] != 3:
            raise ValueError('Invalid road geometry record')
        parts, points = struct.unpack_from('<ii', body, 36)
        if parts < 1 or points < 2 or size != 44 + 4 * parts + 16 * points:
            raise ValueError('Invalid PolyLine dimensions')
        starts = struct.unpack_from('<' + 'i' * parts, body, 44)
        if starts[0] != 0 or any(b <= a or b - a < 2 for a, b in zip(starts, starts[1:] + (points,))):
            raise ValueError('Invalid PolyLine part offsets')
        bounds = struct.unpack_from('<dddd', body, 4)
        coordinates = list(struct.iter_unpack('<dd', body[44 + 4 * parts:]))
        for lon, lat in coordinates:
            coordinate(str(lon), -180, 180)
            coordinate(str(lat), -90, 90)
        xs, ys = zip(*coordinates)
        if bounds != (min(xs), min(ys), max(xs), max(ys)):
            raise ValueError('Geometry bounds do not match its points')
        yield canonical({'record': number, 'parts': parts, 'points': points, 'bounds': bounds,
                         'shape_record_sha256': hashlib.sha256(body).hexdigest(), 'crs': 'NAD83 (source .prj retained)'})
        offset += 8 + size


def road_records(source, path):
    stem = Path(source['path']).stem
    with zipfile.ZipFile(path) as archive:
        expected = {stem + suffix for suffix in ('.shp', '.dbf', '.prj', '.shx')}
        names = archive.namelist()
        if len(names) != len(set(names)) or not expected <= set(names) or archive.testzip() is not None:
            raise ValueError('Road archive members missing or corrupt')
        projection = archive.read(stem + '.prj').decode('ascii')
        if 'GCS_North_American_1983' not in projection or 'UNIT["Degree"' not in projection:
            raise ValueError('Road coordinate reference system changed')
        encoding = archive.read(stem + '.cpg').decode('ascii').strip() if stem + '.cpg' in names else 'utf-8'
        if encoding in ('UTF-8', '65001'):
            encoding = 'utf-8'
        dbf = dbf_records(archive.read(stem + '.dbf'), encoding)
        geometry = shape_records(archive.read(stem + '.shp'))
        for ordinal, (row, shape) in enumerate(itertools.zip_longest(dbf, geometry), 1):
            if row is None or shape is None:
                raise ValueError('Road attribute and geometry counts differ')
            if not {'LINEARID', 'FULLNAME', 'RTTYP', 'MTFCC'} <= row.keys() or not row['LINEARID']:
                raise ValueError('Road schema or identity changed')
            if not re.fullmatch(r'S[0-9]{4}', row['MTFCC']):
                raise ValueError('Unexpected feature outside the All Roads specification')
            yield (source['id'], ordinal, source['country'], 'tiger_road', row['LINEARID'], source['county'],
                   row['FULLNAME'], '', '', '', None, None, canonical(row), shape)


def records(source, root):
    path = source_path(root, source)
    yield from ban_records(source, path) if source['format'] == 'ban_csv_gz' else road_records(source, path)


def update_digest(digest, row):
    digest.update(canonical(list(row)).encode('utf-8') + b'\n')


def build(manifest, sources, output):
    verify_pins(manifest, sources)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('Use a new output database; accepted results are not overwritten')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.caribbean-', suffix='.sqlite', dir=output.parent) as temp:
        db = sqlite3.connect(temp.name)
        try:
            db.executescript('''CREATE TABLE observations (
                source TEXT NOT NULL, ordinal INTEGER NOT NULL, country TEXT NOT NULL, kind TEXT NOT NULL,
                source_id TEXT NOT NULL, admin_code TEXT NOT NULL, street TEXT NOT NULL, number TEXT NOT NULL,
                suffix TEXT NOT NULL, municipality_certified TEXT NOT NULL, longitude REAL, latitude REAL,
                raw_json TEXT NOT NULL, geometry_json TEXT, PRIMARY KEY(source, ordinal));
                CREATE TABLE sources (id TEXT PRIMARY KEY, country TEXT, sha256 TEXT, rows INTEGER, row_sha256 TEXT);
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);''')
            reports = []
            for source in manifest['sources']:
                digest = hashlib.sha256()
                count = 0
                for row in records(source, sources):
                    db.execute('INSERT INTO observations VALUES (' + ','.join('?' * len(FIELDS)) + ')', row)
                    update_digest(digest, row)
                    count += 1
                if not count:
                    raise ValueError('Empty official source: ' + source['id'])
                db.execute('INSERT INTO sources VALUES (?,?,?,?,?)',
                           (source['id'], source['country'], source['sha256'], count, digest.hexdigest()))
                reports.append({'source': source['id'], 'country': source['country'], 'rows': count,
                                'row_sha256': digest.hexdigest(), 'status': 'PASS'})
            db.executescript('CREATE INDEX lookup ON observations(country,kind,number);'
                             'CREATE INDEX source_identity ON observations(country,source_id);')
            for key, value in {'schema_version': 1, 'manifest_sha256': hashlib.sha256(canonical(manifest).encode()).hexdigest(),
                               'complete': False, 'deliverability_in_scope': False,
                               'source_reports': reports}.items():
                db.execute('INSERT INTO metadata VALUES (?,?)', (key, canonical(value)))
            db.commit()
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('SQLite integrity failure')
        finally:
            db.close()
        # Hard-link creation is atomic and fails if another writer created output meanwhile.
        output.hardlink_to(temp.name)
    return {'status': 'PASS', 'sources': reports, 'complete': False, 'deliverability_in_scope': False}


def open_database(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('Build the official-source index first')
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    return db


def replay(manifest, sources, database):
    verify_pins(manifest, sources)
    with open_database(database) as db:
        metadata = {r['key']: json.loads(r['value']) for r in db.execute('SELECT * FROM metadata')}
        if metadata['manifest_sha256'] != hashlib.sha256(canonical(manifest).encode()).hexdigest():
            raise ValueError('Database manifest differs')
        if {r[0] for r in db.execute('SELECT id FROM sources')} != set(manifest['required_source_ids']):
            raise ValueError('Database source inventory differs')
        results = []
        for source in manifest['sources']:
            digest = hashlib.sha256()
            count = 0
            actual = db.execute('SELECT ' + ','.join(FIELDS) + ' FROM observations WHERE source=? ORDER BY ordinal', (source['id'],))
            for expected, stored in itertools.zip_longest(records(source, sources), actual):
                if expected is None or stored is None or tuple(stored) != expected:
                    raise ValueError('Stored source row differs: ' + source['id'])
                update_digest(digest, expected)
                count += 1
            pin = db.execute('SELECT * FROM sources WHERE id=?', (source['id'],)).fetchone()
            if count != pin['rows'] or digest.hexdigest() != pin['row_sha256'] or pin['sha256'] != source['sha256']:
                raise ValueError('Stored source totals differ')
            results.append({'source': source['id'], 'rows': count, 'row_sha256': digest.hexdigest()})
        if sum(r['rows'] for r in results) != db.execute('SELECT count(*) FROM observations').fetchone()[0]:
            raise ValueError('Unreplayed source rows')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity failure')
    return {'status': 'PASS', 'source_replays': results, 'complete': False, 'deliverability_in_scope': False}


def coverage(database):
    with open_database(database) as db:
        results = []
        for country in SCOPE:
            counts = dict(Counter({r['kind']: r['n'] for r in db.execute(
                'SELECT kind,count(*) n FROM observations WHERE country=? GROUP BY kind', (country,))}))
            scalar = lambda sql: db.execute(sql, (country,)).fetchone()[0]
            results.append({'country': country, 'ban_position_observations': counts.get('ban_address', 0),
                'ban_numbered_source_ids': scalar("SELECT count(DISTINCT source_id) FROM observations WHERE country=? AND kind='ban_address' AND number<>''"),
                'ban_certified_position_observations': scalar("SELECT count(*) FROM observations WHERE country=? AND kind='ban_address' AND municipality_certified='1'"),
                'addressed_street_name_groups': scalar("SELECT count(*) FROM (SELECT admin_code,street FROM observations WHERE country=? AND kind='ban_address' GROUP BY admin_code,street)"),
                'road_feature_observations': counts.get('tiger_road', 0),
                'unnamed_road_feature_observations': scalar("SELECT count(*) FROM observations WHERE country=? AND kind='tiger_road' AND street=''"),
                'all_administrative_levels_complete': False, 'addressed_streets_complete': False,
                'physical_roads_complete': False, 'assigned_numbers_complete': False,
                'independent_national_denominators': None, 'deliverability_in_scope': False})
    return {'schema_version': 1, 'region': 'caribbean', 'countries': results, 'complete': False,
            'deliverability_in_scope': False, 'count_semantics': [
                'BAN source IDs can have multiple positions; certified and uncertified observations remain distinct.',
                'Street name groups are retrieval buckets, not an authoritative inventory of distinct streets.',
                'Census All Roads may include coincident features for multiple road names and routes.',
                'All source rows were ingested; national completeness requires independent inventories and a reference date.']}


def crosscheck_admin(database, hierarchy_database):
    """Join only matching INSEE codes; never join administrative areas by names."""
    results = []
    with open_database(database) as observations, open_database(hierarchy_database) as hierarchy:
        for country in DEPARTMENTS:
            codes = [r[0] for r in observations.execute(
                "SELECT DISTINCT admin_code FROM observations WHERE country=? AND kind='ban_address' ORDER BY admin_code", (country,))]
            for code in codes:
                matches = [r[0] for r in hierarchy.execute(
                    "SELECT id FROM nodes WHERE country=? AND namespace='insee-2026' AND code=? AND kind IN ('commune','collectivity')",
                    (country, code))]
                join = 'exact_official_code'
                if not matches and country in ('BL', 'MF'):
                    # COG explicitly publishes 97701/97801 as code aliases of the
                    # corresponding collectivity. These are not extra communes.
                    for observation in hierarchy.execute(
                            "SELECT n.id,n.code,o.raw_json FROM nodes n JOIN observations o ON o.node=n.id "
                            "WHERE n.country=? AND n.namespace='insee-2026' AND n.kind='collectivity' AND o.source='fr-insee-cog-2026'",
                            (country,)):
                        raw = json.loads(observation['raw_json'])
                        fields = raw.get('fields', {})
                        if (raw.get('member') == 'v_commune_comer_2026.csv' and fields.get('COM_COMER') == code
                                and fields.get('COMER') == observation['code'] and fields.get('NATURE_ZONAGE') == 'COM'):
                            matches.append(observation['id'])
                    join = 'explicit_insee_code_alias'
                if len(matches) != 1:
                    raise ValueError('Unresolved or ambiguous INSEE administrative reference: ' + country + ':' + code)
                results.append({'country': country, 'code': code, 'hierarchy_node': matches[0], 'join': join})
    return {'status': 'PASS', 'insee_code_references': results, 'reference_count': len(results),
            'complete': False, 'spatial_containment_verified': False, 'deliverability_in_scope': False}


def search(database, country, text='', number=None, kind=None, limit=20, offset=0):
    if country not in SCOPE or not 1 <= limit <= 200 or offset < 0 or (number is not None and not isinstance(number, str)):
        raise ValueError('Invalid search scope or pagination')
    clauses = ['country=?']
    values = [country]
    if text:
        escaped = text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        clauses.append("street LIKE ? ESCAPE '\\'")
        values.append('%' + escaped + '%')
    if number is not None:
        clauses.append('number=?')
        values.append(number)
    if kind is not None:
        if kind not in ('ban_address', 'tiger_road'):
            raise ValueError('Invalid observation kind')
        clauses.append('kind=?')
        values.append(kind)
    with open_database(database) as db:
        rows = db.execute('SELECT * FROM observations WHERE ' + ' AND '.join(clauses) +
                          ' ORDER BY source,ordinal LIMIT ? OFFSET ?', values + [limit + 1, offset]).fetchall()
        results = []
        for row in rows[:limit]:
            value = dict(row)
            value['raw'] = json.loads(value.pop('raw_json'))
            geometry = value.pop('geometry_json')
            value['geometry_reference'] = json.loads(geometry) if geometry else None
            value['assignment_status'] = ('municipality_certified_source_record' if value['municipality_certified'] == '1'
                                           else 'observed_in_source_assignment_not_independently_verified') if value['kind'] == 'ban_address' else 'not_an_assigned_number'
            results.append(value)
    more = len(rows) > limit
    return {'country': country, 'results': results, 'has_more': more, 'next_offset': offset + limit if more else None,
            'complete': False, 'deliverability_in_scope': False}


def acquire(manifest, target):
    target = Path(target).resolve()
    target.mkdir(parents=True, exist_ok=False)
    def fetch(source):
        url = source['requested_url']
        if urlsplit(url).scheme != 'https' or urlsplit(url).hostname not in {'adresse.data.gouv.fr', 'www2.census.gov'}:
            raise ValueError('Only registered official HTTPS hosts are accepted')
        path = source_path(target, source)
        path.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(Request(url, headers={'User-Agent': 'WorldLocalities-Caribbean/1.0'}), timeout=45) as response:
            final = urlsplit(response.url)
            if final.scheme != 'https' or final.hostname not in {'adresse.data.gouv.fr', 'www2.census.gov'}:
                raise ValueError('Unexpected download redirect')
            with path.open('xb') as stream:
                count = 0
                for block in iter(lambda: response.read(1024 * 1024), b''):
                    count += len(block)
                    if count > source['bytes']:
                        raise ValueError('Source changed; inspect a new candidate before accepting')
                    stream.write(block)
        if path.stat().st_size != source['bytes'] or sha256(path) != source['sha256']:
            raise ValueError('Source changed; the pinned historical snapshot was not recovered')
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(fetch, manifest['sources']))
        verify_pins(manifest, target)
    except Exception as exc:
        (target / 'ACQUISITION_FAILED.json').write_text(canonical({'status': 'FAIL', 'error': str(exc)}) + '\n')
        raise
    (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return {'status': 'PINNED_BYTES_RECOVERED', 'files': len(manifest['sources']), 'complete': False, 'deliverability_in_scope': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inventory', 'acquire', 'verify', 'build', 'replay', 'coverage', 'search', 'crosscheck-admin'])
    parser.add_argument('--manifest', type=Path, default=ROOT / 'releases/hierarchy/caribbean/official-sources.json')
    parser.add_argument('--sources', type=Path)
    parser.add_argument('--db', type=Path)
    parser.add_argument('--hierarchy-db', type=Path)
    parser.add_argument('--target', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--country')
    parser.add_argument('--text', default='')
    parser.add_argument('--number')
    parser.add_argument('--kind', choices=['ban_address', 'tiger_road'])
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--offset', type=int, default=0)
    args = parser.parse_args()
    try:
        if args.command == 'crosscheck-admin':
            if not args.db or not args.hierarchy_db: raise ValueError('--db and --hierarchy-db are required')
            result = crosscheck_admin(args.db, args.hierarchy_db)
        elif args.command == 'coverage':
            if not args.db: raise ValueError('--db is required')
            result = coverage(args.db)
        elif args.command == 'search':
            if not args.db or not args.country: raise ValueError('--db and --country are required')
            result = search(args.db, args.country, args.text, args.number, args.kind, args.limit, args.offset)
        else:
            manifest = load_manifest(args.manifest)
            if args.command == 'inventory':
                result = {'status': 'VALID_MANIFEST', 'countries': len(SCOPE), 'source_files': len(manifest['sources']),
                          'complete': False, 'deliverability_in_scope': False}
            elif args.command == 'acquire':
                if not args.target: raise ValueError('--target is required')
                result = acquire(manifest, args.target)
            else:
                if not args.sources: raise ValueError('--sources is required')
                if args.command == 'verify':
                    verify_pins(manifest, args.sources)
                    result = {'status': 'PINNED_BYTES_VERIFIED', 'sources': len(manifest['sources']), 'complete': False, 'deliverability_in_scope': False}
                elif args.command == 'build':
                    if not args.db: raise ValueError('--db is required')
                    result = build(manifest, args.sources, args.db)
                else:
                    if not args.db: raise ValueError('--db is required')
                    result = replay(manifest, args.sources, args.db)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if args.output:
            args.output.write_text(rendered, encoding='utf-8')
        else:
            print(rendered, end='')
    except (OSError, ValueError, KeyError, sqlite3.Error, zipfile.BadZipFile, struct.error) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
