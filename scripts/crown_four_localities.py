#!/usr/bin/env python3
"""Four European crown/overseas territory evidence layers: JE, GG, IM, GI.

The module audits existing GeoNames archives, authenticates a small *named*
public-government reference, and optionally builds a source-qualified ODbL
OSM evidence index. It never certifies deliverable addresses or legal borders.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import csv
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
from urllib.request import Request, urlopen
from urllib.parse import quote, urlsplit
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
HOME = ROOT / 'registries/europe/crown-four'
CATALOG = HOME / 'sources.json'
REFERENCE = HOME / 'official-reference.csv'
SCOPE = ('JE', 'GG', 'IM', 'GI')
EXTRACTS = {'guernsey-jersey': 'https://download.geofabrik.de/europe/guernsey-jersey-latest.osm.pbf',
            'isle-of-man': 'https://download.geofabrik.de/europe/isle-of-man-latest.osm.pbf'}
COLUMNS = ('country','source_id','feature_id','kind','name','street','number','postcode',
           'locality','lon','lat','assign_basis','tags_json')
OSM_KEYS = frozenset(('name','name:en','name:fr','name:gv','name:gg','highway','place',
                     'addr:housenumber','addr:street','addr:place','addr:postcode','addr:city',
                     'addr:country','is_in:country_code','ISO3166-1:alpha2','boundary','admin_level'))
NO_ROADS = frozenset(('proposed','construction','abandoned','razed','disused'))


def canon(v):
    return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def safe(root,name):
    if not isinstance(name,str) or not name or name in ('.','..') or '\\' in name:
        raise ValueError('Invalid source filename')
    root=Path(root).resolve();f=Path(name)
    if f.is_absolute() or '..' in f.parts or not (root/f).resolve().is_relative_to(root):
        raise ValueError('Unsafe source filename')
    p=(root/f).resolve()
    if not p.is_file():raise ValueError('Missing source')
    return p


def catalog(path=CATALOG):
    j=json.loads(Path(path).read_text(encoding='utf-8'))
    if j['schema_version']!=1 or j['country_codes']!=list(SCOPE):
        raise ValueError('Scope mismatch')
    if (j['national_address_completeness_verified'] is not False or
            j['delivery_verified'] is not False):raise ValueError('Invalid quality assertion')
    return j


def audit_reference(reference=REFERENCE,catalog_path=CATALOG):
    j=catalog(catalog_path)
    p=Path(reference)
    if sha(p)!=j['official_reference_sha256']:
        raise ValueError('Reference list hash differs')
    with p.open(encoding='utf-8',newline='') as f:
        reader=csv.DictReader(f)
        required=('country','reference_id','kind','name','source_url','status')
        if tuple(reader.fieldnames or ())!=required:raise ValueError('Reference schema mismatch')
        seen=set();cnt=Counter();rows=[]
        for row in reader:
            if None in row or any(value is None for value in row.values()):raise ValueError('Malformed reference')
            country,uid=row['country'],row['reference_id']
            if country not in SCOPE or not uid.startswith('ref:'+country+':') or (country,uid) in seen:
                raise ValueError('Invalid/duplicate source-qualified reference ID')
            if row['kind'] not in ('administrative_name','postal_reference') or not row['name'] or not row['source_url'].startswith('https://'):
                raise ValueError('Invalid evidence reference')
            if row['status']!='official_text_name_no_boundary_or_unique_address_assurance':
                raise ValueError('Reference quality mislabelled')
            seen.add((country,uid));cnt[country]+=1;rows.append(row)
    if dict(cnt)!=j['official_reference_counts']:
        raise ValueError('Official reference counts differ')
    return {'status':'PASS','counts':dict(cnt),'records':len(rows),'source_sha256':sha(p),
            'legal_boundary_verified':False,'complete_address_inventory':False},rows


def geonames(country,root=ROOT):
    if country not in SCOPE:raise ValueError('Country outside scope')
    folder=Path(root)/'registries/europe/countries'/country
    meta=json.loads((folder/'metadata.json').read_text(encoding='utf-8'))
    if meta['country']['country']!=country:raise ValueError('GeoNames country mismatch')
    seen=set();records=[];pending=[];kinds=Counter()
    for file,pin in sorted(meta['files'].items()):
        path=safe(folder,file)
        if path.stat().st_size!=pin['bytes'] or sha(path)!=pin['sha256']:
            raise ValueError('GeoNames compressed bytes differ')
        h=hashlib.sha256();n=0
        with gzip.open(path,'rb') as raw:
            class HashReader(io.RawIOBase):
                def readable(self):return True
                def readinto(self,b):
                    data=raw.read(len(b));h.update(data);b[:len(data)]=data
                    return len(data)
            with io.TextIOWrapper(io.BufferedReader(HashReader()),encoding='utf-8',newline='') as text:
                reader=csv.DictReader(text)
                if not reader.fieldnames or not {'id','country_code','kind','parent_id','name','latitude','longitude'}<=set(reader.fieldnames):
                    raise ValueError('GeoNames schema differs')
                for row in reader:
                    if None in row or any(v is None for v in row.values()):raise ValueError('Malformed GeoNames row')
                    if row['country_code']!=country or not row['id'].startswith('gn:') or row['id'] in seen:
                        raise ValueError('GeoNames cross-country/duplicate source ID')
                    seen.add(row['id']);n+=1;kinds[row['kind']]+=1
                    if row['parent_id'] and row['parent_id']!='country:'+country:
                        pending.append(row['parent_id'])
                    records.append(row)
        if n!=pin['rows'] or h.hexdigest()!=pin['uncompressed_sha256']:
            raise ValueError('GeoNames decompressed source does not match')
    if any(parent not in seen for parent in pending):
        raise ValueError('Asserted GeoNames parent not found')
    if (len(records)!=sum(p['rows'] for p in meta['files'].values()) or
        kinds['admin_subdivision']!=meta['counts']['admin_rows'] or
        kinds['locality']!=meta['counts']['locality_rows'] or
        kinds['other_admin_feature']!=meta['counts']['other_admin_rows']):
        raise ValueError('GeoNames kind totals differ')
    return records


def audit(root=ROOT,reference=REFERENCE,catalog_path=CATALOG):
    result,rows=audit_reference(reference,catalog_path)
    results=[]
    for country in SCOPE:
        r=geonames(country,root)
        results.append({'country':country,'records':len(r),'official_reference_count':sum(x['country']==country for x in rows),
                        'source':'GeoNames','hashes_counts_unique_ids_parents':'PASS',
                        'national_address_completeness_verified':False})
    return {'status':'PASS','countries':results,'geonames_records':sum(r['records'] for r in results),
            'official_text_references':len(rows),'postal_existence_verified':False,
            'national_address_completeness_verified':False,'deliverability_verified':False}


def postcode_shape(code,value):
    if code not in SCOPE or not isinstance(value,str):return False
    t=value.upper().replace(' ','')
    if code=='GI':return t=='GX111AA'
    return bool(re.fullmatch({'JE':r'JE\d{1,2}\d[A-Z]{2}',
                              'GG':r'GY\d{1,2}\d[A-Z]{2}',
                              'IM':r'IM\d{1,2}\d[A-Z]{2}'}[code],t))


def pin_source(slug,path,fixture=False):
    if slug not in EXTRACTS:raise ValueError('Unknown OSM extract')
    path=Path(path)
    if not path.is_file():raise ValueError('Source missing')
    if not (path.name.endswith('.osm.pbf') or (fixture and path.name.endswith('.osm'))):
        raise ValueError('Only full PBF or explicit OSM XML fixture')
    return {'schema_version':1,'source_id':slug,'url':EXTRACTS[slug],
            'path':path.name,'bytes':path.stat().st_size,'sha256':sha(path),
            'retrieved_at':datetime.now(timezone.utc).isoformat(),
            'license':'ODbL-1.0','attribution':'© OpenStreetMap contributors / Geofabrik',
            'fixture':bool(fixture),'legal_boundary_verified':False}


def checked_pin(pin,root):
    slug=pin.get('source_id')
    if (pin.get('schema_version')!=1 or slug not in EXTRACTS or pin.get('url')!=EXTRACTS[slug]
        or pin.get('license')!='ODbL-1.0' or pin.get('attribution')!='© OpenStreetMap contributors / Geofabrik'):
        raise ValueError('Unexpected OSM source/rights metadata')
    if type(pin.get('bytes')) is not int or not 0<pin['bytes']<=1_000_000_000:
        raise ValueError('Invalid size')
    if not re.fullmatch('[0-9a-f]{64}',pin.get('sha256','')):
        raise ValueError('Invalid hash')
    if pin.get('fixture') not in (True,False):raise ValueError('Unknown fixture status')
    p=safe(root,pin['path'])
    if p.name.endswith('.osm') and pin['fixture'] is not True:raise ValueError('XML reserved for fixtures')
    if not (p.name.endswith('.osm.pbf') or p.name.endswith('.osm')):
        raise ValueError('Unsupported OSM format')
    if p.stat().st_size!=pin['bytes'] or sha(p)!=pin['sha256']:
        raise ValueError('Immutable OSM source pin mismatch')
    return p


def download(slug,dest):
    if slug not in EXTRACTS:raise ValueError('Unlisted Geofabrik source')
    dest=Path(dest)
    if not dest.is_dir():raise ValueError('Destination directory must exist')
    target=dest/(slug+'-latest.osm.pbf')
    receipt=dest/(slug+'-source-pin.json')
    if target.exists() or receipt.exists():raise ValueError('Output already exists')
    part=dest/(slug+'-latest.osm.pbf.partial')
    if part.exists():raise ValueError('Stale partial source must be reviewed')
    try:
        req=Request(EXTRACTS[slug],headers={'User-Agent':'Veygrit-Crown-Four-OSM/1.0'})
        with urlopen(req,timeout=120) as r:
            endpoint=urlsplit(r.geturl())
            if (r.status!=200 or endpoint.scheme!='https' or
                not re.fullmatch(r'download(?:-ext[0-9]+)?\.geofabrik\.de',endpoint.hostname or '') or
                endpoint.path!=urlsplit(EXTRACTS[slug]).path):
                raise ValueError('Unexpected Geofabrik download/redirect: HTTP='+str(r.status)+' host='+str(endpoint.hostname)+' path='+endpoint.path)
            n=0
            with part.open('xb') as f:
                for b in iter(lambda:r.read(1024*1024),b''):
                    n+=len(b)
                    if n>1_000_000_000:raise ValueError('Unexpected source size')
                    f.write(b)
        if not n:raise ValueError('Empty source')
        os.link(part,target);part.unlink()
        pin=pin_source(slug,target)
        with receipt.open('x',encoding='utf-8') as f:f.write(json.dumps(pin,ensure_ascii=False,indent=2)+'\n')
        return pin
    finally:
        part.unlink(missing_ok=True)


def osm_objects(path):
    if path.name.endswith('.osm'):
        with path.open('rb') as f:
            raw=f.read()
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
            raise ValueError('Unsafe XML DTD/entity')
        root=ET.fromstring(raw)
        for obj in root:
            if obj.tag not in ('node','way','relation'):continue
            tags={x.attrib['k']:x.attrib.get('v','') for x in obj if x.tag=='tag'}
            yield obj.tag,int(obj.attrib['id']),tags, obj.attrib.get('lon'),obj.attrib.get('lat')
        return
    try:import osmium
    except ImportError as exc:raise RuntimeError('OSM PBF parsing requires osmium==4.2.0') from exc
    output=[]
    class Handler(osmium.SimpleHandler):
        def seen(self,obj,typ):
            tags={t.k:t.v for t in obj.tags}
            loc=obj.location if typ=='node' else None
            lon=loc.lon if loc and loc.valid() else None
            lat=loc.lat if loc and loc.valid() else None
            output.append((typ,obj.id,tags,lon,lat))
        def node(self,obj):self.seen(obj,'node')
        def way(self,obj):self.seen(obj,'way')
        def relation(self,obj):self.seen(obj,'relation')
    # Avoid loading large PBF extracts into memory: visit with callbacks rather
    # than using this iterator for production; see ingest_osm().
    h=Handler();h.apply_file(str(path),locations=False,filters=[osmium.filter.EmptyTagFilter()])
    yield from output


def spatial_candidate(slug,tags,lon,lat):
    declared=tags.get('addr:country') or tags.get('is_in:country_code') or tags.get('ISO3166-1:alpha2')
    if slug=='isle-of-man':
        if declared and declared!='IM':return ('UNRESOLVED','country_tag_conflict')
        return ('IM','osm_extract_region_not_legal_border')
    if declared:
        if declared in ('JE','GG'):
            return (declared,'unverified_osm_country_tag')
        return ('UNRESOLVED','country_tag_conflict')
    try:lon,lat=float(lon),float(lat)
    except (TypeError,ValueError):return ('UNRESOLVED','shared_extract_no_object_country')
    # Boxes only separate Jersey and the Guernsey Bailiwick; neither proves
    # legal membership or address validity. French continental objects may be
    # included in the upstream extract buffer.
    if -2.36 <= lon <= -1.96 and 49.13 <= lat <= 49.32:
        return ('JE','geographic_bbox_candidate_not_legal_border')
    if -2.85 <= lon <= -2.08 and 49.35 <= lat <= 49.82:
        return ('GG','geographic_bbox_candidate_not_legal_border')
    return ('UNRESOLVED','outside_candidate_rectangles')


def project_osm(slug,typ,identifier,tags,lon=None,lat=None):
    if slug not in EXTRACTS or typ not in ('node','way','relation') or int(identifier)<=0:
        raise ValueError('Invalid object identity')
    selected={k:v for k,v in tags.items() if k in OSM_KEYS and isinstance(v,str) and v}
    if not selected:return []
    categories=[]
    if selected.get('addr:housenumber'):categories.append('address_candidate')
    if selected.get('name') and selected.get('highway') not in NO_ROADS and selected.get('highway'):
        categories.append('named_road_segment')
    if selected.get('place') and selected.get('name'):categories.append('named_place')
    if selected.get('boundary')=='administrative' and selected.get('name'):
        categories.append('administrative_label')
    if not categories:return []
    if typ!='node':lon=lat=None
    country,basis=spatial_candidate(slug,selected,lon,lat)
    return [(country,'osm:'+slug,'osm:'+typ+':'+str(identifier),category,
        selected.get('name',''),selected.get('addr:street',''),selected.get('addr:housenumber',''),
        selected.get('addr:postcode',''),selected.get('addr:city',selected.get('addr:place','')),
        float(lon) if lon is not None else None,float(lat) if lat is not None else None,basis,canon(selected))
        for category in categories]


def schema(db):
    db.executescript('''
        PRAGMA journal_mode=DELETE;
        CREATE TABLE features(
          country TEXT NOT NULL,source_id TEXT NOT NULL,feature_id TEXT NOT NULL,
          kind TEXT NOT NULL,name TEXT NOT NULL,street TEXT NOT NULL,number TEXT NOT NULL,
          postcode TEXT NOT NULL,locality TEXT NOT NULL,lon REAL,lat REAL,
          assign_basis TEXT NOT NULL,tags_json TEXT NOT NULL,
          PRIMARY KEY(country,source_id,feature_id,kind)
        ) WITHOUT ROWID;
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE INDEX ix_country_kind ON features(country,kind);
        CREATE INDEX ix_postcode ON features(country,postcode);
    ''')


def rows_digest(db):
    h=hashlib.sha256()
    for row in db.execute('SELECT * FROM features ORDER BY source_id,feature_id,kind'):
        h.update(canon(row).encode('utf-8')+b'\n')
    return h.hexdigest()


def ingest_osm(db,pin,root):
    path=checked_pin(pin,root)
    counts=Counter()
    sql='INSERT INTO features VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)'
    def consume(typ,identity,tags,lon=None,lat=None):
        for row in project_osm(pin['source_id'],typ,identity,tags,lon,lat):
            db.execute(sql,row);counts[row[0]+':'+row[3]]+=1
    if path.name.endswith('.osm'):
        for item in osm_objects(path):consume(*item)
    else:
        try:import osmium
        except ImportError as exc:raise RuntimeError('Install osmium==4.2.0 for full PBF intake') from exc
        class Handler(osmium.SimpleHandler):
            def take(self,obj,typ):
                tags={t.k:t.v for t in obj.tags}
                loc=obj.location if typ=='node' else None
                lon=loc.lon if loc and loc.valid() else None
                lat=loc.lat if loc and loc.valid() else None
                consume(typ,obj.id,tags,lon,lat)
            def node(self,obj):self.take(obj,'node')
            def way(self,obj):self.take(obj,'way')
            def relation(self,obj):self.take(obj,'relation')
        Handler().apply_file(str(path),locations=False,filters=[osmium.filter.EmptyTagFilter()])
    return dict(counts)


def build(output,root=ROOT,reference=REFERENCE,catalog_path=CATALOG,pins=(),source_root=None):
    output=Path(output).absolute()
    if output.exists() or output.is_symlink():raise ValueError('Output already exists')
    source_root=Path(source_root) if source_root else Path(root)
    ref_report,refs=audit_reference(reference,catalog_path)
    out_counts=Counter();pin_reports=[]
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.crown-four-',dir=output.parent) as td:
        staged=Path(td)/'index.sqlite';db=sqlite3.connect(staged)
        try:
            schema(db)
            stmt='INSERT INTO features VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)'
            for cc in SCOPE:
                for row in geonames(cc,root):
                    def coord(field,limit):
                        val=row.get(field,'')
                        if not val:return None
                        v=float(val)
                        if abs(v)>limit:raise ValueError('Invalid GeoNames coordinates')
                        return v
                    kind={'admin_subdivision':'admin','locality':'locality','other_admin_feature':'other_administrative'}[row['kind']]
                    item=(cc,'geonames',row['id'],kind,row['name'],'','','','',
                          coord('longitude',180),coord('latitude',90),row['parent_relation'],
                          canon({'feature_code':row['feature_code'],'parent_id':row['parent_id'],
                                 'alternate_names':row.get('alternatenames',''),'source_modified':row.get('modification_date','')}))
                    db.execute(stmt,item);out_counts[cc+':geonames']+=1
            for ref in refs:
                item=(ref['country'],'official_text',ref['reference_id'],ref['kind'],ref['name'],'','','',
                      '',None,None,'name_or_postal_reference_only',canon({'source_url':ref['source_url'],'status':ref['status']}))
                db.execute(stmt,item);out_counts[ref['country']+':official_text']+=1
            for item in pins:
                p=json.loads(Path(item).read_text(encoding='utf-8'))
                n=ingest_osm(db,p,source_root)
                pin_reports.append({'source_id':p['source_id'],'sha256':p['sha256'],'bytes':p['bytes'],'counts':n,
                                    'license':p['license'],'territorial_membership_verified':False})
                out_counts.update(n)
            report={'status':'SOURCE_EVIDENCE_INDEXED','indexed_records':sum(out_counts.values()),
                    'counts':dict(sorted(out_counts.items())),'official_reference_sha256':ref_report['source_sha256'],
                    'osm_imports':pin_reports,'national_address_completeness_verified':False,
                    'postal_existence_verified':False,'delivery_verified':False,
                    'shared_osm_extract_does_not_prove_country_boundary':True,
                    'digest_sha256':rows_digest(db)}
            db.execute('INSERT INTO metadata VALUES(?,?)',('report',canon(report)))
            db.commit()
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity failure')
        finally:db.close()
        if output.exists() or output.is_symlink():raise ValueError('Target appeared')
        os.link(staged,output)
        staged.unlink()
    return report


def open_db(path):
    path=Path(path).resolve()
    if not path.is_file():raise ValueError('Index missing')
    db=sqlite3.connect('file:'+quote(path.as_posix(),safe='/')+'?mode=ro',uri=True)
    try:
        report=json.loads(db.execute("SELECT value FROM metadata WHERE key='report'").fetchone()[0])
        return db,report
    except Exception:
        db.close();raise


def verify(path):
    db,r=open_db(path)
    try:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Corrupt SQLite')
        if db.execute('SELECT COUNT(*) FROM features').fetchone()[0]!=r['indexed_records']:
            raise ValueError('Index count mismatch')
        if rows_digest(db)!=r['digest_sha256']:raise ValueError('Index content hash mismatch')
        return {'status':'PASS','records':r['indexed_records'],'counts':r['counts'],
                'national_address_completeness_verified':False,'delivery_verified':False}
    finally:db.close()


def query(path,country,text='',kind=None,limit=20):
    if country not in SCOPE+('UNRESOLVED',):raise ValueError('Unknown region')
    if type(limit) is not int or not 1<=limit<=100:raise ValueError('Invalid limit')
    db,r=open_db(path)
    try:
        sql='SELECT country,source_id,feature_id,kind,name,street,number,postcode,locality,lon,lat,assign_basis FROM features WHERE country=?'
        args=[country]
        if kind:
            sql+=' AND kind=?';args.append(kind)
        if text:
            sql+=" AND (name LIKE ? ESCAPE '\\' OR street LIKE ? ESCAPE '\\' OR locality LIKE ? ESCAPE '\\')"
            literal=text.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            args += ['%'+literal+'%']*3
        sql+=' ORDER BY source_id,feature_id,kind LIMIT ?';args.append(limit)
        cols=('country','source_id','feature_id','kind','name','street','number','postcode','locality','lon','lat','assign_basis')
        rows=[dict(zip(cols,x)) for x in db.execute(sql,args)]
        return {'country':country,'matches':rows,'postal_existence_verified':False,'delivery_verified':False}
    finally:db.close()


def cli(args=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('audit')
    a=sub.add_parser('postcode');a.add_argument('--country',choices=SCOPE,required=True);a.add_argument('--value',required=True)
    a=sub.add_parser('download');a.add_argument('--source',choices=EXTRACTS,required=True);a.add_argument('--directory',type=Path,required=True)
    a=sub.add_parser('pin');a.add_argument('--source',choices=EXTRACTS,required=True);a.add_argument('--file',type=Path,required=True);a.add_argument('--out',type=Path,required=True);a.add_argument('--fixture',action='store_true')
    a=sub.add_parser('build');a.add_argument('--output',type=Path,required=True);a.add_argument('--pin',type=Path,action='append',default=[]);a.add_argument('--source-root',type=Path)
    a=sub.add_parser('verify');a.add_argument('--db',type=Path,required=True)
    a=sub.add_parser('query');a.add_argument('--db',type=Path,required=True);a.add_argument('--country',choices=SCOPE+('UNRESOLVED',),required=True);a.add_argument('--text',default='');a.add_argument('--kind');a.add_argument('--limit',type=int,default=20)
    v=p.parse_args(args)
    if v.command=='audit':result=audit()
    elif v.command=='postcode':result={'country':v.country,'input':v.value,'syntax_valid':postcode_shape(v.country,v.value),'existence_verified':v.country=='GI' and postcode_shape(v.country,v.value),'matched_to_any_delivery_address':False}
    elif v.command=='download':result=download(v.source,v.directory)
    elif v.command=='pin':
        result=pin_source(v.source,v.file,v.fixture)
        with v.out.open('x',encoding='utf-8') as f:f.write(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    elif v.command=='build':result=build(v.output,pins=v.pin,source_root=v.source_root)
    elif v.command=='verify':result=verify(v.db)
    else:result=query(v.db,v.country,v.text,v.kind,v.limit)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:cli()
    except (ValueError,OSError,KeyError,sqlite3.Error,RuntimeError) as e:sys.exit(str(e))
