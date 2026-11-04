"""Read pinned Western Europe registers without inferring national completeness.

Python standard library only. Source rows, languages, status flags and identifiers
remain separate. A street register is not an inventory of all physical roads.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import struct
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCOPE = ('AT', 'BE', 'CH', 'DE', 'FR', 'GB', 'IE', 'LI', 'LU', 'MC', 'NL')
M49 = tuple(cc for cc in SCOPE if cc not in ('GB', 'IE'))
FORMATS = {'llv_addresses_zip', 'llv_streets_zip', 'caclr_zip',
           'swiss_addresses_zip', 'swiss_streets_zip', 'best_addresses_zip',
           'best_streets_zip', 'bev_relational_zip', 'ban_csv_gz', 'ban_national_csv_gz'}
HOSTS = {'service.geo.llv.li', 'download.data.public.lu', 'data.geo.admin.ch',
         'opendata.bosa.be', 'data.bev.gv.at', 'adresse.data.gouv.fr'}
DEFAULT_MANIFEST = ROOT / 'releases/hierarchy/western-europe/official-sources.json'
MAINLAND_DEPARTMENTS = {f'{n:02}' for n in range(1, 96) if n != 20} | {'2A', '2B'}
BAN_OVERSEAS = {'971': 'GP', '972': 'MQ', '973': 'GF', '974': 'RE', '975': 'PM',
                '976': 'YT', '977': 'BL', '978': 'MF', '984': 'TF', '986': 'WF',
                '987': 'PF', '988': 'NC', '989': 'CP'}
FORMAT_COUNTRIES = {'llv_addresses_zip': {'LI'}, 'llv_streets_zip': {'LI'},
                    'caclr_zip': {'LU'}, 'swiss_addresses_zip': {'CH'},
                    'swiss_streets_zip': {'CH'}, 'best_addresses_zip': {'BE'},
                    'best_streets_zip': {'BE'}, 'bev_relational_zip': {'AT'},
                    'ban_csv_gz': {'FR'}, 'ban_national_csv_gz': {'FR'}}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def source_path(root, source):
    root = Path(root).resolve()
    relative = Path(source['path'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Unsafe source path')
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Source escapes data root')
    return path


def load_manifest(path):
    manifest = json.loads(Path(path).read_text(encoding='utf-8'))
    if (manifest.get('schema_version') != 1 or manifest.get('region') != 'western-europe'
            or manifest.get('scope_codes') != list(SCOPE)
            or manifest.get('national_completeness_verified') is not False
            or manifest.get('deliverability_in_scope') is not False):
        raise ValueError('Invalid regional source manifest')
    sources = manifest['sources']
    if not sources:
        raise ValueError('No accepted source pins')
    for field in ('id', 'path'):
        if len({s[field] for s in sources}) != len(sources):
            raise ValueError('Duplicate source ' + field)
    for source in sources:
        if (source['country'] not in SCOPE or source['format'] not in FORMATS
                or type(source['bytes']) is not int or source['bytes'] <= 0
                or not re.fullmatch('[0-9a-f]{64}', source['sha256'])):
            raise ValueError('Invalid source pin or format')
        if source['country'] not in FORMAT_COUNTRIES[source['format']]:
            raise ValueError('Source format belongs to another jurisdiction')
        source_path(Path('.'), source)
    return manifest


def selected_sources(manifest, country=None):
    if country is not None and country not in SCOPE:
        raise ValueError('Country outside Western Europe project scope')
    return [s for s in manifest['sources'] if country is None or s['country'] == country]


def verify_pin(source, root):
    path = source_path(root, source)
    if not path.is_file() or path.stat().st_size != source['bytes'] or sha256(path) != source['sha256']:
        raise ValueError('Source bytes differ: ' + source['id'])
    return path


def csv_rows(archive, member, delimiter=';', encoding='utf-8-sig'):
    with archive.open(member) as binary, io.TextIOWrapper(binary, encoding=encoding, newline='') as stream:
        reader = csv.DictReader(stream, delimiter=delimiter)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError('Missing or duplicate CSV headers: ' + member)
        for ordinal, row in enumerate(reader, 1):
            if None in row or any(value is None for value in row.values()):
                raise ValueError('Malformed CSV row: ' + member + ':' + str(ordinal))
            yield ordinal, row


def require(row, *fields):
    if not set(fields) <= row.keys():
        raise ValueError('Source schema changed; missing ' + ','.join(sorted(set(fields) - row.keys())))


def observation(source, member, ordinal, raw, kind, identity, **values):
    return {'source': source['id'], 'country': source['country'], 'member': member,
            'ordinal': ordinal, 'kind': kind, 'source_id': identity,
            'source_sha256': source['sha256'],
            'source_qualified_id': source['id'] + ':' + member + ':' + str(ordinal),
            'raw': raw, **values}


def dbf_rows(data, encoding='cp1252'):
    if len(data) < 33:
        raise ValueError('Truncated DBF')
    count, header, width = struct.unpack_from('<IHH', data, 4)
    if header < 33 or (header - 33) % 32 or len(data) < header + count * width:
        raise ValueError('Invalid DBF sizes')
    fields = []
    for offset in range(32, header - 1, 32):
        field = data[offset:offset + 32]
        fields.append((field[:11].split(b'\0')[0].decode('ascii'), field[16]))
    if width != 1 + sum(size for _, size in fields) or data[header - 1] != 13:
        raise ValueError('Invalid DBF layout')
    if len({name for name, _ in fields}) != len(fields):
        raise ValueError('Duplicate DBF field')
    for index in range(count):
        record = data[header + index * width:header + (index + 1) * width]
        if record[:1] != b' ':
            raise ValueError('Deleted DBF row needs explicit review')
        row, cursor = {}, 1
        for name, size in fields:
            row[name] = record[cursor:cursor + size].decode(encoding).strip()
            cursor += size
        yield index + 1, row


def fixed_rows(archive, member, minimum):
    with archive.open(member) as stream:
        for ordinal, line in enumerate(stream, 1):
            line = line.rstrip(b'\r\n')
            if len(line) < minimum:
                raise ValueError('Truncated fixed-width row: ' + member)
            yield ordinal, line.decode('cp1252')


def fixed_value(line, start, width, null_position=None):
    if null_position is not None and line[null_position - 1:null_position] == '?':
        return None
    return line[start - 1:start - 1 + width].strip()


def caclr_records(source, archive):
    """Positions are byte positions in ACT's CACLR ASCII specification v2.2.

    COMMMUALL uses the exported 95th-character O/N marker. The obsolete district
    reference and special canton 00 remain source fields, not current divisions.
    """
    cantons = {line[:2]: line[2:42].strip() for _, line in fixed_rows(archive, 'CANTON', 57)}
    communes = {}
    for ordinal, raw in fixed_rows(archive, 'COMMUALL', 95):
        key = raw[92:94] + raw[:2]
        if key in communes:
            raise ValueError('Duplicate composite CACLR commune key')
        communes[key] = raw
        yield observation(source, 'COMMUALL', ordinal, raw, 'municipality', key,
                          name=raw[2:42].strip(), canton_code=raw[92:94],
                          current_marker=raw[94], status='current' if raw[94] == 'O' else 'historical')
    for ordinal, raw in fixed_rows(archive, 'CANTON', 57):
        yield observation(source, 'CANTON', ordinal, raw, 'canton_reference', raw[:2], name=raw[2:42].strip(),
                          historical_district_reference=raw[52:56])
    localities = {}
    for ordinal, raw in fixed_rows(archive, 'LOCALITE', 115):
        code = raw[:5]
        if code in localities:
            raise ValueError('Duplicate CACLR locality key')
        localities[code] = raw
        commune = raw[109:111] + raw[112:114]
        yield observation(source, 'LOCALITE', ordinal, raw, 'locality', code,
                          name=raw[5:45].strip(), admin_code=commune,
                          status='current' if fixed_value(raw, 89, 10, 99) is None else 'ended',
                          missing_references=[] if commune in communes else ['municipality:' + commune])
    streets = {}
    for ordinal, raw in fixed_rows(archive, 'RUE', 138):
        code, locality = raw[:5], fixed_value(raw, 132, 5, 137)
        if code in streets:
            raise ValueError('Duplicate CACLR street key')
        streets[code] = raw
        yield observation(source, 'RUE', ordinal, raw, 'street', code,
                          street_names={'und': raw[5:45].strip()}, locality_code=locality,
                          status='current' if fixed_value(raw, 103, 10, 113) is None else 'ended',
                          missing_references=[] if locality is None or locality in localities else ['locality:' + locality])
    for ordinal, raw in fixed_rows(archive, 'IMMEUBLE', 57):
        street_id = fixed_value(raw, 50, 5, 55)
        street = streets.get(street_id)
        locality_id = fixed_value(street, 132, 5, 137) if street is not None else None
        locality = localities.get(locality_id)
        numeric = raw[8:11]
        if not numeric.isascii() or not numeric.isdigit():
            raise ValueError('Unexpected CACLR numeric house field')
        yield observation(source, 'IMMEUBLE', ordinal, raw, 'address', raw[:8],
                          number=None if raw[55] == 'O' else str(int(numeric)), source_number=numeric,
                          suffix=raw[11:17].strip(), street_id=street_id,
                          street_names={'und': street[5:45].strip()} if street is not None else {},
                          locality_code=locality_id, locality=locality[5:45].strip() if locality is not None else None,
                          postcode=fixed_value(raw, 39, 4, 43),
                          status='current' if fixed_value(raw, 18, 10, 28) is None else 'ended',
                          provisional_marker=raw[56], indefinite_number_marker=raw[55],
                          missing_references=[] if street_id is None or street is not None else ['street:' + street_id])
    # Keep supplementary tables without counting aliases, postcode links or
    # duplicate building designations as additional streets/addresses.
    for member, kind, minimum in (
            ('ALIAS.LOCALITE', 'locality_alias', 99), ('ALIAS.RUE', 'street_alias', 180),
            ('CODEPT', 'postcode_reference', 63), ('CPTCH', 'road_number_reference', 16),
            ('DISTRICT', 'historical_district_reference', 54),
            ('IMMDESIG', 'building_designation', 98), ('QUARTIER', 'quarter_reference', 61),
            ('TR.DICACOLO.RUCP', 'street_postcode_link', 205)):
        for ordinal, raw in fixed_rows(archive, member, minimum):
            yield observation(source, member, ordinal, raw, kind, member + ':' + str(ordinal))


def bev_records(source, archive):
    municipalities, localities, streets = {}, {}, {}
    for member, table, key_field, label, kind in (
            ('GEMEINDE.csv', municipalities, 'GKZ', 'GEMEINDENAME', 'municipality'),
            ('ORTSCHAFT.csv', localities, 'OKZ', 'ORTSNAME', 'locality'),
            ('STRASSE.csv', streets, 'SKZ', 'STRASSENNAME', 'street')):
        for ordinal, raw in csv_rows(archive, member):
            require(raw, key_field, label, 'GKZ')
            key = (raw['GKZ'], raw[key_field]) if kind != 'municipality' else raw['GKZ']
            if key in table:
                raise ValueError('Duplicate BEV reference key')
            table[key] = raw
            yield observation(source, member, ordinal, raw, kind, raw[key_field],
                              name=raw[label], admin_code=raw['GKZ'],
                              street_names={'de': raw[label]} if kind == 'street' else {})
    for member, kind, id_fields in (
            ('ADRESSE.csv', 'address', ('ADRCD',)),
            ('ZAEHLSPRENGEL.csv', 'statistical_area', ('ZAEHLSPRENGEL',)),
            ('GEBAEUDE.csv', 'building', ('ADRCD', 'SUBCD', 'OBJEKTNUMMER')),
            ('ADRESSE_GST.csv', 'parcel_link', ('ADRCD', 'KGNR', 'GSTNR', 'LFDNR')),
            ('GEBAEUDE_FUNKTION.csv', 'building_function', ('ADRCD', 'SUBCD', 'OBJEKTNUMMER', 'OBJFUNKTKENNZIFFER'))):
        for ordinal, raw in csv_rows(archive, member):
            require(raw, *id_fields)
            values = {}
            if kind == 'address':
                require(raw, 'GKZ', 'OKZ', 'SKZ', 'HNR_ADR_ZUSAMMEN', 'EPSG', 'RW', 'HW')
                street = streets.get((raw['GKZ'], raw['SKZ']))
                locality = localities.get((raw['GKZ'], raw['OKZ']))
                missing = []
                if raw['GKZ'] not in municipalities:
                    missing.append('municipality:' + raw['GKZ'])
                if street is None:
                    missing.append('street:' + raw['GKZ'] + ':' + raw['SKZ'])
                if locality is None:
                    missing.append('locality:' + raw['GKZ'] + ':' + raw['OKZ'])
                values = {'number': raw['HNR_ADR_ZUSAMMEN'], 'street_id': raw['SKZ'],
                          'street_names': {'de': street['STRASSENNAME']} if street is not None else {},
                          'admin_code': raw['GKZ'], 'locality_code': raw['OKZ'],
                          'locality': locality['ORTSNAME'] if locality is not None else None,
                          'postcode': raw['PLZ'], 'missing_references': missing,
                          'coordinates': {'source_crs': 'EPSG:' + raw['EPSG'], 'x': raw['RW'], 'y': raw['HW']}}
            yield observation(source, member, ordinal, raw, kind, ':'.join(raw[k] for k in id_fields), **values)


def records(source, root):
    path = source_path(root, source)
    fmt = source['format']
    if fmt in ('ban_csv_gz', 'ban_national_csv_gz'):
        import gzip
        with gzip.open(path, 'rt', encoding='utf-8-sig', newline='') as stream:
            for ordinal, raw in enumerate(csv.DictReader(stream, delimiter=';'), 1):
                require(raw, 'id', 'numero', 'rep', 'nom_voie', 'code_insee', 'certification_commune')
                if None in raw or any(v is None for v in raw.values()):
                    raise ValueError('BAN row schema or department mismatch')
                code = raw['code_insee']
                mainland = code[:2] in MAINLAND_DEPARTMENTS
                jurisdiction = 'FR' if mainland else BAN_OVERSEAS.get(code[:3])
                if (jurisdiction is None or not re.fullmatch(r'(?:[0-9]{2}|2A|2B)[0-9]{3}', code)
                        or raw['certification_commune'] not in ('', '0', '1')
                        or (fmt == 'ban_csv_gz' and not code.startswith(source['department']))):
                    raise ValueError('BAN jurisdiction or certification needs review: ' + code)
                yield observation(source, path.name, ordinal, raw,
                                  'address' if jurisdiction == 'FR' else 'outside_scope_address', raw['id'],
                                  country=jurisdiction,
                                  number=raw['numero'], suffix=raw['rep'], street_names={'fr': raw['nom_voie']},
                                  admin_code=raw['code_insee'], postcode=raw.get('code_postal'),
                                  municipality_certified=raw['certification_commune'])
        return
    with zipfile.ZipFile(path) as archive:
        if len(set(archive.namelist())) != len(archive.namelist()):
            raise ValueError('Duplicate ZIP member names')
        if fmt == 'caclr_zip':
            yield from caclr_records(source, archive)
            return
        if fmt == 'bev_relational_zip':
            yield from bev_records(source, archive)
            return
        if fmt == 'llv_streets_zip':
            for member, kind in (('OfficialIndexOfStreetsStreet.dbf', 'street'),
                                 ('OfficialIndexOfStreetsArea.dbf', 'named_area')):
                for ordinal, raw in dbf_rows(archive.read(member)):
                    require(raw, 'STR_ESID', 'COM_FOSNR', 'NAME', 'OFFICIAL', 'STATUS')
                    yield observation(source, member, ordinal, raw, kind, raw['STR_ESID'],
                                      street_names={'de': raw['NAME']}, admin_code=raw['COM_FOSNR'],
                                      status=raw['STATUS'], official=raw['OFFICIAL'],
                                      geometry_reference={'member': member[:-4] + '.shp', 'record': ordinal})
            return
        members = [m for m in archive.namelist() if m.lower().endswith('.csv')]
        if not members:
            raise ValueError('No CSV source members')
        for member in members:
            for ordinal, raw in csv_rows(archive, member,
                                         ',' if fmt.startswith('best_') else ';',
                                         'cp1252' if fmt == 'llv_addresses_zip' else 'utf-8-sig'):
                if fmt in ('swiss_addresses_zip', 'llv_addresses_zip'):
                    require(raw, 'ADR_EGAID', 'STR_ESID', 'ADR_NUMBER', 'COM_FOSNR')
                    street_field = 'STN_LABEL' if fmt.startswith('swiss') else 'STN_NAME'
                    require(raw, street_field)
                    values = dict(number=raw['ADR_NUMBER'], street_id=raw['STR_ESID'],
                                  street_names={'und' if source['country'] == 'CH' else 'de': raw[street_field]},
                                  admin_code=raw['COM_FOSNR'],
                                  status=raw.get('ADR_STATUS', raw.get('STATUS')),
                                  official=raw.get('ADR_OFFICIAL', raw.get('OFFICIAL')))
                    if fmt.startswith('swiss'):
                        values['coordinates'] = {'source_crs': 'EPSG:2056', 'x': raw['ADR_EASTING'], 'y': raw['ADR_NORTHING']}
                    else:
                        values['coordinates'] = {'source_crs': 'EPSG:4326', 'x': raw['WGS84_E'], 'y': raw['WGS84_N']}
                    yield observation(source, member, ordinal, raw, 'address', raw['ADR_EGAID'], **values)
                elif fmt == 'swiss_streets_zip':
                    require(raw, 'STR_ESID', 'STN_LABEL', 'COM_FOSNR', 'STR_STATUS', 'STR_OFFICIAL')
                    yield observation(source, member, ordinal, raw, 'street', raw['STR_ESID'],
                                      street_names={'und': raw['STN_LABEL']}, admin_code=raw['COM_FOSNR'],
                                      status=raw['STR_STATUS'], official=raw['STR_OFFICIAL'])
                elif fmt == 'best_addresses_zip':
                    require(raw, 'address_id', 'house_number', 'street_id', 'municipality_id', 'region_code',
                            'EPSG:4326_lat', 'EPSG:4326_lon', 'EPSG:3812_x', 'EPSG:3812_y', 'status')
                    yield observation(source, member, ordinal, raw, 'address', raw['region_code'] + ':' + raw['address_id'],
                                      number=raw['house_number'], box_number=raw.get('box_number'),
                                      street_id=raw['region_code'] + ':' + raw['street_id'],
                                      street_names={lang: raw.get('streetname_' + lang, '') for lang in ('nl', 'fr', 'de')},
                                      admin_code=raw['municipality_id'], status=raw['status'],
                                      coordinates={'source_crs': 'EPSG:4326', 'x': raw['EPSG:4326_lon'], 'y': raw['EPSG:4326_lat']})
                elif fmt == 'best_streets_zip':
                    require(raw, 'street_prefix', 'street_no', 'street_version', 'city_no')
                    yield observation(source, member, ordinal, raw, 'street', raw['street_prefix'] + '/' + raw['street_no'],
                                      source_version=raw['street_version'], admin_code=raw['city_no'],
                                      street_names={lang: raw.get('street_' + lang, '') for lang in ('nl', 'fr', 'de')},
                                      list_category='no_address_source_list' if 'empty' in member else 'addressed_source_list',
                                      postcode_association_is_approximate=True)
                else:
                    raise ValueError('Unsupported source format')


def analyze(source, root):
    path = verify_pin(source, root)
    digest, counts, statuses, flags, missing, members = hashlib.sha256(), Counter(), Counter(), Counter(), Counter(), Counter()
    for row in records(source, root):
        digest.update(canonical(row).encode('utf-8') + b'\n')
        counts[row['kind']] += 1
        members[row['member']] += 1
        if row.get('status') is not None:
            statuses[row['kind'] + ':' + row['status']] += 1
        if 'official' in row:
            flags[row['kind'] + ':' + row['official']] += 1
        if row['kind'] == 'address' and row.get('number'):
            counts['numbered_address_rows'] += 1
        if row.get('box_number'):
            counts['rows_with_box_number'] += 1
        for reference in row.get('missing_references', []):
            missing[reference.split(':')[0]] += 1
    if not members:
        raise ValueError('Empty source')
    if source['format'].endswith('_zip'):
        with zipfile.ZipFile(path) as archive:
            bad = archive.testzip()
            if bad is not None:
                raise ValueError('ZIP CRC mismatch: ' + bad)
    return {'id': source['id'], 'country': source['country'], 'source_sha256': source['sha256'],
            'canonical_rows_sha256': digest.hexdigest(), 'counts': dict(counts),
            'member_rows': dict(members), 'source_status_counts': dict(statuses),
            'source_official_flag_counts': dict(flags), 'unresolved_reference_counts': dict(missing),
            'source_integrity': 'PASS', 'national_completeness_verified': False}


def audit(manifest, root, country=None):
    sources = selected_sources(manifest, country)
    reports = []
    for source in sources:
        report = analyze(source, root)
        reports.append(report)
        print(canonical({'source': source['id'], 'counts': report['counts'], 'status': 'VALIDATED'}), flush=True)
    return {'schema_version': 1, 'region': 'western-europe', 'status': 'PASS' if sources else 'NO_ACCEPTED_SOURCE',
            'scope_codes': list(SCOPE), 'audited_country': country,
            'implementation_sha256': sha256(__file__),
            'manifest_sha256': hashlib.sha256(canonical(manifest).encode()).hexdigest(),
            'source_reports': reports, 'national_completeness_verified': False,
            'deliverability_in_scope': False,
            'counts_semantics': 'Source observations, including historical, provisional and unofficial flags. Not unique real-world addresses.'}


def replay(manifest, root, accepted, country=None):
    if accepted.get('implementation_sha256') != sha256(__file__):
        raise ValueError('Implementation differs from accepted audit')
    if accepted.get('manifest_sha256') != hashlib.sha256(canonical(manifest).encode()).hexdigest():
        raise ValueError('Manifest differs from accepted audit')
    old = {r['id']: r for r in accepted['source_reports']}
    selected = selected_sources(manifest, country)
    if not {s['id'] for s in selected} <= old.keys():
        raise ValueError('Accepted audit is missing source receipts')
    current = audit(manifest, root, country)
    for report in current['source_reports']:
        if old.get(report['id']) != report:
            raise ValueError('Source replay differs: ' + report['id'])
    return {**current, 'source_row_replay': 'PASS'}


def search(manifest, root, country, text='', number=None, kind=None, limit=20, offset=0, current_only=False):
    if not 1 <= limit <= 200 or offset < 0 or (number is not None and not isinstance(number, str)):
        raise ValueError('Invalid query or pagination')
    if kind is not None and kind not in ('address', 'street', 'municipality', 'locality', 'canton_reference', 'named_area'):
        raise ValueError('Unsupported query kind')
    matches, skipped = [], 0
    for source in selected_sources(manifest, country):
        verify_pin(source, root)
        for row in records(source, root):
            if row['country'] != country:
                continue
            if kind is not None and row['kind'] != kind:
                continue
            if number is not None and row.get('number') != number:
                continue
            if text and text.casefold() not in canonical(row).casefold():
                continue
            if current_only and row.get('status') not in ('current', 'real'):
                continue
            if skipped < offset:
                skipped += 1
                continue
            matches.append(row)
            if len(matches) > limit:
                return {'country': country, 'results': matches[:limit], 'has_more': True,
                        'next_offset': offset + limit, 'national_completeness_verified': False, 'deliverability_in_scope': False}
    return {'country': country, 'results': matches, 'has_more': False, 'next_offset': None,
            'national_completeness_verified': False, 'deliverability_in_scope': False}


def acquire(manifest, target, country=None):
    target = Path(target).resolve()
    target.mkdir(parents=True, exist_ok=True)
    recovered = []
    for source in selected_sources(manifest, country):
        path = source_path(target, source)
        if path.exists():
            verify_pin(source, target)
            recovered.append(source['id'])
            continue
        url = urlsplit(source['requested_url'])
        if url.scheme != 'https' or url.hostname not in HOSTS:
            raise ValueError('Unregistered download host')
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + '.partial')
        if partial.exists():
            raise ValueError('Prior incomplete download needs explicit review')
        try:
            with urlopen(Request(source['requested_url'], headers={'User-Agent': 'WorldLocalities-WesternEurope/1.0'}), timeout=50) as response:
                final = urlsplit(response.geturl())
                if final.scheme != 'https' or final.hostname not in HOSTS:
                    raise ValueError('Unexpected download redirect')
                with partial.open('xb') as output:
                    count = 0
                    for block in iter(lambda: response.read(1024 * 1024), b''):
                        count += len(block)
                        if count > source['bytes']:
                            raise ValueError('Snapshot changed; inspect a new candidate')
                        output.write(block)
            if partial.stat().st_size != source['bytes'] or sha256(partial) != source['sha256']:
                raise ValueError('Pinned historical bytes were not recovered')
            # Refuse concurrent overwrite even after successful download.
            path.hardlink_to(partial)
            partial.unlink()
            recovered.append(source['id'])
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
    return {'status': 'PINNED_BYTES_RECOVERED', 'sources': recovered,
            'national_completeness_verified': False, 'deliverability_in_scope': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inventory', 'audit', 'replay', 'search', 'acquire'))
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--country', choices=SCOPE)
    parser.add_argument('--accepted', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--text', default='')
    parser.add_argument('--number')
    parser.add_argument('--kind')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--current-only', action='store_true')
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        if args.command == 'inventory':
            result = {'scope_codes': list(SCOPE), 'm49_western_europe': list(M49),
                      'legacy_group_additions': ['GB', 'IE'], 'sources': manifest['sources'],
                      'national_completeness_verified': False, 'deliverability_in_scope': False}
        else:
            if args.data_root is None:
                raise ValueError('--data-root is required')
            if args.command == 'search':
                if args.country is None:
                    raise ValueError('--country is required')
                result = search(manifest, args.data_root, args.country, args.text, args.number,
                                args.kind, args.limit, args.offset, args.current_only)
            elif args.command == 'acquire':
                result = acquire(manifest, args.data_root, args.country)
            elif args.command == 'audit':
                result = audit(manifest, args.data_root, args.country)
            else:
                if args.accepted is None:
                    raise ValueError('--accepted is required')
                result = replay(manifest, args.data_root, json.loads(args.accepted.read_text()), args.country)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if args.output:
            args.output.write_text(rendered, encoding='utf-8')
        else:
            print(rendered, end='')
    except (OSError, ValueError, KeyError, UnicodeError, zipfile.BadZipFile, struct.error) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
