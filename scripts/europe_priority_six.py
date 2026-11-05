#!/usr/bin/env python3
"""Source-qualified official locality/address intake for IT, RS, BG, RO, GR, HU.

No source observation certifies residential existence, postal correctness, or deliverability.
All official-source imports require explicit rights review, source hashes, and column mapping.
"""
from __future__ import annotations

import argparse
import csv
from collections import Counter
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unicodedata
from urllib.parse import urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'registries/europe/priority-six'
CATALOG = REGISTRY / 'sources.json'
RO_CSV = REGISTRY / 'data/RO/siruta_s1_2026_normalized.csv'
COUNTRIES = ('IT', 'RS', 'BG', 'RO', 'GR', 'HU')
KINDS = ('admin', 'locality', 'street', 'address')
FORMATS = ('csv', 'zip_csv', 'json_array', 'zip_json_array', 'gpkg')
FIELDS = frozenset(('id', 'name', 'parent_id', 'street_id', 'street', 'house_number',
                    'postcode', 'latitude', 'longitude', 'status', 'municipality_id', 'region_id'))
RO_BLOB_SHA = '508d9477e575ff2bdaa6a2351241e7c3522cd096'
RO_FIELDS = ('siruta','nume','cod_postal','judet_cod_numeric','siruta_parinte','tip',
             'nivel','mediu','regiune','fsj','nuts','lau')
RO_EXPECTED = {'county': 42, 'uat': 3187, 'locality': 13749, 'total':16978}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1<<20),b''):
            h.update(chunk)
    return h.hexdigest()


def verified_path(root, relative):
    root = Path(root).resolve()
    p = Path(relative)
    if p == Path('.') or p.is_absolute() or '..' in p.parts:
        raise ValueError('Unsafe source path')
    target = (root / p).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise ValueError('Missing source or symlink escape')
    return target


def load_catalog(path=CATALOG):
    j = json.loads(Path(path).read_text(encoding='utf-8'))
    if j.get('schema_version')!=1 or set(j.get('countries', {}))!=set(COUNTRIES):
        raise ValueError('Unexpected six-country catalog')
    for code,v in j['countries'].items():
        if v.get('national_address_completeness_verified') is not False or v.get('deliverability_verified') is not False:
            raise ValueError('Illegal completion assertion: ' + code)
        if not v.get('official_source_url','').startswith('https://'):
            raise ValueError('Missing authoritative source URL: '+code)
    return j


def audit_geonames(code):
    if code not in COUNTRIES: raise ValueError('Country out of scope')
    folder = ROOT / 'registries/europe/countries' / code
    meta = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
    if meta['country']['country'] != code: raise ValueError('Country metadata differs')
    seen = set(); counts=Counter()
    for name,pin in sorted(meta['files'].items()):
        p = verified_path(folder,name)
        if p.stat().st_size != pin['bytes'] or file_hash(p) != pin['sha256']:
            raise ValueError('GeoNames part differs: '+name)
        uncompressed=hashlib.sha256()
        with gzip.open(p,'rb') as stream:
            # Hash original decompressed bytes while reading exact rows.
            content=stream.read()
        uncompressed.update(content)
        if uncompressed.hexdigest() != pin['uncompressed_sha256']:
            raise ValueError('GeoNames decoded bytes differ: '+name)
        reader=csv.DictReader(io.StringIO(content.decode('utf-8'), newline=''))
        if not reader.fieldnames or not {'id','country_code','kind'} <= set(reader.fieldnames):
            raise ValueError('GeoNames schema differs')
        this_count=0
        for row in reader:
            if row['country_code'] != code or not row['id'].startswith('gn:'):
                raise ValueError('Cross-country or invalid GeoNames ID')
            if row['id'] in seen: raise ValueError('Duplicate GeoNames ID')
            seen.add(row['id']); counts[row['kind']]+=1;this_count+=1
        if this_count != pin['rows']: raise ValueError('GeoNames part rows differ')
    expected = sum(v['rows'] for v in meta['files'].values())
    if len(seen)!=expected: raise ValueError('GeoNames total rows differ')
    return {'country':code,'geonames_rows':len(seen),'by_kind':dict(counts),
            'geo_source_verified':True,'official_currentness_verified':False,
            'address_existence_verified':False, 'deliverability_verified':False}


def audit_ro(path=RO_CSV, strict=True):
    """Verify full 2026 Romanian SIRUTA data and its one-to-many hierarchy.

    Dataset derived by romania/siruta from INS SIRUTA S1 2026 (CC BY 4.0).
    Root county parent '1' is a source root marker, not a missing municipality.
    """
    path = Path(path)
    raw = path.read_bytes()
    git_blob = hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\x00'+raw).hexdigest()
    if strict and git_blob!=RO_BLOB_SHA:
        raise ValueError('Romanian official-source-derived snapshot differs from pinned Git blob')
    try: rendered=raw.decode('utf-8')
    except UnicodeDecodeError as exc: raise ValueError('Romanian source must be UTF-8') from exc
    reader=csv.DictReader(io.StringIO(rendered,newline=''))
    if tuple(reader.fieldnames or []) != RO_FIELDS: raise ValueError('SIRUTA CSV columns differ')
    by_id={};counts=Counter()
    for row in reader:
        if None in row or any(v is None for v in row.values()): raise ValueError('Malformed SIRUTA CSV')
        identity=row['siruta']
        if not re.fullmatch(r'[0-9]+',identity) or identity in by_id:
            raise ValueError('Duplicate/invalid SIRUTA ID')
        if not row['nume'].strip() or row['nivel'] not in ('1','2','3'):
            raise ValueError('Missing label / invalid level')
        by_id[identity]=row
        if row['nivel']=='1':counts['county']+=1
        elif row['nivel']=='2' or row['tip']=='6':counts['uat']+=1
        else:counts['locality']+=1
    counts['total']=len(by_id)
    for identity,row in by_id.items():
        par=row['siruta_parinte']
        if row['nivel']=='1' and par=='1':continue
        if par not in by_id or par==identity:
            raise ValueError('Missing/self Romanian parent for ' +identity)
    if strict and dict(counts)!=RO_EXPECTED:
        raise ValueError('Unexpected SIRUTA totals / subtype classification')
    return {'country':'RO','source':'INS SIRUTA S1 2026 via romania/siruta derived data',
            'rows':len(by_id),'classification':dict(counts),'sha256':hashlib.sha256(raw).hexdigest(),
            'git_blob_sha1':git_blob,'source_identity_replay':'PASS',
            'current_2026_hierarchy_verified_from_source':True,
            'postal_existence_verified':False,'street_number_verified':False,
            'deliverability_verified':False}


def validated_pin(pin, root):
    if pin.get('schema_version')!=1 or pin.get('country') not in COUNTRIES:
        raise ValueError('Invalid country/source pin schema')
    if pin.get('kind') not in KINDS or pin.get('format') not in FORMATS:
        raise ValueError('Unrecognized source kind or format')
    if pin.get('rights_reviewed') is not True or not pin.get('license_name'):
        raise ValueError('Explicit rights review and license needed')
    if pin.get('source') is None or pin.get('source_version') is None or pin.get('downloaded_at') is None:
        raise ValueError('Provenance fields required')
    uri=urlsplit(pin.get('official_url',''))
    if uri.scheme!='https' or not uri.hostname or uri.username or uri.password:
        raise ValueError('Official source URL must be HTTPS')
    if type(pin.get('bytes')) is not int or not 0 < pin['bytes'] <= 5_000_000_000:
        raise ValueError('Invalid source size')
    if not re.fullmatch('[0-9a-f]{64}',pin.get('sha256','')):
        raise ValueError('Invalid SHA-256 source checksum')
    fields=pin.get('fields')
    if not isinstance(fields,dict) or 'id' not in fields or not set(fields)<=FIELDS:
        raise ValueError('Explicit identity field mapping required')
    if pin['kind'] in ('admin','locality','street') and 'name' not in fields:
        raise ValueError('Named records must provide name field mapping')
    if pin['kind']=='address' and 'house_number' not in fields:
        raise ValueError('Address records must preserve house number')
    if any(not isinstance(v,str) or not v for v in fields.values()):
        raise ValueError('Invalid field mapping')
    if pin.get('coordinate_crs') not in ('not_provided','EPSG:4326','EPSG:4258'):
        raise ValueError('Unsupported CRS: explicitly transform other CRS upstream')
    if pin.get('format') in ('zip_csv','zip_json_array') and not pin.get('member'):
        raise ValueError('Zip source member name required')
    if pin['format']=='gpkg' and not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',pin.get('table','')):
        raise ValueError('Explicit GeoPackage table required')
    path=verified_path(root,pin['filename'])
    if path.stat().st_size != pin['bytes'] or file_hash(path)!=pin['sha256']:
        raise ValueError('Source byte pin does not match')
    return path


def _csv_rows(handle,pin):
    enc=pin.get('encoding','utf-8-sig')
    if enc not in ('utf-8','utf-8-sig','cp1250','cp1251','cp1252','iso-8859-1','iso-8859-7'):
        raise ValueError('Source encoding not approved')
    sep=pin.get('delimiter',',')
    if sep not in (',',';','\t','|'):
        raise ValueError('Source separator not approved')
    with io.TextIOWrapper(handle,encoding=enc,newline='') as stream:
        reader=csv.DictReader(stream,delimiter=sep)
        if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames):
            raise ValueError('Duplicate/empty CSV header')
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('Malformed source CSV row')
            yield row


def _zip_member(z,pin):
    names=z.namelist()
    if len(names)!=len(set(names)):
        raise ValueError('Duplicate ZIP entries')
    member=pin['member']
    if member not in names or Path(member).is_absolute() or '..' in Path(member).parts:
        raise ValueError('Unsafe/missing ZIP member')
    zi=z.getinfo(member)
    if zi.file_size > 1_500_000_000 or zi.file_size > max(zi.compress_size,1)*400:
        raise ValueError('ZIP decompression size exceeded')
    return z.open(zi)


def _json_rows(raw,pin):
    obj=json.loads(raw.decode('utf-8'))
    for step in pin.get('records_path',[]):
        if not isinstance(obj,dict) or step not in obj:
            raise ValueError('JSON source record path differs')
        obj=obj[step]
    if not isinstance(obj,list):raise ValueError('Source records must be a JSON array')
    for row in obj:
        if not isinstance(row,dict):raise ValueError('Source row not an object')
        yield row


def iter_source(path,pin):
    fmt=pin['format']
    if fmt=='csv':
        with path.open('rb') as raw:yield from _csv_rows(raw,pin)
    elif fmt=='zip_csv':
        with zipfile.ZipFile(path) as z:
            with _zip_member(z,pin) as raw:yield from _csv_rows(raw,pin)
    elif fmt=='json_array':
        yield from _json_rows(path.read_bytes(),pin)
    elif fmt=='zip_json_array':
        with zipfile.ZipFile(path) as z:
            with _zip_member(z,pin) as raw:yield from _json_rows(raw.read(),pin)
    else:
        table=pin['table']
        db=sqlite3.connect('file:'+path.as_uri().removeprefix('file:')+'?mode=ro',uri=True)
        try:
            if db.execute("select count(*) from sqlite_master where type='table' and name=?",(table,)).fetchone()[0]!=1:
                raise ValueError('Requested GeoPackage table not found')
            cur=db.execute('SELECT * FROM "'+table+'"')
            col=[x[0] for x in cur.description]
            for row in cur:
                yield dict(zip(col,row))
        finally:db.close()


def _str(value):
    return '' if value is None else str(value)


def project(pin,row,ordinal):
    fields=pin['fields']
    missing=set(fields.values())-set(row)
    if missing:raise ValueError('Source schema changed: missing '+','.join(sorted(missing)))
    data={dest:_str(row[src]).strip() for dest,src in fields.items()}
    identity=data['id']
    if not identity:raise ValueError('Blank source identifier at row '+str(ordinal))
    if data.get('name','')=='' and pin['kind'] in ('admin','locality','street'):
        raise ValueError('Blank name for named feature')
    if not data.get('house_number','') and pin['kind']=='address':
        raise ValueError('Blank house number for address candidate')
    country=pin['country']; kind=pin['kind']
    if pin.get('source') == 'ins-siruta-s1-2026':
        kind = 'admin' if (row['nivel'] != '3' or row['tip'] == '6') else 'locality'
    status=data.get('status') or 'unspecified'
    for field in ('latitude','longitude'):
        if data.get(field):
            try:value=float(data[field])
            except ValueError as e:raise ValueError('Invalid geographic number') from e
            if not -180<=value<=180:raise ValueError('Unbounded coordinate')
    if data.get('latitude') and not -90<=float(data['latitude'])<=90:
        raise ValueError('Invalid latitude')
    if bool(data.get('latitude'))!=bool(data.get('longitude')):
        raise ValueError('Partial coordinate pair')
    postal=data.get('postcode','')
    if country=='RO' and postal=='0':postal=''
    # Postcode is an unchanged source observation, NOT proven to be assigned/deliverable.
    return (country,kind,pin['source']+':'+identity,identity,data.get('name',''),
            data.get('parent_id',''),data.get('municipality_id',''),data.get('region_id',''),
            data.get('street_id',''),data.get('street',''),data.get('house_number',''),
            postal,status,data.get('latitude',''),data.get('longitude',''),
            pin['sha256'],ordinal,unicodedata.normalize('NFKC',data.get('name','')).casefold())


def schema(db):
    db.executescript('''
      CREATE TABLE features (
        country TEXT NOT NULL, kind TEXT NOT NULL, ref TEXT NOT NULL PRIMARY KEY,
        source_id TEXT NOT NULL, name TEXT NOT NULL, parent_id TEXT NOT NULL,
        municipality_id TEXT NOT NULL, region_id TEXT NOT NULL, street_id TEXT NOT NULL,
        street TEXT NOT NULL, house_number TEXT NOT NULL, postcode TEXT NOT NULL,
        source_status TEXT NOT NULL, latitude TEXT NOT NULL, longitude TEXT NOT NULL,
        source_sha256 TEXT NOT NULL, source_line INTEGER NOT NULL, search_fold TEXT NOT NULL
      );
      CREATE INDEX ix_source_name ON features(country,kind,name);
      CREATE INDEX ix_source_postcode ON features(country,kind,postcode);
      CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    ''')


def index_official(pin,root,output):
    path=validated_pin(pin,root)
    output=Path(output).absolute()
    if output.exists() or output.is_symlink():raise ValueError('Do not overwrite output')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.six-registries-',dir=output.parent) as temp:
        staged=Path(temp)/'index.sqlite'
        db=sqlite3.connect(staged)
        counts=Counter()
        try:
            schema(db)
            for ordinal,row in enumerate(iter_source(path,pin),1):
                projected=project(pin,row,ordinal)
                try:
                    db.execute('INSERT INTO features VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',projected)
                except sqlite3.IntegrityError as e:
                    raise ValueError('Duplicate source ID') from e
                counts[projected[1]]+=1
                if ordinal%10000==0:db.commit()
            report={'schema_version':1,'country':pin['country'],'source':pin['source'],
                    'source_file_sha256':pin['sha256'],'records':sum(counts.values()),
                    'kind_counts':dict(counts),'rights_reviewed':True,
                    'national_completeness_verified':False,'address_existence_verified':False,
                    'postal_existence_verified':False,'deliverability_verified':False,
                    'unverified_parent_refs':True,'status':'SOURCE_OBSERVATIONS_INDEXED'}
            db.execute('INSERT INTO metadata VALUES (?,?)',('report',canonical(report)))
            db.commit()
            if db.execute('pragma integrity_check').fetchone()[0]!='ok':
                raise ValueError('SQLite index integrity failed')
        finally:db.close()
        if output.exists() or output.is_symlink():raise ValueError('Output appeared during build')
        os.link(staged,output)
    return report


def index_ro(output,source=RO_CSV):
    receipt=audit_ro(source)
    raw=Path(source)
    pin={'schema_version':1,'country':'RO','kind':'locality','format':'csv',
         'rights_reviewed':True,'license_name':'CC-BY-4.0',
         'official_url':'https://data.gov.ro/dataset/721c9059-5f87-4c79-9854-a1d5c18f58d5',
         'source':'ins-siruta-s1-2026','source_version':'2026',
         'downloaded_at':'2026-10-19T00:07:07.548Z','bytes':raw.stat().st_size,
         'sha256':receipt['sha256'],'filename':raw.name,'coordinate_crs':'not_provided',
         'fields':{'id':'siruta','name':'nume','parent_id':'siruta_parinte','postcode':'cod_postal'}}
    result=index_official(pin,raw.parent,output)
    # SIRUTA counties/UAT and settlements are distinguished by source level and type.
    return {**result,'siruta_hierarchy_audit':receipt['classification'],
            'kinds_not_implied_by_index':'Mixed 42 counties / 3187 UAT / 13749 localities'}


def query(dbpath,text,limit=20):
    if not 1 <= limit <= 100:raise ValueError('Invalid result limit')
    db=sqlite3.connect('file:'+Path(dbpath).resolve().as_posix()+'?mode=ro',uri=True)
    try:
        cols=[v[1] for v in db.execute('pragma table_info(features)')]
        sql='SELECT * FROM features WHERE search_fold LIKE ? ESCAPE "\\" ORDER BY source_id LIMIT ?'
        token=unicodedata.normalize('NFKC',text).casefold().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        rows=[dict(zip(cols,r)) for r in db.execute(sql,('%'+token+'%',limit))]
        return {'results':rows,'postal_existence_verified':False,'deliverability_verified':False}
    finally:db.close()


def cli():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('inventory')
    a=sub.add_parser('audit-geonames');a.add_argument('--country',choices=COUNTRIES+('all',),default='all')
    a=sub.add_parser('audit-ro');a.add_argument('--source',type=Path,default=RO_CSV)
    a=sub.add_parser('ingest-ro');a.add_argument('--output',type=Path,required=True);a.add_argument('--source',type=Path,default=RO_CSV)
    a=sub.add_parser('ingest');a.add_argument('--pin',type=Path,required=True);a.add_argument('--source-root',type=Path,required=True);a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('search');a.add_argument('--db',type=Path,required=True);a.add_argument('--text',required=True);a.add_argument('--limit',type=int,default=20)
    args=p.parse_args()
    if args.command=='inventory': result=load_catalog()
    elif args.command=='audit-geonames':
        result=[audit_geonames(c) for c in (COUNTRIES if args.country=='all' else (args.country,))]
    elif args.command=='audit-ro': result=audit_ro(args.source)
    elif args.command=='ingest-ro':result=index_ro(args.output,args.source)
    elif args.command=='ingest':result=index_official(json.loads(args.pin.read_text()),args.source_root,args.output)
    else:result=query(args.db,args.text,args.limit)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:cli()
    except (OSError,ValueError,KeyError,sqlite3.Error,zipfile.BadZipFile) as exc: sys.exit(str(exc))
