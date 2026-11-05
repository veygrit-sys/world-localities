"""Offline, checksum-pinned intakes for the five priority European countries.

FR and NL keep their existing accepted official-source parsers. CZ reads RUIAN CSV
address points; DK captures source-qualified DAR entities without unsafe joins;
PL surveys GML schema before a format-specific parser can be approved.
No record produced by this utility claims deliverability or national completeness.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
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
CATALOG = ROOT / 'docs/plans/europe-five-country-sources.json'
CZ_REQUIRED = ('Kód ADM', 'Kód obce', 'Název obce', 'Kód části obce',
               'Název části obce', 'Kód ulice', 'Název ulice', 'Typ SO',
               'Číslo domovní', 'Číslo orientační', 'Znak čísla orientačního',
               'PSČ', 'Souřadnice Y', 'Souřadnice X', 'Platí Od')
DK_FIELDS = {
    'Adresse': ('husnummer',),
    'Husnummer': ('navngivenVej', 'postnummer'),
    'NavngivenVej': (),
    'Postnummer': (),
    'Adressepunkt': (),
}
HEX = re.compile(r'[0-9a-f]{64}\Z')
DIGITS = re.compile(r'[0-9]+\Z')


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def pin(path, expected):
    if not HEX.fullmatch(expected):
        raise ValueError('Expected SHA-256 must be a lowercase 64-digit hex string')
    if not path.is_file() or sha256(path) != expected:
        raise ValueError('Input is missing or SHA-256 does not match the supplied source pin')
    return {'sha256': expected, 'bytes': path.stat().st_size}


def date_string(value):
    date.fromisoformat(value)
    return value


def check_zip(archive, suffix):
    files = archive.infolist()
    paths = [x.filename for x in files]
    if len(paths) != len(set(paths)):
        raise ValueError('Duplicate ZIP members')
    for info in files:
        name = info.filename
        if (not name or '\\' in name or ':' in name or name.startswith('/')
                or '..' in Path(name).parts or info.flag_bits & 1):
            raise ValueError('Unsafe or encrypted ZIP member')
        if info.file_size > 2 * 1024**3:
            raise ValueError('Unexpectedly large ZIP member')
    return sorted((x for x in files if not x.is_dir() and x.filename.lower().endswith(suffix)),
                  key=lambda x: x.filename)


def csv_streams(source, encoding):
    """Return context-managed iterator of (filename, text stream), no extraction."""
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            members = check_zip(archive, '.csv')
            if not members:
                raise ValueError('ZIP has no CSV members')
            for member in members:
                with archive.open(member) as binary:
                    with io.TextIOWrapper(binary, encoding=encoding, newline='') as stream:
                        yield member.filename, stream
    elif source.suffix.lower() == '.csv':
        with source.open('r', encoding=encoding, newline='') as stream:
            yield source.name, stream
    else:
        raise ValueError('Expected a CSV or a ZIP of CSV files')


def read_csv(stream, delimiter, required, member):
    reader = csv.DictReader(stream, delimiter=delimiter)
    fields = reader.fieldnames or []
    if not fields or len(fields) != len(set(fields)) or not set(required) <= set(fields):
        raise ValueError('CSV header missing, changed or duplicated in ' + member)
    for number, row in enumerate(reader, 2):
        if None in row or any(value is None for value in row.values()):
            raise ValueError('Malformed CSV at ' + member + ':' + str(number))
        yield number, row


def coordinate(value):
    if not value:
        return None
    try:
        coordinate_value = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError('Invalid S-JTSK coordinate') from exc
    if not coordinate_value.is_finite():
        raise ValueError('Non-finite S-JTSK coordinate')
    return value  # Keep lexical source precision; do not pretend WGS84.


def cz_record(row, member, line):
    identity = row['Kód ADM'].strip()
    code = row['Kód obce'].strip()
    if not DIGITS.fullmatch(identity) or not DIGITS.fullmatch(code):
        raise ValueError('Invalid RÚIAN address or municipality identifier')
    if not row['Název obce'].strip() or not DIGITS.fullmatch(row['Číslo domovní'].strip()):
        raise ValueError('RÚIAN municipality or building number missing')
    postcode = row['PSČ'].strip()
    if postcode and not re.fullmatch(r'[0-9]{5}', postcode):
        raise ValueError('Invalid RÚIAN postcode')
    valid_from = row['Platí Od'].strip()
    if valid_from:
        date_string(valid_from[:10])
        if len(valid_from) > 10 and valid_from[10] not in ('T', ' '):
            raise ValueError('Invalid RÚIAN validity timestamp')
    y, x = coordinate(row['Souřadnice Y'].strip()), coordinate(row['Souřadnice X'].strip())
    return {'country': 'CZ', 'kind': 'address_point', 'source_registry': 'RÚIAN',
            'source_id': identity, 'qualified_id': 'CZ:RUIAN:' + identity,
            'municipality': {'id': code, 'name': row['Název obce']},
            'municipality_part': {'id': row['Kód části obce'], 'name': row['Název části obce']},
            'street': {'id': row['Kód ulice'], 'name': row['Název ulice']},
            'house': {'type': row['Typ SO'], 'building_number': row['Číslo domovní'],
                      'orientation_number': row['Číslo orientační'],
                      'orientation_suffix': row['Znak čísla orientačního']},
            'postcode': postcode, 'source_point': {'crs': 'S-JTSK', 'y_m': y, 'x_m': x},
            'valid_from_source': valid_from, 'member': member, 'line': line, 'raw': row,
            'deliverability_verified': False, 'national_completeness_verified': False}


def dk_record(row, member, line, entity, mode):
    identity = row['id_lokalId'].strip()
    if not identity:
        raise ValueError('DAR entity missing id_lokalId')
    references = {key: row[key] for key in DK_FIELDS[entity]}
    return {'country': 'DK', 'kind': 'registry_entity', 'source_registry': 'DAR',
            'entity': entity, 'source_id': identity,
            'qualified_id': 'DK:DAR:' + entity + ':' + identity,
            'references': references, 'extract_mode': mode,
            'temporal_join_verified': False, 'member': member, 'line': line,
            'raw': row, 'deliverability_verified': False,
            'national_completeness_verified': False}


def normalize(args):
    if args.country not in ('CZ', 'DK'):
        raise ValueError('Normalization is currently approved for CZ and DK entity capture only')
    if args.country == 'DK' and args.entity not in DK_FIELDS:
        raise ValueError('Select a supported DAR entity')
    if args.country == 'CZ' and args.entity:
        raise ValueError('Czech input has no DAR entity')
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('Output already exists; refusing overwrite')
    date_string(args.source_date)
    receipt = pin(args.input, args.sha256)
    rows, members = 0, []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Source-supplied rows can be millions: use an on-disk unique index.
    with tempfile.TemporaryDirectory(prefix='europe-audit-') as temp:
        db = sqlite3.connect(str(Path(temp) / 'ids.db'))
        db.execute('CREATE TABLE ids (id TEXT PRIMARY KEY)')
        temporary = args.output.with_name(args.output.name + '.partial')
        if temporary.exists() or temporary.is_symlink():
            raise ValueError('An incomplete prior output needs explicit review')
        try:
            with temporary.open('x', encoding='utf-8', newline='\n') as out:
                for member, stream in csv_streams(args.input, 'cp1250' if args.country == 'CZ' else args.encoding):
                    members.append(member)
                    required = CZ_REQUIRED if args.country == 'CZ' else ('id_lokalId',) + DK_FIELDS[args.entity]
                    iterator = read_csv(stream, ';' if args.country == 'CZ' else args.delimiter, required, member)
                    for line, raw in iterator:
                        record = (cz_record(raw, member, line) if args.country == 'CZ'
                                  else dk_record(raw, member, line, args.entity, args.mode))
                        try:
                            db.execute('INSERT INTO ids (id) VALUES (?)', (record['qualified_id'],))
                        except sqlite3.IntegrityError as exc:
                            raise ValueError('Duplicate source-qualified identifier: ' + record['qualified_id']) from exc
                        out.write(json.dumps(record, ensure_ascii=False, sort_keys=True, allow_nan=False) + '\n')
                        rows += 1
                if not rows:
                    raise ValueError('No parsed address/entity rows')
            # Leave existing inputs untouched; output becomes visible only after full pass.
            temporary.rename(args.output)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        finally:
            db.close()
    return {'country': args.country, 'entity': args.entity, 'records': rows,
            'members': len(members), 'source_date': args.source_date,
            'source_pin': receipt, 'normalized_sha256': sha256(args.output),
            'output': str(args.output), 'status': 'SOURCE_ROWS_NORMALIZED_NOT_VALIDATED_FOR_DELIVERY',
            'national_completeness_verified': False, 'deliverability_verified': False}


class GuardedXML:
    def __init__(self, stream):
        self.stream, self.tail = stream, b''

    def read(self, size=-1):
        chunk = self.stream.read(size)
        window = (self.tail + chunk).upper()
        if b'<!DOCTYPE' in window or b'<!ENTITY' in window:
            raise ValueError('GML DTD/entity declarations not permitted')
        self.tail = window[-16:]
        return chunk


def survey_pl(args):
    if args.country != 'PL':
        raise ValueError('GML schema survey is for PL only')
    date_string(args.source_date)
    receipt = pin(args.input, args.sha256)
    counts, roots = Counter(), []
    if zipfile.is_zipfile(args.input):
        archive = zipfile.ZipFile(args.input)
        members = check_zip(archive, '.gml')
        if not members:
            archive.close()
            raise ValueError('PRG source ZIP contains no GML')
        def streams():
            with archive:
                for info in members:
                    with archive.open(info) as stream:
                        yield info.filename, stream
    elif args.input.suffix.lower() == '.gml':
        def streams():
            with args.input.open('rb') as stream:
                yield args.input.name, stream
    else:
        raise ValueError('Expected a PRG GML or ZIP with GML')
    for name, stream in streams():
        first, depth = None, 0
        for event, element in ET.iterparse(GuardedXML(stream), events=('start', 'end')):
            if event == 'start':
                depth += 1
                if first is None:
                    first = element.tag
                counts[element.tag] += 1
            else:
                element.clear()
                depth -= 1
        if depth != 0 or first is None:
            raise ValueError('Empty or unbalanced GML')
        roots.append({'member': name, 'root_qname': first})
    return {'country': 'PL', 'source_date': args.source_date, 'source_pin': receipt,
            'files': roots, 'xml_elements_by_qname': dict(sorted(counts.items())),
            'status': 'SCHEMA_SURVEY_ONLY', 'format_verified': False,
            'address_rows_normalized': 0, 'deliverability_verified': False,
            'national_completeness_verified': False}


def inventory():
    catalog = json.loads(CATALOG.read_text(encoding='utf-8'))
    if list(catalog['country_codes']) != ['FR', 'NL', 'PL', 'CZ', 'DK']:
        raise ValueError('Priority country scope changed')
    fr = json.loads((ROOT / 'releases/hierarchy/western-europe/official-sources.json').read_text())
    nl = json.loads((ROOT / 'releases/hierarchy/western-europe/netherlands/official-sources.json').read_text())
    return {'countries': catalog['countries'],
            'pinned_legacy_source_files': {'FR': sum(s['country'] == 'FR' for s in fr['sources']),
                                           'NL': len(nl['sources'])},
            'national_completeness_verified': False, 'deliverability_verified': False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inventory', 'normalize', 'survey-pl'))
    parser.add_argument('--country', choices=('FR', 'NL', 'PL', 'CZ', 'DK'))
    parser.add_argument('--input', type=Path)
    parser.add_argument('--sha256')
    parser.add_argument('--source-date')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--entity', choices=tuple(DK_FIELDS))
    parser.add_argument('--mode', choices=('current', 'temporal', 'bitemporal'), default='current')
    parser.add_argument('--delimiter', choices=(';', ','), default=',')
    parser.add_argument('--encoding', choices=('utf-8-sig', 'utf-8', 'cp1252'), default='utf-8-sig')
    args = parser.parse_args(argv)
    try:
        if args.command != 'inventory' and any(not value for value in (args.country, args.input, args.sha256, args.source_date)):
            raise ValueError('Country, input, source date and SHA-256 pin required')
        if args.command == 'inventory':
            report = inventory()
        elif args.command == 'normalize':
            if args.output is None:
                raise ValueError('A nonexisting --output is required')
            report = normalize(args)
        else:
            report = survey_pl(args)
            if args.output is not None:
                if args.output.exists() or args.output.is_symlink():
                    raise ValueError('Output already exists')
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (OSError, KeyError, ValueError, UnicodeError, zipfile.BadZipFile, ET.ParseError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    sys.exit(main())

