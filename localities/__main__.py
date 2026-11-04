"""Unified command line entry point for repository-wide locality operations."""

from __future__ import annotations

import argparse
import json

from .layout import REPOSITORY_ROOT, load_catalog, validate_catalog
from .materialize import materialize_country


def materialization_roots() -> dict[str, str]:
    catalog = load_catalog()
    return {
        entry["id"]: entry["path"]
        for entry in catalog["registries"]
        if entry.get("split_materialization")
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("layout", help="validate registry paths and duplicate-code rules")
    restore = commands.add_parser("materialize", help="restore split files for one country")
    roots = materialization_roots()
    restore.add_argument("--registry", choices=sorted(roots), required=True)
    restore.add_argument("--country", required=True)
    args = parser.parse_args()

    if args.command == "layout":
        print(json.dumps(validate_catalog(), sort_keys=True))
        return
    registry_root = REPOSITORY_ROOT / roots[args.registry]
    for path in materialize_country(registry_root, args.country):
        print(path.relative_to(registry_root))


if __name__ == "__main__":
    main()
