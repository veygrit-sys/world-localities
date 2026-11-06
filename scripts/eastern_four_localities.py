#!/usr/bin/env python3
"""Source-qualified East Europe localities and official-code evidence (MD, UA, BY, RU).

GeoNames is a gazetteer, not an authoritative address register. This CLI never
conflates political/territorial claims, address presence, or deliverability.
Python 3.11+, standard library only, offline and immutable by default.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, quote
import re
import sqlite3
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'registries/europe/eastern-four/sources.json'
CODES = ('MD', 'UA', 'BY', 'RU')
FORMATS = ('csv', 'csv_gz', 'zip_csv', 'json_array', 'xlsx', 'zip_xml')
KINDS = ('administrative', 'locality', 'street', 'address_candidate')
FIELDS = frozenset(('id', 'name', 'parent_id', 'kind', 'postcode', 'house_number',
                    'street_id', 'status', 'admin_code', 'country', 'latitude', 'longitude',
                    'date_from', 'date_to'))
COLS = ('country','source_id','feature_id','kind','name','search_key','aliases','parent_id',
        'parent_status','street_id','house_number','postcode','postal_shape','record_status',
        'lat','lon','source_date','payload_json')
ALLOWED_DOMAINS = {
    'MD': ('statistica.gov.md','dataset.gov.md','semantic.gov.md'),
    'UA': ('mininfra.gov.ua','data.gov.ua','stat.gov.ua'),
    'BY': ('belstat.gov.by','pravo.by'),
    'RU': ('nalog.gov.ru','rosstat.gov.ru'),
}
CODE_SCHEMES = ('source-native','CUATM','KATOTTG','SOATO','GAR_OBJECTID','GAR_GUID','OKATO','OKTMO')


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def safe_path(root, name):
    if not isinstance(name,str) or not name or '\\' in name:
        raise ValueError('Invalid source path')
    part=Path(name)
    if part==Path('.') or part.is_absolute() or '..' in part.parts:
        raise ValueError('Unsafe relative source path')
    root=Path(root).resolve()
    result=(root/part).resolve()
    if not result.is_relative_to(root) or not result.is_file():
        raise ValueError('Missing or escaping source file')
    return result


def load_catalog(path=CATALOG):
    cat=json.loads(Path(path).read_text(encoding='utf-8'))
    if cat.get('schema_version')!=1 or tuple(cat.get('scope',[]))!=CODES or set(cat.get('countries',{}))!=set(CODES):
        raise ValueError('Four-country catalog scope differs')
    for country,item in cat['countries'].items():
        if item.get('national_address_completeness_verified') is not False or item.get('deliverability_verified') is not False:
            raise ValueError('Unsupported complete/deliverable claim for '+country)
        for source in item['official_candidates']:
            url=urlsplit(source['url'])
            if url.scheme!='https' or not url.hostname:
                raise ValueError('Official source URL invalid')
            if source.get('downloaded') is not False:
                raise ValueError('Do not claim an unverified official snapshot')
    return cat


def postal_shape(country,value):
    """Syntax only; never confirms assigned or deliverable postal identifiers."""
    if not isinstance(value,str):return False
    patterns={'MD':r'(?:MD-)?\d{4}','UA':r'\d{5}','BY':r'\d{6}','RU':r'\d{6}'}
    return bool(country in patterns and re.fullmatch(patterns[country],value))


def geo_rows(country,root=ROOT):
    if country not in CODES:raise ValueError('Outside eastern-four scope')
    base=Path(root)/'registries/europe/countries'/country
    metadata=json.loads((base/'metadata.json').read_text(encoding='utf-8'))
    if metadata.get('country',{}).get('country')!=country:raise ValueError('Incorrect GeoNames country')
    ids=set(); counts=Counter(); refs=[];rel=Counter()
    for name,pin in sorted(metadata['files'].items()):
        source=safe_path(base,name)
        if source.stat().st_size!=pin['bytes'] or sha256(source)!=pin['sha256']:
            raise ValueError('Original GeoNames bytes changed: '+country+'/'+name)
        contenthash=hashlib.sha256()
        items=0
        with gzip.open(source,'rb') as f:
            with tempfile.TemporaryFile(mode='w+b') as buf:
                for block in iter(lambda:f.read(1024*1024),b''):
                    contenthash.update(block);buf.write(block)
                buf.seek(0)
                with io.TextIOWrapper(buf,encoding='utf-8',newline='') as text:
                    reader=csv.DictReader(text)
                    required={'id','country_code','kind','name','parent_id','parent_relation','latitude','longitude'}
                    if not reader.fieldnames or not required<=set(reader.fieldnames):raise ValueError('GeoNames schema mismatch')
                    for row in reader:
                        if None in row or any(x is None for x in row.values()):raise ValueError('Malformed GeoNames row')
                        gid=row['id']
                        if row['country_code']!=country or not re.fullmatch(r'gn:\d+',gid):
                            raise ValueError('Cross-country/invalid GeoNames identity')
                        if gid in ids:raise ValueError('Duplicate GeoNames ID: '+gid)
                        ids.add(gid)
                        counts[row['kind']]+=1
                        rel[row['parent_relation']]+=1
                        parent=row['parent_id']
                        if parent and parent!='country:'+country:refs.append(parent)
                        items+=1
                        yield row
        if items!=pin['rows'] or contenthash.hexdigest()!=pin['uncompressed_sha256']:
            raise ValueError('Decoded GeoNames rows/hash changed')
    if sum(counts.values())!=sum(p['rows'] for p in metadata['files'].values()):
        raise ValueError('Partition totals differ')
    if any(counts[k]!=metadata['counts'][v] for k,v in [('admin_subdivision','admin_rows'),('locality','locality_rows'),('other_admin_feature','other_admin_rows')]):
        raise ValueError('GeoNames category totals differ')
    missing=set(refs)-ids
    if missing:raise ValueError('Asserted GeoNames parent not in source: '+next(iter(missing)))


def audit_country(country,root=ROOT):
    if country not in CODES:raise ValueError('Country outside scope')
    count=Counter(); relations=Counter(); total=0
    for row in geo_rows(country,root):
        count[row['kind']]+=1;relations[row['parent_relation']]+=1;total+=1
    return {'country':country,'source':'geonames','rows':total,'kinds':dict(sorted(count.items())),
            'parent_relations':dict(sorted(relations.items())), 'source_hashes_ids_and_parent_refs':'PASS',
            'official_country_hierarchy_verified':False,'address_existence_verified':False,
            'postal_existence_verified':False,'deliverability_verified':False}


def domain_ok(code,hostname):
    return any(hostname==base or hostname.endswith('.'+base) for base in ALLOWED_DOMAINS[code])


def validate_id_scheme(scheme,id):
    patterns={'KATOTTG':r'UA\d{17}', 'SOATO':r'\d{10}', 'GAR_OBJECTID':r'\d+',
              'GAR_GUID':r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}',
              'OKATO':r'\d{2,11}', 'OKTMO':r'\d{8,11}', 'CUATM':r'\d{2,10}'}
    if not id or (scheme in patterns and not re.fullmatch(patterns[scheme],id)):
        raise ValueError('Invalid '+scheme+' source identifier')
    return id


def validate_pin(pin,source_root):
    if pin.get('schema_version')!=1 or pin.get('country') not in CODES:
        raise ValueError('Unknown official snapshot country/schema')
    if pin.get('kind') not in KINDS or pin.get('format') not in FORMATS:
        raise ValueError('Unsupported source kind/format')
    if pin.get('rights_reviewed') is not True or pin.get('commercial_reuse_reviewed') is not True or not pin.get('license'):
        raise ValueError('License and commercial reuse review required')
    uri=urlsplit(pin.get('source_url',''))
    if uri.scheme!='https' or not uri.hostname or uri.username or uri.password or uri.port:
        raise ValueError('Official source URL must be HTTPS without credentials')
    if not domain_ok(pin['country'],uri.hostname):
        raise ValueError('Publisher domain is not approved for country')
    for name in ('source_id','snapshot_version','acquired_at'):
        if not isinstance(pin.get(name),str) or not pin[name]:raise ValueError('Missing source identifier/version/date')
    stamp=datetime.fromisoformat(pin['acquired_at'].replace('Z','+00:00'))
    if stamp.utcoffset() is None:raise ValueError('Unzoned acquisition timestamp')
    scheme=pin.get('code_scheme')
    if scheme not in CODE_SCHEMES:raise ValueError('Explicit official source code scheme required')
    if scheme=='KATOTTG' and pin['country']!='UA':raise ValueError('KATOTTG source must be UA')
    if scheme=='CUATM' and pin['country']!='MD':raise ValueError('CUATM source must be MD')
    if scheme=='SOATO' and pin['country']!='BY':raise ValueError('SOATO source must be BY')
    if scheme.startswith(('GAR_','OKATO','OKTMO')) and pin['country']!='RU':raise ValueError('Russian source code mismatch')
    if not isinstance(pin.get('field_map'),dict) or 'id' not in pin['field_map'] or not set(pin['field_map'])<=FIELDS:
        raise ValueError('Explicit source field mapping with ID required')
    if any(not isinstance(v,str) or not v for v in pin['field_map'].values()):
        raise ValueError('Invalid mapped source field')
    if pin['kind']!='address_candidate' and 'name' not in pin['field_map']:
        raise ValueError('Named source has no mapped name')
    if pin['kind']=='address_candidate' and 'house_number' not in pin['field_map']:
        raise ValueError('Address candidates need house-number evidence')
    if pin.get('coordinate_crs') not in ('not_provided','EPSG:4326','EPSG:4258'):
        raise ValueError('Coordinates must be transformed to WGS84/ETRS89 first')
    if pin['format'] in ('zip_csv','zip_xml') and not pin.get('member'):
        raise ValueError('Archive member must be selected explicitly')
    if pin['format']=='zip_xml' and not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]*',pin.get('record_tag','')):
        raise ValueError('XML record tag must be explicit')
    if pin['format']=='xlsx' and (not pin.get('sheet') or type(pin.get('header_row',1)) is not int or pin.get('header_row',1)<1):
        raise ValueError('Spreadsheet sheet and header row required')
    if type(pin.get('bytes')) is not int or not 0<pin['bytes']<=100_000_000_000:
        raise ValueError('Invalid snapshot byte size')
    if not re.fullmatch(r'[a-f0-9]{64}',pin.get('sha256','')):
        raise ValueError('SHA-256 snapshot digest must be pinned')
    source=safe_path(source_root,pin.get('filename',''))
    if source.stat().st_size!=pin['bytes'] or sha256(source)!=pin['sha256']:
        raise ValueError('Source bytes differ from pinned hash/size')
    return source


def csv_rows(handle,pin):
    encoding=pin.get('encoding','utf-8-sig')
    if encoding not in ('utf-8-sig','utf-8','cp1251','cp1252','cp1250'):
        raise ValueError('Undeclared CSV encoding')
    sep=pin.get('delimiter',',')
    if sep not in (',',';','\t','|'):raise ValueError('Unsupported separator')
    with io.TextIOWrapper(handle,encoding=encoding,newline='') as text:
        reader=csv.DictReader(text,delimiter=sep)
        if not reader.fieldnames or not all(reader.fieldnames) or len(set(reader.fieldnames))!=len(reader.fieldnames):
            raise ValueError('Duplicate/missing CSV headers')
        for row in reader:
            if None in row or any(v is None for v in row.values()):raise ValueError('Malformed CSV')
            yield row


def safe_archive_member(z,name):
    if not isinstance(name,str) or not name or '\\' in name or Path(name).is_absolute() or '..' in Path(name).parts:
        raise ValueError('Unsafe archive member')
    if z.namelist().count(name)!=1:raise ValueError('Duplicate/missing archive member')
    info=z.getinfo(name)
    if info.is_dir() or info.file_size>4_000_000_000 or info.file_size>max(info.compress_size,1)*500:
        raise ValueError('Archive member expansion too large')
    return z.open(info)


def json_rows(path,pin):
    obj=json.loads(path.read_text(encoding='utf-8'))
    for key in pin.get('records_path',[]):
        if not isinstance(obj,dict) or key not in obj:raise ValueError('JSON records path missing')
        obj=obj[key]
    if not isinstance(obj,list):raise ValueError('Expected JSON array')
    for r in obj:
        if not isinstance(r,dict):raise ValueError('Invalid JSON row')
        yield r


def xlsx_rows(path,pin):
    """Strict read-only workbook adapter. Needs openpyxl installed for real XLSX files.

    Source codes must be stored as strings: Excel may discard leading zeros
    once an identifier was entered as a numeric cell.
    """
    try:from openpyxl import load_workbook
    except ImportError as e:raise RuntimeError('XLSX support requires openpyxl>=3.1') from e
    book=load_workbook(path,read_only=True,data_only=True)
    try:
        if pin['sheet'] not in book.sheetnames:raise ValueError('XLSX sheet not found')
        sheet=book[pin['sheet']]
        headers=None
        idcolumn=pin['field_map']['id']
        for line,values in enumerate(sheet.iter_rows(),start=1):
            if line<pin.get('header_row',1):continue
            if headers is None:
                headers=[str(cell.value).strip() if cell.value is not None else '' for cell in values]
                if len(set(headers))!=len(headers) or not all(headers):raise ValueError('Duplicate/blank XLSX headers')
                if idcolumn not in headers:raise ValueError('ID column not found in XLSX')
                idindex=headers.index(idcolumn)
                continue
            if not any(c.value is not None for c in values):continue
            if len(values)!=len(headers):raise ValueError('XLSX changed columns')
            if values[idindex].data_type not in ('s','inlineStr','str'):
                raise ValueError('Official identifier is numeric or formula in XLSX (leading zeros at risk)')
            yield {h:('' if c.value is None else str(c.value)) for h,c in zip(headers,values)}
    finally:book.close()


def _xml_forbidden(stream):
    previous=b''
    for block in iter(lambda:stream.read(1024*1024),b''):
        combined=(previous+block).upper()
        if b'<!DOCTYPE' in combined or b'<!ENTITY' in combined:raise ValueError('DTD/entity XML forbidden')
        previous=combined[-16:]


def xml_rows(path,zip_member,pin):
    with zipfile.ZipFile(path) as z:
        with safe_archive_member(z,zip_member) as f:_xml_forbidden(f)
        with safe_archive_member(z,zip_member) as f:
            context=ET.iterparse(f,events=('start','end'))
            root=None
            for event,elem in context:
                if event=='start':
                    if root is None:root=elem
                    continue
                if elem.tag.rsplit('}',1)[-1]==pin['record_tag']:
                    yield dict(elem.attrib)
                    elem.clear()
                    if root is not None:root.clear()


def source_rows(path,pin):
    fmt=pin['format']
    if fmt=='csv':
        with path.open('rb') as stream:yield from csv_rows(stream,pin)
    elif fmt=='csv_gz':
        with gzip.open(path,'rb') as stream:yield from csv_rows(stream,pin)
    elif fmt=='zip_csv':
        with zipfile.ZipFile(path) as z:
            with safe_archive_member(z,pin['member']) as f:yield from csv_rows(f,pin)
    elif fmt=='json_array':yield from json_rows(path,pin)
    elif fmt=='xlsx':yield from xlsx_rows(path,pin)
    else:yield from xml_rows(path,pin['member'],pin)


def number(row,field,bound):
    if not row.get(field):return None
    try:v=float(row[field])
    except ValueError:raise ValueError('Non-numeric coordinate') from None
    if not -bound<=v<=bound:raise ValueError('Coordinate outside EPSG:4326/4258 bounds')
    return v


def official_projection(pin,raw):
    mapping=pin['field_map']
    if not set(mapping.values())<=set(raw):raise ValueError('Official source schema changed')
    vals={key:('' if raw[col] is None else str(raw[col]).strip()) for key,col in mapping.items()}
    ident=validate_id_scheme(pin['code_scheme'],vals['id'])
    if pin['kind']!='address_candidate' and not vals.get('name'):
        raise ValueError('Named official source with empty name')
    if pin['kind']=='address_candidate' and not vals.get('house_number'):
        raise ValueError('Official address candidate missing house number')
    if vals.get('country') and vals['country']!=pin['country']:
        raise ValueError('Official country code differs')
    kind=vals.get('kind') or pin['kind']
    if kind not in KINDS:raise ValueError('Unsupported source-specific feature kind')
    postal=vals.get('postcode','')
    return (pin['country'],pin['source_id'],ident,kind,vals.get('name',''),
            vals.get('name','').casefold(),'',vals.get('parent_id',''),
            'official_source_unlinked',vals.get('street_id',''),vals.get('house_number',''),postal,
            'syntax_valid' if postal and postal_shape(pin['country'],postal) else 'syntax_invalid' if postal else 'not_provided',
            vals.get('status','unspecified'),number(vals,'latitude',90),number(vals,'longitude',180),
            vals.get('date_from',''),canonical(vals))


def geo_projection(code,row):
    def geo_num(k,bound):
        if not row.get(k):return None
        try:v=float(row[k])
        except ValueError:raise ValueError('Invalid GeoNames coordinate') from None
        if not -bound<=v<=bound:raise ValueError('GeoNames coordinate out of range')
        return v
    kind={'locality':'locality','admin_subdivision':'administrative','other_admin_feature':'administrative'}[row['kind']]
    return (code,'geonames',row['id'],kind,row['name'],row['name'].casefold(),
            row.get('alternatenames',''),row['parent_id'],row['parent_relation'],
            '', '', '', 'not_provided',row.get('feature_code',''),geo_num('latitude',90),geo_num('longitude',180),
            row.get('modification_date',''),canonical({'feature_code':row.get('feature_code',''),
                    'state_id':row.get('state_id',''),'source_country_code':row['country_code'],
                    'source_name':row['name'],'source_last_edit':row.get('modification_date','')}))


def initialize(db):
    db.executescript('''
        PRAGMA journal_mode=DELETE;
        CREATE TABLE features (
            country TEXT NOT NULL,source_id TEXT NOT NULL,feature_id TEXT NOT NULL,
            kind TEXT NOT NULL,name TEXT NOT NULL,search_key TEXT NOT NULL,
            aliases TEXT NOT NULL,parent_id TEXT NOT NULL,parent_status TEXT NOT NULL,
            street_id TEXT NOT NULL,house_number TEXT NOT NULL,postcode TEXT NOT NULL,
            postal_shape TEXT NOT NULL,record_status TEXT NOT NULL,
            lat REAL,lon REAL,source_date TEXT NOT NULL,payload_json TEXT NOT NULL,
            PRIMARY KEY(country,source_id,feature_id)
        ) WITHOUT ROWID;
        CREATE TABLE provenance(country TEXT NOT NULL,source_id TEXT NOT NULL,receipt_json TEXT NOT NULL,
                               PRIMARY KEY(country,source_id));
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    ''')


def source_digest(db):
    h=hashlib.sha256()
    for row in db.execute('SELECT * FROM features ORDER BY country,source_id,feature_id'):
        h.update(canonical(row).encode('utf-8')+b'\n')
    return h.hexdigest()


def build(countries,output,root=ROOT,pins=(),source_root=None):
    countries=tuple(countries)
    if not countries or len(set(countries))!=len(countries) or not set(countries)<=set(CODES):
        raise ValueError('Invalid build country scope')
    output=Path(output).absolute()
    if output.exists() or output.is_symlink():raise ValueError('Output already exists')
    source_root=Path(source_root or root)
    catalog=load_catalog(Path(root)/'registries/europe/eastern-four/sources.json')
    pin_docs=[]
    for filename in pins:
        doc=json.loads(Path(filename).read_text(encoding='utf-8'))
        if doc['country'] not in countries:raise ValueError('Pin country not requested')
        path=validate_pin(doc,source_root)
        pin_docs.append((doc,path))
    output.parent.mkdir(parents=True,exist_ok=True)
    reports=[]; counts=Counter()
    with tempfile.TemporaryDirectory(prefix='.eastern-four-',dir=output.parent) as d:
        stage=Path(d)/'index.sqlite'
        db=sqlite3.connect(stage)
        try:
            initialize(db)
            sql='INSERT INTO features VALUES ('+','.join('?'*len(COLS))+')'
            for code in countries:
                report=audit_country(code,root)
                reports.append(report)
                for row in geo_rows(code,root):
                    db.execute(sql,geo_projection(code,row));counts[code+':geonames']+=1
                db.execute('INSERT INTO provenance VALUES (?,?,?)',
                           (code,'geonames',canonical({'existing_metadata':f'registries/europe/countries/{code}/metadata.json',
                            'source_license':'CC-BY-4.0','counts':report,'territorial_assertion':False})))
                db.commit()
            for pin,path in pin_docs:
                source=pin['country']+':'+pin['source_id']
                if source=='geonames' or pin['source_id']=='geonames':raise ValueError('Reserved source ID')
                count=0
                for raw in source_rows(path,pin):
                    try:db.execute(sql,official_projection(pin,raw))
                    except sqlite3.IntegrityError as e:raise ValueError('Duplicate source-qualified official identifier') from e
                    counts[source]+=1;count+=1
                    if count%10000==0:db.commit()
                db.execute('INSERT INTO provenance VALUES (?,?,?)',(pin['country'],pin['source_id'],canonical(pin)))
                db.commit()
            db.execute('CREATE INDEX ix_country_name ON features(country,search_key)')
            db.execute('CREATE INDEX ix_country_kind ON features(country,kind)')
            db.execute('CREATE INDEX ix_country_postcode ON features(country,postcode)')
            summary={'schema_version':1,'scope':list(countries),'indexed_records':sum(counts.values()),
                     'counts':dict(sorted(counts.items())),'geonames_audit':reports,
                     'catalog_name':catalog.get('project'),'source_digest':source_digest(db),
                     'geographic_reconciliation_status':'source_observations_only',
                     'disputed_territory_assignment_verified':False,
                     'national_address_completeness_verified':False,'postal_existence_verified':False,
                     'deliverability_verified':False}
            db.execute('INSERT INTO metadata VALUES (?,?)',('index_report',canonical(summary)))
            db.commit()
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity check failed')
        finally:db.close()
        if output.exists() or output.is_symlink():raise ValueError('Output appeared during import')
        os.link(stage,output);stage.unlink()
    return summary


def read_db(path):
    path=Path(path).resolve()
    if not path.is_file():raise ValueError('SQLite index missing')
    db=sqlite3.connect('file:'+quote(path.as_posix(),safe='/')+'?mode=ro',uri=True)
    try:
        d=db.execute('SELECT value FROM metadata WHERE key="index_report"').fetchone()
        if not d:raise ValueError('Index has no report')
        r=json.loads(d[0])
        if r.get('schema_version')!=1 or not set(r['scope'])<=set(CODES):
            raise ValueError('Unsupported SQLite schema/scope')
        return db,r
    except BaseException:db.close();raise


def verify(path):
    db,report=read_db(path)
    try:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity failure')
        actual={f'{code}:{source}':count for code,source,count in db.execute('SELECT country,source_id,COUNT(*) FROM features GROUP BY country,source_id')}
        if actual!=report['counts'] or sum(actual.values())!=report['indexed_records']:
            raise ValueError('Index counts differ')
        if source_digest(db)!=report['source_digest']:
            raise ValueError('Indexed source observations changed')
        return {'status':'PASS','indexed_records':report['indexed_records'],'scope':report['scope'],
                'country_source_counts':actual,'national_address_completeness_verified':False,
                'deliverability_verified':False}
    finally:db.close()


def query(path,country,text='',kind=None,source=None,limit=20):
    if country not in CODES or type(limit) is not int or not 1<=limit<=100:
        raise ValueError('Invalid query country or limit')
    if kind and kind not in KINDS:raise ValueError('Unsupported kind')
    db,report=read_db(path)
    try:
        sql='SELECT * FROM features WHERE country=?';args=[country]
        if kind:sql+=' AND kind=?';args.append(kind)
        if source:sql+=' AND source_id=?';args.append(source)
        # SQLite LIKE is not Unicode casefolding; stored search keys and input are.
        if text:
            safe=text.casefold().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            sql+=" AND search_key LIKE ? ESCAPE '\\'";args.append('%'+safe+'%')
        sql+=' ORDER BY source_id,feature_id LIMIT ?';args.append(limit)
        rows=[dict(zip(COLS,x)) for x in db.execute(sql,args)]
        for item in rows:
            item['source_fields']=json.loads(item.pop('payload_json'))
        return {'country':country,'matches':rows,'source_qualifiers_preserved':True,
                'national_address_completeness_verified':False,'deliverability_verified':False}
    finally:db.close()


def cli(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='operation',required=True)
    sub.add_parser('inventory')
    a=sub.add_parser('audit');a.add_argument('--country',default='all',choices=['all',*CODES])
    b=sub.add_parser('build');b.add_argument('--country',default='all',choices=['all',*CODES]);b.add_argument('--output',type=Path,required=True)
    b.add_argument('--pin',type=Path,action='append',default=[]);b.add_argument('--source-root',type=Path)
    v=sub.add_parser('verify');v.add_argument('--db',type=Path,required=True)
    q=sub.add_parser('query');q.add_argument('--db',type=Path,required=True);q.add_argument('--country',choices=CODES,required=True)
    q.add_argument('--text',default='');q.add_argument('--kind',choices=KINDS);q.add_argument('--source');q.add_argument('--limit',type=int,default=20)
    c=sub.add_parser('postcode');c.add_argument('--country',choices=CODES,required=True);c.add_argument('--value',required=True)
    args=p.parse_args(argv)
    if args.operation=='inventory':res=load_catalog()
    elif args.operation=='audit':
        codes=CODES if args.country=='all' else (args.country,)
        entries=[audit_country(code) for code in codes]
        res={'countries':entries,'total_source_observations':sum(x['rows'] for x in entries),
             'official_address_rows_added':0,'postal_existence_verified':False,'deliverability_verified':False}
    elif args.operation=='build':
        codes=CODES if args.country=='all' else (args.country,)
        res=build(codes,args.output,pins=args.pin,source_root=args.source_root)
    elif args.operation=='verify':res=verify(args.db)
    elif args.operation=='query':res=query(args.db,args.country,args.text,args.kind,args.source,args.limit)
    else:res={'country':args.country,'input':args.value,'syntax_valid':postal_shape(args.country,args.value),
              'postal_existence_verified':False,'deliverability_verified':False}
    print(json.dumps(res,ensure_ascii=False,indent=2))
    return res


if __name__=='__main__':
    try:cli()
    except (ValueError,RuntimeError,OSError,sqlite3.Error,zipfile.BadZipFile) as e:
        raise SystemExit(str(e))
