#!/usr/bin/env python3
"""Verify every part, ZIP member, original base file, and ID reference."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from addresskit.region_names import RegionCatalog, open_split_archive


def validate(root):
    manifest = json.loads((root / 'pack_manifest.json').read_text())
    seen = {}
    counts = Counter()
    for key, entry in list(manifest['countries'].items()) + [('shared', manifest['shared'])]:
        with open_split_archive(root, entry) as archive:
            if set(archive.namelist()) != set(entry['members']):
                raise ValueError('archive member list mismatch: ' + key)
            for member, meta in entry['members'].items():
                data = archive.read(member)
                if len(data) != meta['bytes'] or hashlib.sha256(data).hexdigest() != meta['sha256']:
                    raise ValueError('member checksum mismatch: ' + member)
                if member.startswith('base/'):
                    if member in seen:
                        raise ValueError('duplicate base member: ' + member)
                    seen[member] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
                counts['members'] += 1
            if key == 'shared':
                original = json.loads(archive.read('base/manifest.json'))
            else:
                for name, member in [('places', entry['places_member']), ('names', 'locale/names.jsonl'),
                                     ('postal_links', 'locale/postal_links.jsonl')]:
                    count = len(archive.read(member).decode('utf-8').splitlines())
                    if count != entry['counts'][name]:
                        raise ValueError('row count mismatch: ' + key + '/' + name)
                    counts[name] += count
        counts['parts'] += len(entry['parts'])
    for row in original['files']:
        if seen.get('base/' + row['path']) != {'bytes': row['bytes'], 'sha256': row['sha256']}:
            raise ValueError('original base changed: ' + row['path'])
    catalog = RegionCatalog.from_pack(root)
    for entity in catalog.entities.values():
        parent = entity.get('parent_id')
        if parent and (parent not in catalog.entities or catalog.entities[parent]['country_code'] != entity['country_code']):
            raise ValueError('missing or cross-country parent: ' + entity['id'])
    for profile in catalog.profiles.values():
        for field in ('fmt', 'lfmt'):
            if set(re.findall(r'%(.)', profile.get(field, ''))) - set('NOADCSZXn'):
                raise ValueError('unsupported template token')
        if set(profile['require']) - set('NOADCSZX'):
            raise ValueError('unsupported required field')
    if counts['places'] != original['geonames_records'] or len(catalog.entities) != counts['places'] + 29:
        raise ValueError('base entity count mismatch')
    if sum(map(len, catalog.names.values())) != counts['names']:
        raise ValueError('name count mismatch')
    report = {'status': 'pass', 'countries': len(manifest['countries']), **counts,
              'entities_including_country_roots': len(catalog.entities),
              'original_base_files_verified': len(original['files']),
              'postal_relations_are_not_delivery_validation': True}
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--pack', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = validate(args.pack)
    result = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.write_text(result)
    print(result, end='')
