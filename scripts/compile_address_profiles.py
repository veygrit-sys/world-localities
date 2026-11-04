#!/usr/bin/env python3
"""Compile pinned OpenCage address templates into deterministic runtime JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import yaml


FIELDS = {
    "address_template",
    "fallback_template",
    "replace",
    "postformat_replace",
    "add_component",
    "change_country",
    "use_country",
}
LANGUAGE_ALIASES = {"jp": "ja"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compile_profiles(source: Path) -> dict[str, object]:
    countries_path = source / "conf/countries/worldwide.yaml"
    codes_path = source / "conf/country_codes.yaml"
    languages_path = source / "conf/country2lang.yaml"
    state_codes_path = source / "conf/state_codes.yaml"
    county_codes_path = source / "conf/county_codes.yaml"
    license_path = source / "LICENSE.txt"
    source_paths = (
        countries_path,
        codes_path,
        languages_path,
        state_codes_path,
        county_codes_path,
        license_path,
    )
    for path in source_paths:
        if not path.is_file():
            raise ValueError(f"missing address-formatting source file: {path}")
    commit = subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True
    ).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("invalid source commit")
    raw_profiles = yaml.safe_load(countries_path.read_text(encoding="utf-8"))
    raw_codes = yaml.safe_load(codes_path.read_text(encoding="utf-8"))
    raw_languages = yaml.safe_load(languages_path.read_text(encoding="utf-8"))
    state_codes = yaml.safe_load(state_codes_path.read_text(encoding="utf-8"))
    county_codes = yaml.safe_load(county_codes_path.read_text(encoding="utf-8"))
    country_codes = sorted(str(code) for code in raw_codes)
    if len(country_codes) != 251:
        raise ValueError("unexpected country-code coverage")
    profiles: dict[str, dict[str, object]] = {}
    for key, raw in raw_profiles.items():
        key = str(key)
        match = re.fullmatch(r"([A-Z]{2})(?:_([A-Za-z0-9_-]+))?", key)
        if not match:
            continue
        if not isinstance(raw, dict):
            raise ValueError(f"unexpected address profile: {key}")
        country_code, language = match.groups()
        profile = {
            name: value for name, value in raw.items() if name in FIELDS
        }
        profile["country_code"] = country_code
        if language:
            profile["language"] = language
        profiles[key] = profile
    if set(country_codes) - set(profiles):
        raise ValueError("country profile missing")
    combined = hashlib.sha256()
    for path in source_paths:
        combined.update(path.name.encode("utf-8") + b"\0" + path.read_bytes())
    return {
        "schema_version": 1,
        "representation": "compiled display-compatibility address templates; not postal deliverability evidence",
        "source": {
            "repository": "https://github.com/OpenCageData/address-formatting",
            "commit": commit,
            "license": "MIT",
            "sha256": combined.hexdigest(),
            "files": {
                path.relative_to(source).as_posix(): digest(path) for path in source_paths
            },
        },
        "country_codes": country_codes,
        "country_languages": {
            str(country): [
                LANGUAGE_ALIASES.get(item.strip(), item.strip())
                for item in str(languages).split(",")
            ]
            for country, languages in sorted(raw_languages.items())
        },
        "state_codes": state_codes,
        "county_codes": county_codes,
        "profiles": dict(sorted(profiles.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    payload = compile_profiles(args.source.resolve())
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded, encoding="utf-8")
    print(
        json.dumps(
            {
                "countries": len(payload["country_codes"]),
                "profiles": len(payload["profiles"]),
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
