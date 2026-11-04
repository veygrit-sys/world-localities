"""Keep OSM roads, address observations and boundary references as supplemental evidence."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import tempfile
import zlib

ACTIVE_ROADS = {
    'motorway','motorway_link','trunk','trunk_link','primary','primary_link',
    'secondary','secondary_link','tertiary','tertiary_link','unclassified',
    'residential','service','living_street','pedestrian','track','road',
    'footway','bridleway','steps','path','cycleway','corridor','busway','bus_guideway',
}
LIFECYCLES = ('construction','proposed','abandoned','disused','demolished','razed')


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def file_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def classify(kind, tags):
    """Classification is a description of source tags, never official assignment."""
    highway=tags.get('highway', '')
    lifecycle=next((state for state in LIFECYCLES if tags.get(state+':highway')), None)
    road_state='none'
    if kind=='way' and (highway or lifecycle):
        road_state=highway if highway in LIFECYCLES else lifecycle or ('active_tag' if highway in ACTIVE_ROADS else 'other_highway_tag')
    address=any(key.startswith('addr:') for key in tags)
    admin=tags.get('boundary')=='administrative'
    return {
        'selected':road_state!='none' or address or admin,
        'road_state':road_state,
        'named_road':road_state=='active_tag' and any(value and (key=='name' or key.startswith('name:') or key in ('official_name','alt_name','loc_name')) for key,value in tags.items()),
        'address_tags':address,
        'house_number':bool(tags.get('addr:housenumber')),
        'interpolation':bool(tags.get('addr:interpolation')),
        'administrative_tag':admin,
    }


def schema(db):
    db.executescript('''
    PRAGMA foreign_keys=ON;
    CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE sources(extract_code TEXT PRIMARY KEY, source_id TEXT UNIQUE NOT NULL, receipt_json TEXT NOT NULL, header_json TEXT NOT NULL);
    CREATE TABLE objects(
      id TEXT NOT NULL, variant_sha256 TEXT NOT NULL, osm_type TEXT NOT NULL,
      osm_id TEXT NOT NULL, version INTEGER NOT NULL, timestamp TEXT NOT NULL,
      road_state TEXT NOT NULL, named_road INTEGER NOT NULL, address_tags INTEGER NOT NULL,
      house_number INTEGER NOT NULL, interpolation INTEGER NOT NULL, administrative_tag INTEGER NOT NULL,
      tags_json TEXT NOT NULL, topology_json TEXT NOT NULL, geometry_zlib BLOB,
      geometry_status TEXT NOT NULL,
      PRIMARY KEY(id, variant_sha256));
    CREATE TABLE observations(
      extract_code TEXT NOT NULL REFERENCES sources(extract_code),
      id TEXT NOT NULL, variant_sha256 TEXT NOT NULL,
      PRIMARY KEY(extract_code, id, variant_sha256),
      FOREIGN KEY(id, variant_sha256) REFERENCES objects(id, variant_sha256));
    CREATE INDEX object_kind ON objects(road_state, house_number, administrative_tag);
    CREATE INDEX observation_object ON observations(id, variant_sha256);
    ''')


def verified_sources(manifest, data_root):
    root=Path(data_root).resolve()
    sources=manifest.get('sources', [])
    if not sources:raise ValueError('No source receipts')
    seen=set()
    for source in sources:
        code=source['country_extract']
        if not re.fullmatch('[A-Z]{2}',code) or code in seen:raise ValueError('Invalid or duplicate extract code')
        seen.add(code)
        relative=PurePosixPath(source['path'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe source path')
        path=(root/relative).resolve()
        if not path.is_relative_to(root):raise ValueError('Source escapes data root')
        if path.stat().st_size!=source['bytes'] or file_hash(path)!=source['sha256']:
            raise ValueError('Source hash or byte count mismatch: '+code)
        yield source,path
    if seen!=set(manifest['scope_codes']):raise ValueError('Receipt scope mismatch')


def store_object(db, extract_code, kind, identifier, version, timestamp, tags, topology, geometry, geometry_status):
    flags=classify(kind,tags)
    if not flags['selected']:return False
    identifier=str(identifier)
    if not identifier.isascii() or not identifier.isdigit():raise ValueError('Invalid OSM identity')
    uid='osm:'+kind+':'+identifier
    payload={'id':uid,'version':version,'timestamp':timestamp,'tags':tags,'topology':topology,'geometry':geometry,'geometry_status':geometry_status}
    digest=hashlib.sha256(canonical(payload).encode()).hexdigest()
    geometry_bytes=zlib.compress(canonical(geometry).encode()) if geometry is not None else None
    db.execute('INSERT OR IGNORE INTO objects VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
               (uid,digest,kind,identifier,version,timestamp,flags['road_state'],int(flags['named_road']),int(flags['address_tags']),int(flags['house_number']),int(flags['interpolation']),int(flags['administrative_tag']),canonical(tags),canonical(topology),geometry_bytes,geometry_status))
    db.execute('INSERT INTO observations VALUES(?,?,?)',(extract_code,uid,digest))
    return True


def parse_source(db, source, path, index_dir):
    import osmium
    code=source['country_extract']
    with osmium.io.Reader(str(path)) as reader:
        header=reader.header()
        header_data={key:header.get(key) for key in ['generator','osmosis_replication_timestamp','osmosis_replication_sequence_number']}
    db.execute('INSERT INTO sources VALUES(?,?,?,?)',(code,source['source_id'],canonical(source),canonical(header_data)))
    counts=Counter()

    class Evidence(osmium.SimpleHandler):
        def accept(self,obj,kind):
            counts['scanned_'+kind]+=1
            tags={tag.k:tag.v for tag in obj.tags}
            if not classify(kind,tags)['selected']:return
            topology={};geometry=None
            geometry_status='not_assembled'
            if kind=='node':
                if obj.location.valid():
                    geometry={'type':'Point','coordinates':[obj.location.lon,obj.location.lat]}
                    geometry_status='complete'
                else:geometry_status='missing_location'
            elif kind=='way':
                topology={'nodes':[str(node.ref) for node in obj.nodes]}
                if len(obj.nodes)>=2 and all(node.location.valid() for node in obj.nodes):
                    geometry={'type':'LineString','coordinates':[[node.location.lon,node.location.lat] for node in obj.nodes]}
                    geometry_status='complete'
                else:geometry_status='missing_node_locations_or_short_way'
            else:
                topology={'members':[{'type':member.type,'ref':str(member.ref),'role':member.role} for member in obj.members]}
                geometry_status='relation_member_geometry_not_assembled'
            store_object(db,code,kind,obj.id,obj.version,str(obj.timestamp),tags,topology,geometry,geometry_status)
            counts['retained_'+kind]+=1
        def node(self,obj):self.accept(obj,'node')
        def way(self,obj):self.accept(obj,'way')
        def relation(self,obj):self.accept(obj,'relation')

    handler=Evidence()
    handler.apply_file(str(path),locations=True,idx='sparse_file_array,'+str(Path(index_dir)/(code+'.locations')))
    db.commit()
    return {'extract_code':code,'counts':dict(counts),'pbf_header':header_data}


def summarize(db):
    counts={key:db.execute('SELECT count(*) FROM '+key).fetchone()[0] for key in ['objects','observations','sources']}
    counts['distinct_osm_ids']=db.execute('SELECT count(DISTINCT id) FROM objects').fetchone()[0]
    counts['ids_with_multiple_payloads']=db.execute('SELECT count(*) FROM (SELECT id FROM objects GROUP BY id HAVING count(*)>1)').fetchone()[0]
    extracts=[]
    for (code,) in db.execute('SELECT extract_code FROM sources ORDER BY extract_code').fetchall():
        row=db.execute('''SELECT count(*),sum(o.road_state='active_tag'),sum(o.named_road),sum(o.house_number),sum(o.address_tags),sum(o.administrative_tag),sum(o.interpolation),sum(o.road_state='active_tag' AND o.geometry_status<>'complete')
          FROM observations a JOIN objects o USING(id,variant_sha256) WHERE a.extract_code=?''',(code,)).fetchone()
        extracts.append(dict(zip(['extract_code','observation_records','active_road_way_records','named_road_way_records','house_number_tag_observations','address_tag_observations','administrative_tag_observations','interpolation_features','active_road_ways_with_missing_geometry'],[code]+[value or 0 for value in row])))
    return {'status':'SOURCE_EVIDENCE_INDEXED','counts':counts,'extracts':extracts,
            'extract_membership_is_legal_country_membership':False,'official_administrative_assignment_verified':False,
            'house_numbers_are_issuing_authority_verified':False,'national_completeness_verified':False,
            'deliverability_in_scope':False,'interpolation_expanded':False,
            'licence':'ODbL-1.0','attribution':'OpenStreetMap contributors; extract by Geofabrik'}


def build(manifest, data_root, output):
    output=Path(output).absolute()
    if output.exists() or output.is_symlink():raise ValueError('Use a new output; accepted indexes are not overwritten')
    sources=list(verified_sources(manifest,data_root))
    output.parent.mkdir(parents=True,exist_ok=True)
    reports=[]
    with tempfile.TemporaryDirectory(prefix='.osm-evidence-',dir=output.parent) as temporary:
        staged=Path(temporary)/'evidence.sqlite'
        db=sqlite3.connect(staged)
        try:
            schema(db)
            db.execute("INSERT INTO metadata VALUES('schema_version','1')")
            db.execute("INSERT INTO metadata VALUES('implementation_sha256',?)",(canonical(file_hash(__file__)),))
            for source,path in sources:
                with tempfile.TemporaryDirectory(prefix='locations-',dir=temporary) as index_dir:
                    report=parse_source(db,source,path,index_dir)
                reports.append(report)
                print(canonical({'extract_code':source['country_extract'],'status':'PARSED'}),flush=True)
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Evidence database integrity failed')
            report={**summarize(db),'checked_at':datetime.now(timezone.utc).isoformat(),'source_replays':reports,'source_bytes':sum(source['bytes'] for source,_ in sources)}
            db.execute("INSERT INTO metadata VALUES('build_report',?)",(canonical(report),));db.commit()
        finally:db.close()
        if output.exists():raise ValueError('Output appeared during build')
        staged.replace(output)
    return report


def query(db, extract_code, kind, text=None, identifier=None, limit=20):
    if not re.fullmatch('[A-Z]{2}',extract_code) or not 1<=limit<=100:raise ValueError('Invalid extract code or pagination')
    if db.execute('SELECT 1 FROM sources WHERE extract_code=?',(extract_code,)).fetchone() is None:raise ValueError('Unknown source extract')
    conditions={'roads':"o.road_state='active_tag'",'address-numbers':'o.house_number=1','administrative':'o.administrative_tag=1','all':'1'}
    if kind not in conditions:raise ValueError('Unknown feature kind')
    where=['a.extract_code=?',conditions[kind]];params=[extract_code]
    if identifier:where.append('o.id=?');params.append(identifier)
    if text:
        where.append("o.tags_json LIKE ? ESCAPE '\\'")
        params.append('%'+text.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
    db.row_factory=sqlite3.Row
    rows=db.execute('SELECT o.* FROM observations a JOIN objects o USING(id,variant_sha256) WHERE '+' AND '.join(where)+' ORDER BY o.id,o.variant_sha256 LIMIT ?',params+[limit]).fetchall()
    results=[]
    for row in rows:
        item=dict(row)
        item['tags']=json.loads(item.pop('tags_json'));item['topology']=json.loads(item.pop('topology_json'))
        packed=item.pop('geometry_zlib');item['geometry']=json.loads(zlib.decompress(packed)) if packed else None
        results.append(item)
    return {'extract_code':extract_code,'results':results,'official_assignment_verified':False,'extract_membership_is_legal_country_membership':False,'national_completeness_verified':False,'deliverability_in_scope':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    make=commands.add_parser('build');make.add_argument('--manifest',type=Path,required=True);make.add_argument('--data-root',type=Path,required=True);make.add_argument('--output',type=Path,required=True)
    show=commands.add_parser('summary');show.add_argument('--db',type=Path,required=True)
    find=commands.add_parser('query');find.add_argument('--db',type=Path,required=True);find.add_argument('--extract',required=True);find.add_argument('--kind',choices=['roads','address-numbers','administrative','all'],required=True);find.add_argument('--text');find.add_argument('--id');find.add_argument('--limit',type=int,default=20)
    args=parser.parse_args()
    try:
        if args.command=='build':
            report=build(json.loads(args.manifest.read_text()),args.data_root,args.output)
            args.output.with_suffix('.report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        else:
            with sqlite3.connect(args.db.resolve().as_uri()+'?mode=ro',uri=True) as db:
                report=summarize(db) if args.command=='summary' else query(db,args.extract,args.kind,args.text,args.id,args.limit)
        print(json.dumps(report,ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError,sqlite3.Error,ImportError) as error:parser.exit(2,str(error)+'\n')


if __name__=='__main__':main()
