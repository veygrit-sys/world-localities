#!/usr/bin/env python3
"""Import and replay pinned Hong Kong ALS district 2D address observations.

The original ZIP is retained unchanged. The optional public-housing 3D member is
not parsed or included in this layer. Observation IDs identify rows in a pinned
source member, whereas the original CSU identifier identifies a building.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import zipfile

SOURCE_URL = 'https://www.als.gov.hk/data/ALS-GeoJSON.zip'
CATALOGUE_URL = 'https://data.gov.hk/en-data/dataset/hk-dpo-als_01-als/resource/92eed8bd-9e6f-4aac-9c9a-5ea6f5dbb4b8'
SCHEMA_URL = 'https://www.als.gov.hk/docs/als-geojson.schema.json'
TERMS_URL = 'https://data.gov.hk/en/terms-and-conditions'
SOURCE_ID = 'hk-dpo-als-district-2d'
RAW_NAME = 'sources/ALS-GeoJSON.zip'
SCOPE = ('All district 2D GeoJSON members in the pinned archive; optional public-housing 3D member excluded. '
         'Observation rows are not unique addresses.')
CLAIMS = {'national_completeness_verified': False, 'freshness_verified': False,
          'deliverability_verified': False, 'all_current_buildings_verified': False,
          'all_floor_unit_addresses_verified': False, 'optional_3d_layer_verified': False}
COLUMNS = ['observation_id', 'country', 'csu_id', 'geo_address', 'source_member', 'source_row',
           'feature_sha256', 'native_region', 'native_district', 'native_street', 'native_village',
           'native_building_name', 'english_region', 'english_district', 'english_street',
           'english_village', 'english_building_name', 'coordinate_status', 'longitude', 'latitude',
           'hk1980_easting', 'hk1980_northing', 'feature_json']
SEARCH_FIELDS = ['csu_id', 'geo_address', 'native_region', 'native_district', 'native_street',
                 'native_village', 'native_building_name', 'english_region', 'english_district',
                 'english_street', 'english_village', 'english_building_name', 'feature_json']
MAX_DISTRICT_BYTES = 100_000_000
MAX_SOURCE_ROWS = 1_000_000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def file_spec(path, **extra):
    content = Path(path).read_bytes()
    return {'bytes': len(content), 'sha256': digest(content), **extra}


def text(value, label):
    require(isinstance(value, str), label + ' must remain a source string')
    return value


def validate_number_strings(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {'BuildingNoFrom', 'BuildingNoTo'}:
                text(item, key)
            validate_number_strings(item)
    elif isinstance(value, list):
        for item in value:
            validate_number_strings(item)


def numeric(value, label):
    require(type(value) in {int, float} and math.isfinite(value), label + ' must be a finite number')
    return str(value)


def normalize_feature(feature, member, row):
    require(isinstance(feature, dict) and feature.get('type') == 'Feature', 'invalid source feature')
    require(type(row) is int and row >= 1, 'source row must be one-based')
    properties = feature['properties']
    premises = properties['Address']['PremisesAddress']
    csu = text(premises['BuildingCsuInformation']['CsuId'], 'CsuId')
    require(re.fullmatch(r'[0-9]{10}[PT][0-9]{8}', csu) is not None, 'invalid CSU identifier')
    chi, eng = premises['ChiPremisesAddress'], premises['EngPremisesAddress']
    require(isinstance(chi, dict) and isinstance(eng, dict), 'missing bilingual premises structure')
    validate_number_strings(feature)
    feature_json = canonical(feature)
    record = dict.fromkeys(COLUMNS, '')
    record.update(observation_id='hk:als:obs:' + digest((member + '\0' + str(row)).encode('utf-8')),
                  country='HK', csu_id=csu, geo_address=text(premises.get('GeoAddress', ''), 'GeoAddress'),
                  source_member=member, source_row=str(row), feature_sha256=digest(feature_json.encode('utf-8')),
                  feature_json=feature_json)
    for prefix, source, language in [('native', chi, 'Chi'), ('english', eng, 'Eng')]:
        record[prefix + '_region'] = text(source['Region'], language + ' Region')
        record[prefix + '_district'] = text(source[language + 'District'], language + ' District')
        record[prefix + '_street'] = text(source.get(language + 'Street', {}).get('StreetName', ''), 'StreetName')
        record[prefix + '_village'] = text(source.get(language + 'Village', {}).get('VillageName', ''), 'VillageName')
        record[prefix + '_building_name'] = text(source.get('BuildingName', ''), 'BuildingName')
    geometry = feature.get('geometry')
    coordinates = geometry.get('coordinates') if isinstance(geometry, dict) else None
    if coordinates is not None:
        require(geometry.get('type') == 'Point' and isinstance(coordinates, list) and len(coordinates) == 2,
                'invalid WGS84 point')
        lon, lat = coordinates
        record['longitude'] = numeric(lon, 'longitude')
        record['latitude'] = numeric(lat, 'latitude')
        require(-180 <= lon <= 180 and -90 <= lat <= 90, 'WGS84 coordinate outside valid range')
        record['coordinate_status'] = 'source_coordinate'
    else:
        record['coordinate_status'] = 'not_supplied_by_source'
    for source, target in [('Easting', 'hk1980_easting'), ('Northing', 'hk1980_northing')]:
        if source in properties:
            record[target] = numeric(properties[source], source)
    return record


def source_members(archive):
    names = archive.namelist()
    require(len(names) == len(set(names)), 'duplicate source ZIP member')
    for name in names:
        path = PurePosixPath(name)
        require(not path.is_absolute() and '..' not in path.parts and '\\' not in name,
                'unsafe source ZIP member')
    selected = sorted(name for name in names
                      if re.fullmatch(r'[^/]+/als_addresses_\([^/]+_district\)\.geojson', name))
    require(selected, 'source contains no district 2D members')
    for name in selected:
        require(archive.getinfo(name).file_size <= MAX_DISTRICT_BYTES, 'district source exceeds size limit')
    return selected


def source_rows(source, receipts=None):
    total = 0
    with zipfile.ZipFile(source) as archive:
        selected = source_members(archive)
        for name in selected:
            raw = archive.read(name)
            doc = json.loads(raw.decode('utf-8-sig'))
            require(doc.get('type') == 'FeatureCollection' and isinstance(doc.get('features'), list),
                    'invalid district FeatureCollection')
            if receipts is not None:
                receipts[name] = {'bytes': len(raw), 'sha256': digest(raw), 'rows': len(doc['features']),
                                  'zip_timestamp': list(archive.getinfo(name).date_time)}
            for row, feature in enumerate(doc['features'], 1):
                total += 1
                require(total <= MAX_SOURCE_ROWS, 'source exceeds row limit')
                yield normalize_feature(feature, name, row)


def counts_for(rows):
    csus = Counter(row['csu_id'] for row in rows)
    return {'source_observations': len(rows), 'unique_csu_ids': len(csus),
            'csu_ids_with_multiple_observations': sum(value > 1 for value in csus.values()),
            'maximum_observations_per_csu': max(csus.values(), default=0),
            'rows_without_source_coordinates': sum(row['coordinate_status'] == 'not_supplied_by_source' for row in rows),
            'native_districts': len({row['native_district'] for row in rows}),
            'source_members': len({row['source_member'] for row in rows})}


def build(source, output, schema=None, terms=None, retrieved_at=None):
    source, output = Path(source), Path(output)
    require(not output.exists() and not output.is_symlink(), 'output must not already exist')
    receipts = {}
    rows = list(source_rows(source, receipts))
    counts = counts_for(rows)
    observed = retrieved_at or datetime.now(timezone.utc).isoformat()
    output.mkdir(parents=True)
    (output / 'sources').mkdir()
    shutil.copyfile(source, output / RAW_NAME)
    with (output / 'records.csv.gz').open('wb') as binary:
        with gzip.GzipFile(filename='', mode='wb', fileobj=binary, mtime=0) as compressed:
            with io.TextIOWrapper(compressed, encoding='utf-8', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=COLUMNS, lineterminator='\n')
                writer.writeheader()
                writer.writerows(rows)
    bundled = {RAW_NAME: file_spec(output / RAW_NAME)}
    for value, name in [(schema, 'sources/als-geojson.schema.json'), (terms, 'sources/data-gov-hk-terms.html')]:
        if value is not None:
            shutil.copyfile(value, output / name)
            bundled[name] = file_spec(output / name)
    with zipfile.ZipFile(source) as archive:
        excluded = {i.filename: {'bytes': i.file_size, 'zip_timestamp': list(i.date_time),
                                  'reason': 'optional 3D member is preserved in ZIP but not parsed or normalized'}
                    for i in archive.infolist() if not i.is_dir() and i.filename not in receipts}
    raw_spec = file_spec(source)
    source_spec = {'provider': 'Hong Kong Digital Policy Office / Address Lookup Service',
                   'url': SOURCE_URL, 'catalogue': CATALOGUE_URL, 'schema': SCHEMA_URL,
                   'retrieved_at': observed, 'source_date': '2026-10-23',
                   'source_date_meaning': 'catalogue resource last update; not attestation of each address currentness',
                   'license': 'DATA.GOV.HK terms and conditions; no SPDX identifier assigned',
                   'terms': TERMS_URL, 'source_bytes': raw_spec['bytes'], 'source_sha256': raw_spec['sha256'],
                   'selected_members': receipts, 'excluded_members': excluded, 'scope': SCOPE}
    write_json(output / 'sources.json', {'schema_version': 1, 'country': 'HK',
                                       'sources': {SOURCE_ID: source_spec}, 'bundled_files': bundled})
    write_json(output / 'coverage.json', {'schema_version': 1, 'country': 'HK',
        'layer_kind': 'official_bilingual_building_address_observations', 'scope': SCOPE,
        'rows': len(rows), 'counts': counts, 'retrieved_at': observed, 'source_date': '2026-10-23',
        'record_file': 'records.csv.gz', 'search_fields': SEARCH_FIELDS,
        'files': {'records.csv.gz': file_spec(output / 'records.csv.gz', rows=len(rows), columns=COLUMNS)},
        'claims': CLAIMS,
        'identifier_semantics': 'CSU identifies a building; observation IDs identify one-based rows in pinned source members',
        'known_issues': ['Two observations in the pinned 2026-10 source do not supply coordinates; retained without inference.',
                         'Multiple observations can share a CSU identifier. Counts are not unique addresses.',
                         'Empty English fields remain empty; Chinese street names are never substituted.',
                         'Optional public-rental-housing 3D member is not normalized; no floor/unit coverage claim.']})
    return {'country': 'HK', 'status': 'built', 'rows': len(rows), 'counts': counts,
            'records': file_spec(output / 'records.csv.gz')}


def managed(folder, name):
    require(isinstance(name, str) and name and '\\' not in name and ':' not in name, 'unsafe managed path')
    relative = PurePosixPath(name)
    require(not relative.is_absolute() and '..' not in relative.parts, 'unsafe managed path')
    path = folder / relative
    require(not path.is_symlink() and path.resolve().is_relative_to(folder.resolve()), 'unsafe managed file')
    return path


def read_records(folder):
    csv.field_size_limit(1_000_000)
    with gzip.open(folder / 'records.csv.gz', 'rt', encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == COLUMNS, 'derived CSV columns differ')
        for row in reader:
            require(None not in row and all(value is not None for value in row.values()), 'invalid CSV row')
            yield row


def verify(folder, source_path=None):
    folder = Path(folder)
    coverage = json.loads((folder / 'coverage.json').read_text(encoding='utf-8'))
    sources = json.loads((folder / 'sources.json').read_text(encoding='utf-8'))
    require(coverage['country'] == sources['country'] == 'HK', 'country mismatch')
    require(coverage['record_file'] == 'records.csv.gz' and coverage['search_fields'] == SEARCH_FIELDS,
            'unsupported search schema')
    require(coverage['claims'] == CLAIMS and coverage['scope'] == SCOPE, 'unsupported scope or quality claims')
    require(set(coverage['files']) == {'records.csv.gz'}, 'unexpected derived file')
    for name, info in {**coverage['files'], **sources['bundled_files']}.items():
        path = managed(folder, name)
        actual = file_spec(path)
        require(actual['bytes'] == info['bytes'] and actual['sha256'] == info['sha256'], 'checksum mismatch: ' + name)
    rows = list(read_records(folder))
    require(type(coverage['rows']) is int and len(rows) == coverage['rows'], 'row count mismatch')
    spec = coverage['files']['records.csv.gz']
    require(spec['columns'] == COLUMNS and spec['rows'] == len(rows), 'CSV schema or row count mismatch')
    ids = set()
    for row in rows:
        require(row['country'] == 'HK', 'row country mismatch')
        require(row['source_row'].isdigit() and int(row['source_row']) >= 1, 'invalid source row')
        expected = normalize_feature(json.loads(row['feature_json']), row['source_member'], int(row['source_row']))
        require(row == expected, 'normalized feature row mismatch')
        require(row['observation_id'] not in ids, 'duplicate observation identifier')
        ids.add(row['observation_id'])
    counts = counts_for(rows)
    require(coverage['counts'] == counts, 'coverage counts mismatch')
    source_spec = sources['sources'][SOURCE_ID]
    source = Path(source_path) if source_path is not None else folder / RAW_NAME
    replay = 'not_run_raw_source_not_available'
    if source.exists():
        receipt = file_spec(source)
        require(receipt['bytes'] == source_spec['source_bytes'] and receipt['sha256'] == source_spec['source_sha256'],
                'original source receipt mismatch')
        replay_receipts = {}
        replay_rows = source_rows(source, replay_receipts)
        for actual in rows:
            require(next(replay_rows, None) == actual, 'source row replay mismatch')
        require(next(replay_rows, None) is None, 'unreplayed source rows')
        require(replay_receipts == source_spec['selected_members'], 'source member receipt mismatch')
        replay = 'passed_all_selected_district_2d_source_rows'
    return {'country': 'HK', 'status': 'passed', 'source_integrity': 'passed' if source.exists() else 'saved_receipts_only',
            'row_integrity': 'passed', 'rows': len(rows), 'counts': counts, 'source_replay': replay,
            'source_sha256': source_spec['source_sha256'], 'records_sha256': spec['sha256'],
            'scope': SCOPE, 'national_completeness_verified': False, 'freshness_verified': None,
            'deliverability_verified': False, 'optional_3d_layer_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('build')
    create.add_argument('--source', type=Path, required=True)
    create.add_argument('--output', type=Path, required=True)
    create.add_argument('--schema', type=Path)
    create.add_argument('--terms', type=Path)
    create.add_argument('--retrieved-at')
    check = commands.add_parser('verify')
    check.add_argument('--folder', type=Path, required=True)
    check.add_argument('--source', type=Path)
    args = parser.parse_args()
    try:
        report = (build(args.source, args.output, args.schema, args.terms, args.retrieved_at)
                  if args.command == 'build' else verify(args.folder, args.source))
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, UnicodeError, csv.Error, zipfile.BadZipFile) as error:
        parser.exit(1, 'Hong Kong official import failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
