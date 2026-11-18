"""Replay the mainland China display-name index from two local CLDR 48 source files."""

import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


CATALOG = Path(__file__).resolve().parents[1] / "addressing/china_reference/cldr-subdivision-names.json"
CLDR_REVISION = "acd6d88ae493633240e19a87a721076a8a75c310"
OTHER_ADDRESS_PROFILES = {"cnhk", "cnmo", "cntw"}


def verify(catalog, zh_path, en_path):
    if catalog["release"] != "48" or catalog["revision"] != CLDR_REVISION:
        raise ValueError("expected the pinned CLDR 48 revision")
    expected = catalog["subdivisions"]
    if len(expected) != 31:
        raise ValueError("expected 31 mainland subdivisions in the index")
    replay = {}
    for locale, path in (("zh", zh_path), ("en", en_path)):
        source = path.read_bytes()
        if hashlib.sha256(source).hexdigest() != catalog["source_files"][locale]["sha256"]:
            raise ValueError(f"{locale} XML SHA-256 mismatch")
        root = ET.fromstring(source)
        language = root.find("identity/language")
        if language is None or language.get("type") != locale:
            raise ValueError(f"expected {locale} XML locale")
        found = set()
        for node in root.findall("localeDisplayNames/subdivisions/subdivision"):
            code = node.attrib["type"]
            if not code.startswith("cn") or code in OTHER_ADDRESS_PROFILES:
                continue
            if code in found:
                raise ValueError(f"duplicate {locale} subdivision: {code}")
            found.add(code)
            row = replay.setdefault(code, {})
            row[locale] = node.text
            row[f"{locale}_draft_status"] = node.get("draft", "approved")
        if found != expected.keys():
            raise ValueError(f"{locale} subdivision keys differ: {sorted(found ^ expected.keys())}")
    for code, row in replay.items():
        if expected[code] != row:
            raise ValueError(f"subdivision name or draft status mismatch: {code}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zh", type=Path, required=True)
    parser.add_argument("--en", type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    try:
        verify(catalog, args.zh, args.en)
    except (ValueError, OSError, ET.ParseError) as error:
        parser.exit(1, f"{error}\n")
    print("Verified 31 mainland subdivision name pairs and draft statuses against CLDR 48.")


if __name__ == "__main__":
    main()
