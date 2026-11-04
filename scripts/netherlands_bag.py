"""Pinned Dutch BAG object histories and CBS administrative references.

National number designations and named public spaces are separate registers;
neither implies an inventory of every physical road or deliverability.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re
import sqlite3
import struct
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile
import zlib

import western_europe_sources as shared

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / 'releases/hierarchy/western-europe/netherlands/official-sources.json'
OBJECT_NS = 'www.kadaster.nl/schemas/lvbag/imbag/objecten/v20200601'
HISTORY_NS = 'www.kadaster.nl/schemas/lvbag/imbag/historie/v20200601'
REF_NS = 'www.kadaster.nl/schemas/lvbag/imbag/objecten-ref/v20200601'
GWR_NS = 'www.kadaster.nl/schemas/lvbag/gem-wpl-rel/gwr-producten-lvc/v20200601'
EXTRACT_NS = 'http://www.kadaster.nl/schemas/lvbag/extract-deelbestand-lvc/v20200601'
SELECT_NS = 'http://www.kadaster.nl/schemas/lvbag/extract-selecties/v20200601'
INVESTIGATION_NS = 'www.kadaster.nl/schemas/lvbag/imbag/kenmerkinonderzoek/v20200601'
STAND_NS = 'http://www.kadaster.nl/schemas/standlevering-generiek/1.0'
NS = {'o': OBJECT_NS, 'h': HISTORY_NS, 'r': REF_NS, 'g': GWR_NS}
ROLES = {'number_designations', 'public_spaces', 'localities',
         'municipality_locality_links', 'not_bag', 'investigations', 'inactive',
         'delivery_document', 'municipalities'}


def fetch_range(container, start, length):
    """Require an exact, same-version byte range; never accept an ignored Range."""
    parsed = urlsplit(container['url'])
    if (parsed.scheme != 'https' or parsed.hostname != 'service.pdok.nl'
            or parsed.path != '/kadaster/bag/atom/downloads/lvbag-extract-nl.zip'
            or parsed.query or parsed.fragment or start < 0 or length <= 0
            or start + length > container['bytes']):
        raise ValueError('Invalid BAG container or byte range')
    end = start + length - 1
    response = urlopen(Request(container['url'], headers={
        'Range': f'bytes={start}-{end}', 'If-Match': container['etag'],
        'User-Agent': 'WorldLocalities-BAG/1.0'}), timeout=50)
    if (response.status != 206 or response.geturl() != container['url']
            or response.headers.get('Content-Range') != f'bytes {start}-{end}/{container["bytes"]}'
            or response.headers.get('ETag') != container['etag']
            or int(response.headers.get('Content-Length', '-1')) != length):
        response.close()
        raise ValueError('BAG range or container version changed')
    return response


def download_member(container, pin, path):
    """Recover original inner ZIP bytes, checking outer size, CRC and SHA pin.

    The outer archive is not retained or claimed to be fully byte-verified.
    Its central directory and the selected members are preserved separately.
    """
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise ValueError('Use a new output for a candidate source')
    temporary = path.with_name(path.name + '.partial')
    if temporary.exists() or temporary.is_symlink():
        raise ValueError('Prior incomplete download needs explicit review')
    with fetch_range(container, pin['offset'], 30) as response:
        header = response.read()
    if len(header) != 30:
        raise ValueError('Truncated ZIP local header')
    values = struct.unpack('<4s5H3I2H', header)
    name_size, extra_size = values[-2:]
    if values[0] != b'PK\x03\x04' or values[3] != pin['method'] or values[2] & 1:
        raise ValueError('Unexpected ZIP local header')
    with fetch_range(container, pin['offset'] + 30, name_size + extra_size) as response:
        extra = response.read()
    name = extra[:name_size].decode('utf-8' if values[2] & 2048 else 'cp437')
    if name != pin['container_member'] or len(extra) != name_size + extra_size:
        raise ValueError('ZIP member name differs')
    if pin['method'] not in (0, 8):
        raise ValueError('Unsupported ZIP compression')
    start = pin['offset'] + 30 + name_size + extra_size
    path.parent.mkdir(parents=True, exist_ok=True)
    digest, crc, written, received = hashlib.sha256(), 0, 0, 0
    inflater = zlib.decompressobj(-15) if pin['method'] == 8 else None
    created_partial = False
    try:
        with fetch_range(container, start, pin['compressed_bytes']) as response, temporary.open('xb') as output:
            created_partial = True
            for block in iter(lambda: response.read(1024 * 1024), b''):
                received += len(block)
                decoded = inflater.decompress(block) if inflater is not None else block
                written += len(decoded)
                if written > pin['bytes']:
                    raise ValueError('Unexpected expanded source size')
                output.write(decoded)
                digest.update(decoded)
                crc = zlib.crc32(decoded, crc)
        if (received != pin['compressed_bytes'] or written != pin['bytes']
                or f'{crc:08x}' != pin['crc32']
                or (inflater is not None and (not inflater.eof or inflater.unused_data))
                or ('sha256' in pin and digest.hexdigest() != pin['sha256'])):
            raise ValueError('Recovered ZIP member bytes differ')
        path.hardlink_to(temporary)
        return {'bytes': written, 'sha256': digest.hexdigest(), 'outer_crc32': f'{crc:08x}'}
    finally:
        if created_partial:
            temporary.unlink(missing_ok=True)


def load_manifest(path=DEFAULT_MANIFEST):
    value = json.loads(Path(path).read_text(encoding='utf-8'))
    if (value.get('schema_version') != 1 or value.get('region') != 'western-europe'
            or value.get('country') != 'NL'
            or value.get('national_completeness_verified') is not False
            or value.get('deliverability_in_scope') is not False):
        raise ValueError('Invalid Dutch source manifest or scope')
    date.fromisoformat(value['snapshot_date'])
    sources = value['sources']
    if {s['role'] for s in sources} != ROLES or len(sources) != len(ROLES):
        raise ValueError('Missing or duplicate Dutch source roles')
    for field in ('id', 'path'):
        if len({s[field] for s in sources}) != len(sources):
            raise ValueError('Duplicate source ' + field)
    for pin in sources + value.get('evidence', []):
        if (type(pin['bytes']) is not int or pin['bytes'] <= 0
                or not re.fullmatch('[0-9a-f]{64}', pin['sha256'])
                or pin.get('country') != 'NL'):
            raise ValueError('Invalid Dutch source byte pin')
        shared.source_path(Path('.'), pin)
    for pin in sources:
        expected = ('cbs_xlsx' if pin['role'] == 'municipalities' else
                    'bag_xml' if pin['role'] == 'delivery_document' else 'bag_xml_zip')
        if pin['format'] != expected:
            raise ValueError('Source role and format differ')
        if 'container_member' in pin:
            if (Path(pin['container_member']).name != pin['container_member']
                    or pin['method'] not in (0, 8)
                    or not re.fullmatch('[0-9a-f]{8}', pin['crc32'])):
                raise ValueError('Unsafe ZIP source member')
    return value


def local_name(tag):
    return tag.rsplit('}', 1)[-1]


def one(element, path, required=True):
    matches = element.findall(path, NS)
    if len(matches) > 1 or (required and (len(matches) != 1 or matches[0].text is None)):
        raise ValueError('Missing or duplicate XML field: ' + path)
    return matches[0].text if matches else None


def raw_leaves(element):
    """Expose source lexical values; full geometry and namespaces stay in raw ZIPs."""
    result = {}

    def visit(node, prefix=''):
        for child in node:
            field = prefix + local_name(child.tag)
            if local_name(child.tag) == 'geometrie':
                continue
            if len(child):
                visit(child, field + '/')
            else:
                if field in result:
                    raise ValueError('Repeated source field needs review: ' + field)
                result[field] = child.text
                if child.attrib:
                    result[field + '/@attributes'] = dict(child.attrib)
    visit(element)
    return result


def open_at_snapshot(history, status, snapshot, category):
    if category != 'main' or status not in ('Naamgeving uitgegeven', 'Woonplaats aangewezen'):
        return False
    begin = history['beginGeldigheid']
    end = history.get('eindGeldigheid')
    date.fromisoformat(begin)
    if end:
        date.fromisoformat(end)
    closed = ('eindRegistratie', 'tijdstipInactief', 'tijdstipEindRegistratieLV',
              'tijdstipInactiefLV', 'tijdstipNietBagLV')
    return begin <= snapshot and (not end or end > snapshot) and not any(history.get(k) for k in closed)


def object_record(element, source, member, ordinal, snapshot, category):
    typename = local_name(element.tag)
    identity = one(element, 'o:identificatie')
    if not re.fullmatch('[0-9]{4}' if typename == 'Woonplaats' else '[0-9]{16}', identity):
        raise ValueError('Unexpected BAG object identifier')
    status = one(element, 'o:status')
    history_node = element.find('o:voorkomen/h:Voorkomen', NS)
    if history_node is None:
        raise ValueError('Missing BAG object history')
    history = {local_name(e.tag): e.text for e in history_node.iter() if not len(e)}
    for field in ('voorkomenidentificatie', 'beginGeldigheid', 'tijdstipRegistratie', 'tijdstipRegistratieLV'):
        if not history.get(field):
            raise ValueError('Missing BAG history field: ' + field)
    current = open_at_snapshot(history, status, snapshot, category)
    kind = {'Nummeraanduiding': 'address', 'OpenbareRuimte': 'street', 'Woonplaats': 'locality'}[typename]
    values = dict(object_type=typename, history=history, status=status, source_category=category,
                  registry_open_at_snapshot=current, geconstateerd=one(element, 'o:geconstateerd'),
                  document_date=one(element, 'o:documentdatum'), document_number=one(element, 'o:documentnummer'),
                  snapshot_date=snapshot)
    if typename == 'Nummeraanduiding':
        values.update(number=one(element, 'o:huisnummer'), house_letter=one(element, 'o:huisletter', False),
                      number_addition=one(element, 'o:huisnummertoevoeging', False),
                      postcode=one(element, 'o:postcode', False),
                      addressable_object_type=one(element, 'o:typeAdresseerbaarObject'),
                      street_id=one(element, 'o:ligtAan/r:OpenbareRuimteRef'),
                      locality_override_id=one(element, 'o:ligtIn/r:WoonplaatsRef', False))
        if not re.fullmatch('[0-9]{16}', values['street_id']):
            raise ValueError('Invalid BAG public-space reference')
    elif typename == 'OpenbareRuimte':
        values.update(street_names={'nl': one(element, 'o:naam')},
                      public_space_type=one(element, 'o:type'),
                      locality_id=one(element, 'o:ligtIn/r:WoonplaatsRef'))
        if values['public_space_type'] != 'Weg':
            kind = 'named_area'
    else:
        values.update(name=one(element, 'o:naam'), geometry_reference={
            'source_crs': 'EPSG:28992', 'member': member, 'object_ordinal': ordinal})
    if category != 'main':
        kind = category + '_' + kind + '_history'
    return shared.observation(source, member, ordinal, raw_leaves(element), kind, identity, **values)


class GuardedXML:
    def __init__(self, stream):
        self.stream, self.tail = stream, b''

    def read(self, size=-1):
        block = self.stream.read(size)
        window = (self.tail + block).upper()
        if b'<!DOCTYPE' in window or b'<!ENTITY' in window:
            raise ValueError('DTD and entity declarations are not accepted')
        self.tail = window[-16:]
        return block


def xml_records(stream, source, member, snapshot, category):
    stack, ordinal, technical_date, national = [], 0, None, False
    is_gwr = source['role'] == 'municipality_locality_links'
    expected_root = ('www.kadaster.nl/schemas/lvbag/gem-wpl-rel/gwr-deelbestand-lvc/v20200601'
                     + '}BAG-GWR-Deelbestand-LVC' if is_gwr else EXTRACT_NS + '}bagStand')
    targets = {'{' + OBJECT_NS + '}' + x for x in ('Nummeraanduiding', 'OpenbareRuimte', 'Woonplaats')}
    gwr_tag = '{' + GWR_NS + '}GemeenteWoonplaatsRelatie'
    expected_object = {'number_designations': 'Nummeraanduiding', 'public_spaces': 'OpenbareRuimte',
                       'localities': 'Woonplaats'}.get(source['role'])
    for event, element in ET.iterparse(GuardedXML(stream), events=('start', 'end')):
        if event == 'start':
            if not stack and element.tag != '{' + expected_root:
                raise ValueError('Unexpected BAG XML root or schema namespace')
            stack.append(element)
            continue
        if element.tag == '{' + SELECT_NS + '}StandTechnischeDatum':
            technical_date = element.text
        if element.tag == '{' + SELECT_NS + '}Gebied-NLD':
            national = True
        if element.tag in targets or element.tag == gwr_tag or (
                category == 'investigation' and element.tag.startswith('{' + INVESTIGATION_NS + '}Kenmerk')
                and local_name(element.tag).endswith('InOnderzoek')):
            if technical_date != snapshot or (not is_gwr and not national):
                raise ValueError('BAG snapshot date or national selection differs')
            ordinal += 1
            if element.tag == gwr_tag:
                raw = raw_leaves(element)
                locality = one(element, 'g:gerelateerdeWoonplaats/g:identificatie')
                municipality = one(element, 'g:gerelateerdeGemeente/g:identificatie')
                begin = raw['tijdvakgeldigheid/begindatumTijdvakGeldigheid']
                end = raw.get('tijdvakgeldigheid/einddatumTijdvakGeldigheid')
                date.fromisoformat(begin)
                if end:
                    date.fromisoformat(end)
                status = one(element, 'g:status')
                if not re.fullmatch('[0-9]{4}', locality) or not re.fullmatch('[0-9]{4}', municipality):
                    raise ValueError('Invalid GWR reference identifier')
                row = shared.observation(source, member, ordinal, raw, 'municipality_locality_link',
                                         locality + ':' + municipality + ':' + begin,
                                         locality_id=locality, municipality_id=municipality,
                                         valid_from=begin, valid_until=end, status=status,
                                         registry_open_at_snapshot=begin <= snapshot and (not end or end > snapshot)
                                         and status == 'definitief',
                                         authoritative_bag_attribute=False)
            elif element.tag in targets:
                if expected_object and local_name(element.tag) != expected_object:
                    raise ValueError('BAG object type differs from source role')
                row = object_record(element, source, member, ordinal, snapshot, category)
            else:
                raw = raw_leaves(element)
                row = shared.observation(source, member, ordinal, raw, 'investigation',
                                         source['id'] + ':' + member + ':' + str(ordinal),
                                         investigation_type=local_name(element.tag), registry_open_at_snapshot=False)
            yield row
            if len(stack) > 1:
                stack[-2].remove(element)
            element.clear()
        elif element.tag in ('{' + EXTRACT_NS + '}bagObject', '{' + EXTRACT_NS + '}kenmerkInOnderzoek'):
            if len(element):
                raise ValueError('Unrecognized BAG object namespace or type')
        elif element.tag == '{' + STAND_NS + '}stand':
            if len(stack) > 1:
                stack[-2].remove(element)
            element.clear()
        stack.pop()
    if technical_date != snapshot or (not is_gwr and not national):
        raise ValueError('Missing BAG national selection or snapshot date')


def check_members(archive):
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError('Duplicate ZIP member')
    for name in names:
        if Path(name).name != name or '\\' in name or ':' in name or not name:
            raise ValueError('Unsafe Dutch ZIP member name')


def cbs_records(path, source):
    """Read the fixed official table by its named sheet and header, using OOXML."""
    ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with zipfile.ZipFile(path) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError('Duplicate XLSX member')
        strings = [''.join(n.itertext()) for n in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si', ns)]
        workbook = ET.fromstring(archive.read('xl/workbook.xml'))
        sheet = next((s for s in workbook.findall('s:sheets/s:sheet', ns)
                      if s.get('name') == 'Gemeenten_alfabetisch'), None)
        if sheet is None:
            raise ValueError('CBS municipality worksheet changed')
        relation = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
        rels = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        target = next((r.get('Target') for r in rels if r.get('Id') == relation), None)
        if not target or not re.fullmatch(r'worksheets/sheet[0-9]+\.xml', target):
            raise ValueError('Unsafe or changed worksheet relationship')
        member = 'xl/' + target
        sheet_data = ET.fromstring(archive.read(member))
        headers = None
        seen = set()
        expected = ['Gemeentecode', 'GemeentecodeGM', 'Gemeentenaam', 'Provinciecode', 'ProvinciecodePV', 'Provincienaam']
        for row in sheet_data.findall('s:sheetData/s:row', ns):
            cells = {}
            for cell in row:
                column = re.sub('[0-9]+$', '', cell.get('r', ''))
                if cell.find('s:f', ns) is not None or column in cells:
                    raise ValueError('Formula or duplicate cell in CBS reference')
                value = cell.findtext('s:v', default='', namespaces=ns)
                cells[column] = strings[int(value)] if cell.get('t') == 's' else value
            values = [cells.get(c, '') for c in 'ABCDEF']
            if headers is None:
                if values != expected:
                    raise ValueError('CBS municipality table headers changed')
                headers = values
                continue
            raw = dict(zip(headers, values))
            code, prefixed, name, province, pv, province_name = values
            if (not re.fullmatch('[0-9]{4}', code) or prefixed != 'GM' + code
                    or not re.fullmatch('[0-9]{2}', province) or pv != 'PV' + province
                    or not name or not province_name or code in seen):
                raise ValueError('Invalid or duplicate CBS municipality reference')
            seen.add(code)
            yield shared.observation(source, member, int(row.get('r')), raw, 'municipality', code,
                                     name=name, province_id=pv, province_name=province_name,
                                     reference_date='2026-01-01', registry_open_at_snapshot=True)
        if not seen:
            raise ValueError('Empty CBS municipality worksheet')
        if archive.testzip() is not None:
            raise ValueError('XLSX CRC differs')


def records(source, root, snapshot):
    path = shared.source_path(root, source)
    if source['role'] == 'municipalities':
        yield from cbs_records(path, source)
        return
    if source['role'] == 'delivery_document':
        document = ET.fromstring(path.read_bytes())
        technical = document.find('.//{' + SELECT_NS + '}StandTechnischeDatum')
        if (technical is None or technical.text != snapshot
                or document.find('.//{' + SELECT_NS + '}Gebied-NLD') is None):
            raise ValueError('Delivery document differs from national snapshot')
        yield shared.observation(source, path.name, 1, raw_leaves(document), 'delivery_document', source['id'])
        return
    category = {'not_bag': 'not_bag', 'inactive': 'inactive', 'investigations': 'investigation'}.get(source['role'], 'main')
    with zipfile.ZipFile(path) as archive:
        check_members(archive)
        for member in archive.namelist():
            if member.endswith('.xml'):
                with archive.open(member) as stream:
                    yield from xml_records(stream, source, member, snapshot, category)
            elif member.endswith('.zip') and category != 'main':
                # The source contains all seven object types. Keep and CRC-check all
                # nested ZIPs, but normalize only address/name/locality objects here.
                with zipfile.ZipFile(io.BytesIO(archive.read(member))) as inner:
                    check_members(inner)
                    selected = re.fullmatch('9999(?:IA|NB|IO)(?:NUM|OPR|WPL)[0-9]{8}.zip', member)
                    if selected:
                        for child in inner.namelist():
                            if not child.endswith('.xml'):
                                raise ValueError('Unexpected nested BAG member')
                            with inner.open(child) as stream:
                                yield from xml_records(stream, source, member + '/' + child, snapshot, category)
                    elif inner.testzip() is not None:
                        raise ValueError('Nested BAG CRC differs')
            else:
                raise ValueError('Unexpected source member type')


def source_by_role(manifest, role):
    return next(s for s in manifest['sources'] if s['role'] == role)


def reference_index(manifest, root):
    indexes = {'public_spaces': {}, 'localities': {}, 'municipality_locality_links': {}, 'municipalities': {}}
    historical_ids = {'public_spaces': set(), 'localities': set()}
    for role, index in indexes.items():
        source = source_by_role(manifest, role)
        shared.verify_pin(source, root)
        for row in records(source, root, manifest['snapshot_date']):
            key = row.get('locality_id') if role == 'municipality_locality_links' else row['source_id']
            if role in historical_ids:
                historical_ids[role].add(key)
            if row.get('registry_open_at_snapshot'):
                if key in index:
                    raise ValueError('Multiple open reference records: ' + role + ':' + key)
                # Geometry and raw XML are not needed in the join index.
                index[key] = {k: v for k, v in row.items() if k not in ('raw', 'geometry_reference')}
    return indexes, historical_ids


def address_references(row, indexes):
    """Join explicitly at the snapshot; never label old rows with current names."""
    public_space = indexes['public_spaces'].get(row['street_id'])
    locality_id = row.get('locality_override_id') or (public_space or {}).get('locality_id')
    locality = indexes['localities'].get(locality_id)
    link = indexes['municipality_locality_links'].get(locality_id)
    municipality = indexes['municipalities'].get((link or {}).get('municipality_id'))
    return public_space, locality, link, municipality


def audit(manifest, root, work_dir=None):
    for pin in manifest.get('evidence', []):
        shared.verify_pin(pin, root)
    indexes, historical_ids = reference_index(manifest, root)
    reports, issues, examples = [], Counter(), {}
    municipality_numbers, municipality_spaces = Counter(), Counter()
    with tempfile.TemporaryDirectory(prefix='bag-audit-', dir=work_dir) as temp:
        db = sqlite3.connect(str(Path(temp) / 'number-ids.sqlite'))
        try:
            db.execute('PRAGMA journal_mode=OFF')
            db.execute('PRAGMA synchronous=OFF')
            db.execute('CREATE TABLE number_ids(id TEXT PRIMARY KEY, observations INTEGER, open_records INTEGER) WITHOUT ROWID')
            batch = []
            for source in manifest['sources']:
                shared.verify_pin(source, root)
                digest, counts, statuses, members = hashlib.sha256(), Counter(), Counter(), Counter()
                for row in records(source, root, manifest['snapshot_date']):
                    digest.update(shared.canonical(row).encode('utf-8') + b'\n')
                    kind = row['kind']
                    counts[kind] += 1
                    if kind == 'address' and counts[kind] % 1000000 == 0:
                        print(shared.canonical({'source': source['id'], 'address_versions_read': counts[kind]}), flush=True)
                    members[row['member']] += 1
                    if row.get('status') is not None:
                        statuses[row['status']] += 1
                    if row.get('registry_open_at_snapshot'):
                        counts['registry_open_at_snapshot:' + kind] += 1
                    for field in ('house_letter', 'number_addition', 'locality_override_id'):
                        if row.get(field):
                            counts['with:' + field] += 1
                    if kind == 'address':
                        batch.append((row['source_id'], 1, int(row['registry_open_at_snapshot'])))
                        problem = []
                        if row['street_id'] not in historical_ids['public_spaces']:
                            problem.append('street_id_absent_from_main_public_space_history')
                        if row['registry_open_at_snapshot']:
                            space, locality, link, municipality = address_references(row, indexes)
                            if space is None:
                                problem.append('open_number_without_open_public_space')
                            if locality is None:
                                problem.append('open_number_without_open_locality')
                            if link is None:
                                problem.append('open_number_without_open_gwr_helper_link')
                            if municipality is None:
                                problem.append('open_number_without_cbs_municipality')
                            else:
                                municipality_numbers[municipality['source_id']] += 1
                        for reason in problem:
                            issues[reason] += 1
                            if len(examples.setdefault(reason, [])) < 10:
                                examples[reason].append(row['source_qualified_id'])
                        if len(batch) >= 20000:
                            db.executemany('INSERT INTO number_ids VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET '
                                           'observations=observations+excluded.observations, open_records=open_records+excluded.open_records', batch)
                            batch.clear()
                    if kind in ('street', 'named_area') and row['registry_open_at_snapshot']:
                        link = indexes['municipality_locality_links'].get(row['locality_id'])
                        if link is not None:
                            municipality_spaces[link['municipality_id']] += 1
                if batch:
                    db.executemany('INSERT INTO number_ids VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET '
                                   'observations=observations+excluded.observations, open_records=open_records+excluded.open_records', batch)
                    batch.clear()
                report = {'id': source['id'], 'role': source['role'], 'source_sha256': source['sha256'],
                          'canonical_rows_sha256': digest.hexdigest(), 'counts': dict(counts),
                          'source_status_counts': dict(statuses), 'member_rows': dict(members),
                          'source_integrity': 'PASS'}
                reports.append(report)
                print(shared.canonical({'source': source['id'], 'counts': dict(counts)}), flush=True)
            number_identity_counts = dict(zip(
                ('distinct_main_number_ids', 'ids_with_open_record', 'ids_with_multiple_open_records'),
                db.execute('SELECT COUNT(*),COALESCE(SUM(open_records>0),0),COALESCE(SUM(open_records>1),0) FROM number_ids').fetchone()))
        finally:
            db.close()
    expected_municipalities = set(indexes['municipalities'])
    provinces = {r['province_id'] for r in indexes['municipalities'].values()}
    administrative = {
        'cbs_reference_date': '2026-01-01', 'bag_snapshot_date': manifest['snapshot_date'],
        'municipalities_in_cbs': len(expected_municipalities), 'provinces_in_cbs': len(provinces),
        'municipalities_with_open_number_rows': len(municipality_numbers),
        'municipalities_with_open_named_public_spaces': len(municipality_spaces),
        'cbs_municipalities_without_open_number_rows': sorted(expected_municipalities - municipality_numbers.keys()),
        'number_municipalities_not_in_cbs': sorted(municipality_numbers.keys() - expected_municipalities),
        'open_number_rows_by_municipality': dict(sorted(municipality_numbers.items())),
        'gwr_links_are_supporting_non_authentic_bag_attributes': True,
        'all_administrative_levels_complete': False}
    reference_gaps = (bool(issues) or number_identity_counts['ids_with_multiple_open_records'] > 0
                      or bool(administrative['cbs_municipalities_without_open_number_rows'])
                      or bool(administrative['number_municipalities_not_in_cbs']))
    return {'schema_version': 1, 'region': 'western-europe', 'country': 'NL',
            'snapshot_date': manifest['snapshot_date'], 'status': 'PASS',
            'reference_status': 'GAPS_REQUIRE_REVIEW' if reference_gaps else 'PASS_FOR_CHECKED_REFERENCES',
            'implementation_sha256': shared.sha256(__file__),
            'shared_helpers_sha256': shared.sha256(shared.__file__),
            'manifest_sha256': hashlib.sha256(shared.canonical(manifest).encode()).hexdigest(),
            'source_reports': reports, 'number_identity_counts': number_identity_counts,
            'administrative_comparison': administrative, 'unresolved_reference_counts': dict(issues),
            'unresolved_reference_examples': examples,
            'counts_semantics': 'BAG source versions, including ended histories. Not unique real-world or deliverable addresses. '
                                'Not-BAG, inactive and investigation records are separate from main address observations.',
            'national_completeness_verified': False, 'all_physical_roads_complete': False,
            'all_assigned_numbers_complete': False, 'deliverability_in_scope': False}


def replay(manifest, root, accepted, work_dir=None):
    for field, current in (
            ('implementation_sha256', shared.sha256(__file__)),
            ('shared_helpers_sha256', shared.sha256(shared.__file__)),
            ('manifest_sha256', hashlib.sha256(shared.canonical(manifest).encode()).hexdigest())):
        if accepted.get(field) != current:
            raise ValueError('Accepted Dutch audit differs: ' + field)
    current = audit(manifest, root, work_dir)
    if current != {k: v for k, v in accepted.items() if k != 'source_row_replay'}:
        raise ValueError('Dutch source row replay differs')
    return {**current, 'source_row_replay': 'PASS'}


def search(manifest, root, text='', number=None, kind='address', limit=20, offset=0, current_only=False, postcode=None):
    if not 1 <= limit <= 200 or offset < 0 or (number is not None and not isinstance(number, str)):
        raise ValueError('Invalid Dutch query or pagination')
    roles = {'address': ['number_designations'], 'street': ['public_spaces'],
             'named_area': ['public_spaces'], 'locality': ['localities'],
             'municipality': ['municipalities'], 'municipality_locality_link': ['municipality_locality_links']}
    if kind not in roles:
        raise ValueError('Unsupported Dutch query kind')
    indexes = reference_index(manifest, root)[0] if kind == 'address' else None
    found, skipped = [], 0
    for role in roles[kind]:
        source = source_by_role(manifest, role)
        shared.verify_pin(source, root)
        for row in records(source, root, manifest['snapshot_date']):
            if row['kind'] != kind or (number is not None and row.get('number') != number):
                continue
            if postcode is not None and row.get('postcode') != postcode:
                continue
            if current_only and not row.get('registry_open_at_snapshot'):
                continue
            if kind == 'address':
                space, locality, link, municipality = address_references(row, indexes)
                row = {**row, 'reference_at_snapshot': {
                    'date': manifest['snapshot_date'],
                    'street_names': (space or {}).get('street_names'),
                    'public_space_type': (space or {}).get('public_space_type'),
                    'locality_id': (locality or {}).get('source_id'), 'locality_name': (locality or {}).get('name'),
                    'municipality_id': (municipality or {}).get('source_id'), 'municipality_name': (municipality or {}).get('name'),
                    'province_id': (municipality or {}).get('province_id'),
                    'basis': 'Open references at snapshot date; not a reconstruction of historical names.',
                    'gwr_link_is_authentic_bag_attribute': False}}
            if text and text.casefold() not in shared.canonical(row).casefold():
                continue
            if skipped < offset:
                skipped += 1
                continue
            found.append(row)
            if len(found) > limit:
                break
    return {'country': 'NL', 'snapshot_date': manifest['snapshot_date'], 'results': found[:limit],
            'has_more': len(found) > limit, 'next_offset': offset + limit if len(found) > limit else None,
            'national_completeness_verified': False, 'deliverability_in_scope': False}


def acquire(manifest, root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    recovered = []
    for pin in manifest['sources'] + manifest.get('evidence', []):
        path = shared.source_path(root, pin)
        if path.exists():
            shared.verify_pin(pin, root)
        elif 'container_member' in pin:
            download_member(manifest['container'], pin, path)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            parsed = urlsplit(pin['requested_url'])
            if parsed.scheme != 'https' or parsed.hostname not in ('www.cbs.nl', 'service.pdok.nl'):
                raise ValueError('Unregistered Dutch source host')
            temporary = path.with_name(path.name + '.partial')
            if temporary.exists() or temporary.is_symlink():
                raise ValueError('Prior incomplete download needs explicit review')
            created_partial = False
            try:
                if 'range_start' in pin:
                    response = fetch_range(manifest['container'], pin['range_start'], pin['bytes'])
                else:
                    response = urlopen(Request(pin['requested_url'], headers={'User-Agent': 'WorldLocalities-BAG/1.0'}), timeout=50)
                with response, temporary.open('xb') as output:
                    created_partial = True
                    if response.geturl() != pin['requested_url']:
                        raise ValueError('Unexpected Dutch source redirect')
                    count = 0
                    for block in iter(lambda: response.read(1024 * 1024), b''):
                        count += len(block)
                        if count > pin['bytes']:
                            raise ValueError('Dutch source snapshot changed')
                        output.write(block)
                if temporary.stat().st_size != pin['bytes'] or shared.sha256(temporary) != pin['sha256']:
                    raise ValueError('Pinned Dutch source bytes unavailable')
                path.hardlink_to(temporary)
            finally:
                if created_partial:
                    temporary.unlink(missing_ok=True)
        recovered.append(pin['id'])
    return {'status': 'PINNED_BYTES_RECOVERED', 'country': 'NL', 'sources': recovered,
            'national_completeness_verified': False, 'deliverability_in_scope': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('inventory', 'audit', 'replay', 'search', 'acquire'))
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--country', choices=('NL',), default='NL')
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--accepted', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--work-dir', type=Path)
    parser.add_argument('--text', default='')
    parser.add_argument('--number')
    parser.add_argument('--postcode')
    parser.add_argument('--kind', default='address')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--current-only', action='store_true')
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        if args.command == 'inventory':
            result = manifest
        else:
            if args.data_root is None:
                raise ValueError('--data-root is required')
            if args.command == 'acquire':
                result = acquire(manifest, args.data_root)
            elif args.command == 'search':
                result = search(manifest, args.data_root, args.text, args.number, args.kind,
                                args.limit, args.offset, args.current_only, args.postcode)
            elif args.command == 'audit':
                result = audit(manifest, args.data_root, args.work_dir)
            else:
                if args.accepted is None:
                    raise ValueError('--accepted is required')
                result = replay(manifest, args.data_root, json.loads(args.accepted.read_text()), args.work_dir)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if args.output:
            args.output.write_text(rendered, encoding='utf-8')
        else:
            print(rendered, end='')
    except (OSError, ValueError, KeyError, UnicodeError, ET.ParseError, zipfile.BadZipFile,
            sqlite3.Error, zlib.error, struct.error) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
