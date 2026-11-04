#!/usr/bin/env python3
"""Build and verify the source-preserving South America GeoNames pack."""
import argparse, csv, gzip, io, json, re, zipfile
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from localities import geonames as core
from localities.materialize import materialize_country, safe_path
SCOPE = {'AR','BO','BV','BR','CL','CO','EC','FK','GF','GS','GY','PE','PY','SR','UY','VE'}
PENDING = set()
PUBLISHED_SCOPE = SCOPE - PENDING
ALIAS_RAW = 'alternate_name_id geonameid language value preferred short colloquial historic from_period to_period'.split()
ALIAS_FIELDS = ['id','entity_id','value_type'] + ALIAS_RAW
SPECIAL_CODES = {'post':'postal_code','iata':'airport_code','icao':'airport_code','faac':'airport_code','abbr':'abbreviation','link':'link','wkdt':'wikidata_id'}

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=None; self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='tr': self.row=[]
        elif tag=='td' and self.row is not None: self.cell=[]
    def handle_data(self,data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self,tag):
        if tag=='td' and self.cell is not None:
            self.row.append(' '.join(''.join(self.cell).split())); self.cell=None
        elif tag=='tr' and self.row is not None:
            self.rows.append(self.row); self.row=None

def countries(inputs, scope_from=None):
    if scope_from is not None:
        # Reuse the already preserved M49 observations, without recreating HTML.
        source_scope=json.loads(scope_from.read_text(encoding='utf-8'))
        assert source_scope['source_url']==core.M49_URL
        source_rows=source_scope['source_rows']
        assert all(len(r)==12 and r[6]=='005' and r[7]=='South America' for r in source_rows)
    else:
        parser=TableParser(); parser.feed((inputs/'m49.html').read_text())
        source_rows=[r[:12] for r in parser.rows if len(r)>=12 and r[6]=='005' and r[7]=='South America']
    assert len(source_rows)==16 and {r[10] for r in source_rows}==SCOPE
    info={}
    for line in (inputs/'countryInfo.txt').read_text().splitlines():
        if not line or line.startswith('#'): continue
        r=line.split('\t'); info[r[0]]=r
    records=[]
    for r in source_rows:
        cc=r[10]; ci=info[cc]
        records.append(dict(country=cc,id='country:'+cc,name_en=r[8],m49=r[9],alpha3=r[11],region='South America',region_m49='005',geonames_id=ci[16],geonames_continent=ci[8],source_country_languages=ci[15].split(',') if ci[15] else [],status='source_country_or_area'))
    return sorted(records,key=lambda c:c['country']),source_rows

def aliases(path, cc, ids):
    values=[]; total=0
    with zipfile.ZipFile(path) as z:
        with z.open(cc+'.txt') as f:
            for line in io.TextIOWrapper(f,encoding='utf-8'):
                parts=line.rstrip('\r\n').split('\t'); assert len(parts)==10
                total+=1; raw=dict(zip(ALIAS_RAW,parts))
                if raw['geonameid'] not in ids: continue
                assert re.fullmatch('[1-9][0-9]*',raw['alternate_name_id']) and raw['value']
                for flag in ['preferred','short','colloquial','historic']: assert raw[flag] in ('','1')
                typ=SPECIAL_CODES.get(raw['language'],'language_name' if raw['language'] else 'untyped_name')
                values.append(dict(id='gn-alt:'+raw['alternate_name_id'],entity_id='gn:'+raw['geonameid'],value_type=typ,**raw))
    values.sort(key=lambda r:int(r['alternate_name_id']))
    assert len(values)==len({r['id'] for r in values})
    return values,total

def snapshot(path,url,retrieved):
    return dict(url=url,retrieved_on=retrieved,sha256=core.sha(path.read_bytes()),bytes=path.stat().st_size)

def label_coverage(rows, values, country):
    langs={v['entity_id'] for v in values if v['value_type']=='language_name'}
    english={v['entity_id'] for v in values if v['language']=='en' and v['historic']!='1' and not v['to_period']}
    country_langs={l.split('-')[0] for l in country['source_country_languages']}
    native={v['entity_id'] for v in values if v['language'].split('-')[0] in country_langs and v['historic']!='1' and not v['to_period']}
    return dict(language_tagged_name_entities=len(langs),current_english_name_entities=len(english),current_country_language_name_entities=len(native),missing_english_name_entities=len(rows)-len(english),missing_country_language_name_entities=len(rows)-len(native),native_label_rule='Exact source language tag matched against countryInfo language list; no language is inferred from primary name, ASCII, spelling or script. Country-language match is not proof of each place\'s indigenous language.')

def update_inventory(inputs, output, retrieved, selected):
    path=output/'sources/source-inventory.json'
    inventory=json.loads(path.read_text()) if path.exists() else dict(inputs=[],selected_raw_columns_preserved_in_output=True)
    entries={entry['input']:entry for entry in inventory['inputs']}
    source_dir=output/'sources';source_dir.mkdir(parents=True,exist_ok=True)
    for cc in sorted(selected):
        for name,url in [(cc+'.zip',core.SOURCE_URL+cc+'.zip'),(cc+'-alternatenames.zip',core.SOURCE_URL+'alternatenames/'+cc+'.zip')]:
            data=(inputs/name).read_bytes();(source_dir/name).write_bytes(data)
            entries[name]=dict(input=name,repository_path='sources/'+name,**snapshot(inputs/name,url,retrieved))
    name='countryInfo-'+retrieved+'.txt'
    (source_dir/name).write_bytes((inputs/'countryInfo.txt').read_bytes())
    entries[name]=dict(input=name,repository_path='sources/'+name,**snapshot(inputs/'countryInfo.txt',core.SOURCE_URL+'countryInfo.txt',retrieved))
    inventory['inputs']=[entries[k] for k in sorted(entries)]
    inventory['source_archives_included_in_repository']=True
    inventory['source_archive_country_codes']=sorted({e['input'][:2] for e in entries.values() if e.get('repository_path') and e['input'].endswith('.zip')})
    inventory['all_source_archives_included_in_repository']=set(inventory['source_archive_country_codes'])==PUBLISHED_SCOPE
    inventory['retrieval_dates']=sorted({e.get('retrieved_on',inventory.get('retrieved_on')) for e in entries.values()} - {None})
    inventory['publication_scope']=dict(published_country_area_count=len(PUBLISHED_SCOPE),m49_country_area_count=len(SCOPE),pending_country_codes=sorted(PENDING))
    core.write_json(path,inventory)

def build(inputs, output, retrieved, selected, scope_from=None):
    if selected and not set(selected).issubset(PUBLISHED_SCOPE):
        raise ValueError('Requested countries are outside the M49 South America publication')
    selected=set(selected or PUBLISHED_SCOPE)
    required=['countryInfo.txt']+[name for cc in sorted(selected) for name in (cc+'.zip',cc+'-alternatenames.zip')]
    if scope_from is None:required.append('m49.html')
    missing=[name for name in required if not (inputs/name).is_file()]
    if missing:raise FileNotFoundError('Missing source bytes: '+', '.join(missing))
    scope,source_rows=countries(inputs,scope_from)
    m49_source=json.loads(scope_from.read_text()) if scope_from is not None else dict(retrieved_on=retrieved)
    prior=json.loads((output/'scope.json').read_text()) if (output/'scope.json').exists() else {}
    prior_countries={c['country']:c for c in prior.get('countries',[])}
    scope=[prior_countries.get(c['country'],c) if c['country'] not in selected else c for c in scope]
    output.mkdir(parents=True,exist_ok=True)
    core.write_json(output/'scope.json',dict(schema_version=1,source_url=core.M49_URL,retrieved_on=m49_source['retrieved_on'],scope_m49='005',m49_country_area_count=len(SCOPE),source_rows=source_rows,countries=[c for c in scope if c['country'] in PUBLISHED_SCOPE],published_country_area_count=len(PUBLISHED_SCOPE),pending_countries=[],related_separate_layers=[dict(country='BR',layer='official-registry/countries/BR',note='Existing official IBGE municipality layer; not duplicated or reconciled with this pack.')] ))
    for c in scope:
        cc=c['country']
        if cc not in selected: continue
        path=inputs/(cc+'.zip'); raw=list(core.source_rows(path,cc))
        rows=core.build_rows([r for r in raw if r['feature_class'] in ('A','P')],cc)
        sm=snapshot(path,core.SOURCE_URL+cc+'.zip',retrieved)
        sm.update(source_rows=len(raw),retained_rows=len(rows),discarded_feature_classes=dict(Counter(r['feature_class'] for r in raw if r['feature_class'] not in ('A','P'))))
        core.write_country(rows,cc,output,sm,c)
        d=output/'countries'/cc; meta=json.loads((d/'metadata.json').read_text())
        ap=inputs/(cc+'-alternatenames.zip'); values,alias_total=aliases(ap,cc,{r['geonameid'] for r in rows})
        payload=core.csv_bytes(values,ALIAS_FIELDS); encoded=core.compressed(payload); (d/'alternate-values.csv.gz').write_bytes(encoded)
        meta['alternate_values_file']=dict(filename='alternate-values.csv.gz',rows=len(values),bytes=len(encoded),sha256=core.sha(encoded),uncompressed_sha256=core.sha(payload))
        meta['alternate_values_source']=snapshot(ap,core.SOURCE_URL+'alternatenames/'+cc+'.zip',retrieved)
        meta['alternate_values_source'].update(source_rows=alias_total,retained_rows=len(values),source_columns=10)
        meta['label_coverage']=label_coverage(rows,values,c)
        meta['country_profile_source']=snapshot(inputs/'countryInfo.txt',core.SOURCE_URL+'countryInfo.txt',retrieved)
        meta['country_profile_source']['repository_path']='sources/countryInfo-'+retrieved+'.txt'
        meta['postal_coverage']=dict(source_postal_value_rows=sum(v['value_type']=='postal_code' for v in values),postal_validation=False,postal_deliverability_verified=False,note='Only source post-tag values, if any; not joined by place name and not delivery validation.')
        core.write_json(d/'metadata.json',meta)
        print(json.dumps(dict(**meta['counts'],alternate_values=len(values),**meta['label_coverage']),ensure_ascii=False),flush=True)
    update_inventory(inputs,output,retrieved,selected)

def verify(output):
    scope=json.loads((output/'scope.json').read_text()); reports=[]; allids=set(); aliasids=set()
    inventory=json.loads((output/'sources/source-inventory.json').read_text())
    inputs={e['input']:e for e in inventory['inputs']}
    assert len(inputs)==len(inventory['inputs']), 'duplicate source inventory input'
    assert inventory['publication_scope']==dict(published_country_area_count=len(PUBLISHED_SCOPE),m49_country_area_count=len(SCOPE),pending_country_codes=sorted(PENDING))
    assert len(scope['countries'])==scope['published_country_area_count']==len(PUBLISHED_SCOPE)
    assert scope['m49_country_area_count']==len(SCOPE) and scope['pending_countries']==[]
    assert len(scope['source_rows'])==len(SCOPE) and {r[10] for r in scope['source_rows']}==SCOPE
    assert {c['country'] for c in scope['countries']} == PUBLISHED_SCOPE
    assert {p.name for p in (output/'countries').iterdir() if p.is_dir()} == PUBLISHED_SCOPE
    for c in scope['countries']:
        cc=c['country']; d=output/'countries'/cc
        assert d.is_dir(), ('missing published country',cc)
        materialize_country(output,cc)
        meta=json.loads((d/'metadata.json').read_text()); rows=list(core.read_csv(d/'entities.csv.gz')); by={r['id']:r for r in rows}
        assert meta['country']==c
        assert meta['current_official_hierarchy_verified'] is False
        assert meta['postal_coverage']['postal_validation'] is False and meta['postal_coverage']['postal_deliverability_verified'] is False
        for name,source in [(cc+'.zip',meta['source_file']),(cc+'-alternatenames.zip',meta['alternate_values_source'])]:
            entry=inputs[name]
            assert entry['sha256']==source['sha256'] and entry['bytes']==source['bytes']
            assert entry.get('retrieved_on',inventory.get('retrieved_on'))==source['retrieved_on']
        assert meta['source_file']['source_rows']==len(rows)+sum(meta['source_file']['discarded_feature_classes'].values())
        assert len(by)==len(rows); assert not allids.intersection(by); allids.update(by)
        assert rows==core.build_rows([{k:r[k] for k in core.RAW} for r in rows],cc)
        fi=meta['files']['entities.csv.gz']; data=(d/'entities.csv.gz').read_bytes()
        assert len(rows)==fi['rows']==meta['source_file']['retained_rows']
        assert len(data)==fi['bytes'] and core.sha(data)==fi['sha256'] and core.sha(gzip.decompress(data))==fi['uncompressed_sha256']
        for r in rows:
            assert r['country_code']==cc
            pid=r['parent_id']; assert not pid or pid=='country:'+cc or pid in by
            seen={r['id']}; node=pid
            while node in by:
                assert node not in seen;seen.add(node);p=by[node]
                assert p['kind']=='admin_subdivision';node=p['parent_id']
            if pid in by:
                p=by[pid];assert core.code_key(r,int(p['admin_level']))==core.code_key(p,int(p['admin_level']))
                if r['admin_level']: assert int(p['admin_level'])==int(r['admin_level'])-1
            assert not r['state_id'] or (r['state_id'] in by and by[r['state_id']]['admin_level']=='1')
            for f in ['parent_candidates_json','state_candidates_json']: assert all(i in by for i in json.loads(r[f]))
        assert (d/'admin1.csv').read_bytes()==core.csv_bytes([r for r in rows if r['admin_level']=='1'])
        av=list(core.read_csv(d/'alternate-values.csv.gz')); fi=meta['alternate_values_file'];data=(d/'alternate-values.csv.gz').read_bytes()
        assert len(av)==fi['rows'] and len(data)==fi['bytes'] and core.sha(data)==fi['sha256'] and core.sha(gzip.decompress(data))==fi['uncompressed_sha256']
        for a in av:
            assert a['entity_id'] in by and a['id'] not in aliasids;aliasids.add(a['id'])
            assert a['id']=='gn-alt:'+a['alternate_name_id'] and a['entity_id']=='gn:'+a['geonameid']
            assert a['value_type']==SPECIAL_CODES.get(a['language'],'language_name' if a['language'] else 'untyped_name')
            assert a['value'] and all(a[f] in ('','1') for f in ['preferred','short','colloquial','historic'])
        assert meta['label_coverage']==label_coverage(rows,av,c)
        assert meta['postal_coverage']['source_postal_value_rows']==sum(a['value_type']=='postal_code' for a in av)
        expected_counts=dict(country=cc,name_en=c['name_en'],region=c['region'],admin_rows=sum(r['kind']=='admin_subdivision' for r in rows),locality_rows=sum(r['kind']=='locality' for r in rows),other_admin_rows=sum(r['kind']=='other_admin_feature' for r in rows),address_candidates=sum(r['address_candidate']=='1' for r in rows),unresolved_parents=sum(r['parent_relation'] in ('missing_code','missing_reference','ambiguous_code') for r in rows),ambiguous_parents=sum(r['parent_relation']=='ambiguous_code' for r in rows),country_scope_only=sum(r['parent_relation']=='country_scope_only' for r in rows),localities_without_adm1=sum(r['kind']=='locality' and not r['state_id'] for r in rows))
        assert meta['counts']==expected_counts
        source_replay='not_run_original_source_archives_not_published'
        archives=[inputs[cc+'.zip'],inputs[cc+'-alternatenames.zip']]
        if all(e.get('repository_path') for e in archives):
            paths=[safe_path(output,e['repository_path']) for e in archives]
            for path,entry in zip(paths,archives):
                assert path.stat().st_size==entry['bytes'] and core.sha(path.read_bytes())==entry['sha256']
            raw=list(core.source_rows(paths[0],cc))
            assert len(raw)==meta['source_file']['source_rows']
            assert rows==core.build_rows([r for r in raw if r['feature_class'] in ('A','P')],cc)
            assert meta['source_file']['discarded_feature_classes']==dict(Counter(r['feature_class'] for r in raw if r['feature_class'] not in ('A','P')))
            replay_values,total=aliases(paths[1],cc,{r['geonameid'] for r in rows})
            assert av==replay_values and total==meta['alternate_values_source']['source_rows']
            source_replay='exact'
        if 'country_profile_source' in meta:
            source=meta['country_profile_source'];path=safe_path(output,source['repository_path'])
            assert path.stat().st_size==source['bytes'] and core.sha(path.read_bytes())==source['sha256']
            entry=inputs[path.name]
            assert all(entry[k]==source[k] for k in ('bytes','sha256','retrieved_on','url','repository_path'))
            info=[line.split('\t') for line in path.read_text().splitlines() if line.startswith(cc+'\t')]
            assert len(info)==1 and c['source_country_languages']==(info[0][15].split(',') if info[0][15] else [])
        assert not {'address1','street','house_number'}.intersection(rows[0] if rows else {})
        reports.append(dict(country=cc,rows=len(rows),alternate_values=len(av),integrity='passed',derived_columns_replay='exact',source_archive_replay=source_replay,**{k:v for k,v in meta['counts'].items() if k not in ('country','name_en','region')}))
    report=dict(status='passed',scope_countries=len(PUBLISHED_SCOPE),m49_country_area_count=len(SCOPE),pending_country_codes=sorted(PENDING),prepared_countries=len(reports),rows=len(allids),alternate_values=len(aliasids),errors=0,no_address1=True,reports=reports,current_official_hierarchy_verified=False,full_municipality_coverage_verified=False,postal_deliverability_verified=False,source_archive_replay_countries=[r['country'] for r in reports if r['source_archive_replay']=='exact'])
    core.write_json(output/'verification.json',report)
    counts=[json.loads((output/'countries'/r['country']/'metadata.json').read_text())['counts'] for r in reports]
    if counts: (output/'coverage.csv').write_bytes(core.csv_bytes(counts,list(counts[0])))
    core.write_json(output/'manifest.json',dict(schema_version=1,source='GeoNames',data_license='CC-BY-4.0',scope_m49='005',m49_country_area_count=len(SCOPE),pack_country_area_count=len(reports),external_country_area_count=0,pending_country_codes=sorted(PENDING),pending_country_area_count=len(PENDING),complete_pack=len(reports)==len(SCOPE),complete_pack_definition='All M49 South America countries/areas have source A/P gazetteer payloads; this is not official municipality or postal completeness.',complete_published_subset=len(reports)==len(PUBLISHED_SCOPE),complete_official_country_coverage=False,counts=report,countries=[dict(country=r['country'],metadata_sha256=core.sha((output/'countries'/r['country']/'metadata.json').read_bytes())) for r in reports]))
    metadata=[json.loads((output/'countries'/r['country']/'metadata.json').read_text()) for r in reports]
    summary=dict(country_area_count=len(reports),m49_country_area_count=len(SCOPE),pending_country_codes=sorted(PENDING),entity_rows=len(allids),alternate_value_rows=len(aliasids),label_coverage={k:sum(m['label_coverage'][k] for m in metadata) for k in metadata[0]['label_coverage'] if k!='native_label_rule'},source_postal_value_rows=sum(m['postal_coverage']['source_postal_value_rows'] for m in metadata),tests=dict(all_entity_replay='exact',full_pack_integrity='passed',source_archive_replay_countries=report['source_archive_replay_countries']),current_official_hierarchy_verified=False,full_municipality_coverage_verified=False,postal_deliverability_verified=False)
    summary.update({k:sum(m['counts'][k] for m in metadata) for k in ['admin_rows','locality_rows','other_admin_rows','unresolved_parents','address_candidates','country_scope_only','localities_without_adm1']})
    summary['limitations']=['Source A/P selection is not independently verified official municipality completeness',str(summary['unresolved_parents'])+' unresolved exact-code parent references are retained','Labels materially incomplete; ASCII is not English','Source-tagged postal values do not certify delivery coverage','BR GeoNames and official IBGE counts must not be summed as unique real-world places','Original source ZIP replay is available for '+', '.join(report['source_archive_replay_countries'])+'; other countries replay preserved entity columns and validate recorded source archive hashes against the inventory']
    core.write_json(output/'summary.json',summary)
    print(json.dumps({k:v for k,v in report.items() if k!='reports'}));return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['build','verify']);p.add_argument('--inputs',type=Path);p.add_argument('--output',type=Path,default=ROOT);p.add_argument('--retrieved-on');p.add_argument('--countries',nargs='+');p.add_argument('--scope-from',type=Path,help='Reuse preserved M49 source_rows instead of downloading/guessing a changed HTML table');a=p.parse_args()
    if a.command=='build':
        if a.inputs is None:p.error('--inputs required')
        if a.retrieved_on is None:p.error('--retrieved-on required to record the actual retrieval date')
        build(a.inputs,a.output,a.retrieved_on,a.countries,a.scope_from)
    else:verify(a.output)
if __name__=='__main__':main()
