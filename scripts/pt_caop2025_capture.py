#!/usr/bin/env python3
"""Acquire, inspect and pin 2025 DGT CAOP official municipality/parish GeoPackages.

No unlicensed redistribution or address/delivery inference. This consumes an officially
published no-cost administrative-boundary release, not the postal address registry.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
from urllib.request import Request, urlopen
import zipfile

# URLs are the three direct GPKG archives linked from DGT's CAOP2025 page.
SOURCES={
    'continent':'https://geo2.dgterritorio.gov.pt/caop/CAOP_Continente_2025-gpkg.zip',
    'azores':'https://geo2.dgterritorio.gov.pt/caop/CAOP_RAA_2025-gpkg.zip',
    'madeira':'https://geo2.dgterritorio.gov.pt/caop/CAOP_RAM_2025-gpkg.zip',
}
BASE='https://www.dgterritorio.gov.pt/atividades/cartografia/cartografia-tematica/caop'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for c in iter(lambda:f.read(1024*1024),b''):h.update(c)
    return h.hexdigest()


def _source_download(region,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    dest=folder/(region+'-caop2025.zip')
    if dest.exists() or dest.is_symlink():raise ValueError('Use a fresh original-source directory')
    partial=dest.with_suffix('.download')
    if partial.exists():raise ValueError('Incomplete download must be inspected')
    if region not in SOURCES:raise ValueError('Unknown DGT region')
    url=SOURCES[region];size=0;h=hashlib.sha256()
    with urlopen(Request(url,headers={'User-Agent':'Veygrit-CAOP2025/1.0'}),timeout=120) as src,partial.open('xb') as out:
        if src.status!=200 or src.geturl()!=url:raise ValueError('Unexpected DGT download redirect/status')
        for block in iter(lambda:src.read(1024*1024),b''):
            size+=len(block)
            if size>2_000_000_000:raise ValueError('Unexpected CAOP archive size')
            out.write(block);h.update(block)
    if size<10000:raise ValueError('Unexpectedly small CAOP archive')
    os.link(partial,dest);partial.unlink()
    return {'publisher':'DGT','url':url,'region':region,'acquired_at':datetime.now(timezone.utc).isoformat(),
            'bytes':size,'sha256':h.hexdigest(),'license':'CC BY 4.0 (verify downloaded source NOTICE)',
            'source_date':'2025-12-31','publication_date':'2026-02-18'}


def _extract_one_gpkg(path,destination):
    destination=Path(destination)
    if destination.exists():raise ValueError('Refuse overwrite')
    with zipfile.ZipFile(path) as z:
        files=[x for x in z.infolist() if x.filename.lower().endswith('.gpkg') and not x.is_dir()]
        if len(files)!=1:raise ValueError('Expected exactly one CAOP GeoPackage; got: '+str([(i.filename,i.file_size) for i in z.infolist()][:40]))
        one=files[0]
        if (one.file_size>2_000_000_000 or (one.compress_size and one.file_size/one.compress_size>1000)
            or Path(one.filename).is_absolute() or '..' in Path(one.filename).parts or '\\' in one.filename):
            raise ValueError('Unsafe archive member')
        with z.open(one) as src,destination.open('xb') as out:
            shutil.copyfileobj(src,out,1024*1024)
    return {'member':one.filename,'bytes':destination.stat().st_size,'sha256':digest(destination)}


def _schema(path):
    db=sqlite3.connect('file:'+Path(path).resolve().as_posix()+'?mode=ro',uri=True)
    try:
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('GPKG integrity check failed')
        tables=db.execute('SELECT table_name,srs_id FROM gpkg_contents').fetchall()
        choices=[]
        for table,srs in tables:
            if not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*',table):continue
            cols={x[1] for x in db.execute(f'PRAGMA table_info("{table}")')}
            lower={x.lower():x for x in cols}
            if {'dtmnfr','freguesia'}<=set(lower) and 'freguesias' in table.lower():
                choices.append((table,srs,lower))
        if len(choices)!=1:raise ValueError('Unexpected CAOP freguesia schema: '+str([(a,b) for a,b in tables]))
        table,srs,lower=choices[0]
        count=db.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
        if count<20 or count>10000:raise ValueError('Unexpected freguesia count: '+str(count))
        key=lower['dtmnfr']
        row=db.execute(f'SELECT "{key}" FROM "{table}" LIMIT 1').fetchone()[0]
        if not isinstance(row,str):raise ValueError('DTMNFR must be preserved as a source string')
        geom=db.execute('SELECT column_name,srs_id FROM gpkg_geometry_columns WHERE table_name=?',(table,)).fetchone()
        if geom and geom[1]!=srs:raise ValueError('GPKG layer SRID conflict')
        fields={'id':lower['dtmnfr'],'name':lower['freguesia']}
        if 'municipio' in lower:fields['locality']=lower['municipio']
        return {'table':table,'srs':srs,'count':count,'fields':fields,'columns':sorted(cols)}
    finally:db.close()


def capture(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    originals=folder/'raw';originals.mkdir(exist_ok=False)
    receipts=folder/'receipts';receipts.mkdir(exist_ok=False)
    events=[]
    for region in SOURCES:
        download=_source_download(region,originals)
        original=originals/(region+'-caop2025.zip')
        gpkg=originals/(region+'-caop2025.gpkg')
        extracted=_extract_one_gpkg(original,gpkg)
        schema=_schema(gpkg)
        receipt={
          'schema_version':1,'country':'PT','kind':'administrative','dataset':'dgt-caop2025-'+region+'-freguesias',
          'publisher_url':download['url'],'rights_reviewed':True,
          'license':'CC-BY-4.0','attribution':'Direção-Geral do Território (DGT), CAOP2025',
          'source_date':download['source_date'],'crs':'EPSG:'+str(schema['srs']),
          'format':'gpkg','path':gpkg.name,'bytes':extracted['bytes'],'sha256':extracted['sha256'],
          'table':schema['table'],'fields':schema['fields']
        }
        receipt_path=receipts/(region+'.json')
        receipt_path.write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        events.append({'region':region,'original_archive':download,'gpkg':extracted,'selected_layer':schema,
                       'receipt_path':str(receipt_path)})
    report={'status':'DGT_SOURCE_ACQUIRED_AND_INSPECTED','scope':'official administrative boundaries, not current addresses',
            'region_files':events,'national_address_completeness_verified':False,'deliverability_verified':False}
    (folder/'dgt-acquisition.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    return report


def cli():
    p=argparse.ArgumentParser();p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args()
    print(json.dumps(capture(a.output_dir),ensure_ascii=False,indent=2))

if __name__=='__main__':cli()
