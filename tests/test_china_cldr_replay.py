"""Regressions for offline CLDR source replay with miniature XML fixtures."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import xml.etree.ElementTree as ET

from scripts.check_china_cldr import CATALOG, verify


class ChinaCldrReplay(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.zh, self.en = (Path(tmp.name) / f"{lang}.xml" for lang in ("zh", "en"))
        for lang, path in (("zh", self.zh), ("en", self.en)):
            root = ET.Element("ldml")
            ET.SubElement(ET.SubElement(root, "identity"), "language", type=lang)
            nodes = ET.SubElement(ET.SubElement(root, "localeDisplayNames"), "subdivisions")
            for code, row in self.catalog["subdivisions"].items():
                node = ET.SubElement(nodes, "subdivision", type=code)
                node.text = row[lang]
                if row[f"{lang}_draft_status"] != "approved":
                    node.set("draft", row[f"{lang}_draft_status"])
            ET.SubElement(nodes, "subdivision", type="cnhk").text = "excluded"
            path.write_bytes(ET.tostring(root, encoding="utf-8"))
            self.catalog["source_files"][lang]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()

    def test_checks_exact_names_and_implicit_and_explicit_draft_status(self):
        verify(self.catalog, self.zh, self.en)
        for key in ("en", "zh", "en_draft_status", "zh_draft_status"):
            with self.subTest(key=key):
                row = self.catalog["subdivisions"]["cnbj"]
                original = row[key]
                row[key] = "unexpected"
                with self.assertRaisesRegex(ValueError, "cnbj"):
                    verify(self.catalog, self.zh, self.en)
                row[key] = original

    def test_rejects_swapped_sources_before_xml_comparison(self):
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            verify(self.catalog, self.en, self.zh)

    def test_rejects_missing_extra_or_duplicate_mainland_record(self):
        original = self.en.read_bytes()
        for replacement, reason in (
            (b"usxx", "keys differ"), (b"cnxx", "keys differ"), (b"cnah", "duplicate"),
        ):
            with self.subTest(replacement=replacement):
                # The excluded HK fixture can become a spurious second row.
                target = b"cnbj" if replacement == b"usxx" else b"cnhk"
                modified = original.replace(target, replacement)
                self.en.write_bytes(modified)
                self.catalog["source_files"]["en"]["sha256"] = hashlib.sha256(modified).hexdigest()
                with self.assertRaisesRegex(ValueError, reason):
                    verify(self.catalog, self.zh, self.en)
