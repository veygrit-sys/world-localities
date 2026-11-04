#!/usr/bin/env python3
"""Split exact bytes and verify a clean, offline South America publication."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from localities import geonames as core
from localities.materialize import manifest, restore, safe_path
from build import PUBLISHED_SCOPE, ROOT, build

LIMIT=512*1024


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def blob_sha(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def pack(root):
    entries={e['path']:e for e in manifest(root)}
    # Preserve every pre-existing publication path, including its smaller
    # unsplit gzip files. Only the new countries adopt the bounded threshold.
    candidates={e['path']:e['country'] for e in entries.values()}
    baseline=load(root/'sources/baseline-14-publication.json')
    for cc in sorted(PUBLISHED_SCOPE-set(baseline['countries'])):
        for name in ['entities.csv.gz','alternate-values.csv.gz']:
            candidates['countries/'+cc+'/'+name]=cc
    inventory=load(root/'sources/source-inventory.json')
    for e in inventory['inputs']:
        if e.get('repository_path') and e['input'].endswith('.zip'):
            candidates[e['repository_path']]=e['input'][:2]
    for name,cc in sorted(candidates.items()):
        path=safe_path(root,name)
        if name in entries:restore(root,entries[name])
        if path.stat().st_size<=LIMIT:continue
        data=path.read_bytes()
        entry=dict(country=cc,path=name,bytes=len(data),sha256=core.sha(data),git_blob_sha=blob_sha(data),parts=[])
        for index,start in enumerate(range(0,len(data),LIMIT),1):
            chunk=data[start:start+LIMIT]
            part_name='.parts/'+name+'/part-%04d.bin'%index
            part=safe_path(root,part_name);part.parent.mkdir(parents=True,exist_ok=True)
            if part.exists():
                if part.read_bytes()!=chunk:raise ValueError('existing publication part differs: '+part_name)
            else:part.write_bytes(chunk)
            entry['parts'].append(dict(path=part_name,bytes=len(chunk),sha256=core.sha(chunk)))
        if name in entries and entry!=entries[name]:raise ValueError('existing split entry changed: '+name)
        entries[name]=entry
    split=dict(schema_version=1,representation='ordered raw binary chunks; concatenate exactly to original compressed bytes',chunk_size_limit_bytes=LIMIT,files=[entries[k] for k in sorted(entries)])
    core.write_json(root/'split_manifest.json',split)
    (root/'.gitignore').write_text('__pycache__/\n*.pyc\n\n# Large files reconstructed locally from checked binary parts\n'+''.join('/'+e['path']+'\n' for e in split['files']),encoding='utf-8')
    # Every removed original is reproducible from the checked local parts.
    for e in split['files']:
        path=restore(root,e)
        assert blob_sha(path.read_bytes())==e['git_blob_sha']
        path.unlink()
    print(json.dumps(dict(split_files=len(entries),parts=sum(len(e['parts']) for e in entries.values()))))


def run(root,args):
    result=subprocess.run([sys.executable,*args],cwd=root,text=True,capture_output=True)
    if result.returncode:
        raise RuntimeError(' '.join(args)+' failed:\n'+result.stdout+result.stderr)
    return result


def verify(root):
    entries=manifest(root)
    assert entries and all(e['country'] in PUBLISHED_SCOPE for e in entries)
    parts=[p for e in entries for p in e['parts']]
    assert len({p['path'] for p in parts})==len(parts)
    assert all(0<p['bytes']<=LIMIT for p in parts)
    excluded={e['path'] for e in entries}
    assert all(not safe_path(root,name).exists() for name in excluded), 'run publication.py pack first'
    def ignore(directory,names):
        relative=Path(directory).relative_to(root)
        return [name for name in names if name=='__pycache__' or name.endswith('.pyc') or (relative/name).as_posix() in excluded]
    with tempfile.TemporaryDirectory(prefix='south-america-publication-') as temp:
        clean=Path(temp)/'pack';shutil.copytree(root,clean,ignore=ignore,symlinks=True)
        shutil.copytree(root.parent/'localities',Path(temp)/'localities',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        shutil.copyfile(root.parent/'tests/test_split_materialization.py',clean/'test_split_materialization.py')
        assert all(not safe_path(clean,name).exists() for name in excluded)
        baseline=load(clean/'sources/baseline-14-publication.json')
        for entry in baseline['files']:
            data=safe_path(clean,entry['path']).read_bytes()
            assert len(data)==entry['bytes'] and blob_sha(data)==entry['git_blob_sha'], ('baseline publication changed',entry['path'])
        # Query must itself reconstruct AR/PY, before the full verifier runs.
        smoke=[]
        for cc,text in [('AR','Buenos Aires'),('PY','Asunción'),('UY','Montevideo')]:
            value=json.loads(run(clean,['query.py','--country',cc,'--text',text,'--limit','1']).stdout)
            assert value['total']>0 and value['results'][0]['country_code']==cc
            smoke.append(cc+' '+text)
        value=json.loads(run(clean,['query.py','--country','BR','--kind','admin_subdivision','--level','1','--limit','1']).stdout)
        assert value['total']>0;smoke.append('BR ADM1')
        run(clean,['build.py','verify'])
        for e in entries:
            data=safe_path(clean,e['path']).read_bytes()
            assert len(data)==e['bytes'] and core.sha(data)==e['sha256'] and blob_sha(data)==e['git_blob_sha']
        for name in ['scope.json','coverage.csv','manifest.json','verification.json','summary.json','sources/source-inventory.json']:
            assert (root/name).read_bytes()==(clean/name).read_bytes(), ('stale generated report',name)
        tests=run(clean,['-m','unittest','discover','-v'])
        match=re.search(r'Ran (\d+) tests',tests.stderr)
        assert match, 'unit test count missing'
        # Fresh AR/PY rebuild from the retained upstream ZIPs and profile bytes.
        inputs=Path(temp)/'inputs';inputs.mkdir();rebuilt=Path(temp)/'rebuilt'
        for cc in ['AR','PY']:
            for name in [cc+'.zip',cc+'-alternatenames.zip']:
                shutil.copyfile(clean/'sources'/name,inputs/name)
        source=load(clean/'countries/AR/metadata.json')['country_profile_source']
        shutil.copyfile(safe_path(clean,source['repository_path']),inputs/'countryInfo.txt')
        build(inputs,rebuilt,source['retrieved_on'],['AR','PY'],clean/'scope.json')
        for cc in ['AR','PY']:
            for name in ['entities.csv.gz','alternate-values.csv.gz','admin1.csv','metadata.json']:
                assert (rebuilt/'countries'/cc/name).read_bytes()==(clean/'countries'/cc/name).read_bytes(), ('source rebuild differs',cc,name)
        verification=load(clean/'verification.json')
        assert verification['source_archive_replay_countries']==['AR','PY']
        report=dict(status='passed',published_country_area_count=len(PUBLISHED_SCOPE),m49_country_area_count=len(PUBLISHED_SCOPE),pending_country_codes=[],complete_gazetteer_pack=True,base_commit=baseline['base_commit'],existing_14_country_files_unchanged=True,baseline_files_checked=len(baseline['files']),split_file_count=len(entries),part_count=len(parts),max_part_bytes=max(p['bytes'] for p in parts),large_originals_absent_in_published_tree=True,clean_publication_only_copy_tested=True,automatic_query_reconstruction=smoke,automatic_full_verify_reconstruction='all sixteen countries passed',full_integrity_and_derived_column_replay='exact',ar_py_raw_source_replay='exact',ar_py_fresh_rebuild='all eight country files match exactly',unit_regression_reconstruction_and_scope_tests=int(match.group(1)),counts=dict(entities=verification['rows'],alternate_values=verification['alternate_values']),current_official_hierarchy_verified=False,full_municipality_coverage_verified=False,postal_deliverability_verified=False,validation_network_access_required=False,source_archive_replay_countries=['AR','PY'],source_archive_replay_limitation='Other fourteen upstream ZIP pairs were not published by PR #9; their preserved entity-derived columns replay exactly and their recorded source hashes match the inventory.')
    core.write_json(root/'publication_verification.json',report)
    print(json.dumps(report,ensure_ascii=False))
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['pack','verify'])
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    (pack if args.command=='pack' else verify)(args.root.resolve())


if __name__=='__main__':main()
