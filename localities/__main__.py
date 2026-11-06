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
    balkan = commands.add_parser("balkan", help="audit and index the 11-country Balkan/Central Europe layer")
    balkan.add_argument("balkan_args", nargs=argparse.REMAINDER)
    microstates = commands.add_parser("microstates", help="audit and build six sovereign European microstates")
    microstates.add_argument("microstate_args", nargs=argparse.REMAINDER)
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

    if args.command == "microstates":
        import sqlite3
        from scripts.europe_microstates import main as microstates_main
        try:
            microstates_main(args.microstate_args)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, RuntimeError) as error:
            parser.exit(2, str(error) + "\n")
        return

    if args.command == "balkan":
        import sqlite3
        import zipfile
        from scripts.balkan_11_localities import cli as balkan_cli
        try:
            balkan_cli(args.balkan_args)
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error, zipfile.BadZipFile) as error:
            parser.exit(2, str(error) + "\n")
        return

    registry_root = REPOSITORY_ROOT / roots[args.registry]
    for path in materialize_country(registry_root, args.country):
        print(path.relative_to(registry_root))


if __name__ == "__main__":
    main()
