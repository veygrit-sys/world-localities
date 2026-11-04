#!/usr/bin/env python3
"""Pack verified country ZIPs into small volumes, or verify and unpack them."""
import argparse
import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
COUNTRY_FILES = ('entities.csv.gz', 'metadata.json', 'admin1.csv')
VOLUME_BYTES = 8 * 1024 * 1024


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')


def pack_country(country, *, root=ROOT, volume_bytes=VOLUME_BYTES):
    if not re.fullmatch('[A-Z]{2}', country) or volume_bytes < 1:
        raise ValueError('Invalid country or volume size')
    directory = root / 'countries' / country
    meta = json.loads((directory / 'metadata.json').read_text(encoding='utf-8'))
    members = {country + '/' + name: (directory / name).read_bytes() for name in COUNTRY_FILES}
    if digest(members[country + '/entities.csv.gz']) != meta['files']['entities.csv.gz']['sha256']:
        raise ValueError('Country data checksum mismatch')
    members['NOTICE.md'] = (root / 'NOTICE.md').read_bytes()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(members.items()):
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.external_attr = 0o100644 << 16
            entry.create_system = 3
            archive.writestr(entry, data)
    payload = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for name, data in members.items():
            if archive.read(name) != data:
                raise ValueError('Archive roundtrip mismatch')
    output = root / 'country-archives'
    output.mkdir(exist_ok=True)
    parts = []
    for index, offset in enumerate(range(0, len(payload), volume_bytes), 1):
        data = payload[offset:offset + volume_bytes]
        name = country + '.zip' if len(payload) <= volume_bytes else country + '.zip.part%03d' % index
        path = output / name
        if path.exists() and path.read_bytes() != data:
            raise ValueError('Refusing to replace a different published volume: ' + name)
        path.write_bytes(data)
        parts.append(dict(path=str(path.relative_to(root)), bytes=len(data), sha256=digest(data)))
    return dict(country=country, path='country-archives/' + country + '.zip', bytes=len(payload),
                sha256=digest(payload), rows=meta['files']['entities.csv.gz']['rows'], parts=parts,
                members={name: dict(bytes=len(data), sha256=digest(data)) for name, data in sorted(members.items())})


def unpack_record(row, *, root=ROOT, destination_root=None):
    cc = row['country']
    if not re.fullmatch('[A-Z]{2}', cc) or row['path'] != 'country-archives/' + cc + '.zip':
        raise ValueError('Invalid archive path')
    # Version 1 used a single ZIP; version 2 adds ordered volumes.
    parts = row.get('parts', [dict(path=row['path'], bytes=row['bytes'], sha256=row['sha256'])])
    if not parts:
        raise ValueError('Missing archive volumes')
    payloads = []
    for index, part in enumerate(parts, 1):
        expected_path = row['path'] if len(parts) == 1 else row['path'] + '.part%03d' % index
        if part['path'] != expected_path or part['bytes'] > 100_000_000:
            raise ValueError('Unexpected volume path or size')
        data = (root / part['path']).read_bytes()
        if len(data) != part['bytes'] or digest(data) != part['sha256']:
            raise ValueError('Volume checksum mismatch: ' + cc)
        payloads.append(data)
    payload = b''.join(payloads)
    if len(payload) != row['bytes'] or digest(payload) != row['sha256']:
        raise ValueError('Reassembled archive checksum mismatch')
    expected = {cc + '/' + name for name in COUNTRY_FILES} | {'NOTICE.md'}
    destination = (destination_root if destination_root is not None else root / 'countries') / cc
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        entries = archive.infolist()
        if set(row['members']) != expected or set(archive.namelist()) != expected or len(entries) != len(expected):
            raise ValueError('Unexpected or duplicate archive members')
        verified = {}
        for entry in entries:
            spec = row['members'][entry.filename]
            if entry.file_size != spec['bytes'] or entry.file_size > 100_000_000:
                raise ValueError('Unexpected member size')
            data = archive.read(entry)
            if digest(data) != spec['sha256']:
                raise ValueError('Member checksum mismatch')
            verified[entry.filename] = data
        destination.mkdir(parents=True, exist_ok=True)
        for name in COUNTRY_FILES:
            target = destination / name
            if target.exists() and target.read_bytes() != verified[cc + '/' + name]:
                raise ValueError('Refusing to overwrite different local data: ' + str(target))
        for name in COUNTRY_FILES:
            (destination / name).write_bytes(verified[cc + '/' + name])
    return destination


def pack():
    manifest = json.loads((ROOT / 'manifest.json').read_text(encoding='utf-8'))
    rows = [pack_country(item['country']) for item in manifest['countries']]
    write_json(ROOT / 'archives.json', dict(schema_version=2, total_rows=manifest['total_rows'],
                                          archives=rows, roundtrip_verification='pass'))
    print(json.dumps(dict(status='pass', countries=len(rows), bytes=sum(r['bytes'] for r in rows))))


def unpack(country=None):
    inventory = json.loads((ROOT / 'archives.json').read_text(encoding='utf-8'))
    if country and country not in {r['country'] for r in inventory['archives']}:
        raise ValueError('Country not published in this release')
    for row in inventory['archives']:
        if country is None or row['country'] == country:
            unpack_record(row)
            print(row['country'] + ': verified and unpacked', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['pack', 'unpack'])
    parser.add_argument('--country', help='Unpack only the named alpha-2 country/area profile')
    args = parser.parse_args()
    if args.command == 'pack':
        if args.country:
            parser.error('--country applies only to unpack')
        pack()
    else:
        unpack(args.country)
