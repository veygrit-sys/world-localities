#!/usr/bin/env python3
"""Build a source-preserving Asia gazetteer. Python 3.11+, standard library only."""
import argparse
import datetime as dt
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import gzip
import hashlib
import io
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ('geonameid name asciiname alternatenames latitude longitude feature_class '
       'feature_code country_code cc2 admin1_code admin2_code admin3_code admin4_code '
       'population elevation dem timezone modification_date').split()
DERIVED = ('id kind admin_level parent_id parent_relation parent_candidates_json '
           'state_id state_relation state_candidates_json address_candidate '
           'quality_flags_json').split()
FIELDS = DERIVED + RAW
CURRENT_PLACES = {'PPL', 'PPLA', 'PPLA2', 'PPLA3', 'PPLA4', 'PPLA5', 'PPLC',
                  'PPLL', 'PPLX', 'PPLG'}
SOURCE_URL = 'https://download.geonames.org/export/dump/'
M49_URL = 'https://unstats.un.org/unsd/methodology/m49/'


def jdump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def csv_bytes(rows, fields=FIELDS):
    f = io.StringIO(newline='')
    writer = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return f.getvalue().encode('utf-8')


def compressed(data):
    f = io.BytesIO()
    with gzip.GzipFile(fileobj=f, mode='wb', filename='', mtime=0, compresslevel=9) as z:
        z.write(data)
    return f.getvalue()


def read_csv(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8', newline='') as f:
        yield from csv.DictReader(f)


def freshness_issues(country, adm1_count):
    path = ROOT / 'source_freshness.json'
    if not path.is_file():
        return []
    issue = json.loads(path.read_text(encoding='utf-8'))['countries'].get(country)
    if not issue:
        return []
    issue = dict(issue, geonames_adm1_count_in_this_snapshot=adm1_count)
    if adm1_count == issue['official_reference_adm1_count']:
        issue['status'] = 'count_matches_reference_hierarchy_not_verified'
    return [issue]


def source_rows(path, country):
    """Read a named ZIP member without extracting archive paths."""
    with zipfile.ZipFile(path) as z:
        info = z.getinfo(country + '.txt')
        if info.file_size > 2_000_000_000:
            raise ValueError('unexpected country file size')
        with z.open(info) as f:
            for line in io.TextIOWrapper(f, encoding='utf-8'):
                values = line.rstrip('\r\n').split('\t')
                if len(values) != 19:
                    raise ValueError('GeoNames schema changed')
                yield dict(zip(RAW, values))


def level(row):
    match = re.fullmatch(r'ADM([1-5])', row['feature_code'])
    return int(match[1]) if row['feature_class'] == 'A' and match else None


def code_key(row, n):
    codes = tuple(row['admin%d_code' % i] for i in range(1, n + 1))
    if any(not c for c in codes) or (codes and codes[0] == '00'):
        return None
    return (row['country_code'],) + codes


def build_rows(raw_rows, country):
    rows = sorted(raw_rows, key=lambda r: int(r['geonameid']))
    indexes = {n: defaultdict(list) for n in range(1, 5)}
    seen = set()
    for r in rows:
        if r['country_code'] != country or r['feature_class'] not in ('A', 'P'):
            raise ValueError('unexpected row scope')
        if not re.fullmatch(r'[1-9][0-9]*', r['geonameid']) or not r['name']:
            raise ValueError('missing source identity or name')
        if r['geonameid'] in seen:
            raise ValueError('duplicate GeoNames identity')
        seen.add(r['geonameid'])
        if not (-90 <= float(r['latitude']) <= 90 and -180 <= float(r['longitude']) <= 180):
            raise ValueError('invalid source coordinate')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', r['modification_date']):
            raise ValueError('invalid source modification date')
        dt.date.fromisoformat(r['modification_date'])
        n = level(r)
        if n and n <= 4 and code_key(r, n):
            indexes[n][code_key(r, n)].append('gn:' + r['geonameid'])

    def resolve(r, n):
        key = code_key(r, n)
        if key is None:
            return '', 'missing_code', []
        candidates = sorted(indexes[n].get(key, []))
        if len(candidates) == 1:
            return candidates[0], 'source_admin_code', candidates
        return '', 'ambiguous_code' if candidates else 'missing_reference', candidates

    result = []
    for r in rows:
        n = level(r)
        eid = 'gn:' + r['geonameid']
        flags = ['names_and_legal_status_not_independently_verified']
        if r['cc2']:
            flags.append('alternate_country_codes_retained')
        if n == 1:
            pid, relation, candidates = 'country:' + country, 'source_country', []
        elif n:
            pid, relation, candidates = resolve(r, n - 1)
        elif r['feature_class'] == 'P':
            populated = [i for i in range(1, 5) if r['admin%d_code' % i] and not
                         (i == 1 and r['admin1_code'] == '00')]
            if populated:
                pid, relation, candidates = resolve(r, max(populated))
            else:
                pid, relation, candidates = 'country:' + country, 'country_scope_only', []
                flags.append('administrative_assignment_missing')
        else:
            pid, relation, candidates = '', 'not_assigned_for_other_feature', []
        if relation in ('missing_code', 'missing_reference', 'ambiguous_code'):
            flags.append('parent_' + relation)
        if n == 1:
            state, state_relation, state_candidates = eid, 'self_is_adm1', [eid]
        elif n or r['feature_class'] == 'P':
            state, state_relation, state_candidates = resolve(r, 1)
        else:
            state, state_relation, state_candidates = '', 'not_applicable', []
        if n == 5:
            flags.append('admin5_code_not_in_standard_dump')
        if r['feature_code'] in {'PPLH', 'PPLCH', 'PPLQ', 'PPLW'} or re.fullmatch(r'ADM[1-5]H', r['feature_code']):
            pid, relation, candidates = '', 'historical_parent_not_asserted', []
            state, state_relation, state_candidates = '', 'historical_parent_not_asserted', []
        kind = 'admin_subdivision' if n else ('locality' if r['feature_class'] == 'P' else 'other_admin_feature')
        candidate = r['feature_class'] == 'P' and r['feature_code'] in CURRENT_PLACES
        if r['feature_class'] == 'P' and not candidate:
            flags.append('excluded_from_default_address_candidates')
        result.append(dict(id=eid, kind=kind, admin_level=str(n or ''), parent_id=pid,
                           parent_relation=relation, parent_candidates_json=jdump(candidates),
                           state_id=state, state_relation=state_relation,
                           state_candidates_json=jdump(state_candidates),
                           address_candidate='1' if candidate else '0',
                           quality_flags_json=jdump(sorted(flags)), **r))

    by_id = {r['id']: r for r in result}
    for r in result:
        if not r['parent_id'] or r['parent_id'].startswith('country:'):
            continue
        p = by_id[r['parent_id']]
        # A separately resolved ADM1 must agree with the parent's source ADM1 code.
        if r['admin1_code'] != p['admin1_code']:
            raise ValueError('cross-state parent')
    return result


def write_country(rows, country, output, source_meta, country_meta):
    directory = output / 'countries' / country
    directory.mkdir(parents=True, exist_ok=True)
    groups = {'entities.csv.gz': rows}
    files = {}
    for filename, data_rows in groups.items():
        data = csv_bytes(data_rows)
        payload = compressed(data) if filename.endswith('.gz') else data
        (directory / filename).write_bytes(payload)
        files[filename] = {'rows': len(data_rows), 'bytes': len(payload), 'sha256': sha(payload),
                           'uncompressed_sha256': sha(data)}
    preview = csv_bytes([r for r in rows if r['admin_level'] == '1'])
    (directory / 'admin1.csv').write_bytes(preview)
    stats = dict(country=country, name_en=country_meta['name_en'],
                 region=country_meta['region'], admin_rows=sum(r['kind'] == 'admin_subdivision' for r in rows),
                 locality_rows=sum(r['kind'] == 'locality' for r in rows),
                 other_admin_rows=sum(r['kind'] == 'other_admin_feature' for r in rows),
                 address_candidates=sum(r['address_candidate'] == '1' for r in rows),
                 unresolved_parents=sum(r['parent_relation'] in ('missing_code', 'missing_reference', 'ambiguous_code') for r in rows),
                 ambiguous_parents=sum(r['parent_relation'] == 'ambiguous_code' for r in rows),
                 country_scope_only=sum(r['parent_relation'] == 'country_scope_only' for r in rows),
                 localities_without_adm1=sum(r['kind'] == 'locality' and not r['state_id'] for r in rows))
    meta = dict(schema_version=1, source='GeoNames', license='CC-BY-4.0',
                country=country_meta, source_file=source_meta, files=files, counts=stats,
                current_official_hierarchy_verified=False,
                known_issues=freshness_issues(country, sum(r['admin_level'] == '1' for r in rows)),
                preview_files={'admin1.csv': {'sha256': sha(preview), 'rows': sum(r['admin_level'] == '1' for r in rows),
                                             'note': 'Duplicate display projection; do not add to entity counts.'}},
                feature_counts=dict(sorted(Counter(r['feature_code'] for r in rows).items())),
                parent_relation_counts=dict(sorted(Counter(r['parent_relation'] for r in rows).items())),
                completeness='all A/P records in this source country extract; official municipality completeness unverified',
                source_modified_min=min((r['modification_date'] for r in rows), default=None),
                source_modified_max=max((r['modification_date'] for r in rows), default=None))
    write_json(directory / 'metadata.json', meta)
    return stats



def fetch(inputs, filename, group='dump'):
    path = inputs / filename
    metadata = path.with_suffix(path.suffix + '.meta.json')
    url = 'https://download.geonames.org/export/' + group + '/' + filename
    if path.exists() and metadata.exists():
        meta = json.loads(metadata.read_text())
        if sha(path.read_bytes()) != meta['sha256']:
            raise ValueError('Source checksum mismatch')
        return meta
    with urllib.request.urlopen(url, timeout=60) as response:
        payload = response.read()
        meta = dict(url=url, sha256=sha(payload), bytes=len(payload),
                    retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                    last_modified=response.headers.get('Last-Modified'))
    path.write_bytes(payload)
    write_json(metadata, meta)
    return meta


def run(inputs, output):
    inputs.mkdir(parents=True, exist_ok=True)
    sc = json.loads((output / 'scope.json').read_text())
    country_source = fetch(inputs, 'countryInfo.txt')
    info = {}
    for line in (inputs / 'countryInfo.txt').read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#'):
            columns = line.split('\t')
            info[columns[0]] = columns
    for spec in sc['countries']:
        spec.update(name_en=info[spec['country']][4], alpha3=info[spec['country']][1])
    sc['country_name_source'] = country_source
    write_json(output / 'scope.json', sc)
    metas = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch, inputs, c['country'] + '.zip'): c for c in sc['countries']}
        for future in as_completed(jobs):
            c = jobs[future]
            source = future.result()
            cc = c['country']
            selected = []
            source_count = 0
            for r in source_rows(inputs / (cc + '.zip'), cc):
                source_count += 1
                if r['feature_class'] == 'P' or (r['feature_class'] == 'A' and (
                        re.fullmatch(r'ADM[1-5]H?', r['feature_code']) or r['feature_code'] == 'ADMD')):
                    selected.append(r)
            source['retained_rows'] = len(selected)
            source['all_source_rows'] = source_count
            rows = build_rows(selected, cc)
            counts = write_country(rows, cc, output, source, c)
            metadata_path = output / 'countries' / cc / 'metadata.json'
            meta = json.loads(metadata_path.read_text())
            meta['completeness'] = 'All P, ADM1-5, ADMD and historical ADM rows in this source; not a complete official municipality register.'
            meta['names_language_status'] = 'und; additional tagged names are separate source claims'
            meta['postal_relation_status'] = 'not_joined_in_gazetteer'
            write_json(metadata_path, meta)
            metas.append(meta)
            print(jdump(counts), flush=True)
    metas.sort(key=lambda m: m['country']['country'])
    write_json(output / 'manifest.json', dict(schema_version=1, scope_count=len(metas),
        total_rows=sum(m['source_file']['retained_rows'] for m in metas),
        admin_rows=sum(m['counts']['admin_rows'] for m in metas),
        countries=[dict(country=m['country']['country'], counts=m['counts'], source=m['source_file']) for m in metas],
        license='CC-BY-4.0'))
    print('BUILD COMPLETE', flush=True)


def verify(output, country=None):
    scope = json.loads((output / 'scope.json').read_text())
    reports, seen = [], set()
    for spec in scope['countries']:
        cc = spec['country']
        if country is not None and cc != country:
            continue
        folder = output / 'countries' / cc
        metadata = json.loads((folder / 'metadata.json').read_text())
        payload = (folder / 'entities.csv.gz').read_bytes()
        part = metadata['files']['entities.csv.gz']
        assert sha(payload) == part['sha256']
        raw = gzip.decompress(payload)
        assert sha(raw) == part['uncompressed_sha256']
        rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8'))))
        del raw, payload
        assert len(rows) == part['rows']
        ids = {r['id']: r for r in rows}
        assert len(ids) == len(rows) and not seen.intersection(ids)
        seen.update(ids)
        for row in rows:
            assert row['country_code'] == cc
            pid = row['parent_id']
            if pid and not pid.startswith('country:'):
                parent = ids[pid]
                assert parent['kind'] == 'admin_subdivision' and pid != row['id']
                depth = int(parent['admin_level'])
                assert depth <= 4 and code_key(row, depth) == code_key(parent, depth)
                if row['admin_level']:
                    assert depth < int(row['admin_level'])
            sid = row['state_id']
            assert not sid or ids[sid]['admin_level'] == '1'
        rebuilt = build_rows(({k: r[k] for k in RAW} for r in rows), cc)
        assert rebuilt == rows
        assert (folder / 'admin1.csv').read_bytes() == csv_bytes([r for r in rows if r['admin_level'] == '1'])
        reports.append(dict(country=cc, rows=len(rows), replay='exact', status='pass'))
        del rows, ids, rebuilt
    if not reports:
        raise ValueError('Country outside configured scope')
    if country is None:
        manifest = json.loads((output / 'manifest.json').read_text())
        assert len(seen) == manifest['total_rows']
    report = dict(status='pass', errors=0, countries=len(reports), rows=len(seen), reports=reports,
                  source_accuracy_and_legal_status_independently_verified=False)
    destination = output / 'verification.json' if country is None else output / 'countries' / country / 'verification.json'
    write_json(destination, report)
    print(jdump({k:v for k,v in report.items() if k != 'reports'}), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['build','verify'])
    parser.add_argument('--inputs', type=Path, default=ROOT.parent.parent / 'source-cache-asia')
    parser.add_argument('--country', help='Verify a single alpha-2 country/area profile')
    args = parser.parse_args()
    if args.command == 'build':
        if args.country:
            parser.error('--country applies to verify only')
        run(args.inputs, ROOT)
    else:
        verify(ROOT, args.country)
