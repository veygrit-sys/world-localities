#!/usr/bin/env python3
"""Audit and query source-separated locality/official-address evidence for 11 countries.

Existing GeoNames records are candidate gazetteer observations, *not* deliverable
addresses. A source row and a postal-pattern match cannot certify last-mile delivery.
Python 3.11+, standard library only, offline by default.
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
import tempfile
from urllib.parse import urlsplit, quote
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'registries/europe/balkan-11/sources.json'
SCOPE = ('RS', 'BG', 'RO', 'HU', 'AL', 'MK', 'ME', 'BA', 'XK', 'HR', 'SI')
NEW = ('RS', 'BG', 'RO', 'HU', 'AL', 'MK', 'ME', 'BA', 'XK')
CONTINUE = ('HR', 'SI')
KIND = ('admin', 'locality', 'street', 'address')
FORMAT = ('csv', 'csv_gz', 'zip_csv', 'json_array', 'zip_json_array', 'gpkg')
FIELDS = frozenset(('id', 'name', 'parent_id', 'street_id', 'street', 'house_number',
                    'postcode', 'latitude', 'longitude', 'status', 'municipality_id',
                    'region_id', 'country'))
COLUMNS = ('country', 'source_id', 'feature_id', 'kind', 'name', 'name_key', 'aliases',
           'parent_id', 'street_id', 'house_number', 'postcode', 'status', 'lat', 'lon',
           'payload_json')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def load_catalog(path=CATALOG):
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if data.get('schema_version') != 1 or tuple(data.get('priority_codes', [])) != NEW \
            or tuple(data.get('continuation_codes', [])) != CONTINUE or set(data['countries']) != set(SCOPE):
        raise ValueError('Unexpected 11-country scope')
    for c, item in data['countries'].items():
        if not item['official_url'].startswith('https://'):
            raise ValueError('Non-HTTPS source reference: '+c)
        if item.get('country_address_completeness_verified') is not False or item.get('delivery_verified') is not False:
            raise ValueError('Unsupported completeness assertion')
        if item.get('stage') not in ('existing_accepted_source', 'candidate_requires_acquisition',
                                    'candidate_requires_rights_review', 'continue_existing_pr'):
            raise ValueError('Invalid acquisition stage')
    return data


def existing_file(root, filename):
    root = Path(root).resolve()
    name = Path(filename)
    if filename in ('', '.') or name.is_absolute() or '..' in name.parts or name == Path('.'):
        raise ValueError('Unsafe relative source path')
    path = (root / name).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('Missing source or source escapes its root')
    return path


def geonames_rows(country, repository_root=ROOT):
    if country not in SCOPE:
        raise ValueError('Country outside the audited project')
    base = Path(repository_root) / 'registries/europe/countries' / country
    meta = json.loads((base/'metadata.json').read_text(encoding='utf-8'))
    if meta.get('country', {}).get('country') != country:
        raise ValueError('Metadata country differs')
    if not meta.get('files'):
        raise ValueError('Missing GeoNames source partitions')
    counts = Counter()
    seen = set()
    relation = Counter()
    for part, receipt in sorted(meta['files'].items()):
        p = existing_file(base, part)
        if p.stat().st_size != receipt['bytes'] or file_hash(p) != receipt['sha256']:
            raise ValueError('GeoNames source bytes differ: ' + country + '/' + part)
        h = hashlib.sha256()
        part_count = 0
        with gzip.open(p, 'rb') as binary:
            # Text wrapper retains a faithful byte hash of the *decompressed* CSV stream.
            chunks = iter(lambda:binary.read(1 << 20), b'')
            buf = io.BytesIO()
            for b in chunks:
                h.update(b)
                buf.write(b)
            buf.seek(0)
            with io.TextIOWrapper(buf, encoding='utf-8', newline='') as stream:
                reader = csv.DictReader(stream)
                required = {'id', 'country_code', 'kind', 'name', 'parent_id', 'parent_relation', 'feature_code'}
                if not reader.fieldnames or not required <= set(reader.fieldnames):
                    raise ValueError('Unexpected GeoNames columns')
                for row in reader:
                    if None in row or any(v is None for v in row.values()):
                        raise ValueError('Malformed GeoNames row')
                    if row['country_code'] != country or not row['id'].startswith('gn:'):
                        raise ValueError('Cross-country or invalid ID')
                    if row['id'] in seen:
                        raise ValueError('Duplicate GeoNames entity ID')
                    seen.add(row['id'])
                    part_count += 1
                    counts[row['kind']] += 1
                    relation[row['parent_relation']] += 1
                    yield row
        if h.hexdigest() != receipt['uncompressed_sha256'] or part_count != receipt['rows']:
            raise ValueError('GeoNames decoded source differs: ' + country + '/' + part)
    if sum(counts.values()) != sum(f['rows'] for f in meta['files'].values()):
        raise ValueError('GeoNames partition totals differ')
    if meta['counts'].get('admin_rows') != counts['admin_subdivision'] \
            or meta['counts'].get('locality_rows') != counts['locality'] \
            or meta['counts'].get('other_admin_rows') != counts['other_admin_feature']:
        raise ValueError('GeoNames category totals differ')


def audit_geonames(country, repository_root=ROOT):
    counts, parents, total, ids = Counter(), Counter(), 0, set()
    # Deferred parent-reference check: cannot match until all parts have been read.
    pending = []
    for row in geonames_rows(country, repository_root):
        ids.add(row['id'])
        total += 1
        counts[row['kind']] += 1
        parents[row['parent_relation']] += 1
        if row['parent_id'] and row['parent_id'] != 'country:' + country:
            pending.append(row['parent_id'])
    gaps = sorted({p for p in pending if p not in ids})
    if gaps:
        raise ValueError('Unresolved asserted parent identities: ' + ','.join(gaps[:5]))
    return {'country': country, 'source': 'GeoNames', 'records': total,
            'kinds': dict(sorted(counts.items())), 'parent_relation_counts': dict(sorted(parents.items())),
            'byte_hashes_and_row_ids': 'PASS', 'asserted_parents': 'PASS',
            'current_official_hierarchy_verified': False, 'address_existence_verified': False,
            'postal_existence_verified': False, 'deliverability_verified': False}


def audit_ro_existing(repository_root=ROOT):
    import importlib.util
    import sys
    # Existing accepted code remains canonical; no duplication or mutation.
    script = Path(repository_root) / 'scripts/europe_priority_six.py'
    spec = importlib.util.spec_from_file_location('accepted_europe_priority_six', script)
    if spec is None or spec.loader is None:
        raise ValueError('Existing Romanian verifier is missing')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    path = Path(repository_root)/'registries/europe/priority-six/data/RO/siruta_s1_2026_normalized.csv'
    return module.audit_ro(path, strict=True)


def checked_pin(pin, root):
    if pin.get('schema_version') != 1 or pin.get('country') not in SCOPE:
        raise ValueError('Source pin scope differs')
    if pin.get('kind') not in KIND or pin.get('format') not in FORMAT:
        raise ValueError('Source kind or encoding unsupported')
    if pin.get('rights_reviewed') is not True or not pin.get('license') or not pin.get('commercial_reuse_reviewed') is True:
        raise ValueError('Usage and redistribution rights require explicit review')
    uri = urlsplit(pin.get('official_url', ''))
    if uri.scheme != 'https' or not uri.hostname or uri.username or uri.password or uri.port is not None:
        raise ValueError('A verified official source URL is required')
    if not all(pin.get(f) for f in ('source_id', 'source_version', 'acquired_at')):
        raise ValueError('Source id, version, acquisition date required')
    if pin['source_id'] == 'geonames' or ':' in pin['source_id']:
        raise ValueError('Reserved or ambiguous source identity')
    if type(pin.get('bytes')) is not int or not 0 < pin['bytes'] <= 5_000_000_000:
        raise ValueError('Invalid byte count')
    if not re.fullmatch('[0-9a-f]{64}', str(pin.get('sha256', ''))):
        raise ValueError('Invalid source SHA-256')
    mapping = pin.get('fields')
    if not isinstance(mapping, dict) or 'id' not in mapping or not set(mapping) <= FIELDS:
        raise ValueError('Source-identity mapping is required')
    if any(not isinstance(v, str) or not v for v in mapping.values()):
        raise ValueError('Blank or invalid source field mapping')
    if pin['kind'] != 'address' and 'name' not in mapping:
        raise ValueError('Named features require names')
    if pin['kind'] == 'address' and 'house_number' not in mapping:
        raise ValueError('Address source requires house numbers')
    if pin.get('coordinate_crs') not in ('not_provided', 'EPSG:4326', 'EPSG:4258'):
        raise ValueError('Unconverted source coordinate system')
    if pin['format'] in ('zip_csv','zip_json_array') and not pin.get('member'):
        raise ValueError('ZIP member must be fixed')
    if pin['format'] == 'gpkg' and not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*',pin.get('table','')):
        raise ValueError('GeoPackage table must be named')
    path=existing_file(root,pin.get('filename',''))
    if path.stat().st_size != pin['bytes'] or file_hash(path) != pin['sha256']:
        raise ValueError('Source receipt differs from pinned bytes')
    return path


def csv_iter(binary, pin):
    if pin.get('encoding','utf-8-sig') not in ('utf-8','utf-8-sig','cp1250','cp1251','cp1252','iso-8859-7'):
        raise ValueError('Undeclared source encoding')
    if pin.get('delimiter',',') not in (',',';','\t','|'):
        raise ValueError('Unsupported CSV delimiter')
    with io.TextIOWrapper(binary, encoding=pin.get('encoding','utf-8-sig'), newline='') as f:
        reader = csv.DictReader(f,delimiter=pin.get('delimiter',','))
        if not reader.fieldnames or len(reader.fieldnames)!=len(set(reader.fieldnames)):
            raise ValueError('Invalid CSV header')
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('Malformed CSV row')
            yield row


def json_iter(contents, pin):
    data = json.loads(contents.decode('utf-8'))
    for key in pin.get('records_path',[]):
        if not isinstance(data,dict) or key not in data:
            raise ValueError('Unknown JSON object path')
        data = data[key]
    if not isinstance(data,list): raise ValueError('Expected JSON array')
    for row in data:
        if not isinstance(row,dict): raise ValueError('Non-object JSON row')
        yield row


def source_iter(path,pin):
    fmt=pin['format']
    if fmt=='csv':
        with path.open('rb') as f:yield from csv_iter(f,pin)
    elif fmt=='csv_gz':
        with gzip.open(path,'rb') as f:yield from csv_iter(f,pin)
    elif fmt=='json_array':yield from json_iter(path.read_bytes(),pin)
    elif fmt in ('zip_csv','zip_json_array'):
        with zipfile.ZipFile(path) as z:
            names=z.namelist()
            member=pin['member']
            if len(set(names))!=len(names) or member not in names or Path(member).is_absolute() or '..' in Path(member).parts:
                raise ValueError('Unsafe/missing ZIP member')
            info=z.getinfo(member)
            if info.file_size>1_500_000_000 or info.file_size>max(info.compress_size,1)*400:
                raise ValueError('Excessive ZIP expansion')
            with z.open(info) as f:
                if fmt=='zip_csv':yield from csv_iter(f,pin)
                else:yield from json_iter(f.read(),pin)
    else:
        table=pin['table']
        db=sqlite3.connect('file:'+quote(path.resolve().as_posix(),safe='/')+'?mode=ro',uri=True)
        try:
            if db.execute('SELECT count(*) FROM sqlite_master WHERE type="table" AND name=?',(table,)).fetchone()[0]!=1:
                raise ValueError('Missing source table')
            cur=db.execute('SELECT * FROM "'+table+'"')
            columns=[a[0] for a in cur.description]
            for values in cur:yield dict(zip(columns,values))
        finally:db.close()


def project_source(pin, raw):
    mapping=pin['fields']
    if not set(mapping.values())<=set(raw):
        raise ValueError('Source columns changed')
    row={dest:('' if raw[col] is None else str(raw[col]).strip()) for dest,col in mapping.items()}
    identity=row['id']
    if not identity or (pin['kind']!='address' and not row.get('name')) or (pin['kind']=='address' and not row.get('house_number')):
        raise ValueError('Source has empty primary field')
    if 'country' in row and row['country'] and row['country'] != pin['country']:
        raise ValueError('Cross-country official row')
    def coordinate(k,limit):
        if not row.get(k):return None
        try:value=float(row[k])
        except (TypeError,ValueError):raise ValueError('Invalid coordinate') from None
        if not -limit<=value<=limit:raise ValueError('Out-of-range coordinate')
        return value
    return (pin['country'],pin['source_id'],identity,pin['kind'],row.get('name',''),
            row.get('name','').casefold(),'',row.get('parent_id',''),row.get('street_id',''),
            row.get('house_number',''),row.get('postcode',''),row.get('status','unknown'),
            coordinate('latitude',90),coordinate('longitude',180),canonical(row))


def geo_project(country, row):
    kind={'admin_subdivision':'admin','locality':'locality','other_admin_feature':'admin'}.get(row['kind'])
    if kind is None:raise ValueError('Unknown GeoNames classification')
    def number(k,low,high):
        v=row.get(k,'')
        if not v:return None
        value=float(v)
        if not low <= value <= high:raise ValueError('Invalid GeoNames coordinates')
        return value
    name=row['name']
    return (country,'geonames',row['id'],kind,name,name.casefold(),row.get('alternatenames',''),
            row.get('parent_id',''),'', '', '',row.get('parent_relation',''),
            number('latitude',-90,90),number('longitude',-180,180),
            canonical({'feature_code':row['feature_code'],'address_candidate':row.get('address_candidate',''),
                       'state_id':row.get('state_id',''),'name_source':row['name'],
                       'source_modified':row.get('modification_date','')}))


def init_db(db):
    db.executescript('''
      PRAGMA journal_mode=DELETE;
      CREATE TABLE features (
        country TEXT NOT NULL, source_id TEXT NOT NULL, feature_id TEXT NOT NULL,
        kind TEXT NOT NULL, name TEXT NOT NULL, name_key TEXT NOT NULL,
        aliases TEXT NOT NULL, parent_id TEXT NOT NULL, street_id TEXT NOT NULL,
        house_number TEXT NOT NULL, postcode TEXT NOT NULL, status TEXT NOT NULL,
        lat REAL, lon REAL, payload_json TEXT NOT NULL,
        PRIMARY KEY(country,source_id,feature_id)
      ) WITHOUT ROWID;
      CREATE TABLE provenance (source_id TEXT PRIMARY KEY, receipt_json TEXT NOT NULL);
      CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
      CREATE INDEX ix_features_country_kind ON features(country,kind);
      CREATE INDEX ix_features_country_name ON features(country,name_key);
    ''')


def digest_rows(db):
    h=hashlib.sha256()
    for row in db.execute('SELECT * FROM features ORDER BY country,source_id,feature_id'):
        h.update((canonical(row)+'\n').encode('utf-8'))
    return h.hexdigest()


def build(output, root=ROOT, countries=SCOPE, pins=(), data_root=None, include_ro=True):
    catalog=load_catalog(Path(root)/'registries/europe/balkan-11/sources.json')
    if output.exists() or output.is_symlink():raise ValueError('Output already exists')
    output.parent.mkdir(parents=True,exist_ok=True)
    if not set(countries)<=set(SCOPE) or len(countries)!=len(set(countries)):raise ValueError('Invalid country scope')
    receipts=[]
    for pin_path in pins:
        pin=json.loads(Path(pin_path).read_text(encoding='utf-8'))
        checked_pin(pin,data_root or root)
        if pin['country'] not in countries:raise ValueError('Pinned source outside selected scope')
        receipts.append(pin)
    with tempfile.TemporaryDirectory(prefix='.balkan-11-',dir=output.parent) as folder:
        stage=Path(folder)/'index.sqlite'
        db=sqlite3.connect(stage)
        counts=Counter()
        try:
            init_db(db)
            for country in countries:
                n=0
                for raw in geonames_rows(country,root):
                    db.execute('INSERT INTO features VALUES ('+','.join('?'*len(COLUMNS))+')',geo_project(country,raw))
                    n+=1
                    if n%5000==0:db.commit()
                counts[country+':geonames']=n
            if include_ro and 'RO' in countries:
                check=audit_ro_existing(root)
                if check['rows']!=16978:raise ValueError('Romanian verifier differs')
                # Preserve the accepted Romania importer; do not re-implement official IDs here.
                db.execute('INSERT INTO provenance VALUES (?,?)',('RO:ins-siruta-s1-2026',canonical(check)))
                counts['RO:siruta_2026_separately_verified']=check['rows']
            for pin in receipts:
                path=checked_pin(pin,data_root or root)
                srcid=pin['country']+':'+pin['source_id']
                db.execute('INSERT INTO provenance VALUES (?,?)',(srcid,canonical(pin)))
                n=0
                for raw in source_iter(path,pin):
                    try:db.execute('INSERT INTO features VALUES ('+','.join('?'*len(COLUMNS))+')',project_source(pin,raw))
                    except sqlite3.IntegrityError as exc:raise ValueError('Repeated source-qualified identity') from exc
                    n+=1
                    if n%5000==0:db.commit()
                counts[srcid]=n
            db.commit()
            summary={'schema_version':1,'countries':list(countries),'counts':dict(sorted(counts.items())),
                     'indexed_records':db.execute('SELECT COUNT(*) FROM features').fetchone()[0],
                     'source_qualified':True,'national_completeness_verified':False,
                     'postal_existence_verified':False,'deliverability_verified':False,
                     'romania_siruta_is_separate_source':True,
                     'cross_source_identity_joins_automatically_performed':False}
            summary['row_digest']=digest_rows(db)
            db.execute('INSERT INTO metadata VALUES (?,?)',('summary',canonical(summary)))
            db.commit()
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity failed')
        finally:db.close()
        if output.exists() or output.is_symlink():raise ValueError('Output appeared during build')
        os.link(stage,output)
        stage.unlink()
    return summary


def verify_index(path):
    if not Path(path).is_file():raise ValueError('Missing index')
    db=sqlite3.connect('file:'+quote(Path(path).resolve().as_posix(),safe='/')+'?mode=ro',uri=True)
    try:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity failure')
        m=json.loads(db.execute("SELECT value FROM metadata WHERE key='summary'").fetchone()[0])
        if m['indexed_records']!=db.execute('SELECT COUNT(*) FROM features').fetchone()[0]:
            raise ValueError('Source count changed')
        if digest_rows(db)!=m['row_digest']:raise ValueError('Source rows changed')
        return {'status':'PASS','countries':m['countries'],'indexed_records':m['indexed_records'],
                'national_completeness_verified':False,'deliverability_verified':False}
    finally:db.close()


def query_index(path,country,text='',kind=None,limit=20):
    if country not in SCOPE or (kind is not None and kind not in KIND) or not 1<=limit<=100:
        raise ValueError('Invalid query parameters')
    db=sqlite3.connect('file:'+quote(Path(path).resolve().as_posix(),safe='/')+'?mode=ro',uri=True)
    try:
        # Python casefold performs language-safe matching; LIKE/NOCASE in stock SQLite does not.
        sql='SELECT country,source_id,feature_id,kind,name,aliases,parent_id,lat,lon,status FROM features WHERE country=?'
        pars=[country]
        if kind:
            sql+=' AND kind=?';pars.append(kind)
        # Iterate to avoid ASCII-only SQLite Unicode matching surprises.
        out=[]
        for row in db.execute(sql+' ORDER BY source_id,feature_id',pars):
            if text and text.casefold() not in (row[4]+' '+row[5]).casefold():continue
            out.append(dict(zip(('country','source_id','id','kind','name','aliases','parent_id','lat','lon','status'),row)))
            if len(out)>=limit:break
        return {'country':country,'matches':out,'address_existence_verified':False,'deliverability_verified':False}
    finally:db.close()


def cli(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    subs=p.add_subparsers(dest='command',required=True)
    a=subs.add_parser('inventory');a.add_argument('--catalog',type=Path,default=CATALOG)
    a=subs.add_parser('audit');a.add_argument('--country',choices=(*SCOPE,'all'),default='all');a.add_argument('--root',type=Path,default=ROOT)
    a=subs.add_parser('build');a.add_argument('--output',type=Path,required=True);a.add_argument('--country',choices=(*SCOPE,'all'),default='all');a.add_argument('--root',type=Path,default=ROOT);a.add_argument('--pin',type=Path,action='append',default=[]);a.add_argument('--source-root',type=Path);a.add_argument('--skip-ro',action='store_true')
    a=subs.add_parser('verify');a.add_argument('--db',type=Path,required=True)
    a=subs.add_parser('query');a.add_argument('--db',type=Path,required=True);a.add_argument('--country',choices=SCOPE,required=True);a.add_argument('--text',default='');a.add_argument('--kind',choices=KIND);a.add_argument('--limit',type=int,default=20)
    args=p.parse_args(argv)
    if args.command=='inventory':result=load_catalog(args.catalog)
    elif args.command=='audit':
        codes=SCOPE if args.country=='all' else (args.country,)
        result={'countries':[audit_geonames(c,args.root) for c in codes], 'status':'SOURCE_INTEGRITY_PASS',
                'national_completeness_verified':False,'deliverability_verified':False}
        if 'RO' in codes:result['accepted_ro_siruta']=audit_ro_existing(args.root)
    elif args.command=='build':
        codes=SCOPE if args.country=='all' else (args.country,)
        result=build(args.output,args.root,codes,args.pin,args.source_root,not args.skip_ro)
    elif args.command=='verify':result=verify_index(args.db)
    else:result=query_index(args.db,args.country,args.text,args.kind,args.limit)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return result


if __name__=='__main__':
    try:cli()
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error,zipfile.BadZipFile) as exc:
        raise SystemExit(str(exc)) from exc
