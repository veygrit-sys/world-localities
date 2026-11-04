"""Acquire and import the official 202609 Sejong Korean road-name address pilot."""
from __future__ import annotations

import argparse
import binascii
import csv
from datetime import date, datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import struct
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import zlib

SOURCE_ID = 'kr-juso-sejong-korean-addresses'
MEMBER = 'rnaddrkor_sejong.txt'
RAW_NAME = 'sources/rnaddrkor_sejong.txt.gz'
SOURCE_MONTH = '202609'
CATALOGUE_URL = 'https://www.data.go.kr/data/15050417/fileData.do'
CATALOGUE_METADATA_URL = 'https://www.data.go.kr/catalog/15050417/fileData.json'
DOWNLOAD_PAGE = 'https://business.juso.go.kr/jst/jstAddressDownload'
TERMS_URL = 'https://www.data.go.kr/ugs/selectPortalPolicyView.do'
LICENSE = '이용허락범위 제한 없음'
GUIDE_URL = 'https://business.juso.go.kr/api/jst/download?' + urlencode({
    'reqType': 'rnadr_kor', 'fileName': '도로명주소한글활용가이드.pdf',
    'realFileName': 'rnadr_korDBGuide.pdf', 'regYmd': '2023'})
SOURCE_URL = 'https://business.juso.go.kr/api/jst/download?' + urlencode({
    'regYmd': '2026', 'reqType': 'ALLRNADR_KOR', 'ctprvnCd': '00', 'stdde': SOURCE_MONTH,
    'fileName': '202609_도로명주소 한글_전체분.zip', 'realFileName': 'RNADDR_KOR_2609.zip',
    'intFileNo': '0', 'intNum': '0'})
# Exact selected member from the ZIP central directory; the public server supports standard HTTP Range.
MEMBER_RECEIPT = {'archive_bytes': 92134273, 'member': MEMBER, 'local_header_offset': 83799057,
                  'compressed_bytes': 345389, 'bytes': 4120385, 'method': 8,
                  'crc32': 23239862,
                  'sha256': 'afddfbdcd17bbd27df4df4e0314b2958d26b9b612044cb86fb867fc41303b389'}
SOURCE_COLUMNS = ['address_id', 'legal_dong_code', 'province_ko', 'district_ko', 'legal_emd_ko',
                  'legal_ri_ko', 'mountain_flag', 'lot_main_number', 'lot_sub_number', 'road_code',
                  'road_name_ko', 'basement_flag', 'building_main_number', 'building_sub_number',
                  'admin_dong_code', 'admin_dong_ko', 'postcode', 'previous_road_address',
                  'effective_date', 'apartment_flag', 'change_reason', 'building_register_name',
                  'local_building_name', 'remarks']
SOURCE_COLUMN_LABELS = ['도로명주소관리번호', '법정동코드', '시도명', '시군구명', '법정읍면동명',
                        '법정리명', '산여부', '지번본번', '지번부번', '도로명코드', '도로명',
                        '지하여부', '건물본번', '건물부번', '행정동코드', '행정동명',
                        '기초구역번호(우편번호)', '이전도로명주소', '효력발생일', '공동주택구분',
                        '이동사유코드', '건축물대장건물명', '시군구용건물명', '비고']
COLUMNS = ['record_id', 'country', *SOURCE_COLUMNS, 'source_ref', 'source_row']
SEARCH_FIELDS = ['address_id', 'postcode', 'road_code', 'road_name_ko', 'province_ko', 'district_ko',
                 'legal_emd_ko', 'legal_ri_ko', 'admin_dong_ko', 'building_main_number',
                 'building_sub_number', 'building_register_name', 'local_building_name']
CLAIMS = {'national_address_completeness_verified': False, 'upstream_freshness_verified': False,
          'street_verified': False, 'premise_verified': False, 'deliverability_verified': False}
SCOPE = ('All rows of rnaddrkor_sejong.txt in the supplied 202609 Korean road-name address DB; '
         'Sejong-only pilot. Not nationwide coverage, physical premise verification, or deliverability.')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def file_spec(content, **extra):
    return {'bytes': len(content), 'sha256': digest(content), **extra}


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def acquire(output):
    """Fetch the exact public ZIP member with HTTP Range; no login or account is used."""
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), 'output must be a new file')
    start = MEMBER_RECEIPT['local_header_offset']
    end = start + 30 + len(MEMBER.encode('ascii')) + MEMBER_RECEIPT['compressed_bytes'] - 1
    request = Request(SOURCE_URL, headers={'Range': f'bytes={start}-{end}'})
    with urlopen(request, timeout=60) as response:
        require(response.status == 206, 'official download did not honor byte range')
        require(response.headers.get('Content-Range') ==
                f"bytes {start}-{end}/{MEMBER_RECEIPT['archive_bytes']}", 'source archive length or range changed')
        data = response.read(end - start + 2)
    require(len(data) == end - start + 1, 'source member download length differs')
    header = struct.unpack_from('<4s5H3L2H', data)
    signature, _, flags, method, _, _, crc, compressed_size, uncompressed_size, name_len, extra_len = header
    require(signature == b'PK\x03\x04' and method == 8 and not flags & 1, 'unsupported source ZIP header')
    require(data[30:30 + name_len].decode('ascii') == MEMBER and extra_len == 0,
            'source ZIP member name or header changed')
    require(compressed_size == MEMBER_RECEIPT['compressed_bytes'] and uncompressed_size == MEMBER_RECEIPT['bytes'],
            'source ZIP sizes changed')
    raw = zlib.decompress(data[30 + name_len:], -15)
    require(binascii.crc32(raw) == crc == MEMBER_RECEIPT['crc32'], 'source ZIP CRC differs')
    require(len(raw) == MEMBER_RECEIPT['bytes'] and digest(raw) == MEMBER_RECEIPT['sha256'],
            'selected official source checksum differs')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(gzip.compress(raw, mtime=0))
    return {'status': 'acquired', 'member': MEMBER, **file_spec(raw)}


def source_rows(raw):
    """All 24 source columns remain text, including codes, postcodes and building numbers."""
    require(len(raw) <= 15_000_000, 'source TXT exceeds supported size')
    seen, checked_dates = set(), set()
    for number, line in enumerate(io.StringIO(raw.decode('cp949'), newline=''), 1):
        fields = line.rstrip('\r\n').split('|')
        require(len(fields) == 24, 'source TXT must have 24 fields')
        require(not any('\x00' in value for value in fields), 'NUL in source field')
        row = dict(zip(SOURCE_COLUMNS, fields))
        for field, width in [('address_id', 26), ('legal_dong_code', 10), ('road_code', 12), ('postcode', 5)]:
            require(bool(re.fullmatch(r'[0-9]{' + str(width) + '}', row[field])), 'invalid string code: ' + field)
        require(row['address_id'].startswith('36110') and row['legal_dong_code'].startswith('36110') and
                row['road_code'].startswith('36110') and row['province_ko'] == '세종특별자치시',
                'source row outside Sejong pilot')
        require(not row['admin_dong_code'] or bool(re.fullmatch('[0-9]{10}', row['admin_dong_code'])),
                'invalid string admin dong code')
        for field in ['lot_main_number', 'lot_sub_number', 'building_main_number', 'building_sub_number']:
            require(bool(re.fullmatch('[0-9]+', row[field])), 'invalid string number: ' + field)
        require(row['mountain_flag'] in {'0', '1'} and row['basement_flag'] in {'0', '1', '2', '3'}, 'unsupported source flag')
        require(row['apartment_flag'] in {'0', '1', '2'}, 'unsupported apartment flag')
        require(row['road_name_ko'] and row['legal_emd_ko'], 'empty source road or legal emd')
        value = row['effective_date']
        if value and value not in checked_dates:
            require(bool(re.fullmatch('[0-9]{8}', value)), 'invalid effective date')
            try:
                date(int(value[:4]), int(value[4:6]), int(value[6:]))
            except ValueError as error:
                raise ValueError('invalid effective date') from error
            checked_dates.add(value)
        require(not row['change_reason'] or row['change_reason'] in {'31', '34', '63'}, 'unsupported change reason')
        require(row['address_id'] not in seen, 'duplicate official address ID')
        seen.add(row['address_id'])
        yield {'record_id': 'kr:sejong-address:' + row['address_id'], 'country': 'KR',
               **row, 'source_ref': SOURCE_ID, 'source_row': str(number)}
    require(bool(seen), 'source TXT is empty')


def transform(raw):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, COLUMNS, lineterminator='\n', extrasaction='raise')
    writer.writeheader()
    roads, postcodes, dong_codes = set(), set(), set()
    count = missing_effective = deletion_rows = 0
    for row in source_rows(raw):
        writer.writerow(row)
        count += 1
        roads.add(row['road_code'])
        postcodes.add(row['postcode'])
        dong_codes.add(row['legal_dong_code'])
        missing_effective += not bool(row['effective_date'])
        deletion_rows += row['change_reason'] == '63'
    return stream.getvalue().encode('utf-8'), {
        'source_observations': count, 'unique_road_codes': len(roads), 'unique_postcodes': len(postcodes),
        'legal_dong_codes': len(dong_codes), 'rows_without_effective_date': missing_effective,
        'rows_with_deletion_change_reason': deletion_rows}


def build(source, output, retrieved_at=None):
    source, output = Path(source), Path(output)
    require(source.is_file() and not source.is_symlink(), 'source TXT gzip missing or symlink')
    require(not output.exists() and not output.is_symlink(), 'output must be a new directory')
    compressed_raw = source.read_bytes()
    require(len(compressed_raw) <= 5_000_000, 'source gzip exceeds supported size')
    raw = gzip.decompress(compressed_raw)
    plain, counts = transform(raw)
    compressed = gzip.compress(plain, mtime=0)
    observed = retrieved_at or datetime.now(timezone.utc).isoformat()
    output.mkdir(parents=True)
    (output / 'sources').mkdir()
    (output / RAW_NAME).write_bytes(compressed_raw)
    (output / 'records.csv.gz').write_bytes(compressed)
    write_json(output / 'sources.json', {'schema_version': 1, 'country': 'KR', 'sources': {
        SOURCE_ID: {'provider': 'Republic of Korea Ministry of the Interior and Safety / Juso',
            'name': '도로명주소 한글 (Korean road-name address DB), Sejong member',
            'url': SOURCE_URL, 'catalogue': CATALOGUE_URL, 'catalogue_metadata': CATALOGUE_METADATA_URL,
            'download_page': DOWNLOAD_PAGE, 'layout_guide': GUIDE_URL,
            'as_of': '2026-09', 'source_date': '2026-09', 'source_date_precision': 'month',
            'retrieved_at': observed, 'license': LICENSE, 'terms': TERMS_URL,
            'website_terms': 'https://www.juso.go.kr/Terms',
            'license_evidence': {'catalogue_identifier': '15050417', 'catalogue_name': '행정안전부_도로명주소 주소DB_일간',
                                 'license_name': LICENSE, 'isAccessibleForFree': True},
            'source_bytes': len(compressed_raw), 'source_sha256': digest(compressed_raw),
            'source_member': MEMBER, 'source_member_bytes': len(raw), 'source_member_sha256': digest(raw),
            'archive_member_receipt': MEMBER_RECEIPT, 'encoding': 'cp949', 'delimiter': '|',
            'source_columns': SOURCE_COLUMNS, 'source_column_labels': SOURCE_COLUMN_LABELS, 'scope': SCOPE}},
        'bundled_files': {RAW_NAME: file_spec(compressed_raw)}})
    write_json(output / 'coverage.json', {'schema_version': 1, 'country': 'KR',
        'layer_kind': 'road_name_address_pilot', 'rows': counts['source_observations'], 'counts': counts,
        'source_date': '2026-09', 'retrieved_at': observed, 'scope': SCOPE,
        'record_file': 'records.csv.gz', 'search_fields': SEARCH_FIELDS,
        'geographic_scope': {'country': 'KR', 'province': '세종특별자치시', 'district_code': '36110'},
        'files': {'records.csv.gz': file_spec(compressed, rows=counts['source_observations'],
                                            columns=COLUMNS, uncompressed_sha256=digest(plain))},
        'claims': CLAIMS, 'limitations': [
            'Only the Sejong member is included; other provinces and the related-parcel (jibun) companion are excluded.',
            'Source describes shared-address buildings as one address observation; this is not one row per physical premise.',
            'Korean source labels are copied verbatim. This source supplies no English labels; none are generated.',
            'The full monthly snapshot supplies change-reason columns but does not establish complete deletion history.',
            'Identifiers, postal codes and building/lot numbers are strings; no numeric or postcode inference is performed.',
            'File-month and retrieval date are distinct; upstream freshness and physical deliverability are not verified.']})
    return {'country': 'KR', 'status': 'built', 'rows': counts['source_observations'], 'counts': counts}


def verify(folder):
    folder = Path(folder)
    coverage = json.loads((folder / 'coverage.json').read_text())
    sources = json.loads((folder / 'sources.json').read_text())
    require(coverage['country'] == sources['country'] == 'KR', 'country differs from KR')
    require(coverage['layer_kind'] == 'road_name_address_pilot', 'unsupported source layer')
    require(coverage['claims'] == CLAIMS, 'unsupported address quality claim')
    require(coverage['scope'] == SCOPE, 'source scope changed')
    require(coverage['record_file'] == 'records.csv.gz' and coverage['search_fields'] == SEARCH_FIELDS,
            'unsupported search schema')
    require(set(coverage['files']) == {'records.csv.gz'} and set(sources['bundled_files']) == {RAW_NAME},
            'unexpected managed paths')
    for name, spec in {**coverage['files'], **sources['bundled_files']}.items():
        path = folder / name
        require(path.is_file() and not path.is_symlink(), 'missing or symlink managed file')
        content = path.read_bytes()
        require(len(content) == spec['bytes'] and digest(content) == spec['sha256'], 'checksum mismatch: ' + name)
    compressed_raw = (folder / RAW_NAME).read_bytes()
    source = sources['sources'][SOURCE_ID]
    require(source['source_member'] == MEMBER and source['source_columns'] == SOURCE_COLUMNS and
            source['source_column_labels'] == SOURCE_COLUMN_LABELS, 'source schema mismatch')
    require(source['url'] == SOURCE_URL and source['catalogue'] == CATALOGUE_URL and
            source['license'] == LICENSE and source['terms'] == TERMS_URL, 'source attribution or terms changed')
    require(source['archive_member_receipt'] == MEMBER_RECEIPT, 'source archive receipt changed')
    require(len(compressed_raw) == source['source_bytes'] and digest(compressed_raw) == source['source_sha256'],
            'source receipt mismatch')
    raw = gzip.decompress(compressed_raw)
    require(len(raw) == source['source_member_bytes'] and digest(raw) == source['source_member_sha256'],
            'source member receipt mismatch')
    require(source['source_date'] == coverage['source_date'] == '2026-09', 'source date changed')
    expected, counts = transform(raw)
    plain = gzip.decompress((folder / 'records.csv.gz').read_bytes())
    require(plain == expected, 'source row replay mismatch')
    spec = coverage['files']['records.csv.gz']
    require(spec['columns'] == COLUMNS and digest(plain) == spec['uncompressed_sha256'],
            'derived schema or uncompressed checksum mismatch')
    require(spec['rows'] == coverage['rows'] == counts['source_observations'], 'row count mismatch')
    require(coverage['counts'] == counts, 'source layer counts mismatch')
    return {'country': 'KR', 'status': 'passed', 'source_integrity': 'passed', 'row_integrity': 'passed',
            'rows': counts['source_observations'], 'counts': counts,
            'scope': 'exact saved Sejong source member replay; original upstream ZIP is not bundled',
            'freshness_verified': None, 'national_completeness_verified': False, 'deliverability_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='action', required=True)
    fetch = commands.add_parser('acquire')
    fetch.add_argument('--output', type=Path, required=True)
    create = commands.add_parser('build')
    create.add_argument('--source', type=Path, required=True)
    create.add_argument('--output', type=Path, required=True)
    create.add_argument('--retrieved-at')
    check = commands.add_parser('verify')
    check.add_argument('--folder', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.action == 'acquire':
            report = acquire(args.output)
        elif args.action == 'build':
            report = build(args.source, args.output, args.retrieved_at)
        else:
            report = verify(args.folder)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, UnicodeError, csv.Error, zlib.error) as error:
        parser.exit(1, 'Korea import failed: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
