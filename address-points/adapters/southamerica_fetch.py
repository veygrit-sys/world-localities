#!/usr/bin/env python3
"""Refresh a NEW candidate package; default: 12 countries, retain 4 supplements."""
import argparse
from datetime import datetime,timezone
import gzip,hashlib,io,json
from pathlib import Path
import shutil,urllib.request,zipfile

import os as _hierarchy_os
ROOT = Path(_hierarchy_os.environ.get('WORLD_LOCALITIES_ADDRESS_ROOT', str(Path(__file__).resolve().parents[1]))).resolve()
COUNTRIES={'AR','BO','BR','CL','CO','EC','GY','PY','PE','SR','UY','VE'}

def validate_payload(s,b):
    decoded=gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b
    if s['kind'] in ('geonames','names','insee'):
        with zipfile.ZipFile(io.BytesIO(decoded)) as z:
            if z.testzip() is not None:raise ValueError('Source ZIP CRC error')
            if s['kind'] in ('geonames','names') and s['country']+'.txt' not in z.namelist():raise ValueError('Missing country member')
    elif s['kind']=='ban':
        if not decoded.startswith(b'id;'):raise ValueError('Unexpected BAN header')
    elif s['kind'] in ('georef','georef-extra','ibge','dane','metadata') or s['kind'].startswith('py-'):
        obj=json.loads(decoded)
        if isinstance(obj,dict) and obj.get('error'):raise ValueError('Source API error')
        if isinstance(obj,dict) and 'numberMatched' in obj and len(obj.get('features',[]))!=obj['numberMatched']:raise ValueError('Truncated WFS response')
        if isinstance(obj,dict) and all(k in obj for k in ['cantidad','total','inicio']):
            if obj['cantidad']!=obj['total'] or obj['inicio']!=0:raise ValueError('Truncated Georef response')
    elif b'<html' in decoded[:2000].lower():raise ValueError('HTML returned instead of reference data')

def refresh_source(s,root,same_hash=False):
    req=urllib.request.Request(s['url'],headers={'User-Agent':'Veygrit-SouthAmerica-research/0.2','Accept-Encoding':'identity'})
    with urllib.request.urlopen(req,timeout=45) as r:
        b=r.read(100*1024*1024+1)
        if len(b)>100*1024*1024:raise ValueError('Source exceeds 100 MiB guard')
        headers={k:r.headers.get(k) for k in ['Content-Type','Content-Encoding','Last-Modified','ETag']};url=r.url
    validate_payload(s,b)
    sha=hashlib.sha256(b).hexdigest()
    if same_hash and sha!=s['sha256']:raise ValueError('Rolling source differs from pinned bytes')
    path=(root/s['path']).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Unsafe source path')
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b)
    updated={**s,'sha256':sha,'bytes':len(b),'retrieved_at':datetime.now(timezone.utc).isoformat(),
        'http_headers':headers,'resolved_url':url,'changed_since_prior_snapshot':sha!=s['sha256']}
    if s['kind'] in ('geonames','names','insee'):
        with zipfile.ZipFile(io.BytesIO(gzip.decompress(b) if b[:2]==b'\x1f\x8b' else b)) as z:updated['archive_members']=z.namelist()
    path.with_suffix(path.suffix+'.receipt.json').write_text(json.dumps(updated,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return updated

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--scope',choices=['countries','all'],default='countries');p.add_argument('--require-same-hash',action='store_true');a=p.parse_args()
    out=a.output.resolve()
    if out.exists():raise SystemExit('Use a new directory; existing releases are never overwritten.')
    shutil.copytree(ROOT.parent,out,ignore=shutil.ignore_patterns('__pycache__','generated','reports'))
    ap=out/'address-points'
    for f in list(ap.glob('*VALIDATION.json'))+list(ap.glob('*BUILD.json'))+list(ap.glob('*LOOP.json')):
        f.unlink()
    for f in [out/'MANIFEST.json',out/'COUNTRY_RESULTS_JA.md',out/'tests/RESULTS.txt']:
        if f.exists():f.unlink()
    failures=[];counts={cc:{'updated_sources':0,'failures':0} for cc in sorted(COUNTRIES)}
    for filename,folder in [('SOUTH_AMERICA_SOURCES.json','SOUTHAMERICA'),('SOUTH_AMERICA_HIERARCHY_SOURCES.json','HIERARCHY')]:
        m=json.loads((ROOT/filename).read_text());results=[];failed=[]
        for s in m['sources']:
            if a.scope=='countries' and s['country'] not in COUNTRIES and s['country']!='ALL':results.append(s);continue
            try:
                results.append(refresh_source(s,ap/'sources'/folder,a.require_same_hash))
                if s['country'] in counts:counts[s['country']]['updated_sources']+=1
                print(s['id']+': acquired',flush=True)
            except Exception as e:
                results.append(s);entry={'source':s['id'],'error':str(e)};failed.append(entry);failures.append(entry)
                if s['country'] in counts:counts[s['country']]['failures']+=1
                print(s['id']+': failed: '+str(e),flush=True)
        m.update({'sources':results,'failures':failed,'candidate_snapshot':True,'refresh_scope':a.scope,'fetched_at':datetime.now(timezone.utc).isoformat()})
        (ap/filename).write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    review={'status':'ACQUISITION_FAILED' if failures else 'CANDIDATE_REQUIRES_BUILD_AND_REVIEW','scope':a.scope,
        'country_count':12,'country_results':counts,'failures':failures,
        'supplementary_area_policy':'Retained pinned sources unless --scope all',
        'required_next_steps':['build indexes','run validators','run country loop','review source/schema/licence changes','refresh counts/docs','regenerate manifest']}
    (ap/'SOUTH_AMERICA_REFRESH_REVIEW.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    readme=out/'README_JA.md';readme.write_text('# 再取得候補版・未検証\n\n以下の説明や件数は元版のものです。再生成・再検証後に更新してください。\n\n'+readme.read_text(),encoding='utf-8')
    print(json.dumps(review,ensure_ascii=False,indent=2))
    if failures:raise SystemExit(1)

if __name__=='__main__':main()
