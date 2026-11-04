"""Fetch and stream the content-pinned INEGI / Digital Guard Mexico address CSV."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile, BadZipFile

SOURCE_SHA256 = '090735bf608a3202a141da670d960a05dbe464893ba49208fc37c30485f5bedc'
SOURCE_BYTES = 683565189
SOURCE_URL = 'https://dl.digital-guard.org/' + SOURCE_SHA256 + '.zip'
SOURCE_ID = 'digital-guard-inegi-mx-pk0002.01-geoaddress'
MEMBER = 'produto_final.csv'
COLUMNS = ['gid', 'estado', 'cidade', 'via', 'hnum', 'nsvia', 'latitude', 'longitude', 'postcode']
NUMBER_PLACEHOLDERS = {'SN', 'S/N', 'SIN NUMERO', 'SIN NÚMERO'}
REVIEW_EXTENT = [-119, 14, -86, 33]


def source_metadata():
    return {
        'source_id': SOURCE_ID, 'url': SOURCE_URL, 'bytes': SOURCE_BYTES,
        'sha256': SOURCE_SHA256,
        'source_metadata_url': 'https://github.com/digital-guard/preserv-MX/tree/main/data/_pk0002.01',
        'upstream_recipe': 'https://github.com/openaddresses/openaddresses/blob/master/sources/mx/countrywide.json',
        'preservation_metadata_acquisition_date': '2023-08-16',
        'attribution': 'INEGI Instituto Nacional de Estadística y Geografía; preserved by Digital Guard / AddressForAll',
        'licence_name': 'INEGI TERMS OF FREE USE OF INFORMATION',
        'licence_evidence_url': 'https://dl.digital-guard.org/647a8f64ed703b93ecc541f39fb7c08dbe445cb704ee78e69036ce5ef711b8a4.pdf',
        'national_completeness_verified': False, 'issuing_authority_assignment_verified': False,
        'deliverability_in_scope': False,
        'identity_note': 'gid is the preserved CSV row key, not an official INEGI administrative or address identifier.',
        'parent_note': 'estado, cidade and nsvia retain source labels; no legal administrative parent links are inferred.',
    }


def verify_archive(path, expected_sha256=SOURCE_SHA256, expected_bytes=SOURCE_BYTES):
    path = Path(path)
    if path.stat().st_size != expected_bytes:
        raise ValueError('Source byte count mismatch')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != expected_sha256:
        raise ValueError('Content-addressed source SHA-256 mismatch')
    with ZipFile(path) as archive:
        if archive.namelist() != [MEMBER]:
            raise ValueError('Unexpected source archive members')
    return path


def acquire(output):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('Use a new source output')
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + '.part')
    with urlopen(SOURCE_URL, timeout=60) as response, temporary.open('xb') as target:
        for block in iter(lambda: response.read(1024 * 1024), b''):
            target.write(block)
    verify_archive(temporary)
    if output.exists():
        raise ValueError('Source output appeared during acquisition')
    temporary.replace(output)
    receipt = {**source_metadata(), 'retrieved_at': datetime.now(timezone.utc).isoformat()}
    output.with_suffix('.receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt


class DigestReader(io.RawIOBase):
    def __init__(self, source, digest):
        super().__init__()
        self.source, self.digest = source, digest

    def readable(self):
        return True

    def readinto(self, buffer):
        block = self.source.read(len(buffer))
        buffer[:len(block)] = block
        self.digest.update(block)
        return len(block)


def rows(path, digest=None):
    import csv
    with ZipFile(path) as archive, archive.open(MEMBER) as source:
        binary = io.BufferedReader(DigestReader(source, digest)) if digest is not None else source
        with io.TextIOWrapper(binary, encoding='utf-8-sig', newline='') as text:
            reader = csv.DictReader(text)
            if reader.fieldnames != COLUMNS:
                raise ValueError('Source CSV columns changed')
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError('Malformed source CSV record')
                yield row


def inspect(path):
    verify_archive(path)
    counts = Counter()
    regions = defaultdict(Counter)
    cities = defaultdict(set)
    bounds = [math.inf, math.inf, -math.inf, -math.inf]
    digest = hashlib.sha256()
    sequential = True
    for row in rows(path, digest):
        counts['source_rows'] += 1
        sequential = sequential and row['gid'] == str(counts['source_rows'])
        number = row['hnum'].strip()
        placeholder = number.upper() in NUMBER_PLACEHOLDERS
        counts['nonempty_number_strings'] += bool(number)
        counts['number_placeholder_rows'] += placeholder
        counts['empty_number_rows'] += not number
        counts['nonplaceholder_number_rows'] += bool(number) and not placeholder
        counts['empty_street_rows'] += not row['via'].strip()
        counts['NINGUNO_street_rows'] += row['via'].strip().upper() == 'NINGUNO'
        counts['empty_postcode_rows'] += not row['postcode']
        counts['empty_estado_rows'] += not row['estado']
        counts['empty_cidade_rows'] += not row['cidade']
        region = regions[row['estado']]
        region['source_rows'] += 1
        region['nonplaceholder_number_rows'] += bool(number) and not placeholder
        cities[row['estado']].add(row['cidade'])
        try:
            longitude, latitude = float(row['longitude']), float(row['latitude'])
            valid = math.isfinite(longitude) and math.isfinite(latitude) and -180 <= longitude <= 180 and -90 <= latitude <= 90
        except ValueError:
            valid = False
        if valid:
            bounds = [min(bounds[0], longitude), min(bounds[1], latitude), max(bounds[2], longitude), max(bounds[3], latitude)]
            counts['world_valid_points_outside_broad_mexico_extent'] += not (REVIEW_EXTENT[0] <= longitude <= REVIEW_EXTENT[2] and REVIEW_EXTENT[1] <= latitude <= REVIEW_EXTENT[3])
        else:
            counts['invalid_or_missing_coordinate_rows'] += 1
        if counts['source_rows'] % 1000000 == 0:
            print(json.dumps({'status': 'SCANNING', 'rows': counts['source_rows']}), flush=True)
    return {
        'status': 'SOURCE_CSV_FULLY_READ_CRC_CHECKED', 'source': source_metadata(),
        'checked_at': datetime.now(timezone.utc).isoformat(), 'counts': dict(counts),
        'uncompressed_csv_sha256': digest.hexdigest(), 'gid_sequential_from_one': sequential,
        'gid_uniqueness_verified': True if sequential else None,
        'coordinate_bounds_wgs84': bounds if all(math.isfinite(value) for value in bounds) else None,
        'coordinate_review_extent_wgs84': REVIEW_EXTENT,
        'review_extent_is_legal_boundary_test': False,
        'regions_by_original_label': [{'estado': name, **dict(values), 'distinct_cidade_labels': len(cities[name])} for name, values in sorted(regions.items())],
        'all_source_rows_retained': True, 'number_ranges_or_suffixes_expanded': False,
        'national_completeness_verified': False, 'issuing_authority_assignment_verified': False,
        'deliverability_in_scope': False,
    }


def query(path, state=None, city=None, text=None, gid=None, limit=20):
    if not 1 <= limit <= 100:
        raise ValueError('Limit must be between 1 and 100')
    verify_archive(path)
    results = []
    for row in rows(path):
        if state is not None and row['estado'].casefold() != state.casefold(): continue
        if city is not None and row['cidade'].casefold() != city.casefold(): continue
        if gid is not None and row['gid'] != gid: continue
        if text is not None and not any(text.casefold() in row[field].casefold() for field in ('via', 'hnum', 'nsvia')): continue
        results.append({'id': SOURCE_ID + ':row:' + row['gid'], 'original': row})
        if len(results) >= limit: break
    return {'source_id': SOURCE_ID, 'results': results, 'national_completeness_verified': False,
            'issuing_authority_assignment_verified': False, 'deliverability_in_scope': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    fetch = commands.add_parser('fetch'); fetch.add_argument('--output', type=Path, required=True)
    check = commands.add_parser('inspect'); check.add_argument('--archive', type=Path, required=True); check.add_argument('--output', type=Path, required=True)
    find = commands.add_parser('query'); find.add_argument('--archive', type=Path, required=True)
    find.add_argument('--state'); find.add_argument('--city'); find.add_argument('--text'); find.add_argument('--gid'); find.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    try:
        if args.command == 'fetch': report = acquire(args.output)
        elif args.command == 'inspect':
            report = inspect(args.archive)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        else: report = query(args.archive, args.state, args.city, args.text, args.gid, args.limit)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, BadZipFile) as error:
        parser.exit(2, str(error) + '\n')


if __name__ == '__main__': main()
