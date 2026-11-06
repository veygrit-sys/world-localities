#!/usr/bin/env python3
"""Source-isolated microstate gazetteer, approved-name and community OSM evidence.

Six sovereign places: AD, LI, MC, SM, VA, MT. Existing official address
registries remain separate: this is not a national postcode or delivery API.
Python 3.11+; standard library except optional pyosmium for PBF build.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'registries/europe/microstates/catalog.json'
CODES = ('AD', 'LI', 'MC', 'SM', 'VA', 'MT')
LICENSE = 'ODbL-1.0'
ATTRIBUTION = '© OpenStreetMap contributors; Geofabrik / OpenStreetMap.fr extract'
FEATURE_KINDS = ('admin', 'locality', 'other_admin', 'official_name', 'postal_reference',
                 'osm_address_candidate', 'osm_named_road_segment', 'osm_named_place', 'osm_admin_label')
SOURCE_NAMES = {'geofabrik': 'https://download.geofabrik.de',
                'osmfr': 'https://download.openstreetmap.fr'}
TAGS = frozenset(('name', 'name:de', 'name:fr', 'name:it', 'name:ca', 'name:mt', 'name:en',
                  'place', 'highway', 'admin_level', 'boundary', 'addr:housenumber',
                  'addr:street', 'addr:place', 'addr:city', 'addr:postcode',
                  'addr:country', 'addr:suburb', 'addr:district'))
PROPOSED = frozenset(('construction', 'proposed', 'abandoned', 'razed', 'disused'))


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def safe_path(root, rel):
    rel = Path(rel)
    if rel.is_absolute() or rel == Path('.') or '..' in rel.parts or '\\' in str(rel):
        raise ValueError('unsafe path')
    root = Path(root).resolve()
    value = (root / rel).resolve()
    if not value.is_relative_to(root) or not value.is_file():
        raise ValueError('missing or escaped source file')
    return value


def load_catalog(path=CATALOG):
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    if doc.get('schema_version') != 1 or tuple(doc.get('countries', {})) != CODES:
        raise ValueError('six-country catalog scope changed')
    if any(doc.get(field) is not False for field in ('national_address_completeness_verified',
                                                     'postcode_existence_verified', 'deliverability_verified')):
        raise ValueError('microstates may not assert certified address coverage')
    for code, item in doc['countries'].items():
        url = urlsplit(item['source'])
        origin = SOURCE_NAMES[item['extract_provider']]
        expected = urlsplit(origin)
        if (url.scheme != 'https' or url.netloc != expected.netloc or url.query or url.fragment
                or not url.path.endswith('-latest.osm.pbf')):
            raise ValueError('non-authorized OSM extract '+code)
        if code == 'SM' and '/san_marino-latest.osm.pbf' != url.path[-len('/san_marino-latest.osm.pbf'):]:
            raise ValueError('San Marino URL changed')
        if code == 'VA' and not url.path.endswith('/vatican_city-latest.osm.pbf'):
            raise ValueError('Vatican URL changed')
        if not item['primary_official_reference'].startswith('https://'):
            raise ValueError('missing named official reference')
        if type(item['official_reference_count']) is not int or item['official_reference_count'] < 0:
            raise ValueError('invalid official-reference count')
    return doc


def official_rows(root=ROOT, manifest=None):
    m = manifest or load_catalog(Path(root) / 'registries/europe/microstates/catalog.json')
    path = safe_path(root, m['official_name_csv'])
    if path.stat().st_size != m['official_reference_bytes'] or sha256(path) != m['official_reference_sha256']:
        raise ValueError('official reference bytes changed')
    with path.open('r', encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        expected = ('country','reference_id','kind','name','source_locator','source_scope','authority_code_verified')
        if tuple(reader.fieldnames or ()) != expected:
            raise ValueError('official name CSV schema changed')
        seen = set()
        counts = Counter()
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('malformed official name row')
            code = row['country']
            if (code not in CODES or not row['reference_id'].startswith(code+':')
                    or not row['name'] or row['authority_code_verified'] != 'false'
                    or row['kind'] != m['countries'][code]['official_reference_kind']):
                raise ValueError('official reference identity / classification changed')
            if row['reference_id'] in seen:
                raise ValueError('duplicate source-qualified name')
            seen.add(row['reference_id'])
            counts[code] += 1
            yield row
        if any(counts[code] != m['countries'][code]['official_reference_count'] for code in CODES):
            raise ValueError('official names do not match expected scope')


def gazetteer_rows(code, root=ROOT, verify=True):
    if code not in CODES:
        raise ValueError('not a sovereign microstate in the catalog')
    base = Path(root) / 'registries/europe/countries' / code
    meta = json.loads((base/'metadata.json').read_text(encoding='utf-8'))
    if meta.get('country', {}).get('country') != code:
        raise ValueError('country metadata mismatch')
    seen, counts = set(), Counter()
    for member, pin in sorted(meta['files'].items()):
        path = safe_path(base, member)
        if path.stat().st_size != pin['bytes'] or sha256(path) != pin['sha256']:
            raise ValueError('GeoNames stored-file hash mismatch: '+code)
        h, n = hashlib.sha256(), 0
        with gzip.open(path, 'rb') as stream:
            with tempfile.SpooledTemporaryFile(max_size=8*1024*1024) as temp:
                for chunk in iter(lambda: stream.read(1<<20), b''):
                    h.update(chunk); temp.write(chunk)
                temp.seek(0)
                reader = csv.DictReader(io.TextIOWrapper(temp, encoding='utf-8', newline=''))
                if not reader.fieldnames or not {'country_code','id','kind','name','parent_id','latitude','longitude'} <= set(reader.fieldnames):
                    raise ValueError('GeoNames header changed')
                for row in reader:
                    if None in row or any(v is None for v in row.values()):
                        raise ValueError('malformed GeoNames row')
                    if row['country_code'] != code or not re.fullmatch(r'gn:[0-9]+', row['id']):
                        raise ValueError('cross-country / invalid GeoNames ID')
                    if row['id'] in seen:
                        raise ValueError('duplicate GeoNames ID')
                    seen.add(row['id'])
                    counts[row['kind']] += 1
                    n += 1
                    yield row
        if n != pin['rows'] or h.hexdigest() != pin['uncompressed_sha256']:
            raise ValueError('GeoNames content/record hash mismatch')
    if sum(counts.values()) != sum(v['rows'] for v in meta['files'].values()):
        raise ValueError('GeoNames partitions incomplete')
    for field, key in [('admin_rows','admin_subdivision'), ('locality_rows','locality'),
                       ('other_admin_rows','other_admin_feature')]:
        if counts[key] != meta['counts'][field]:
            raise ValueError('GeoNames category totals do not match')


def audit_one(code, root=ROOT):
    rows = list(gazetteer_rows(code,root))
    ids = {r['id'] for r in rows}
    parents = {r['parent_id'] for r in rows if r['parent_id'] and r['parent_id'] != 'country:'+code}
    if not parents <= ids:
        raise ValueError('asserted parent ID not present in national extract')
    m = load_catalog(Path(root)/'registries/europe/microstates/catalog.json')
    names = [r for r in official_rows(root, m) if r['country'] == code]
    return {'country':code, 'geonames_observations':len(rows), 'official_name_observations':len(names),
            'geo_source_integrity':'PASS', 'official_reference_integrity':'PASS',
            'no_source_identity_inference':True, 'national_address_completeness_verified':False,
            'postal_existence_verified':False, 'deliverability_verified':False}


def postal_syntax(code, text):
    if code not in CODES or not isinstance(text,str):
        return False
    value = text.strip().upper()
    patterns = {'AD':r'AD[0-9]{3}', 'LI':r'[0-9]{4}', 'MC':r'[0-9]{5}',
                'SM':r'478[0-9]{2}', 'VA':r'(?:SCV-)?00120', 'MT':r'[A-Z]{3} ?[0-9]{4}'}
    return bool(re.fullmatch(patterns[code],value))


def check_receipt(pin, code, folder, catalog=None):
    doc = catalog or load_catalog()
    if pin.get('schema_version')!=1 or pin.get('country')!=code or pin.get('source_kind')!='osm-community-extract':
        raise ValueError('receipt schema/country differs')
    if pin.get('source_url') != doc['countries'][code]['source']:
        raise ValueError('source URL not approved for jurisdiction')
    if pin.get('license') != LICENSE or pin.get('attribution') != ATTRIBUTION:
        raise ValueError('ODbL attribution/license required')
    if pin.get('rights_reviewed') is not True or pin.get('fixture') not in (False,None):
        raise ValueError('unreviewed or fixture source')
    try:
        stamp = datetime.fromisoformat(pin['acquired_at'].replace('Z','+00:00'))
        if stamp.tzinfo is None or stamp.utcoffset() is None:
            raise ValueError('acquisition timestamp without timezone')
    except (TypeError, KeyError) as exc:
        raise ValueError('timestamp missing') from exc
    filename = code.lower()+'-microstate.osm.pbf'
    if pin.get('filename') != filename or type(pin.get('bytes')) is not int or not 0 < pin['bytes'] <= 64_000_000:
        raise ValueError('source size/filename mismatch')
    if not re.fullmatch(r'[0-9a-f]{64}', str(pin.get('sha256',''))):
        raise ValueError('invalid hash pin')
    source = safe_path(folder,filename)
    if source.stat().st_size != pin['bytes'] or sha256(source) != pin['sha256']:
        raise ValueError('pinned source bytes mismatch')
    return source


def download(code, root, catalog=None):
    doc = catalog or load_catalog()
    url = doc['countries'][code]['source']
    folder = Path(root).resolve()
    if not folder.is_dir():
        raise ValueError('existing new download directory required')
    destination = folder / (code.lower()+'-microstate.osm.pbf')
    receipt_path = folder / (code.lower()+'-microstate-receipt.json')
    part = destination.with_suffix('.osm.pbf.partial')
    if any(p.exists() or p.is_symlink() for p in (destination,receipt_path,part)):
        raise ValueError('source snapshot exists; use new download directory')
    total, digest = 0, hashlib.sha256()
    try:
        with urlopen(Request(url,headers={'User-Agent':'Veygrit-EuroMicrostates/1.0'}),timeout=100) as stream:
            if stream.status != 200 or stream.geturl() != url:
                raise ValueError('unexpected HTTP download redirect or status')
            with part.open('xb') as output:
                for chunk in iter(lambda:stream.read(1 << 20),b''):
                    total+=len(chunk)
                    if total > 64_000_000:
                        raise ValueError('source exceeded 64 MB safeguard')
                    output.write(chunk);digest.update(chunk)
        if total == 0:
            raise ValueError('empty source')
        os.link(part,destination)
        part.unlink()
        pin={'schema_version':1,'source_kind':'osm-community-extract','country':code,
             'source_url':url,'filename':destination.name,
             'acquired_at':datetime.now(timezone.utc).isoformat(), 'bytes':total,
             'sha256':digest.hexdigest(),'license':LICENSE,'attribution':ATTRIBUTION,
             'rights_reviewed':True,'fixture':False,'national_completeness_verified':False}
        with receipt_path.open('x',encoding='utf-8') as handle:
            json.dump(pin,handle,ensure_ascii=False,indent=2)
            handle.write('\n')
        return pin
    finally:
        part.unlink(missing_ok=True)


def db_create(db):
    db.executescript('''
    PRAGMA journal_mode=DELETE;
    CREATE TABLE records (
      country TEXT NOT NULL, source_id TEXT NOT NULL, record_id TEXT NOT NULL,
      kind TEXT NOT NULL, name TEXT NOT NULL, query_text TEXT NOT NULL,
      parent_id TEXT NOT NULL, street TEXT NOT NULL, number TEXT NOT NULL,
      postcode TEXT NOT NULL, lat REAL, lon REAL, payload_json TEXT NOT NULL,
      PRIMARY KEY(country,source_id,record_id,kind)
    ) WITHOUT ROWID;
    CREATE INDEX idx_search ON records(country,kind,query_text);
    CREATE INDEX idx_postcode ON records(country,postcode);
    CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    ''')


def projected_hash(db):
    h=hashlib.sha256()
    for r in db.execute('SELECT * FROM records ORDER BY country,source_id,record_id,kind'):
        h.update(canonical(r).encode('utf-8')+b'\n')
    return h.hexdigest()


def make_record(code,source,identifier,kind,name='',parent='',street='',number='',postcode='',lat=None,lon=None,payload=None):
    if code not in CODES or kind not in FEATURE_KINDS or not identifier:
        raise ValueError('invalid projection identity')
    if not isinstance(name,str): raise ValueError('invalid feature name')
    if lat is not None and not -90 <= float(lat) <= 90:
        raise ValueError('invalid latitude')
    if lon is not None and not -180 <= float(lon) <= 180:
        raise ValueError('invalid longitude')
    search=' '.join([name,street,parent,number,postcode]).casefold()
    return (code,source,str(identifier),kind,name,search,parent,street,number,postcode,lat,lon,canonical(payload or {}))


def osm_rows(code, kind, identity, tags, lat=None,lon=None):
    if code not in CODES or kind not in ('node','way','relation') or int(identity) <= 0:
        raise ValueError('invalid OSM identity')
    clean={key:value for key,value in tags.items() if key in TAGS and isinstance(value,str) and value}
    coords=(lat,lon) if kind=='node' and lat is not None and lon is not None else (None,None)
    categories=[]
    if clean.get('addr:housenumber'):
        categories.append('osm_address_candidate')
    if clean.get('name') and clean.get('highway') and clean['highway'] not in PROPOSED:
        categories.append('osm_named_road_segment')
    if clean.get('name') and clean.get('place'):
        categories.append('osm_named_place')
    if clean.get('name') and clean.get('boundary')=='administrative':
        categories.append('osm_admin_label')
    for item in categories:
        number=clean.get('addr:housenumber','') if item=='osm_address_candidate' else ''
        postcode=clean.get('addr:postcode','') if item=='osm_address_candidate' else ''
        actual=clean.get('addr:country','').upper()
        payload={'tags':clean,'osm_primitive':kind,'address_tag_country_conflict':bool(actual and actual != code),
                 'postcode_syntax_valid':postal_syntax(code,postcode) if postcode else None,
                 'postcode_existence_verified':False,'no_derived_way_centroid':True}
        yield make_record(code, 'osm-community',f'osm:{kind}:{int(identity)}',item,
                    clean.get('name',''),clean.get('addr:place',''),clean.get('addr:street',''),number,
                    postcode,*coords,payload)


def add_baseline(db, root, only=None):
    codes=tuple(only or CODES)
    counts=Counter()
    add='INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)'
    for code in codes:
        for r in gazetteer_rows(code,root):
            kind={'admin_subdivision':'admin','locality':'locality','other_admin_feature':'other_admin'}[r['kind']]
            def loc(k,maximum):
                if not r.get(k): return None
                val=float(r[k])
                if not -maximum<=val<=maximum: raise ValueError('invalid gazetteer coordinate')
                return val
            row=make_record(code,'geonames',r['id'],kind,r['name'],r.get('parent_id',''),
                            lat=loc('latitude',90),lon=loc('longitude',180),
                            payload={'alt_names':r.get('alternatenames',''), 'feature_code':r.get('feature_code',''),
                                     'parent_relation':r.get('parent_relation',''),'source_modified':r.get('modification_date','')})
            db.execute(add,row);counts[code+':geonames']+=1
    for row in official_rows(root):
        if row['country'] not in codes:continue
        kind='postal_reference' if row['kind']=='postal_reference' else 'official_name'
        rec=make_record(row['country'],'official-names-transcribed',row['reference_id'],kind,row['name'],
                        payload={'original_kind':row['kind'],'source_locator':row['source_locator'],
                                 'authority_code_verified':False,'postcode_existence_verified':False})
        db.execute(add,rec);counts[row['country']+':official-names-transcribed']+=1
    return counts


def append_osm(db, folder, codes, cat=None):
    try: import osmium
    except ImportError as exc: raise RuntimeError('OSM build needs pip install osmium==4.2.0') from exc
    document=cat or load_catalog()
    counts=Counter()
    add='INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)'
    for code in codes:
        receipt=json.loads(safe_path(folder,code.lower()+'-microstate-receipt.json').read_text(encoding='utf-8'))
        source=check_receipt(receipt, code, folder, document)
        class Handler(osmium.SimpleHandler):
            def scan(self,obj,kind):
                ts={x.k:x.v for x in obj.tags}
                point=obj.location if kind=='node' else None
                lat=point.lat if point is not None and point.valid() else None
                lon=point.lon if point is not None and point.valid() else None
                for row in osm_rows(code,kind,obj.id,ts,lat,lon):
                    db.execute(add,row)
                    counts[code+':osm-community']+=1
            def node(self,obj):self.scan(obj,'node')
            def way(self,obj):self.scan(obj,'way')
            def relation(self,obj):self.scan(obj,'relation')
        Handler().apply_file(str(source),locations=False,filters=[osmium.filter.EmptyTagFilter()])
        db.execute('INSERT INTO metadata VALUES(?,?)',('receipt:'+code,canonical(receipt)))
        db.commit()
    return counts


def build(path, root=ROOT, osm_folder=None, codes=CODES):
    path=Path(path).absolute()
    if path.exists() or path.is_symlink():raise ValueError('target exists; never overwrite')
    if not path.parent.is_dir():raise ValueError('output parent must already exist')
    cat=load_catalog(Path(root)/'registries/europe/microstates/catalog.json')
    codes=tuple(codes)
    if not codes or len(codes)!=len(set(codes)) or not set(codes)<=set(CODES):
        raise ValueError('invalid country subset')
    with tempfile.TemporaryDirectory(prefix='.microstate-',dir=path.parent) as temp:
        scratch=Path(temp)/'staging.sqlite'
        db=sqlite3.connect(scratch)
        try:
            db_create(db)
            counts=add_baseline(db,root,codes)
            if osm_folder is not None:counts.update(append_osm(db,osm_folder,codes,cat))
            n=sum(counts.values())
            report={'schema_version':1,'countries':list(codes),'counts':dict(sorted(counts.items())),
                    'records':n,'projected_sha256':projected_hash(db),
                    'official_names_pinned':True,'source_separation':True,
                    'osm_imported':osm_folder is not None,'national_address_completeness_verified':False,
                    'postcode_existence_verified':False,'deliverability_verified':False,
                    'caveat':'OSM labels and house-number tags are observations, not national address certification',
                    'osm_license':LICENSE if osm_folder is not None else None,
                    'osm_attribution':ATTRIBUTION if osm_folder is not None else None}
            db.execute('INSERT INTO metadata VALUES(?,?)',('report',canonical(report)))
            db.commit()
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('database integrity failure')
        finally:db.close()
        if path.exists() or path.is_symlink(): raise ValueError('target was created by another writer')
        os.link(scratch,path)
    return report


def verify(path):
    db=sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro',uri=True)
    try:
        report=json.loads(db.execute("SELECT value FROM metadata WHERE key='report'").fetchone()[0])
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity failed')
        actual=dict(db.execute("SELECT country||':'||source_id, COUNT(*) FROM records GROUP BY country,source_id"))
        if report['counts']!=actual or report['records']!=sum(actual.values()):
            raise ValueError('indexed source counts differ')
        if projected_hash(db)!=report['projected_sha256']:
            raise ValueError('source-projected content hash differs')
        if any(report.get(x) is not False for x in ('national_address_completeness_verified','postcode_existence_verified','deliverability_verified')):
            raise ValueError('unsupported certified-address assertion')
        return {'status':'PASS','countries':report['countries'],'records':report['records'],
                'counts':report['counts'],'national_address_completeness_verified':False,
                'postcode_existence_verified':False,'deliverability_verified':False}
    finally:db.close()


def search(path,code,text='',kind=None,limit=25):
    if code not in CODES or (kind is not None and kind not in FEATURE_KINDS) or not 1<=limit<=100:
        raise ValueError('invalid query')
    db=sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro',uri=True)
    try:
        # Unicode-aware matching is performed in Python rather than SQLite's ASCII-only LIKE.
        needle=text.casefold()
        rows=[]
        cur=db.execute('SELECT country,source_id,record_id,kind,name,parent_id,street,number,postcode,lat,lon,payload_json,query_text FROM records WHERE country=? '+
                       ('AND kind=? ' if kind else '')+'ORDER BY source_id,record_id,kind', (code,kind) if kind else (code,))
        for a in cur:
            if needle and needle not in a[-1]:continue
            rows.append({'country':a[0],'source':a[1],'id':a[2],'kind':a[3],'name':a[4],
                         'parent_id':a[5],'street':a[6],'number':a[7],'postcode':a[8],
                         'lat':a[9],'lon':a[10],'source_fields':json.loads(a[11])})
            if len(rows)>=limit:break
        return {'results':rows,'country':code,'national_address_completeness_verified':False,
                'deliverability_verified':False}
    finally:db.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('inventory')
    a=sub.add_parser('audit');a.add_argument('--country',choices=CODES+('all',),default='all')
    a=sub.add_parser('download');a.add_argument('--country',choices=CODES,required=True);a.add_argument('--directory',type=Path,required=True)
    a=sub.add_parser('build');a.add_argument('--output',type=Path,required=True);a.add_argument('--osm-root',type=Path)
    a=sub.add_parser('verify');a.add_argument('--db',type=Path,required=True)
    a=sub.add_parser('search');a.add_argument('--db',type=Path,required=True);a.add_argument('--country',choices=CODES,required=True)
    a.add_argument('--text',default='');a.add_argument('--kind',choices=FEATURE_KINDS);a.add_argument('--limit',type=int,default=25)
    a=sub.add_parser('postcode');a.add_argument('--country',choices=CODES,required=True);a.add_argument('--value',required=True)
    args=p.parse_args()
    if args.action=='inventory':
        d=load_catalog();out={'countries':d['countries'],'official_reference_rows':len(list(official_rows())),
                              'national_address_completeness_verified':False}
    elif args.action=='audit':
        out={'audits':[audit_one(cc) for cc in (CODES if args.country=='all' else (args.country,))]}
    elif args.action=='download':out=download(args.country,args.directory)
    elif args.action=='build':out=build(args.output,osm_folder=args.osm_root)
    elif args.action=='verify':out=verify(args.db)
    elif args.action=='search':out=search(args.db,args.country,args.text,args.kind,args.limit)
    else:out={'country':args.country,'value':args.value,'syntax_valid':postal_syntax(args.country,args.value),
              'postcode_existence_verified':False,'deliverability_verified':False}
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error,RuntimeError) as error:
        raise SystemExit(str(error)) from None
