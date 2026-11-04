"""Exact OSM identity lookup with a native ID filter and original lexical values."""
import argparse
import json
import re
from pathlib import Path
import east_asia_sources as e
import east_asia_projection as p


def lookup(source, root, identities):
    import osmium
    wanted=set(identities)
    if not wanted or any(not re.fullmatch(r'osm:(node|way|relation):[1-9][0-9]*', value) for value in wanted):
        raise ValueError('Use complete positive OSM identities')
    path=e.verified(source,root);results=[]
    ids=[int(value.rsplit(':',1)[1]) for value in wanted]
    for obj in osmium.FileProcessor(str(path)).with_filter(osmium.filter.IdFilter(ids)):
        kind='node' if obj.is_node() else 'way' if obj.is_way() else 'relation'
        identity='osm:'+kind+':'+str(obj.id)
        if identity not in wanted:continue
        tags={t.k:t.v for t in obj.tags};flags=e.classify(kind,tags)
        if not flags['selected']:continue
        row={'id':identity,'kind':kind,'version':obj.version,'timestamp':str(obj.timestamp),'tags':tags,'classification':flags}
        if kind=='node':row['coordinates']=[obj.location.lon,obj.location.lat] if obj.location.valid() else None
        elif kind=='way':row['nodes']=[str(node.ref) for node in obj.nodes]
        else:row['members']=[{'type':m.type,'ref':str(m.ref),'role':m.role} for m in obj.members]
        results.append(row)
    return {'source_id':source['id'],'source_sha256':source['sha256'],'results':results,
            'missing_ids':sorted(wanted-{r['id'] for r in results}), 'method':'native numeric-ID prefilter plus complete type-qualified identity match',
            'interpolation_expanded':False,'deliverability_in_scope':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=e.DEFAULT_MANIFEST)
    parser.add_argument('--projection-manifest',type=Path,default=p.DEFAULT_MANIFEST)
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--source',required=True);parser.add_argument('--id',action='append',required=True)
    parser.add_argument('--source-projection',action='store_true')
    args=parser.parse_args()
    try:
        manifest=e.load_manifest(args.manifest);source=next(s for s in manifest['sources'] if s['id']==args.source)
        if args.source_projection:
            projection=json.loads(args.projection_manifest.read_text())
            candidates=[r['source'] for r in projection['sources'] if r['source']['id']==source['id'] and r['status']=='PASS']
            if len(candidates)!=1 or candidates[0]['original_source_sha256']!=source['sha256']:raise ValueError('Projection original pin differs')
            source=candidates[0]
        print(json.dumps(lookup(source,args.data_root,args.id),ensure_ascii=False,indent=2))
    except (OSError,ValueError,KeyError,StopIteration) as exc:parser.exit(2,str(exc)+'\n')


if __name__=='__main__':main()
