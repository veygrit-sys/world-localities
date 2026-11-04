"""Restore a pinned file from ordered ZIP-wrapped byte parts without extracting paths."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from zipfile import ZipFile, BadZipFile


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as reader:
        for block in iter(lambda: reader.read(1024 * 1024), b''): result.update(block)
    return result.hexdigest()


def restore(manifest, parts_directory, output):
    if manifest.get('format') != 'zip-wrapped-byte-parts-v1' or not manifest.get('parts'):
        raise ValueError('Unsupported or empty part manifest')
    output = Path(output)
    if output.exists() or output.is_symlink(): raise ValueError('Use a new restored output')
    parts = []; seen = set()
    for item in manifest['parts']:
        name = item['file']; member = item['member']
        if Path(name).name != name or name in seen or name in ('.', '..'):
            raise ValueError('Unsafe or repeated part filename')
        if Path(member).name != member or member in ('.', '..'): raise ValueError('Unsafe part member')
        seen.add(name); path = Path(parts_directory) / name
        if path.stat().st_size != item['bytes'] or digest(path) != item['sha256']:
            raise ValueError('Part byte count or SHA-256 mismatch')
        parts.append((item, path))
    output.parent.mkdir(parents=True, exist_ok=True)
    full_hash = hashlib.sha256(); size = 0
    with tempfile.TemporaryDirectory(prefix='.data-restore-', dir=output.parent) as temporary:
        staged = Path(temporary) / 'restored'
        with staged.open('xb') as writer:
            for item, path in parts:
                with ZipFile(path) as archive:
                    if archive.namelist() != [item['member']] or archive.getinfo(item['member']).file_size != item['member_bytes']:
                        raise ValueError('Part member layout mismatch')
                    with archive.open(item['member']) as reader:
                        for block in iter(lambda: reader.read(1024 * 1024), b''):
                            full_hash.update(block); writer.write(block); size += len(block)
        if size != manifest['archive_bytes'] or full_hash.hexdigest() != manifest['archive_sha256']:
            raise ValueError('Restored file byte count or SHA-256 mismatch')
        if output.exists(): raise ValueError('Restored output appeared during reconstruction')
        staged.replace(output)
    return {'status': 'RESTORED_HASH_VERIFIED', 'bytes': size, 'sha256': full_hash.hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True); parser.add_argument('--parts-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    try:
        print(json.dumps(restore(json.loads(args.manifest.read_text()), args.parts_directory, args.output)))
    except (OSError, ValueError, KeyError, BadZipFile) as error: parser.exit(2, str(error) + '\n')


if __name__ == '__main__': main()
