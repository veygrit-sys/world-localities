#!/usr/bin/env python3
"""Source-qualified ES/PT/MT locality and address evidence; offline and fail closed.

Reads pinned real GeoNames registry files and optionally separately reviewed official files.
A source observation is not evidence of postal existence or parcel deliverability.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import struct
import tempfile
from urllib.parse import urlsplit
import zipfile

COUNTRIES = ('ES', 'PT', 'MT')
FORMATS = ('csv', 'csv.gz', 'zip-csv', 'jsonl', 'geojson', 'gpkg', 'zip-gpkg')
KINDS = ('address', 'street', 'administrative', 'locality')
FIELDS = ('id', 'name', 'street', 'house_number', 'postcode', 'locality', 'municipality_code',
          'parent_id', 'status', 'x', 'y', 'language')
ALLOWED_GPKG_IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z_0-9]{0,127}\Z')
SHA = re.compile(r'[a-f0-9]{64}\Z')
POSTCODES = {'ES': re.compile(r'[0-9]{5}\Z'),
             'PT': re.compile(r'[0-9]{4}-[0-9]{3}\Z'),
             'MT': re.compile(r'[A-Z]{3} ?[0-9]{4}\Z')}


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def file_sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def raw_postcode(country, value):
    """Do not correct data; report syntax separately from existence."""
    value = str(value or '')
    return {'raw': value, 'syntax_valid': bool(POSTCODES[country].fullmatch(value)),
            'exists': None, 'deliverable': None}


def _safe_path(root, name):
    rel = Path(name)
    if rel.is_absolute() or rel == Path('.') or '..' in rel.parts:
        raise ValueError('Unsafe source path')
    root = Path(root).resolve()
    resolved = (root / rel).resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError('Source missing or outside data root')
    return resolved


def _check_hash_size(path, size, digest):
    if type(size) is not int or size <= 0 or not isinstance(digest, str) or not SHA.fullmatch(digest):
        raise ValueError('Missing or malformed byte receipt')
    if path.stat().st_size != size or file_sha(path) != digest:
        raise ValueError('Pinned source differs in size or SHA-256')


def _validate_receipt(r, root):
    if r.get('schema_version') != 1 or r.get('country') not in COUNTRIES:
        raise ValueError('Unknown receipt schema or country')
    if r.get('kind') not in KINDS or r.get('format') not in FORMATS:
        raise ValueError('Unrecognized entity or format')
    if not re.fullmatch('[a-z0-9][a-z0-9_.-]{1,79}', r.get('dataset', '')):
        raise ValueError('Invalid dataset namespace')
    origin = urlsplit(r.get('publisher_url', ''))
    if origin.scheme != 'https' or not origin.hostname or origin.username or origin.password:
        raise ValueError('HTTPS publisher source is required')
    if r.get('rights_reviewed') is not True or not r.get('license') or not r.get('attribution'):
        raise ValueError('Reviewed license and attribution required')
    if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', r.get('source_date', '')):
        raise ValueError('Pinned source reference date required')
    if not re.fullmatch('EPSG:[0-9]{4,6}', r.get('crs', '')):
        raise ValueError('Explicit source CRS required')
    mapping = r.get('fields')
    if not isinstance(mapping, dict) or 'id' not in mapping or not set(mapping) <= set(FIELDS):
        raise ValueError('Explicit source field mapping required')
    if any(not isinstance(v, str) or not v for v in mapping.values()):
        raise ValueError('Invalid source column')
    if r.get('format') in ('zip-csv', 'zip-gpkg'):
        member = r.get('member', '')
        if not member or Path(member).name != member or member in ('.', '..') or '\\' in member:
            raise ValueError('Explicit safe ZIP member required')
    if r['format'] in ('gpkg', 'zip-gpkg'):
        if not ALLOWED_GPKG_IDENTIFIER.fullmatch(r.get('table', '')):
            raise ValueError('Explicit safe GeoPackage table name required')
    if r['format'] in ('csv', 'csv.gz', 'zip-csv'):
        if r.get('delimiter', ',') not in (',', ';', '\t') or r.get('encoding', 'utf-8-sig') not in ('utf-8','utf-8-sig','cp1252'):
            raise ValueError('Unreviewed CSV dialect or encoding')
    path = _safe_path(root, r.get('path', ''))
    _check_hash_size(path, r.get('bytes'), r.get('sha256'))
    return path


def _csv_rows(f, r):
    with io.TextIOWrapper(f, encoding=r.get('encoding', 'utf-8-sig'), newline='') as text:
        dr = csv.DictReader(text, delimiter=r.get('delimiter', ','))
        if not dr.fieldnames or len(set(dr.fieldnames)) != len(dr.fieldnames):
            raise ValueError('CSV headers missing/duplicate')
        if not set(r['fields'].values()).issubset(set(dr.fieldnames)):
            raise ValueError('Missing official source columns')
        for row in dr:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('Malformed source CSV row')
            yield row


def _json_rows(f, r, geojson=False):
    if not geojson:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError('Expected JSON object per line')
            yield row
        return
    # Do not parse potentially multi-GB FeatureCollections into RAM.
    if f.seekable():
        pos = f.tell(); f.seek(0, 2); length = f.tell(); f.seek(pos)
        if length > 32_000_000:
            raise ValueError('Large GeoJSON requires streamed JSONL or GeoPackage')
    collection = json.load(f)
    if collection.get('type') != 'FeatureCollection' or not isinstance(collection.get('features'), list):
        raise ValueError('Expected GeoJSON FeatureCollection')
    for item in collection['features']:
        if item.get('type') != 'Feature' or not isinstance(item.get('properties'), dict):
            raise ValueError('Malformed GeoJSON feature')
        row = dict(item['properties'])
        geom = item.get('geometry') or {}
        if geom.get('type') == 'Point' and r['crs'] == 'EPSG:4326':
            coord = geom.get('coordinates', [])
            if len(coord) >= 2:
                row['__geometry_x'], row['__geometry_y'] = coord[0], coord[1]
        yield row


def _read_point(blob):
    """Return raw point x/y and SRS from GeoPackage; never infer a centroid."""
    if blob is None:
        return None
    if not isinstance(blob, bytes) or len(blob) < 29 or blob[:2] != b'GP' or blob[2] != 0:
        return None
    flags = blob[3]
    if flags & 0b11100000 or flags & 0b00010000:
        return None
    little = bool(flags & 1)
    endian = '<' if little else '>'
    envelope = (flags >> 1) & 7
    if envelope > 4:
        return None
    start = 8 + {0:0, 1:32, 2:48, 3:48, 4:64}[envelope]
    if len(blob) < start + 21:
        return None
    srs = struct.unpack(endian+'i', blob[4:8])[0]
    wkb = blob[start:]
    wend = '<' if wkb[0] == 1 else '>' if wkb[0] == 0 else None
    if wend is None or struct.unpack(wend+'I', wkb[1:5])[0] not in (1, 1001):
        return None
    x, y = struct.unpack(wend+'dd', wkb[5:21])
    return (x, y, srs)


def _gpkg_rows(path, r):
    # Read-only: never modify an official source file.
    db = sqlite3.connect('file:' + path.resolve().as_posix() + '?mode=ro', uri=True)
    try:
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('Invalid GeoPackage SQLite')
        table = r['table']
        available = db.execute('SELECT table_name,srs_id FROM gpkg_contents').fetchall()
        if table not in {a for a, _ in available}:
            raise ValueError('GeoPackage layer not registered')
        columns = {v[1] for v in db.execute(f'PRAGMA table_info("{table}")')}
        if not set(r['fields'].values()) <= columns:
            raise ValueError('Missing GeoPackage columns')
        geo = db.execute('SELECT column_name,srs_id FROM gpkg_geometry_columns WHERE table_name=?', (table,)).fetchone()
        source_srs = int(r['crs'].split(':')[1])
        if geo and source_srs != geo[1]:
            raise ValueError('Source CRS disagrees with GPKG geometry metadata')
        if geo and geo[0] not in columns:
            raise ValueError('Missing geometry column')
        query = f'SELECT * FROM "{table}"'
        cur = db.execute(query)
        cols = [x[0] for x in cur.description]
        for values in cur:
            row = dict(zip(cols, values))
            if geo:
                point = _read_point(row.get(geo[0]))
                if point and point[2] != geo[1]:
                    raise ValueError('Feature CRS disagrees with layer')
                if point:
                    row['__geometry_x'], row['__geometry_y'] = point[:2]
            yield row
    finally:
        db.close()


def _archive_member(archive, filename, limit=2_000_000_000):
    names = archive.namelist()
    if len(set(names)) != len(names):
        raise ValueError('Duplicate ZIP entries')
    for info in archive.infolist():
        if Path(info.filename).is_absolute() or '..' in Path(info.filename).parts or '\\' in info.filename:
            raise ValueError('Unsafe ZIP path')
    item = archive.getinfo(filename)
    if item.is_dir() or item.file_size > limit or (item.compress_size and item.file_size / item.compress_size > 1000):
        raise ValueError('Unsafe ZIP member expansion')
    return item


def source_rows(path, r):
    fmt = r['format']
    if fmt == 'csv':
        with path.open('rb') as src:
            yield from _csv_rows(src, r)
    elif fmt == 'csv.gz':
        with gzip.open(path, 'rb') as src:
            yield from _csv_rows(src, r)
    elif fmt == 'zip-csv':
        with zipfile.ZipFile(path) as arch:
            _archive_member(arch, r['member'])
            with arch.open(r['member']) as src:
                yield from _csv_rows(src, r)
    elif fmt in ('jsonl', 'geojson'):
        with path.open('r', encoding='utf-8') as src:
            yield from _json_rows(src, r, geojson=(fmt=='geojson'))
    elif fmt == 'gpkg':
        yield from _gpkg_rows(path, r)
    elif fmt == 'zip-gpkg':
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)/'input.gpkg'
            with zipfile.ZipFile(path) as arch:
                _archive_member(arch,r['member'])
                with arch.open(r['member']) as src, target.open('xb') as dst:
                    while chunk := src.read(1024*1024): dst.write(chunk)
            yield from _gpkg_rows(target, r)


def _schema(db):
    db.executescript('''
       PRAGMA journal_mode=DELETE;
       CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
       CREATE TABLE observations (
        source_ref TEXT PRIMARY KEY, country TEXT NOT NULL, source_key TEXT NOT NULL,
        kind TEXT NOT NULL, name TEXT NOT NULL, street TEXT NOT NULL,
        house_number TEXT NOT NULL, postcode TEXT NOT NULL, postcode_syntax TEXT NOT NULL,
        locality TEXT NOT NULL, municipality_code TEXT NOT NULL, parent_ref TEXT NOT NULL,
        status TEXT NOT NULL, language TEXT NOT NULL, x REAL, y REAL, crs TEXT NOT NULL,
        confidence TEXT NOT NULL
       );
       CREATE INDEX ix_obs_name ON observations(country, name);
       CREATE INDEX ix_obs_postcode ON observations(country, postcode);
       CREATE INDEX ix_obs_municipality ON observations(country, municipality_code);
    ''')


def _str(value):
    return '' if value is None else str(value)


def _mapped(r, row, field):
    if field not in r['fields']:
        return ''
    value = row.get(r['fields'][field])
    # Numeric coercion destroys possible leading zeroes in source identifiers.
    if field in ('id','postcode','municipality_code','house_number') and value is not None and not isinstance(value,str):
        raise ValueError('Identity/postal/house fields must be lexical source strings')
    return _str(value)


def _x_y(r, row):
    x = _mapped(r, row, 'x') or row.get('__geometry_x')
    y = _mapped(r, row, 'y') or row.get('__geometry_y')
    if x in (None, '') and y in (None, ''):
        return (None, None)
    if x in (None, '') or y in (None, ''):
        raise ValueError('Partial coordinate pair')
    xx, yy = float(x), float(y)
    if not all(__import__('math').isfinite(v) for v in (xx,yy)):
        raise ValueError('Nonfinite coordinate')
    if r['crs'] == 'EPSG:4326' and not (-180 <= xx <= 180 and -90 <= yy <= 90):
        raise ValueError('Out of bounds WGS84 coordinate')
    return (xx, yy)


def _official_row(r, raw):
    identity = _mapped(r,raw,'id')
    if not identity or len(identity)>400:
        raise ValueError('Missing official ID')
    prefix = 'official:'+r['country']+':'+r['dataset']+':'
    postcode = _mapped(r,raw,'postcode')
    x, y = _x_y(r,raw)
    name, street, number = (_mapped(r,raw,k) for k in ('name','street','house_number'))
    if r['kind'] == 'address' and not (number or street or _mapped(r,raw,'locality')):
        raise ValueError('Address observation has no address components')
    return (prefix+identity, r['country'], r['dataset'], r['kind'], name, street, number,
            postcode, 'valid_shape' if raw_postcode(r['country'],postcode)['syntax_valid'] else 'not_verified_or_invalid',
            _mapped(r,raw,'locality'), _mapped(r,raw,'municipality_code'), _mapped(r,raw,'parent_id'),
            _mapped(r,raw,'status'), _mapped(r,raw,'language'), x, y, r['crs'],
            'official_source_observation_not_verified_address')


def _baseline_iter(repo, country):
    directory = repo / 'registries' / 'europe' / 'countries' / country
    meta = json.loads((directory/'metadata.json').read_text(encoding='utf-8'))
    if meta['country']['country'] != country or meta['source'] != 'GeoNames':
        raise ValueError('GeoNames baseline metadata changed')
    seen=set(); total=0
    for name, entry in sorted(meta['files'].items()):
        path = _safe_path(directory,name)
        _check_hash_size(path,entry['bytes'],entry['sha256'])
        with gzip.open(path,'rb') as fh:
            decompressed = fh.read()
        if hashlib.sha256(decompressed).hexdigest()!=entry['uncompressed_sha256']:
            raise ValueError('Decompressed GeoNames hash mismatch')
        with io.StringIO(decompressed.decode('utf-8')) as txt:
            reader=csv.DictReader(txt)
            needed={'id','name','country_code','kind','latitude','longitude','parent_id','admin_level'}
            if not needed <= set(reader.fieldnames or []):
                raise ValueError('GeoNames columns changed')
            partcount=0
            for row in reader:
                key=row['id']
                if row['country_code']!=country or key in seen or not key.startswith('gn:'):
                    raise ValueError('Country or ID mismatch in GeoNames')
                seen.add(key)
                x,y=(float(row['longitude']),float(row['latitude'])) if row['longitude'] and row['latitude'] else (None,None)
                partcount+=1; total+=1
                yield (key,country,'geonames','locality' if row['kind']=='locality' else 'administrative',
                       row['name'],'','','','not_checked','',row.get('admin2_code',''),row['parent_id'],'',
                       'und',x,y,'EPSG:4326','geonames_observation_not_official_address')
            if partcount!=entry['rows']:
                raise ValueError('GeoNames part count mismatch')
    if total!=sum(v['rows'] for v in meta['files'].values()):
        raise ValueError('GeoNames total count mismatch')


def observations_digest(db):
    digest=hashlib.sha256()
    for row in db.execute('SELECT * FROM observations ORDER BY source_ref'):
        digest.update(canonical(row).encode('utf-8')+b'\n')
    return digest.hexdigest()

def build(root, out, countries=COUNTRIES, receipts=(), source_root=None):
    root=Path(root);out=Path(out).absolute()
    if out.exists() or out.is_symlink(): raise ValueError('Output already exists')
    out.parent.mkdir(parents=True,exist_ok=True)
    recipes=[json.loads(Path(p).read_text(encoding='utf-8')) for p in receipts]
    if recipes and source_root is None: raise ValueError('Explicit source root required')
    validated=[(r,_validate_receipt(r,source_root)) for r in recipes]
    counts=Counter()
    with tempfile.TemporaryDirectory(dir=out.parent,prefix='.es-pt-mt-') as td:
        stage=Path(td)/'observations.sqlite'
        db=sqlite3.connect(stage)
        try:
            _schema(db)
            insert='INSERT INTO observations VALUES ('+','.join(['?']*18)+')'
            for country in countries:
                for row in _baseline_iter(root,country):
                    db.execute(insert,row)
                    counts[country+':geonames']+=1
            for receipt, source in validated:
                if receipt['country'] not in countries:
                    raise ValueError('Official source outside selected country scope')
                for raw in source_rows(source, receipt):
                    db.execute(insert,_official_row(receipt,raw))
                    counts[receipt['country']+':'+receipt['dataset']]+=1
            db.commit()
            records=sum(counts.values())
            report={'schema_version':1,'countries':list(countries),'counts':dict(sorted(counts.items())),
                    'total_observations':records,'observations_sha256':observations_digest(db),'official_snapshots':[{'country':r['country'],'dataset':r['dataset'],'sha256':r['sha256'],'source_date':r['source_date']} for r,_ in validated],
                    'source_identifiers_separate':True,'postal_existence_verified':False,
                    'national_address_completeness_verified':False,'deliverability_verified':False,
                    'description':'source-qualified observations, not distinct current addresses or legal administrative verification'}
            db.execute('INSERT INTO metadata VALUES (?,?)',('report',canonical(report)))
            db.commit()
            if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':
                raise ValueError('SQLite consistency failed')
        finally:db.close()
        if out.exists() or out.is_symlink():raise ValueError('Publication target appeared')
        os.link(stage,out)
        stage.unlink()
    return report


def _ro_db(path):
    path=Path(path).resolve()
    if not path.is_file(): raise ValueError('Index missing')
    return sqlite3.connect('file:'+path.as_posix()+'?mode=ro',uri=True)


def verify(dbpath):
    db=_ro_db(dbpath)
    try:
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Invalid SQLite')
        report=json.loads(db.execute('SELECT value FROM metadata WHERE key="report"').fetchone()[0])
        if report['countries']!=list(COUNTRIES) and not set(report['countries']).issubset(COUNTRIES):
            raise ValueError('Unknown report scope')
        actual=dict(db.execute('SELECT country||":"||source_key, count(*) FROM observations GROUP BY country,source_key'))
        if actual!=report['counts'] or sum(actual.values())!=report['total_observations']:
            raise ValueError('Index count mismatch')
        if observations_digest(db)!=report.get('observations_sha256'):
            raise ValueError('Indexed row digest differs from accepted evidence')
        if any(report.get(k) is not False for k in ('postal_existence_verified','national_address_completeness_verified','deliverability_verified')):
            raise ValueError('Unsupported assurance claim')
        return {'status':'PASS','counts':actual,'total_observations':sum(actual.values()),'delivery_verified':False}
    finally:db.close()


def search(dbpath,country,phrase='',kind=None,postcode=None,limit=20):
    if country not in COUNTRIES or type(limit) is not int or not 1<=limit<=200 or kind not in (None,)+KINDS:
        raise ValueError('Invalid query')
    db=_ro_db(dbpath)
    try:
        sql='SELECT source_ref,country,source_key,kind,name,street,house_number,postcode,postcode_syntax,locality,municipality_code,parent_ref,status,language,x,y,crs,confidence FROM observations WHERE country=?'
        args=[country]
        if kind: sql+=' AND kind=?';args.append(kind)
        if postcode is not None: sql+=' AND postcode=?';args.append(postcode)
        if phrase: sql+=" AND (name LIKE ? ESCAPE '\\' OR street LIKE ? ESCAPE '\\' OR locality LIKE ? ESCAPE '\\')";args.extend('%'+phrase.replace('%','\\%').replace('_','\\_')+'%' for _ in range(3))
        sql+=' ORDER BY source_ref LIMIT ?';args.append(limit)
        columns=[d[0] for d in db.execute(sql,args).description]
        rows=[dict(zip(columns,row)) for row in db.execute(sql,args)]
        return {'country':country,'results':rows,'postal_existence_verified':False,'deliverability_verified':False}
    finally:db.close()


def cli():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    s=sub.add_parser('postcode');s.add_argument('--country',choices=COUNTRIES,required=True);s.add_argument('--value',required=True)
    s=sub.add_parser('build');s.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[1]);s.add_argument('--countries',nargs='+',choices=COUNTRIES,default=list(COUNTRIES));s.add_argument('--receipt',type=Path,action='append',default=[]);s.add_argument('--source-root',type=Path);s.add_argument('--output',type=Path,required=True)
    s=sub.add_parser('verify');s.add_argument('--db',type=Path,required=True)
    s=sub.add_parser('search');s.add_argument('--db',type=Path,required=True);s.add_argument('--country',choices=COUNTRIES,required=True);s.add_argument('--text',default='');s.add_argument('--kind',choices=KINDS);s.add_argument('--postcode');s.add_argument('--limit',type=int,default=20)
    a=p.parse_args()
    if a.command=='postcode':result=raw_postcode(a.country,a.value)
    elif a.command=='build':result=build(a.repo,a.output,a.countries,a.receipt,a.source_root)
    elif a.command=='verify':result=verify(a.db)
    else:result=search(a.db,a.country,a.text,a.kind,a.postcode,a.limit)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    cli()
