#!/usr/bin/env python3
"""Build reproducible ID-linked labels and postal evidence from pinned snapshots."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def csv_bytes(rows):
    stream = io.StringIO(newline='')
    if rows:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: encode(v) if isinstance(v, (list, dict)) else v for k, v in row.items()})
    return ('\ufeff' + stream.getvalue()).encode('utf-8')


def build(base, sources, output):
    with zipfile.ZipFile(base) as archive:
        prefix = 'oceania_dataset_20260927/'
        countries = json.loads(archive.read(prefix + 'countries.json'))
        entities = {}
        for name in sorted(archive.namelist()):
            if name.startswith(prefix + 'data/') and name.endswith('/places.jsonl'):
                for line in archive.read(name).decode('utf-8').splitlines():
                    row = json.loads(line)
                    entities[row['source_id']] = row
    entity_count = len(entities)
    base_counts = Counter(row['country_code'] for row in entities.values())
    for country in countries:
        entities[country['geonames_country_id']] = {
            'id': country['id'], 'country_code': country['country_code'],
            'kind': 'country', 'name': country['name_en']}
    names, postals, profiles, coverage = [], [], {}, []
    defaults = json.loads((sources / 'address-templates/ZZ.json').read_text())
    for country in sorted(countries, key=lambda c: c['country_code']):
        cc = country['country_code']
        source_file = 'alternatenames/' + cc + '.zip'
        before_names, before_postals = len(names), len(postals)
        excluded = Counter()
        with zipfile.ZipFile(sources / source_file) as archive:
            lines = archive.read(cc + '.txt').decode('utf-8').splitlines()
        for lineno, line in enumerate(lines, 1):
            fields = line.split('\t')
            if len(fields) != 10:
                raise ValueError(f'{cc}:{lineno}: expected 10 alternate-name columns')
            aid, gid, lang, text, preferred, short, colloquial, historic, start, end = fields
            entity = entities.get(gid)
            if not entity or entity['country_code'] != cc:
                excluded['entity_outside_base_scope'] += 1
                continue
            shared = {'id': 'geonames-alternate:' + aid, 'entity_id': entity['id'],
                      'source': 'GeoNames', 'source_file': source_file,
                      'source_line': lineno, 'historic': historic == '1',
                      'valid_from': start, 'valid_to': end}
            if lang == 'post':
                postals.append({**shared, 'country_code': cc, 'postal_code': text,
                                'relation': 'source_direct_id', 'delivery_validated': False})
            elif re.fullmatch(r'[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*', lang) and lang not in {'abbr', 'link', 'post', 'wkdt', 'unlc', 'iata', 'icao', 'faac', 'phon'}:
                names.append({**shared, 'language': lang, 'text': text, 'usage': 'generic',
                              'preferred': preferred == '1', 'short': short == '1',
                              'colloquial': colloquial == '1', 'status': 'source_attested'})
            else:
                excluded['untagged_or_non_language'] += 1
        names.append({'id': 'un-m49:' + country['m49_code'] + ':en', 'entity_id': country['id'],
                      'source': 'UN M49', 'source_file': 'base:countries.json', 'source_line': None,
                      'historic': False, 'valid_from': '', 'valid_to': '',
                      'language': 'en', 'text': country['name_en'], 'usage': 'generic',
                      'preferred': True, 'short': False, 'colloquial': False,
                      'status': 'source_attested'})
        raw = json.loads((sources / 'address-templates' / (cc + '.json')).read_text())
        merged = {**defaults, **raw}
        profiles[cc] = {key: merged[key] for key in ('fmt', 'lfmt', 'require', 'upper', 'zip') if key in merged}
        profiles[cc].update({
            'country_code': cc, 'country_name_en': country['name_en'],
            'reported_local_languages': list(filter(None, country['geonames_reported_languages'].split(','))),
            'language_policy': 'explicit_locale_required; no monolingual-country assumption',
            'language_source': 'GeoNames countryInfo; not exhaustive or official-language certification',
            'modes': {'local': 'caller-supplied locale', 'international_english': 'en',
                      'domestic_english': 'en-' + cc},
            'template_status': 'country_specific' if 'fmt' in raw else 'generic_fallback',
            'inherited_default_fields': [key for key in ('fmt', 'require', 'upper') if key not in raw],
            'source': 'https://chromium-i18n.appspot.com/ssl-address/data/' + cc,
            'default_source': 'https://chromium-i18n.appspot.com/ssl-address/data/ZZ',
        })
        own_names = names[before_names:]
        own_postals = postals[before_postals:]
        current = [row for row in own_names if not row['historic'] and not row['valid_to']]
        coverage.append({'country_code': cc,
                         'base_entities_including_country': base_counts[cc] + 1,
                         'language_tagged_names': len(own_names),
                         'entities_with_tagged_names': len({r['entity_id'] for r in own_names}),
                         'entities_with_current_english': len({r['entity_id'] for r in current if r['language'].lower() == 'en'}),
                         'domestic_english_variant_names': sum(r['language'].lower() == 'en-' + cc.lower() for r in current),
                         'postal_links': len(own_postals),
                         'postal_linked_entities': len({r['entity_id'] for r in own_postals}),
                         'template_status': profiles[cc]['template_status'],
                         'excluded_rows': dict(excluded)})
    names.sort(key=lambda row: (row['entity_id'], row['language'], row['id']))
    postals.sort(key=lambda row: (row['country_code'], row['postal_code'], row['entity_id'], row['id']))
    if len({row['id'] for row in names}) != len(names) or len({row['id'] for row in postals}) != len(postals):
        raise ValueError('duplicate source alternate-name IDs')
    files = {
        'names.jsonl': ('\n'.join(map(encode, names)) + '\n').encode(),
        'postal_links.jsonl': ('\n'.join(map(encode, postals)) + '\n').encode(),
        'names.csv': csv_bytes(names), 'postal_links.csv': csv_bytes(postals),
        'country_profiles.json': (json.dumps(profiles, ensure_ascii=False, indent=2) + '\n').encode(),
        'coverage.csv': csv_bytes(coverage),
        'coverage.json': (json.dumps(coverage, ensure_ascii=False, indent=2) + '\n').encode(),
    }
    for path in sorted(sources.rglob('*')):
        if path.is_file() and not path.name.endswith('.part'):
            files['sources/' + path.relative_to(sources).as_posix()] = path.read_bytes()
    postal_sets = defaultdict(set)
    for row in postals:
        postal_sets[(row['country_code'], row['postal_code'])].add(row['entity_id'])
    manifest = {
        'schema_version': '1.0.0', 'base_archive': base.name,
        'base_archive_sha256': hashlib.sha256(base.read_bytes()).hexdigest(),
        'base_places': entity_count, 'country_roots': len(countries),
        'language_tagged_names': len(names), 'postal_links': len(postals),
        'country_postcodes_with_multiple_entities': sum(len(ids) > 1 for ids in postal_sets.values()),
        'country_profiles': len(profiles),
        'country_specific_templates': sum(p['template_status'] == 'country_specific' for p in profiles.values()),
        'postal_coverage_complete': False, 'local_language_coverage_complete': False,
        'domestic_english_distinctions_verified': False,
        'geonames_license': 'CC-BY-4.0', 'google_address_data_license': 'CC-BY-4.0',
        'source_license_reference': 'https://github.com/google/libaddressinput#license',
        'transformations': ['ID filter to original base scope', 'language-tag extraction',
                            'country GeoNames IDs mapped to country:<CC> roots',
                            'direct-ID postal associations', 'Google ZZ default template inheritance'],
        'files': {name: {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                  for name, data in sorted(files.items())}}
    files['manifest.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 9, 27, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    for name in ['country_profiles.json', 'coverage.csv', 'coverage.json', 'manifest.json']:
        (output.parent / ('locale_' + name if name == 'manifest.json' else name)).write_bytes(files[name])
    print(json.dumps({k: v for k, v in manifest.items() if k != 'files'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', type=Path, required=True)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.base, args.sources, args.output)
