#!/usr/bin/env python3
"""Independent full source-to-index replay, plus real-data search/spatial checks."""
import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parent))
import southamerica as sa

def digest_rows(rows):
    h=hashlib.sha256();n=0
    for row in rows:
        h.update(json.dumps(row,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8'))
        h.update(b'\n');n+=1
    return n,h.hexdigest()

def replay(db):
    m=sa.verify_sources();results=[]
    for s in m['sources']:
        path=sa.SOURCES/s['path'];cc=s['country'];source=s['id'];kind=s['kind']
        if kind=='geonames':
            expected=(dict(zip(sa.GN_FIELDS,r)) for r in sa.zip_rows(path,cc))
            actual=(json.loads(r[0]) for r in db.execute('SELECT source_json FROM records WHERE source=? ORDER BY rid',(source,)))
        elif kind=='names':
            parent=cc.lower()+'-geonames-geonames'
            ids={r[0] for r in db.execute('SELECT source_id FROM records WHERE source=?',(parent,))}
            expected=(dict(zip(sa.NAME_FIELDS,r)) for r in sa.zip_rows(path,cc) if r[1] in ids)
            actual=(json.loads(r[0]) for r in db.execute('SELECT n.source_json FROM names n JOIN records r ON n.rid=r.rid WHERE r.source=? AND n.source_json IS NOT NULL ORDER BY n.rowid',(parent,)))
        elif kind=='georef':
            obj=sa.read_json(path);key='provincias' if source.endswith('provincias') else 'localidades'
            expected=iter(obj[key])
            actual=(json.loads(r[0]) for r in db.execute('SELECT source_json FROM records WHERE source=? ORDER BY rid',(source,)))
        else:
            # Consume source before closing the gzip file.
            with gzip.open(path,'rt',encoding='utf-8-sig',newline='') as f:
                original=digest_rows(csv.DictReader(f,delimiter=';'))
            actual=(json.loads(r[0]) for r in db.execute('SELECT source_json FROM records WHERE source=? ORDER BY rid',(source,)))
            reconstructed=digest_rows(actual)
            if original!=reconstructed:raise ValueError('BAN raw row replay mismatch')
            results.append({'source':source,'replayed_rows':original[0],'canonical_sha256':original[1],'status':'PASS'})
            continue
        original=digest_rows(expected);reconstructed=digest_rows(actual)
        if original!=reconstructed:raise ValueError('Source replay mismatch: '+source)
        results.append({'source':source,'replayed_rows':original[0],'canonical_sha256':original[1],'status':'PASS'})
    return results

def real_queries(db):
    reports=[]
    for cc in sa.profiles():
        layer='feature' if cc=='BV' else 'place'
        # Pick an eligible observed row; tests demonstrate reference retrieval, not correctness on the ground.
        row=db.execute('SELECT * FROM records WHERE country=? AND layer=? AND historic=0 AND source_country=country AND latitude IS NOT NULL AND length(name) BETWEEN 6 AND 35 ORDER BY length(name) DESC,record_key LIMIT 1',(cc,layer)).fetchone()
        if row is None:raise ValueError('No eligible reference for '+cc)
        search=sa.search(db,cc,row['name'],layer=layer,limit=100,name_view='source')
        if row['record_key'] not in {r['record_key'] for r in search['results']}:raise ValueError('Reference name retrieval failed: '+cc)
        reverse=sa.reverse(db,cc,row['latitude'],row['longitude'],layer=layer,radius_m=1,limit=100)
        if row['record_key'] not in {r['record_key'] for r in reverse['results']}:raise ValueError('Reference point retrieval failed: '+cc)
        reports.append({'country':cc,'layer':layer,'record_key':row['record_key'],'name_query':'PASS','point_query':'PASS'})
    row=db.execute("SELECT * FROM records WHERE source='gf-ban-973' AND precision='ban:entrée' AND latitude IS NOT NULL ORDER BY record_key LIMIT 1").fetchone()
    raw=json.loads(row['source_json'])
    search=sa.search(db,'GF',row['name'],layer='address',limit=100)
    if row['record_key'] not in {r['record_key'] for r in search['results']}:raise ValueError('BAN forward reference query failed')
    reverse=sa.reverse(db,'GF',row['latitude'],row['longitude'],layer='address',radius_m=1,limit=100)
    if row['record_key'] not in {r['record_key'] for r in reverse['results']}:raise ValueError('BAN reverse reference query failed')
    if any(r['delivery_verified'] or r['unit_verified'] for r in reverse['results']):raise ValueError('Invalid verification upgrade')
    reports.append({'country':'GF','layer':'address','record_key':row['record_key'],'name_query':'PASS','point_query':'PASS'})
    return reports

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db',type=Path,default=sa.DEFAULT_DB)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    suite=unittest.defaultTestLoader.discover(str(sa.ROOT.parent/'tests'),pattern='test_southamerica.py')
    tests=unittest.TextTestRunner(verbosity=1).run(suite)
    if not tests.wasSuccessful():raise SystemExit(1)
    with sa.open_database(args.db) as db:
        results=replay(db)
        queries=real_queries(db)
        summary={r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM metadata')}
        foreign_keys=db.execute('PRAGMA foreign_key_check').fetchall()
        if foreign_keys:raise ValueError('Orphan index row')
        integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
        if integrity!='ok':raise ValueError('SQLite integrity error')
    report={'status':'PASS','checked_at':datetime.now(timezone.utc).isoformat(),
      'behavior_tests':tests.testsRun,'failures':0,'source_replays':results,'real_data_queries':queries,
      'build_summary':summary,'foreign_key_check':'PASS','sqlite_integrity_check':'PASS',
      'limit':'Checks verify faithfully indexed source snapshots and behavior, not real-world coverage, location accuracy or postal deliverability.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'PASS','behavior_tests':tests.testsRun,'source_replays':len(results),'real_data_query_pairs':len(queries)},ensure_ascii=False))

if __name__=='__main__':main()
