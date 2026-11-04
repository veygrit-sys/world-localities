"""Unified command line entry point for repository-wide locality operations."""

from __future__ import annotations

import argparse
import json

from .layout import REPOSITORY_ROOT, load_catalog, validate_catalog
from .materialize import materialize_country
from .country import add_cli, run_cli


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
    add_cli(commands)
    restore = commands.add_parser("materialize", help="restore split files for one country")
    roots = materialization_roots()
    restore.add_argument("--registry", choices=sorted(roots), required=True)
    restore.add_argument("--country", required=True)
    args = parser.parse_args()

    if args.command == "country":
        try:
            result = run_cli(args)
        except (ValueError, OSError, KeyError) as error:
            parser.exit(2, str(error) + "\n")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if result.get("status") in {"failed", "unsupported"}:
            parser.exit(1)
        return

    if args.command == "layout":
        print(json.dumps(validate_catalog(), sort_keys=True))
        return
    registry_root = REPOSITORY_ROOT / roots[args.registry]
    for path in materialize_country(registry_root, args.country):
        print(path.relative_to(registry_root))


if __name__ == "__main__":
    main()
