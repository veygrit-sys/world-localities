#!/usr/bin/env python3
"""Extract hash-checked country packages; never overwrite differing files."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from addresskit.region_names import open_split_archive


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pack', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--country', required=True, help='AU, NZ, ... or shared')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.pack / 'pack_manifest.json').read_text())
    entry = manifest['shared'] if args.country == 'shared' else manifest['countries'][args.country.upper()]
    root = args.output.resolve()
    with open_split_archive(args.pack, entry) as archive:
        pending = []
        for member in archive.namelist():
            path = (root / member).resolve()
            if not path.is_relative_to(root):
                raise ValueError('unsafe archive member')
            data = archive.read(member)
            if path.exists() and path.read_bytes() != data:
                raise ValueError('refusing to overwrite differing file: ' + str(path))
            pending.append((path, data))
        for path, data in pending:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print(json.dumps({'country': args.country, 'files': len(pending), 'output': str(root)}))


if __name__ == '__main__':
    main()
