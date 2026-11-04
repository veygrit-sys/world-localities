#!/usr/bin/env python3
"""Replay source records independently, exercise real queries, and emit country audit reports."""
from __future__ import annotations
import argparse,csv,hashlib,io,itertools,json,re,sqlite3,sys,unittest
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import centralamerica as h
import centralamerica_common as common


def check(condition,message):
    if not condition:raise ValueError(message)


def csv_source(source):
    return common.csv_rows(source['local_path'],source.get('member'),source.get('delimiter',','),source.get('encoding','utf-8-sig'))


def expected_observations(source):
    sid=source['id'];cc=source['country']
    if sid.endswith('-geonames-geonames'):
        for ordinal,row in enumerate(common.zip_rows(source['local_path'],cc),1):
            check(len(row)==19,'Malformed GeoNames geographic row')
            r=dict(zip(common.GN_FIELDS,row))
            if r['country_code']==cc and ((r['feature_class']=='P' and r['feature_code'] not in common.HISTORIC_FEATURES) or re.fullmatch(r'ADM[1-4]',r['feature_code'])):
                yield ordinal,'gn:'+r['geonameid'],r
    elif sid in ('gn-admin1CodesASCII','gn-admin2Codes'):
        for ordinal,row in enumerate(csv.reader(io.StringIO(common.decoded(source['local_path']).decode('utf-8')),delimiter='\t'),1):
            if row[0].split('.')[0] in h.ALL_SCOPES:yield ordinal,'gn:'+row[3],row
    elif source.get('layers'):
        for layer in source['layers']:
            level=layer['level'];rows=list(common.xlsx_rows(source['local_path'],layer['sheet']))
            code_counts=Counter(r['pcode'] for _,r in rows) if level==5 else Counter()
            for rownum,r in rows:
                code=r['pcode'] if level==5 else r[f'adm{level}_pcode']
                node=source['namespace']+(':'+('place' if level==5 else 'adm'+str(level))+':')+code
                if level==5 and code_counts[code]>1:node+=':row:'+str(rownum)
                yield level*1000000+rownum,node,{'sheet':layer['sheet'],'row':rownum,'fields':r}
    else:raise ValueError('No independent replay recipe: '+sid)


def replay_source(db,source):
    actual=db.execute('SELECT ordinal,node,raw_json FROM observations WHERE source=? ORDER BY ordinal',(source['id'],))
    hasher=hashlib.sha256();count=0
    for expected,row in itertools.zip_longest(expected_observations(source),actual):
        check(expected is not None and row is not None,'Observation count mismatch: '+source['id'])
        got=(row['ordinal'],row['node'],json.loads(row['raw_json']))
        check(got==expected,'Observation mismatch: '+source['id']+':'+str(expected[0]))
        hasher.update(json.dumps(expected,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()+b'\n');count+=1
    return {'source':source['id'],'rows':count,'canonical_row_sha256':hasher.hexdigest(),'status':'PASS'}


def replay_names(db,source,node_ids):
    def expected():
        for row in common.zip_rows(source['local_path'],source['country']):
            check(8<=len(row)<=10,'Malformed alternate-name row')
            r=dict(zip(common.NAME_FIELDS,row+['']*(10-len(row))))
            node='gn:'+r['geonameid']
            if node in node_ids and r['language'] not in common.NON_NAME_TAGS and not common.historical_or_time_bounded_name(r):
                yield node,r['name'],r['language'] or None
    actual=db.execute('SELECT node,name,language FROM names WHERE source=? ORDER BY rowid',(source['id'],))
    count=0;hasher=hashlib.sha256()
    for exp,row in itertools.zip_longest(expected(),actual):
        check(exp is not None and row is not None and tuple(row)==exp,'Alternate-name replay mismatch: '+source['id'])
        hasher.update(json.dumps(exp,ensure_ascii=False,separators=(',',':')).encode()+b'\n');count+=1
    return {'source':source['id'],'rows':count,'canonical_row_sha256':hasher.hexdigest(),'status':'PASS'}


def real_checks(db):
    checks=[]
    examples=[
      ('BZ',['codab-bz-v01:adm1:BZ02'],'Cayo','source_path_consistent'),
      ('GT',['codab-gt-v01:adm1:GT01','codab-gt-v01:adm2:GT0101'],'Guatemala','source_path_consistent'),
      ('SV',['codab-sv-v02:adm1:SV10','codab-sv-v02:adm2:SV10001','codab-sv-v02:adm3:SV10001005'],'San Salvador','source_path_consistent'),
      ('HN',['codab-hn-v01:adm1:HN08','codab-hn-v01:adm2:HN0801','codab-hn-v01:place:HN080101001'],'Distrito Central','source_path_consistent'),
      ('NI',['codab-ni-v02:adm1:NI55','codab-ni-v02:adm2:NI5525'],'Managua','source_path_consistent'),
      ('CR',['codab-cr-v01:adm1:CR6','codab-cr-v01:adm2:CR612','codab-cr-v01:adm3:CR61201'],'Monteverde','source_path_consistent'),
      ('PA',['codab-pa-v01:adm1:PA12','codab-pa-v01:adm2:PA1204'],'Panama','review_required')]
    for cc,path,text,status in examples:
        node=path[-1];p=['scope:'+cc]+path
        result=h.validate_path(db,cc,p);check(result['status']==status,'Real hierarchy failed: '+cc)
        row=db.execute('SELECT namespace,kind FROM nodes WHERE id=?',(node,)).fetchone()
        search=h.search(db,cc,text,namespace=row['namespace'],kind=row['kind'],parent=p[-2],limit=100)
        check(node in {r['id'] for r in search['results']},'Real search failed: '+cc)
        check(not result['address_verified'] and not result['delivery_verified'],'False address assurance')
        checks.append({'country':cc,'path':p,'query':text,'expected_path_status':status,'status':'PASS'})
    wrong=h.validate_path(db,'SV',['scope:SV','codab-sv-v02:adm2:SV10002','codab-sv-v02:adm3:SV10001005'])
    check(wrong['status']=='review_required','Wrong municipality accepted')
    for node in ['codab-gt-v01:adm2:GT0100','codab-sv-v02:adm2:SV03999','codab-sv-v02:adm3:SV03999001']:
        check(h.hierarchy(db,node)['node']['kind']=='cartographic_water_area','Water feature treated as municipality')
    duplicate_rows=db.execute("SELECT count(*) FROM issues WHERE code='duplicate_source_pcode'").fetchone()[0]
    duplicate_codes=db.execute("SELECT count(DISTINCT raw_value) FROM issues WHERE code='duplicate_source_pcode'").fetchone()[0]
    check((duplicate_codes,duplicate_rows)==(20,40),'Honduras duplicate-code audit changed')
    a=h.hierarchy(db,'codab-hn-v01:place:HN020831003:row:1569');b=h.hierarchy(db,'codab-hn-v01:place:HN020831003:row:1571')
    check(a['node']['name']!=b['node']['name'] and a['status']==b['status']=='review_required','Ambiguous code merged or unflagged')
    check(h.hierarchy(db,'codab-cr-v01:adm2:CR613')['node']['name']=='Puerto Jiménez','Recent Costa Rica canton absent')
    check(h.hierarchy(db,'gn:12508964')['status']=='review_required','Naso administrative level difference suppressed')
    check(common.postcode_review('NI','12005')['status']=='matches_syntax_only','Obsolete Nicaragua postal syntax used')
    check(common.postcode_review('PA','0801')['status']=='review_required','Panama postal transition ignored')
    for cc in h.COUNTRIES:
        row=db.execute("SELECT id FROM nodes WHERE country=? AND namespace='geonames' AND kind='place' ORDER BY id LIMIT 1",(cc,)).fetchone()
        check(row and 'scope:'+cc in {r['id'] for r in h.ancestors(db,row['id'])},'Country-scoped place missing: '+cc)
    return {'country_queries':checks,'wrong_municipality_rejected':True,'cartographic_water_features_separated':True,
            'honduras_duplicate_codes':duplicate_codes,'honduras_ambiguous_rows':duplicate_rows,
            'costa_rica_new_cantons_present':True,'panama_currentness_issues_visible':True,'all_country_place_checks':len(h.COUNTRIES)}


def validate(db_path,output):
    # Test the installed implementation even when sources live in a restored archive.
    installed_tests=Path(__file__).resolve().parents[2]/'hierarchy-tests'
    tests=installed_tests if installed_tests.is_dir() else common.ROOT.parent/'tests'
    pattern='test_hierarchy_central_america_centralamerica.py' if installed_tests.is_dir() else 'test_centralamerica.py'
    suite=unittest.defaultTestLoader.discover(str(tests),pattern=pattern)
    check(suite.countTestCases()>0,'No behavior tests discovered')
    output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    reports_root=output.parent
    # Fresh reports belong beside this run's output, never over accepted historical reports.
    test_result=unittest.TextTestRunner(verbosity=2).run(suite)
    check(test_result.wasSuccessful(),'Behavior tests failed')
    sources=h.source_registry();results=[];name_results=[]
    for cc in h.COUNTRIES:
        m=common.read_json(sources[cc.lower()+'-codab-metadata']['local_path'])
        check(m.get('success') and m['result'].get('license_id')=='cc-by-igo','Publisher licence metadata changed')
        gazetteer=sources[cc.lower()+'-codab-gazetteer']
        check(any(r['url']==gazetteer['url'] for r in m['result']['resources']),'Gazetteer no longer linked in source catalogue')
    with h.open_database(db_path) as db:
        structure=h.structural_checks(db);check(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','SQLite integrity failure')
        ids={r[0] for r in db.execute("SELECT id FROM nodes WHERE namespace='geonames'")}
        for sid,s in sources.items():
            if sid.endswith('-geonames-names'):name_results.append(replay_names(db,s,ids))
            elif s.get('selected_for_index'):results.append(replay_source(db,s))
        real=real_checks(db)
        counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['nodes','names','links','observations','issues']}
        check(sum(r['rows'] for r in results)==counts['observations'],'Unreplayed observations')
        expected_source_counts={r['source']:r['rows'] for r in results}
        actual_source_counts=json.loads(db.execute("SELECT value FROM metadata WHERE key='source_observation_counts'").fetchone()[0])
        check(expected_source_counts==actual_source_counts,'Build source count mismatch')
        for scope in ['countries','all']:
            report=h.run_loop(db,scope)
            (reports_root/('CENTRAL_AMERICA_'+scope.upper()+'_LOOP.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        for cc in h.ALL_SCOPES:
            report=h.country_report(db,cc)
            report['issue_records']=[dict(r) for r in db.execute('SELECT i.* FROM issues i JOIN nodes n ON n.id=i.node WHERE n.country=? ORDER BY i.node,i.code',(cc,))]
            folder=reports_root/'reports'/('countries' if cc in h.COUNTRIES else 'supplementary');folder.mkdir(parents=True,exist_ok=True)
            (folder/(cc+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        report={'status':'PASS','checked_at':datetime.now(timezone.utc).isoformat(),'behavior_tests':test_result.testsRun,
                'country_count':len(h.COUNTRIES),'supplementary_area_count':len(h.TERRITORIES),'source_integrity_objects':len(sources),
                'observation_replays':results,'alternate_name_replays':name_results,'structural_checks':structure,'sqlite_integrity':'PASS','real_data_checks':real,'counts':counts,
                'limit':'PASS verifies faithful ingestion and conservative source navigation, not all addresses, physical containment, current postal assignment, or deliverability.'}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return {'status':'PASS','behavior_tests':test_result.testsRun,'source_objects':len(sources),'observation_replays':len(results),'name_replays':len(name_results),'counts':counts}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,default=h.DEFAULT_DB);p.add_argument('--output',type=Path,default=common.ROOT/'generated/central-america-validation/validation.json');args=p.parse_args()
    try:print(json.dumps(validate(args.db,args.output),ensure_ascii=False))
    except (OSError,ValueError,KeyError,sqlite3.Error) as exc:
        print(json.dumps({'status':'FAIL','message':str(exc)},ensure_ascii=False),file=sys.stderr);raise SystemExit(2)

if __name__=='__main__':main()
