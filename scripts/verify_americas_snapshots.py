#!/usr/bin/env python3
"""Verify preserved US/CA/MX/BR snapshots without network or dependencies.

Adapted snapshot-integrity checks from Address Foundation's test_official.py,
plus exact Git blob provenance, coverage, and source-specific identity checks.
This does not rebuild upstream archives or validate current source freshness.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

COUNTRIES = ('US', 'CA', 'MX', 'BR')
EXPECTED_ROWS = {'US': 68744, 'CA': 5054, 'MX': 2478, 'BR': 5571}
EXPECTED_REGIONS = {'US': 52, 'CA': 13, 'MX': 32, 'BR': 27}
EXPECTED_ANCHORS = {'US': 3275, 'CA': 304, 'MX': 33, 'BR': 28}
SOURCE_COMMIT = '4efec82671b15a6bca4f0099acb6377c55af9aae'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_csv(path, columns):
    with path.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        require(reader.fieldnames == columns, f'{path}: unexpected CSV header')
        rows = list(reader)
    for row in rows:
        require(None not in row and all(value is not None for value in row.values()),
                f'{path}: invalid field count')
    return rows


def verify_source_map(root):
    mapping = read_json(root/'official-registry/americas-provenance/source-map.json')
    require(mapping['source_commit'] == SOURCE_COMMIT, 'source commit mismatch')
    require(set(mapping['countries']) == set(COUNTRIES), 'source-map country scope mismatch')
    seen = set()
    for entry in mapping['files']:
        rel = Path(entry['destination_path'])
        require(not rel.is_absolute() and '..' not in rel.parts, 'unsafe mapped path')
        require(str(rel) not in seen, f'duplicate mapped file: {rel}')
        seen.add(str(rel))
        require(entry['source_commit'] == SOURCE_COMMIT, f'{rel}: source commit mismatch')
        data = (root/rel).read_bytes()
        require(len(data) == entry['bytes'], f'{rel}: byte length mismatch')
        require(digest(data) == entry['sha256'], f'{rel}: SHA-256 mismatch')
        git_sha = hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        require(git_sha == entry['source_git_blob_sha1'], f'{rel}: Git blob SHA-1 mismatch')
    for cc in COUNTRIES:
        actual = {str(p.relative_to(root)) for p in (root/'official-registry'/cc).iterdir() if p.is_file()}
        expected = {p for p in seen if p.startswith(f'official-registry/{cc}/')}
        require(actual == expected, f'{cc}: missing or unexpected country files')
    require(len(mapping['files']) == 151, 'expected 140 country and 11 provenance files')
    return {'files': len(seen), 'bytes': sum(x['bytes'] for x in mapping['files']),
            'git_blob_sha1_and_sha256': 'passed'}


def verify_country(registry, cc, schema):
    path = registry/cc
    index, manifest = read_json(path/'index.json'), read_json(path/'manifest.json')
    require(index['country'] == manifest['country'] == cc, f'{cc}: country mismatch')
    require(index['columns'] == schema['country_files'][cc]['columns'], f'{cc}: schema mismatch')
    require(index['counts']['source_localities'] == EXPECTED_ROWS[cc], f'{cc}: index count mismatch')
    require(len(index['regions']) == EXPECTED_REGIONS[cc], f'{cc}: region count mismatch')
    require(all(not value for value in manifest['claims'].values()), f'{cc}: unexpected completeness claim')
    for filename, expected in manifest['sha256'].items():
        rel = Path(filename)
        require(not rel.is_absolute() and len(rel.parts) == 1, f'{cc}: unsafe manifest path')
        require(digest((path/filename).read_bytes()) == expected, f'{cc}/{filename}: original manifest hash mismatch')
    declared = set(manifest['sha256']) | {'manifest.json'}
    require(declared == {p.name for p in path.iterdir() if p.is_file()}, f'{cc}: original manifest coverage mismatch')
    anchors_list = read_csv(path/'anchors.csv', index['columns'])
    anchors = {r['id']: r for r in anchors_list}
    require(len(anchors) == len(anchors_list) == EXPECTED_ANCHORS[cc], f'{cc}: duplicate or unexpected anchors')
    require(f'country:{cc}' in anchors, f'{cc}: absent root')
    require(anchors[f'country:{cc}']['parent_id'] == '', f'{cc}: country root has parent')
    localities = {}
    total_candidates = 0
    region_ids, region_codes, region_files = set(), set(), set()
    for region in index['regions']:
        require(region['id'] not in region_ids and region['code'] not in region_codes and region['file'] not in region_files,
                f'{cc}: duplicate region identity or file')
        region_ids.add(region['id']); region_codes.add(region['code']); region_files.add(region['file'])
        require(region['id'] in anchors, f'{cc}: unresolved region anchor')
        require(anchors[region['id']]['code'] == region['code'], f'{cc}: region code mismatch')
        rows = read_csv(path/region['file'], index['columns'])
        require(len(rows) == region['localities'], f'{cc}/{region["file"]}: row count mismatch')
        candidates = sum(row['address_candidate'] == '1' for row in rows)
        require(candidates == region['address_candidates'], f'{cc}: region address-candidate count mismatch')
        total_candidates += candidates
        for row in rows:
            require(row['id'] not in anchors and row['id'] not in localities, f'{cc}: duplicate entity {row["id"]}')
            require(row['name'] and row['code'], f'{cc}: empty locality name or code')
            require(row['state_id'] == region['id'] and row['state_code'] == region['code'], f'{cc}: wrong region assignment')
            require(row['address_candidate'] in ('0', '1'), f'{cc}: invalid address flag')
            require(row['postcodes'] == row['postcode_relations'] == '', f'{cc}: unexpected loaded postal association')
            require(row['department_code'] == row['collectivity_code'] == '', f'{cc}: unexpected shared field')
            require(row['id'].endswith(':'+row['code']), f'{cc}: code/id mismatch')
            if cc == 'US':
                require(row['source_type'] in ('place', 'cousub'), 'US: invalid source type')
                require(row['code'].isdigit() and len(row['code']) == (7 if row['source_type'] == 'place' else 10), 'US: invalid string code')
                parent = row['state_id'] if row['source_type'] == 'place' else 'admin:us:census:county:'+row['code'][:5]
                require(row['parent_id'] == parent, 'US: fabricated or incorrect parent')
                require(row['address_country'] == ('PR' if row['state_code'] == 'US-PR' else 'US'), 'US: lost address-country distinction')
                if row['category'] == 'fictitious_census_entity':
                    require(row['address_candidate'] == '0', 'US: fictitious entity became address candidate')
            elif cc == 'CA':
                require(row['code'].isdigit() and len(row['code']) == 7, 'CA: invalid CSDUID')
                require(row['code'][:4] == row['census_division_code'] and row['code'][:2] == row['source_state_code'], 'CA: code ancestry mismatch')
                require(row['parent_id'] == 'admin:ca:statcan:cd:'+row['census_division_code'], 'CA: incorrect census division parent')
                require(row['csd_type_code'] and row['lang'] == 'und', 'CA: missing type or inferred language')
                if row['category'] == 'unorganized_or_statistical_census_subdivision':
                    require(row['address_candidate'] == '0', 'CA: unorganized/statistical address candidate')
            elif cc == 'MX':
                require(row['code'].isdigit() and len(row['code']) == 5 and row['code'] == row['source_state_code']+row['municipality_component'], 'MX: invalid AGEM identity')
                require(row['parent_id'] == row['state_id'] and row['lang'] == 'es', 'MX: wrong parent or language')
            else:
                require(row['code'].isdigit() and len(row['code']) == 7, 'BR: invalid IBGE code')
                require(row['parent_id'] == row['state_id'] and row['lang'] == 'pt', 'BR: wrong parent or language')
            if cc != 'US':
                require(row['address_country'] == cc, f'{cc}: wrong address country')
            localities[row['id']] = row
    require(len(localities) == EXPECTED_ROWS[cc], f'{cc}: total count mismatch')
    if 'address_candidates' in index['counts']:
        require(total_candidates == index['counts']['address_candidates'], f'{cc}: address-candidate total mismatch')
    merged = anchors | localities
    for row in merged.values():
        seen = set()
        current = row
        while current['parent_id']:
            require(current['id'] not in seen, f'{cc}: parent cycle at {current["id"]}')
            seen.add(current['id'])
            require(current['parent_id'] in merged, f'{cc}: unresolved parent {current["parent_id"]}')
            current = merged[current['parent_id']]
        require(current['id'] == f'country:{cc}', f'{cc}: wrong hierarchy root')
        if row['id'] in localities:
            require(row['state_id'] in seen, f'{cc}: state is not an ancestor')
    categories = dict(Counter(r['category'] for r in localities.values()))
    if 'categories' in index['counts']:
        require(categories == index['counts']['categories'], f'{cc}: category count mismatch')
    if cc == 'CA':
        require(dict(Counter(r['csd_type_code'] for r in localities.values())) == index['counts']['type_counts'], 'CA: CSDTYPE distribution mismatch')
    if cc == 'US':
        require(Counter(r['source_type'] for r in localities.values()) == {'place': 32363, 'cousub': 36381}, 'US: source-role count mismatch')
        require(categories['fictitious_census_entity'] == 4830, 'US: fictitious role count mismatch')
    require(read_json(path/'unmatched-source-rows.json') == [], f'{cc}: unexpected unmatched rows')
    world = registry/'americas-provenance/registry/countries'/f'{cc}.json'
    require(digest(world.read_bytes()) == manifest['source_manifest']['world_registry_sha256'], f'{cc}: original world-anchor hash mismatch')
    return {'regions':len(region_ids), 'anchors':len(anchors), 'localities':len(localities),
            'address_candidates':total_candidates, 'categories':categories, 'vintage':index['vintage'],
            'observed_at':manifest['observed_at'], 'original_manifest_hashes':'passed',
            'unique_ids_and_closed_acyclic_hierarchy':'passed', 'source_specific_contracts':'passed'}


def verify(root):
    registry = root/'official-registry'
    schema = read_json(registry/'americas-snapshot-schema.json')
    require(all(not value for value in schema['snapshot_claims'].values()), 'schema completeness claims changed')
    source = verify_source_map(root)
    countries = {cc:verify_country(registry, cc, schema) for cc in COUNTRIES}
    return {'status':'passed','source_repository':'rei-k/world-address','source_commit':SOURCE_COMMIT,
            'verification_scope':'Offline preserved-byte and snapshot-integrity checks only; no upstream refresh or raw-source rebuild',
            'source_files':source,'countries':countries,
            'total_locality_rows':sum(x['localities'] for x in countries.values()),
            'total_anchor_rows':sum(x['anchors'] for x in countries.values()),
            'no_address1':True,'current_source_freshness_verified':False,'full_continent_coverage':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--write-report', type=Path)
    args = parser.parse_args()
    report = verify(args.root.resolve())
    rendered = json.dumps(report, ensure_ascii=False, indent=2)+'\n'
    if args.write_report:
        args.write_report.write_text(rendered, encoding='utf-8')
    print(rendered, end='')


if __name__ == '__main__':
    main()
