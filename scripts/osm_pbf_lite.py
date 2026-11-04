"""Bounded standard-library reader for raw/zlib OSM PBF evidence.

Supports ordinary/dense nodes, ways and relations. Never expands interpolation.
Intended for small extracts; large-scale imports should use libosmium.
"""
from __future__ import annotations

from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import struct
import zlib

from osm_evidence import canonical, classify, file_hash


def varint(data, offset=0):
    value = 0
    for shift in range(0, 70, 7):
        if offset >= len(data):
            raise ValueError('Truncated PBF varint')
        byte = data[offset]
        offset += 1
        value |= (byte & 127) << shift
        if byte < 128:
            return value, offset
    raise ValueError('Oversized PBF varint')


def zigzag(value):
    return (value >> 1) ^ -(value & 1)


def fields(data):
    offset = 0
    while offset < len(data):
        tag, offset = varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError('Invalid PBF field number')
        if wire == 0:
            value, offset = varint(data, offset)
        elif wire == 2:
            size, offset = varint(data, offset)
            value = data[offset:offset + size]
            if len(value) != size:
                raise ValueError('Truncated PBF field')
            offset += size
        else:
            raise ValueError('Unsupported PBF wire type')
        yield number, value


def packed(data, signed=False, delta=False):
    offset = total = 0
    while offset < len(data):
        value, offset = varint(data, offset)
        value = zigzag(value) if signed else value
        total = total + value if delta else value
        yield total


def tags(keys, values, strings):
    keys, values = list(packed(keys)), list(packed(values))
    if len(keys) != len(values):
        raise ValueError('PBF tag counts differ')
    return {strings[k]: strings[v] for k, v in zip(keys, values)}


def objects(path):
    with Path(path).open('rb') as stream:
        while True:
            prefix = stream.read(4)
            if not prefix:
                break
            if len(prefix) != 4:
                raise ValueError('Truncated PBF block')
            size = struct.unpack('>I', prefix)[0]
            if not 0 < size <= 65536:
                raise ValueError('Invalid PBF block header size')
            header = dict(fields(stream.read(size)))
            block_size = header[3]
            if not 0 < block_size <= 32 * 1024 * 1024:
                raise ValueError('Invalid PBF compressed size')
            blob = stream.read(block_size)
            if len(blob) != block_size:
                raise ValueError('Truncated PBF blob')
            content = dict(fields(blob))
            if 1 in content:
                data = content[1]
            elif 3 in content and 2 in content and 0 < content[2] <= 32 * 1024 * 1024:
                decoder = zlib.decompressobj()
                data = decoder.decompress(content[3], content[2] + 1)
                if not decoder.eof or decoder.unused_data or len(data) != content[2]:
                    raise ValueError('PBF decompression size mismatch')
            else:
                raise ValueError('Unsupported PBF compression')
            if header[1] == b'OSMHeader':
                required = [v for k, v in fields(data) if k == 4]
                if any(v not in (b'OsmSchema-V0.6', b'DenseNodes', b'HistoricalInformation') for v in required):
                    raise ValueError('Unsupported required PBF feature')
                continue
            if header[1] != b'OSMData':
                raise ValueError('Unknown PBF block type')
            block = list(fields(data))
            strings = [v.decode('utf-8') for k, v in fields(next(v for k, v in block if k == 1)) if k == 1]
            attrs = {k: v for k, v in block if k in (17, 19, 20)}
            granularity = attrs.get(17, 100)
            lat_offset, lon_offset = attrs.get(19, 0), attrs.get(20, 0)
            for key, group in block:
                if key != 2:
                    continue
                for kind, value in fields(group):
                    obj = dict(fields(value))
                    if kind == 2:
                        ids = list(packed(obj.get(1, b''), True, True))
                        latitudes = list(packed(obj.get(8, b''), True, True))
                        longitudes = list(packed(obj.get(9, b''), True, True))
                        if not len(ids) == len(latitudes) == len(longitudes):
                            raise ValueError('Dense coordinate counts differ')
                        dense_tags = list(packed(obj.get(10, b'')))
                        cursor = 0
                        for identity, latitude, longitude in zip(ids, latitudes, longitudes):
                            row_tags = {}
                            while cursor < len(dense_tags) and dense_tags[cursor] != 0:
                                if cursor + 1 >= len(dense_tags):
                                    raise ValueError('Truncated dense tags')
                                row_tags[strings[dense_tags[cursor]]] = strings[dense_tags[cursor + 1]]
                                cursor += 2
                            if dense_tags:
                                if cursor >= len(dense_tags):
                                    raise ValueError('Missing dense tag terminator')
                                cursor += 1
                            yield 'node', identity, row_tags, {'lon': (lon_offset + granularity * longitude) * 1e-9,
                                                            'lat': (lat_offset + granularity * latitude) * 1e-9}
                        if cursor != len(dense_tags):
                            raise ValueError('Extra dense tag data')
                    elif kind in (1, 3, 4):
                        identity = zigzag(obj[1]) if kind == 1 else obj[1]
                        row_tags = tags(obj.get(2, b''), obj.get(3, b''), strings)
                        if kind == 1:
                            topology = {'lon': (lon_offset + granularity * zigzag(obj[9])) * 1e-9,
                                        'lat': (lat_offset + granularity * zigzag(obj[8])) * 1e-9}
                        elif kind == 3:
                            topology = {'nodes': list(packed(obj.get(8, b''), True, True))}
                        else:
                            roles = list(packed(obj.get(8, b'')))
                            refs = list(packed(obj.get(9, b''), True, True))
                            types = list(packed(obj.get(10, b'')))
                            if not len(roles) == len(refs) == len(types):
                                raise ValueError('PBF relation member counts differ')
                            topology = {'members': [{'type': ('node', 'way', 'relation')[t], 'ref': ref,
                                                      'role': strings[role]} for role, ref, t in zip(roles, refs, types)]}
                        yield {1: 'node', 3: 'way', 4: 'relation'}[kind], identity, row_tags, topology
                    elif kind not in (5,):
                        raise ValueError('Unsupported PBF primitive group')


def export(path, receipt, output):
    path, output = Path(path), Path(output)
    if path.stat().st_size != receipt['bytes'] or file_hash(path) != receipt['sha256']:
        raise ValueError('PBF source pin mismatch')
    if path.stat().st_size > 20 * 1024 * 1024:
        raise ValueError('Use libosmium for larger extracts')
    if output.exists():
        raise ValueError('Use a new evidence output')
    counts, nodes = Counter(), {}
    digest = hashlib.sha256()
    with output.open('xb') as file, gzip.GzipFile(fileobj=file, mode='wb', filename='', mtime=0) as gz:
        for kind, identity, row_tags, topology in objects(path):
            counts['scanned_' + kind] += 1
            if kind == 'node':
                nodes[identity] = [topology['lon'], topology['lat']]
            flags = classify(kind, row_tags)
            if not flags['selected']:
                continue
            geometry = None
            if kind == 'node':
                geometry = {'type': 'Point', 'coordinates': nodes[identity]}
            elif kind == 'way' and len(topology['nodes']) >= 2 and all(n in nodes for n in topology['nodes']):
                geometry = {'type': 'LineString', 'coordinates': [nodes[n] for n in topology['nodes']]}
            record = {'id': f'osm:{kind}:{identity}', 'tags': row_tags, 'source_topology': topology,
                      'geometry': geometry, 'geometry_status': 'complete' if geometry else 'not_assembled_or_missing_nodes',
                      'extract_code': receipt['country'], 'source_sha256': receipt['sha256'],
                      'metadata_policy': 'Version/timestamp are retained in the pinned original PBF, not decoded in this projection.',
                      **{k: v for k, v in flags.items() if k != 'selected'}}
            rendered = canonical(record).encode() + b'\n'
            digest.update(rendered)
            gz.write(rendered)
            counts['observation_records'] += 1
            counts['active_road_ways'] += flags['road_state'] == 'active_tag'
            counts['number_tag_observations'] += flags['house_number']
            counts['administrative_tag_observations'] += flags['administrative_tag']
    return {'source': receipt['id'], 'counts': dict(counts), 'bytes': output.stat().st_size,
            'sha256': file_hash(output), 'canonical_rows_sha256': digest.hexdigest(),
            'extract_membership_is_legal_country_membership': False,
            'national_completeness_verified': False, 'deliverability_in_scope': False,
            'interpolation_expanded': False, 'attribution': 'OpenStreetMap contributors; extract by Geofabrik',
            'license': 'ODbL-1.0'}
