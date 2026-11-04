#!/usr/bin/env python3
"""Source-qualified South America hierarchy. Python 3.10+, standard library."""
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

import southamerica as sa

ROOT = sa.ROOT
EXTRA = ROOT / 'sources/HIERARCHY'
DEFAULT_DB = ROOT / 'generated/south_america_hierarchy.sqlite'
COUNTRIES = ('AR','BO','BR','CL','CO','EC','GY','PY','PE','SR','UY','VE')
TERRITORIES = ('GF','FK','GS','BV')
ALL_SCOPES = COUNTRIES + TERRITORIES
VERSION = 2


def digest(value):
    return hashlib.sha256(sa.dump(value).encode()).hexdigest()


def decoded(path):
    b = Path(path).read_bytes()
    return gzip.decompress(b) if b[:2] == b'\x1f\x8b' else b


def read_data(path):
    return json.loads(decoded(path))


def source_registry(verify=True):
    old = sa.verify_sources() if verify else sa.read_json(ROOT/'SOUTH_AMERICA_SOURCES.json')
    extra = sa.read_json(ROOT/'SOUTH_AMERICA_HIERARCHY_SOURCES.json')
    if extra.get('failures'):
        raise ValueError('Candidate supplementary sources contain acquisition failures')
    registry = {s['id']: {**s, 'local_path': sa.SOURCES/s['path']} for s in old['sources']}
    for s in extra['sources']:
        p = (EXTRA/s['path']).resolve()
        if not p.is_relative_to(EXTRA.resolve()):
            raise ValueError('Source path outside package')
        if verify and (not p.is_file() or p.stat().st_size != s['bytes'] or sa.file_hash(p) != s['sha256']):
            raise ValueError('Supplement integrity mismatch: '+s['id'])
        if s['id'] in registry:
            raise ValueError('Duplicate source ID')
        registry[s['id']] = {**s, 'local_path': p}
    return registry


def inputs_fingerprint():
    return digest({name:sa.file_hash(ROOT/name) for name in [
        'SOUTH_AMERICA_SOURCES.json','SOUTH_AMERICA_HIERARCHY_SOURCES.json',
        'SOUTH_AMERICA_RULES.json','SOUTH_AMERICA_SCOPE.json']})


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

    def geonames(self):
        admin = defaultdict(list)
        code_only = defaultdict(list)
        raw_nodes = []
        for cc in ALL_SCOPES:
            source = cc.lower()+'-geonames-geonames'
            for ordinal,row in enumerate(sa.zip_rows(self.sources[source]['local_path'],cc),1):
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
                r=dict(zip(sa.NAME_FIELDS,row+['']*(10-len(row))))
                id='gn:'+r['geonameid']
                if id in self.nodes and r['language'] not in sa.NON_NAME_TAGS and not sa.historical_or_time_bounded_name(r):
                    self.name(id,r['name'],r['language'] or None,source)

    def ar(self):
        batches=[('ar-georef-provincias','provincias','province',10),
                 ('ar-georef-departamentos','departamentos','department',20),
                 ('ar-georef-municipios','municipios','municipality',25),
                 ('ar-georef-localidades-censales','localidades_censales','census_locality',30),
                 ('ar-georef-localidades','localidades','locality',40)]
        fields={'provincia':'province','departamento':'department','municipio':'municipality','localidad_censal':'census_locality'}
        for source,field,kind,rank in batches:
            d=read_data(self.sources[source]['local_path']);rows=d[field]
            if d['inicio']!=0 or d['total']!=len(rows) or d['cantidad']!=len(rows):
                raise ValueError('Incomplete Georef response: '+source)
            for ordinal,r in enumerate(rows,1):
                id='ar-georef:'+kind+':'+r['id']
                self.node(id,'AR','ar-georef-v1',kind,rank,r['id'],r['nombre'],source,r)
                self.observation(source,ordinal,id,r)
                if kind=='province':self.ref(id,'scope:AR','in_scope',source)
                for field,parent_kind in fields.items():
                    code=(r.get(field) or {}).get('id')
                    if code:self.ref(id,'ar-georef:'+parent_kind+':'+code,field,source)

    def br(self):
        for endpoint,kind,rank in [('estados','state',10),('municipios','municipality',20),('distritos','district',30),('subdistritos','subdistrict',40)]:
            source='br-ibge-'+endpoint
            for ordinal,r in enumerate(read_data(self.sources[source]['local_path']),1):
                code=str(r['id']);id='br-ibge:'+kind+':'+code
                self.node(id,'BR','br-ibge',kind,rank,code,r['nome'],source,r)
                self.observation(source,ordinal,id,r)
                if kind=='state':self.ref(id,'scope:BR','in_scope',source)
                elif kind=='municipality':
                    # Immediate/intermediate geography supersedes old statistical regions;
                    # neither is inserted as a political administrative level.
                    state=r['regiao-imediata']['regiao-intermediaria']['UF']['id']
                    self.ref(id,'br-ibge:state:'+str(state),'state',source)
                elif kind=='district':self.ref(id,'br-ibge:municipality:'+str(r['municipio']['id']),'municipality',source)
                else:self.ref(id,'br-ibge:district:'+str(r['distrito']['id']),'district',source)

    def co(self):
        source='co-dane-divipola'
        for ordinal,r in enumerate(read_data(self.sources[source]['local_path']),1):
            dp,code=r['cod_dpto'],r['cod_mpio']
            if not re.fullmatch('[0-9]{2}',dp) or not re.fullmatch('[0-9]{5}',code) or not code.startswith(dp):
                raise ValueError('Invalid DANE code tuple')
            parent='co-dane:department:'+dp;id='co-dane:municipality:'+code
            self.node(parent,'CO','co-dane-2024','department',10,dp,r['dpto'],source,{'cod_dpto':dp,'dpto':r['dpto'],'derived_from':'explicit row fields'})
            self.node(id,'CO','co-dane-2024','municipal_unit',20,code,r['nom_mpio'],source,r)
            self.observation(source,ordinal,id,r)
            self.ref(parent,'scope:CO','in_scope',source);self.ref(id,parent,'department',source)

    def pe(self):
        source='pe-inei-ubigeos'
        rows=csv.DictReader(io.StringIO(decoded(self.sources[source]['local_path']).decode('utf-8-sig')),delimiter=';')
        for ordinal,r in enumerate(rows,1):
            code=r['UBIGEO_INEI']
            if not re.fullmatch('[0-9]{6}',code):raise ValueError('Invalid UBIGEO string')
            parent='scope:PE'
            for kind,rank,part,label in [('department',10,code[:2],r['DEPARTAMENTO']),('province',20,code[:4],r['PROVINCIA']),('district',30,code,r['DISTRITO'])]:
                id='pe-inei:'+kind+':'+part
                self.node(id,'PE','pe-inei-reference',kind,rank,part,label,source,r if kind=='district' else {'code':part,'name':label,'derived_from':'explicit UBIGEO fields'})
                self.ref(id,parent,'ubigeo_parent',source);parent=id
            self.observation(source,ordinal,id,r)

    def py(self):
        district_tuples=defaultdict(list)
        for suffix,kind,rank,codefield,namefield in [('departamentos','department',10,'DPTO','DPTO_DESC'),('distritos','district',20,'CLAVE','DIST_DESC_'),('barloc','neighbourhood_or_locality',30,'CLAVE_BAR','BARLO_DESC')]:
            source='py-ine-'+suffix;d=read_data(self.sources[source]['local_path'])
            if d['numberMatched']!=len(d['features']) or d['numberReturned']!=len(d['features']):
                raise ValueError('Truncated Paraguay WFS response')
            for ordinal,f in enumerate(d['features'],1):
                r=f['properties'];code=r[codefield];id='py-ine:'+kind+':'+code
                self.node(id,'PY','py-ine-statistical',kind,rank,code,r[namefield],source,f)
                self.observation(source,ordinal,id,f)
                if kind=='district':district_tuples[(r['DPTO'],r['DISTRITO'])].append(id)
                parent='scope:PY' if kind=='department' else ('py-ine:department:'+r['DPTO'] if kind=='district' else 'py-ine:district:'+r['CLAVE'])
                relation='explicit_statistical_parent'
                if kind=='neighbourhood_or_locality':
                    candidates=district_tuples.get((r['DPTO'],r['DISTRITO']),[])
                    if not r['CLAVE'] and len(candidates)==1:
                        parent=candidates[0];relation='explicit_department_district_tuple'
                        self.db.execute('INSERT INTO checks VALUES(?,?,?,?)',(id,'CLAVE','resolved_from_explicit_components',sa.dump({'CLAVE':r['CLAVE'],'DPTO':r['DPTO'],'DISTRITO':r['DISTRITO']})))
                    elif r['CLAVE'] and candidates!=[parent]:
                        self.issue(id,'parent_tuple_conflict','CLAVE',r['CLAVE'],candidates)
                        continue
                self.ref(id,parent,relation,source)
                if kind!='department' and not code.startswith(r['DPTO']):self.issue(id,'code_prefix_conflict','DPTO',r['DPTO'],[])

    def uy(self):
        source='uy-ide-calles-2020'
        rows=csv.DictReader(io.StringIO(decoded(self.sources[source]['local_path']).decode('utf-8-sig')))
        for ordinal,r in enumerate(rows,1):
            dp,loc,code=r['departamento'],r['localidad'],r['idcalle']
            # These are source label groups, not newly invented municipality IDs.
            dep='uy-ide:department-label:'+digest(dp)
            local='uy-ide:locality-label:'+digest([dp,loc])
            id='uy-ide:street:'+digest([dp,loc,code])
            self.node(dep,'UY','uy-ide-2020','source_department_label',10,dp,dp,source,{'departamento':dp})
            self.node(local,'UY','uy-ide-2020','source_locality_label',30,loc,loc,source,{'departamento':dp,'localidad':loc})
            self.node(id,'UY','uy-ide-2020','street',50,code,r['calle'],source,r)
            self.observation(source,ordinal,id,r)
            self.ref(dep,'scope:UY','source_scope',source);self.ref(local,dep,'source_label_parent',source);self.ref(id,local,'source_label_parent',source)
            if dp=='LIMITE CONTESTADO':self.issue(id,'disputed_source_label','departamento',dp,[])

    def gf(self):
        source='gf-insee-cog-2026'
        with zipfile.ZipFile(self.sources[source]['local_path']) as z:
            for kind,rank,member,key in [('region',10,'v_region_2026.csv','REG'),('department',20,'v_departement_2026.csv','DEP'),('arrondissement',30,'v_arrondissement_2026.csv','ARR'),('commune',40,'v_commune_2026.csv','COM')]:
                for ordinal,r in enumerate(csv.DictReader(io.StringIO(z.read(member).decode('utf-8-sig'))),1):
                    if (r.get('REG')!='03' if kind=='region' else r.get('DEP')!='973'):continue
                    if kind=='commune' and r['TYPECOM']!='COM':continue
                    id='gf-insee:'+kind+':'+r[key]
                    self.node(id,'GF','gf-insee-2026',kind,rank,r[key],r['LIBELLE'],source,r)
                    # Composite ordinal namespaces prevent overlapping CSV row numbers.
                    self.observation(source,rank*1000000+ordinal,id,{'member':member,'row':r})
                    parent='scope:GF' if kind=='region' else ('gf-insee:region:'+r['REG'] if kind=='department' else 'gf-insee:department:'+r['DEP'] if kind=='arrondissement' else 'gf-insee:arrondissement:'+r['ARR'])
                    self.ref(id,parent,'insee_parent',source)
        source='gf-ban-973'
        with gzip.open(self.sources[source]['local_path'],'rt',encoding='utf-8-sig',newline='') as f:
            for ordinal,r in enumerate(csv.DictReader(f,delimiter=';'),1):
                grouping=[r['code_insee'],r['id_fantoir'],r['nom_voie']]
                id='gf-ban:street:'+digest(grouping)
                self.node(id,'GF','gf-ban','street',50,r['id_fantoir'],r['nom_voie'],source,{'code_insee':r['code_insee'],'id_fantoir':r['id_fantoir'],'nom_voie':r['nom_voie'],'grouping':'exact observed tuple; not a street geometry'})
                self.observation(source,ordinal,id,r)
                self.ref(id,'gf-insee:commune:'+r['code_insee'],'insee_commune_code',source)
                self.db.execute('INSERT OR IGNORE INTO postal VALUES(?,?,?)',(id,r['code_postal'],source))


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
    db=sqlite3.connect(temp);schema(db);b=Builder(db,registry)
    try:
        b.roots();b.geonames()
        for method in (b.ar,b.br,b.co,b.pe,b.py,b.uy,b.gf):method()
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
    return {'status':'PASS','db':str(path),'nodes':len(b.nodes),'countries':12,'supplementary_areas':4,
            'source_observation_counts':dict(b.source_counts)}


def open_database(path=DEFAULT_DB):
    if not Path(path).is_file():raise ValueError('Run southamerica_hierarchy.py build first')
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
        'address_verified':False,'national_coverage_verified':False}


def run_loop(db,scope='countries'):
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
    q=sub.add_parser('loop');q.add_argument('--scope',choices=['countries','territories','all'],default='countries');q.add_argument('--output',type=Path)
    q=sub.add_parser('hierarchy');q.add_argument('--id',required=True)
    q=sub.add_parser('children');q.add_argument('--parent',required=True);q.add_argument('--namespace');q.add_argument('--kind');q.add_argument('--limit',type=int,default=50);q.add_argument('--offset',type=int,default=0)
    q=sub.add_parser('search');q.add_argument('--country',required=True);q.add_argument('--text',required=True);q.add_argument('--namespace');q.add_argument('--kind');q.add_argument('--parent');q.add_argument('--limit',type=int,default=20);q.add_argument('--offset',type=int,default=0)
    q=sub.add_parser('validate-path');q.add_argument('--country',required=True);q.add_argument('--input',type=Path,required=True)
    q=sub.add_parser('issues');q.add_argument('--country',required=True);q.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    try:
        if args.command=='build':out=build_database(args.db)
        else:
            with open_database(args.db) as db:
                if args.command=='loop':
                    out=run_loop(db,args.scope)
                    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                elif args.command=='hierarchy':out=hierarchy(db,args.id)
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
