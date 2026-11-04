"""Keep Caribbean OSM observations separate from official address records.

Extracting PBF needs the optional requirements-caribbean-osm.txt dependencies.
Restoring, querying and checking the normalized data uses the standard library.
OSM objects retain their type/ID/version, tags and explicit member references.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import zlib

SCOPE = ('AG', 'BS', 'BB', 'CU', 'DM', 'DO', 'GD', 'HT', 'JM', 'KN', 'LC', 'VC', 'TT',
         'AI', 'AW', 'BQ', 'VG', 'KY', 'CW', 'GP', 'MQ', 'MS', 'PR', 'BL', 'MF', 'SX', 'TC', 'VI')
ATTRIBUTION = '© OpenStreetMap contributors'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def packed_document(rendered):
    return zlib.compress(rendered.encode('utf-8'), 6)


def unpacked_document(value):
    return json.loads(zlib.decompress(value).decode('utf-8') if isinstance(value, bytes) else value)


def osm_key(kind, identity):
    if kind not in ('node', 'way', 'relation') or type(identity) is not int or identity <= 0:
        raise ValueError('Invalid OSM object identity')
    return f'osm:{kind}:{identity}'


def categories(kind, tags):
    result = []
    if tags.get('boundary') == 'administrative': result.append('administrative_boundary')
    if tags.get('boundary') == 'legal': result.append('legal_boundary')
    if kind == 'way' and tags.get('highway'): result.append('road_way')
    if tags.get('addr:housenumber'): result.append('explicit_number_observation')
    if tags.get('addr:interpolation'): result.append('interpolation_way_evidence')
    if tags.get('type') == 'associatedStreet': result.append('associated_street_relation')
    return result


class Classifier:
    """Source polygon coverage is a derived geographic label, not a legal code join."""
    def __init__(self, boundaries):
        import shapely
        self.codes = sorted(boundaries)
        self.shapes = [shapely.union_all(boundaries[cc]) for cc in self.codes]
        if any(g.is_empty or not g.is_valid for g in self.shapes):
            raise ValueError('Invalid source country polygon; do not silently repair it')
        self.tree = shapely.STRtree(self.shapes)
        for geometry in self.shapes: shapely.prepare(geometry)

    def classify(self, geometry):
        if geometry is None or geometry.is_empty or not geometry.is_valid:
            return None, [], 'geometry_unresolved'
        intersecting = [int(i) for i in self.tree.query(geometry, predicate='intersects')]
        covered = sorted({self.codes[i] for i in intersecting if self.shapes[i].covers(geometry)})
        candidates = sorted({self.codes[i] for i in intersecting})
        if len(covered) == 1: return covered[0], candidates, 'source_polygon_covers_geometry'
        if len(covered) > 1: return None, candidates, 'overlapping_source_country_polygons'
        return None, candidates, 'crosses_or_touches_country_boundary' if candidates else 'outside_selected_source_polygons'


def document(obj, kind):
    result = {'osm_key': osm_key(kind, obj.id), 'osm_type': kind, 'osm_id': obj.id,
              'osm_version': obj.version, 'source_tags': dict(obj.tags)}
    if kind == 'way': result['source_node_refs'] = [n.ref for n in obj.nodes]
    if kind == 'relation':
        result['source_members'] = [{'type': m.type, 'ref': m.ref, 'role': m.role} for m in obj.members]
    return result


def extract(pbf, receipt, target):
    import osmium
    import shapely
    from importlib.metadata import version
    pbf, target = Path(pbf), Path(target)
    if pbf.stat().st_size != receipt['bytes'] or file_hash(pbf) != receipt['sha256']:
        raise ValueError('PBF differs from its pinned receipt')
    target.mkdir(parents=True, exist_ok=False)
    pending_path = target / 'INCOMPLETE.json'
    pending_path.write_text(canonical({'status': 'EXTRACTION_IN_PROGRESS'}) + '\n')
    relation_info, way_info = {}, {}
    selection = osmium.filter.KeyFilter('boundary', 'addr:housenumber', 'type')
    for obj in osmium.FileProcessor(str(pbf), osmium.osm.RELATION | osmium.osm.WAY).with_filter(selection):
        tags = dict(obj.tags)
        if obj.is_relation() and categories('relation', tags): relation_info[obj.id] = document(obj, 'relation')
        elif obj.is_way() and tags.get('boundary') in ('administrative', 'legal'):
            way_info[obj.id] = document(obj, 'way')
    needed_member_ways = {m['ref'] for doc in relation_info.values()
                          if any(c in categories('relation', doc['source_tags']) for c in
                                 ('explicit_number_observation', 'associated_street_relation'))
                          for m in doc['source_members'] if m['type'] == 'w'}
    member_geometries = {}
    print(canonical({'phase': 'relation_inventory', 'objects': len(relation_info)}), file=sys.stderr, flush=True)
    factory = osmium.geom.WKBFactory()
    areas, boundaries = [], {}
    area_failures = []
    boundary_filter = lambda: osmium.filter.TagFilter(('boundary', 'administrative'), ('boundary', 'legal'))
    fp = (osmium.FileProcessor(str(pbf)).with_areas(boundary_filter())
          .with_filter(osmium.filter.EntityFilter(osmium.osm.AREA)).with_filter(boundary_filter()))
    for area in fp:
        kind = 'way' if area.from_way() else 'relation'
        tags = dict(area.tags)
        try:
            geometry_hex = factory.create_multipolygon(area)
            geometry = shapely.from_wkb(bytes.fromhex(geometry_hex))
            if not geometry.is_valid or geometry.is_empty: raise ValueError('Invalid source area geometry')
        except (RuntimeError, ValueError) as exc:
            area_failures.append({'osm_key': osm_key(kind, area.orig_id()), 'reason': str(exc)})
            continue
        doc = {'osm_key': osm_key(kind, area.orig_id()), 'osm_type': kind, 'osm_id': area.orig_id(),
               'osm_version': area.version, 'source_tags': tags, 'geometry_wkb_hex': geometry_hex}
        if kind == 'relation' and area.orig_id() in relation_info:
            doc.update(relation_info[area.orig_id()])
        elif kind == 'way' and area.orig_id() in way_info:
            doc.update(way_info[area.orig_id()])
        cc = tags.get('ISO3166-1') or tags.get('ISO3166-1:alpha2')
        if cc in SCOPE: boundaries.setdefault(cc, []).append(geometry)
        areas.append((doc, geometry))
    missing = sorted(set(SCOPE) - boundaries.keys())
    if missing:
        raise ValueError('Source country polygons missing; no guessed bounding boxes are used: ' + ','.join(missing))
    classifier = Classifier(boundaries)
    print(canonical({'phase': 'country_polygons', 'countries': len(boundaries), 'admin_or_legal_areas': len(areas)}), file=sys.stderr, flush=True)
    db_path = target / 'caribbean_osm.sqlite'
    db = sqlite3.connect(db_path)
    db.execute('PRAGMA journal_mode=OFF')
    db.execute('PRAGMA synchronous=OFF')
    db.executescript('''CREATE TABLE records (osm_key TEXT PRIMARY KEY,country TEXT,number TEXT,street TEXT,document BLOB NOT NULL);
                       CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);''')
    totals, country_counts, review_counts = Counter(), {cc: Counter() for cc in SCOPE}, Counter()
    processed = set()
    unresolved = []
    output_path = target / 'observations.jsonl.gz'
    digest = hashlib.sha256()

    def emit(doc, geometry, explicit_country=None, assignment_evidence=None):
        if doc['osm_key'] in processed: return False
        tags = doc['source_tags']
        cc, candidates, assignment = classifier.classify(geometry)
        if explicit_country is not None:
            cc = explicit_country
            assignment = assignment_evidence or 'explicit_source_ISO3166_1_scope_tag'
            candidates = sorted(set(candidates + [cc]))
        if cc is None and not candidates:
            return False
        doc.update(country=cc, country_candidates=candidates, country_assignment=assignment,
                   categories=categories(doc['osm_type'], tags), source='OpenStreetMap', license='ODbL-1.0',
                   assignment_verified=False, national_completeness_verified=False, deliverability_in_scope=False)
        if not doc['categories']: return False
        if tags.get('addr:interpolation'): doc['interpolation_expanded'] = False
        rendered = canonical(doc)
        db.execute('INSERT INTO records VALUES (?,?,?,?,?)',
                   (doc['osm_key'], cc, tags.get('addr:housenumber', ''), tags.get('addr:street', ''), packed_document(rendered)))
        stream.write((rendered + '\n').encode('utf-8'))
        digest.update((rendered + '\n').encode('utf-8'))
        processed.add(doc['osm_key'])
        totals.update(doc['categories'])
        if cc: country_counts[cc].update(doc['categories'])
        else: review_counts.update(doc['categories'])
        if assignment not in ('source_polygon_covers_geometry', 'explicit_source_ISO3166_1_scope_tag'):
            unresolved.append({'osm_key': doc['osm_key'], 'candidates': candidates, 'reason': assignment})
        return True

    try:
        with output_path.open('wb') as raw, gzip.GzipFile(filename='', fileobj=raw, mode='wb', mtime=0) as stream:
            for doc, geometry in areas:
                cc = doc['source_tags'].get('ISO3166-1') or doc['source_tags'].get('ISO3166-1:alpha2')
                emit(doc, geometry, cc if cc in SCOPE else None)
            # Location storage sees all nodes before the tag filter removes them.
            fp = (osmium.FileProcessor(str(pbf)).with_locations()
                  .with_filter(osmium.filter.KeyFilter('addr:housenumber', 'addr:interpolation').enable_for(osmium.osm.NODE))
                  .with_filter(osmium.filter.EntityFilter(osmium.osm.NODE | osmium.osm.WAY)))
            scanned = 0
            for obj in fp:
                if obj.is_relation(): continue
                kind = 'node' if obj.is_node() else 'way'
                tags = dict(obj.tags)
                needed = kind == 'way' and obj.id in needed_member_ways
                if not categories(kind, tags) and not needed: continue
                doc = document(obj, kind)
                try:
                    geometry_hex = factory.create_point(obj) if kind == 'node' else factory.create_linestring(obj)
                    geometry = shapely.from_wkb(bytes.fromhex(geometry_hex))
                    doc['geometry_wkb_hex'] = geometry_hex
                except (RuntimeError, ValueError) as exc:
                    geometry = None
                    doc['geometry_issue'] = str(exc)
                if needed and geometry is not None: member_geometries[obj.id] = geometry
                if categories(kind, tags): emit(doc, geometry)
                scanned += 1
                if scanned % 100000 == 0:
                    print(canonical({'phase': 'roads_and_explicit_addresses', 'source_objects_scanned': scanned, 'retained': len(processed)}), file=sys.stderr, flush=True)
            # Retain numbered and associatedStreet relations by their actual members.
            prefixes = {'n': 'node', 'w': 'way', 'r': 'relation'}
            for doc in relation_info.values():
                if doc['osm_key'] in processed or not any(c in categories('relation', doc['source_tags']) for c in
                                                          ('associated_street_relation', 'explicit_number_observation')): continue
                geometries = [member_geometries[m['ref']] for m in doc['source_members']
                              if m['type'] == 'w' and m['ref'] in member_geometries]
                if geometries:
                    geometry = shapely.union_all(geometries)
                    doc['geometry_wkb_hex'] = shapely.to_wkb(geometry, hex=True)
                    doc['geometry_role'] = 'collection_of_available_explicit_relation_member_ways'
                    doc['unresolved_geometry_members'] = [m for m in doc['source_members']
                        if m['type'] == 'r' or (m['type'] == 'w' and m['ref'] not in member_geometries)]
                    if emit(doc, geometry): continue
                matches = set()
                for member in doc['source_members']:
                    row = db.execute('SELECT country FROM records WHERE osm_key=?',
                                     (osm_key(prefixes[member['type']], member['ref']),)).fetchone()
                    if row and row[0]: matches.add(row[0])
                if len(matches) == 1:
                    doc['geometry_issue'] = 'Relation membership retained; no polygon or number was inferred'
                    emit(doc, None, matches.pop(), 'country_of_explicit_source_relation_members')
        db.execute('CREATE INDEX country_number ON records(country,number)')
        manifest = {'schema_version': 1, 'region': 'caribbean', 'scope_codes': list(SCOPE),
                    'source_pbf': receipt, 'source_reference': 'https://download.geofabrik.de/central-america.html',
                    'license': 'ODbL-1.0', 'license_url': 'https://opendatacommons.org/licenses/odbl/1-0/',
                    'attribution': ATTRIBUTION, 'data_derived_from_OSM': True,
                    'complete': False, 'deliverability_in_scope': False, 'country_polygon_count': len(boundaries),
                    'records': len(processed), 'category_counts': dict(totals),
                    'country_counts': {cc: dict(country_counts[cc]) for cc in SCOPE},
                    'unassigned_review_counts': dict(review_counts), 'country_assignment_reviews': unresolved,
                    'source_area_geometry_failures': area_failures,
                    'normalized': {'path': output_path.name, 'bytes': output_path.stat().st_size,
                                   'sha256': file_hash(output_path), 'uncompressed_row_sha256': digest.hexdigest()},
                    'runtime_versions': {'osmium': version('osmium'), 'shapely': version('shapely')},
                    'policies': ['OSM IDs include object type; original versions, tags, nodes and relation members are retained.',
                                 'Geographic country labels derived from OSM polygons are not official administrative ID joins.',
                                 'Legal BQ grouping is not counted as a shared administrative government.',
                                 'Explicit addr:housenumber values remain strings; interpolation is never expanded.',
                                 'Coincident official and OSM observations are not merged or added as unique roads/addresses.',
                                 'Construction, proposed and unnamed highway ways retain source tags, not a usability guarantee.']}
        for key, value in manifest.items(): db.execute('INSERT INTO metadata VALUES (?,?)', (key, canonical(value)))
        db.commit()
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise ValueError('OSM index integrity failure')
    finally:
        db.close()
    (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    pending_path.unlink()
    return manifest


def restore_index(root, output):
    root, output = Path(root), Path(output)
    if (root / 'INCOMPLETE.json').exists(): raise ValueError('Snapshot extraction is incomplete')
    manifest = json.loads((root / 'manifest.json').read_text())
    if (manifest.get('complete') is not False or manifest.get('deliverability_in_scope') is not False
            or sorted(manifest['scope_codes']) != sorted(SCOPE) or manifest.get('license') != 'ODbL-1.0'):
        raise ValueError('Invalid OSM snapshot manifest')
    pin = manifest['normalized']
    if Path(pin['path']).name != pin['path']: raise ValueError('Unsafe normalized-data filename')
    source = root / pin['path']
    if source.stat().st_size != pin['bytes'] or file_hash(source) != pin['sha256']:
        raise ValueError('Normalized OSM bytes differ')
    if output.exists(): raise ValueError('Use a new index path')
    output.parent.mkdir(parents=True, exist_ok=True)
    count, digest = 0, hashlib.sha256()
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix='.sqlite') as temp:
        db = sqlite3.connect(temp.name)
        try:
            db.execute('PRAGMA journal_mode=OFF')
            db.execute('PRAGMA synchronous=OFF')
            db.executescript('CREATE TABLE records (osm_key TEXT PRIMARY KEY,country TEXT,number TEXT,street TEXT,document BLOB NOT NULL);'
                             'CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);')
            with gzip.open(source, 'rt', encoding='utf-8') as stream:
                for line in stream:
                    doc = json.loads(line)
                    if doc['osm_key'] != osm_key(doc['osm_type'], doc['osm_id']) or (doc['country'] is not None and doc['country'] not in SCOPE):
                        raise ValueError('Invalid source identity or country')
                    if doc['categories'] != categories(doc['osm_type'], doc['source_tags']):
                        raise ValueError('Source category changed')
                    if (doc.get('license') != 'ODbL-1.0' or doc.get('assignment_verified') is not False
                            or doc.get('national_completeness_verified') is not False
                            or doc.get('deliverability_in_scope') is not False):
                        raise ValueError('Unjustified assignment or completeness claim')
                    tags = doc['source_tags']
                    rendered = canonical(doc)
                    digest.update((rendered + '\n').encode())
                    db.execute('INSERT INTO records VALUES (?,?,?,?,?)',
                               (doc['osm_key'], doc['country'], tags.get('addr:housenumber', ''), tags.get('addr:street', ''), packed_document(rendered)))
                    count += 1
            if count != manifest['records'] or digest.hexdigest() != pin['uncompressed_row_sha256']:
                raise ValueError('Normalized OSM row count or digest differs')
            db.execute('CREATE INDEX country_number ON records(country,number)')
            for key, value in manifest.items(): db.execute('INSERT INTO metadata VALUES (?,?)', (key, canonical(value)))
            db.commit()
        finally:
            db.close()
        output.hardlink_to(temp.name)
    return {'status': 'PASS', 'records': count, 'license': 'ODbL-1.0', 'attribution': ATTRIBUTION,
            'complete': False, 'deliverability_in_scope': False}


def replay(pbf, root):
    """Re-read PBF source tags, versions, node refs and explicit relation members."""
    import osmium
    root, pbf = Path(root), Path(pbf)
    manifest = json.loads((root / 'manifest.json').read_text())
    pin = manifest['source_pbf']
    if pbf.stat().st_size != pin['bytes'] or file_hash(pbf) != pin['sha256']: raise ValueError('PBF source differs')
    db = sqlite3.connect((root / 'caribbean_osm.sqlite').resolve().as_uri() + '?mode=ro', uri=True)
    remaining = {r[0] for r in db.execute('SELECT osm_key FROM records')}
    matched = 0
    try:
        for obj in osmium.FileProcessor(str(pbf)).with_filter(osmium.filter.KeyFilter('highway', 'addr:housenumber', 'addr:interpolation', 'boundary', 'type')):
            kind = 'node' if obj.is_node() else 'way' if obj.is_way() else 'relation'
            key = osm_key(kind, obj.id)
            if key not in remaining: continue
            stored = unpacked_document(db.execute('SELECT document FROM records WHERE osm_key=?', (key,)).fetchone()[0])
            source = document(obj, kind)
            for field in ('osm_key', 'osm_type', 'osm_id', 'osm_version', 'source_tags', 'source_node_refs', 'source_members'):
                # Area-derived way geometries do not add missing raw node refs.
                if field in stored and stored[field] != source.get(field): raise ValueError('OSM source replay differs: ' + key + ':' + field)
            remaining.remove(key)
            matched += 1
    finally:
        db.close()
    if remaining or matched != manifest['records']:
        raise ValueError('Source records not replayed or manifest count differs: ' + str(len(remaining)))
    return {'status': 'PASS', 'source_objects_replayed': matched, 'complete': False, 'deliverability_in_scope': False,
            'scope': 'Tags, versions, IDs and available original node/member references; not independent national completeness or geometric accuracy.'}


def query(database, country, number=None, limit=20, offset=0):
    if country not in SCOPE or not 1 <= limit <= 200 or offset < 0: raise ValueError('Invalid query scope or pagination')
    path = Path(database).resolve()
    if not path.is_file(): raise ValueError('Index not found')
    if (path.parent / 'INCOMPLETE.json').exists(): raise ValueError('Snapshot extraction is incomplete')
    values, clause = [country], 'country=?'
    if number is not None:
        if not isinstance(number, str): raise ValueError('Number must remain a string')
        clause += ' AND number=?'; values.append(number)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        rows = db.execute('SELECT document FROM records WHERE ' + clause + ' ORDER BY osm_key LIMIT ? OFFSET ?',
                          values + [limit + 1, offset]).fetchall()
    return {'country': country, 'results': [unpacked_document(r[0]) for r in rows[:limit]], 'has_more': len(rows) > limit,
            'next_offset': offset + limit if len(rows) > limit else None, 'license': 'ODbL-1.0', 'attribution': ATTRIBUTION,
            'complete': False, 'deliverability_in_scope': False}


def audit_parent_references(database):
    """Audit only explicit relation/subarea members, without inventing a tree."""
    path = Path(database).resolve()
    if not path.is_file(): raise ValueError('Index not found')
    if (path.parent / 'INCOMPLETE.json').exists(): raise ValueError('Snapshot extraction is incomplete')
    nodes = {}
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
        for key, country, packed in db.execute("SELECT osm_key,country,document FROM records WHERE osm_key LIKE 'osm:relation:%'"):
            doc = unpacked_document(packed)
            if 'administrative_boundary' not in doc['categories']: continue
            nodes[key] = {'country': country, 'level': doc['source_tags'].get('admin_level'),
                          'children': [osm_key('relation', m['ref']) for m in doc.get('source_members', [])
                                       if m['type'] == 'r' and m['role'] == 'subarea']}
    edges, problems = [], []
    graph = {key: [] for key in nodes}
    for parent, info in nodes.items():
        for child in info['children']:
            edges.append({'parent': parent, 'child': child, 'role': 'subarea'})
            if child not in nodes:
                problems.append({'parent': parent, 'child': child, 'issue': 'child_not_in_selected_source_index'})
                continue
            graph[parent].append(child)
            target = nodes[child]
            if info['country'] and target['country'] and info['country'] != target['country']:
                problems.append({'parent': parent, 'child': child, 'issue': 'source_country_labels_differ'})
            if str(info['level']).isdigit() and str(target['level']).isdigit() and int(info['level']) >= int(target['level']):
                problems.append({'parent': parent, 'child': child, 'issue': 'source_admin_level_order_requires_review'})
    state, cycles = {}, []
    for start in graph:
        if state.get(start): continue
        stack = [(start, iter(graph[start]))]
        state[start] = 1
        while stack:
            key, children = stack[-1]
            child = next(children, None)
            if child is None:
                state[key] = 2; stack.pop()
            elif state.get(child) == 1:
                cycles.append({'parent': key, 'child': child})
            elif not state.get(child):
                state[child] = 1; stack.append((child, iter(graph[child])))
    return {'status': 'SOURCE_REFERENCES_AUDITED', 'administrative_relation_objects': len(nodes),
            'explicit_subarea_edges': edges, 'issues': problems, 'cycles': cycles,
            'complete': False, 'deliverability_in_scope': False,
            'policy': 'Missing parents/children, contradictory levels and cycles remain source issues; no parent is inferred from a name or numeric level.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['extract', 'restore-index', 'replay', 'query', 'audit-parents'])
    parser.add_argument('--pbf', type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--target', type=Path)
    parser.add_argument('--snapshot', type=Path)
    parser.add_argument('--db', type=Path)
    parser.add_argument('--country')
    parser.add_argument('--number')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'extract':
            if not args.pbf or not args.receipt or not args.target: raise ValueError('--pbf, --receipt and --target are required')
            result = extract(args.pbf, json.loads(args.receipt.read_text()), args.target)
        elif args.command == 'restore-index':
            if not args.snapshot or not args.db: raise ValueError('--snapshot and --db are required')
            result = restore_index(args.snapshot, args.db)
        elif args.command == 'replay':
            if not args.pbf or not args.snapshot: raise ValueError('--pbf and --snapshot are required')
            result = replay(args.pbf, args.snapshot)
        elif args.command == 'audit-parents':
            if not args.db: raise ValueError('--db is required')
            result = audit_parent_references(args.db)
        else:
            if not args.db or not args.country: raise ValueError('--db and --country are required')
            result = query(args.db, args.country, args.number, args.limit, args.offset)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if args.output: args.output.write_text(rendered)
        else: print(rendered, end='')
    except (OSError, ValueError, KeyError, sqlite3.Error, RuntimeError, ImportError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
