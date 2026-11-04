"""Verify pinned snapshot archives and restore them into a new directory."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import stat
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def safe_member(info, roots):
    name = info.filename
    path = PurePosixPath(name)
    mode = info.external_attr >> 16
    if (not name or path.is_absolute() or '..' in path.parts or '\\' in name
            or ':' in name or '\x00' in name or path.parts[0] not in roots
            or path.as_posix().rstrip('/') != name.rstrip('/')
            or stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}):
        raise ValueError('Unsafe archive member')
    return path


def file_hash(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify(manifest, archives):
    seen = set()
    for pin in manifest['archives']:
        if Path(pin['name']).name != pin['name']:
            raise ValueError('Unsafe archive filename')
        path = Path(archives) / pin['name']
        if not path.is_file() or path.stat().st_size != pin['bytes'] or file_hash(path) != pin['sha256']:
            raise ValueError('Archive size or SHA-256 mismatch: ' + pin['name'])
        with zipfile.ZipFile(path) as z:
            if len(z.infolist()) != pin['files']:
                raise ValueError('Archive inventory mismatch')
            for info in z.infolist():
                member = safe_member(info, pin['roots']).as_posix()
                if not info.is_dir():
                    if member in seen:
                        raise ValueError('Duplicate archive destination')
                    seen.add(member)
            if z.testzip() is not None:
                raise ValueError('Archive CRC mismatch')
    return {'status': 'VERIFIED_ARCHIVES', 'archives': len(manifest['archives']),
            'files': len(seen), 'world_complete': False, 'deliverability_in_scope': False}


def restore(manifest, archives, target):
    target = Path(target).absolute()
    if target.exists() or target.is_symlink():
        raise ValueError('Use a new target; existing targets are never overwritten')
    report = verify(manifest, archives)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.hierarchy-', dir=target.parent) as temp:
        stage = Path(temp) / 'snapshot'
        stage.mkdir()
        for pin in manifest['archives']:
            with zipfile.ZipFile(Path(archives) / pin['name']) as z:
                for info in z.infolist():
                    output = stage / safe_member(info, pin['roots'])
                    if info.is_dir():
                        output.mkdir(parents=True, exist_ok=True)
                    else:
                        output.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(info) as src, output.open('xb') as dst:
                            shutil.copyfileobj(src, dst, 1024 * 1024)
                        if output.stat().st_size != info.file_size:
                            raise ValueError('Incomplete restored member')
        target.mkdir()
        stage.replace(target)
    return {**report, 'status': 'RESTORED_SNAPSHOT', 'target': str(target)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['verify', 'restore'])
    selection = p.add_mutually_exclusive_group(required=True)
    selection.add_argument('--region')
    selection.add_argument('--manifest', type=Path, help='Explicit data-only archive manifest')
    p.add_argument('--archives', type=Path, required=True)
    p.add_argument('--target', type=Path)
    args = p.parse_args()
    try:
        if args.manifest is not None:
            manifest = json.loads(args.manifest.read_text())
        else:
            catalog = json.loads((ROOT / 'releases/hierarchy/catalog.json').read_text())
            entry = catalog['regions'][args.region]
            manifest = json.loads((ROOT / entry['archive_manifest']).read_text())
        if args.command == 'restore':
            if args.target is None:
                raise ValueError('--target is required for restore')
            report = restore(manifest, args.archives, args.target)
        else:
            report = verify(manifest, args.archives)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        p.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
