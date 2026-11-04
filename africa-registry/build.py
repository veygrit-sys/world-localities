#!/usr/bin/env python3
"""Build a source-preserving Africa gazetteer. Python 3.11+, standard library only."""
import argparse
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
        if info.file_size > 250_000_000:
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


def scope(inputs):
    countries = {}
    for line in (inputs / 'countryInfo.txt').read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        r = line.split('\t')
        countries[r[1]] = dict(country=r[0], alpha3=r[1], numeric=r[2],
                               geonames_country_name=r[4], geonames_continent=r[8],
                               geonames_id=r[16])
    if (inputs / 'm49-rows.json').is_file():
        rows = json.loads((inputs / 'm49-rows.json').read_text(encoding='utf-8'))
    else:
        frozen_scope = json.loads((ROOT / 'scope.json').read_text(encoding='utf-8'))
        rows = [['Country or Area', 'M49', 'alpha3']] + frozen_scope['source_rows']
    active, region, selected, source = False, None, [], []
    for r in rows[1:]:
        if r[1] == '002' and not r[2]:
            active = True
        elif r[1] == '019' and not r[2]:
            break
        if not active:
            continue
        source.append(r[:3])
        if not r[2]:
            if r[1] in ('015', '014', '017', '018', '011'):
                region = r[0].replace('+', '').strip()
            continue
        c = dict(countries[r[2]], name_en=r[0], m49=r[1], region=region)
        c['id'] = 'country:' + c['country']
        c['status'] = 'disputed' if c['country'] == 'EH' else 'source_country_or_area'
        selected.append(c)
    if len(selected) != 60 or len({c['country'] for c in selected}) != 60:
        raise ValueError('UN M49 Africa scope changed; review required')
    return sorted(selected, key=lambda c: c['country']), source


def build(inputs, output, retrieved_on, only=None):
    selected, source = scope(inputs)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / 'scope.json', dict(schema_version=1, source_url=M49_URL,
               retrieved_on=retrieved_on, source_rows=source, countries=selected))
    selected = [c for c in selected if not only or c['country'] in only]
    result = []
    for c in selected:
        cc = c['country']
        path = inputs / (cc + '.zip')
        raw = list(source_rows(path, cc))
        rows = build_rows([r for r in raw if r['feature_class'] in ('A', 'P')], cc)
        source_meta = dict(url=SOURCE_URL + cc + '.zip', retrieved_on=retrieved_on,
                           sha256=sha(path.read_bytes()), bytes=path.stat().st_size,
                           source_rows=len(raw), retained_rows=len(rows),
                           discarded_feature_classes=dict(Counter(r['feature_class'] for r in raw if r['feature_class'] not in ('A', 'P'))))
        s = write_country(rows, cc, output, source_meta, c)
        result.append(s)
        print(cc, s['admin_rows'], s['locality_rows'], s['unresolved_parents'], flush=True)
    return result


def summarize(output):
    sc = json.loads((output / 'scope.json').read_text(encoding='utf-8'))
    metas = [json.loads((output / 'countries' / c['country'] / 'metadata.json').read_text(encoding='utf-8')) for c in sc['countries']]
    counts = [m['counts'] for m in metas]
    (output / 'coverage.csv').write_bytes(csv_bytes(counts, list(counts[0])))
    totals = {k: sum(c[k] for c in counts) for k in counts[0] if isinstance(counts[0][k], int)}
    write_json(output / 'manifest.json', dict(schema_version=1, scope_count=len(counts),
               totals=totals, countries=[dict(country=m['country']['country'], metadata_sha256=sha((output / 'countries' / m['country']['country'] / 'metadata.json').read_bytes())) for m in metas],
               license='CC-BY-4.0', source=SOURCE_URL, scope_source=M49_URL,
               scope_sha256=sha((output / 'scope.json').read_bytes()),
               coverage_sha256=sha((output / 'coverage.csv').read_bytes())))
    return totals


def verify(output):
    sc = json.loads((output / 'scope.json').read_text(encoding='utf-8'))
    seen, checks, reports = set(), 0, []
    for c in sc['countries']:
        cc = c['country']
        d = output / 'countries' / cc
        meta = json.loads((d / 'metadata.json').read_text(encoding='utf-8'))
        rows = []
        for filename, info in meta['files'].items():
            payload = (d / filename).read_bytes()
            assert sha(payload) == info['sha256'], (cc, filename, 'checksum')
            data = gzip.decompress(payload) if filename.endswith('.gz') else payload
            assert sha(data) == info['uncompressed_sha256']
            part = list(read_csv(d / filename))
            assert len(part) == info['rows']
            rows.extend(part)
            checks += 3
        rows.sort(key=lambda r: int(r['geonameid']))
        by_id = {r['id']: r for r in rows}
        assert len(by_id) == len(rows)
        assert not seen.intersection(by_id), ('duplicate ID across countries', cc)
        seen.update(by_id)
        for r in rows:
            assert r['country_code'] == cc
            pid = r['parent_id']
            assert not pid or pid == 'country:' + cc or pid in by_id
            if pid in by_id:
                p = by_id[pid]
                assert p['kind'] == 'admin_subdivision'
                if r['admin_level']:
                    assert int(p['admin_level']) == int(r['admin_level']) - 1
                assert code_key(r, int(p['admin_level'])) == code_key(p, int(p['admin_level']))
            visited = {r['id']}
            node = pid
            while node in by_id:
                assert node not in visited, ('cycle', cc, node)
                visited.add(node)
                node = by_id[node]['parent_id']
            assert not r['state_id'] or (r['state_id'] in by_id and by_id[r['state_id']]['admin_level'] == '1')
            for field in ('parent_candidates_json', 'state_candidates_json'):
                assert all(e in by_id for e in json.loads(r[field]))
        # All 19 original fields survive; rebuilding from the shipped data is exact.
        replay = build_rows([{k: r[k] for k in RAW} for r in rows], cc)
        assert replay == rows, (cc, 'offline replay mismatch')
        preview = (d / 'admin1.csv').read_bytes()
        assert sha(preview) == meta['preview_files']['admin1.csv']['sha256']
        assert preview == csv_bytes([r for r in rows if r['admin_level'] == '1'])
        assert len(rows) == meta['source_file']['retained_rows']
        checks += 10
        reports.append(dict(country=cc, rows=len(rows), replay='exact', integrity='passed'))
    report = dict(schema_version=1, countries=len(reports), rows=len(seen),
                  file_and_country_checks=checks, errors=0, reports=reports,
                  limits=['Integrity checks do not certify current legal administrative boundaries.',
                          'Unresolved source references are retained and counted, not repaired by name matching.'])
    write_json(output / 'verification.json', report)
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['build', 'summarize', 'verify'])
    p.add_argument('--inputs', type=Path)
    p.add_argument('--output', type=Path, default=ROOT)
    p.add_argument('--retrieved-on', default='2026-09-26')
    p.add_argument('--countries', nargs='+')
    args = p.parse_args()
    if args.command == 'build':
        if args.inputs is None:
            p.error('--inputs is required')
        build(args.inputs, args.output, args.retrieved_on, args.countries)
    elif args.command == 'summarize':
        print(jdump(summarize(args.output)))
    else:
        report = verify(args.output)
        print(jdump({k: v for k, v in report.items() if k not in ('reports', 'limits')}))


if __name__ == '__main__':
    main()
