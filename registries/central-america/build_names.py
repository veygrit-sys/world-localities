#!/usr/bin/env python3
"""Build language-attested names and direct-ID postal evidence; never name-join."""
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile
from build import ROOT, read_csv, write_json, compressed, csv_bytes
from localities.materialize import materialize_country

ALT = 'alternate_name_id geonameid language name is_preferred is_short is_colloquial is_historic valid_from valid_to'.split()
NON_LANGUAGE = {'abbr','link','post','wkdt','unlc','iata','icao','faac','phon'}
NAMES = ['id','entity_id','country_code','source_line'] + ALT
POSTAL = ['id','entity_id','country_code','postal_code','relation','delivery_validated','source_line'] + ALT

def sha(data):
    return hashlib.sha256(data).hexdigest()

def rows_from_zip(path, cc):
    with zipfile.ZipFile(path) as z:
        text = z.read(cc + '.txt').decode('utf-8')
    for n,line in enumerate(text.splitlines(),1):
        parts=line.split('\t')
        if len(parts) != 10:
            raise ValueError(f'{cc}:{n}: expected 10 alternate-name columns')
        yield n,dict(zip(ALT,parts))

def classify(rows, allowed, country):
    names,postals=[],[]
    excluded=Counter()
    seen=set()
    for lineno,r in rows:
        if r['geonameid'] not in allowed:
            excluded['entity_outside_locality_admin_scope']+=1
            continue
        if not r['alternate_name_id'].isdigit() or not r['name']:
            raise ValueError('invalid alternate-name identity or empty name')
        if r['alternate_name_id'] in seen:
            raise ValueError('duplicate alternate-name ID')
        seen.add(r['alternate_name_id'])
        shared=dict(id='geonames-alternate:'+r['alternate_name_id'],entity_id=allowed[r['geonameid']],country_code=country,source_line=str(lineno))
        if r['language']=='post':
            postals.append(dict(**shared,postal_code=r['name'],relation='source_direct_id',delivery_validated='0',**r))
        elif r['language'] not in NON_LANGUAGE and re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*',r['language']):
            names.append(dict(**shared,**r))
        else:
            excluded['untagged_or_non_language']+=1
    return names,postals,dict(excluded)

def build_locale(inputs,output,cc):
    materialize_country(output,cc)
    directory=output/'countries'/cc
    meta=json.loads((directory/'metadata.json').read_text())
    entities=list(read_csv(directory/'entities.csv.gz'))
    allowed={r['geonameid']:r['id'] for r in entities}
    # Country-root label IDs are distinct from political entity source records.
    allowed[meta['country']['geonames_id']]='country:'+cc
    names,postals,excluded=classify(rows_from_zip(inputs/'alternatenames'/(cc+'.zip'),cc),allowed,cc)
    names.sort(key=lambda r:(r['entity_id'],r['language'],int(r['alternate_name_id'])))
    postals.sort(key=lambda r:(r['postal_code'],r['entity_id'],int(r['alternate_name_id'])))
    files={}
    for filename,rows,fields in [('names.csv.gz',names,NAMES),('postal_links.csv.gz',postals,POSTAL)]:
        raw=csv_bytes(rows,fields);data=compressed(raw);(directory/filename).write_bytes(data)
        files[filename]={'rows':len(rows),'bytes':len(data),'sha256':sha(data),'uncompressed_sha256':sha(raw)}
    current=[r for r in names if r['is_historic']!='1' and not r['valid_to']]
    info={'schema_version':1,'source':'GeoNames','license':'CC-BY-4.0',
          'source_file':json.loads((inputs/'alternatenames'/(cc+'.json')).read_text()),
          'country':cc,'files':files,'counts':{'language_tagged_names':len(names),'entities_with_names':len({r['entity_id'] for r in names}),
          'entities_with_current_english':len({r['entity_id'] for r in current if r['language']=='en'}),
          'entities_with_current_spanish':len({r['entity_id'] for r in current if r['language']=='es'}),
          'postal_links':len(postals),'postal_linked_entities':len({r['entity_id'] for r in postals})},
          'language_counts':dict(sorted(Counter(r['language'] for r in names).items())),
          'excluded_counts':excluded,'complete_english_coverage':False,'complete_native_language_coverage':False,
          'language_policy':'Use explicitly tagged source labels; native language is selected by caller locale, not inferred from country or ASCII name.',
          'postal_coverage_complete':False,'postal_delivery_validated':False,
          'postal_policy':'Only source post rows carrying exact GeoNames IDs; no name matching or coordinate inference.',
          'country_root_mapping':{meta['country']['geonames_id']:'country:'+cc}}
    write_json(directory/'locale_metadata.json',info)
    return info

def verify_locale(inputs,output,cc):
    materialize_country(output,cc)
    directory=output/'countries'/cc
    meta=json.loads((directory/'locale_metadata.json').read_text())
    entity_meta=json.loads((directory/'metadata.json').read_text())
    allowed={r['geonameid']:r['id'] for r in read_csv(directory/'entities.csv.gz')}
    allowed[entity_meta['country']['geonames_id']]='country:'+cc
    expected=classify(rows_from_zip(inputs/'alternatenames'/(cc+'.zip'),cc),allowed,cc)
    names=list(read_csv(directory/'names.csv.gz'));postals=list(read_csv(directory/'postal_links.csv.gz'))
    assert sorted(names,key=lambda r:r['id'])==sorted(expected[0],key=lambda r:r['id'])
    assert sorted(postals,key=lambda r:r['id'])==sorted(expected[1],key=lambda r:r['id'])
    for fn, info in meta['files'].items():
        data=(directory/fn).read_bytes(); assert sha(data)==info['sha256'];assert sha(gzip.decompress(data))==info['uncompressed_sha256']
        assert len(list(read_csv(directory/fn)))==info['rows']
    allowed_ids=set(allowed.values())
    assert all(r['entity_id'] in allowed_ids for r in names+postals)
    assert all(r['language']=='post' and r['relation']=='source_direct_id' for r in postals)
    assert len({r['id'] for r in names+postals})==len(names)+len(postals)
    return {'country':cc,**meta['counts'],'errors':0,'source_replay':'exact'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['build','verify']);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,default=ROOT);p.add_argument('--countries',nargs='+',required=True);a=p.parse_args()
    for cc in a.countries:
        result=build_locale(a.inputs,a.output,cc) if a.command=='build' else verify_locale(a.inputs,a.output,cc)
        print(json.dumps({'country':cc,**result.get('counts',result)},ensure_ascii=False))
