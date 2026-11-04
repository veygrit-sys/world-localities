"""Deterministic official-code and postal joins; no machine translation."""
import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from romanize import METHOD, REFERENCE, convert
from sync import SOURCES

ROOT = Path(__file__).resolve().parent
ROLES = ['prefecture', 'municipality', 'town']


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def key_id(prefix, values):
    return prefix + digest(json.dumps(values, ensure_ascii=False, separators=(',', ':')).encode())[:24]


def write_csv(path, rows, fields):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fields, lineterminator='\n', extrasaction='raise')
    writer.writeheader(); writer.writerows(rows)
    data = stream.getvalue().encode('utf-8')
    if path.suffix == '.gz':
        data = gzip.compress(data, mtime=0)
    path.write_bytes(data)
    return {'rows': len(rows), 'bytes': len(data), 'sha256': digest(data), 'columns': fields}


def zip_csv(path, encoding, width):
    with zipfile.ZipFile(path) as archive:
        members = [n for n in archive.namelist() if n.lower().endswith('.csv')]
        if len(members) != 1 or archive.getinfo(members[0]).file_size > 100_000_000:
            raise ValueError('Unexpected ZIP contents')
        rows = list(csv.reader(io.StringIO(archive.read(members[0]).decode(encoding))))
    if any(len(r) != width for r in rows):
        raise ValueError('Source CSV schema changed')
    return rows


def spaces(text):
    return ''.join(text.split())


def roman_index(rows):
    index = defaultdict(list)
    for n, row in enumerate(rows, 1):
        index[tuple(spaces(v) for v in row[:4])].append((n, row))
    return index


def roman_match(row, index):
    matches = index.get((row[2], *(spaces(v) for v in row[6:9])), [])
    return ('matched_unique' if len(matches) == 1 else 'ambiguous' if matches else 'unmatched'), matches


def valid_lg(code):
    if not re.fullmatch('[0-9]{6}', code):
        return False
    check = (11 - sum(int(d) * w for d, w in zip(code[:5], (6, 5, 4, 3, 2))) % 11) % 10
    return 1 <= int(code[:2]) <= 47 and int(code[-1]) == check


def source_metadata(country, folder):
    data = {'schema_version': 1, 'observed_on': '2026-10-01', 'sources': {}, 'bundled_files': {}}
    if country == 'JP':
        data['sources']['jp-abr-snapshot'] = {
            'provider': 'Digital Agency Japan ABR / WorldAddress curated registry',
            'repository': 'https://github.com/rei-k/world-address',
            'commit': '8e30ef141e40769fa932adeb2f901505023bfd1e',
            'path': 'address-foundation/japan-registry', 'source_observed_on': '2026-09-25',
            'as_of': '2026-09-26', 'licence': 'ODbL-1.0; ABR CC-BY-4.0 source terms retained',
            'terms': 'https://www.digital.go.jp/policies/base_registry_address_tos',
            'note': 'Pinned source rows and hierarchy retained; fresh ABR ZIP requests returned HTTP 403 on 2026-10-01. Six originally unresolved rows are not promoted into the address hierarchy.'}
        for suffix, key in [('utf', 'jp-post-utf'), ('roman', 'jp-post-roman')]:
            relative = f'JP/sources/postal-{suffix}.zip'
            data['sources'][key] = {'provider': 'Japan Post', **SOURCES[relative],
                'licence': 'LicenseRef-JapanPost-Postal-Data',
                'terms': 'https://www.post.japanpost.jp/service/search/zipcode/download/' + ('utf-readme.html' if suffix == 'utf' else 'readme_ro.html')}
        data['romanization'] = {'method': METHOD, 'reference': REFERENCE,
            'code_sha256': digest((ROOT / 'romanize.py').read_bytes()),
            'storage_policy': 'Omit only exact source matches; retain literal exceptions. New conversions are generated_unreviewed.'}
    else:
        data['sources']['tw-chunghwa-names'] = {'provider': 'Chunghwa Post', **SOURCES['TW/sources/names.xml'],
            'catalogue': 'https://data.gov.tw/dataset/5949',
            'publication_date_source': 'https://www.post.gov.tw/post/internet/Download/index.jsp?ID=220306',
            'licence': 'Open Government Data License, version 1.0 (Taiwan)', 'terms': 'https://data.gov.tw/license',
            'note': 'Published source postal view. Three digits are prefixes, not complete six-digit codes; retrieval date is not a currentness guarantee.'}
    for path in sorted((folder / 'sources').iterdir()):
        raw = path.read_bytes()
        data['bundled_files'][str(path.relative_to(folder))] = {'bytes': len(raw), 'sha256': digest(raw)}
    write_json(folder / 'sources.json', data)


def build_jp(folder, gn_path=None):
    snapshot = json.loads(gzip.decompress((folder / 'sources/registry.json.gz').read_bytes()))
    native = zip_csv(folder / 'sources/postal-utf.zip', 'utf-8-sig', 15)
    roman = zip_csv(folder / 'sources/postal-roman.zip', 'cp932', 7)
    index = roman_index(roman)
    entities, lookup, names = [], {}, set()
    fields = ['entity_id', 'country', 'lg_code', 'jis_code', 'kind', 'parent_id', 'state_id',
              'native_name', 'address_name', 'address_candidate', 'source_ref', 'source_row',
              'source_effective_from', 'source_effective_to']
    def name(eid, lang, text, kind, ref):
        if text:
            names.add((eid, lang, text, kind, 'unspecified', ref))
    for p in snapshot['prefectures']:
        pref = p['prefecture']; r = pref['source_row']; pid = pref['id']; lg = pref['lg_code']
        if not valid_lg(lg):
            raise ValueError('Invalid prefecture LG code')
        entities.append(dict(zip(fields, [pid, 'JP', lg, lg[:5], 'prefecture', 'country:JP', pid,
            r['pref'], r['pref'], 'false', 'jp-abr-snapshot', p['path'] + '#prefecture', r['efct_date'], r['ablt_date']])))
        for suffix, lang, kind in [('', 'ja', 'source_label'), ('_kana', 'ja-Kana', 'reading'), ('_roma', 'ja-Latn', 'romanized')]:
            name(pid, lang, r['pref' + suffix], kind, 'jp-abr-snapshot')
        for local in p['localities']:
            r = local['source_row']; code = local['lg_code']; eid = local['id']
            if not valid_lg(code) or code[:5] != local['jis_code'] or code[:2] != lg[:2] or code[:5] in lookup:
                raise ValueError('Invalid or duplicate official code')
            lookup[code[:5]] = local
            entities.append(dict(zip(fields, [eid, 'JP', code, code[:5], local['category'], local['parent_id'],
                local['state_id'], r['ward'] or r['city'], r['county'] + r['city'] + r['ward'],
                str(local['address_candidate']).lower(), 'jp-abr-snapshot', p['path'] + '#lg_code=' + code,
                r['efct_date'], r['ablt_date']])))
            for suffix, lang, kind in [('', 'ja', 'source_label'), ('_kana', 'ja-Kana', 'reading'), ('_roma', 'ja-Latn', 'romanized')]:
                name(eid, lang, r[('ward' if r['ward'] else 'city') + suffix], kind, 'jp-abr-snapshot')
    variants = {'13381': ('三宅村', '三宅島三宅村'), '13401': ('八丈町', '八丈島八丈町'), '40344': ('糟屋郡須恵町', '糟屋郡須惠町')}
    postal, unresolved, statuses, storage = [], [], Counter(), Counter()
    pfields = ['association_id', 'country', 'scheme', 'code', 'code_kind', 'entity_id', 'jis_code',
        'prefecture_ja', 'municipality_ja', 'town_ja', 'prefecture_kana', 'municipality_kana', 'town_kana',
        'prefecture_roman', 'municipality_roman', 'town_roman', 'roman_language', 'roman_match_status',
        'roman_storage_modes', 'roman_method', 'roman_row', 'roman_truncation_possible', 'town_is_postal_instruction',
        'town_has_multiple_codes', 'numbering_by_subarea', 'has_chome', 'code_has_multiple_towns',
        'update_flag', 'change_reason', 'old_code', 'source_ref', 'source_row', 'roman_source_ref']
    for number, row in enumerate(native, 1):
        jis, code = row[0], row[2]
        if not re.fullmatch('[0-9]{5}', jis) or not re.fullmatch('[0-9]{7}', code) or jis not in lookup:
            raise ValueError('Unknown or malformed postal municipality/code')
        local = lookup[jis]; r = local['source_row']; eid = local['id']
        expected = r['county'] + r['city'] + r['ward']
        if row[6] != r['pref'] or (row[7] != expected and variants.get(jis) != (expected, row[7])):
            raise ValueError('Official code/name conflict: ' + jis)
        status, matches = roman_match(row, index); statuses[status] += 1
        rr = matches[0][1] if status == 'matched_unique' else None
        if not rr:
            unresolved.append({'source_row': number, 'jis_code': jis, 'code': code, 'municipality_ja': row[7],
                'town_ja': row[8], 'status': status, 'candidate_roman_rows': '|'.join(str(m[0]) for m in matches)})
        values, modes = [], []
        for j, role in enumerate(ROLES):
            value = rr[4 + j] if rr else ''
            omit = bool(value and convert(row[3 + j], row[6 + j], role) == value)
            values.append('' if omit else value)
            modes.append('algorithm' if omit else 'literal' if value else 'unavailable')
        storage.update(modes)
        truncated = bool(rr and (any(len(v) >= 17 for v in rr[2:4]) or any(len(v) >= 35 for v in rr[5:7])))
        instruction = row[8] == '以下に掲載がない場合' or row[8].endswith('一円') or 'の次に番地がくる場合' in row[8]
        postal.append(dict(zip(pfields, [key_id('jp-postal:', row[:9]), 'JP', 'JapanPost', code, 'full', eid, jis,
            *row[6:9], *row[3:6], *values, 'ja-Latn' if rr else '', status, '|'.join(modes), METHOD,
            str(matches[0][0]) if rr else '', str(truncated).lower(), str(instruction).lower(),
            *row[9:15], row[1], 'jp-post-utf', number, 'jp-post-roman' if rr else ''])))
        name(eid, 'ja', row[7], 'postal_address_label', 'jp-post-utf')
        name(eid, 'ja-Kana', row[4], 'postal_reading', 'jp-post-utf')
        if rr:
            name(eid, 'ja-Latn', rr[5], 'postal_romanized', 'jp-post-roman')
    ids = {e['entity_id'] for e in entities}
    if len(ids) != len(entities) or any(e['parent_id'] not in ids | {'country:JP'} for e in entities):
        raise ValueError('Invalid official hierarchy')
    candidates = geonames_candidates(entities, gn_path) if gn_path else []
    nfields = ['entity_id', 'language', 'text', 'kind', 'audience', 'source_ref']
    ufields = ['source_row', 'jis_code', 'code', 'municipality_ja', 'town_ja', 'status', 'candidate_roman_rows']
    cfields = ['entity_id', 'geonames_id', 'status', 'method', 'matched_name', 'official_jis_code']
    files = {}
    for filename, rows, columns in [('entities.csv.gz', entities, fields),
            ('names.csv.gz', [dict(zip(nfields, x)) for x in sorted(names)], nfields),
            ('postal_rows.csv.gz', postal, pfields), ('unresolved_roman.csv', unresolved, ufields),
            ('geonames_candidates.csv', candidates, cfields)]:
        files[filename] = write_csv(folder / filename, rows, columns)
    groups = defaultdict(set)
    for r in postal:
        groups[r['code']].add(r['entity_id'])
    report = {'country': 'JP', 'official_entities': len(entities), 'prefectures': len(snapshot['prefectures']),
        'municipalities_and_wards': len(lookup), 'postal_municipalities_and_wards': len({r['entity_id'] for r in postal}),
        'names': len(names), 'postal_source_rows': len(postal), 'roman_source_rows': len(roman),
        'unique_postcodes': len(groups), 'municipality_postcode_pairs': sum(len(v) for v in groups.values()),
        'postcodes_shared_by_multiple_entities': sum(len(v) > 1 for v in groups.values()),
        'roman_match_status': dict(statuses), 'roman_storage_fields': dict(storage), 'romanization_method': METHOD,
        'roman_truncation_possible': sum(r['roman_truncation_possible'] == 'true' for r in postal),
        'geonames_candidate_status': dict(Counter(r['status'] for r in candidates)),
        'official_geonames_crosswalks': 0, 'english_translation_claims': 0, 'business_postcodes_included': False,
        'files': files}
    source_metadata('JP', folder); write_json(folder / 'coverage.json', report)
    return report


def geonames_candidates(entities, path):
    with gzip.open(path, 'rt', encoding='utf-8', newline='') as file:
        rows = [r for r in csv.DictReader(file) if r['feature_code'] in {'ADM1', 'ADM2', 'ADM3', 'ADM4', 'ADM5'}]
    def aliases(row):
        return {row['name'], row.get('asciiname', ''), *row.get('alternatenames', '').split(',')}
    prefs = {}
    for e in entities:
        if e['kind'] == 'prefecture':
            matches = [r for r in rows if r['feature_code'] == 'ADM1' and e['native_name'] in aliases(r)]
            if len(matches) == 1:
                prefs[e['entity_id']] = matches[0]['admin1_code']
    result = []
    for e in entities:
        pref = prefs.get(e['state_id'])
        if not pref:
            continue
        for g in rows:
            if g['admin1_code'] != pref or (g['feature_code'] == 'ADM1') != (e['kind'] == 'prefecture'):
                continue
            matched = aliases(g) & {e['native_name'], e['address_name']}
            if not matched:
                continue
            code = e['kind'] != 'prefecture' and e['jis_code'] in [g.get(f'admin{i}_code') for i in range(2, 5)]
            result.append({'entity_id': e['entity_id'], 'geonames_id': g['id'],
                'status': 'candidate_code_and_name' if code else 'candidate_name_and_prefecture',
                'method': 'official_code+exact_alias+prefecture' if code else 'exact_alias+prefecture',
                'matched_name': sorted(matched)[0], 'official_jis_code': e['jis_code']})
    return sorted(result, key=lambda r: (r['entity_id'], r['geonames_id']))


def build_tw(folder):
    root = ET.fromstring((folder / 'sources/names.xml').read_bytes())
    entities, names, links = [], [], []
    for number, element in enumerate(root, 1):
        r = {x.tag: x.text for x in element}
        if set(r) != {'欄位1', '欄位2', '欄位3'} or not re.fullmatch('[0-9]{3}', r['欄位1'] or ''):
            raise ValueError('Chunghwa Post schema changed')
        code, native, english = [r[k] for k in ['欄位1', '欄位2', '欄位3']]
        if not native or not english:
            raise ValueError('Missing bilingual label')
        eid = key_id('tw-postal-area:', [native])
        entities.append({'entity_id': eid, 'country': 'TW', 'kind': 'postal_area', 'native_name': native,
                         'source_ref': 'tw-chunghwa-names', 'source_row': number})
        for language, text in [('zh-Hant', native), ('en', english)]:
            names.append({'entity_id': eid, 'language': language, 'text': text, 'kind': 'postal_authority_label',
                          'audience': 'unspecified', 'source_ref': 'tw-chunghwa-names', 'source_row': number})
        links.append({'entity_id': eid, 'country': 'TW', 'scheme': 'ChunghwaPost', 'code': code, 'code_kind': 'prefix',
                      'prefix_length': 3, 'complete_code_length': 6, 'source_ref': 'tw-chunghwa-names', 'source_row': number})
    if len({r['entity_id'] for r in entities}) != len(entities):
        raise ValueError('Duplicate postal area label')
    files = {name: write_csv(folder / name, rows, list(rows[0])) for name, rows in
             [('entities.csv', entities), ('names.csv', names), ('postal_links.csv', links)]}
    codes = Counter(r['code'] for r in links)
    report = {'country': 'TW', 'postal_areas': len(entities), 'official_bilingual_pairs': len(entities),
        'names': len(names), 'postal_links': len(links), 'unique_three_digit_prefixes': len(codes),
        'prefixes_shared_by_multiple_source_areas': {k: v for k, v in codes.items() if v > 1},
        'complete_six_digit_links': 0, 'official_administrative_code_crosswalks': 0, 'files': files}
    source_metadata('TW', folder); write_json(folder / 'coverage.json', report)
    return report


def verify(folder):
    report = json.loads((folder / 'coverage.json').read_text()); sources = json.loads((folder / 'sources.json').read_text())
    for path, info in {**report['files'], **sources['bundled_files']}.items():
        raw = (folder / path).read_bytes()
        if len(raw) != info['bytes'] or digest(raw) != info['sha256']:
            raise ValueError('Checksum mismatch: ' + path)
    if folder.name == 'JP' and sources['romanization']['code_sha256'] != digest((ROOT / 'romanize.py').read_bytes()):
        raise ValueError('Romanization implementation changed: rebuild and replay required')
    return {'country': folder.name, 'checksums': 'passed'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['build', 'verify'])
    parser.add_argument('--country', choices=['JP', 'TW'], required=True)
    parser.add_argument('--geonames-jp', type=Path)
    args = parser.parse_args(); folder = ROOT / args.country
    report = verify(folder) if args.action == 'verify' else build_jp(folder, args.geonames_jp) if args.country == 'JP' else build_tw(folder)
    print(json.dumps({k: v for k, v in report.items() if k != 'files'}, ensure_ascii=False, indent=2))
