#!/usr/bin/env python3
"""Replay source records independently, exercise real queries, and emit country audit reports."""
from __future__ import annotations
import argparse,csv,hashlib,io,itertools,json,re,sqlite3,sys,unittest
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import northamerica as h
import northamerica_common as common


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
    elif sid in ('us-census-state','us-census-counties','us-census-cousubs','us-census-place'):
        kind={'us-census-state':'state','us-census-counties':'county_equivalent','us-census-cousubs':'county_subdivision','us-census-place':'place'}[sid]
        for ordinal,r in enumerate(csv_source(source),1):
            if r['USPS']!='PR':yield ordinal,'us-census-2026:'+kind+':'+r['GEOID'],r
    elif sid.startswith('ca-statcan-sgc-'):
        kinds={1:'geographical_region',2:'province_territory',3:'census_division',4:'census_subdivision'}
        for ordinal,r in enumerate(csv_source(source),1):
            v=list(r.values());yield ordinal,'ca-sgc-2021:'+kinds[int(v[0])]+':'+v[2],r
    elif sid.startswith('mx-inegi-'):
        kind={'mx-inegi-catun_entidad':'state','mx-inegi-catun_municipio':'municipality','mx-inegi-min_con_acento':'locality'}[sid]
        for ordinal,r in enumerate(csv_source(source),1):yield ordinal,'mx-inegi-catalogue:'+kind+':'+r['CVEGEO'],r
    elif sid=='pm-insee-cog-2026':
        for ordinal,r in enumerate(common.csv_rows(source['local_path'],'v_comer_2026.csv'),1):
            if r['COMER']=='975':yield ordinal,'pm-insee-2026:collectivity:975',r
        for ordinal,r in enumerate(common.csv_rows(source['local_path'],'v_commune_comer_2026.csv'),10001):
            if r['COMER']=='975':yield ordinal,'pm-insee-2026:commune:'+r['COM_COMER'],r
    elif sid=='ca-statcan-oda-nt':
        for ordinal,r in enumerate(csv_source(source),1):yield ordinal,'ca-oda-2021:address:'+r['id'],r
    elif sid=='pm-ban-975':
        for ordinal,r in enumerate(csv_source(source),1):yield ordinal,'pm-ban:address:'+r['id'],r
    elif sid in ('us-census-dc-addr','us-census-dc-featnames'):
        for ordinal,r in enumerate(common.dbf_rows(source['local_path']),1):
            if sid.endswith('addr'):yield ordinal,'us-census-2026:dc-range:'+r['ARID'],r
            elif r['MTFCC'].startswith('S') and r['FULLNAME']:yield ordinal,'us-census-2026:dc-street:'+r['LINEARID'],r
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
    results=[]
    examples=[('US','us-census-2026:state:36','us-census-2026:place:3651000','New York'),
              ('CA','ca-sgc-2021:province_territory:24','ca-sgc-2021:census_subdivision:2466023','Montreal'),
              ('MX','mx-inegi-catalogue:state:09','mx-inegi-catalogue:municipality:09015','Cuauhtemoc'),
              ('PM','pm-insee-2026:collectivity:975','pm-insee-2026:commune:97502','Saint-Pierre')]
    for cc,parent,node,text in examples:
        r=h.validate_path(db,cc,['scope:'+cc,parent,node]);check(r['status']=='source_path_consistent','Real hierarchy failed '+cc)
        ns=db.execute('SELECT namespace,kind FROM nodes WHERE id=?',(node,)).fetchone()
        q=h.search(db,cc,text,namespace=ns['namespace'],kind=ns['kind'],parent=parent,limit=100)
        check(node in {n['id'] for n in q['results']},'Real search failed '+cc)
        results.append({'country':cc,'node':node,'query':text,'status':'PASS'})
    wrong=h.validate_path(db,'US',['scope:US','us-census-2026:state:06','us-census-2026:place:3651000'])
    check(wrong['status']=='review_required','Wrong state accepted')
    check('us-census-2026:county_equivalent:36061' not in {r['id'] for r in h.ancestors(db,'us-census-2026:place:3651000')},'NYC was assigned one invented county')
    check(h.names(db,'ca-sgc-2021:province_territory:24','fr')['results'][0]['name']=='Québec','French diacritics lost')
    check(h.postal_records(db,'PM','97500')['results'],'BAN postal observations missing')
    check(db.execute("SELECT count(*) FROM nodes WHERE namespace='us-census-2026' AND kind='state'").fetchone()[0]==51,'US scope must be 50 states plus DC')
    check(db.execute("SELECT count(*) FROM nodes WHERE namespace='ca-sgc-2021' AND kind='province_territory'").fetchone()[0]==13,'Canada province/territory count')
    check(db.execute("SELECT count(*) FROM nodes WHERE namespace='mx-inegi-catalogue' AND kind='state'").fetchone()[0]==32,'Mexico state count')
    fixture_checks={}
    for source,cc in [('ca-statcan-oda-nt','CA'),('pm-ban-975','PM'),('us-census-dc-addr','US')]:
        total=0;direct_links=0;issue_nodes=0
        for r in db.execute('SELECT node FROM observations WHERE source=?',(source,)):
            total+=1
            links=db.execute('SELECT parent FROM links WHERE child=?',(r['node'],)).fetchall()
            direct_links+=bool(links)
            issue_nodes+=bool(db.execute('SELECT 1 FROM issues WHERE node=?',(r['node'],)).fetchone())
        check(total>0 and total==direct_links,'Fixture parent links missing '+source)
        fixture_checks[source]={'observations':total,'with_parent_links':direct_links,'direct_issue_nodes':issue_nodes}
    for cc in h.ALL_SCOPES:
        row=db.execute("SELECT id FROM nodes WHERE country=? AND namespace='geonames' AND kind='place' ORDER BY id LIMIT 1",(cc,)).fetchone()
        check(row is not None,'No real GeoNames place in '+cc)
        check(any(r['id']=='scope:'+cc for r in h.ancestors(db,row['id'])),'GeoNames country link absent '+cc)
    return {'official_queries':results,'wrong_state_rejected':True,'city_county_relation_not_fabricated':True,'fixture_checks':fixture_checks,'all_scope_geonames_checks':len(h.ALL_SCOPES)}


def validate(db_path,output):
    suite=unittest.defaultTestLoader.discover(str(common.ROOT.parent/'tests'),pattern='test_northamerica.py')
    test_result=unittest.TextTestRunner(verbosity=2).run(suite)
    check(test_result.wasSuccessful(),'Behavior tests failed')
    sources=h.source_registry();results=[];name_results=[]
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
        for scope in ['countries','territories','all']:
            report=h.run_loop(db,scope)
            (common.ROOT/('NORTH_AMERICA_'+scope.upper()+'_LOOP.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        for cc in h.ALL_SCOPES:
            report=h.country_report(db,cc)
            report['issue_records']=[dict(r) for r in db.execute('SELECT i.* FROM issues i JOIN nodes n ON n.id=i.node WHERE n.country=? ORDER BY i.node,i.code',(cc,))]
            folder=common.ROOT/'reports'/('countries' if cc in h.COUNTRIES else 'supplementary');folder.mkdir(parents=True,exist_ok=True)
            (folder/(cc+'.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        report={'status':'PASS','checked_at':datetime.now(timezone.utc).isoformat(),'behavior_tests':test_result.testsRun,
                'country_count':len(h.COUNTRIES),'supplementary_area_count':len(h.TERRITORIES),'source_integrity_objects':len(sources),
                'observation_replays':results,'alternate_name_replays':name_results,'structural_checks':structure,'sqlite_integrity':'PASS','real_data_checks':real,'counts':counts,
                'limit':'PASS verifies faithful ingestion and conservative source navigation, not all addresses, physical containment, current postal assignment, or deliverability.'}
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return {'status':'PASS','behavior_tests':test_result.testsRun,'source_objects':len(sources),'observation_replays':len(results),'name_replays':len(name_results),'counts':counts}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,default=h.DEFAULT_DB);p.add_argument('--output',type=Path,default=common.ROOT/'NORTH_AMERICA_VALIDATION.json');args=p.parse_args()
    try:print(json.dumps(validate(args.db,args.output),ensure_ascii=False))
    except (OSError,ValueError,KeyError,sqlite3.Error) as exc:
        print(json.dumps({'status':'FAIL','message':str(exc)},ensure_ascii=False),file=sys.stderr);raise SystemExit(2)

if __name__=='__main__':main()
