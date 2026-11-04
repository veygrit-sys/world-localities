"""Download pinned public Geofabrik extracts; never overwrite an accepted directory."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
import argparse
import hashlib
import json
import re

EXTRACTS={'belize':'BZ','costa-rica':'CR','el-salvador':'SV','guatemala':'GT','honduras':'HN','nicaragua':'NI','panama':'PA','mexico':'MX'}
INDEX_URL='https://download.geofabrik.de/index-v1.json'


def open_source(url):
    if not url.startswith('https://download.geofabrik.de/'):
        raise ValueError('Expected a public Geofabrik download URL')
    return urlopen(Request(url,headers={'User-Agent':'WorldLocalities/0.1 (source-qualified open geodata research)','Accept-Encoding':'identity'}),timeout=60)


def publisher_checksum(url):
    with open_source(url+'.md5') as response:value=response.read(4096).decode('ascii')
    match=re.match(r'([0-9a-fA-F]{32})\b',value)
    if not match:raise ValueError('Invalid publisher checksum')
    return match[1].lower()


def acquire(extract_id,code,url,root,pin=None):
    before=publisher_checksum(url)
    path=root/'sources'/(code+'.osm.pbf')
    temp=path.with_suffix('.part')
    sha,md5=hashlib.sha256(),hashlib.md5()
    with open_source(url) as response,temp.open('xb') as target:
        final=response.url;size=0
        headers={k:v for k,v in response.headers.items() if k.lower() in ('etag','last-modified','content-type','content-length')}
        for block in iter(lambda:response.read(1024*1024),b''):
            target.write(block);size+=len(block);sha.update(block);md5.update(block)
        declared=response.headers.get('Content-Length')
        if declared is not None and size!=int(declared):raise ValueError('Truncated extract')
    if before!=publisher_checksum(url) or md5.hexdigest()!=before:raise ValueError('Moving snapshot or invalid publisher checksum')
    if pin and (size!=pin['bytes'] or sha.hexdigest()!=pin['sha256']):raise ValueError('Pinned source changed')
    temp.replace(path)
    receipt={'country_extract':code,'source_id':'geofabrik-osm-'+code.lower(),'extract_id':extract_id,'requested_url':url,'resolved_url':final,'retrieved_at':datetime.now(timezone.utc).isoformat(),'bytes':size,'sha256':sha.hexdigest(),'publisher_md5':before,'publisher_checksum_stable_before_after':True,'http_metadata':headers,'licence':'ODbL-1.0','licence_url':'https://opendatacommons.org/licenses/odbl/1-0/','attribution':'OpenStreetMap contributors; extract by Geofabrik','path':'sources/'+path.name,'extract_is_not_a_legal_country_boundary':True}
    (root/(code+'.receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'extract_code':code,'status':'DOWNLOADED_VERIFIED','bytes':size}),flush=True)
    return receipt


def download(output,manifest=None,workers=3):
    output=Path(output).resolve()
    if output.exists() or output.is_symlink():raise ValueError('Use a new download directory')
    if not 1<=workers<=3:raise ValueError('Use one to three download workers')
    jobs=[]
    footprints=[]
    if manifest is not None:
        pins=json.loads(Path(manifest).read_text())
        for pin in pins['sources']:
            if EXTRACTS.get(pin['extract_id'])!=pin['country_extract']:raise ValueError('Unexpected extract scope')
            jobs.append((pin['extract_id'],pin['country_extract'],pin['resolved_url'],pin))
        if len(jobs)!=8 or {job[1] for job in jobs}!=set(EXTRACTS.values()):raise ValueError('Incomplete eight-extract manifest')
    else:
        with open_source(INDEX_URL) as response:index_bytes=response.read()
        index=json.loads(index_bytes)
        for feature in index['features']:
            properties=feature['properties'];extract_id=properties['id']
            if extract_id in EXTRACTS:
                code=EXTRACTS[extract_id]
                if properties.get('iso3166-1:alpha2')!=[code]:raise ValueError('Publisher extract scope changed')
                jobs.append((extract_id,code,properties['urls']['pbf'],None));footprints.append(feature)
        if len(jobs)!=8:raise ValueError('Missing extract in publisher index')
    (output/'sources').mkdir(parents=True)
    if footprints:
        (output/'extract-footprints.geojson').write_text(json.dumps({'type':'FeatureCollection','features':footprints})+'\n')
    receipts=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending=[pool.submit(acquire,key,code,url,output,pin) for key,code,url,pin in jobs]
        for task in as_completed(pending):receipts.append(task.result())
    report={'schema_version':1,'scope_codes':sorted(EXTRACTS.values()),'sources':sorted(receipts,key=lambda x:x['country_extract']),'national_completeness_verified':False,'deliverability_in_scope':False}
    (output/'source-manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--manifest',type=Path,help='Replay resolved dated URLs and require identical SHA-256 and size')
    parser.add_argument('--workers',type=int,default=3)
    args=parser.parse_args()
    try:
        report=download(args.output,args.manifest,args.workers)
        print(json.dumps({'status':'DOWNLOADED_VERIFIED','extracts':len(report['sources']),'bytes':sum(source['bytes'] for source in report['sources'])}))
    except (OSError,ValueError,KeyError) as error:parser.exit(2,str(error)+'\n')


if __name__=='__main__':main()
