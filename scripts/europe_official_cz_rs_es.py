#!/usr/bin/env python3
"""Actual-source CZ/RS/ES official-address acquisition and evidence ingestion.

Non-interchangeable providers:
 * CZ: nationwide ČÚZK monthly RÚIAN CSV/ZIP; preserve native S-JTSK.
 * RS: RGZ address register street and house-number CSV; require source schema review.
 * ES: CNIG CartoCiudad province GPKG ZIP (52 provinces); each province is distinct.

This is immutable evidence, not a guarantee of universal address completeness,
correct postal assignments, property rights, or successful carrier delivery.
Requires Python 3.11; standard library only.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time
from urllib import parse, request
import xml.etree.ElementTree as ET
import zipfile

CZ_ATOM = 'https://atom.cuzk.gov.cz/RUIAN-CSV-ADR-ST/RUIAN-CSV-ADR-ST.xml'
RS_DOWNLOADS = {
    'streets': 'https://download.geosrbija.rs/download-api/opendata-proxy/export?category=ar&layer=ulica_ar&geometry=true&fileName=ulica_csv&format=csv',
    'numbers': 'https://download.geosrbija.rs/download-api/opendata-proxy/export?category=ar&layer=kucni_broj_ar&geometry=true&fileName=kucni_br_csv&format=csv',
}
ES_CATALOG = 'https://centrodedescargas.cnig.es/CentroDescargas/cartociudad'
ES_ENTRY = 'https://centrodedescargas.cnig.es/CentroDescargas/detalleArchivo?sec=42602'
ES_PROVINCES = 52
CZ_FIELDS = (
    'Kód ADM', 'Kód obce', 'Název obce', 'Kód části obce', 'Název části obce',
    'Kód ulice', 'Název ulice', 'Typ SO', 'Číslo domovní', 'Číslo orientační',
    'Znak čísla orientačního', 'PSČ', 'Souřadnice Y', 'Souřadnice X', 'Platí Od',
)
PROVIDER_HOSTS = {
    'CZ': {'atom.cuzk.gov.cz', 'atom.cuzk.cz', 'vdp.cuzk.gov.cz', 'services.cuzk.gov.cz', 'download.cuzk.cz'},
    'RS': {'download.geosrbija.rs'},
    'ES': {'centrodedescargas.cnig.es', 'www.cnig.es', 'www.ign.es'},
}
UA = 'Veygrit-world-localities/1.0 (source traceability; public open-data research)'


def canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def ensure_origin(url, country):
    u=parse.urlsplit(url)
    if (u.scheme != 'https' or u.hostname not in PROVIDER_HOSTS[country] or
            u.username is not None or u.password is not None or u.port is not None or u.fragment):
        raise ValueError('Source/download redirect URL is not authorized for '+country+': '+url[:160])
    return url


def http_client():
    jar=http.cookiejar.CookieJar()
    return request.build_opener(request.HTTPCookieProcessor(jar))


def get_response(opener,url,country,method='GET',body=None):
    ensure_origin(url,country)
    req=request.Request(url,data=body,headers={'User-Agent': UA,'Accept':'*/*'},method=method)
    response=opener.open(req,timeout=120)
    ensure_origin(response.geturl(),country)
    if response.status != 200:
        response.close()
        raise ValueError('Source HTTP status not 200')
    return response


def fetch_text(opener,url,country,max_size=3_000_000):
    with get_response(opener,url,country) as response:
        body=response.read(max_size+1)
        if len(body)>max_size:raise ValueError('Metadata response too large')
        if country == 'CZ' and (b'<!DOCTYPE' in body.upper() or b'<!ENTITY' in body.upper()):
            raise ValueError('XML external entity declarations rejected')
        return body


def safe_download(opener,url,country,target,max_bytes=3_000_000_000,post=None):
    """Fully stream one HTTP response to a new file; no silent overwrite or partial publish."""
    target=Path(target)
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() or target.is_symlink() or target.with_suffix(target.suffix+'.partial').exists():
        raise ValueError('The raw output already exists; snapshots are immutable')
    stage=target.with_suffix(target.suffix+'.partial')
    header=b'';h=hashlib.sha256();size=0
    try:
        with get_response(opener,url,country,'POST' if post is not None else 'GET',post) as response:
            mime=response.headers.get('Content-Type','')
            final_url=response.geturl()
            with stage.open('xb') as f:
                for block in iter(lambda:response.read(1<<20),b''):
                    if not header:header=block[:64]
                    size+=len(block)
                    if size>max_bytes:raise ValueError('Source file unexpectedly large')
                    h.update(block)
                    f.write(block)
            expected=response.headers.get('Content-Length')
            if expected and expected.isdecimal() and int(expected)!=size:
                raise ValueError('HTTP source stream truncated')
        if size==0 or header.lstrip().startswith((b'<html',b'<!DOCTYPE html',b'{"error"',b'Error')):
            raise ValueError('Source returned an error page, not the dataset')
        os.link(stage,target)
        stage.unlink()
        return {'uri':url,'final_uri':final_url,'filename':target.name,'bytes':size,'sha256':h.hexdigest(),
                'content_type':mime,'fetched_at':now(),'first_bytes_hex':header[:16].hex()}
    except BaseException:
        stage.unlink(missing_ok=True)
        raise


def atom_candidates(payload,base_url):
    """Only literal downloadable ZIPs and nested ATOM feeds; no scraped HTML guess."""
    root=ET.fromstring(payload)
    zips=[];feeds=[]
    for x in root.iter():
        if x.tag.rsplit('}',1)[-1]!='link':continue
        href=x.attrib.get('href','').strip()
        if not href:continue
        full=parse.urljoin(base_url,href)
        linktype=x.attrib.get('type','').lower()
        rel=x.attrib.get('rel','').lower()
        path=parse.urlsplit(full).path.lower()
        if path.endswith('.zip') or ('application/zip' in linktype):zips.append(full)
        elif path.endswith('.xml') or ('atom' in linktype and rel != 'self'):feeds.append(full)
    return list(dict.fromkeys(zips)),list(dict.fromkeys(feeds))


def discover_cz(opener,max_depth=2):
    queue=[CZ_ATOM];seen=set();archives=[];trace=[]
    while queue:
        url=queue.pop(0)
        if url in seen:continue
        seen.add(url)
        if len(seen)>12:raise ValueError('Unexpected many Atom feed URLs')
        data=fetch_text(opener,url,'CZ')
        ziplinks,feeds=atom_candidates(data,url)
        archives.extend(ziplinks);trace.append({'url':url,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'zip_count':len(ziplinks),'other_feeds':len(feeds)})
        if len(seen)<max_depth+1:queue.extend(f for f in feeds if f not in seen)
    archives=list(dict.fromkeys(archives))
    for url in archives:ensure_origin(url,'CZ')
    if not archives:raise ValueError('No RUIAN national CSV ZIP link present in ATOM feed')
    # Published feed lists may include earlier snapshots; select last embedded date deterministically.
    def key(url):
        name=parse.urlsplit(url).path
        dated=re.findall(r'(?:20\d{2})[-_]?\d{2}[-_]?\d{2}',name)
        return (max(dated) if dated else '',name)
    chosen=sorted(archives,key=key)[-1]
    return {'country':'CZ','selected_zip':chosen,'all_archives':archives,'feed_receipts':trace,'discovered_at':now()}


def sniff_csv_header(path,max_bytes=32768):
    with Path(path).open('rb') as f:header=f.read(max_bytes)
    if header.startswith(b'PK\x03\x04'):return {'format':'zip','header':None,'bytes_inspected':len(header)}
    if header.startswith(b'SQLite format 3'):return {'format':'gpkg','header':None,'bytes_inspected':len(header)}
    for encoding in ('utf-8-sig','cp1250','cp1251'):
        try:content=header.decode(encoding)
        except UnicodeError:continue
        for sep in (',',';','\t'):
            row=next(csv.reader(io.StringIO(content),delimiter=sep),[])
            if len(row)>=2 and len(set(row))==len(row):
                return {'format':'csv','encoding':encoding,'delimiter':sep,'headers':row,'bytes_inspected':len(header)}
    raise ValueError('Source is not recognizable CSV or supported archive')


def get_zip_csv(archive):
    """RÚIAN's *national* ZIP contains one municipal CSV per municipality.

    In the 2026-10-31 snapshot the actual archive holds 6,258 municipal files,
    not a single monolithic CSV. Preserve each member identity, never guess a
    municipality by a display name.
    """
    seen=set()
    for member in archive.infolist():
        name=member.filename
        if (not name or name in seen or name.startswith('/') or '\\' in name or '..' in Path(name).parts
                or member.flag_bits&1 or member.file_size>2_500_000_000 or member.file_size>max(member.compress_size,1)*500):
            raise ValueError('ZIP contains unsafe member or expansion')
        seen.add(name)
    csvs=sorted([x for x in archive.infolist() if x.filename.lower().endswith('.csv')],key=lambda x:x.filename)
    if not csvs:raise ValueError('National RÚIAN ZIP contains no municipal CSV files')
    for item in csvs:
        if not re.fullmatch(r'CSV/20\d{6}_OB_\d{6}_ADR\.csv',item.filename):
            raise ValueError('Unexpected RÚIAN municipal file name: '+item.filename[:140])
    codes=[re.search(r'_OB_(\d{6})_ADR\.csv',v.filename).group(1) for v in csvs]
    if len(codes)!=len(set(codes)):raise ValueError('Repeated RÚIAN municipal source file code')
    return csvs

def create_db(db):
    db.executescript('''
        PRAGMA journal_mode=DELETE;
        CREATE TABLE records (
          country TEXT NOT NULL, source TEXT NOT NULL, source_id TEXT NOT NULL,
          kind TEXT NOT NULL, parent_code TEXT NOT NULL, municipality TEXT NOT NULL,
          locality TEXT NOT NULL, street_id TEXT NOT NULL, street TEXT NOT NULL,
          house TEXT NOT NULL, postcode TEXT NOT NULL, source_crs TEXT NOT NULL,
          source_x TEXT, source_y TEXT, status TEXT NOT NULL,
          raw_row_sha256 TEXT NOT NULL,
          PRIMARY KEY(country,source,source_id));
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    ''')


def import_cz(archive_path,db_path,receipt):
    raw=Path(archive_path)
    if raw.stat().st_size!=receipt['bytes'] or sha256(raw)!=receipt['sha256']:
        raise ValueError('Czech archive receipt mismatch')
    db_path=Path(db_path).resolve()
    if db_path.exists():raise ValueError('Do not overwrite accepted database')
    db_path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cz-index-',dir=db_path.parent) as tmp:
        staged=Path(tmp)/'index.sqlite';db=sqlite3.connect(staged)
        try:
            create_db(db)
            count=0;codes=set();postcodes=set();missing_street=0;missing_xy=0;min_date='';max_date='';preview=[]
            with zipfile.ZipFile(raw) as z:
                files=get_zip_csv(z)
                if len(files)<6000:raise ValueError('Nationwide Czech archive has fewer than 6,000 municipal files')
                source_days=set()
                parts_with_no_rows=0
                ins='INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
                batch=[]
                for n,info in enumerate(files,1):
                    member_code=re.search(r'_OB_(\d{6})_ADR\.csv',info.filename).group(1)
                    source_days.add(re.search(r'CSV/(20\d{6})_OB_',info.filename).group(1))
                    this_count=0
                    with z.open(info) as buf,io.TextIOWrapper(buf,encoding='cp1250',newline='') as txt:
                        reader=csv.DictReader(txt,delimiter=';')
                        if not reader.fieldnames or not set(CZ_FIELDS)<=set(reader.fieldnames):
                            raise ValueError('Unexpected RUIAN columns in '+info.filename+': '+canonical(reader.fieldnames))
                        if len(reader.fieldnames)!=len(set(reader.fieldnames)):
                            raise ValueError('Repeated Czech CSV column in '+info.filename)
                        for row in reader:
                            if None in row or any(v is None for v in row.values()):raise ValueError('Invalid RUIAN CSV row')
                            rid=row['Kód ADM'].strip();mun=row['Kód obce'].strip();number=row['Číslo domovní'].strip();postcode=row['PSČ'].strip()
                            if not (rid.isdecimal() and mun.isdecimal() and number.isdecimal()):
                                raise ValueError('Invalid RUIAN unique address ID or municipal/house number')
                            if mun != member_code:
                                raise ValueError('RUIAN municipal code conflicts with ZIP member: '+info.filename)
                            if not row['Název obce'].strip():raise ValueError('RUIAN municipality missing')
                            if postcode and not re.fullmatch(r'\d{5}',postcode):raise ValueError('Unexpected Czech postcode')
                            source_date=row['Platí Od'].strip()
                            if source_date:
                                d=source_date[:10]
                                try:datetime.fromisoformat(d)
                                except ValueError as exc:raise ValueError('Invalid Czech validity date') from exc
                                min_date=min(min_date,d) if min_date else d
                                max_date=max(max_date,d)
                            cpost=''.join((row['Číslo orientační'].strip(),row['Znak čísla orientačního'].strip()))
                            house=number+('/'+cpost if cpost else '')
                            y=row['Souřadnice Y'].strip();x=row['Souřadnice X'].strip()
                            if (x and not y) or (y and not x):raise ValueError('Half pair of native RUIAN coordinates')
                            for c in (x,y):
                                if c and not re.fullmatch(r'-?\d+(?:[.,]\d+)?',c):raise ValueError('Bad native S-JTSK coordinate')
                            values=('CZ','CUZK-RUIAN-CSV-ADR-ST',rid,'address',mun,row['Název obce'].strip(),
                               row['Název části obce'].strip(),row['Kód ulice'].strip(),row['Název ulice'].strip(),
                               house,postcode,'S-JTSK',x or None,y or None,'registry_observation',
                               hashlib.sha256(canonical(row).encode('utf-8')).hexdigest())
                            batch.append(values);count+=1;this_count+=1;codes.add(mun)
                            if postcode:postcodes.add(postcode)
                            if not values[8]:missing_street+=1
                            if not x:missing_xy+=1
                            if len(preview)<3:preview.append({'id':rid,'municipality':row['Název obce'],'postcode':postcode})
                            if len(batch)>=10000:
                                db.executemany(ins,batch);db.commit();batch.clear()
                    if this_count==0:parts_with_no_rows+=1
                    if n%500==0:print(canonical({'country':'CZ','municipality_files_read':n,'addresses_read':count}),flush=True)
                if batch:db.executemany(ins,batch);db.commit();batch.clear()
            if len(source_days)!=1:raise ValueError('Mixed RUIAN national source dates')
            if count<1_000_000:raise ValueError('Nationwide RUIAN dataset unexpectedly small')
            report={'country':'CZ','source':'CUZK-RUIAN-CSV-ADR-ST','status':'SOURCE_ROWS_INDEXED',
               'address_observations':count,'municipal_csv_files':len(files),'empty_municipal_csv_files':parts_with_no_rows,
               'distinct_municipality_codes_with_rows':len(codes),'distinct_postcodes_observed':len(postcodes),
               'empty_street_name_rows':missing_street,'missing_native_xy_rows':missing_xy,
               'min_source_valid_from':min_date,'max_source_valid_from':max_date,
               'municipal_source_date':next(iter(source_days)),'source_receipt':receipt,'preview':preview,
               'source_crs':'S-JTSK','all_provided_municipal_files_read':True,
               'independently_verified_national_completeness':False,
               'postal_existence_verified':False,'carrier_deliverability_verified':False}
            db.execute('INSERT INTO metadata VALUES (?,?)',('report',canonical(report)))
            db.execute('CREATE INDEX ix_cz_municipality ON records(municipality)')
            db.execute('CREATE INDEX ix_cz_postcode ON records(postcode)')
            db.commit()
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('CZ SQLite integrity failed')
        finally:db.close()
        os.link(staged,db_path)
    return report

def inspect_rs(path):
    """Never invent official ID/header mapping; source inspector is independent of the ingest adapter."""
    file=Path(path)
    receipt={'file':file.name,'bytes':file.stat().st_size,'sha256':sha256(file)}
    try:shape=sniff_csv_header(file)
    except ValueError as exc:shape={'status':'SOURCE_FORMAT_REQUIRES_REVIEW','reason':str(exc)}
    return {**receipt,**shape,'actual_source_record_count':None,
       'address_id_join_verified':False,'official_address_imported':False}


def import_rs_csv_files(files,pins,db_path,field_map):
    """Mapping is approved only after inspecting the *actual* exported CSV headers.
    field_map: {'streets':{'id':'source-id-header','street':'source-name-header',...},
                'numbers':{'id':...,'house':'...', 'street_id':...}}
    """
    db_path=Path(db_path)
    if db_path.exists():raise ValueError('Output index exists')
    with tempfile.TemporaryDirectory(prefix='rgz-index-',dir=db_path.parent) as tmp:
        staging=Path(tmp)/'rs.sqlite';db=sqlite3.connect(staging)
        try:
            create_db(db)
            counts={}
            for kind in ('streets','numbers'):
                p=Path(files[kind]);pin=pins[kind]
                if sha256(p)!=pin['sha256'] or p.stat().st_size!=pin['bytes']:raise ValueError('Serbian source pin mismatch')
                desc=sniff_csv_header(p)
                if desc['format']!='csv':raise ValueError('Unrecognized RGZ CSV; review required')
                fields=field_map[kind]
                if kind=='numbers' and not {'id','house','street_id'}<=set(fields):raise ValueError('House number requires unique ID and street ID')
                if kind=='streets' and not {'id','street'}<=set(fields):raise ValueError('Street requires source ID and name')
                if not set(fields.values()) <= set(desc['headers']):raise ValueError('RGZ approved source field missing')
                count=0
                with p.open('r',encoding=desc['encoding'],newline='') as f:
                    rdr=csv.DictReader(f,delimiter=desc['delimiter'])
                    insert='INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
                    batch=[]
                    for row in rdr:
                        if None in row or any(v is None for v in row.values()):raise ValueError('Malformed RGZ CSV')
                        id=(row[fields['id']] or '').strip()
                        if not id:raise ValueError('RGZ row lacks unique ID')
                        val=lambda name:(row.get(fields[name],'') or '').strip() if name in fields else ''
                        house=val('house');street=val('street');street_id=val('street_id')
                        if kind=='streets' and not street:raise ValueError('RGZ named street missing')
                        if kind=='numbers' and not house:raise ValueError('RGZ house number missing')
                        batch.append(('RS','RGZ-'+kind,id,'street' if kind=='streets' else 'address',
                            val('municipality_id'),val('municipality'),val('locality'),street_id,street,house,
                            val('postcode'),'not_provided',None,None,val('status') or 'registry_observation',
                            hashlib.sha256(canonical({k:row[v] for k,v in fields.items()}).encode()).hexdigest()))
                        count+=1
                        if len(batch)>=10000:db.executemany(insert,batch);db.commit();batch.clear()
                    if batch:db.executemany(insert,batch);db.commit()
                counts[kind]=count
            # Exact source street code join is conditional on the official schema mapping.
            streets={x[0] for x in db.execute("SELECT source_id FROM records WHERE kind='street'")}
            ref_stats=Counter()
            for sid, in db.execute("SELECT street_id FROM records WHERE kind='address'"):
                ref_stats['nonempty_street_id' if sid else 'missing_street_id']+=1
                if sid and sid not in streets:ref_stats['unmatched_to_street_identifier']+=1
            report={'country':'RS','source':'RGZ open-data address register','status':'SOURCE_ROWS_INDEXED',
                'counts':counts,'join':dict(ref_stats),'source_receipts':pins,
                'source_street_id_join_verified':ref_stats['unmatched_to_street_identifier']==0 and ref_stats['missing_street_id']==0,
                'national_address_completeness_verified':False,'deliverability_verified':False}
            db.execute('INSERT INTO metadata VALUES (?,?)',('report',canonical(report)))
            db.commit()
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('RGZ SQLite failure')
        finally:db.close()
        os.link(staging,db_path)
    return report


def inspect_gpkg(gpkg):
    path=Path(gpkg).resolve()
    with path.open('rb') as head: signature=head.read(16)
    if signature != b'SQLite format 3\x00':
        raise ValueError('Expected SQLite GeoPackage')
    uri='file:'+parse.quote(path.as_posix(),safe='/')+'?mode=ro'
    db=sqlite3.connect(uri,uri=True)
    try:
        tables=[a[0] for a in db.execute("SELECT table_name FROM gpkg_contents ORDER BY table_name")]
        selected='portalpk_publi'
        if selected not in tables:raise ValueError('CartoCiudad expected portalpk_publi layer missing; found '+canonical(tables))
        columns=[r[1] for r in db.execute('PRAGMA table_info("portalpk_publi")')]
        count=db.execute('SELECT count(*) FROM "portalpk_publi"').fetchone()[0]
        srs=list(db.execute('SELECT srs_id,organization,organization_coordsys_id FROM gpkg_spatial_ref_sys ORDER BY srs_id LIMIT 20'))
        return {'expected_layer':selected,'rows':count,'columns':columns,'tables':tables,'declared_crs':srs,
            'national_completeness_verified':False,'deliverability_verified':False}
    finally:db.close()


def inspect_es_zip(zip_path):
    """Inspect one CNIG provincial archive, without assuming availability of full 52 provinces."""
    with zipfile.ZipFile(zip_path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)):raise ValueError('ZIP duplicate entry')
        allowed=[]
        for item in z.infolist():
            n=item.filename
            if n.startswith('/') or '..' in Path(n).parts or '\\' in n or item.flag_bits & 1:
                raise ValueError('Unsafe province archive entry')
            if item.filename.lower().endswith('.gpkg'):
                if item.file_size>2_500_000_000:raise ValueError('Too large GeoPackage')
                allowed.append(item)
        if len(allowed)!=1:raise ValueError('Province archive must contain one GeoPackage')
        with tempfile.TemporaryDirectory(prefix='cartociudad-') as temp:
            gpkg=Path(temp)/'part.gpkg'
            with z.open(allowed[0]) as raw,gpkg.open('wb') as f:
                for chunk in iter(lambda:raw.read(1<<20),b''):f.write(chunk)
            report=inspect_gpkg(gpkg)
        report.update(archive=Path(zip_path).name,zip_member=allowed[0].filename,
                      zip_sha256=sha256(zip_path),zip_bytes=Path(zip_path).stat().st_size)
        return report


def find_es_detail_ids(html):
    data=html.decode('utf-8',errors='replace')
    ids=re.findall(r'detalleArchivo(?:\?|[^"\']*?\?)sec=(\d+)',data,re.I)
    return sorted(set(ids),key=int)


def es_two_step_probe(opener,seq):
    """Read public CNIG download handshake. If consent is required, abort rather than bypass."""
    if not re.fullmatch('[0-9]{3,10}',str(seq)):raise ValueError('Invalid public CNIG file number')
    base='https://centrodedescargas.cnig.es/CentroDescargas/'
    url=base+'initDescargaDir?secuencial='+str(seq)
    raw=fetch_text(opener,url,'ES',max_size=200_000)
    try:init=json.loads(raw.decode('utf-8'))
    except (ValueError,UnicodeError):
        return {'status':'CNIG_HANDSHAKE_NOT_JSON','seq':str(seq),'preview':raw[:300].decode('utf-8','replace')}
    return {'status':'CNIG_HANDSHAKE_RECEIVED','seq':str(seq),'response':init}


def save_json(out,obj):
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:f.write(json.dumps(obj,ensure_ascii=False,sort_keys=True,indent=2)+'\n')


def run(args):
    o=http_client();dest=Path(args.output_dir);dest.mkdir(parents=True,exist_ok=True)
    result={'started_at':now(),'country':args.country,'task':args.task,'results':[]}
    if args.country=='CZ':
        info=discover_cz(o);result['discovery']=info
        if args.task=='download':
            raw=dest/'czechia-ruian-national.zip'
            pin=safe_download(o,info['selected_zip'],'CZ',raw,max_bytes=300_000_000)
            pin['license']='CC-BY-4.0';pin['authority']='ČÚZK';result['results'].append(pin)
            idx=import_cz(raw,dest/'cz-addresses.sqlite',pin)
            result['country_index']=idx
    elif args.country=='RS':
        for kind,url in RS_DOWNLOADS.items():
            if args.task=='download':
                p=dest/('serbia-rgz-'+kind+'.csv')
                pin=safe_download(o,url,'RS',p,max_bytes=2_500_000_000)
                pin['license']='Serbian Open Data License';pin['authority']='RGZ';result['results'].append({**pin,'schema_inspection':inspect_rs(p)})
            else:
                result['results'].append({'kind':kind,'url':url})
    elif args.country=='ES':
        page=fetch_text(o,ES_CATALOG,'ES',max_size=3_000_000)
        ids=find_es_detail_ids(page)
        result['catalog_discovery']={'detail_page_ids':ids,'found':len(ids),'expected':ES_PROVINCES,'page_sha256':hashlib.sha256(page).hexdigest()}
        try:
            result['pilot_handshake']=es_two_step_probe(o,'42602')
        except Exception as exc:
            result['pilot_handshake']={'status':'ACCESS_NOT_CONFIRMED','error':str(exc)[:300]}
        # ES has 52 province files, but an unverified handshake is NOT approval for bulk.
        result['all_52_provinces_downloaded']=False
    result['completed_at']=now()
    save_json(dest/('report-'+args.country.lower()+'.json'),result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--country',required=True,choices=('CZ','RS','ES'))
    p.add_argument('--task',choices=('discover','download'),default='discover')
    p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args()
    try:
        res=run(args)
        print(canonical({'country':res['country'],'task':res['task'],'completed_at':res['completed_at'],
            'status':'PASS','reports':str(args.output_dir)}))
    except (OSError,ValueError,zipfile.BadZipFile,sqlite3.DatabaseError,ET.ParseError) as exc:
        print(canonical({'country':args.country,'status':'ERROR','error':str(exc)[:500]}))
        sys.exit(1)

if __name__=='__main__':main()
