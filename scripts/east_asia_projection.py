"""Retain native OSM objects selected by the pinned East Asia classifier."""
import argparse
import json
from pathlib import Path

import east_asia_sources as e

DEFAULT_MANIFEST = e.ROOT / 'releases/hierarchy/east-asia/projections.json'


def export(source, root, output, accepted):
    import osmium
    output = Path(output)
    if output.exists(): raise ValueError('Use a new projection output')
    if accepted['source_sha256'] != source['sha256']: raise ValueError('Original audit pin differs')
    path = e.verified(source, root); output.parent.mkdir(parents=True, exist_ok=True)
    with osmium.io.Reader(str(path)) as reader:
        with osmium.SimpleWriter(str(output), header=reader.header()) as writer:
            for obj in osmium.FileProcessor(str(path)).with_filter(osmium.filter.EmptyTagFilter()):
                kind = 'node' if obj.is_node() else 'way' if obj.is_way() else 'relation'
                if e.classify(kind, {t.k: t.v for t in obj.tags})['selected']: writer.add(obj)
    if e.file_hash(path) != source['sha256']: raise ValueError('Original source changed during projection')
    pin = dict(source, path=output.name, sha256=e.file_hash(output), bytes=output.stat().st_size)
    actual = e.audit_one(pin, output.parent)
    for key in ('ordered_rows_sha256', 'counts', 'examples'):
        if actual[key] != accepted[key]: raise ValueError('Native projection differs: ' + key)
    pin['path'] = 'projections/' + output.name
    pin['original_source_sha256'] = source['sha256']
    pin['original_source_bytes'] = source['bytes']
    pin['original_source_url'] = source['url']
    pin['format'] = 'selected_osm_pbf'
    pin['original_pbf_preserved_in_distribution'] = False
    return {'status': 'PASS', 'source': pin, 'counts': actual['counts'],
            'ordered_rows_sha256': actual['ordered_rows_sha256'],
            'projection_implementation_sha256': e.file_hash(__file__),
            'classifier_implementation_sha256': e.implementation_pins(),
            'verification': 'Every selected native object re-read; canonical fields, counts and ordered digest match full original source audit',
            'all_tags_versions_timestamps_and_ordered_references_preserved': True,
            'untagged_dependency_nodes_copied': False, 'way_or_relation_geometry_assembled': False,
            'interpolation_expanded': False, 'national_completeness_verified': False}


def search(original_manifest, projection_manifest, root, source_id, text='', kind='all', identity=None, limit=10):
    original = [s for s in original_manifest['sources'] if s['id'] == source_id]
    projections = [r for r in projection_manifest['sources'] if r['source']['id'] == source_id]
    if len(original) != 1 or len(projections) != 1: raise ValueError('Unknown or duplicate source projection')
    report = projections[0]; source = report['source']
    if report['status'] != 'PASS' or source['original_source_sha256'] != original[0]['sha256'] or source['country'] != original[0]['country']:
        raise ValueError('Projection does not match pinned original')
    result = e.search(dict(source, format='osm_pbf'), root, text, kind, identity, limit)
    result.update(original_source_sha256=source['original_source_sha256'], dataset='selected_native_osm_projection',
                  untagged_dependency_nodes_copied=False, way_or_relation_geometry_assembled=False)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['export', 'search'])
    parser.add_argument('--manifest', type=Path, default=e.DEFAULT_MANIFEST)
    parser.add_argument('--projection-manifest', type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--source', required=True); parser.add_argument('--accepted', type=Path)
    parser.add_argument('--text', default=''); parser.add_argument('--id')
    parser.add_argument('--kind', choices=['all', 'road', 'address', 'admin'], default='all')
    parser.add_argument('--limit', type=int, default=10); parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        manifest = e.load_manifest(args.manifest)
        if args.command == 'export':
            source = next(s for s in manifest['sources'] if s['id'] == args.source)
            if args.accepted is None or args.output is None: raise ValueError('Export requires --accepted and --output')
            result = export(source, args.data_root, args.output, json.loads(args.accepted.read_text()))
        else:
            result = search(manifest, json.loads(args.projection_manifest.read_text()), args.data_root,
                            args.source, args.text, args.kind, args.id, args.limit)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, StopIteration) as exc: parser.exit(2, str(exc) + '\n')


if __name__ == '__main__': main()
