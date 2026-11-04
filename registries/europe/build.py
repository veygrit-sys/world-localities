#!/usr/bin/env python3
"""Build a source-preserving European gazetteer. Python 3.11+, standard library only."""
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
import time
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
PART_ROWS = 20000


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
    groups = {'entities-%04d.csv.gz' % (i // PART_ROWS + 1): rows[i:i + PART_ROWS]
              for i in range(0, len(rows), PART_ROWS)}
    if not groups:
        groups['entities-0001.csv.gz'] = []
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


def download(inputs, filename, url=None):
    """Cache verified source bytes; removing a cache entry explicitly refreshes it."""
    inputs.mkdir(parents=True, exist_ok=True)
    path = inputs / filename
    metapath = inputs / (filename + '.meta.json')
    url = url or SOURCE_URL + filename
    if path.exists() and metapath.exists():
        meta = json.loads(metapath.read_text(encoding='utf-8'))
        if meta['url'] != url or sha(path.read_bytes()) != meta['sha256']:
            raise ValueError('cached source URL/hash mismatch: ' + filename)
        return meta
    last_error = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'world-address-europe/1.0'})
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = response.read(200_000_001)
                if len(payload) > 200_000_000:
                    raise ValueError('source exceeds size limit')
                meta = dict(url=url, sha256=sha(payload), bytes=len(payload),
                            retrieved_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                            last_modified=response.headers.get('Last-Modified'))
            path.write_bytes(payload)
            write_json(metapath, meta)
            return meta
        except (OSError, TimeoutError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(attempt + 1)
    raise RuntimeError('source download failed: ' + filename) from last_error


def country_rows(output, country):
    folder = output / 'countries' / country
    meta = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
    for filename in sorted(meta['files']):
        if not re.fullmatch(r'entities-[0-9]{4}\.csv\.gz', filename):
            raise ValueError('unexpected part filename')
        yield from read_csv(folder / filename)


def run(inputs, output, countries=None):
    scope = json.loads((output / 'scope.json').read_text(encoding='utf-8'))
    selected = [c for c in scope['countries'] if not countries or c['country'] in countries]
    if countries and set(countries) != {c['country'] for c in selected}:
        raise ValueError('country outside documented scope')
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(download, inputs, c['country'] + '.zip'): c for c in selected}
        for future in as_completed(jobs):
            spec = jobs[future]
            cc = spec['country']
            source = dict(future.result())
            retained = []
            all_count = 0
            excluded = Counter()
            for row in source_rows(inputs / (cc + '.zip'), cc):
                all_count += 1
                if row['feature_class'] == 'P' or (row['feature_class'] == 'A' and (
                        re.fullmatch(r'ADM[1-5]H?', row['feature_code']) or row['feature_code'] == 'ADMD')):
                    retained.append(row)
                else:
                    excluded[row['feature_class']] += 1
            source.update(all_source_rows=all_count, retained_rows=len(retained),
                          excluded_feature_class_counts=dict(sorted(excluded.items())))
            rows = build_rows(retained, cc)
            counts = write_country(rows, cc, output, source, spec)
            metapath = output / 'countries' / cc / 'metadata.json'
            meta = json.loads(metapath.read_text(encoding='utf-8'))
            meta.update(completeness='All P, ADM1-5, ADMD and historical ADM rows in this source extract; not a complete official municipality register.',
                        names_language_status='und: source labels and untagged aliases; ASCII is not English',
                        postal_relation_status='not_loaded', address1_status='not_loaded',
                        identity_policy='GeoNames ID preserved; no name-based merging with official LAU or existing registries')
            write_json(metapath, meta)
            report = verify_country(output, cc)
            print(jdump(dict(counts, verification=report['status'])), flush=True)
    summarize(output)


def check(condition, message):
    if not condition:
        raise ValueError(message)


def verify_country(output, cc):
    folder = output / 'countries' / cc
    meta = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
    rows = []
    for name, part in sorted(meta['files'].items()):
        check(re.fullmatch(r'entities-[0-9]{4}\.csv\.gz', name), 'unsafe part name')
        payload = (folder / name).read_bytes()
        check(sha(payload) == part['sha256'], cc + ' compressed checksum mismatch')
        check(len(payload) == part['bytes'], cc + ' part bytes mismatch')
        data = gzip.decompress(payload)
        check(sha(data) == part['uncompressed_sha256'], cc + ' CSV checksum mismatch')
        reader = csv.DictReader(io.StringIO(data.decode('utf-8')))
        check(reader.fieldnames == FIELDS, cc + ' CSV columns mismatch')
        partrows = list(reader)
        check(len(partrows) == part['rows'] <= PART_ROWS, cc + ' part row count mismatch')
        rows.extend(partrows)
    ids = {r['id']: r for r in rows}
    check(len(ids) == len(rows), cc + ' duplicate identity')
    check(len(rows) == meta['source_file']['retained_rows'], cc + ' retained row count mismatch')
    for row in rows:
        check(row['country_code'] == cc, cc + ' cross-country row')
        pid = row['parent_id']
        if pid and not pid.startswith('country:'):
            check(pid in ids and pid != row['id'], cc + ' missing/self parent')
            parent = ids[pid]
            check(parent['kind'] == 'admin_subdivision', cc + ' parent is not administrative')
            depth = int(parent['admin_level'])
            check(depth <= 4 and code_key(row, depth) == code_key(parent, depth), cc + ' parent codes differ')
            if row['admin_level']:
                check(depth == int(row['admin_level']) - 1, cc + ' skipped administrative parent')
        elif pid:
            check(pid == 'country:' + cc, cc + ' incorrect country scope')
        sid = row['state_id']
        if sid:
            check(sid in ids and ids[sid]['admin_level'] == '1', cc + ' invalid ADM1')
            check(code_key(row, 1) == code_key(ids[sid], 1) or row['id'] == sid, cc + ' ADM1 code mismatch')
    rebuilt = build_rows([{k: r[k] for k in RAW} for r in rows], cc)
    check(rebuilt == rows, cc + ' deterministic replay differs')
    preview = (folder / 'admin1.csv').read_bytes()
    check(preview == csv_bytes([r for r in rows if r['admin_level'] == '1']), cc + ' ADM1 projection differs')
    check(sha(preview) == meta['preview_files']['admin1.csv']['sha256'], cc + ' ADM1 checksum mismatch')
    for key, expected in {
        'admin_rows': sum(r['kind'] == 'admin_subdivision' for r in rows),
        'locality_rows': sum(r['kind'] == 'locality' for r in rows),
        'other_admin_rows': sum(r['kind'] == 'other_admin_feature' for r in rows),
        'unresolved_parents': sum(r['parent_relation'] in ('missing_code','missing_reference','ambiguous_code') for r in rows),
    }.items():
        check(meta['counts'][key] == expected, cc + ' metadata count differs: ' + key)
    return dict(country=cc, rows=len(rows), parts=len(meta['files']), replay='exact', status='pass')


def summarize(output):
    scope = json.loads((output / 'scope.json').read_text(encoding='utf-8'))
    entries = []
    missing = []
    for spec in scope['countries']:
        cc = spec['country']
        path = output / 'countries' / cc / 'metadata.json'
        if not path.is_file():
            missing.append(cc)
            continue
        meta = json.loads(path.read_text(encoding='utf-8'))
        entries.append(dict(country=cc, counts=meta['counts'],
                            metadata_sha256=sha(path.read_bytes()),
                            rows=meta['source_file']['retained_rows'], parts=len(meta['files'])))
    result = dict(schema_version=1, source='GeoNames', scope_count=len(scope['countries']),
                  built_count=len(entries), missing_countries=missing,
                  total_rows=sum(e['rows'] for e in entries),
                  countries=entries, license='CC-BY-4.0',
                  official_completeness_verified=False)
    for key in ('admin_rows','locality_rows','other_admin_rows','address_candidates',
                'unresolved_parents','ambiguous_parents','country_scope_only','localities_without_adm1'):
        result[key] = sum(e['counts'][key] for e in entries)
    write_json(output / 'manifest.json', result)
    if entries:
        (output / 'coverage.csv').write_bytes(csv_bytes([e['counts'] for e in entries], list(entries[0]['counts'])))
    return result


def verify(output, countries=None):
    scope = json.loads((output / 'scope.json').read_text(encoding='utf-8'))
    selected = [c['country'] for c in scope['countries'] if not countries or c['country'] in countries]
    check(not countries or set(selected) == set(countries), 'country outside documented scope')
    reports, seen = [], set()
    for cc in selected:
        reports.append(verify_country(output, cc))
        ids = {r['id'] for r in country_rows(output, cc)}
        check(not seen.intersection(ids), 'cross-country duplicate GeoNames IDs')
        seen.update(ids)
    if not countries:
        manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
        check(manifest['scope_count'] == manifest['built_count'] == len(reports), 'manifest scope incomplete')
        check(manifest['total_rows'] == len(seen), 'manifest total mismatch')
        for e in manifest['countries']:
            p = output / 'countries' / e['country'] / 'metadata.json'
            check(e['metadata_sha256'] == sha(p.read_bytes()), 'manifest metadata hash differs')
    report = dict(status='pass', errors=0, countries=len(reports), rows=len(seen), reports=reports,
                  source_accuracy_and_legal_status_independently_verified=False,
                  note='Structural validation; unresolved source relationships remain recorded.')
    if not countries:
        write_json(output / 'verification.json', report)
    print(jdump({k:v for k,v in report.items() if k != 'reports'}), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['build', 'verify', 'summarize'])
    p.add_argument('--inputs', type=Path, default=ROOT / 'source-cache')
    p.add_argument('--countries', nargs='+')
    args = p.parse_args()
    if args.command == 'build':
        run(args.inputs, ROOT, args.countries)
    elif args.command == 'verify':
        verify(ROOT, args.countries)
    else:
        print(jdump(summarize(ROOT)))


