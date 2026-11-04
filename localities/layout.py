"""Validate the repository's registry catalog and stable directory boundaries."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path, PurePosixPath
import re
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = Path(__file__).with_name("registry_catalog.json")
ROLES = {"official_overlay", "regional_coordinator", "regional_registry"}


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_catalog(root: Path = REPOSITORY_ROOT) -> dict[str, Any]:
    catalog = load_catalog()
    if catalog.get("schema_version") != 1 or catalog.get("package") != "localities":
        raise ValueError("unsupported registry catalog")

    paths: set[str] = set()
    identifiers: set[str] = set()
    for registry in catalog.get("registries", []):
        relative = PurePosixPath(registry["path"])
        identifier = registry.get("id", "")
        if relative.is_absolute() or len(relative.parts) != 1 or relative.name in paths:
            raise ValueError("invalid or duplicate registry path")
        if not re.fullmatch(r"[a-z]+(?:-[a-z]+)*", identifier) or identifier in identifiers:
            raise ValueError("invalid or duplicate registry id")
        if registry.get("role") not in ROLES or not registry.get("scope"):
            raise ValueError(f"invalid registry entry: {relative}")
        directory = root / relative
        if not directory.is_dir() or not (directory / "README.md").is_file():
            raise ValueError(f"missing registry or README: {relative}")
        paths.add(relative.name)
        identifiers.add(identifier)

    consumers: set[str] = set()
    consumer_links: set[tuple[str, str]] = set()
    for component in catalog.get("shared_components", []):
        module_path = root.joinpath(*component["module"].split(".")).with_suffix(".py")
        if not module_path.is_file():
            raise ValueError(f"missing shared component: {component['module']}")
        for name in component.get("consumers", []):
            relative = PurePosixPath(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("unsafe shared-component consumer")
            link = (component["module"], name)
            if link in consumer_links or not (root / relative).is_file():
                raise ValueError(f"missing or duplicate consumer: {name}")
            consumers.add(name)
            consumer_links.add(link)

    allowed_basenames = set(catalog.get("scoped_python_basenames", {}))
    by_name: dict[str, list[Path]] = defaultdict(list)
    by_hash: dict[str, list[Path]] = defaultdict(list)
    for path in root.rglob("*.py"):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        by_name[path.name].append(path)
        by_hash[hashlib.sha256(path.read_bytes()).hexdigest()].append(path)
    unexpected_names = {
        name: files
        for name, files in by_name.items()
        if len(files) > 1 and name not in allowed_basenames
    }
    if unexpected_names:
        detail = ", ".join(
            f"{name} ({len(files)})" for name, files in sorted(unexpected_names.items())
        )
        raise ValueError(f"duplicate Python basenames: {detail}")
    exact_duplicates = [files for files in by_hash.values() if len(files) > 1]
    if exact_duplicates:
        detail = ", ".join(
            " = ".join(str(path.relative_to(root)) for path in files)
            for files in exact_duplicates
        )
        raise ValueError(f"exact duplicate Python files: {detail}")

    return {
        "status": "passed",
        "registry_count": len(paths),
        "shared_component_count": len(catalog["shared_components"]),
        "consumer_count": len(consumers),
        "python_files": sum(len(files) for files in by_name.values()),
        "duplicate_python_basenames": sorted(
            name for name, files in by_name.items() if len(files) > 1
        ),
        "exact_duplicate_python_files": 0,
    }


if __name__ == "__main__":
    print(json.dumps(validate_catalog(), sort_keys=True))
