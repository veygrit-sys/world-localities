"""Pinned, offline parsing for six European official address source candidates.

Source discovery is separate from acceptance. An unpinned, unreviewed file is
never treated as a verified address register or proof of deliverability.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / 'docs/plans/europe-six-sources.json'
COUNTRIES = frozenset(('LT', 'LV', 'SI', 'HR', 'AT', 'SE'))
FORMATS = frozenset(('csv', 'csv_zip', 'jsonl', 'geojson', 'gml', 'gpkg'))
FIELDS = frozenset(('id', 'name', 'locality', 'street', 'number', 'postcode',
                    'parent_id', 'status', 'x', 'y'))


def catalog(path=CATALOG):
    doc = json.loads(Path(path).read_text(encoding='utf-8'))
    if doc.get('schema_version') != 1 or set(doc.get('countries', {})) != COUNTRIES:
        raise ValueError('Six-country catalog scope differs')
    for code, item in doc['countries'].items():
        if not item.get('official_url', '').startswith('https://'):
            raise ValueError('Missing HTTPS official source: ' + code)
        if item.get('national_completeness_verified') is not False:
            raise ValueError('Do not assert nationwide completeness')
        if item.get('deliverability_verified') is not False:
            raise ValueError('Do not assert deliverability')
        if item['access'] not in ('public', 'registration_review', 'terms_review'):
            raise ValueError('Unknown source-access state')
    return doc


def safe_file(root, relative):
    root = Path(root).resolve()
    value = Path(relative)
    if value.is_absolute() or '..' in value.parts or value == Path('.'):
        raise ValueError('Unsafe source path')
    full = (root / value).resolve()
    if not full.is_relative_to(root) or not full.is_file():
        raise ValueError('Source missing or escapes data root')
    return full


def verify_pin(pin, source_root):
    if pin.get('country') not in COUNTRIES or pin.get('format') not in FORMATS:
        raise ValueError('Unknown country or file format')
    if pin.get('rights_reviewed') is not True:
        raise ValueError('Usage rights must be reviewed for this snapshot')
    if not pin.get('source_id') or not pin.get('snapshot_date'):
        raise ValueError('Source ID and snapshot date are mandatory')
    if type(pin.get('bytes')) is not int or pin['bytes'] <= 0:
        raise ValueError('Invalid expected file size')
    if not re.fullmatch(r'[0-9a-f]{64}', pin.get('sha256', '')):
        raise ValueError('Invalid SHA-256 pin')
    fields = pin.get('fields', {})
    if (not isinstance(fields, dict) or 'id' not in fields or not set(fields) <= FIELDS
            or any(not isinstance(v, str) or not v for v in fields.values())
            or pin.get('kind') not in ('address', 'street', 'locality', 'administrative')):
        raise ValueError('Explicit approved field mapping and kind are required')
    if not isinstance(pin.get('coordinate_crs'), str) or not pin['coordinate_crs']:
        raise ValueError('CRS must be explicit, including unknown')
    if pin['format'] == 'csv_zip' and not pin.get('member'):
        raise ValueError('ZIP member must be selected explicitly')
    if pin['format'] in ('gml', 'gpkg') and not pin.get('record_selector'):
        raise ValueError('GML record tag or GeoPackage table must be selected')
    path = safe_file(source_root, pin['path'])
    if path.stat().st_size != pin['bytes']:
        raise ValueError('Pinned source size differs')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    if digest.hexdigest() != pin['sha256']:
        raise ValueError('Pinned source hash differs')
    return path


def _csv_rows(binary, pin):
    delimiter = pin.get('delimiter', ',')
    encoding = pin.get('encoding', 'utf-8-sig')
    if delimiter not in (',', ';', '\t') or encoding not in ('utf-8', 'utf-8-sig', 'cp1250'):
        raise ValueError('CSV delimiter/encoding must be declared')
    with io.TextIOWrapper(binary, encoding=encoding, newline='') as text:
        reader = csv.DictReader(text, delimiter=delimiter)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError('Missing or duplicate headers')
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError('Malformed CSV row')
            yield row


def _gml_rows(path, pin):
    # DTD and entity expansion are not permitted. Prevent them before iterparse.
    with path.open('rb') as f:
        carry = b''
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            upper = (carry + chunk).upper()
            if b'<!DOCTYPE' in upper or b'<!ENTITY' in upper:
                raise ValueError('Unsafe XML declaration')
            carry = upper[-16:]
    tag = pin['record_selector']
    if not re.fullmatch(r'[A-Za-z][\w.-]*', tag):
        raise ValueError('Invalid GML record selector')
    context = ET.iterparse(str(path), events=('start', 'end'))
    stack = []
    for event, element in context:
        if event == 'start':
            stack.append(element)
            continue
        if element.tag.rsplit('}', 1)[-1] == tag:
            row = {}
            for part in element.iter():
                if len(part):
                    continue
                key = part.tag.rsplit('}', 1)[-1]
                if key in row:
                    raise ValueError('Repeated GML leaf requires specific schema adapter')
                row[key] = part.text or ''
            yield row
            if len(stack) > 1:
                stack[-2].remove(element)
            element.clear()
        stack.pop()


def _gpkg_rows(path, pin):
    table = pin['record_selector']
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', table):
        raise ValueError('Unsafe GeoPackage table')
    conn = sqlite3.connect(f'file:{path.as_posix()}?mode=ro', uri=True)
    try:
        known = {r[0] for r in conn.execute('SELECT table_name FROM gpkg_contents')}
        if table not in known:
            raise ValueError('Unlisted GeoPackage table')
        required = set(pin['fields'].values())
        columns = {r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')}
        if not required <= columns:
            raise ValueError('GeoPackage mapping fields missing')
        names = sorted(required)
        query = 'SELECT ' + ','.join('"' + x + '"' for x in names) + f' FROM "{table}"'
        for values in conn.execute(query):
            yield {k: '' if v is None else str(v) for k, v in zip(names, values)}
    finally:
        conn.close()


def source_rows(path, pin):
    fmt = pin['format']
    if fmt == 'csv':
        with path.open('rb') as stream:
            yield from _csv_rows(stream, pin)
    elif fmt == 'csv_zip':
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            member = pin['member']
            if len(names) != len(set(names)) or member not in names or any(
                    p.startswith('/') or '..' in Path(p).parts or '\\' in p for p in names):
                raise ValueError('Unsafe ZIP members')
            meta = archive.getinfo(member)
            if meta.file_size > 10_000_000_000:
                raise ValueError('Unexpected ZIP expansion')
            with archive.open(member) as stream:
                yield from _csv_rows(stream, pin)
    elif fmt == 'jsonl':
        with path.open('r', encoding='utf-8-sig') as stream:
            for line in stream:
                if line.strip():
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError('JSONL record must be object')
                    yield row
    elif fmt == 'geojson':
        if path.stat().st_size > 100_000_000:
            raise ValueError('Large GeoJSON requires streaming conversion to JSONL')
        value = json.loads(path.read_text(encoding='utf-8-sig'))
        if value.get('type') != 'FeatureCollection':
            raise ValueError('Only FeatureCollection supported')
        for feature in value['features']:
            if feature.get('type') != 'Feature' or not isinstance(feature.get('properties'), dict):
                raise ValueError('Invalid GeoJSON feature')
            yield feature['properties']
    elif fmt == 'gml':
        yield from _gml_rows(path, pin)
    elif fmt == 'gpkg':
        yield from _gpkg_rows(path, pin)


def normalized(row, pin):
    fields = pin['fields']
    missing = [key for key in fields.values() if key not in row]
    if missing:
        raise ValueError('Missing approved source columns: ' + repr(missing))
    source_id = row[fields['id']]
    if source_id is None or str(source_id) == '':
        raise ValueError('Source record ID must not be blank')
    properties = {name: str(row[source_field]) if row[source_field] is not None else ''
                  for name, source_field in fields.items()}
    return {'country': pin['country'], 'source': pin['source_id'],
            'source_record_id': str(source_id), 'kind': pin['kind'],
            'snapshot_date': pin['snapshot_date'], 'properties': properties,
            'coordinate_crs': pin['coordinate_crs'], 'validation_level': 'source_record_only',
            'delivery_status': 'not_verified'}


def normalize(pin, source_root, target):
    path = verify_pin(pin, source_root)
    target = Path(target)
    if target.exists() or target.is_symlink():
        raise ValueError('Output exists; do not overwrite')
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + '.partial')
    if partial.exists() or partial.is_symlink():
        raise ValueError('Previous partial output requires review')
    count = 0
    try:
        with tempfile.TemporaryDirectory() as temp:
            conn = sqlite3.connect(str(Path(temp) / 'seen.db'))
            try:
                conn.execute('CREATE TABLE seen (id TEXT PRIMARY KEY)')
                with partial.open('x', encoding='utf-8', newline='\n') as output:
                    for row in source_rows(path, pin):
                        record = normalized(row, pin)
                        try:
                            conn.execute('INSERT INTO seen VALUES (?)', (record['source_record_id'],))
                        except sqlite3.IntegrityError as exc:
                            raise ValueError('Duplicate source record ID') from exc
                        output.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + '\n')
                        count += 1
                if count == 0:
                    raise ValueError('No source rows found')
            finally:
                conn.close()
        partial.rename(target)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return {'country': pin['country'], 'source_id': pin['source_id'], 'records': count,
            'validation_level': 'source_record_only', 'national_completeness_verified': False,
            'deliverability_verified': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['catalog', 'audit', 'normalize'])
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'catalog':
            result = catalog()
        else:
            if not args.manifest or not args.data_root:
                raise ValueError('Explicit --manifest and --data-root required')
            pin = json.loads(args.manifest.read_text(encoding='utf-8'))
            path = verify_pin(pin, args.data_root)
            if args.command == 'audit':
                result = {'country': pin['country'], 'source': pin['source_id'],
                          'bytes_verified': path.stat().st_size, 'sha256_verified': True,
                          'national_completeness_verified': False, 'deliverability_verified': False}
            else:
                if not args.output:
                    raise ValueError('--output required')
                result = normalize(pin, args.data_root, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, UnicodeError, ET.ParseError, zipfile.BadZipFile,
            sqlite3.DatabaseError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
