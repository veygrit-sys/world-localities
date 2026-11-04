"""Strict local-input checks; integrity is not freshness or deliverability."""
import csv
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


class DataError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise DataError(message)


def _object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def decode_json(data):
    def reject_constant(value):
        raise DataError(f"non-finite JSON number: {value}")
    return json.loads(data, object_pairs_hook=_object, parse_constant=reject_constant)


def safe_file(root, relative):
    """Reject traversal, Windows paths and symlinks, even within the root."""
    require(isinstance(relative, str) and relative and '\\' not in relative,
            "unsafe source path")
    parts = relative.split('/')
    require(not Path(relative).is_absolute() and
            all(p not in ('', '.', '..') and ':' not in p for p in parts),
            "unsafe source path")
    root = Path(root).resolve()
    target = root
    for part in parts:
        target = target / part
        require(not target.is_symlink(), "symlink source path rejected")
    require(target.is_file() and target.resolve().is_relative_to(root),
            f"missing or unsafe source file: {relative}")
    return target


def load_json(root, relative):
    return decode_json(safe_file(root, relative).read_bytes())


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verified_bytes(root, relative, expected):
    require(isinstance(expected, str) and re.fullmatch(r'[0-9a-f]{64}', expected),
            f"missing or invalid SHA-256: {relative}")
    data = safe_file(root, relative).read_bytes()
    require(digest(data) == expected, f"SHA-256 mismatch: {relative}")
    return data


def csv_rows(data, columns=None):
    reader = csv.DictReader(io.StringIO(data.decode('utf-8'), newline=''), strict=True)
    header = reader.fieldnames
    require(header and len(header) == len(set(header)) and all(header),
            "missing or duplicate CSV columns")
    if columns is not None:
        require(header == columns, "unexpected CSV columns")
    rows = []
    for row in reader:
        require(None not in row and all(v is not None for v in row.values()),
                "invalid CSV field count")
        rows.append(row)
    return rows


def count(value, field):
    require(type(value) is int and value >= 0, f"invalid nonnegative count: {field}")
    return value


def unique_rows(rows, key, label):
    require(isinstance(rows, list), f"{label}: expected a list")
    result = {}
    for row in rows:
        value = row[key]
        require(isinstance(value, str) and value and value not in result,
                f"{label}: missing or duplicate {key}")
        result[value] = row
    return result


CLAIMS = {'all_world_localities_complete', 'all_postal_city_names_complete',
          'all_languages_complete', 'street_addresses_complete', 'deliverability_verified'}
REQUIRED_COLUMNS = {'id', 'code', 'name', 'lang', 'parent_id', 'state_id', 'state_code',
                    'address_country', 'address_candidate', 'source_type', 'category'}


def official_index(root, country):
    require(country in {'US', 'CA', 'MX', 'BR'}, "unsupported official country")
    directory = f'official-registry/{country}'
    manifest_bytes = safe_file(root, directory + '/manifest.json').read_bytes()
    manifest = decode_json(manifest_bytes)
    require(manifest['country'] == country, "manifest country mismatch")
    claims = manifest['claims']
    require(set(claims) == CLAIMS and all(v is False for v in claims.values()),
            "missing or unsafe completeness claims")
    hashes = manifest['sha256']
    for filename in hashes:
        require('/' not in filename and filename not in ('', '.', '..'),
                "unsafe manifest filename")
        safe_file(root, directory + '/' + filename)
    index = decode_json(verified_bytes(root, directory + '/index.json', hashes.get('index.json')))
    require(index['country'] == country, "index country mismatch")
    require(index['vintage'] == manifest['vintage'], "source vintage mismatch")
    columns = index['columns']
    require(isinstance(columns, list) and len(columns) == len(set(columns)) and
            REQUIRED_COLUMNS.issubset(columns), "invalid index columns")
    regions = unique_rows(index['regions'], 'code', 'regions')
    unique_rows(index['regions'], 'id', 'regions')
    unique_rows(index['regions'], 'file', 'regions')
    total = 0
    for code, region in regions.items():
        require(code.startswith(country + '-'), "wrong region country")
        require(region['file'] == code + '.csv', "region filename/code mismatch")
        total += count(region['localities'], code)
        require(count(region['address_candidates'], code) <= region['localities'],
                "candidate count exceeds row count")
    require(total == count(index['counts']['source_localities'], country),
            "index region totals mismatch")
    anchors = csv_rows(verified_bytes(root, directory + '/anchors.csv', hashes.get('anchors.csv')), columns)
    anchors = unique_rows(anchors, 'id', 'anchors')
    for region in regions.values():
        require(region['id'] in anchors and anchors[region['id']]['code'] == region['code'],
                "missing or incorrect region anchor")
    return index, manifest, anchors, digest(manifest_bytes)


def region_rows(root, country, index, manifest, anchors, region):
    filename = region['file']
    raw = verified_bytes(root, f'official-registry/{country}/{filename}', manifest['sha256'].get(filename))
    rows = csv_rows(raw, index['columns'])
    require(len(rows) == region['localities'], "region row count mismatch")
    seen, candidates = set(), 0
    for row in rows:
        identity = row['id']
        require(identity and identity not in seen and identity not in anchors, "duplicate or empty locality ID")
        seen.add(identity)
        require(row['name'].strip() and row['lang'].strip(), "empty name or language")
        require(row['state_id'] == region['id'] and row['state_code'] == region['code'],
                "locality region mismatch")
        require(row['address_country'] == ('PR' if region['code'] == 'US-PR' else country),
                "address country mismatch")
        require(row['address_candidate'] in ('0', '1'), "invalid candidate flag")
        require(row['parent_id'] in anchors, "unresolved locality parent")
        require(re.fullmatch(r'[0-9]+', row['code']) and identity.endswith(':' + row['code']),
                "invalid source identifier")
        if row['category'] == 'fictitious_census_entity':
            require(row['address_candidate'] == '0', "fictitious role is an address candidate")
        candidates += row['address_candidate'] == '1'
    require(candidates == region['address_candidates'], "region candidate count mismatch")
    return rows, digest(raw)


def https_evidence(url, hosts=None):
    require(isinstance(url, str), "invalid evidence URL")
    parsed = urlsplit(url)
    require(parsed.scheme == 'https' and parsed.hostname and not parsed.username and
            not parsed.password and parsed.port in (None, 443), "unsafe evidence URL")
    if hosts is not None:
        require(parsed.hostname in hosts, "unexpected evidence publisher")


def validate_seed_data(data):
    require(data['schema_version'] == 1, "unsupported seed schema")
    records = data['records']
    unique_rows(records, 'provisional_id', 'administrative seeds')
    sources = data['source_evidence']
    kinds = {'BM': {'parish', 'municipality'}, 'GL': {'municipality'}, 'PM': {'commune'}}
    hosts = {'BM': {'www.gov.bm', 'gov.bm'}, 'GL': {'stat.gl', 'bank.stat.gl', 'www.stat.gl'},
             'PM': {'www.insee.fr', 'insee.fr', 'www.legifrance.gouv.fr'}}
    pm_names = {'97501': 'Miquelon-Langlade', '97502': 'Saint-Pierre'}
    seen, codes, counts = set(), set(), dict.fromkeys(kinds, 0)
    for row in records:
        cc = row['country']
        require(cc in kinds and row['kind'] in kinds[cc], "invalid seed country/type")
        require(row['provisional_id'].startswith(f"seed:{cc}:{row['kind']}:"), "invalid provisional ID")
        name = row['source_name']
        require(isinstance(name, str) and name.strip() and row['language'] in ('en', 'fr', 'und'),
                "invalid seed name/language")
        key = (cc, row['kind'], name.casefold())
        require(key not in seen, "duplicate administrative name")
        seen.add(key)
        require(row['status'] == 'source_attested_administrative_name' and
                row['can_validate_postal_or_street'] is False, "unsafe seed claim")
        require(row['evidence_id'] in sources, "missing seed evidence")
        source = sources[row['evidence_id']]
        https_evidence(source['url'], hosts[cc])
        require(source.get('publisher') and source.get('source_vintage') and source.get('license_status'),
                "missing source provenance")
        if cc == 'PM':
            code = row['official_code']
            require(code in pm_names and name == pm_names[code] and code not in codes and
                    row['authority_code_scheme'] == 'FR-INSEE-COG-COM', "PM code/name mismatch")
            codes.add(code)
        else:
            require(row['official_code'] is None and row['authority_code_scheme'] is None,
                    "unverified official seed code")
        counts[cc] += 1
    return counts
