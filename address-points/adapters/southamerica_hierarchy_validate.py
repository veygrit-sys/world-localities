#!/usr/bin/env python3
"""Replay hierarchy source observations and run country-level behavioral checks."""
import argparse
import csv
from datetime import datetime,timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import unittest
import zipfile
import southamerica as sa
import southamerica_hierarchy as h


def expected_observations(s):
    id=s['id'];p=s['local_path']
    if s['kind']=='geonames':
        for i,r in enumerate(sa.zip_rows(p,s['country']),1):
            raw=dict(zip(sa.GN_FIELDS,r))
            if raw['country_code']==s['country'] and ((raw['feature_class']=='P' and raw['feature_code'] not in sa.HISTORIC_FEATURES) or raw['feature_code'] in ['ADM1','ADM2','ADM3','ADM4']):yield i,raw
    elif id in ['gn-admin1CodesASCII','gn-admin2Codes']:
        for i,r in enumerate(csv.reader(io.StringIO(h.decoded(p).decode('utf-8')),delimiter='\t'),1):
            if r[0].split('.')[0] in h.ALL_SCOPES:yield i,r
    elif s['kind'] in ('georef','georef-extra'):
        d=h.read_data(p)
        field={'ar-georef-provincias':'provincias','ar-georef-localidades':'localidades','ar-georef-departamentos':'departamentos','ar-georef-municipios':'municipios','ar-georef-localidades-censales':'localidades_censales'}[id]
        for i,r in enumerate(d[field],1):yield i,r
    elif s['kind'] in ('ibge','dane'):
        for i,r in enumerate(h.read_data(p),1):yield i,r
    elif s['kind'].startswith('py-'):
        d=h.read_data(p)
        if len(d['features'])!=d['numberMatched']:raise ValueError('Truncated WFS')
        for i,r in enumerate(d['features'],1):yield i,r
    elif s['kind'] in ('inei','uy-streets'):
        for i,r in enumerate(csv.DictReader(io.StringIO(h.decoded(p).decode('utf-8-sig')),delimiter=';' if s['kind']=='inei' else ','),1):yield i,r
    elif s['kind']=='ban':
        with gzip.open(p,'rt',encoding='utf-8-sig',newline='') as f:
            for i,r in enumerate(csv.DictReader(f,delimiter=';'),1):yield i,r
    elif s['kind']=='insee':
        with zipfile.ZipFile(p) as z:
            for rank,member in [(10,'v_region_2026.csv'),(20,'v_departement_2026.csv'),(30,'v_arrondissement_2026.csv'),(40,'v_commune_2026.csv')]:
                for i,r in enumerate(csv.DictReader(io.StringIO(z.read(member).decode('utf-8-sig'))),1):
                    belongs=r.get('REG')=='03' if rank==10 else r.get('DEP')=='973'
                    if belongs and (rank!=40 or r['TYPECOM']=='COM'):yield rank*1000000+i,{'member':member,'row':r}
    else:raise ValueError('No independent replay reader for '+id)


def replay(db,registry):
    reports=[]
    for source in [r[0] for r in db.execute('SELECT DISTINCT source FROM observations ORDER BY source')]:
        expected=iter(expected_observations(registry[source]));sha=hashlib.sha256();count=0
        for row in db.execute('SELECT ordinal,raw_json FROM observations WHERE source=? ORDER BY ordinal',(source,)):
            item=next(expected,None)
            if item is None or item[0]!=row['ordinal'] or item[1]!=json.loads(row['raw_json']):raise ValueError('Raw observation mismatch '+source)
            sha.update((sa.dump([item[0],item[1]])+'\n').encode());count+=1
        if next(expected,None) is not None:raise ValueError('Missing indexed observation '+source)
        reports.append({'source':source,'rows':count,'sha256':sha.hexdigest(),'status':'PASS'})
    return reports


def country_checks(db):
    results=[]
    for cc in h.ALL_SCOPES:
        root='scope:'+cc
        scope=h.hierarchy(db,root)
        if scope['node']['kind']!=('country' if cc in h.COUNTRIES else 'supplementary_area'):raise ValueError('Scope classification mismatch')
        row=db.execute("SELECT n.* FROM nodes n WHERE n.country=? AND n.namespace='geonames' AND EXISTS(SELECT 1 FROM links l WHERE l.child=n.id) ORDER BY n.rank DESC,n.id LIMIT 1",(cc,)).fetchone()
        if row:
            path=h.hierarchy(db,row['id'])
            if root not in [p['id'] for p in path['ancestors']]:raise ValueError('Country path not rooted')
            found=h.search(db,cc,row['name'],namespace='geonames',parent=root,limit=100)
            if row['id'] not in [x['id'] for x in found['results']]:raise ValueError('Name/ancestor search failed')
        results.append({'code':cc,'scope':'country' if cc in h.COUNTRIES else 'supplementary_area','status':'PASS','example_node':row['id'] if row else None,'geonames_path_available':row is not None})
    # Official nationwide code systems retain leading zeros and reject a different state.
    for cc,ns in [('AR','ar-georef-v1'),('BR','br-ibge'),('CO','co-dane-2024'),('PE','pe-inei-reference'),('PY','py-ine-statistical'),('UY','uy-ide-2020'),('GF','gf-ban')]:
        n=db.execute('SELECT * FROM nodes WHERE country=? AND namespace=? ORDER BY rank DESC,id LIMIT 1',(cc,ns)).fetchone()
        if n is None:raise ValueError('Official layer is empty '+cc)
        p=h.hierarchy(db,n['id'])
        if 'scope:'+cc not in [x['id'] for x in p['ancestors']]:raise ValueError('Official hierarchy root absent '+cc)
        if p['address_verified'] or p['delivery_verified']:raise ValueError('Unsupported verification upgrade')
    for code in ['07013045','07016350']:
        id='py-ine:neighbourhood_or_locality:'+code
        result=h.hierarchy(db,id)
        if result['status']!='source_relations_resolved' or 'py-ine:district:0701' not in [r['id'] for r in result['ancestors']]:
            raise ValueError('Explicit Paraguay component tuple was not resolved')
        raw=json.loads(db.execute('SELECT raw_json FROM nodes WHERE id=?',(id,)).fetchone()[0])
        if raw['properties']['CLAVE']!='':raise ValueError('Blank source value was overwritten')
    return results


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,default=h.DEFAULT_DB);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    suite=unittest.defaultTestLoader.discover(str(sa.ROOT.parent/'tests'),pattern='test_southamerica*.py')
    t=unittest.TextTestRunner(verbosity=1).run(suite)
    if not t.wasSuccessful():raise SystemExit(1)
    registry=h.source_registry()
    with h.open_database(a.db) as db:
        r=replay(db,registry);c=country_checks(db);s=h.structural_checks(db)
        integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity!='ok':raise ValueError('SQLite integrity check failed')
        counts={name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ['nodes','links','observations','names','issues']}
    report={'status':'PASS','checked_at':datetime.now(timezone.utc).isoformat(),'behavior_tests':t.testsRun,
        'source_integrity_objects':len(registry),'observation_replays':r,'country_checks':c,'structural_checks':s,
        'sqlite_integrity':'PASS','counts':counts,'country_count':12,'supplementary_area_count':4,
        'limit':'Tests prove source fidelity, deterministic navigation and conservative mismatch handling, not national coverage or deliverability.'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(sa.dump({'status':'PASS','behavior_tests':t.testsRun,'source_integrity_objects':len(registry),'source_replays':len(r),'countries':12,'supplementary_areas':4,'counts':counts}))


if __name__=='__main__':main()
