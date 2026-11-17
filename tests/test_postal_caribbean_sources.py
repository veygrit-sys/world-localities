"""Country-specific PDF tables exclude examples and preserve source positions."""

import gzip
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from localities.postal_caribbean_sources import iter_caribbean_records


class CaribbeanPostalSources(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def source(self, adapter="lc_gazette_postal_pdf", country="LC"):
        return {"format": "official_postal_source", "adapter": adapter,
                "expected_country": country, "default_code_kind": "official_full"}

    def pdf(self, pages):
        from pypdf import PdfWriter
        from pypdf.generic import NameObject, DictionaryObject, DecodedStreamObject
        writer = PdfWriter()
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        font_id = writer._add_object(font)
        for lines in pages:
            page = writer.add_blank_page(width=600, height=800)
            page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
                NameObject("/F1"): font_id
            })})
            content = ["BT /F1 10 Tf 10 780 Td"]
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

    def lc_pages(self):
        pages = [[] for _ in range(20)]
        pages[0] = ["Other Gazette notice", "Unrelated business LC99 999"]
        pages[12] = ["1501", "Saint Lucia Government Gazette", "SAINT LUCIA POST AL SERVICE",
                     "Customer Notice", "DELIVERY POINT POSTCODE", "AgArd P . O LC03 101",
                     "DELIVERY POINT POSTCODE", "Baywalk (private letter boxes) LC01 601"]
        pages[13] = ["Saint Lucia Government Gazette1502", "DELIVERY POINT POSTCODE",
                     "Hospital Road P. O LC04 201", "DELIVERY POINT POSTCODE",
                     "Vieux Fort P. O LC12 201",
                     "2. The standard addressing format using postcodes are as follows:",
                     "Castries LC04 113", "Sample Box LC07 301"]
        return pages

    def records(self, source, path):
        return list(iter_caribbean_records(source, path))

    def test_lc_selects_only_assignment_rows_and_keeps_private_box_use(self):
        records = self.records(self.source(), self.pdf(self.lc_pages()))
        self.assertEqual([x["code"] for x in records], ["LC03 101", "LC01 601", "LC04 201", "LC12 201"])
        self.assertEqual(records[0]["place_name"], "AgArd P . O")
        self.assertEqual(records[1]["postal_use"], "private_letter_box")
        self.assertEqual(records[2]["source_locator"], "pdf:page=14:line=3")
        self.assertEqual(records[0]["source_text_line"], "AgArd P . O LC03 101")

    def test_lc_split_header_and_blank_lines_do_not_become_observations(self):
        pages = self.lc_pages()
        pages[12][2:3] = ["SAINT LUCIA", "POST AL SERVICE"]
        pages[12].insert(7, "")
        records = self.records(self.source(), self.pdf(pages))
        self.assertEqual(len(records), 4)

    def test_lc_malformed_or_split_code_rows_fail_without_guessing(self):
        for row in (["Place LC3 101"], ["Place LC03", "101"], ["Place LC03 101 extra"], ["LC03 101"]):
            pages = self.lc_pages()
            pages[12][5:6] = row
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.records(self.source(), self.pdf(pages))

    def test_lc_requires_notice_headers_continuation_and_end_boundary(self):
        mutations = [(12, 2, "Missing service"), (12, 6, "Unknown heading"),
                     (13, 0, "Unknown continuation"), (13, 5, "No section boundary")]
        for page, line, value in mutations:
            pages = self.lc_pages()
            pages[page][line] = value
            with self.subTest(page=page, line=line), self.assertRaises(ValueError):
                self.records(self.source(), self.pdf(pages))

    def test_lc_wrong_edition_page_count_is_rejected(self):
        with self.assertRaises(ValueError):
            self.records(self.source(), self.pdf(self.lc_pages()[:-1]))

    def ms_pages(self):
        return [["Montserrat Postal Service", "Example MSR9999", "Active Postcodes",
                 "GPO, Letter Boxes MSR1110", "Little Bay MSR1120", "Interpreting Postcodes",
                 "MSR 1110", "Contact MSR9998"], ["Sample Address MSR9997"]]

    def test_ms_reads_only_active_table_and_preserves_code_without_space(self):
        records = self.records(self.source("ms_active_postcodes_pdf", "MS"), self.pdf(self.ms_pages()))
        self.assertEqual([r["code"] for r in records], ["MSR1110", "MSR1120"])
        self.assertEqual(records[0]["place_name"], "GPO, Letter Boxes")
        self.assertEqual(records[0]["source_locator"], "pdf:page=1:line=4")

    def test_ms_missing_or_repeated_boundaries_fail(self):
        for token, replacement in (("Active Postcodes", "No table"),
                                   ("Interpreting Postcodes", "No table")):
            pages = self.ms_pages()
            pages[0] = [replacement if line == token else line for line in pages[0]]
            with self.subTest(token=token), self.assertRaises(ValueError):
                self.records(self.source("ms_active_postcodes_pdf", "MS"), self.pdf(pages))
        pages = self.ms_pages()
        pages[0].append("Active Postcodes")
        with self.assertRaises(ValueError):
            self.records(self.source("ms_active_postcodes_pdf", "MS"), self.pdf(pages))

    def test_ms_invalid_active_row_is_rejected(self):
        for value in ("Place MSR 1110", "Place MSR111", "MSR1110", "Place MSR11100"):
            pages = self.ms_pages()
            pages[0][3] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.records(self.source("ms_active_postcodes_pdf", "MS"), self.pdf(pages))

    def sh_pages(self):
        return [["Saint Helena", "Single postcode for the whole territory",
                 "STHL 1ZZ postcode", "Contact Royal Mail", "PO1 1AF", "STHL 1ZZ",
                 "S T H L 1 Z Z"], []]

    def test_sh_requires_explicit_single_code_declaration_and_ignores_contact(self):
        records = self.records(self.source("sh_upu_single_postcode_pdf", "SH"), self.pdf(self.sh_pages()))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["code"], "STHL 1ZZ")
        self.assertEqual(records[0]["postal_use"], "single_code_island")

    def test_sh_missing_declaration_or_duplicate_label_is_rejected(self):
        for update in (lambda pages: pages[0].remove("Single postcode for the whole territory"),
                       lambda pages: pages[0].append("STHL 1ZZ postcode"),
                       lambda pages: pages[0].remove("STHL 1ZZ postcode")):
            pages = self.sh_pages()
            update(pages)
            with self.assertRaises(ValueError):
                self.records(self.source("sh_upu_single_postcode_pdf", "SH"), self.pdf(pages))

    def test_lossless_gzip_replays_the_same_bytes_and_checks_original_hash(self):
        source = self.source("ms_active_postcodes_pdf", "MS")
        path = self.pdf(self.ms_pages())
        expected = self.records(source, path)
        raw = path.read_bytes()
        compressed = self.root / "source.gz"
        compressed.write_bytes(gzip.compress(raw, mtime=0))
        source.update(compression="gzip", uncompressed_bytes=len(raw),
                      uncompressed_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual(self.records(source, compressed), expected)
        with self.assertRaises(ValueError):
            self.records({**source, "uncompressed_sha256": "0" * 64}, compressed)

    def test_adapter_country_format_and_kind_are_whitelisted(self):
        valid = self.source()
        for source in (None, {}, {**valid, "adapter": "arbitrary_pdf"},
                       {**valid, "expected_country": "MS"}, {**valid, "format": "pdf"},
                       {**valid, "default_code_kind": []}, {**valid, "default_code_kind": "prefix"}):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.records(source, self.root / "not-opened")

    def test_damaged_pdf_is_rejected(self):
        path = self.root / "source.pdf"
        path.write_bytes(b"Not a PDF")
        with self.assertRaisesRegex(ValueError, "PDF"):
            self.records(self.source(), path)


if __name__ == "__main__":
    unittest.main()
