#!/usr/bin/env python3
"""Fetch a reviewable Central America candidate; never overwrite the accepted package."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import csv,gzip,hashlib,io,json,shutil,sys,zipfile
from pathlib import Path
from urllib.request import Request,urlopen
import centralamerica_common as common


def validate_payload(source,data):
    raw=gzip.decompress(data) if data[:2]==b'\x1f\x8b' else data
    if not raw or b'<html' in raw[:1000].lower() or b'<!doctype html' in raw[:1000].lower():
        raise ValueError('Empty response or HTML instead of source data')
    if source['format'] in ('zip','xlsx'):
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            if z.testzip():raise ValueError('Corrupt archive')
            if source.get('member') and source['member'] not in z.namelist():
                raise ValueError('Archive member changed; inspect schema and update the recipe')
            if '-geonames-' in source['id'] and source['country']+'.txt' not in z.namelist():
                raise ValueError('Country archive member missing')
            if source['format']=='xlsx':
                import xml.etree.ElementTree as ET
                ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                names={s.get('name') for s in ET.fromstring(z.read('xl/workbook.xml')).findall('m:sheets/m:sheet',ns)}
                if not {l['sheet'] for l in source.get('layers',[])}<=names:raise ValueError('Worksheet inventory changed')
    elif source['format'] in ('csv','csv.gz'):
        rows=csv.reader(io.StringIO(raw.decode(source.get('encoding','utf-8-sig'))),delimiter=source.get('delimiter',','))
        header=next(rows,None);first=next(rows,None)
        if not header or not first or len(header)!=len(first):raise ValueError('CSV header or data missing')
    elif source['format']=='json':
        d=json.loads(raw)
        if '-codab-metadata' in source['id']:
            if not d.get('success') or d.get('result',{}).get('license_id')!='cc-by-igo':
                raise ValueError('COD-AB catalogue or published licence changed; manual review required')
    return raw


def fetch_one(source,root):
    path=(root/source['path']).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Unsafe source path')
    started=datetime.now(timezone.utc).isoformat()
    try:
        with urlopen(Request(source['url'],headers={'User-Agent':'Veygrit-CentralAmerica/0.1','Accept-Encoding':'identity'}),timeout=180) as response:
            data=response.read();final=response.url
            headers={k:v for k,v in response.headers.items() if k.lower() in ('content-type','last-modified','etag','content-encoding')}
        validate_payload(source,data)
        sha=hashlib.sha256(data).hexdigest()
        updated={**source,'retrieved_at':started,'bytes':len(data),'sha256':sha,'final_url':final,'http_metadata':headers,'unchanged_from_previous_hash':sha==source['sha256']}
        # Recipe metadata is retained, but the original inherited receipt describes the earlier snapshot.
        if 'original_receipt' in updated:updated['prior_snapshot_receipt']=updated.pop('original_receipt')
        updated.pop('inherited_from',None)
        path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_name(path.name+'.part')
        temp.write_bytes(data);temp.replace(path)
        path.with_name(path.name+'.receipt.json').write_text(json.dumps(updated,ensure_ascii=False,indent=2)+'\n')
        return updated,None
    except Exception as exc:
        return source,{'id':source['id'],'url':source['url'],'attempted_at':started,'error':str(exc)}


def stage_candidate(output):
    """Copy only this region's recipe, code, tests and descriptions."""
    output=Path(output)
    newroot=output/'address-points'
    adapters=newroot/'adapters'
    adapters.mkdir(parents=True)
    code_root=Path(__file__).resolve().parent
    for name in ['centralamerica.py','centralamerica_common.py','centralamerica_fetch.py','centralamerica_validate.py']:
        shutil.copyfile(code_root/name,adapters/name)
    for name in ['CENTRAL_AMERICA_SCOPE.json','CENTRAL_AMERICA_RULES.json']:
        shutil.copyfile(common.ROOT/name,newroot/name)
    repository=code_root.parents[1]
    release=repository/'releases/hierarchy/central-america'
    documents=release/'original' if release.is_dir() else common.ROOT.parent
    for name in ['README_JA.md','LICENSE_DATA.md','POSTAL_REFERENCE_JA.md']:
        shutil.copyfile(documents/name,output/name)
    examples=release/'examples' if release.is_dir() else common.ROOT.parent/'examples'
    shutil.copytree(examples,output/'examples')
    installed_tests=repository/'hierarchy-tests/test_hierarchy_central_america_centralamerica.py'
    test=installed_tests if installed_tests.is_file() else common.ROOT.parent/'tests/test_centralamerica.py'
    (output/'tests').mkdir()
    shutil.copyfile(test,output/'tests/test_centralamerica.py')
    return newroot


def refresh(output,scope='countries',workers=4):
    if scope not in ('countries','all') or not 1<=workers<=4:raise ValueError('Invalid scope or worker count')
    output=Path(output).resolve();package=common.ROOT.parent.resolve()
    if output.exists() or output.is_relative_to(package):raise ValueError('Use a new candidate directory outside the accepted package')
    # A clean repository has pinned recipes but no raw payloads. Refresh does
    # not need an old payload copy; every selected source is fetched anew.
    manifest=common.read_json(common.ROOT/'CENTRAL_AMERICA_SOURCES.json');scope_data=common.read_json(common.ROOT/'CENTRAL_AMERICA_SCOPE.json')
    source_ids=[s['id'] for s in manifest['sources']]
    if not source_ids or len(set(source_ids))!=len(source_ids) or set(source_ids)!=set(manifest['required_source_ids']):
        raise ValueError('Source recipe inventory mismatch')
    selected=set(scope_data['country_codes'])|{'COMMON'}
    if scope=='all':selected|=set(scope_data['supplementary_area_codes'])
    if any(s['country'] not in selected for s in manifest['sources']):
        raise ValueError('Requested scope would leave inherited sources unrefreshed')
    newroot=stage_candidate(output);records={s['id']:s for s in manifest['sources']};failures=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending=[pool.submit(fetch_one,s,newroot/'sources/CENTRALAMERICA') for s in manifest['sources'] if s['country'] in selected]
        for future in as_completed(pending):
            source,error=future.result();records[source['id']]=source
            if error:failures.append(error)
            print(json.dumps({'source':source['id'],'status':'failed' if error else 'acquired'},ensure_ascii=False),file=sys.stderr)
    created=datetime.now(timezone.utc)
    updated={**manifest,'release_date':created.date().isoformat(),'candidate_created_at':created.isoformat(),'scope':scope,'sources':[records[s['id']] for s in manifest['sources']],'failures':failures,'validation_required':True}
    (newroot/'CENTRAL_AMERICA_SOURCES.json').write_text(json.dumps(updated,ensure_ascii=False,indent=2)+'\n')
    rules=common.read_json(newroot/'CENTRAL_AMERICA_RULES.json');rules['release_date']=created.date().isoformat()
    (newroot/'CENTRAL_AMERICA_RULES.json').write_text(json.dumps(rules,ensure_ascii=False,indent=2)+'\n')
    (newroot/'CENTRAL_AMERICA_ACQUISITION_REVIEW.json').write_text(json.dumps({'status':'unvalidated_candidate','scope':scope,'created_at':created.isoformat(),'failures':failures,'full_source_replay_required':True},ensure_ascii=False,indent=2)+'\n')
    readme=output/'README_JA.md'
    readme.write_text('# 未検証の再取得候補\n\n再取得した原典を含みます。以下は元版の説明です。階層の再構築・原行再照合・出典の版確認が完了するまで確定版として扱わないでください。\n\n'+readme.read_text())
    return {'status':'acquisition_failed' if failures else 'candidate_requires_validation','country_count':len(scope_data['country_codes']),'supplementary_refreshed':scope=='all','failed_sources':failures,'output':str(output)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--scope',choices=['countries','all'],default='countries');parser.add_argument('--workers',type=int,default=4)
    args=parser.parse_args()
    try:
        result=refresh(args.output,args.scope,args.workers);print(json.dumps(result,ensure_ascii=False,indent=2))
        if result['failed_sources']:raise SystemExit(2)
    except (OSError,ValueError,KeyError) as exc:
        print(json.dumps({'status':'error','message':str(exc)}),file=sys.stderr);raise SystemExit(2)

if __name__=='__main__':main()
