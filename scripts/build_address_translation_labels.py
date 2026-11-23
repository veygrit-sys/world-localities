"""Reproduce the small address display name table from a local Unicode CLDR 48 tree.

Usage: python scripts/build_address_translation_labels.py /path/to/cldr-release-48 --check
Only fully spelled labels (no CLDR inheritance marker or alternatives) are selected.
The pinned blob hashes are Git blob SHA-1s, including the standard object header.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "addressing/translation_labels.json"
LANGUAGES = {"en": "en", "ja": "ja", "zh": "zh-Hans", "zh_Hant": "zh-Hant"}
PINS = {
    "common/main/en.xml": "50319634140f54c1960559c48e3b5c9e7c1c5a74",
    "common/main/ja.xml": "ccc773a50abd146969622b7d52d559ecebced5cb",
    "common/main/zh.xml": "9202c22bd6e8986c53d3df91a770a4dad4d9a55b",
    "common/main/zh_Hant.xml": "bcafa82732bde0a36e7371ad52ebababeaf6a10b",
    "common/subdivisions/en.xml": "d9c5a88debdf65136cadaa3e0bb417338ae9629a",
    "common/subdivisions/ja.xml": "d3d0575886b344a1840c1790c36d4f814caa0a93",
    "common/subdivisions/zh.xml": "81b85047f0af8ad3d5d439f955088c764d0141d7",
    "common/subdivisions/zh_Hant.xml": "6cfe52e0224d95a784a3ea315729c83d012ac123",
}


def build(tree):
    scope = json.loads((ROOT / "addressing/profiles.json").read_text())["country_codes"]
    countries, subdivisions = {}, {}
    for path, pin in PINS.items():
        data = (tree / path).read_bytes()
        if hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest() != pin:
            raise ValueError(f"CLDR release 48 input differs: {path}")
        lang = LANGUAGES[Path(path).stem]
        root = ET.fromstring(data)
        table, selector = (countries, "./localeDisplayNames/territories/territory") if "/main/" in path else (
            subdivisions, "./localeDisplayNames/subdivisions/subdivision")
        for el in root.findall(selector):
            code, text = el.attrib["type"], el.text
            if ("alt" in el.attrib or not text or text == "↑↑↑"
                    or (table is countries and code not in scope)
                    or (table is subdivisions and not re.fullmatch(r"(cn|jp|us)([a-z]{2}|[0-9]{2})", code))):
                continue
            table.setdefault(code, {})[lang] = [text, el.get("draft", "approved")]

    def rows(table):
        return ",\n".join("    " + json.dumps(k) + ": " + json.dumps(v, ensure_ascii=False, separators=(",", ":"))
                          for k, v in sorted(table.items()))
    return ('{\n  "release": "48",\n  "license": "Unicode-3.0",\n  "source_blobs": {\n' + rows(PINS)
            + '\n  },\n  "countries": {\n' + rows(countries) + '\n  },\n  "subdivisions": {\n'
            + rows(subdivisions) + '\n  }\n}\n')


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("cldr_tree", type=Path)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    result = build(args.cldr_tree)
    if args.check:
        if result != OUTPUT.read_text(encoding="utf-8"):
            raise SystemExit("Generated labels differ from the committed projection")
    else:
        OUTPUT.write_text(result, encoding="utf-8")
