#!/usr/bin/env python3
"""Costa Rica supplement: preserve the six-country base, add real A/P source data.

Import is explicit and create-only. Verification never uses the network.
GeoNames language tags and direct-ID postal evidence are not official address
or delivery certification. Sources and all 19 original feature columns survive.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from functools import lru_cache
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import urllib.request
from urllib.parse import urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RELATIVE = 'central-america-registry/enrichment'
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_TEXT = 128 * 1024 * 1024
URLS = {
    'CR.zip': 'https://download.geonames.org/export/dump/CR.zip',
    'alternatenames/CR.zip': 'https://download.geonames.org/export/dump/alternatenames/CR.zip',
    'countryInfo.txt': 'https://download.geonames.org/export/dump/countryInfo.txt',
    'readme.txt': 'https://download.geonames.org/export/dump/readme.txt'
}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@lru_cache(maxsize=1)
def libraries():
    """Load existing region adapters without polluting other regions' imports."""
    directory = Path(__file__).resolve().parent
    saved = sys.modules.get('build')
    try:
        build = load_module('cr_builder', directory / 'build.py')
        sys.modules['build'] = build
        names = load_module('cr_names', directory / 'build_names.py')
    finally:
        if saved is None:
            sys.modules.pop('build', None)
        else:
            sys.modules['build'] = saved
    validation = load_module('cr_strict_validation', ROOT / 'north-america-registry/validation.py')
    return build, names, validation


def safe(root, relative):
    return libraries()[2].safe_file(root, relative)


def json_read(root, relative):
    return libraries()[2].decode_json(safe(root, relative).read_bytes())


def json_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def bounded_zip(path, member):
    require(path.stat().st_size <= MAX_ARCHIVE, 'archive exceeds bound')
    with zipfile.ZipFile(path) as archive:
        require(archive.namelist().count(member) == 1, 'missing or duplicated source ZIP member')
        entry = archive.getinfo(member)
        require(entry.file_size <= MAX_TEXT and not entry.is_dir(), 'expanded source exceeds bound')
        with archive.open(entry) as handle:
            data = handle.read(MAX_TEXT + 1)
        require(len(data) == entry.file_size and len(data) <= MAX_TEXT, 'expanded source size mismatch')
    return data


def country_profile(inputs):
    selected = []
    for line in safe(inputs, 'countryInfo.txt').read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):
            continue
        values = line.split('\t')
        if values[0] == 'CR':
            require(len(values) >= 17 and values[1:3] == ['CRI', '188'], 'Costa Rica countryInfo mismatch')
            selected.append(values)
    require(len(selected) == 1, 'missing or duplicated Costa Rica countryInfo')
    row = selected[0]
    return dict(country='CR', alpha3='CRI', numeric='188', m49='188',
                name_en='Costa Rica', region='Central America', id='country:CR',
                geonames_country_name=row[4], geonames_continent=row[8],
                geonames_id=row[16], reported_languages=row[15].split(','),
                status='source_country_or_area')


def expected_rows(inputs):
    b, n, _ = libraries()
    raw = []
    for line in bounded_zip(safe(inputs, 'CR.zip'), 'CR.txt').decode('utf-8').splitlines():
        values = line.split('\t')
        require(len(values) == 19, 'GeoNames feature schema changed')
        raw.append(dict(zip(b.RAW, values)))
    require(raw and all(r['country_code'] == 'CR' for r in raw), 'empty or cross-country source')
    rows = b.build_rows([r for r in raw if r['feature_class'] in ('A', 'P')], 'CR')
    require(rows and any(r['kind'] == 'locality' for r in rows), 'source has no localities')
    profile = country_profile(inputs)
    allowed = {r['geonameid']: r['id'] for r in rows}
    allowed[profile['geonames_id']] = 'country:CR'
    alternate_rows = []
    for line_number, line in enumerate(bounded_zip(safe(inputs, 'alternatenames/CR.zip'), 'CR.txt').decode('utf-8').splitlines(), 1):
        values = line.split('\t')
        require(len(values) == 10, 'GeoNames alternate-name schema changed')
        row = dict(zip(n.ALT, values))
        require(all(row[k] in ('', '0', '1') for k in ('is_preferred', 'is_short', 'is_colloquial', 'is_historic')),
                'invalid alternate-name flag')
        alternate_rows.append((line_number, row))
    names, postals, excluded = n.classify(alternate_rows, allowed, 'CR')
    names.sort(key=lambda r: (r['entity_id'], r['language'], int(r['alternate_name_id'])))
    postals.sort(key=lambda r: (r['postal_code'], r['entity_id'], int(r['alternate_name_id'])))
    return raw, rows, names, postals, profile, excluded


def summary(rows, names, postals):
    current = [r for r in names if r['is_historic'] != '1' and not r['valid_to']]
    return {
        'country': 'CR', 'entities': len(rows),
        'locality_rows': sum(r['kind'] == 'locality' for r in rows),
        'admin_rows': sum(r['kind'] == 'admin_subdivision' for r in rows),
        'other_admin_rows': sum(r['kind'] == 'other_admin_feature' for r in rows),
        'address_candidates': sum(r['address_candidate'] == '1' for r in rows),
        'unresolved_parents': sum(r['parent_relation'] in ('missing_code', 'missing_reference', 'ambiguous_code') for r in rows),
        'ambiguous_parents': sum(r['parent_relation'] == 'ambiguous_code' for r in rows),
        'country_scope_only': sum(r['parent_relation'] == 'country_scope_only' for r in rows),
        'localities_without_adm1': sum(r['kind'] == 'locality' and not r['state_id'] for r in rows),
        'language_tagged_names': len(names), 'postal_links': len(postals),
        'entities_with_current_english': len({r['entity_id'] for r in current if r['language'] == 'en'}),
        'entities_with_current_spanish': len({r['entity_id'] for r in current if r['language'] == 'es'}),
        'feature_counts': dict(sorted(Counter(r['feature_code'] for r in rows).items())),
        'language_counts': dict(sorted(Counter(r['language'] for r in names).items()))
    }


def validate_hierarchy(rows):
    by_id = {r['id']: r for r in rows}
    require(len(by_id) == len(rows), 'duplicate feature identity')
    for row in rows:
        parent = row['parent_id']
        require(not parent or parent == 'country:CR' or parent in by_id, 'unresolved nonempty parent ID')
        if parent in by_id:
            require(by_id[parent]['kind'] == 'admin_subdivision', 'parent is not administrative')
        visited = {row['id']}
        while parent in by_id:
            require(parent not in visited, 'parent cycle')
            visited.add(parent)
            parent = by_id[parent]['parent_id']
        require(not row['state_id'] or (row['state_id'] in by_id and by_id[row['state_id']]['admin_level'] == '1'),
                'invalid ADM1 reference')


def build_package(inputs, output):
    b, n, _ = libraries()
    raw, rows, names, postals, profile, excluded = expected_rows(inputs)
    validate_hierarchy(rows)
    receipts = json_read(inputs, 'receipts.json')
    require(set(receipts) == set(URLS), 'source receipt inventory mismatch')
    for filename, url in URLS.items():
        data = safe(inputs, filename).read_bytes()
        receipt = receipts[filename]
        require(receipt['url'] == url and receipt['sha256'] == sha(data) and receipt['bytes'] == len(data),
                'source receipt hash or URL mismatch')
    require('Creative Commons Attribution 4.0' in safe(inputs, 'readme.txt').read_text(encoding='utf-8'),
            'source licence notice changed; manual review required')
    shutil.copytree(inputs, output / 'sources')
    source = dict(receipts['CR.zip'], source_rows=len(raw), retained_rows=len(rows),
                  discarded_feature_classes=dict(Counter(r['feature_class'] for r in raw if r['feature_class'] not in ('A', 'P'))))
    b.write_country(rows, 'CR', output, source, profile)
    json_write(output / 'sources/alternatenames/CR.json', receipts['alternatenames/CR.zip'])
    n.build_locale(output / 'sources', output, 'CR')
    counts = summary(rows, names, postals)
    json_write(output / 'summary.json', counts)
    json_write(output / 'scope.json', {
        'schema_version': 1, 'region_m49': '013', 'countries': [profile],
        'publication': 'Additive Costa Rica source supplement; six-country historical base unchanged',
        'source_url': 'https://unstats.un.org/unsd/methodology/m49/overview/'
    })
    json_write(output / 'quality.json', {
        'official_reference': {'publisher': 'Tribunal Supremo de Elecciones de Costa Rica',
            'url': 'https://tse.go.cr/comunicado1103.html', 'published_on': '2025-11-13',
            'reference': '84 cantonal electoral boards for the 2026 national election', 'cantons': 84},
        'source_adm2_count': counts['feature_counts'].get('ADM2', 0),
        'status': 'count_matches_reference_hierarchy_not_verified' if counts['feature_counts'].get('ADM2') == 84 else 'source_reference_count_mismatch',
        'official_code_crosswalk_verified': False, 'postal_delivery_verified': False,
        'complete_street_or_unit_addresses': False,
        'note': 'An equal count is not proof of current official canton identity or complete district coverage.'
    })
    (output / 'NOTICE.md').write_text(
        '# Costa Rica GeoNames supplement\n\nData: GeoNames, https://www.geonames.org/ and https://download.geonames.org/export/dump/. '
        'CC BY 4.0: https://creativecommons.org/licenses/by/4.0/. '
        'Original country and alternate-name extracts are retained with download receipts. '
        'Changes: A/P feature selection, source-code parent links, language-tag filtering and deterministic CSV/gzip packaging. '
        'No official translation, postal assignment or delivery guarantee is implied. '
        'The countryInfo country root label mapping is explicit. '
        'Existing six-country CC BY 4.0 data and separate Mexico ODbL-linked material retain their licences.\n', encoding='utf-8')
    files = {p.relative_to(output).as_posix(): {'bytes': p.stat().st_size, 'sha256': sha(p.read_bytes())}
             for p in sorted(output.rglob('*')) if p.is_file()}
    json_write(output / 'manifest.json', {
        'schema_version': 1, 'country': 'CR', 'license': 'CC-BY-4.0',
        'source_integrity': 'pinned downloaded bytes; not live freshness or publisher signatures',
        'observed_at': receipts['CR.zip']['retrieved_at'], 'files': files,
        'claims': {'official_municipal_completeness': False, 'postal_delivery_verified': False,
                   'complete_english_names': False, 'street_or_unit_completeness': False}
    })
    return verify_package(output)


def verify_package(output):
    output = Path(output)
    b, n, v = libraries()
    manifest = json_read(output, 'manifest.json')
    require(manifest['schema_version'] == 1 and manifest['country'] == 'CR' and manifest['license'] == 'CC-BY-4.0',
            'invalid supplement identity')
    claims = manifest['claims']
    require(set(claims) == {'official_municipal_completeness', 'postal_delivery_verified', 'complete_english_names', 'street_or_unit_completeness'}
            and all(x is False for x in claims.values()), 'unsafe supplement claims')
    files = manifest['files']
    actual = {p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file() or p.is_symlink()}
    require(actual == set(files) | {'manifest.json'}, 'missing or unexpected supplement files')
    for relative, info in files.items():
        path = safe(output, relative)
        require(type(info['bytes']) is int and 0 <= info['bytes'] <= MAX_TEXT and path.stat().st_size == info['bytes'],
                'file byte-size mismatch')
        require(sha(path.read_bytes()) == info['sha256'], 'file SHA-256 mismatch: ' + relative)
    raw, rows, names, postals, profile, excluded = expected_rows(output / 'sources')
    validate_hierarchy(rows)
    directory = 'countries/CR/'
    for filename, expected, columns in (('entities.csv.gz', rows, b.FIELDS), ('names.csv.gz', names, n.NAMES),
                                        ('postal_links.csv.gz', postals, n.POSTAL)):
        with gzip.GzipFile(fileobj=io.BytesIO(safe(output, directory + filename).read_bytes())) as handle:
            expanded = handle.read(MAX_TEXT + 1)
        require(len(expanded) <= MAX_TEXT, 'derived CSV expands beyond bound')
        require(v.csv_rows(expanded, columns) == expected, 'raw source replay mismatch: ' + filename)
    require(safe(output, directory + 'admin1.csv').read_bytes() == b.csv_bytes([r for r in rows if r['admin_level'] == '1']),
            'ADM1 preview replay mismatch')
    meta = json_read(output, directory + 'metadata.json')
    locale = json_read(output, directory + 'locale_metadata.json')
    counts = summary(rows, names, postals)
    require(json_read(output, 'summary.json') == counts, 'summary replay mismatch')
    for field in ('locality_rows', 'admin_rows', 'other_admin_rows', 'address_candidates', 'unresolved_parents',
                  'ambiguous_parents', 'country_scope_only', 'localities_without_adm1'):
        require(meta['counts'][field] == counts[field], 'country metadata count mismatch: ' + field)
    require(meta['country'] == profile and meta['feature_counts'] == counts['feature_counts'], 'country metadata replay mismatch')
    require(meta['source_file']['retained_rows'] == len(rows) and meta['source_file']['source_rows'] == len(raw),
            'source selection count mismatch')
    require(meta['current_official_hierarchy_verified'] is False and locale['postal_delivery_validated'] is False,
            'unsupported current official/delivery claim')
    require(locale['counts']['language_tagged_names'] == len(names) and locale['counts']['postal_links'] == len(postals)
            and locale['language_counts'] == counts['language_counts'] and locale['excluded_counts'] == excluded,
            'locale metadata replay mismatch')
    receipts = json_read(output, 'sources/receipts.json')
    require(set(receipts) == set(URLS), 'source receipt scope mismatch')
    for filename, url in URLS.items():
        data = safe(output / 'sources', filename).read_bytes()
        require(receipts[filename]['url'] == url and receipts[filename]['sha256'] == sha(data)
                and receipts[filename]['bytes'] == len(data), 'source receipt mismatch')
    return dict(status='passed', raw_source_replay='exact', derived_rows_replay='exact',
                source_observed_at=manifest['observed_at'], manifest_sha256=sha(safe(output, 'manifest.json').read_bytes()),
                checked_files=len(files) + 1, **counts)


def verify(root=ROOT):
    return verify_package(Path(root) / RELATIVE)


class SourceRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        parsed = urlsplit(newurl)
        require(parsed.scheme == 'https' and parsed.hostname == 'download.geonames.org', 'unexpected source redirect')
        return super().redirect_request(request, fp, code, message, headers, newurl)


def download_sources(destination):
    receipts = {}
    opener = urllib.request.build_opener(SourceRedirects())
    for filename, url in URLS.items():
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={'User-Agent': 'world-localities-costa-rica-source-import/1.0'})
                with opener.open(request, timeout=90) as response:
                    data = response.read(MAX_ARCHIVE + 1)
                    require(0 < len(data) <= MAX_ARCHIVE, 'source download size rejected')
                    receipt = dict(url=url, final_url=response.geturl(), bytes=len(data), sha256=sha(data),
                        retrieved_at=datetime.now(timezone.utc).isoformat(),
                        retrieved_on=datetime.now(timezone.utc).date().isoformat(),
                        last_modified=response.headers.get('Last-Modified'), etag=response.headers.get('ETag'))
                path = destination / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                receipts[filename] = receipt
                break
            except (OSError, ValueError):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
    json_write(destination / 'receipts.json', receipts)


def import_once(root=ROOT):
    root = Path(root).resolve()
    target = root / RELATIVE
    require(not target.is_symlink() and not target.parent.is_symlink(), 'unsafe output directory')
    if target.exists():
        return verify_package(target)
    with tempfile.TemporaryDirectory(prefix='.cr-import-', dir=target.parent) as temporary:
        work = Path(temporary)
        inputs, output = work / 'inputs', work / 'output'
        inputs.mkdir(); output.mkdir()
        download_sources(inputs)
        report = build_package(inputs, output)
        require(not target.exists(), 'supplement appeared concurrently; refusing overwrite')
        output.rename(target)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('import', 'verify'))
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        report = import_once(args.root) if args.command == 'import' else verify(args.root)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        parser.exit(2, f'error: {exc}\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
