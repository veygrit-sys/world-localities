"""Replay selected raw OSM identities, tags and topology against a built evidence index."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import zlib

import osm_evidence as evidence


def verify(manifest, data_root, database):
    import osmium
    results=[]
    with sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or db.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('SQLite integrity failure')
        implementation=db.execute("SELECT value FROM metadata WHERE key='implementation_sha256'").fetchone()
        if implementation is None or json.loads(implementation[0])!=evidence.file_hash(evidence.__file__):
            raise ValueError('Index implementation differs; rebuild before replay')
        receipts=list(evidence.verified_sources(manifest,data_root))
        if {row[0] for row in db.execute('SELECT extract_code FROM sources')}!={source['country_extract'] for source,_ in receipts}:
            raise ValueError('Database extract inventory differs from pinned sources')
        for source,path in receipts:
            code=source['country_extract'];counts=Counter();digest=hashlib.sha256()
            if json.loads(db.execute('SELECT receipt_json FROM sources WHERE extract_code=?',(code,)).fetchone()[0])!=source:
                raise ValueError('Stored source receipt differs from pinned manifest')

            class Replay(osmium.SimpleHandler):
                def inspect(self,obj,kind):
                    counts['scanned_'+kind]+=1
                    if not len(obj.tags):return
                    tags={tag.k:tag.v for tag in obj.tags}
                    retain=(kind=='way' and (bool(tags.get('highway')) or any(tags.get(prefix+':highway') for prefix in ('construction','proposed','abandoned','disused','demolished','razed')))) or any(key.startswith('addr:') for key in tags) or tags.get('boundary')=='administrative'
                    if not retain:return
                    identifier='osm:'+kind+':'+str(obj.id)
                    rows=db.execute('''SELECT o.version,o.timestamp,o.tags_json,o.topology_json,o.geometry_zlib,o.geometry_status,o.variant_sha256,o.road_state,o.named_road,o.address_tags,o.house_number,o.interpolation,o.administrative_tag
                        FROM observations a JOIN objects o USING(id,variant_sha256) WHERE a.extract_code=? AND a.id=?''',(code,identifier)).fetchall()
                    if len(rows)!=1:raise ValueError('Missing or repeated source observation: '+identifier)
                    version,timestamp,raw_tags,raw_topology,packed,status,variant_sha256,*stored_flags=rows[0]
                    topology={}
                    if kind=='way':topology={'nodes':[str(node.ref) for node in obj.nodes]}
                    elif kind=='relation':topology={'members':[{'type':member.type,'ref':str(member.ref),'role':member.role} for member in obj.members]}
                    if version!=obj.version or timestamp!=str(obj.timestamp) or json.loads(raw_tags)!=tags or json.loads(raw_topology)!=topology:
                        raise ValueError('Raw source replay mismatch: '+identifier)
                    geometry=json.loads(zlib.decompress(packed)) if packed else None
                    payload={'id':identifier,'version':version,'timestamp':timestamp,'tags':tags,'topology':topology,'geometry':geometry,'geometry_status':status}
                    if hashlib.sha256(evidence.canonical(payload).encode()).hexdigest()!=variant_sha256:
                        raise ValueError('Stored feature payload hash mismatch: '+identifier)
                    flags=evidence.classify(kind,tags)
                    expected_flags=[flags['road_state']]+[int(flags[key]) for key in ['named_road','address_tags','house_number','interpolation','administrative_tag']]
                    if stored_flags!=expected_flags:raise ValueError('Stored classification flags changed')
                    expected_geometry=None
                    if kind=='node':
                        expected_status='complete' if obj.location.valid() else 'missing_location'
                        if obj.location.valid():expected_geometry={'type':'Point','coordinates':[obj.location.lon,obj.location.lat]}
                    elif kind=='way':
                        complete=len(obj.nodes)>=2 and all(node.location.valid() for node in obj.nodes)
                        expected_status='complete' if complete else 'missing_node_locations_or_short_way'
                        if complete:expected_geometry={'type':'LineString','coordinates':[[node.location.lon,node.location.lat] for node in obj.nodes]}
                    else:expected_status='relation_member_geometry_not_assembled'
                    if geometry!=expected_geometry or status!=expected_status:
                        raise ValueError('Original geometry replay mismatch: '+identifier)
                    digest.update(evidence.canonical({'id':identifier,'version':version,'timestamp':timestamp,'tags':tags,'topology':topology}).encode()+b'\n')
                    counts['matched_observations']+=1
                def node(self,obj):self.inspect(obj,'node')
                def way(self,obj):self.inspect(obj,'way')
                def relation(self,obj):self.inspect(obj,'relation')

            with tempfile.TemporaryDirectory(prefix='osm-evidence-replay-') as locations:
                Replay().apply_file(str(path),locations=True,idx='sparse_file_array,'+str(Path(locations)/(code+'.locations')))
            if counts['matched_observations']!=db.execute('SELECT count(*) FROM observations WHERE extract_code=?',(code,)).fetchone()[0]:
                raise ValueError('Unreplayed database observations')
            result={'extract_code':code,'status':'PASS','counts':dict(counts),'canonical_source_replay_sha256':digest.hexdigest()}
            results.append(result)
            print(evidence.canonical({'extract_code':code,'status':'REPLAYED'}),flush=True)
        summary=evidence.summarize(db)
    return {'status':'PASS','checked_at':datetime.now(timezone.utc).isoformat(),'extracts':results,
            'matched_observations':sum(row['counts']['matched_observations'] for row in results),
            'sqlite_integrity':'PASS','foreign_keys':'PASS','feature_payload_hashes':'PASS','source_node_and_way_coordinates':'PASS','classification_flags':'PASS','summary':summary,
            'not_verified':['National real-world completeness','Legal country membership of buffered extracts','Issuing-authority assignment of housenumber tags','Full assembly of administrative relation geometry'],
            'deliverability_in_scope':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,required=True);parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--db',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        report=verify(json.loads(args.manifest.read_text()),args.data_root,args.db)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        print(evidence.canonical({'status':'PASS','matched_observations':report['matched_observations']}))
    except (OSError,ValueError,KeyError,sqlite3.Error,ImportError) as error:parser.exit(2,str(error)+'\n')


if __name__=='__main__':main()
