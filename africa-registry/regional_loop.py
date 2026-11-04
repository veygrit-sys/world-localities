#!/usr/bin/env python3
"""Bounded north-first Africa enrichment. Never modifies the baseline registry.

Python 3.11+, standard library. Outputs are review candidates, not delivery data.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date, datetime, timezone
import gzip
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import re
import sys
import time
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parent
REGIONS = {
    'north': ('Northern Africa', 'DZ EG LY MA SD TN EH'.split()),
    'west': ('Western Africa', 'BJ BF CV CI GM GH GN GW LR ML MR NE NG SH SN SL TG'.split()),
    'middle': ('Middle Africa', 'AO CM CF TD CG CD GQ GA ST'.split()),
    'east': ('Eastern Africa', 'IO BI KM DJ ER ET TF KE MG MW MU YT MZ RE RW SC SO SS TZ UG ZM ZW'.split()),
    'south': ('Southern Africa', 'BW SZ LS NA ZA'.split()),
}
DUMP = 'https://download.geonames.org/export/dump/'
ALT_FIELDS = ('alternateNameId geonameid isolanguage alternate_name isPreferredName '
              'isShortName isColloquial isHistoric from to').split()
NAME_FIELDS = ['entity_id'] + ALT_FIELDS + ['value_kind', 'search_key', 'source_columns']
NON_LANGUAGE = {'post', 'iata', 'icao', 'faac', 'link', 'wkdt', 'abbr'}
MAX_DOWNLOAD = 64_000_000
MAX_MEMBER = 250_000_000


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def save_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(data, encoding='utf-8')
    temporary.replace(path)


def search_key(value: str) -> str:
    # Do not remove diacritics or rewrite Arabic letters: this is not an ID key.
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


def encode_csv(rows: list[dict], fields: list[str]) -> bytes:
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode('utf-8')


def gzip_bytes(data: bytes) -> bytes:
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode='wb', filename='', mtime=0) as handle:
        handle.write(data)
    return out.getvalue()


def ordered_scope(registry: Path, regions: list[str]) -> list[tuple[str, dict]]:
    source = read_json(registry / 'upstream' / 'scope.json')
    countries = source['countries']
    indexed = {c['country']: c for c in countries}
    expected = [cc for _, codes in REGIONS.values() for cc in codes]
    require(len(expected) == len(set(expected)) == 60, 'invalid configured scope')
    require(len(countries) == len(indexed) == 60 and set(indexed) == set(expected),
            'Africa source scope changed: human review required')
    require(bool(regions) and len(regions) == len(set(regions)), 'empty/duplicate regions')
    require(set(regions) <= set(REGIONS), 'unknown region')
    # Always follow north -> west -> middle -> east -> south, even for subsets.
    selected = []
    for key, (name, codes) in REGIONS.items():
        for cc in codes:
            require(indexed[cc]['region'] == name, 'source region changed: ' + cc)
            if key in regions:
                selected.append((key, indexed[cc]))
    return selected


def fetch(relative: str, cache: Path, offline: bool) -> tuple[Path, dict]:
    require(bool(re.fullmatch(r'(?:alternatenames/)?[A-Z]{2}\.zip', relative)),
            'unapproved source path')
    path = cache / relative
    receipt = path.with_suffix('.source.json')
    url = DUMP + relative
    if path.exists():
        require(receipt.exists(), 'cache missing provenance: ' + relative)
        meta = read_json(receipt)
        require(meta['url'] == url and meta['sha256'] == digest(path.read_bytes()),
                'cache checksum/provenance mismatch: ' + relative)
        return path, meta
    require(not offline, 'offline source missing: ' + relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'world-localities-africa/1.0'}),
                         timeout=45) as response:
                require(response.geturl().startswith(DUMP), 'unexpected source redirect')
                payload = response.read(MAX_DOWNLOAD + 1)
                require(0 < len(payload) <= MAX_DOWNLOAD, 'source size limit')
                meta = dict(url=url, sha256=digest(payload), bytes=len(payload),
                            retrieved_at_utc=datetime.now(timezone.utc).isoformat(),
                            http_last_modified=response.headers.get('Last-Modified'),
                            etag=response.headers.get('ETag'), license='CC-BY-4.0')
            require(zipfile.is_zipfile(io.BytesIO(payload)), 'source is not a ZIP')
            temporary = path.with_suffix('.part')
            temporary.write_bytes(payload)
            temporary.replace(path)
            save_json(receipt, meta)
            return path, meta
        except (HTTPError, URLError, TimeoutError) as exc:
            if isinstance(exc, HTTPError) and exc.code not in (408, 429, 500, 502, 503, 504):
                raise
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError('unreachable')


def zip_lines(path: Path, country: str):
    with zipfile.ZipFile(path) as archive:
        matches = [entry for entry in archive.infolist() if entry.filename == country + '.txt']
        require(len(matches) == 1, 'missing or duplicate country ZIP member')
        entry = matches[0]
        require(0 <= entry.file_size <= MAX_MEMBER, 'expanded source size limit')
        with archive.open(entry) as handle:
            yield from io.TextIOWrapper(handle, encoding='utf-8')


def collect_names(lines, entity_ids: set[str]) -> tuple[list[dict], dict]:
    rows, seen, skipped, formats = [], set(), 0, Counter()
    for line in lines:
        values = line.rstrip('\r\n').split('\t')
        require(len(values) in (8, 10), 'alternate names schema changed')
        width = len(values)
        values += [''] * (10 - width)
        r = dict(zip(ALT_FIELDS, values))
        require(bool(re.fullmatch('[1-9][0-9]*', r['alternateNameId'])), 'invalid name ID')
        require(bool(re.fullmatch('[1-9][0-9]*', r['geonameid'])), 'invalid name entity ID')
        require(all(r[f] in ('', '0', '1') for f in ALT_FIELDS[4:8]), 'invalid name flag')
        require(bool(r['alternate_name']), 'empty alternate name')
        eid = 'gn:' + r['geonameid']
        if eid not in entity_ids:
            skipped += 1  # H/R/S/T features are outside this A/P locality scope.
            continue
        require(r['alternateNameId'] not in seen, 'duplicate alternate name ID')
        seen.add(r['alternateNameId'])
        lang = r['isolanguage']
        kind = ('external_identifier' if lang in NON_LANGUAGE else
                'language_name' if re.fullmatch(r'[a-z]{2,3}(?:[-_][A-Za-z0-9]+)*', lang)
                else 'unclassified_name')
        rows.append(dict(entity_id=eid, **r, value_kind=kind,
                         search_key=search_key(r['alternate_name']), source_columns=str(width)))
        formats[str(width)] += 1
    rows.sort(key=lambda r: int(r['alternateNameId']))
    return rows, dict(retained=len(rows), out_of_scope=skipped, source_formats=dict(formats),
                      language_names=sum(r['value_kind'] == 'language_name' for r in rows),
                      historical_names=sum(r['isHistoric'] == '1' for r in rows),
                      external_identifiers=sum(r['value_kind'] == 'external_identifier' for r in rows))


def validate_raw(rows: list[dict], country: str, as_of: date) -> None:
    seen = set()
    for row in rows:
        require(row['country_code'] == country, 'country mismatch')
        require(row['geonameid'] not in seen, 'duplicate source ID')
        seen.add(row['geonameid'])
        require(row['feature_class'] in ('A', 'P'), 'feature scope mismatch')
        require(bool(row['name'].strip()), 'empty name')
        for field, bound in [('latitude', 90), ('longitude', 180)]:
            value = float(row[field])
            require(math.isfinite(value) and -bound <= value <= bound, 'invalid coordinate')
        require(date.fromisoformat(row['modification_date']) <= as_of, 'future modification date')


def compare_baseline(old: list[dict], new: list[dict], has_baseline: bool) -> dict:
    before, after = {r['id']: r for r in old}, {r['id']: r for r in new}
    shared = set(before) & set(after)
    lost = sorted(set(before) - set(after))
    columns = ('name', 'feature_code', 'admin1_code', 'admin2_code',
               'admin3_code', 'admin4_code', 'parent_id')
    changed = sorted(eid for eid in shared if any(before[eid][k] != after[eid][k] for k in columns))
    return dict(baseline_present=has_baseline, before=len(old), after=len(new),
                added=len(set(after) - set(before)), removed=len(lost), changed=len(changed),
                removed_ids=lost, changed_ids=changed,
                baseline_max_modified=max((r['modification_date'] for r in old), default=None),
                candidate_max_modified=max((r['modification_date'] for r in new), default=None))


def release_blockers(delta: dict, old: list[dict], new: list[dict]) -> list[str]:
    blockers = []
    if delta['removed']:
        blockers.append('source_ids_disappeared_review_before_removal')
    if old and len(new) < len(old) * 0.95:
        blockers.append('row_count_drop_over_5_percent')
    if old and delta['candidate_max_modified'] < delta['baseline_max_modified']:
        blockers.append('candidate_is_older_than_baseline')
    unresolved = lambda rows: sum(r['parent_relation'] in (
        'missing_code', 'missing_reference', 'ambiguous_code') for r in rows)
    if old and unresolved(new) > unresolved(old):
        blockers.append('unresolved_parent_count_increased')
    return blockers


def validate_official_reference(reference: dict) -> None:
    require(reference['country'] == 'DZ', 'unexpected official country')
    records = reference['records']
    require(len(records) == 11, 'official reference must contain eleven additions')
    require({r['source_code'] for r in records} == {str(i) for i in range(59, 70)},
            'official source codes must be 59 through 69')
    require(len({r['id'] for r in records}) == 11, 'duplicate official ID')
    for r in records:
        require(r['geonames_id'] is None and r['iso_3166_2'] is None, 'unreviewed crosswalk')
        require(r['name_fr'] == r['seat_name_fr'], 'seat differs from inspected decree')
    require(reference['operational_effective_on'] is None, 'unverified operational date')


def load_builder(registry: Path):
    spec = importlib.util.spec_from_file_location('africa_baseline_builder', registry / 'build.py')
    require(spec is not None and spec.loader is not None, 'baseline builder unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def process_country(builder, registry: Path, cache: Path, output: Path,
                    country_meta: dict, offline: bool) -> dict:
    cc = country_meta['country']
    source, source_meta = fetch(cc + '.zip', cache, offline)
    all_raw = []
    for line in zip_lines(source, cc):
        values = line.rstrip('\r\n').split('\t')
        require(len(values) == len(builder.RAW), 'GeoNames source schema changed')
        all_raw.append(dict(zip(builder.RAW, values)))
    raw = [r for r in all_raw if r['feature_class'] in ('A', 'P')]
    validate_raw(raw, cc, date.fromisoformat(source_meta['retrieved_at_utc'][:10]))
    require(bool(raw), 'empty A/P country extract')
    rows = builder.build_rows(raw, cc)
    require(rows == builder.build_rows(list(reversed(raw)), cc), 'order-dependent build')
    # Rebuild from output source columns, not merely re-hash the same buffer.
    replay = builder.build_rows([{k: r[k] for k in builder.RAW} for r in rows], cc)
    require(rows == replay, 'lossless replay mismatch')
    old_path = registry / 'countries' / cc / 'entities.csv.gz'
    old = list(builder.read_csv(old_path)) if old_path.exists() else []
    if old_path.exists():
        old_meta = read_json(old_path.parent / 'metadata.json')
        require(digest(old_path.read_bytes()) == old_meta['files']['entities.csv.gz']['sha256'],
                'baseline integrity failure: ' + cc)
    delta = compare_baseline(old, rows, old_path.exists())
    blockers = release_blockers(delta, old, rows)
    source_meta = dict(source_meta, retrieved_on=source_meta['retrieved_at_utc'][:10],
                       source_rows=len(all_raw), retained_rows=len(rows),
                       discarded_feature_classes=dict(Counter(r['feature_class'] for r in all_raw
                                                               if r['feature_class'] not in ('A', 'P'))))
    stats = builder.write_country(rows, cc, output, source_meta, country_meta)
    target = output / 'countries' / cc
    save_json(target / 'delta.json', delta)
    names_status, names_stats, names_source = 'not_collected', {}, None
    try:
        path, names_source = fetch('alternatenames/' + cc + '.zip', cache, offline)
        names, names_stats = collect_names(zip_lines(path, cc), {r['id'] for r in rows})
        csv_data = encode_csv(names, NAME_FIELDS)
        payload = gzip_bytes(csv_data)
        require(payload == gzip_bytes(csv_data), 'non-deterministic compression')
        require(list(csv.DictReader(io.StringIO(gzip.decompress(payload).decode('utf-8')))) == names,
                'names round-trip mismatch')
        (target / 'names.csv.gz').write_bytes(payload)
        names_status = 'source_enriched'
        names_stats.update(sha256=digest(payload), uncompressed_sha256=digest(csv_data))
    except (ValueError, OSError, URLError, zipfile.BadZipFile, KeyError) as exc:
        names_status = 'blocked'
        names_stats = dict(error=str(exc))
        blockers.append('alternate_names_not_verified')
    if cc == 'DZ':
        adm1 = sum(r['admin_level'] == '1' for r in rows)
        if adm1 != 69:
            blockers.append('DZ_2026_official_69_wilayas_reference_gap')
    save_json(target / 'enrichment.json', dict(
        schema_version=1, country=cc, names_status=names_status, names=names_stats,
        names_source=names_source, release_blockers=blockers, release_approved=False,
        name_policy='Raw language, preference and time flags retained; not independently official.',
        postal_policy='post values are source identifiers, not verified postcode assignments.',
        identity_policy='gn IDs and source country/cc2 retained; no name-based entity merge.'))
    return dict(country=cc, status='integrity_checked_candidate', counts=stats,
                names_status=names_status, names=names_stats, release_blockers=blockers,
                delta={k: v for k, v in delta.items() if not k.endswith('_ids')})


def run(registry: Path, output: Path, cache: Path, regions: list[str], offline: bool) -> dict:
    require(not sys.flags.optimize, 'run without -O: upstream verification uses assertions')
    require(not output.exists(), 'output exists; choose a new candidate directory')
    registry, output, cache = registry.resolve(), output.resolve(), cache.resolve()
    require(not output.is_relative_to(registry) and not registry.is_relative_to(output),
            'candidate output must be outside baseline registry')
    require(not cache.is_relative_to(registry) and not registry.is_relative_to(cache),
            'source cache must be outside baseline registry')
    require(not output.is_relative_to(cache) and not cache.is_relative_to(output),
            'candidate output and source cache must not overlap')
    selected = ordered_scope(registry, regions)
    official = read_json(registry / 'official-references' / 'DZ-2026-wilayas.json')
    validate_official_reference(official)
    builder = load_builder(registry)
    output.mkdir(parents=True)
    save_json(output / 'official-references' / 'DZ-2026-wilayas.json', official)
    report = dict(schema_version=1, order=list(REGIONS), requested_regions=regions,
                  planned_countries=len(selected), completed_countries=0, errors=[], results=[],
                  baseline_modified=False, release_approved=False,
                  original_scope_sha256=digest((registry / 'upstream' / 'scope.json').read_bytes()),
                  builder_sha256=digest((registry / 'build.py').read_bytes()))
    completed_meta = []
    for region, country in selected:
        print('PROCESS', region, country['country'], flush=True)
        try:
            result = process_country(builder, registry, cache, output, country, offline)
            result['region'] = region
            report['results'].append(result)
            completed_meta.append(country)
            report['completed_countries'] += 1
        except (ValueError, OSError, URLError, zipfile.BadZipFile, KeyError, AssertionError) as exc:
            report['errors'].append(dict(country=country['country'], region=region, error=str(exc)))
        save_json(output / 'run-report.json', report)
    save_json(output / 'scope.json', dict(schema_version=1, countries=completed_meta,
              source_url='https://unstats.un.org/unsd/methodology/m49/',
              source_scope='frozen baseline scope; not a fresh legal-territory certification'))
    if completed_meta:
        builder.summarize(output)
        builder.verify(output)
    report['integrity_passed'] = not report['errors'] and len(completed_meta) == len(selected)
    report['names_complete'] = (report['integrity_passed'] and
                                all(r['names_status'] == 'source_enriched' for r in report['results']))
    report['review_blocked_countries'] = [r['country'] for r in report['results']
                                          if r['release_blockers']]
    report['limits'] = ['Official current hierarchy, postal delivery, Address1 and Address2 unverified.',
                        'Candidates must not replace baseline without reviewing deltas and blockers.',
                        'No sovereign claims inferred from M49 groupings or GeoNames country codes.']
    save_json(output / 'run-report.json', report)
    inventory = {}
    for path in sorted(output.rglob('*')):
        if path.is_file():
            data = path.read_bytes()
            inventory[str(path.relative_to(output))] = dict(sha256=digest(data), bytes=len(data))
    save_json(output / 'artifact-manifest.json', dict(schema_version=1, files=inventory))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--regions', nargs='+', choices=list(REGIONS), default=list(REGIONS))
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    report = run(args.registry, args.output, args.cache, args.regions, args.offline)
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}, ensure_ascii=False))
    return 0 if report['integrity_passed'] and report['names_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
