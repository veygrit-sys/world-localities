"""Specific official-source layouts reject ambiguous rows and keep provenance."""

import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from localities.postal_official import iter_official_records


class OfficialPostalSources(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def source(self, adapter="na_nampost_html", country="NA", kind="official_full"):
        return {"format": "official_postal_source", "adapter": adapter,
                "expected_country": country, "default_code_kind": kind}

    def html(self, text):
        path = self.root / "source.html"
        path.write_text(text, encoding="utf-8")
        return path

    @staticmethod
    def namibia_table(rows):
        return "<table><tbody>" + rows + "</tbody></table>"

    @staticmethod
    def header(name):
        return f"<tr><th>{name}</th><th>Post Code</th></tr>"

    @staticmethod
    def row(name, code):
        return f"<tr><td>{name}</td><td>{code}</td></tr>"

    def records(self, source, path):
        return list(iter_official_records(source, path))

    def kosovo_html(self, entries):
        return self.html("<script>const entries = " + json.dumps(entries, ensure_ascii=False) + ";</script>")

    def pdf(self, lines):
        from pypdf import PdfWriter
        from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
        writer = PdfWriter()
        page = writer.add_blank_page(width=500, height=500)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): writer._add_object(font)
        })})
        content = ["BT /F1 10 Tf 10 480 Td"]
        for number, line in enumerate(lines):
            if number:
                content.append("0 -14 Td")
            escaped = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            content.append(f"({escaped}) Tj")
        content.append("ET")
        stream = DecodedStreamObject()
        stream.set_data(" ".join(content).encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
        path = self.root / "source.pdf"
        with path.open("wb") as output:
            writer.write(output)
        return path

    def test_adapter_country_format_and_kind_are_whitelisted(self):
        valid = self.source()
        for source in (None, {}, {**valid, "adapter": "arbitrary_import"},
                       {**valid, "expected_country": "XK"}, {**valid, "expected_country": None},
                       {**valid, "format": "html"}, {**valid, "default_code_kind": []},
                       {**valid, "default_code_kind": "source_full"}):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.records(source, self.root / "not-opened")

    def test_namibia_region_headers_are_carried_in_order(self):
        path = self.html(self.namibia_table(
            self.header("KHOMAS REGION") + self.row("Office &amp; Kiosk", "00001")
            + '<tr><td colspan="2">-</td></tr>'
            + self.header("KAVANGO EAST") + self.row("Second", "19002")
        ))
        records = self.records(self.source(), path)
        self.assertEqual([row["admin_name1"] for row in records], ["KHOMAS REGION", "KAVANGO EAST"])
        self.assertEqual(records[0]["code"], "00001")
        self.assertEqual(records[0]["place_name"], "Office & Kiosk")
        self.assertEqual(records[1]["postal_use"], "postal_infrastructure")
        self.assertIn("table:1/row:5", records[1]["source_locator"])

    def test_lossless_gzip_preserves_rows_and_requires_the_original_byte_hash(self):
        fixtures = (
            (self.source(), lambda: self.html(self.namibia_table(
                self.header("KHOMAS REGION") + self.row("Office &amp; Kiosk", "00001")))),
            (self.source("xk_postakosoves_entries", "XK"), lambda: self.kosovo_html([
                {"region": "Prishtinë", "subregion": "Prishtina", "code": "10000"}])),
            (self.source("ba_postal_pdf", "BA", "partial_or_legacy"), lambda: self.pdf(["10000 First BHP"])),
        )
        for source, create in fixtures:
            with self.subTest(adapter=source["adapter"]):
                path = create()
                expected = self.records(source, path)
                raw = path.read_bytes()
                compressed = self.root / "source.gz"
                compressed.write_bytes(gzip.compress(raw, mtime=0))
                metadata = {**source, "compression": "gzip", "uncompressed_bytes": len(raw),
                            "uncompressed_sha256": hashlib.sha256(raw).hexdigest()}
                self.assertEqual(self.records(metadata, compressed), expected)
                with self.assertRaises(ValueError):
                    self.records({**metadata, "uncompressed_sha256": "0" * 64}, compressed)

    def test_namibia_unicode_labels_and_data_rows_are_not_deduplicated(self):
        path = self.html(self.namibia_table(self.header("//KARAS REGION")
            + self.row("Ko&#235;s", "23004") + self.row("Koës Kiosk", "23004")))
        records = self.records(self.source(), path)
        self.assertEqual([row["place_name"] for row in records], ["Koës", "Koës Kiosk"])
        self.assertNotEqual(records[0]["source_locator"], records[1]["source_locator"])

    def test_namibia_data_requires_an_explicit_region_heading(self):
        path = self.html(self.namibia_table(self.row("No region", "10001")))
        with self.assertRaisesRegex(ValueError, "NamPost"):
            self.records(self.source(), path)

    def test_namibia_multiple_or_missing_tables_are_rejected(self):
        table = self.namibia_table(self.header("REGION") + self.row("One", "10001"))
        for text in ("<p>10001 One</p>", table + table):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.records(self.source(), self.html(text))

    def test_namibia_unknown_columns_codes_and_incomplete_cells_fail(self):
        bad_rows = (self.row("Place", "1001"), self.row("", "10001"),
                    self.row("Place", "100010"), '<tr><td>Place</td><td>10001</td><td>extra</td></tr>',
                    '<tr><td>Place</td><td>10001</tr>')
        for bad in bad_rows:
            with self.subTest(row=bad), self.assertRaises(ValueError):
                self.records(self.source(), self.html(self.namibia_table(self.header("REGION") + bad)))

    def test_kosovo_extracts_literal_json_and_keeps_unicode_and_locators(self):
        entries = [{"region": "Prishtinë", "subregion": "Prishtina", "code": "10000"},
                   {"region": "Prishtinë", "subregion": "Second", "code": "10000"}]
        records = self.records(self.source("xk_postakosoves_entries", "XK"), self.kosovo_html(entries))
        self.assertEqual([row["admin_name1"] for row in records], ["Prishtinë", "Prishtinë"])
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["source_locator"], "script:1/entries/index:1")
        self.assertEqual(records[1]["source_locator"], "script:1/entries/index:2")

    def test_kosovo_does_not_execute_javascript_expressions(self):
        for text in ('<script>const entries = dangerousFunction();</script>',
                     '<script>const entries = [{region:"Place",subregion:"Other",code:"10000"}];</script>',
                     '<script>const entries = [{"region":"P","subregion":"O","code":"10000"}] + anotherArray;</script>'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.records(self.source("xk_postakosoves_entries", "XK"), self.html(text))

    def test_kosovo_assignment_must_be_unique_and_inside_a_complete_script(self):
        entry = '[{"region":"P","subregion":"O","code":"10000"}]'
        for text in (f"const entries = {entry};", f"<script>const entries = {entry};",
                     f"<script>const entries = {entry}; const entries = {entry};</script>"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.records(self.source("xk_postakosoves_entries", "XK"), self.html(text))

    def test_kosovo_duplicate_fields_and_unknown_columns_are_rejected(self):
        text = '<script>const entries = [{"region":"First","region":"Second","subregion":"P","code":"10000"}];</script>'
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.records(self.source("xk_postakosoves_entries", "XK"), self.html(text))
        for entries in ([{"region": "P", "subregion": "O", "code": "10000", "unknown": "x"}],
                        [{"region": "P", "subregion": "O", "code": 10000}],
                        [{"region": "P", "subregion": "O", "code": "1000"}], []):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                self.records(self.source("xk_postakosoves_entries", "XK"), self.kosovo_html(entries))

    def test_bosnia_keeps_operator_duplicates_and_unreviewed_status(self):
        records = self.records(self.source("ba_postal_pdf", "BA", "partial_or_legacy"),
                               self.pdf(["10000 First BHP", "10000 Second PS"]))
        self.assertEqual(len(records), 2)
        self.assertEqual([row["postal_operator"] for row in records], ["BHP", "PS"])
        self.assertEqual(records[0]["source_text_line"], "10000 First BHP")
        self.assertEqual(records[1]["source_locator"], "pdf:page=1:line=2")
        self.assertTrue(all(row["operational_status"] == "unreviewed_from_pdf_text" for row in records))

    def test_bosnia_legend_and_publisher_address_are_not_postal_rows(self):
        records = self.records(self.source("ba_postal_pdf", "BA", "partial_or_legacy"),
                               self.pdf(["10000 First HP", "LEGENDA", "88000 Mostar"]))
        self.assertEqual([row["code"] for row in records], ["10000"])

    def test_bosnia_source_cannot_be_promoted_to_current_official_full(self):
        with self.assertRaisesRegex(ValueError, "partial_or_legacy"):
            self.records(self.source("ba_postal_pdf", "BA", "official_full"), self.root / "not-opened")

    def test_bosnia_ambiguous_postal_lines_and_empty_pdf_are_rejected(self):
        for lines in (["1000 First PS"], ["10000 First OTHER"], ["Title only"]):
            with self.subTest(lines=lines), self.assertRaises(ValueError):
                self.records(self.source("ba_postal_pdf", "BA", "partial_or_legacy"), self.pdf(lines))

    def test_bosnia_damaged_pdf_is_rejected(self):
        path = self.root / "damaged.pdf"
        path.write_bytes(b"Not a PDF")
        with self.assertRaisesRegex(ValueError, "PDF"):
            self.records(self.source("ba_postal_pdf", "BA", "partial_or_legacy"), path)


if __name__ == "__main__":
    unittest.main()
