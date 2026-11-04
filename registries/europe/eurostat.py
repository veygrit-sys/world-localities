#!/usr/bin/env python3
"""Import a pinned official LAU list; never confuse statistical and administrative parents."""
import argparse
import csv
import gzip
import io
import json
import re
from collections import Counter
from pathlib import Path
from build import ROOT, check, compressed, csv_bytes, download, jdump, sha, write_json

URL = ('https://ec.europa.eu/eurostat/documents/345175/501971/'
       'EU-27-LAU-2025-NUTS-2024.xlsx/574c9e4a-2dae-99fe-5510-3fd18d8e90c2?t=1771601900130')
FILENAME = 'lau-2025.xlsx'
RELEASE = '2025'
NUTS_RELEASE = '2024'
FIELDS = ('id country source_country lau_code source_lau_code eu_lau_code '
          'name_national name_latin statistical_parent_id nuts3_code '
          'source_period source_change source_sheet source_row source_validation quality_flags_json').split()
REGION_FIELDS = 'id country source_code level parent_id relation name_status'.split()
FIRST_HEADERS = ['PERIOD','NUTS3','LAU CODE','EU LAU CODE','LAU NAME NATIONAL','LAU NAME LATIN']


def string(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def transform(values, source_country, source_row, validation):
    raw = [string(v) for v in values]
    check(len(raw) >= 7, 'missing LAU columns')
    period, nuts, local, eu, national, latin, change = raw[:7]
    check(eu.startswith(source_country + '_'), 'EU LAU country prefix differs')
    code = eu[len(source_country) + 1:]
    check(bool(code) and bool(national.strip()), 'missing LAU identity/name')
    check(re.fullmatch(re.escape(source_country) + r'[A-Z0-9]{3}', nuts), 'invalid NUTS3 code')
    cc = 'GR' if source_country == 'EL' else source_country
    flags = ['statistical_parent_not_administrative_parent',
             'release_2025_not_current_2026_municipality_register',
             'latin_label_not_verified_english_translation']
    if local != code:
        flags.append('source_lau_cell_differs_from_eu_code_suffix')
    if validation.get('core') != 'validated':
        flags.append('source_core_not_validated')
    return dict(id='eurostat:lau:' + RELEASE + ':' + eu, country=cc,
                source_country=source_country, lau_code=code, source_lau_code=local,
                eu_lau_code=eu, name_national=national, name_latin=latin,
                statistical_parent_id='eurostat:nuts:' + NUTS_RELEASE + ':' + nuts,
                nuts3_code=nuts, source_period=period, source_change=change,
                source_sheet=source_country, source_row=str(source_row),
                source_validation=validation.get('core', ''), quality_flags_json=jdump(flags))


def region_rows(rows, cc):
    codes = set()
    for row in rows:
        nuts = row['nuts3_code']
        codes.update(nuts[:n] for n in (3,4,5))
    result = []
    for code in sorted(codes):
        level = len(code) - 2
        parent = 'country:' + cc if level == 1 else 'eurostat:nuts:' + NUTS_RELEASE + ':' + code[:-1]
        result.append(dict(id='eurostat:nuts:' + NUTS_RELEASE + ':' + code,
                           country=cc, source_code=code, level=str(level), parent_id=parent,
                           relation='statistical_code_prefix', name_status='not_loaded'))
    return result


def parse_workbook(path):
    import openpyxl
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    validation = {}
    for values in book['Overview'].values:
        v = list(values)
        cc = string(v[0]).strip()
        if re.fullmatch(r'[A-Z]{2}', cc):
            validation[cc] = dict(core=string(v[6]), overall=string(v[11]),
                                  population_and_area='not_validated_by_Eurostat')
    file_info = [[string(c) for c in row] for row in book['File_info'].values if any(c is not None for c in row)]
    output = {}
    for sheet in book:
        cc = sheet.title
        if not re.fullmatch(r'[A-Z]{2}', cc):
            continue
        iterator = sheet.iter_rows(values_only=True)
        headers = [string(x).strip() for x in next(iterator)]
        check(headers[:6] == FIRST_HEADERS, cc + ' workbook schema changed')
        rows, skipped = [], 0
        for rownum, values in enumerate(iterator, 2):
            if not any(v is not None and string(v).strip() for v in values[:7]):
                skipped += 1
                continue
            rows.append(transform(values, cc, rownum, validation.get(cc, {})))
        ids = [r['id'] for r in rows]
        check(len(ids) == len(set(ids)), cc + ' duplicate EU LAU code; review source before import')
        country = 'GR' if cc == 'EL' else cc
        output[country] = dict(rows=rows, source_sheet=cc,
                               validation=validation.get(cc, {}), skipped_empty_rows=skipped)
    book.close()
    return output, file_info


def build(inputs, root=ROOT):
    source = download(inputs, FILENAME, URL)
    result, file_info = parse_workbook(inputs / FILENAME)
    out = root / 'eurostat-lau'
    out.mkdir(exist_ok=True)
    write_json(out / 'source.json', dict(source, release_label=RELEASE,
        nuts_release=NUTS_RELEASE, file_info=file_info,
        reuse_policy='https://ec.europa.eu/eurostat/help/copyright-notice',
        reference_page='https://ec.europa.eu/eurostat/web/nuts/local-administrative-units',
        limitation='Pinned 2025 list; source row PERIOD is preserved separately. Some national units are not municipal governments.'))
    countries, empty = [], []
    for cc, item in sorted(result.items()):
        rows = item.pop('rows')
        if not rows:
            empty.append(dict(country=cc, **item))
            continue
        folder = out / cc
        folder.mkdir(exist_ok=True)
        payload = compressed(csv_bytes(rows, FIELDS))
        regions = csv_bytes(region_rows(rows, cc), REGION_FIELDS)
        (folder / 'units.csv.gz').write_bytes(payload)
        (folder / 'statistical_regions.csv').write_bytes(regions)
        meta = dict(country=cc, release_label=RELEASE, nuts_release=NUTS_RELEASE,
                    rows=len(rows), **item,
                    source_sha256=source['sha256'], source_period_counts=dict(Counter(r['source_period'] for r in rows)),
                    files={'units.csv.gz': dict(sha256=sha(payload), rows=len(rows), bytes=len(payload)),
                           'statistical_regions.csv':dict(sha256=sha(regions),rows=len(region_rows(rows,cc)),bytes=len(regions))},
                    limitations=['national_and_latin_labels_are_source_claims',
                                 'statistical_not_government_hierarchy',
                                 'no_automatic_join_to_geonames',
                                 'no_postcode_or_address1_association'])
        write_json(folder / 'metadata.json', meta)
        countries.append(dict(country=cc, rows=len(rows), core_validation=item['validation'].get('core',''),
                              metadata_sha256=sha((folder/'metadata.json').read_bytes())))
        print(jdump(countries[-1]),flush=True)
    write_json(out/'manifest.json',dict(release_label=RELEASE,nuts_release=NUTS_RELEASE,
        total_rows=sum(x['rows'] for x in countries),country_count=len(countries),countries=countries,
        empty_source_sheets=empty,source_sha256=source['sha256'],
        note='No units invented for empty/missing national sheets. Counts overlap GeoNames and existing official registries.'))
    verify(root)


def verify(root=ROOT, inputs=None):
    out = root / 'eurostat-lau'
    manifest = json.loads((out/'manifest.json').read_text())
    expected = parse_workbook(inputs / FILENAME)[0] if inputs else None
    seen, reports = set(), []
    source = json.loads((out/'source.json').read_text())
    check(manifest['source_sha256'] == source['sha256'], 'LAU manifest/source hash mismatch')
    if inputs:
        check(sha((inputs/FILENAME).read_bytes()) == source['sha256'], 'LAU workbook hash mismatch')
    for item in manifest['countries']:
        cc = item['country']
        folder = out / cc
        check(sha((folder/'metadata.json').read_bytes()) == item['metadata_sha256'], 'LAU metadata hash mismatch')
        meta = json.loads((folder/'metadata.json').read_text())
        for name, part in meta['files'].items():
            check(name in ('units.csv.gz','statistical_regions.csv'),'LAU unexpected filename')
            data = (folder/name).read_bytes()
            check(sha(data)==part['sha256'] and len(data)==part['bytes'], 'LAU file hash/bytes mismatch')
        reader = csv.DictReader(io.StringIO(gzip.decompress((folder/'units.csv.gz').read_bytes()).decode()))
        check(reader.fieldnames == FIELDS, 'LAU columns mismatch')
        rows = list(reader)
        ids = {r['id'] for r in rows}
        check(len(rows)==len(ids)==item['rows']==meta['rows'], 'LAU row/duplicate mismatch')
        check(not seen.intersection(ids), 'cross-country duplicate LAU')
        seen.update(ids)
        regions = region_rows(rows, cc)
        check((folder/'statistical_regions.csv').read_bytes()==csv_bytes(regions,REGION_FIELDS),'LAU statistical regions differ')
        parents={r['id'] for r in regions}
        for r in rows:
            check(r['country']==cc and r['statistical_parent_id'] in parents,'LAU parent mismatch')
            rebuilt=transform([r['source_period'],r['nuts3_code'],r['source_lau_code'],r['eu_lau_code'],
                               r['name_national'],r['name_latin'],r['source_change']],
                              r['source_sheet'],int(r['source_row']),meta['validation'])
            check(r==rebuilt,'LAU derived fields differ')
        if expected is not None:
            check(rows == expected[cc]['rows'], 'LAU workbook replay differs')
        reports.append(dict(country=cc,rows=len(rows),status='pass'))
    check(len(seen)==manifest['total_rows'] and len(reports)==manifest['country_count'],'LAU manifest totals differ')
    report=dict(status='pass',errors=0,countries=len(reports),rows=len(seen),reports=reports,
                source_workbook_replay='exact' if inputs else 'not_run',
                note='Structural and source-preservation checks, not new Eurostat validation.')
    write_json(out/'verification.json',report)
    print(jdump({k:v for k,v in report.items() if k!='reports'}),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['build','verify'])
    parser.add_argument('--inputs',type=Path)
    args=parser.parse_args()
    if args.command=='build':
        build(args.inputs or ROOT/'source-cache')
    else:
        verify(inputs=args.inputs)
