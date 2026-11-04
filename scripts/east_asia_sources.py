"""Acquire and replay source-qualified East Asian open geodata. No inferred numbers."""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
from urllib.request import Request, urlopen
import zipfile

from osm_evidence import canonical, classify, file_hash

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / 'releases/hierarchy/east-asia/sources.json'
SCOPE = ('CN', 'HK', 'JP', 'KP', 'KR', 'MN', 'MO', 'TW')
EXTRACTS = {'CN': 'asia/china', 'HK': 'asia/china/hong-kong', 'JP': 'asia/japan',
            'KP': 'asia/north-korea', 'KR': 'asia/south-korea', 'MN': 'asia/mongolia',
            'MO': 'asia/china/macau', 'TW': 'asia/taiwan'}


def load_manifest(path=DEFAULT_MANIFEST):
    value = json.loads(Path(path).read_text())
    if value['scope_codes'] != list(SCOPE) or value.get('national_completeness_verified') is not False or value.get('deliverability_in_scope') is not False:
        raise ValueError('Scope or coverage contract differs')
    ids, paths, osm = set(), set(), set()
    for source in value['sources']:
        if source['country'] not in SCOPE or source['id'] in ids or source['path'] in paths:
            raise ValueError('Invalid or duplicate source')
        safe_path(Path('.'), source['path'])
        ids.add(source['id']); paths.add(source['path'])
        if not source['url'].startswith('https://'):
            raise ValueError('Expected an HTTPS source')
        if source['format'] == 'osm_pbf':
            code = source['country']; osm.add(code)
            if not re.fullmatch(re.escape('https://download.geofabrik.de/' + EXTRACTS[code]) + r'-\d{6}\.osm\.pbf', source['url']):
                raise ValueError('Unexpected public dated extract')
    if osm != set(SCOPE) or len([s for s in value['sources'] if s['format'] == 'osm_pbf']) != 8:
        raise ValueError('Eight distinct OSM extracts required')
    return value


def safe_path(root, relative):
    part = PurePosixPath(relative)
    if not part.parts or part.is_absolute() or '..' in part.parts or '\\' in relative:
        raise ValueError('Unsafe source path')
    root = Path(root).resolve(); target = (root / part).resolve()
    if not target.is_relative_to(root):
        raise ValueError('Source escapes data root')
    return target


def verified(source, root):
    path = safe_path(root, source['path'])
    if not re.fullmatch('[0-9a-f]{64}', source.get('sha256') or '') or path.stat().st_size != source['bytes'] or file_hash(path) != source['sha256']:
        raise ValueError('Source byte/hash mismatch: ' + source['id'])
    return path


def request(url):
    return urlopen(Request(url, headers={'User-Agent': 'world-localities source-qualified research', 'Accept-Encoding': 'identity'}), timeout=90)


def checksum(url):
    with request(url + '.md5') as response:
        value = response.read(4096).decode('ascii')
    match = re.match(r'([a-fA-F0-9]{32})\b', value)
    if not match: raise ValueError('Invalid publisher MD5')
    return match[1].lower()


def acquire_one(source, root):
    target = safe_path(root, source['path']); partial = target.with_name(target.name + '.partial')
    if target.exists() or partial.exists(): raise ValueError('Use a new source path; preserve prior bytes')
    target.parent.mkdir(parents=True, exist_ok=True)
    before = checksum(source['url']) if source['format'] == 'osm_pbf' else None
    sha, md5, size = hashlib.sha256(), hashlib.md5(), 0
    with request(source['url']) as response, partial.open('xb') as output:
        for block in iter(lambda: response.read(1024 * 1024), b''):
            output.write(block); sha.update(block); md5.update(block); size += len(block)
        declared = response.headers.get('Content-Length')
        if declared and size != int(declared): raise ValueError('Truncated HTTP source')
        headers = {k: v for k, v in response.headers.items() if k.lower() in ('etag', 'last-modified', 'content-type', 'content-length')}
        resolved = response.url
    if before is not None and (md5.hexdigest() != before or checksum(source['url']) != before):
        raise ValueError('Publisher snapshot moved or MD5 differs')
    if source.get('sha256') and (source['sha256'] != sha.hexdigest() or source['bytes'] != size):
        raise ValueError('Pinned source changed')
    partial.replace(target)
    result = dict(source, bytes=size, sha256=sha.hexdigest(), retrieved_at=datetime.now(timezone.utc).isoformat(), resolved_url=resolved, http_metadata=headers)
    if before: result.update(publisher_md5=before, publisher_checksum_stable_before_after=True)
    receipt = target.with_name(target.name + '.receipt.json')
    receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'source': source['id'], 'status': 'ACQUIRED_VERIFIED', 'bytes': size}), flush=True)
    return result


def acquire(manifest, root, workers=3):
    if not 1 <= workers <= 3: raise ValueError('Use one to three workers')
    root = Path(root)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        sources = list(pool.map(lambda source: acquire_one(source, root), manifest['sources']))
    result = dict(manifest, sources=sources)
    (root / 'sources.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def osm_rows(path):
    import osmium
    # Native empty-tag filter avoids visiting every untagged geometry node in Python.
    for obj in osmium.FileProcessor(str(path)).with_filter(osmium.filter.EmptyTagFilter()):
        kind = 'node' if obj.is_node() else 'way' if obj.is_way() else 'relation'
        tags = {tag.k: tag.v for tag in obj.tags}; flags = classify(kind, tags)
        if not flags['selected']: continue
        row = {'id': 'osm:' + kind + ':' + str(obj.id), 'kind': kind, 'version': obj.version,
               'timestamp': str(obj.timestamp), 'tags': tags, 'classification': flags}
        if kind == 'node':
            row['coordinates'] = [obj.location.lon, obj.location.lat] if obj.location.valid() else None
        elif kind == 'way': row['nodes'] = [str(node.ref) for node in obj.nodes]
        else: row['members'] = [{'type': m.type, 'ref': str(m.ref), 'role': m.role} for m in obj.members]
        yield row


@contextmanager
def csv_reader(path):
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            members = [m for m in archive.infolist() if not m.is_dir() and m.filename.endswith('.csv')]
            if len(members) != 1: raise ValueError('Expected exactly one CSV member')
            member = members[0]
            if member.flag_bits & 1: raise ValueError('Encrypted CSV is unsupported')
            with archive.open(member) as raw, io.TextIOWrapper(raw, encoding='utf-8-sig', newline='') as text:
                yield csv.DictReader(text)
    else:
        with Path(path).open(encoding='utf-8-sig', newline='') as text: yield csv.DictReader(text)


def table_rows(source, path):
    if source['format'] == 'json':
        values = json.loads(Path(path).read_text())
        if not isinstance(values, list): raise ValueError('Expected JSON row array')
        for ordinal, row in enumerate(values, 1):
            if not isinstance(row, dict): raise ValueError('Expected JSON record')
            yield ordinal, row
    else:
        with csv_reader(path) as reader:
            if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames): raise ValueError('Duplicate or empty CSV header')
            for ordinal, row in enumerate(reader, 1):
                if None in row or None in row.values(): raise ValueError('CSV row width differs from header')
                yield ordinal, row


def audit_one(source, root):
    path = verified(source, root); digest = hashlib.sha256(); counts = Counter(); blanks = Counter()
    labels = {}; previous_id = None; monotonic = True; examples = {}
    if source['format'] == 'osm_pbf':
        import osmium
        with osmium.io.Reader(str(path)) as reader:
            header = reader.header()
            metadata = {key: header.get(key) for key in ('generator', 'osmosis_replication_timestamp', 'osmosis_replication_sequence_number')}
        for row in osm_rows(path):
            digest.update((canonical(row) + '\n').encode()); counts['observations'] += 1
            flags = row['classification']
            for key in ('named_road', 'house_number', 'address_tags', 'administrative_tag', 'interpolation'):
                if flags[key]: counts[key] += 1
            if flags['road_state'] == 'active_tag': counts['active_road_way'] += 1
            for label, condition in [('road', flags['road_state'] == 'active_tag'), ('address', flags['house_number']), ('admin', flags['administrative_tag'])]:
                if condition and label not in examples: examples[label] = row
    else:
        metadata = {'source_role': source['role']}
        for ordinal, row in table_rows(source, path):
            digest.update((canonical(row) + '\n').encode()); counts['observations'] += 1
            for key, value in row.items():
                if value == '': blanks[key] += 1
            for key in source.get('label_fields', []): labels.setdefault(key, set()).add(row[key])
            if 'id_field' in source:
                identity = row[source['id_field']]
                if not identity: counts['empty_source_id'] += 1
                if previous_id is not None and identity <= previous_id: monotonic = False
                previous_id = identity
            if ordinal == 1: examples['first_row'] = row
        metadata.update(empty_fields=dict(blanks), distinct_labels={key: len(values) for key, values in labels.items()})
        if 'id_field' in source: metadata['source_ids_strictly_increasing'] = monotonic
    return {'source_id': source['id'], 'source_sha256': source['sha256'], 'source_bytes': source['bytes'],
            'counts': dict(counts), 'ordered_rows_sha256': digest.hexdigest(), 'metadata': metadata, 'examples': examples}


def implementation_pins():
    return {name: file_hash(ROOT / 'scripts' / name) for name in ('east_asia_sources.py', 'osm_evidence.py')}


def audit(manifest, root):
    reports = []
    for source in manifest['sources']:
        report = audit_one(source, root); reports.append(report)
        print(json.dumps({'source': source['id'], 'status': 'AUDITED', 'counts': report['counts']}), flush=True)
    return {'schema_version': 1, 'scope_codes': list(SCOPE), 'implementation_sha256': implementation_pins(),
            'manifest_sha256': hashlib.sha256(canonical(manifest).encode()).hexdigest(), 'sources': reports,
            'national_completeness_verified': False, 'deliverability_in_scope': False, 'interpolation_expanded': False}


def replay(manifest, root, accepted):
    if accepted['implementation_sha256'] != implementation_pins(): raise ValueError('Audit implementation differs')
    actual = audit(manifest, root)
    if canonical(actual) != canonical(accepted): raise ValueError('Full source replay differs')
    return {'status': 'PASS', 'method': 'Full source reread using the same pinned parser; not an independent implementation',
            'sources': len(actual['sources']), 'observations': sum(r['counts']['observations'] for r in actual['sources']),
            'implementation_sha256': actual['implementation_sha256'], 'national_completeness_verified': False}


def search(source, root, text='', kind='all', identity=None, limit=10):
    if not 1 <= limit <= 100: raise ValueError('Limit must be 1..100')
    path = verified(source, root); results = []
    if source['format'] == 'osm_pbf':
        for row in osm_rows(path):
            flags = row['classification']
            if kind == 'road' and flags['road_state'] != 'active_tag': continue
            if kind == 'address' and not flags['house_number']: continue
            if kind == 'admin' and not flags['administrative_tag']: continue
            if identity and identity != row['id']: continue
            if text and not any(text.casefold() in str(v).casefold() for v in row['tags'].values()): continue
            results.append(row)
            if len(results) >= limit: break
    else:
        if kind != 'all': raise ValueError('Table grain is fixed; use kind=all')
        for ordinal, row in table_rows(source, path):
            row_id = str(row[source['id_field']]) if source.get('id_field') else str(ordinal)
            if identity and identity != row_id: continue
            if text and not any(text.casefold() in str(v).casefold() for v in row.values()): continue
            results.append({'id': source['id'] + ':' + row_id, 'ordinal': ordinal, 'raw': row})
            if len(results) >= limit: break
    return {'source_id': source['id'], 'source_sha256': source['sha256'], 'results': results,
            'results_are_a_limited_source_query': True, 'extract_membership_is_legal_country_membership': False,
            'interpolation_expanded': False, 'deliverability_in_scope': False}


CN_LEVELS = ('provinces', 'cities', 'areas', 'streets', 'villages')
CN_PARENT_FIELDS = {'provinceCode': 'provinces', 'cityCode': 'cities', 'areaCode': 'areas', 'streetCode': 'streets'}


def cn_tables(manifest, root):
    tables = {}
    for level in CN_LEVELS:
        selected = [s for s in manifest['sources'] if s['id'] == 'CN-statistical-' + level]
        if len(selected) != 1: raise ValueError('Five pinned CN statistical tables required')
        source = selected[0]
        tables[level] = json.loads(verified(source, root).read_text())
    return tables


def cn_reference_audit(manifest, root):
    tables = cn_tables(manifest, root); indexes = {}; duplicates = Counter(); unresolved = Counter(); inconsistent = Counter()
    for level, rows in tables.items():
        index = {}
        for row in rows:
            if not isinstance(row.get('code'), str) or not row['code']: raise ValueError('Missing lexical CN code')
            if row['code'] in index: duplicates[level] += 1
            index[row['code']] = row
        indexes[level] = index
    for level, rows in tables.items():
        for row in rows:
            for field, parent_level in CN_PARENT_FIELDS.items():
                if field not in row: continue
                parent = indexes[parent_level].get(row[field])
                if parent is None: unresolved[level + '.' + field] += 1
                else:
                    for ancestor_field in CN_PARENT_FIELDS:
                        if ancestor_field in row and ancestor_field in parent and row[ancestor_field] != parent[ancestor_field]:
                            inconsistent[level + '.' + ancestor_field] += 1
    return {'source_date': '2023-06-30', 'counts': {level: len(rows) for level, rows in tables.items()},
            'duplicate_codes': dict(duplicates), 'unresolved_explicit_references': dict(unresolved),
            'inconsistent_explicit_ancestors': dict(inconsistent), 'parent_assignment': 'explicit source fields only',
            'streets_are_township_subdistrict_records_not_roads': True, 'national_completeness_verified': False}


def cn_parents(manifest, root, source_id, identity):
    level = source_id.removeprefix('CN-statistical-')
    if level not in CN_LEVELS: raise ValueError('Parents requires a CN statistical source or TW-NLSC')
    tables = cn_tables(manifest, root)
    matches = [row for row in tables[level] if row['code'] == identity]
    if len(matches) != 1: raise ValueError('CN source ID is missing or duplicated')
    target = matches[0]; chain = [{'source_id': source_id, 'raw': target}]
    for field, parent_level in reversed(tuple(CN_PARENT_FIELDS.items())):
        if field not in target: continue
        matches = [row for row in tables[parent_level] if row['code'] == target[field]]
        if len(matches) != 1: raise ValueError('Explicit parent is missing or duplicated')
        chain.append({'source_id': 'CN-statistical-' + parent_level, 'raw': matches[0]})
    return {'chain': chain, 'parent_assignment': 'explicit source fields only; no prefix or name inference',
            'source_date': '2023-06-30', 'national_completeness_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inventory', 'acquire', 'audit', 'replay', 'search', 'parents', 'cn-audit'])
    parser.add_argument('--manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--accepted', type=Path)
    parser.add_argument('--source'); parser.add_argument('--text', default=''); parser.add_argument('--id')
    parser.add_argument('--kind', choices=['all', 'road', 'address', 'admin'], default='all')
    parser.add_argument('--limit', type=int, default=10); parser.add_argument('--workers', type=int, default=3)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        if args.command != 'inventory' and args.data_root is None: raise ValueError('--data-root is required')
        if args.command == 'inventory': result = manifest
        elif args.command == 'acquire': result = acquire(manifest, args.data_root, args.workers)
        elif args.command == 'audit': result = audit(manifest, args.data_root)
        elif args.command == 'replay':
            if args.accepted is None: raise ValueError('--accepted is required')
            result = replay(manifest, args.data_root, json.loads(args.accepted.read_text()))
        elif args.command == 'cn-audit': result = cn_reference_audit(manifest, args.data_root)
        elif args.command == 'parents': result = cn_parents(manifest, args.data_root, args.source or '', args.id)
        else:
            candidates = [s for s in manifest['sources'] if s['id'] == args.source]
            if len(candidates) != 1: raise ValueError('Choose an exact --source from inventory')
            result = search(candidates[0], args.data_root, args.text, args.kind, args.id, args.limit)
        text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.output: args.output.write_text(text)
        else: print(text, end='')
    except (OSError, ValueError, KeyError) as exc: parser.exit(2, str(exc) + '\n')


if __name__ == '__main__': main()
