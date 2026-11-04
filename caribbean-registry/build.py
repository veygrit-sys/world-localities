#!/usr/bin/env python3
"""Reproducible Caribbean GeoNames gazetteer and attested alternate names. Stdlib only."""
import argparse, base64, csv, gzip, hashlib, io, json, re, zipfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from localities import geonames as core

RAW = core.RAW
FIELDS = core.FIELDS
read_csv = core.read_csv
source_rows = core.source_rows
build_rows = core.build_rows
csv_bytes = core.csv_bytes
compressed = core.compressed
sha = core.sha
write_json = core.write_json
code_key = core.code_key


def write_country(rows, country, output, source_meta, country_meta):
    return core.write_country(
        rows,
        country,
        output,
        source_meta,
        country_meta,
        registry_root=ROOT,
    )

CODES='AG AI AW BB BL BQ BS CW DM DO GD GP HT JM KN KY LC MF MQ MS PR SX TC TT VC VG VI'.split()
M49_SCOPE_CODES=sorted(CODES+['CU'])
ALT_RAW='alternate_name_id geonameid language name is_preferred is_short is_colloquial is_historic from to'.split()
ALT_FIELDS=['id','entity_id','record_kind']+ALT_RAW
SPECIAL={'post':'postal_code','link':'link','wkdt':'wikidata_id','iata':'iata','icao':'icao','faac':'faac','abbr':'abbreviation','phon':'phonetic','unlc':'unlocode','tcid':'transport_canada_id'}
class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=None; self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr': self.row=[]
        if tag in ('td','th'): self.cell=''
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            if self.row is not None: self.row.append(' '.join(self.cell.split()))
            self.cell=None
        if tag=='tr' and self.row is not None: self.rows.append(self.row); self.row=None
    def handle_data(self,data):
        if self.cell is not None: self.cell+=data

def make_scope(inputs):
    parser=TableParser(); parser.feed((inputs/'m49.html').read_text())
    idx=next(i for i,r in enumerate(parser.rows) if r[:2]==['Caribbean','029'])
    selected=[]
    for r in parser.rows[idx+1:]:
        if not r[2]: break
        selected.append(r[:3])
    info={}
    for line in (inputs/'countryInfo.txt').read_text().splitlines():
        if not line or line.startswith('#'): continue
        r=line.split('\t'); info[r[1]]=r
    countries=[]
    for name,m49,a3 in selected:
        r=info[a3]; cc=r[0]
        countries.append({'country':cc,'id':'country:'+cc,'alpha3':a3,'m49':m49,'name_en':name,
          'region':'Caribbean','region_m49':'029','geonames_country_name':r[4],'geonames_id':r[16],
          'source_language_codes':r[15].split(',') if r[15] else [],'status':'source_country_or_area'})
    assert sorted(c['country'] for c in countries)==M49_SCOPE_CODES, 'M49 scope changed; review required'
    countries=[c for c in countries if c['country'] in CODES]
    return {'schema_version':1,'scope_name':'UN M49 Caribbean partial publication: 27 of 28 countries and areas','m49_scope_count':28,'published_scope_count':27,'omitted_countries':[{'country':'CU','status':'omitted_from_this_publication'}],'region_m49':'029','source_url':'https://unstats.un.org/unsd/methodology/m49/',
       'retrieved_on':'2026-10-01','source_html_sha256':sha((inputs/'m49.html').read_bytes()),
       'country_info_sha256':sha((inputs/'countryInfo.txt').read_bytes()),'countries':sorted(countries,key=lambda x:x['country']),
       'scope_note':'Statistical grouping only; does not imply any position on sovereignty. Puerto Rico and US Virgin Islands remain independent source country scopes; do not add counts to overlapping US official snapshots.'}

def alt_rows(path,cc,entity_ids):
    with zipfile.ZipFile(path) as z:
        data=z.read(cc+'.txt').decode('utf-8')
    retained=[]; total=0; unmatched=0
    for line in data.splitlines():
        v=line.split('\t'); total+=1
        if len(v)!=10: raise ValueError('alternateNamesV2 schema changed')
        r=dict(zip(ALT_RAW,v))
        if 'gn:'+r['geonameid'] not in entity_ids: unmatched+=1; continue
        for flag in ('is_preferred','is_short','is_colloquial','is_historic'): assert r[flag] in ('','1')
        assert r['alternate_name_id'].isdigit() and r['name']
        retained.append(dict(id='gn-alt:'+r['alternate_name_id'],entity_id='gn:'+r['geonameid'],record_kind=SPECIAL.get(r['language'],'name'),**r))
    retained.sort(key=lambda r:int(r['alternate_name_id']))
    assert len({r['id'] for r in retained})==len(retained)
    return retained,total,unmatched

def info_file(data,payload,rows):
    return {'rows':rows,'bytes':len(payload),'sha256':sha(payload),'uncompressed_sha256':sha(data)}

def build_one(cc,inputs,output,scope):
    cm=next(c for c in scope['countries'] if c['country']==cc)
    p=inputs/(cc+'.zip'); raw=list(source_rows(p,cc)); rows=build_rows([r for r in raw if r['feature_class'] in ('A','P')],cc)
    sm={'url':'https://download.geonames.org/export/dump/'+cc+'.zip','retrieved_on':'2026-10-01','sha256':sha(p.read_bytes()),'bytes':p.stat().st_size,'source_rows':len(raw),'retained_rows':len(rows),
       'discarded_feature_classes':dict(Counter(r['feature_class'] for r in raw if r['feature_class'] not in ('A','P')))}
    stats=write_country(rows,cc,output,sm,cm); d=output/'countries'/cc
    p=inputs/(cc+'-alternates.zip'); alts,total,unmatched=alt_rows(p,cc,{r['id'] for r in rows})
    meta=json.loads((d/'metadata.json').read_text())
    meta['alternate_names_source']={'url':'https://download.geonames.org/export/dump/alternatenames/'+cc+'.zip','retrieved_on':'2026-10-01','sha256':sha(p.read_bytes()),'bytes':p.stat().st_size,
        'source_rows':total,'retained_direct_id_rows':len(alts),'discarded_not_in_entity_scope':unmatched}
    # Keep all records, including source tags that are not linguistic labels.
    data=csv_bytes(alts,ALT_FIELDS); payload=compressed(data); (d/'alternate-names.csv.gz').write_bytes(payload)
    meta['auxiliary_files']={'alternate-names.csv.gz':info_file(data,payload,len(alts))}
    labels=[r for r in alts if r['record_kind']=='name']; english={r['entity_id'] for r in labels if r['language']=='en' or r['language'].startswith('en-')}
    source_languages={x.split('-')[0] for x in cm['source_language_codes']}
    local={r['entity_id'] for r in labels if r['language'].split('-')[0] in source_languages}
    meta['label_coverage']={'source_language_tagged_name_rows':sum(bool(r['language']) for r in labels),'untagged_name_rows':sum(not r['language'] for r in labels),
       'entities_with_attested_english':len(english),'entities_with_attested_country_language':len(local),'entities_without_attested_english':len(rows)-len(english),
       'country_language_reference':'GeoNames countryInfo language codes; not independently verified official/native-language status',
       'language_counts':dict(sorted(Counter(r['language'] or 'und' for r in labels).items())),
       'complete_native_and_english_coverage':False,'asciiname_is_english_translation':False,'generated_translations':0}
    postal=[r for r in alts if r['record_kind']=='postal_code']
    if postal:
        data=csv_bytes(postal,ALT_FIELDS); payload=compressed(data); (d/'postal-links.csv.gz').write_bytes(payload)
        meta['auxiliary_files']['postal-links.csv.gz']=info_file(data,payload,len(postal))
    meta['postal_coverage']={'direct_source_id_rows':len(postal),'relation':'GeoNames alternate-name post tag linked by exact geonameid; not postal-authority confirmation',
       'completeness_verified':False,'deliverability_verified':False,'note':'Subset projection of alternate-names.csv.gz; do not add to alias counts. No name/proximity matching.'}
    meta['auxiliary_record_kind_counts']=dict(sorted(Counter(r['record_kind'] for r in alts).items()))
    meta['scope_overlap_note']='Puerto Rico is independently scoped by GeoNames. Existing US official PR municipality coverage is a separate layer; no inferred cross-source links.' if cc=='PR' else ('US Virgin Islands is independently scoped by GeoNames; no inferred US official cross-source links.' if cc=='VI' else '')
    write_json(d/'metadata.json',meta)
    return dict(stats,entities=len(rows),alternate_rows=len(alts),postal_rows=len(postal),english_entities=len(english))

def verify_one(cc,output):
    d=output/'countries'/cc; m=json.loads((d/'metadata.json').read_text()); rows=[]
    for filename,info in m['files'].items():
        p=(d/filename).read_bytes(); data=gzip.decompress(p) if filename.endswith('.gz') else p
        assert sha(p)==info['sha256'] and sha(data)==info['uncompressed_sha256']
        rs=list(read_csv(d/filename)); assert len(rs)==info['rows']; rows.extend(rs)
    byid={r['id']:r for r in rows}; assert len(byid)==len(rows)
    for r in rows:
        assert r['id']=='gn:'+r['geonameid'] and r['country_code']==cc
        pid=r['parent_id']; assert not pid or pid=='country:'+cc or pid in byid
        if pid in byid:
            p=byid[pid]; assert p['kind']=='admin_subdivision'
            assert code_key(r,int(p['admin_level']))==code_key(p,int(p['admin_level']))
            if r['admin_level']: assert int(r['admin_level'])==int(p['admin_level'])+1
        visited={r['id']}
        while pid in byid:
            assert pid not in visited; visited.add(pid); pid=byid[pid]['parent_id']
        assert not r['state_id'] or byid[r['state_id']]['admin_level']=='1'
        for field in ['parent_candidates_json','state_candidates_json']: assert all(x in byid for x in json.loads(r[field]))
    assert rows==build_rows([{k:r[k] for k in RAW} for r in rows],cc), 'non-reproducible entity transform'
    preview=(d/'admin1.csv').read_bytes(); assert preview==csv_bytes([r for r in rows if r['admin_level']=='1'])
    assert sha(preview)==m['preview_files']['admin1.csv']['sha256']
    assert len(rows)==m['source_file']['retained_rows']
    aux={}
    for filename,info in m['auxiliary_files'].items():
        p=(d/filename).read_bytes(); data=gzip.decompress(p); assert sha(p)==info['sha256'] and sha(data)==info['uncompressed_sha256']
        rs=list(read_csv(d/filename)); assert len(rs)==info['rows']; assert len({r['id'] for r in rs})==len(rs)
        for r in rs:
            assert r['entity_id'] in byid and r['entity_id']=='gn:'+r['geonameid']
            assert r['id']=='gn-alt:'+r['alternate_name_id'] and r['record_kind']==SPECIAL.get(r['language'],'name')
        aux[filename]=rs
    alts=aux['alternate-names.csv.gz']; assert len(alts)==m['alternate_names_source']['retained_direct_id_rows']
    assert [r for r in alts if r['record_kind']=='postal_code']==aux.get('postal-links.csv.gz',[])
    labels=[r for r in alts if r['record_kind']=='name']; en={r['entity_id'] for r in labels if r['language']=='en' or r['language'].startswith('en-')}
    assert len(en)==m['label_coverage']['entities_with_attested_english']
    return {'country':cc,'rows':len(rows),'alternate_rows':len(alts),'postal_rows':m['postal_coverage']['direct_source_id_rows'],'integrity':'passed','replay':'exact'}

def summarize(output,scope):
    ready=[c['country'] for c in scope['countries'] if (output/'countries'/c['country']/'metadata.json').exists()]
    reports=[verify_one(cc,output) for cc in ready]; seen=set(); alt_seen=set()
    for cc in ready:
        for filename,idset in [('entities.csv.gz',seen),('alternate-names.csv.gz',alt_seen)]:
            ids={r['id'] for r in read_csv(output/'countries'/cc/filename)}
            assert not idset.intersection(ids), 'duplicate identity across source countries'; idset.update(ids)
    metas=[json.loads((output/'countries'/cc/'metadata.json').read_text()) for cc in ready]
    cov=[dict(m['counts'],entities=sum(i['rows'] for i in m['files'].values()),alternate_rows=m['alternate_names_source']['retained_direct_id_rows'],postal_rows=m['postal_coverage']['direct_source_id_rows'],english_entities=m['label_coverage']['entities_with_attested_english']) for m in metas]
    if cov:(output/'coverage.csv').write_bytes(csv_bytes(cov,list(cov[0])))
    totals={k:sum(r[k] for r in cov) for k in cov[0] if isinstance(cov[0][k],int)} if cov else {}
    manifest={'schema_version':1,'scope_count':len(M49_SCOPE_CODES),'prepared_count':len(ready),'prepared_countries':ready,'missing_countries':sorted(set(M49_SCOPE_CODES)-set(ready)),'totals':totals,
       'countries':[{'country':cc,'metadata_sha256':sha((output/'countries'/cc/'metadata.json').read_bytes())} for cc in ready],
       'scope_sha256':sha((output/'scope.json').read_bytes()),'license':'CC-BY-4.0','prepared_on':'2026-10-01',
       'coverage_claim':'Partial publication: 27 of 28 M49 countries/areas, Cuba omitted. All A/P rows from each acquired GeoNames country extract; legal municipality, native/English label, and postal completeness unverified.'}
    write_json(output/'manifest.json',manifest)
    write_json(output/'verification.json',{'schema_version':1,'countries':len(reports),'rows':len(seen),'alternate_rows':len(alt_seen),'errors':0,'reports':reports,
       'limits':['Integrity and source-code replay are verified; legal hierarchy and source accuracy are not.','Postal rows are direct-ID GeoNames observations, not authoritative address deliverability.']})
    return manifest

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('command',choices=['build','verify','summarize']); p.add_argument('--inputs',type=Path);p.add_argument('--output',type=Path,default=ROOT);p.add_argument('--country',nargs='+'); a=p.parse_args()
    if a.command=='build':
        if not a.inputs:p.error('--inputs required')
        scope=make_scope(a.inputs); write_json(a.output/'scope.json',scope)
        for cc in a.country or CODES:
            assert cc in CODES; print(json.dumps(build_one(cc,a.inputs,a.output,scope)),flush=True); verify_one(cc,a.output)
    else:scope=json.loads((a.output/'scope.json').read_text())
    if a.command=='verify':
        manifest=json.loads((a.output/'manifest.json').read_text())
        assert sha((a.output/'scope.json').read_bytes())==manifest['scope_sha256']
        selected=a.country or manifest['prepared_countries']
        hashes={r['country']:r['metadata_sha256'] for r in manifest['countries']}
        reports=[]; ids=set(); aids=set()
        for cc in selected:
            assert cc in CODES
            assert sha((a.output/'countries'/cc/'metadata.json').read_bytes())==hashes[cc], 'metadata checksum mismatch'
            reports.append(verify_one(cc,a.output))
            for filename,seen in [('entities.csv.gz',ids),('alternate-names.csv.gz',aids)]:
                new_ids={r['id'] for r in read_csv(a.output/'countries'/cc/filename)}
                assert not seen.intersection(new_ids); seen.update(new_ids)
        if not a.country:
            assert len(ids)==manifest['totals']['entities'] and len(aids)==manifest['totals']['alternate_rows']
            assert len(selected)==manifest['prepared_count']
        print(json.dumps({'countries':len(reports),'rows':len(ids),'alternate_rows':len(aids),'errors':0,'reports':reports}),flush=True)
    else:print(json.dumps(summarize(a.output,scope)),flush=True)
if __name__=='__main__':main()
