"""Export, replay and query source-qualified OSM evidence without a large SQLite index."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import tempfile

import osm_evidence as evidence


def record(obj, kind):
    tags = {tag.k: tag.v for tag in obj.tags}
    flags = evidence.classify(kind, tags)
    if not flags['selected']: return None
    topology = {}; geometry = None
    if kind == 'node':
        status = 'complete' if obj.location.valid() else 'missing_location'
        if obj.location.valid(): geometry = {'type': 'Point', 'coordinates': [obj.location.lon, obj.location.lat]}
    elif kind == 'way':
        topology = {'nodes': [str(node.ref) for node in obj.nodes]}
        complete = len(obj.nodes) >= 2 and all(node.location.valid() for node in obj.nodes)
        status = 'complete' if complete else 'missing_node_locations_or_short_way'
        if complete: geometry = {'type': 'LineString', 'coordinates': [[node.location.lon, node.location.lat] for node in obj.nodes]}
    else:
        topology = {'members': [{'type': member.type, 'ref': str(member.ref), 'role': member.role} for member in obj.members]}
        status = 'relation_member_geometry_not_assembled'
    payload = {'id': 'osm:' + kind + ':' + str(obj.id), 'version': obj.version, 'timestamp': str(obj.timestamp),
               'tags': tags, 'topology': topology, 'geometry': geometry, 'geometry_status': status}
    return {**payload, 'variant_sha256': hashlib.sha256(evidence.canonical(payload).encode()).hexdigest(),
            'osm_type': kind, 'osm_id': str(obj.id), **{key: value for key, value in flags.items() if key != 'selected'}}


def visit(path, consume):
    import osmium
    counts = Counter(); previous = {}

    class Visit(osmium.SimpleHandler):
        def accept(self, obj, kind):
            counts['tagged_' + kind] += 1
            item = record(obj, kind)
            if item is None: return
            if obj.id <= previous.get(kind, -1): raise ValueError('Repeated or unordered source identity')
            previous[kind] = obj.id
            consume(item)
            counts['observation_records'] += 1
            counts['retained_' + kind] += 1
            counts['active_road_way_records'] += item['road_state'] == 'active_tag'
            counts['named_road_way_records'] += item['named_road']
            counts['house_number_tag_observations'] += item['house_number']
            counts['address_tag_observations'] += item['address_tags']
            counts['administrative_tag_observations'] += item['administrative_tag']
            counts['interpolation_features'] += item['interpolation']
            counts['active_road_ways_with_missing_geometry'] += item['road_state'] == 'active_tag' and item['geometry_status'] != 'complete'
        def node(self, obj): self.accept(obj, 'node')
        def way(self, obj): self.accept(obj, 'way')
        def relation(self, obj): self.accept(obj, 'relation')

    with tempfile.TemporaryDirectory(prefix='osm-stream-locations-') as locations:
        Visit().apply_file(str(path), locations=True, idx='sparse_file_array,' + str(Path(locations) / 'nodes'),
                           filters=[osmium.filter.EmptyTagFilter()])
    return dict(counts)


def export(manifest, data_root, output):
    output = Path(output).resolve()
    if output.exists(): raise ValueError('Use a new export directory')
    sources = list(evidence.verified_sources(manifest, data_root))
    output.parent.mkdir(parents=True, exist_ok=True)
    extracts = []
    with tempfile.TemporaryDirectory(prefix='.osm-stream-', dir=output.parent) as temporary:
        stage = Path(temporary) / 'data'; stage.mkdir()
        for source, path in sources:
            code = source['country_extract']; name = code + '.osm-evidence.jsonl.gz'; target = stage / name
            with gzip.open(target, 'wt', encoding='utf-8', compresslevel=1, newline='\n') as writer:
                writer.write(evidence.canonical({'record_type': 'source', 'receipt': source}) + '\n')
                counts = visit(path, lambda item: writer.write(evidence.canonical(item) + '\n'))
            extracts.append({'extract_code': code, 'file': name, 'bytes': target.stat().st_size,
                             'sha256': evidence.file_hash(target), **counts})
            print(evidence.canonical({'extract_code': code, 'status': 'EXPORTED', 'counts': counts}), flush=True)
        report = {'schema_version': 1, 'format': 'osm-evidence-jsonl-gzip-v1', 'status': 'SOURCE_EVIDENCE_EXPORTED',
                  'checked_at': datetime.now(timezone.utc).isoformat(), 'extracts': extracts,
                  'implementation_sha256': evidence.file_hash(__file__), 'classification_sha256': evidence.file_hash(evidence.__file__),
                  'source_bytes': sum(source['bytes'] for source, _ in sources),
                  'observation_records': sum(item['observation_records'] for item in extracts),
                  'counts_scope': 'Extract observations. Cross-extract OSM identities are retained, not summed as unique real-world objects.',
                  'scan_counts_scope': 'Native empty-tag filtering occurs after node locations are cached; tagged_* counts exclude untagged objects.',
                  'national_completeness_verified': False, 'extract_membership_is_legal_country_membership': False,
                  'issuing_authority_assignment_verified': False, 'deliverability_in_scope': False, 'interpolation_expanded': False,
                  'licence': 'ODbL-1.0', 'licence_url': 'https://opendatacommons.org/licenses/odbl/1-0/',
                  'attribution': 'OpenStreetMap contributors; extract by Geofabrik'}
        (stage / 'index.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        if output.exists(): raise ValueError('Output appeared during export')
        stage.replace(output)
    return report


def checked_file(root, item):
    name = item['file']
    if Path(name).name != name or name in ('.', '..'): raise ValueError('Unsafe evidence filename')
    path = Path(root) / name
    if path.stat().st_size != item['bytes'] or evidence.file_hash(path) != item['sha256']:
        raise ValueError('Evidence file hash or byte count mismatch')
    return path


def verify(manifest, data_root, exported):
    exported = Path(exported); index = json.loads((exported / 'index.json').read_text())
    if index['implementation_sha256'] != evidence.file_hash(__file__) or index['classification_sha256'] != evidence.file_hash(evidence.__file__):
        raise ValueError('Export implementation changed; rebuild before replay')
    entries = {item['extract_code']: item for item in index['extracts']}
    sources = list(evidence.verified_sources(manifest, data_root))
    if set(entries) != {source['country_extract'] for source, _ in sources}: raise ValueError('Extract inventory mismatch')
    results = []
    for source, raw in sources:
        entry = entries[source['country_extract']]; path = checked_file(exported, entry)
        digest = hashlib.sha256()
        with gzip.open(path, 'rt', encoding='utf-8') as reader:
            if json.loads(next(reader)) != {'record_type': 'source', 'receipt': source}: raise ValueError('Source receipt mismatch')
            def compare(expected):
                try: actual = json.loads(next(reader))
                except StopIteration: raise ValueError('Missing source observation') from None
                if actual != expected: raise ValueError('Source feature replay mismatch: ' + expected['id'])
                digest.update(evidence.canonical(actual).encode() + b'\n')
            counts = visit(raw, compare)
            if reader.read(): raise ValueError('Unreplayed evidence records')
        if any(entry.get(key) != value for key, value in counts.items()): raise ValueError('Source count replay mismatch')
        results.append({'extract_code': source['country_extract'], 'status': 'PASS', 'counts': counts,
                        'canonical_feature_replay_sha256': digest.hexdigest()})
        print(evidence.canonical({'extract_code': source['country_extract'], 'status': 'REPLAYED'}), flush=True)
    return {'status': 'PASS', 'checked_at': datetime.now(timezone.utc).isoformat(), 'extracts': results,
            'matched_observations': sum(item['counts']['observation_records'] for item in results),
            'source_tags_topology_node_and_way_coordinates': 'PASS', 'gzip_crc_and_source_hashes': 'PASS',
            'not_verified': ['National real-world completeness', 'Legal country membership of buffered extracts',
                             'Issuing-authority assignment of number tags', 'Full assembly of administrative relation geometry'],
            'deliverability_in_scope': False}


def query(exported, code, kind, text=None, identifier=None, limit=20):
    if not 1 <= limit <= 100: raise ValueError('Invalid result limit')
    index = json.loads((Path(exported) / 'index.json').read_text())
    entries = [item for item in index['extracts'] if item['extract_code'] == code]
    if len(entries) != 1: raise ValueError('Unknown extract')
    conditions = {'roads': lambda row: row['road_state'] == 'active_tag', 'address-numbers': lambda row: row['house_number'],
                  'administrative': lambda row: row['administrative_tag'], 'all': lambda row: True}
    if kind not in conditions: raise ValueError('Unknown feature kind')
    results = []
    with gzip.open(checked_file(exported, entries[0]), 'rt', encoding='utf-8') as reader:
        next(reader)
        for line in reader:
            row = json.loads(line)
            if not conditions[kind](row): continue
            if identifier is not None and row['id'] != identifier: continue
            if text is not None and text.casefold() not in evidence.canonical(row['tags']).casefold(): continue
            results.append(row)
            if len(results) >= limit: break
    return {'extract_code': code, 'results': results, 'national_completeness_verified': False,
            'extract_membership_is_legal_country_membership': False, 'issuing_authority_assignment_verified': False,
            'deliverability_in_scope': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest='command', required=True)
    for name in ['export', 'verify']:
        command = commands.add_parser(name); command.add_argument('--manifest', type=Path, required=True)
        command.add_argument('--data-root', type=Path, required=True); command.add_argument('--output', type=Path, required=True)
        if name == 'verify': command.add_argument('--exported', type=Path, required=True)
    find = commands.add_parser('query'); find.add_argument('--exported', type=Path, required=True); find.add_argument('--extract', required=True)
    find.add_argument('--kind', choices=['roads', 'address-numbers', 'administrative', 'all'], required=True)
    find.add_argument('--text'); find.add_argument('--id'); find.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    try:
        if args.command == 'query': report = query(args.exported, args.extract, args.kind, args.text, args.id, args.limit)
        else:
            manifest = json.loads(args.manifest.read_text())
            if args.command == 'export': report = export(manifest, args.data_root, args.output)
            else:
                report = verify(manifest, args.data_root, args.exported)
                args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(evidence.canonical({'status': report.get('status', 'QUERY'), 'report': report}))
    except (OSError, ValueError, KeyError, ImportError, EOFError) as error: parser.exit(2, str(error) + '\n')


if __name__ == '__main__': main()
