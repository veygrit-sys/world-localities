"""Compare saved distribution references with locally available bytes, offline."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def archive_references(data):
    """Keep whole archives and transport parts distinct; never add their counts."""
    entries = []
    for field, kind in [('archives', 'archive'), ('parts', 'transport_part')]:
        for item in data.get(field, []):
            name = item.get('name') or item.get('file')
            if name:
                entries.append((name, item.get('bytes'), item.get('sha256'), kind))
    if data.get('archive_name'):
        entries.append((data['archive_name'], data.get('archive_bytes'),
                        data.get('archive_sha256'), 'reconstructed_archive'))
    return list(dict.fromkeys(entries))


def audit(root=ROOT, artifact_root=None, tracked_paths=None):
    root = Path(root).resolve()
    if tracked_paths is None:
        tracked_paths = subprocess.check_output(
            ['git', '-C', str(root), 'ls-files', '-z']).decode().split('\0')[:-1]
    by_name = {}
    for name in tracked_paths:
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('unsafe tracked path')
        by_name.setdefault(relative.name, []).append(root / relative)
    records = []
    for manifest in sorted((root / 'releases/hierarchy').rglob('archive.json')):
        if manifest.relative_to(root).as_posix() not in tracked_paths:
            continue
        data = json.loads(manifest.read_text())
        for name, size, expected, kind in archive_references(data):
            if PurePosixPath(name).name != name or '\\' in name or name in {'.', '..'}:
                raise ValueError('archive reference must be a filename')
            if type(size) is not int or size < 0 or not re.fullmatch(r'[0-9a-f]{64}', expected or ''):
                raise ValueError(f'invalid saved size/checksum: {name}')
            candidates = list(by_name.get(name, []))
            if artifact_root is not None:
                candidates.append(Path(artifact_root).resolve() / name)
            candidates = [path for path in candidates if path.is_file() and not path.is_symlink()]
            checks = [{'location': 'repository' if path.is_relative_to(root) else 'supplied_directory',
                       'matches': path.stat().st_size == size and sha256(path) == expected}
                      for path in candidates]
            state = ('available_verified' if any(item['matches'] for item in checks) else
                     'local_mismatch' if checks else 'referenced_not_local')
            records.append({'manifest': manifest.relative_to(root).as_posix(), 'name': name,
                            'kind': kind, 'expected_size': size, 'expected_sha256': expected,
                            'availability': state, 'local_checks': checks,
                            'external_storage_status': 'not_checked'})
    historical = {'reference': 'docs/migration/README.md',
                  'description': 'Previously described Europe v0.7 local expansion',
                  'expected_entry': 'europe_expansion/README.md',
                  'repository_entry_present': 'europe_expansion/README.md' in tracked_paths,
                  'external_storage_status': 'not_checked'}
    return {'schema_version': 1, 'scope': 'saved references versus local bytes; external storage not searched',
            'reference_count': len(records), 'archives': records, 'historical_items': [historical],
            'status': 'mismatch' if any(r['availability'] == 'local_mismatch' for r in records) else 'inventory_complete',
            'data_completeness_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-root', type=Path, help='directory containing existing archive filenames')
    args = parser.parse_args()
    try:
        report = audit(artifact_root=args.artifact_root)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report['status'] == 'mismatch':
            raise SystemExit(1)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(2, f'artifact audit failed: {error}\n')


if __name__ == '__main__':
    main()
