#!/usr/bin/env python3
"""Build separate Danish/Swedish searchable place and address evidence layers.

Never infer a deliverable address from a place, OSM tag, postal syntax, or
unreviewed/expired official record. The CLI never fetches third-party data.

Python >=3.11, standard library. Input official sources must be lawfully
obtained, explicitly pinned, and mapped through nordic_localities.py.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unicodedata

import nordic_localities as nordic

ROOT = Path(__file__).resolve().parents[1]
CODES = ('DK', 'SE')
SCB_CSV = 'registries/official/SE/scb-municipalities-2026.csv'
SCB_MANIFEST = 'registries/official/SE/source-manifest.json'
LAU_ROOT = 'registries/europe/eurostat-lau'
PLACE_SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE sources (source_id TEXT PRIMARY KEY, country TEXT NOT NULL,
    kind TEXT NOT NULL, snapshot TEXT NOT NULL, source_sha256 TEXT,
    licence TEXT NOT NULL, verified_input INTEGER NOT NULL);
CREATE TABLE observations (
    source_id TEXT NOT NULL REFERENCES sources(source_id),
    record_id TEXT NOT NULL, country TEXT NOT NULL CHECK (country IN ('DK','SE')),
    kind TEXT NOT NULL, name TEXT NOT NULL, normalized_name TEXT NOT NULL,
    search_name TEXT NOT NULL, administrative_code TEXT,
    parent_id TEXT, latitude TEXT, longitude TEXT,
    source_status TEXT, quality TEXT NOT NULL,
    PRIMARY KEY (source_id, record_id));
CREATE INDEX ix_observations_country_name ON observations(country, normalized_name);
CREATE INDEX ix_observations_country_kind ON observations(country, kind);
CREATE INDEX ix_observations_country_search ON observations(country, search_name);
CREATE INDEX ix_observations_code ON observations(country, administrative_code);
'''
EVIDENCE_SCHEMA = '''
CREATE TABLE evidence (
    source_id TEXT NOT NULL, record_id TEXT NOT NULL,
    country TEXT NOT NULL CHECK (country IN ('DK','SE')),
    kind TEXT NOT NULL, name TEXT, street TEXT, house_number TEXT,
    postcode TEXT, postcode_syntax_valid INTEGER,
    administrative_code TEXT, source_status TEXT, latitude TEXT, longitude TEXT,
    source_refs_json TEXT NOT NULL, original_json TEXT NOT NULL,
    observed_at TEXT, address_exists TEXT, deliverable TEXT,
    PRIMARY KEY(source_id, record_id));
CREATE INDEX ix_evidence_search ON evidence(country, kind, name);
CREATE INDEX ix_evidence_postcode ON evidence(country, postcode);
CREATE INDEX ix_evidence_street_number ON evidence(country, street, house_number);
'''


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def lexical_name(s):
    return unicodedata.normalize('NFC', str(s).strip()).casefold()


def search_name(s):
    # Search convenience only. This is NOT an attested native/English alias.
    value = lexical_name(s).replace('æ', 'ae').replace('ø', 'o').replace('å', 'a')
    value = unicodedata.normalize('NFKD', value)
    return ''.join(c for c in value if not unicodedata.combining(c))


def new_db(path, schema):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # create exclusively, never mutate a DB from another run
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    db = sqlite3.connect(path)
    try:
        db.executescript(schema)
        db.execute('PRAGMA journal_mode=DELETE')
        return db
    except Exception:
        db.close()
        path.unlink(missing_ok=True)
        raise


def atomic_build(target, build, schema):
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        raise FileExistsError('Never overwrite existing database')
    with tempfile.TemporaryDirectory(prefix='.dkse-', dir=target.parent) as tmp:
        stage = Path(tmp) / 'output.sqlite3'
        db = new_db(stage, schema)
        try:
            with db:
                result = build(db)
            report = db.execute('PRAGMA integrity_check').fetchone()[0]
            if report != 'ok':
                raise ValueError('SQLite integrity check failed: ' + report)
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Foreign key violation')
        finally:
            db.close()
        # Link rather than rename: fail if a concurrent process created the target
        os.link(stage, target)
    result['output'] = str(target)
    result['bytes'] = target.stat().st_size
    result['sha256'] = digest(target)
    return result


def add_source(db, source_id, country, kind, snapshot, sha, licence, verified):
    if not source_id or country not in CODES or not licence or not snapshot:
        raise ValueError('Malformed source receipt')
    db.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?)',
               (source_id, country, kind, snapshot, sha, licence, int(verified)))


def add_place(db, source, rid, cc, kind, name, admin=None, parent=None, lat=None, lon=None, status=None, quality='place_only'):
    if cc not in CODES or not rid or not name:
        raise ValueError('Invalid locality source record')
    db.execute('INSERT INTO observations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (source, rid, cc, kind, name, lexical_name(name), search_name(name),
         admin, parent, lat, lon, status, quality))


def scb_rows(root):
    root = Path(root)
    mf = json.loads((root / SCB_MANIFEST).read_text(encoding='utf-8'))
    scb = mf['scb_2026']
    path = root / SCB_CSV
    if path.stat().st_size != scb['bytes'] or digest(path) != scb['sha256']:
        raise ValueError('Sweden SCB transcription mismatch')
    counts = Counter()
    counties = {}
    municipalities = set()
    with path.open(newline='', encoding='utf-8') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ['county_code', 'county_name', 'municipality_code', 'municipality_name']:
            raise ValueError('SCB header changed')
        for row in reader:
            if None in row or any(x is None for x in row.values()):
                raise ValueError('Truncated SCB row')
            cc, cn, mc, mn = (row[k] for k in reader.fieldnames)
            if (not re.fullmatch(r'\d{2}', cc) or not re.fullmatch(r'\d{4}', mc)
                    or not mc.startswith(cc) or not cn or not mn):
                raise ValueError('Invalid SCB administrative code')
            if cc in counties and counties[cc] != cn:
                raise ValueError('SCB county name collision')
            if mc in municipalities:
                raise ValueError('SCB municipality code collision')
            counties[cc] = cn
            municipalities.add(mc)
            counts['municipalities'] += 1
            yield ('municipality', mc, mn, 'scb:county:2026:'+cc)
    if len(counties) != 21 or counts['municipalities'] != 290:
        raise ValueError('SCB 2026 national code baseline changed')
    for cc, name in sorted(counties.items()):
        yield ('county', cc, name, 'country:SE')


def read_lau(root, cc):
    folder = Path(root) / LAU_ROOT / cc
    mf = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
    for fname, spec in mf['files'].items():
        p = folder / fname
        if p.stat().st_size != spec['bytes'] or digest(p) != spec['sha256']:
            raise ValueError('Eurostat LAU pinned source mismatch')
    path = folder / 'units.csv.gz'
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        if not {'id', 'country', 'name_national', 'lau_code', 'source_period'} <= set(reader.fieldnames or []):
            raise ValueError('Unknown Eurostat LAU schema')
        count, seen = 0, set()
        for row in reader:
            if None in row or row['country'] != cc:
                raise ValueError('Mixed country or malformed LAU')
            rid = row['id']
            if not rid.startswith('eurostat:lau:') or rid in seen:
                raise ValueError('Missing or duplicate LAU source ID')
            seen.add(rid)
            count += 1
            yield row
        if count != mf['rows']:
            raise ValueError('Eurostat LAU row count mismatch')


def build_places(root, output):
    root = Path(root)
    def work(db):
        totals = {}
        for cc in CODES:
            stats = nordic.verify(root, cc)  # hashes and complete source counts
            source_id = 'GeoNames:'+cc+':2026-09-29'
            add_source(db, source_id, cc, 'geonames', '2026-09-29', None, 'CC-BY-4.0', True)
            count = 0
            for row in nordic.raw_rows(root, cc):
                add_place(db, source_id, row['id'], cc, row['kind'], row['name'],
                          row.get('admin1_code'), row.get('parent_id'), row.get('latitude'),
                          row.get('longitude'), row.get('feature_code'), 'geonames_place_not_address')
                count += 1
            if count != stats['observations']:
                raise ValueError('GeoNames verified source count drift')
            totals[cc] = {'GeoNames': count}
            lsource = 'Eurostat:LAU:'+cc+':2024'
            add_source(db, lsource, cc, 'statistical_municipality', '2024', None, 'Eurostat source terms', True)
            lcount = 0
            for row in read_lau(root, cc):
                add_place(db, lsource, row['id'], cc, 'statistical_lau', row['name_national'],
                          row['lau_code'], row.get('statistical_parent_id'), None, None,
                          row['source_period'], 'statistical_not_government_address')
                lcount += 1
            totals[cc]['Eurostat_LAU'] = lcount
        scb = json.loads((root / SCB_MANIFEST).read_text(encoding='utf-8'))['scb_2026']
        add_source(db, 'SCB:SE:municipalities:2026', 'SE', 'official_code_transcription', '2026',
                   scb['sha256'], scb['license'], True)
        count = 0
        for kind, code, name, parent in scb_rows(root):
            add_place(db, 'SCB:SE:municipalities:2026', 'scb:'+kind+':2026:'+code,
                      'SE', kind, name, code, parent, quality='scb_transcription_not_independently_replayed')
            count += 1
        if count != 311:
            raise ValueError('SCB total changed')
        totals['SE']['SCB_2026'] = count
        return {'source_observations': totals, 'kind': 'places_and_statistical_codes',
                'source_copied_to_new_independent_index': True,
                'national_address_completeness_verified': False,
                'deliverability_verified': False}
    return atomic_build(output, work, PLACE_SCHEMA)


def postal_syntax(code, value):
    if code not in CODES or not isinstance(value, str):
        raise ValueError('Unknown country or postcode')
    return bool(re.fullmatch(r'[0-9]{4}' if code == 'DK' else r'[1-9][0-9]{2} ?[0-9]{2}', value))


def evidence_insert(db, item):
    if item['country'] not in CODES or not item['source_id'] or not item['record_id']:
        raise ValueError('Invalid evidence identity')
    postcode = item.get('postcode')
    syntax = (int(postal_syntax(item['country'], postcode))
              if postcode is not None and postcode != '' else None)
    db.execute('INSERT INTO evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (item['source_id'], item['record_id'], item['country'], item['kind'],
         item.get('name'), item.get('street'), item.get('house_number'),
         postcode, syntax, item.get('administrative_code'), item.get('source_status'),
         item.get('latitude'), item.get('longitude'),
         json.dumps(item.get('source_refs', {}), sort_keys=True, ensure_ascii=False),
         json.dumps(item.get('original', {}), sort_keys=True, ensure_ascii=False),
         item.get('observed_at'), None, None))


def import_osm(exported, code, output):
    if code not in CODES:
        raise ValueError('Only DK and SE extracts supported')
    exported = Path(exported)
    idx = json.loads((exported / 'index.json').read_text(encoding='utf-8'))
    if (idx.get('schema_version') != 1 or idx.get('licence') != 'ODbL-1.0'
            or idx.get('deliverability_in_scope') is not False):
        raise ValueError('Unrecognized/unclear OSM source evidence receipt')
    extracts = [x for x in idx.get('extracts', []) if x.get('extract_code') == code]
    if len(extracts) != 1:
        raise ValueError('Expected exactly one matching OSM extract')
    entry = extracts[0]
    name = entry['file']
    if Path(name).name != name or not name.endswith('.jsonl.gz'):
        raise ValueError('Unsafe OSM evidence filename')
    source = exported / name
    if source.stat().st_size != entry['bytes'] or digest(source) != entry['sha256']:
        raise ValueError('OSM exported evidence pin mismatch')
    def work(db):
        count, skipped = Counter(), Counter()
        with gzip.open(source, 'rt', encoding='utf-8') as f:
            receipt = json.loads(next(f))
            if (receipt.get('record_type') != 'source'
                    or receipt['receipt'].get('country_extract') != code):
                raise ValueError('OSM provenance mismatch')
            for line in f:
                row = json.loads(line)
                tags = row['tags']
                identity = row['id']
                if not identity.startswith('osm:') or not isinstance(tags, dict):
                    raise ValueError('OSM malformed object')
                road = bool(row.get('named_road') or (row.get('road_state') == 'active_tag' and tags.get('name')))
                address = bool(row.get('house_number') and tags.get('addr:housenumber'))
                if not (road or address):
                    skipped['other_features'] += 1
                    continue
                kind = 'osm_address_tag' if address else 'osm_named_road'
                geo = row.get('geometry')
                lng = lat = None
                if geo and geo.get('type') == 'Point':
                    lng, lat = map(str, geo['coordinates'])
                evidence_insert(db, dict(source_id='OSM:Geofabrik:'+code,
                    record_id=identity, country=code, kind=kind,
                    name=tags.get('name'), street=tags.get('addr:street') or tags.get('name'),
                    house_number=tags.get('addr:housenumber'), postcode=tags.get('addr:postcode'),
                    administrative_code=None, source_status='community_observation',
                    latitude=lat, longitude=lng, source_refs={'osm_type_id': identity},
                    original={'tags': {k: v for k, v in tags.items()
                                      if k in ('name','highway','addr:street','addr:housenumber','addr:postcode','addr:city','addr:unit')}},
                    observed_at=receipt['receipt'].get('retrieved_at')))
                count[kind] += 1
        return {'country': code, 'kind': 'osm_evidence_separate_ODbL_database',
                'observations': dict(count), 'skipped': dict(skipped),
                'source_sha256': entry['sha256'], 'attribution': '© OpenStreetMap contributors',
                'licence': 'ODbL-1.0', 'national_address_completeness_verified': False,
                'deliverability_verified': False}
    return atomic_build(output, work, EVIDENCE_SCHEMA)


def import_official(pin_file, source_root, code, output):
    if code not in CODES:
        raise ValueError('Only DK/SE official sources supported')
    pin = json.loads(Path(pin_file).read_text(encoding='utf-8'))
    if pin.get('country') != code:
        raise ValueError('Official country pin mismatches intended database')
    if pin.get('kind') not in ('address','street','locality','administrative','postal_area'):
        raise ValueError('No unreviewed official record type')
    def work(db):
        # nordic's official importer uses file pins, reviewed rights/access, and strict schemas.
        # The output is transient and never replaces original raw source.
        with tempfile.TemporaryDirectory(prefix='dkse-source-') as tmp:
            temp_jsonl = Path(tmp) / 'source.jsonl'
            receipt = nordic.ingest_official(pin, source_root, temp_jsonl)
            count = 0
            with temp_jsonl.open(encoding='utf-8') as f:
                for line in f:
                    obs = json.loads(line)
                    fields = obs['fields']
                    evidence_insert(db, dict(source_id=pin['source_id'],
                        record_id=obs['source_id'], country=code, kind='official_'+obs['kind'],
                        name=fields.get('name'), street=fields.get('street'),
                        house_number=(fields.get('number') or '') + (fields.get('suffix') or ''),
                        postcode=fields.get('postcode'),
                        administrative_code=fields.get('municipality_code'),
                        source_status=fields.get('status'),
                        latitude=fields.get('latitude'), longitude=fields.get('longitude'),
                        source_refs={'parent_id': fields.get('parent_id')},
                        original={'source_qualified_id': obs['source_qualified_id'],
                                  'coordinate_crs': obs['coordinate_crs']},
                        observed_at=obs['source_retrieved_at']))
                    count += 1
            if count != receipt['records']:
                raise ValueError('Official imported row drift')
        return {'country': code, 'kind': 'rights_reviewed_official_observations',
                'records': count, 'source_sha256': pin['sha256'],
                'licence': pin['license'], 'national_address_completeness_verified': False,
                'deliverability_verified': False,
                'note': 'Official presence is not evidence of present occupancy, active status, or carrier deliverability.'}
    return atomic_build(output, work, EVIDENCE_SCHEMA)


def query(path, cc, text='', kind='', limit=20, offset=0, postcode='', street='', number=''):
    if cc not in CODES or not 1 <= limit <= 200 or offset < 0:
        raise ValueError('Invalid query scope or pagination')
    if not any([text, kind, postcode, street, number]):
        raise ValueError('At least one search filter required')
    db = sqlite3.connect('file:' + str(Path(path).resolve()) + '?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        is_places = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='observations'").fetchone()
        if is_places:
            clauses, params = ['o.country=?'], [cc]
            if text:
                clauses.append('(o.normalized_name LIKE ? OR o.search_name LIKE ? OR o.administrative_code=?)')
                params += ['%'+lexical_name(text)+'%', '%'+search_name(text)+'%', text]
            if kind:
                clauses.append('o.kind=?'); params.append(kind)
            if any([postcode,street,number]):
                raise ValueError('Postcode/street/number filters require an evidence database')
            sql = 'SELECT o.*,s.licence,s.snapshot FROM observations o JOIN sources s ON o.source_id=s.source_id WHERE '
        else:
            clauses,params = ['country=?'],[cc]
            if text:
                clauses.append('(name LIKE ? OR street LIKE ?)')
                params += ['%'+text+'%','%'+text+'%']
            if kind: clauses.append('kind=?');params.append(kind)
            if postcode: clauses.append('postcode=?');params.append(postcode)
            if street: clauses.append('street LIKE ?');params.append('%'+street+'%')
            if number: clauses.append('house_number=?');params.append(number)
            sql = 'SELECT * FROM evidence WHERE '
        where = ' AND '.join(clauses)
        total = db.execute('SELECT COUNT(*) FROM ('+sql+where+')',params).fetchone()[0]
        rows = [dict(r) for r in db.execute(sql+where+' ORDER BY source_id, record_id LIMIT ? OFFSET ?',params+[limit,offset])]
        for row in rows:
            if 'original_json' in row:
                row['original'] = json.loads(row.pop('original_json'))
                row['source_refs'] = json.loads(row.pop('source_refs_json'))
        return {'country':cc,'count':total,'results':rows,'next_offset':offset+len(rows) if offset+len(rows)<total else None,
                'address_existence_verified':False,'deliverability_verified':False}
    finally:
        db.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('build-places');b.add_argument('--root',type=Path,default=ROOT);b.add_argument('--output',type=Path,required=True)
    o=sub.add_parser('import-osm');o.add_argument('--exported',type=Path,required=True);o.add_argument('--country',choices=CODES,required=True);o.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('import-official');a.add_argument('--pin',type=Path,required=True);a.add_argument('--source-root',type=Path,required=True);a.add_argument('--country',choices=CODES,required=True);a.add_argument('--output',type=Path,required=True)
    q=sub.add_parser('search');q.add_argument('--database',type=Path,required=True);q.add_argument('--country',choices=CODES,required=True)
    q.add_argument('--text',default='');q.add_argument('--kind',default='');q.add_argument('--postcode',default='');q.add_argument('--street',default='');q.add_argument('--number',default='');q.add_argument('--limit',type=int,default=20);q.add_argument('--offset',type=int,default=0)
    args=p.parse_args(argv)
    if args.command=='build-places':result=build_places(args.root,args.output)
    elif args.command=='import-osm':result=import_osm(args.exported,args.country,args.output)
    elif args.command=='import-official':result=import_official(args.pin,args.source_root,args.country,args.output)
    else:result=query(args.database,args.country,args.text,args.kind,args.limit,args.offset,args.postcode,args.street,args.number)
    print(json.dumps(result,sort_keys=True,ensure_ascii=False,indent=2))
    return result

if __name__=='__main__':main()
