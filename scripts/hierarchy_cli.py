"""Run a source-qualified regional hierarchy against an explicit data root."""
from __future__ import annotations
import argparse
import importlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def region_entry(region):
    catalog = json.loads((ROOT / 'releases/hierarchy/catalog.json').read_text())
    if region not in catalog['regions']:
        raise ValueError('Region is not installed: ' + region)
    return catalog['regions'][region]


def data_root(entry, supplied=None):
    root = Path(supplied).resolve() if supplied else ROOT / entry['configuration_dir']
    config = json.loads((root / entry['scope_file']).read_text())
    actual = config.get('country_codes', []) + config.get('supplementary_area_codes', [])
    if not actual:
        actual = config.get('countries', []) + config.get('territories', [])
    if set(actual) != set(entry['scope_codes']) or len(actual) != len(entry['scope_codes']):
        raise ValueError('Data root scope differs from the selected regional snapshot')
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--region', required=True)
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        entry = region_entry(args.region)
        root = data_root(entry, args.data_root)
        os.environ['WORLD_LOCALITIES_ADDRESS_ROOT'] = str(root)
        sys.path.insert(0, str(ROOT / 'address-points/adapters'))
        module = importlib.import_module(entry['module'])
        forwarded = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
        sys.argv = [entry['module'] + '.py'] + forwarded
        module.main()
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
