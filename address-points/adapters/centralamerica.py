#!/usr/bin/env python3
"""Source-qualified Central America hierarchy. Python 3.10+, standard library."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import sys
import zipfile

import centralamerica_common as sa

ROOT = sa.ROOT
DEFAULT_DB = ROOT / 'generated/central_america_hierarchy.sqlite'
COUNTRIES = ('BZ','GT','SV','HN','NI','CR','PA')
TERRITORIES = ()
ALL_SCOPES = COUNTRIES + TERRITORIES
VERSION = 1


def digest(value):
    return hashlib.sha256(sa.dump(value).encode()).hexdigest()


def decoded(path):
    b = Path(path).read_bytes()
    return gzip.decompress(b) if b[:2] == b'\x1f\x8b' else b


def read_data(path):
    return json.loads(decoded(path))


def source_registry(verify=True):
    manifest=sa.verify_sources() if verify else sa.read_json(ROOT/'CENTRAL_AMERICA_SOURCES.json')
    return {s['id']:{**s,'local_path':sa.SOURCES/s['path']} for s in manifest['sources']}


def inputs_fingerprint():
    return digest({name:sa.file_hash(ROOT/name) for name in [
        'CENTRAL_AMERICA_SOURCES.json',
        'CENTRAL_AMERICA_RULES.json','CENTRAL_AMERICA_SCOPE.json']})


def schema(db):
    db.executescript('''
    PRAGMA foreign_keys=ON;
    CREATE TABLE nodes(id TEXT PRIMARY KEY,country TEXT NOT NULL,namespace TEXT NOT NULL,
      kind TEXT NOT NULL,rank INTEGER NOT NULL,code TEXT NOT NULL,name TEXT NOT NULL,
      lookup TEXT NOT NULL,source TEXT NOT NULL,raw_json TEXT NOT NULL);
    CREATE TABLE names(node TEXT NOT NULL REFERENCES nodes(id),name TEXT NOT NULL,
      lookup TEXT NOT NULL,language TEXT,source TEXT NOT NULL);
    CREATE TABLE observations(source TEXT NOT NULL,ordinal INTEGER NOT NULL,
      node TEXT NOT NULL REFERENCES nodes(id),raw_json TEXT NOT NULL,
      PRIMARY KEY(source,ordinal));
    CREATE TABLE links(child TEXT NOT NULL REFERENCES nodes(id),parent TEXT NOT NULL REFERENCES nodes(id),
      relation TEXT NOT NULL,source TEXT NOT NULL,PRIMARY KEY(child,parent,relation));
    CREATE TABLE issues(node TEXT NOT NULL REFERENCES nodes(id),code TEXT NOT NULL,
      field TEXT NOT NULL,raw_value TEXT NOT NULL,candidates_json TEXT NOT NULL);
    CREATE TABLE checks(node TEXT NOT NULL REFERENCES nodes(id),field TEXT NOT NULL,
      status TEXT NOT NULL,raw_value TEXT NOT NULL,PRIMARY KEY(node,field));
    CREATE TABLE postal(node TEXT NOT NULL REFERENCES nodes(id),postcode TEXT NOT NULL,
      source TEXT NOT NULL,PRIMARY KEY(node,postcode,source));
    CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE INDEX nodes_scope ON nodes(country,namespace,kind);
    CREATE INDEX names_node ON names(node);
    CREATE INDEX observations_node ON observations(node);
    CREATE INDEX names_lookup ON names(lookup);
    CREATE INDEX links_parent ON links(parent);
    CREATE INDEX issues_node ON issues(node);
    CREATE INDEX checks_node ON checks(node);
    ''')


class Builder:
    def __init__(self, db, registry):
        self.db, self.sources = db, registry
        self.nodes = {}
        self.pending = []
        self.source_counts = Counter()

    def node(self, id, cc, namespace, kind, rank, code, name, source, raw):
        if not isinstance(code,str) or not isinstance(name,str) or not name.strip():
            raise ValueError('Codes and nonempty names must be strings')
        item = (cc,namespace,kind,rank,code,name)
        if id in self.nodes:
            if self.nodes[id] != item:
                self.issue(id,'source_identity_conflict','identity',item,[])
            return id
        self.nodes[id] = item
        self.db.execute('INSERT INTO nodes VALUES(?,?,?,?,?,?,?,?,?,?)',
            (id,cc,namespace,kind,rank,code,name,sa.lookup_key(name),source,sa.dump(raw)))
        self.name(id,name,None,source)
        return id

    def name(self,id,name,language,source):
        self.db.execute('INSERT INTO names VALUES(?,?,?,?,?)',(id,name,sa.lookup_key(name),language,source))

    def observation(self, source, ordinal, node, raw):
        self.db.execute('INSERT INTO observations VALUES(?,?,?,?)',(source,ordinal,node,sa.dump(raw)))
        self.source_counts[source] += 1

    def issue(self,id,code,field,value,candidates):
        self.db.execute('INSERT INTO issues VALUES(?,?,?,?,?)',(id,code,field,sa.dump(value),sa.dump(candidates)))

    def ref(self, child, parent, relation, source):
        self.pending.append((child,parent,relation,source))

    def resolve(self):
        for child,parent,relation,source in self.pending:
            if parent not in self.nodes:
                self.issue(child,'missing_reference',relation,parent,[])
                continue
            c,p = self.nodes[child],self.nodes[parent]
            if c[0] != p[0] or c[3] <= p[3]:
                self.issue(child,'invalid_parent_relation',relation,parent,[])
                continue
            self.db.execute('INSERT OR IGNORE INTO links VALUES(?,?,?,?)',(child,parent,relation,source))

    def roots(self):
        for cc in ALL_SCOPES:
            self.node('scope:'+cc,cc,'scope','country' if cc in COUNTRIES else 'supplementary_area',0,
                cc,sa.profiles()[cc]['name_ja'],'package-scope',{'scope_type':'country' if cc in COUNTRIES else 'supplementary_area'})

    def rows(self,source):
        s=self.sources[source]
        return sa.csv_rows(s['local_path'],s.get('member'),s.get('delimiter',','),s.get('encoding','utf-8-sig'))

    def administrative(self):
        """COD-AB gazetteer relationships, kept separate from GeoNames IDs."""
        for source,s in self.sources.items():
            if not s.get('layers'):continue
            cc=s['country'];namespace=s['namespace'];tuples={};pending=[]
            for layer in s['layers']:
                level=layer['level'];water=set(layer.get('non_administrative_codes',[]))
                count=0;classified=0;seen=set();seen_water=set()
                records=list(sa.xlsx_rows(s['local_path'],layer['sheet']))
                code_counts=Counter(r['pcode'] for _,r in records) if level==5 else Counter()
                for rownum,r in records:
                    if r.get('adm0_pcode')!=cc or r.get('version')!=s['version']:
                        raise ValueError('Country or version mismatch in '+source)
                    code=r['pcode'] if level==5 else r[f'adm{level}_pcode']
                    name=r['featurename_es'] if level==5 else r[f'adm{level}_name']
                    if not code.startswith(cc) or not code.isascii() or (level<5 and code in seen):
                        raise ValueError('Invalid or duplicated P-code in '+layer['sheet'])
                    seen.add(code);count+=1
                    kind='cartographic_water_area' if code in water else layer['kind']
                    if code in water:seen_water.add(code)
                    else:classified+=1
                    id=namespace+(':'+('place' if level==5 else 'adm'+str(level))+':')+code
                    if level==5 and code_counts[code]>1:id+=':row:'+str(rownum)
                    raw={'sheet':layer['sheet'],'row':rownum,'fields':r}
                    self.node(id,cc,namespace,kind,level*10,code,name,source,raw)
                    self.observation(source,level*1000000+rownum,id,raw)
                    if level==5 and code_counts[code]>1:
                        self.issue(id,'duplicate_source_pcode','pcode',code,
                                   [namespace+':place:'+code+':row:'+str(n) for n,a in records if a['pcode']==code])
                    self.name(id,name,'es' if level==5 else r.get('lang') or None,source)
                    refs=['featurerefname','featurealtname1_es','featurealtname2_es'] if level==5 else [f'adm{level}_ref_name',f'adm{level}_name1',f'adm{level}_name2',f'adm{level}_name3']
                    for field in refs:
                        if r.get(field) and r[field]!=name:
                            lang='es' if field.endswith('_es') else None
                            if re.fullmatch(r'adm[1-4]_name[1-3]',field):lang=r.get('lang'+field[-1]) or None
                            self.name(id,r[field],lang,source)
                    self.ref(id,'scope:'+cc,'in_scope',source)
                    ancestors=tuple(r.get(f'adm{k}_pcode','') for k in range(1,3 if level==5 else level+1))
                    if level<5:tuples[(level,code)]=ancestors
                    pending.append((id,level,ancestors,source))
                    if code in water:self.issue(id,'non_administrative_cartographic_feature','pcode',code,[])
                    if r.get('valid_to') or r.get('validto'):self.issue(id,'source_validity_ended','valid_to',r.get('valid_to') or r.get('validto'),[])
                    if cc=='PA' and level==1:
                        self.issue(id,'known_outdated_administrative_snapshot','vintage','COD-AB source 2020; newer IGN division has more districts/corregimientos',[])
                if seen_water!=water:raise ValueError('Reviewed cartographic exception set changed')
                if 'expected_administrative_count' in layer and classified!=layer['expected_administrative_count']:
                    raise ValueError('Administrative count changed; review source before acceptance')
                if 'expected_source_rows' in layer and count!=layer['expected_source_rows']:
                    raise ValueError('Source row count changed; review source before acceptance')
            for id,level,ancestral_codes,source in pending:
                depth=2 if level==5 else level-1
                for k in range(1,depth+1):
                    code=ancestral_codes[k-1]
                    target=namespace+':adm'+str(k)+':'+code
                    expected=ancestral_codes[:k]
                    actual=tuples.get((k,code))
                    if actual is not None and actual!=expected:
                        self.issue(id,'parent_tuple_conflict','adm'+str(k),expected,[actual])
                    else:self.ref(id,target,'adm'+str(k),source)

    def geonames(self):
        admin = defaultdict(list)
        code_only = defaultdict(list)
        raw_nodes = []
        for cc in ALL_SCOPES:
            source = cc.lower()+'-geonames-geonames'
            for ordinal,row in enumerate(sa.zip_rows(self.sources[source]['local_path'],cc),1):
                if len(row)!=len(sa.GN_FIELDS):raise ValueError('Malformed GeoNames source row')
                r = dict(zip(sa.GN_FIELDS,row))
                if r['country_code'] != cc:
                    continue
                fc = r['feature_code']
                if r['feature_class'] == 'P' and fc not in sa.HISTORIC_FEATURES:
                    level,kind = 5,'place'
                elif re.fullmatch('ADM[1-4]',fc):
                    level,kind = int(fc[-1]),'admin'+fc[-1]
                else:
                    continue
                id = 'gn:'+r['geonameid']
                codes = tuple(r['admin'+str(k)] for k in range(1,5))
                self.node(id,cc,'geonames',kind,level*10,r['geonameid'],r['name'],source,r)
                if cc=='CR' and kind=='admin1':
                    self.issue(id,'known_incomplete_administrative_snapshot','namespace','GeoNames: 82 ADM2 / 474 ADM3; COD-AB reference: 84 / 492',[])
                if cc=='PA' and id=='gn:12508964':
                    self.issue(id,'administrative_level_requires_review','feature_code','GeoNames ADM1; IGN describes Naso Tjer Di at district level',[])
                self.observation(source,ordinal,id,r)
                if r['asciiname']:
                    self.name(id,r['asciiname'],None,source)
                raw_nodes.append((id,cc,level,codes,source))
                if level < 5:
                    admin[(cc,level,codes[:level])].append(id)
                    code_only[(cc,level,codes[level-1])].append(id)
        # Supplementary code tables can supply reference-only administrative nodes.
        # An ID already in the country dump must agree with the complete code tuple.
        for level,source in [(1,'gn-admin1CodesASCII'),(2,'gn-admin2Codes')]:
            rows=csv.reader(io.StringIO(decoded(self.sources[source]['local_path']).decode('utf-8')),delimiter='\t')
            for ordinal,row in enumerate(rows,1):
                if len(row)!=4:raise ValueError('Unexpected GeoNames admin table row')
                parts=row[0].split('.');cc=parts[0]
                if cc not in ALL_SCOPES:continue
                if len(parts)!=level+1:raise ValueError('Unexpected admin tuple length')
                codes=tuple(parts[1:]);id='gn:'+row[3]
                if id not in self.nodes:
                    self.node(id,cc,'geonames','admin'+str(level)+'_reference',level*10,row[3],row[1],source,{'fields':row,'code_table_reference_only':True})
                    admin[(cc,level,codes)].append(id);code_only[(cc,level,codes[-1])].append(id)
                    raw_nodes.append((id,cc,level,codes+('',)*(4-level),source))
                elif id not in admin.get((cc,level,codes),[]):
                    self.issue(id,'admin_table_conflict','admin'+str(level),row,admin.get((cc,level,codes),[]))
                self.observation(source,ordinal,id,row)
        # Exact full parent tuple is mandatory; never equate FIPS/ISO/official IDs by appearance.
        for id,cc,level,codes,source in raw_nodes:
            self.ref(id,'scope:'+cc,'in_scope',source)
            specified = False
            for k in range(1,min(level,5)):
                code = codes[k-1]
                if code=='' or (k==1 and code=='00'):
                    self.db.execute('INSERT INTO checks VALUES(?,?,?,?)',(id,'admin'+str(k),'not_supplied',code))
                    continue
                specified = True
                targets = admin.get((cc,k,codes[:k]),[])
                status = 'resolved' if len(targets)==1 else ('ambiguous' if targets else 'unresolved')
                self.db.execute('INSERT INTO checks VALUES(?,?,?,?)',(id,'admin'+str(k),status,code))
                if len(targets)==1:
                    self.ref(id,targets[0],'admin'+str(k),source)
                else:
                    alternatives = targets or code_only.get((cc,k,code),[])
                    reason = 'ambiguous_parent' if targets else ('parent_tuple_conflict' if alternatives else 'missing_reference')
                    self.issue(id,reason,'admin'+str(k),list(codes[:k]),alternatives)
            if level > 1 and not specified and any(key[0]==cc for key in admin):
                self.issue(id,'no_parent_code','admin',list(codes),[])
        # Alternate names stay qualified by source language; identifiers are not names.
        for cc in ALL_SCOPES:
            source=cc.lower()+'-geonames-names'
            for row in sa.zip_rows(self.sources[source]['local_path'],cc):
                if not 8<=len(row)<=10:raise ValueError('Malformed alternate-name row')
                r=dict(zip(sa.NAME_FIELDS,row+['']*(10-len(row))))
                id='gn:'+r['geonameid']
                if id in self.nodes and r['language'] not in sa.NON_NAME_TAGS and not sa.historical_or_time_bounded_name(r):
                    self.name(id,r['name'],r['language'] or None,source)


def structural_checks(db):
    fk=db.execute('PRAGMA foreign_key_check').fetchall()
    bad=db.execute('SELECT l.child,l.parent FROM links l JOIN nodes c ON c.id=l.child JOIN nodes p ON p.id=l.parent WHERE c.country<>p.country OR c.rank<=p.rank').fetchall()
    if fk or bad:raise ValueError('Hierarchy integrity failure')
    # Strictly decreasing rank proves that every parent path is acyclic.
    return {'foreign_keys':'PASS','same_country_links':'PASS','acyclic_rank_order':'PASS'}


def build_database(path=DEFAULT_DB):
    registry=source_registry();path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.building')
    if temp.exists():temp.unlink()
    db=sqlite3.connect(temp)
    # This is a disposable candidate, installed atomically only after all checks.
    db.execute('PRAGMA journal_mode=OFF');db.execute('PRAGMA synchronous=OFF')
    schema(db);b=Builder(db,registry)
    try:
        b.roots();b.geonames()
        b.administrative()
        b.resolve();structural_checks(db)
        metadata={'schema_version':VERSION,'built_at':datetime.now(timezone.utc).isoformat(),
            'input_fingerprint':inputs_fingerprint(),'implementation_sha256':sa.file_hash(Path(__file__)),
            'dependency_sha256':sa.file_hash(Path(sa.__file__)),
            'country_codes':list(COUNTRIES),'supplementary_area_codes':list(TERRITORIES),
            'source_observation_counts':dict(b.source_counts),'national_coverage_verified':False,
            'delivery_verified':False,'identity_policy':'Namespaced original IDs; no cross-source name/coordinate merge'}
        for k,v in metadata.items():db.execute('INSERT INTO metadata VALUES(?,?)',(k,sa.dump(v)))
        db.commit();db.close();temp.replace(path)
    except BaseException:
        db.close()
        if temp.exists():temp.unlink()
        raise
    return {'status':'PASS','db':str(path),'nodes':len(b.nodes),'countries':len(COUNTRIES),'supplementary_areas':len(TERRITORIES),
            'source_observation_counts':dict(b.source_counts)}


def open_database(path=DEFAULT_DB):
    if not Path(path).is_file():raise ValueError('Run centralamerica.py build first')
    db=sqlite3.connect('file:'+str(Path(path).resolve())+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    metadata={r['key']:json.loads(r['value']) for r in db.execute('SELECT * FROM metadata')}
    if metadata['schema_version']!=VERSION or metadata['input_fingerprint']!=inputs_fingerprint() or metadata['implementation_sha256']!=sa.file_hash(Path(__file__)) or metadata.get('dependency_sha256')!=sa.file_hash(Path(sa.__file__)):
        db.close();raise ValueError('Hierarchy index is stale; rebuild after code/source/rule changes')
    return db


def public_node(row):
    return {k:row[k] for k in ('id','country','namespace','kind','rank','code','name','source')}


def ancestors(db,id):
    if db.execute('SELECT 1 FROM nodes WHERE id=?',(id,)).fetchone() is None:raise ValueError('Unknown node ID')
    rows=db.execute('''WITH RECURSIVE up(id) AS (SELECT parent FROM links WHERE child=?
       UNION SELECT l.parent FROM links l JOIN up ON l.child=up.id)
       SELECT n.* FROM up JOIN nodes n ON n.id=up.id ORDER BY n.rank,n.id''',(id,)).fetchall()
    return rows


def hierarchy(db,id):
    row=db.execute('SELECT * FROM nodes WHERE id=?',(id,)).fetchone()
    if row is None:raise ValueError('Unknown node ID')
    parents=ancestors(db,id)
    ids=[id]+[r['id'] for r in parents]
    issues=[]
    for n in ids:
        for r in db.execute('SELECT * FROM issues WHERE node=?',(n,)):
            issues.append({'node':n,'code':r['code'],'field':r['field'],'raw_value':json.loads(r['raw_value']),'candidates':json.loads(r['candidates_json'])})
    rooted=row['kind'] in ('country','supplementary_area') or any(p['id']=='scope:'+row['country'] for p in parents)
    return {'status':'review_required' if issues or not rooted else 'source_relations_resolved',
        'node':public_node(row),'ancestors':[public_node(r) for r in parents],
        'relations':[dict(r) for r in db.execute('SELECT * FROM links WHERE child=? ORDER BY parent',(id,))],
        'issues':issues,'supplied_code_checks':[dict(r) for r in db.execute('SELECT field,status,raw_value FROM checks WHERE node=? ORDER BY field',(id,))],
        'national_coverage_verified':False,'address_verified':False,'delivery_verified':False,
        'note':'Resolved source references do not prove physical containment, complete tiers, current postal assignment, or delivery.'}


def search(db,cc,text,namespace=None,kind=None,parent=None,limit=20,offset=0):
    cc=sa.country_code(cc)
    if not 1<=limit<=100 or offset<0:raise ValueError('Invalid pagination')
    tokens=sa.lookup_key(text).split()
    if not tokens or len(tokens)>20:raise ValueError('Use 1-20 search tokens')
    where=['n.country=?'];params=[cc]
    if namespace:where.append('n.namespace=?');params.append(namespace)
    if kind:where.append('n.kind=?');params.append(kind)
    for t in tokens:
        where.append("a.lookup LIKE ? ESCAPE '\\'")
        params.append('%'+t.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
    if parent:
        p=db.execute('SELECT country FROM nodes WHERE id=?',(parent,)).fetchone()
        if not p or p['country']!=cc:raise ValueError('Unknown parent or country mismatch')
        where.append('n.id IN (WITH RECURSIVE down(id) AS (SELECT child FROM links WHERE parent=? UNION SELECT l.child FROM links l JOIN down ON l.parent=down.id) SELECT id FROM down)');params.append(parent)
    q='SELECT DISTINCT n.* FROM nodes n JOIN names a ON a.node=n.id WHERE '+' AND '.join(where)+' ORDER BY n.name,n.id LIMIT ? OFFSET ?'
    rows=db.execute(q,params+[limit+1,offset]).fetchall()
    results=[]
    for r in rows[:limit]:
        assessment=hierarchy(db,r['id'])
        results.append({**public_node(r),'hierarchy_status':assessment['status'],'source_issue_count':len(assessment['issues'])})
    return {'country':cc,'status':'reference_candidates','results':results,
            'has_more':len(rows)>limit,'next_offset':offset+limit if len(rows)>limit else None,
            'address_verified':False,'delivery_verified':False}


def children(db,parent,namespace=None,kind=None,limit=50,offset=0):
    if not 1<=limit<=100 or offset<0:raise ValueError('Invalid pagination')
    p=db.execute('SELECT country FROM nodes WHERE id=?',(parent,)).fetchone()
    if not p:raise ValueError('Unknown parent ID')
    where=['l.parent=?'];params=[parent]
    if namespace:where.append('n.namespace=?');params.append(namespace)
    if kind:where.append('n.kind=?');params.append(kind)
    rows=db.execute('SELECT DISTINCT n.* FROM links l JOIN nodes n ON n.id=l.child WHERE '+' AND '.join(where)+' ORDER BY n.rank,n.name,n.id LIMIT ? OFFSET ?',params+[limit+1,offset]).fetchall()
    results=[]
    for r in rows[:limit]:
        assessment=hierarchy(db,r['id'])
        results.append({**public_node(r),'hierarchy_status':assessment['status'],'source_issue_count':len(assessment['issues'])})
    return {'parent':parent,'results':results,'has_more':len(rows)>limit,
        'next_offset':offset+limit if len(rows)>limit else None,
        'note':'Explicit parent/ancestor assertions. Some sources provide several administrative branches.'}


def validate_path(db,cc,ids):
    cc=sa.country_code(cc)
    if not isinstance(ids,list) or not 2<=len(ids)<=12 or any(not isinstance(x,str) for x in ids):raise ValueError('Provide 2-12 ordered node IDs')
    problems=[]
    if len(set(ids))!=len(ids):problems.append('repeated_node')
    rows=[db.execute('SELECT * FROM nodes WHERE id=?',(id,)).fetchone() for id in ids]
    if any(r is None for r in rows):problems.append('unknown_node')
    if any(r is not None and r['country']!=cc for r in rows):problems.append('country_mismatch')
    if not problems:
        for parent,child in zip(ids,ids[1:]):
            if parent not in {r['id'] for r in ancestors(db,child)}:problems.append('unproven_parent:'+parent+'->'+child)
        if any(hierarchy(db,id)['status']=='review_required' for id in ids):problems.append('source_issue_requires_review')
    return {'status':'review_required' if problems else 'source_path_consistent','country':cc,'node_ids':ids,
            'problems':problems,'address_verified':False,'delivery_verified':False}


def country_report(db,cc):
    kinds=[dict(r) for r in db.execute('SELECT namespace,kind,count(*) AS nodes FROM nodes WHERE country=? GROUP BY namespace,kind ORDER BY namespace,kind',(cc,))]
    issues=[dict(r) for r in db.execute('SELECT i.code,i.field,count(*) AS observations FROM issues i JOIN nodes n ON n.id=i.node WHERE n.country=? GROUP BY i.code,i.field ORDER BY i.code,i.field',(cc,))]
    checks=[dict(r) for r in db.execute("SELECT c.field,c.status,count(*) AS records FROM checks c JOIN nodes n ON n.id=c.node WHERE n.country=? AND n.kind='place' GROUP BY c.field,c.status ORDER BY c.field,c.status",(cc,))]
    return {'code':cc,'name_ja':sa.profiles()[cc]['name_ja'],'scope_type':'country' if cc in COUNTRIES else 'supplementary_area',
        'processing_status':'PASS','coverage_status':'partial_reference_data','nodes_by_namespace_and_kind':kinds,
        'geonames_place_parent_checks':checks,'issues':issues,
        'geonames_place_count':db.execute("SELECT count(*) FROM nodes WHERE country=? AND namespace='geonames' AND kind='place'",(cc,)).fetchone()[0],
        'linked_nodes':db.execute('SELECT count(DISTINCT n.id) FROM nodes n JOIN links l ON l.child=n.id WHERE n.country=?',(cc,)).fetchone()[0],
        'nodes_requiring_source_review':db.execute('SELECT count(DISTINCT n.id) FROM nodes n JOIN issues i ON i.node=n.id WHERE n.country=?',(cc,)).fetchone()[0],
        'coverage_notes_ja':sa.profiles()[cc]['coverage_notes_ja'],
        'street_names_nationwide_acquired':False,'address_points_acquired':False,
        'address_verified':False,'national_coverage_verified':False,'delivery_verified':False}


def record(db,id):
    row=db.execute('SELECT * FROM nodes WHERE id=?',(id,)).fetchone()
    if row is None:raise ValueError('Unknown node ID')
    source=source_registry(False).get(row['source'])
    return {**hierarchy(db,id),'stored_fields':json.loads(row['raw_json']),
            'source_metadata':{k:v for k,v in source.items() if k!='local_path'} if source else None,
            'observation_count':db.execute('SELECT count(*) FROM observations WHERE node=?',(id,)).fetchone()[0],
            'original_observations':observations(db,id,limit=5),
            'postal_observations':[dict(r) for r in db.execute('SELECT postcode,source FROM postal WHERE node=?',(id,))],
            'unit_autofill':False,'house_number_expansion':False}


def observations(db,id,limit=20,offset=0):
    if not 1<=limit<=100 or offset<0:raise ValueError('Invalid pagination')
    if db.execute('SELECT 1 FROM nodes WHERE id=?',(id,)).fetchone() is None:raise ValueError('Unknown node ID')
    rows=db.execute('SELECT source,ordinal,raw_json FROM observations WHERE node=? ORDER BY source,ordinal LIMIT ? OFFSET ?',(id,limit+1,offset)).fetchall()
    return {'results':[{'source':r['source'],'ordinal':r['ordinal'],'fields':json.loads(r['raw_json'])} for r in rows[:limit]],
            'has_more':len(rows)>limit,'next_offset':offset+limit if len(rows)>limit else None}


def names(db,id,language=None,limit=100,offset=0):
    if not 1<=limit<=100 or offset<0:raise ValueError('Invalid pagination')
    if db.execute('SELECT 1 FROM nodes WHERE id=?',(id,)).fetchone() is None:raise ValueError('Unknown node ID')
    where='node=?';params=[id]
    if language is not None:where+=' AND language=?';params.append(language)
    rows=db.execute('SELECT DISTINCT name,language,source FROM names WHERE '+where+' ORDER BY language,name,source LIMIT ? OFFSET ?',params+[limit+1,offset]).fetchall()
    return {'id':id,'results':[dict(r) for r in rows[:limit]],'has_more':len(rows)>limit,
            'next_offset':offset+limit if len(rows)>limit else None,
            'note':'Language tags are source-qualified. Untagged ASCII names are not asserted English translations.'}


def postal_records(db,cc,postcode,limit=20,offset=0):
    cc=sa.country_code(cc)
    if not isinstance(postcode,str) or not postcode or not 1<=limit<=100 or offset<0:raise ValueError('Provide a postcode string and valid pagination')
    rows=db.execute('SELECT DISTINCT n.* FROM postal p JOIN nodes n ON n.id=p.node WHERE n.country=? AND p.postcode=? ORDER BY n.id LIMIT ? OFFSET ?',(cc,postcode,limit+1,offset)).fetchall()
    return {'country':cc,'postcode':postcode,'results':[public_node(r) for r in rows[:limit]],
            'has_more':len(rows)>limit,'next_offset':offset+limit if len(rows)>limit else None,
            'assignment_verified':False,'delivery_verified':False,'note':'No postal assignment rows are acquired in this package. Empty results mean unavailable evidence, not an invalid postcode.'}


def run_loop(db,scope='countries'):
    if scope not in ('countries','territories','all'):raise ValueError('Invalid processing scope')
    codes=COUNTRIES if scope=='countries' else TERRITORIES if scope=='territories' else ALL_SCOPES
    structural_checks(db)
    reports=[]
    for cc in codes:
        r=country_report(db,cc)
        if db.execute('SELECT 1 FROM nodes WHERE id=?',('scope:'+cc,)).fetchone() is None:raise ValueError('Missing scope root')
        reports.append(r)
    return {'status':'PASS','checked_at':datetime.now(timezone.utc).isoformat(),'scope':scope,
        'country_count':sum(r['scope_type']=='country' for r in reports),
        'supplementary_area_count':sum(r['scope_type']=='supplementary_area' for r in reports),
        'countries':reports,'structural_checks':structural_checks(db),
        'limit':'PASS means the processing and structural checks completed; it is not national address completeness.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,default=DEFAULT_DB)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('build')
    sub.add_parser('verify-sources')
    q=sub.add_parser('postcode');q.add_argument('--country',required=True);q.add_argument('--value',required=True)
    q=sub.add_parser('loop');q.add_argument('--scope',choices=['countries','territories','all'],default='countries');q.add_argument('--output',type=Path)
    q=sub.add_parser('hierarchy');q.add_argument('--id',required=True)
    q=sub.add_parser('record');q.add_argument('--id',required=True)
    q=sub.add_parser('observations');q.add_argument('--id',required=True);q.add_argument('--limit',type=int,default=20);q.add_argument('--offset',type=int,default=0)
    q=sub.add_parser('names');q.add_argument('--id',required=True);q.add_argument('--language');q.add_argument('--limit',type=int,default=100);q.add_argument('--offset',type=int,default=0)
    q=sub.add_parser('postal-records');q.add_argument('--country',required=True);q.add_argument('--value',required=True);q.add_argument('--limit',type=int,default=20);q.add_argument('--offset',type=int,default=0)
    q=sub.add_parser('children');q.add_argument('--parent',required=True);q.add_argument('--namespace');q.add_argument('--kind');q.add_argument('--limit',type=int,default=50);q.add_argument('--offset',type=int,default=0)
    q=sub.add_parser('search');q.add_argument('--country',required=True);q.add_argument('--text',required=True);q.add_argument('--namespace');q.add_argument('--kind');q.add_argument('--parent');q.add_argument('--limit',type=int,default=20);q.add_argument('--offset',type=int,default=0)
    q=sub.add_parser('validate-path');q.add_argument('--country',required=True);q.add_argument('--input',type=Path,required=True)
    q=sub.add_parser('issues');q.add_argument('--country',required=True);q.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    try:
        if args.command=='build':out=build_database(args.db)
        elif args.command=='verify-sources':out={'status':'PASS','source_objects':len(sa.verify_sources()['sources'])}
        elif args.command=='postcode':out=sa.postcode_review(args.country,args.value)
        else:
            with open_database(args.db) as db:
                if args.command=='loop':
                    out=run_loop(db,args.scope)
                    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                elif args.command=='hierarchy':out=hierarchy(db,args.id)
                elif args.command=='record':out=record(db,args.id)
                elif args.command=='observations':out=observations(db,args.id,args.limit,args.offset)
                elif args.command=='names':out=names(db,args.id,args.language,args.limit,args.offset)
                elif args.command=='postal-records':out=postal_records(db,args.country,args.value,args.limit,args.offset)
                elif args.command=='children':out=children(db,args.parent,args.namespace,args.kind,args.limit,args.offset)
                elif args.command=='search':out=search(db,args.country,args.text,args.namespace,args.kind,args.parent,args.limit,args.offset)
                elif args.command=='validate-path':out=validate_path(db,args.country,sa.read_json(args.input))
                else:
                    cc=sa.country_code(args.country);rows=db.execute('SELECT i.* FROM issues i JOIN nodes n ON n.id=i.node WHERE n.country=? ORDER BY i.node,i.code,i.field',(cc,))
                    count=0;args.output.parent.mkdir(parents=True,exist_ok=True)
                    with args.output.open('w',encoding='utf-8') as f:
                        for r in rows:f.write(sa.dump(dict(r))+'\n');count+=1
                    out={'country':cc,'issues':count,'output':str(args.output)}
        print(json.dumps(out,ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError,sqlite3.Error) as e:
        print(sa.dump({'status':'error','message':str(e)}),file=sys.stderr);raise SystemExit(2)


if __name__=='__main__':main()
