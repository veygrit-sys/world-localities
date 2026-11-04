#!/usr/bin/env python3
"""Verify independent country batches against preserved raw source snapshots."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
from build import ROOT, RAW, FIELDS, build_rows, source_rows, csv_bytes, read_csv, write_json
from build_names import verify_locale
from localities.materialize import materialize_country

def digest(data):
    return hashlib.sha256(data).hexdigest()

def verify_country(root,cc):
    materialize_country(root,cc)
    d=root/'countries'/cc
    meta=json.loads((d/'metadata.json').read_text())
    raw_source=(root/'sources'/(cc+'.zip')).read_bytes()
    assert digest(raw_source)==meta['source_file']['sha256'],(cc,'raw source checksum')
    rows=list(read_csv(d/'entities.csv.gz'))
    source=list(source_rows(root/'sources'/(cc+'.zip'),cc))
    expected=build_rows([r for r in source if r['feature_class'] in ('A','P')],cc)
    assert rows==expected,(cc,'entity raw-source replay mismatch')
    assert len(source)==meta['source_file']['source_rows']
    assert len(rows)==meta['source_file']['retained_rows']
    by_id={r['id']:r for r in rows};assert len(rows)==len(by_id)
    for r in rows:
        visited={r['id']};parent=r['parent_id']
        while parent in by_id:
            assert parent not in visited,(cc,'cycle',parent)
            visited.add(parent);parent=by_id[parent]['parent_id']
        assert not parent or parent=='country:'+cc,(cc,'unresolved referenced ID')
    for fn,info in meta['files'].items():
        data=(d/fn).read_bytes();assert digest(data)==info['sha256'];assert digest(gzip.decompress(data))==info['uncompressed_sha256']
    preview=(d/'admin1.csv').read_bytes();assert digest(preview)==meta['preview_files']['admin1.csv']['sha256'];assert preview==csv_bytes([r for r in rows if r['admin_level']=='1'])
    lm=json.loads((d/'locale_metadata.json').read_text())
    assert digest((root/'sources/alternatenames'/(cc+'.zip')).read_bytes())==lm['source_file']['sha256']
    locale=verify_locale(root/'sources',root,cc)
    return {'country':cc,'entities':len(rows),'source_rows':len(source),'unresolved_parents':meta['counts']['unresolved_parents'],'source_replay':'exact','errors':0,'locale':locale}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--countries',nargs='+');p.add_argument('--report',type=Path);a=p.parse_args()
    selected=a.countries or [c['country'] for c in json.loads((a.root/'scope.json').read_text())['countries']]
    reports=[verify_country(a.root,c) for c in selected]
    result={'countries':len(reports),'entities':sum(r['entities'] for r in reports),'language_tagged_names':sum(r['locale']['language_tagged_names'] for r in reports),'postal_links':sum(r['locale']['postal_links'] for r in reports),'errors':0,'reports':reports,'limits':['Source replay and referential checks do not certify source accuracy or current legal hierarchy.','Raw GeoNames A/P scope is not every real-world settlement or an official municipal register.']}
    if a.report:write_json(a.report,result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
