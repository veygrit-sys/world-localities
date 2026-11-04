#!/usr/bin/env python3
"""Replay source records independently, exercise real queries, and emit country audit reports."""
from __future__ import annotations
import argparse,csv,hashlib,io,itertools,json,re,sqlite3,sys,unittest
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import caribbean_hierarchy as h
import caribbean_common as common


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
            if r['country_code']==cc and ((r['feature_class']=='P' and r['feature_code'] not in common.HISTORIC_FEATURES) or re.fullmatch(r'ADM[1-5]',r['feature_code'])):
                yield ordinal,'gn:'+r['geonameid'],r
    elif sid in ('gn-admin1CodesASCII','gn-admin2Codes'):
        for ordinal,row in enumerate(csv.reader(io.StringIO(common.decoded(source['local_path']).decode('utf-8')),delimiter='\t'),1):
            if row[0].split('.')[0] in h.ALL_SCOPES:yield ordinal,'gn:'+row[3],row
    elif sid=='gn-adminCode5':
        import zipfile
        ids=set()
        for country in h.ALL_SCOPES:
            for row in common.zip_rows(common.SOURCES/country/'geonames.zip',country):
                if row[8]==country and ((row[6]=='P' and row[7] not in common.HISTORIC_FEATURES) or re.fullmatch('ADM[1-5]',row[7])):ids.add(row[0])
        with zipfile.ZipFile(source['local_path']) as z:
            rows=csv.reader(io.StringIO(z.read('adminCode5.txt').decode('utf-8')),delimiter='\t')
            for ordinal,row in enumerate(rows,1):
                if row[0] in ids:yield ordinal,'gn:'+row[0],row
    elif source.get('layers'):
        for layer in source['layers']:
            level=layer['level']
            if 'sheet' in layer:rows=common.xlsx_rows(source['local_path'],layer['sheet']);container={'sheet':layer['sheet']}
            else:rows=enumerate(common.dbf_rows(source['local_path'],layer['member']),1);container={'member':layer['member']}
            for rownum,r in rows:
                node=source['namespace']+':adm'+str(level)+':'+r[layer['code_field']]
                yield level*1000000+rownum,node,{**container,'row':rownum,'fields':r}
    elif sid=='fr-insee-cog-2026':
        files=[('v_region_2026.csv','region','REG'),('v_departement_2026.csv','department_code','DEP'),
          ('v_ctcd_2026.csv','departmental_authority','CTCD'),('v_arrondissement_2026.csv','arrondissement','ARR'),
          ('v_commune_2026.csv','commune','COM'),('v_comer_2026.csv','collectivity','COMER'),
          ('v_commune_comer_2026.csv','collectivity','COMER')]
        for number,(member,kind,field) in enumerate(files,1):
            for ordinal,r in enumerate(common.csv_rows(source['local_path'],member),2):
                country={'977':'BL','978':'MF'}.get(r.get('COMER')) if number>=6 else {'01':'GP','02':'MQ'}.get(r.get('REG'))
                if country:
                    node='insee-2026:'+country+':'+kind+':'+r[field]
                    yield number*1000000+ordinal,node,{'member':member,'row':ordinal,'fields':r}
    elif sid.startswith('pr-census-'):
        kind={'state':'territory','counties':'municipio','cousubs':'barrio_or_barrio_pueblo','place':'census_place'}[sid.removeprefix('pr-census-')]
        for ordinal,r in enumerate(csv_source(source),1):
            if r['USPS']=='PR':yield ordinal,'pr-census-2026:'+kind+':'+r['GEOID'],r
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
    examples=[('AG','3576022','Saint John'),('BS','3571824','Nassau'),('BB','3374036','Bridgetown'),
      ('CU','3553478','Havana'),('DM','3575635','Roseau'),('DO','3492908','Santo Domingo'),
      ('GD','3579925','Saint George'),('HT','3718426','Port-au-Prince'),('JM','3489854','Kingston'),
      ('KN','3575551','Basseterre'),('LC','3576812','Castries'),('VC','3577887','Kingstown'),('TT','3573890','Port of Spain'),
      ('AI','3573374','The Valley'),('AW','3577154','Oranjestad'),('BQ','3513563','Kralendijk'),('VG','3577430','Road Town'),
      ('KY','3580661','George Town'),('CW','3513090','Willemstad'),('GP','3579732','Basse-Terre'),('MQ','3570675','Fort-de-France'),
      ('MS','3578069','Plymouth'),('PR','4568127','San Juan'),('BL','3579132','Gustavia'),('MF','3578851','Marigot'),
      ('SX','3513392','Philipsburg'),('TC','3576994','Cockburn Town'),('VI','4795467','Charlotte Amalie')]
    checks=[]
    for cc,geoid,text in examples:
        node='gn:'+geoid;query=h.search(db,cc,text,namespace='geonames',kind='place',limit=100)
        check(node in {r['id'] for r in query['results']},'Real source search failed: '+cc)
        path=['scope:'+cc,node];result=h.validate_path(db,cc,path)
        check('scope:'+cc in {r['id'] for r in h.ancestors(db,node)},'Missing country root: '+cc)
        expected='review_required' if cc in ('DO','JM','MS') else 'source_path_consistent'
        check(result['status']==expected,'Unexpected real place review status: '+cc)
        checks.append({'country':cc,'id':node,'query':text,'path_status':result['status'],'status':'PASS'})
    for scope,expected in [('countries',h.COUNTRIES),('territories',h.TERRITORIES),('all',h.ALL_SCOPES)]:
        report=h.run_loop(db,scope);check([r['code'] for r in report['countries']]==list(expected),'Loop scope/order mismatch')
    five=h.hierarchy(db,'gn:10860589')
    check(any(x['id']=='gn:11168828' and x['kind']=='admin5' for x in five['ancestors']),'ADM5 parent missing')
    check(any(x['kind']=='admin4' for x in five['ancestors']),'ADM4 above ADM5 missing')
    check(db.execute("SELECT count(*) FROM nodes WHERE country='DO' AND kind='admin5'").fetchone()[0]==12565,'ADM5 source inventory changed')
    check(db.execute("SELECT count(*) FROM links WHERE relation='admin5'").fetchone()[0]==7603,'ADM5 place links changed')
    check(db.execute("SELECT count(*) FROM nodes WHERE country='BQ' AND kind='country'").fetchone()[0]==0,'BQ islands counted as sovereign')
    check(db.execute("SELECT count(*) FROM nodes WHERE country='BQ' AND namespace='geonames' AND kind='admin1'").fetchone()[0]==3,'BQ island reference missing')
    cw=h.hierarchy(db,'codab-cw-20261017:adm1:-')
    check(cw['node']['kind']=='non_geographic_reporting_category' and cw['status']=='review_required','CW non-geographic category misclassified')
    check(db.execute("SELECT count(*) FROM nodes WHERE country='CW' AND kind='source_adm1_area'").fetchone()[0]==65,'CW incorrect area count')
    for cc,code in [('BL','977'),('MF','978')]:
        id='insee-2026:'+cc+':collectivity:'+code
        check(db.execute('SELECT count(*) FROM observations WHERE node=?',(id,)).fetchone()[0]==2,'Collectivity alias observation missing')
        check(db.execute("SELECT count(*) FROM nodes WHERE country=? AND namespace='insee-2026'",(cc,)).fetchone()[0]==1,'Invented lower collectivity tier')
    path=['scope:GP','insee-2026:GP:region:01','insee-2026:GP:department_code:971','insee-2026:GP:arrondissement:9711','insee-2026:GP:commune:97105']
    check(h.validate_path(db,'GP',path)['status']=='source_path_consistent','COG commune path broken')
    wrong=['scope:GP','insee-2026:GP:arrondissement:9712','insee-2026:GP:commune:97105']
    check(h.validate_path(db,'GP',wrong)['status']=='review_required','Wrong COG arrondissement accepted')
    authority=h.hierarchy(db,'insee-2026:MQ:commune:97209')
    check(any(a['id']=='insee-2026:MQ:departmental_authority:972R' for a in authority['ancestors']),'Martinique single authority branch missing')
    crossed=h.validate_path(db,'MF',['scope:MF','gn:3513392'])
    check('country_mismatch' in crossed['problems'],'MF/SX merged')
    pr=['scope:PR','pr-census-2026:territory:72','pr-census-2026:municipio:72001','pr-census-2026:barrio_or_barrio_pueblo:7200100401']
    check(h.validate_path(db,'PR',pr)['status']=='source_path_consistent','PR barrio path broken')
    pr_place=h.hierarchy(db,'pr-census-2026:census_place:7200186')
    check(not any(a['kind']=='municipio' for a in pr_place['ancestors']),'Census place falsely linked to municipio')
    check(pr_place['supplied_code_checks']==[{'field':'municipio','status':'not_supplied','raw_value':''}],'Missing municipio evidence lost')
    check(db.execute("SELECT count(*) FROM nodes WHERE namespace='pr-census-2026' AND country<>'PR'").fetchone()[0]==0,'Census PR source applied to another area')
    check(h.hierarchy(db,'codab-do-v01:adm3:DO010102')['status']=='review_required','DO currentness gap hidden')
    return {'all_scope_queries':checks,'loop_scope_counts':{'countries':13,'territories':15,'all':28},'adm5_nodes':12565,'adm5_place_links':7603,
      'bq_single_scope_three_islands':True,'cw_65_areas_plus_one_nongeographic_category':True,'french_collectivity_aliases_not_extra_communes':True,
      'french_and_dutch_saint_martin_separate':True,'cog_parallel_authority_branch_verified':True,'pr_barrio_parentage_verified':True,
      'pr_place_municipio_not_inferred':True,'do_currentness_gap_visible':True}


def validate(db_path,output):
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[2]/'hierarchy-tests'),pattern='test_hierarchy_caribbean.py')
    test_result=unittest.TextTestRunner(verbosity=2).run(suite)
    check(test_result.wasSuccessful(),'Behavior tests failed')
    sources=h.source_registry();results=[];name_results=[]
    for cc in [s['country'] for s in sources.values() if s['id'].endswith('-codab-metadata')]:
        m=common.read_json(sources[cc.lower()+'-codab-metadata']['local_path'])
        check(m.get('success') and m['result'].get('license_id')=='cc-by-igo','Publisher licence metadata changed')
        gazetteer=sources[cc.lower()+'-codab-gazetteer']
        check(any(r['url']==gazetteer['url'] for r in m['result']['resources']),'Gazetteer no longer linked in source catalogue')
    with h.open_database(db_path) as db:
        structure=h.structural_checks(db);check(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','SQLite integrity failure')
        ids={cc:{r[0] for r in db.execute("SELECT id FROM nodes WHERE namespace='geonames' AND country=?",(cc,))} for cc in h.ALL_SCOPES}
        for sid,s in sources.items():
            if sid.endswith('-geonames-names'):name_results.append(replay_names(db,s,ids[s['country']]))
            elif s.get('selected_for_index'):results.append(replay_source(db,s))
        real=real_checks(db)
        counts={t:db.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['nodes','names','links','observations','issues']}
        check(sum(r['rows'] for r in results)==counts['observations'],'Unreplayed observations')
        expected_source_counts={r['source']:r['rows'] for r in results if r['rows']}
        actual_source_counts=json.loads(db.execute("SELECT value FROM metadata WHERE key='source_observation_counts'").fetchone()[0])
        check(expected_source_counts==actual_source_counts,'Build source count mismatch')
        for scope in ['countries','territories','all']:
            report=h.run_loop(db,scope)
            (common.ROOT/('CARIBBEAN_'+scope.upper()+'_LOOP.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,default=h.DEFAULT_DB);p.add_argument('--output',type=Path,default=common.ROOT/'CARIBBEAN_VALIDATION.json');args=p.parse_args()
    try:print(json.dumps(validate(args.db,args.output),ensure_ascii=False))
    except (OSError,ValueError,KeyError,sqlite3.Error) as exc:
        print(json.dumps({'status':'FAIL','message':str(exc)},ensure_ascii=False),file=sys.stderr);raise SystemExit(2)

if __name__=='__main__':main()
