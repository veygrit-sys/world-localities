#!/usr/bin/env python3
"""Inspect actual Central America payloads, not only their metadata totals."""
import argparse
import gzip
import importlib.util
import io
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from localities.materialize import materialize_country

DIRECTORY = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('central_supplement_quality', DIRECTORY / 'supplement.py')
supplement = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(supplement)
BASE = ('BZ', 'GT', 'HN', 'NI', 'PA', 'SV')
COUNTRIES = ('BZ', 'CR', 'GT', 'HN', 'MX', 'NI', 'PA', 'SV')


def read_payload(directory, filename, info, columns):
    _, _, v = supplement.libraries()
    data = v.verified_bytes(directory, filename, info['sha256'])
    v.require(len(data) == info['bytes'], 'compressed payload byte count mismatch')
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as handle:
        raw = handle.read(supplement.MAX_TEXT + 1)
    v.require(len(raw) <= supplement.MAX_TEXT and v.digest(raw) == info['uncompressed_sha256'],
              'uncompressed payload bound/hash mismatch')
    rows = v.csv_rows(raw, columns)
    v.require(len(rows) == info['rows'], 'payload row count mismatch')
    return rows


def load_country(country, root=ROOT):
    """Return (source rows, tagged names, quality report); source types stay distinct."""
    b, n, v = supplement.libraries()
    v.require(country in COUNTRIES, 'country is outside M49 Central America')
    root = Path(root).resolve()
    if country == 'MX':
        index, manifest, anchors, manifest_hash = v.official_index(root, country)
        rows = []
        for region in index['regions']:
            part, _ = v.region_rows(root, country, index, manifest, anchors, region)
            rows.extend(part)
        v.require(len({r['id'] for r in rows}) == len(rows), 'duplicate Mexico source role')
        return rows, [], {
            'country': country, 'status': 'passed', 'source_format': 'official_inegi_snapshot',
            'source_layer': 'official-registry/MX', 'source_locality_rows': len(rows),
            'entities': len(rows), 'language_tagged_names': None,
            'source_vintage': index['vintage'], 'manifest_sha256': manifest_hash,
            'source_raw_replay': 'not_run_preserved_official_snapshot_integrity_checked',
            'delivery_verified': False, 'current_official_hierarchy_verified': False}
    if country == 'CR':
        report = supplement.verify(root)
        directory = root / supplement.RELATIVE / 'countries/CR'
        meta = v.load_json(directory, 'metadata.json')
        locale = v.load_json(directory, 'locale_metadata.json')
    else:
        central = root / 'central-america-registry'
        materialize_country(central, country)
        manifest = v.load_json(central, 'manifest.json')
        entries = v.unique_rows(manifest['countries'], 'country', 'legacy Central America manifest')
        v.require(set(entries) == set(BASE), 'six-country historical base scope changed')
        relative = f'countries/{country}/metadata.json'
        meta = v.decode_json(v.verified_bytes(central, relative, entries[country]['metadata_sha256']))
        locale_manifest = v.load_json(central, 'locale_manifest.json')
        relative = f'countries/{country}/locale_metadata.json'
        locale = v.decode_json(v.verified_bytes(central, relative, locale_manifest['files'][relative]['sha256']))
        directory = central / 'countries' / country
        report = {'status': 'passed', 'raw_source_replay': 'not_run_legacy_raw_archives',
                  'derived_rows_replay': 'exact', 'source_observed_at': meta['source_file']['retrieved_on']}
    v.require(meta['country']['country'] == country and locale['country'] == country, 'country metadata mismatch')
    v.require(meta['current_official_hierarchy_verified'] is False and locale['postal_delivery_validated'] is False,
              'unsupported current official/delivery claim')
    rows = read_payload(directory, 'entities.csv.gz', meta['files']['entities.csv.gz'], b.FIELDS)
    v.require(rows == b.build_rows([{field: r[field] for field in b.RAW} for r in rows], country),
              'gazetteer derived-column replay mismatch')
    by_id = v.unique_rows(rows, 'id', 'gazetteer entities')
    for row in rows:
        parent, seen = row['parent_id'], {row['id']}
        v.require(not parent or parent == 'country:' + country or parent in by_id, 'unresolved parent reference')
        while parent in by_id:
            v.require(parent not in seen, 'parent cycle')
            seen.add(parent)
            parent = by_id[parent]['parent_id']
    names = read_payload(directory, 'names.csv.gz', locale['files']['names.csv.gz'], n.NAMES)
    postals = read_payload(directory, 'postal_links.csv.gz', locale['files']['postal_links.csv.gz'], n.POSTAL)
    allowed = set(by_id) | {'country:' + country}
    v.unique_rows(names + postals, 'id', 'name/postal rows')
    v.require(all(r['entity_id'] in allowed and r['country_code'] == country for r in names + postals),
              'name/postal row has wrong country or entity')
    v.require(all(r['delivery_validated'] == '0' and r['relation'] == 'source_direct_id' and r['language'] == 'post'
                  for r in postals), 'unsupported postal proof')
    computed = supplement.summary(rows, names, postals)
    computed['country'] = country
    for field in ('locality_rows', 'admin_rows', 'other_admin_rows', 'address_candidates',
                  'unresolved_parents', 'ambiguous_parents', 'country_scope_only', 'localities_without_adm1'):
        v.require(meta['counts'][field] == computed[field], 'country metric mismatch: ' + field)
    v.require(meta['feature_counts'] == computed['feature_counts'], 'feature distribution mismatch')
    v.require(locale['counts']['language_tagged_names'] == len(names) and locale['counts']['postal_links'] == len(postals),
              'locale count mismatch')
    return rows, names, dict(report, **{
        'country': country, 'source_format': 'geonames_gazetteer',
        'source_layer': supplement.RELATIVE + '/countries/CR' if country == 'CR' else 'central-america-registry/countries/' + country,
        'entities': len(rows), 'source_locality_rows': computed['locality_rows'],
        'language_tagged_names': len(names), 'postal_links': len(postals),
        'unresolved_parents': computed['unresolved_parents'], 'known_issues': meta['known_issues'],
        'delivery_verified': False, 'current_official_hierarchy_verified': False})


def verify_all(root=ROOT):
    results, seen = [], set()
    for country in COUNTRIES:
        try:
            rows, _, report = load_country(country, root)
            ids = {r['id'] for r in rows}
            supplement.require(not ids.intersection(seen), 'duplicate source entity ID between countries')
            seen.update(ids)
            results.append(report)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            results.append({'country': country, 'status': 'failed', 'error': str(exc)})
    failed = [r['country'] for r in results if r['status'] != 'passed']
    return {'status': 'failed' if failed else 'passed', 'region_m49': '013',
            'countries': results, 'failed_countries': failed,
            'country_source_coverage': None if failed else '8/8',
            'unique_real_world_locality_count': None,
            'note': 'Seven GeoNames source country packs plus a separate Mexico official municipality-role snapshot; not eight identical source types or complete postal coverage.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--country', choices=COUNTRIES)
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        report = load_country(args.country, args.root)[2] if args.country else verify_all(args.root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, f'error: {exc}\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report['status'] != 'passed':
        raise SystemExit(2)


if __name__ == '__main__':
    main()
