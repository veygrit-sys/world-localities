"""Replay with a complete native key prefilter derived from every PBF string table."""
from collections import Counter
from contextlib import nullcontext
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

import east_asia_sources as e
from osm_evidence import LIFECYCLES
from osm_pbf_lite import fields


def candidate_keys(path):
    keys={'highway','boundary'}|{state+':highway' for state in LIFECYCLES}
    blocks=0
    with Path(path).open('rb') as stream:
        while True:
            prefix=stream.read(4)
            if not prefix:break
            if len(prefix)!=4:raise ValueError('Truncated PBF prefix')
            size=struct.unpack('>I',prefix)[0]
            if not 0<size<=65536:raise ValueError('Invalid PBF header size')
            header=dict(fields(stream.read(size)));size=header[3]
            if not 0<size<=32*1024*1024:raise ValueError('Invalid PBF blob size')
            blob=stream.read(size)
            if len(blob)!=size:raise ValueError('Truncated PBF blob')
            content=dict(fields(blob))
            if 1 in content:data=content[1]
            elif 3 in content and 2 in content and 0<content[2]<=32*1024*1024:
                decoder=zlib.decompressobj();data=decoder.decompress(content[3],content[2]+1)
                if not decoder.eof or decoder.unused_data or len(data)!=content[2]:raise ValueError('PBF decompression differs')
            else:raise ValueError('Unsupported PBF compression')
            if header[1]==b'OSMHeader':continue
            if header[1]!=b'OSMData':raise ValueError('Unknown PBF block type')
            table=next((v for k,v in fields(data) if k==1),None)
            if table is None:raise ValueError('Missing PBF string table')
            for number,value in fields(table):
                if number==1 and value.startswith(b'addr:'):keys.add(value.decode('utf-8'))
            blocks+=1
    if not blocks:raise ValueError('No data blocks')
    return sorted(keys),blocks


def audit_native(source,root,output=None,accepted=None):
    import osmium
    path=e.verified(source,root);output=Path(output) if output is not None else None
    if output is not None and output.exists():raise ValueError('Use a new native projection path')
    if accepted is not None and source['sha256']!=accepted['source_sha256']:raise ValueError('Original audit pin differs')
    keys,blocks=candidate_keys(path);digest=hashlib.sha256();counts=Counter();examples={}
    if output is not None:output.parent.mkdir(parents=True,exist_ok=True)
    with osmium.io.Reader(str(path)) as reader:
        header=reader.header()
        metadata={key:header.get(key) for key in ('generator','osmosis_replication_timestamp','osmosis_replication_sequence_number')}
        manager=osmium.SimpleWriter(str(output),header=header) if output is not None else nullcontext(None)
        with manager as writer:
            for obj in osmium.FileProcessor(str(path)).with_filter(osmium.filter.KeyFilter(*keys)):
                kind='node' if obj.is_node() else 'way' if obj.is_way() else 'relation'
                tags={t.k:t.v for t in obj.tags};flags=e.classify(kind,tags)
                if not flags['selected']:continue
                if writer is not None:writer.add(obj)
                row={'id':'osm:'+kind+':'+str(obj.id),'kind':kind,'version':obj.version,
                     'timestamp':str(obj.timestamp),'tags':tags,'classification':flags}
                if kind=='node':row['coordinates']=[obj.location.lon,obj.location.lat] if obj.location.valid() else None
                elif kind=='way':row['nodes']=[str(n.ref) for n in obj.nodes]
                else:row['members']=[{'type':m.type,'ref':str(m.ref),'role':m.role} for m in obj.members]
                digest.update((e.canonical(row)+'\n').encode());counts['observations']+=1
                for key in ('named_road','house_number','address_tags','administrative_tag','interpolation'):
                    if flags[key]:counts[key]+=1
                if flags['road_state']=='active_tag':counts['active_road_way']+=1
                for label,condition in [('road',flags['road_state']=='active_tag'),('address',flags['house_number']),('admin',flags['administrative_tag'])]:
                    if condition and label not in examples:examples[label]=row
    audited={'source_id':source['id'],'source_sha256':source['sha256'],'source_bytes':source['bytes'],
             'counts':dict(counts),'ordered_rows_sha256':digest.hexdigest(),'metadata':metadata,'examples':examples}
    if accepted is not None and audited!=accepted:
        raise ValueError('Native candidate replay differs from complete original audit')
    if e.file_hash(path)!=source['sha256']:raise ValueError('Original source changed')
    pin=None
    if output is not None:
        pin={'id':source['id'],'country':source['country'],'format':'selected_osm_pbf',
             'role':source['role'],'path':output.name,'bytes':output.stat().st_size,'sha256':e.file_hash(output),
             'licence':source['licence'],'licence_url':source['licence_url'],'attribution':source['attribution']}
        actual=e.audit_one(dict(pin,format='osm_pbf'),output.parent)
        for key in ('counts','ordered_rows_sha256','examples'):
            if actual[key]!=audited[key]:raise ValueError('Written native projection differs: '+key)
        pin.update(path='projections/'+output.name,original_source_sha256=source['sha256'],
                   original_source_bytes=source['bytes'],original_source_url=source['url'],original_pbf_preserved_in_distribution=False)
    method='Every original PBF string table scanned for all addr: keys; native key prefilter covers every classifier trigger; canonical rows and written native PBF match the full original audit'
    common={'status':'PASS','source_id':source['id'],'source_sha256':source['sha256'],
            'observations':counts['observations'],'ordered_rows_sha256':digest.hexdigest(),
            'implementation_sha256':e.implementation_pins(),'replay_implementation_sha256':e.file_hash(__file__),
            'pbf_field_reader_sha256':e.file_hash(e.ROOT/'scripts/osm_pbf_lite.py'),
            'candidate_keys':keys,'string_table_data_blocks':blocks,'method':method,
            'independent_parser_implementation':False}
    projection={'status':'PASS','source':pin,'counts':dict(counts),'ordered_rows_sha256':digest.hexdigest(),
                'projection_implementation_sha256':e.file_hash(__file__),'classifier_implementation_sha256':e.implementation_pins(),
                'verification':method,'candidate_keys':keys,'string_table_data_blocks':blocks,
                'all_tags_versions_timestamps_and_ordered_references_preserved':True,
                'untagged_dependency_nodes_copied':False,'way_or_relation_geometry_assembled':False,
                'interpolation_expanded':False,'national_completeness_verified':False}
    return audited,common,projection if output is not None else None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['audit','replay-export'])
    parser.add_argument('--manifest',type=Path,default=e.DEFAULT_MANIFEST)
    parser.add_argument('--data-root',type=Path,required=True);parser.add_argument('--source',required=True)
    parser.add_argument('--accepted',type=Path);parser.add_argument('--projection-output',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    try:
        source=next(s for s in e.load_manifest(args.manifest)['sources'] if s['id']==args.source and s['format']=='osm_pbf')
        accepted=json.loads(args.accepted.read_text()) if args.accepted else None
        if accepted is not None and 'sources' in accepted:
            accepted=next(r for r in accepted['sources'] if r['source_id']==source['id'])
        if args.command=='replay-export' and (accepted is None or args.projection_output is None):
            raise ValueError('replay-export requires --accepted and a new --projection-output')
        audit,replay,projection=audit_native(source,args.data_root,args.projection_output,accepted)
        result=audit if args.command=='audit' else {'audit':audit,'replay':replay,'projection':projection}
        text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
        if args.output:args.output.write_text(text)
        else:print(text,end='')
    except (OSError,ValueError,KeyError,StopIteration) as exc:parser.exit(2,str(exc)+'\n')


if __name__=='__main__':main()
