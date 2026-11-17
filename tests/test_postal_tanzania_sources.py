"""Regressions for TCRA current/old column selection and PDF orientation."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from localities.postal_tanzania_sources import _columns, _spans, iter_tanzania_records


class _Page:
    def __init__(self, spans, rotation=0):
        self.values = spans
        self.rotation = rotation
        self.transferred = False

    def transfer_rotation_to_content(self):
        self.transferred = True
        self.rotation = 0

    def extract_text(self, visitor_text):
        for text, x, y in self.values:
            visitor_text(text, [1, 0, 0, 1, 0, 0], [1, 0, 0, 1, x, y], None, 11)


def _headers():
    return [("REGION", 20, 700), ("POSTCODE", 90, 700),
            ("DISTRICT", 150, 700), ("POSTCODE", 210, 700),
            ("WARD", 270, 700), ("POSTCODE", 360, 700),
            ("OLD", 430, 712), ("POSTCODE", 420, 700),
            ("MTAA/VILLAGE", 480, 700)]


class TanzaniaPostalTests(unittest.TestCase):
    def _parse(self, pages, source=None):
        source = source or {"format": "official_postal_source", "adapter": "tz_tcra_ward_pdf", "expected_country": "TZ",
                            "region_name": "Songwe"}
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "source.pdf"
            path.write_bytes(b"%PDF-fixture")
            with patch("pypdf.PdfReader") as reader:
                reader.return_value.pages = pages
                return list(iter_tanzania_records(source, path))

    def test_current_column_excludes_old_codes_title_and_prefixes(self):
        page = _Page(_headers() + [("REGION 54100", 20, 735),
                      ("54", 95, 650), ("541", 215, 650), ("Gua", 270, 650),
                      ("54101", 370, 650), ("53814", 430, 650),
                      ("Village 99999", 485, 650)])
        rows = self._parse([page])
        self.assertEqual([r["code"] for r in rows], ["54101"])
        self.assertEqual(rows[0]["place_name"], "Gua")
        self.assertEqual(rows[0]["admin_name1"], "Songwe")
        self.assertIn("53814", rows[0]["source_row_text"])
        self.assertTrue(rows[0]["source_locator"].startswith("pdf:page:1/text_span:"))

    def test_subsequent_page_uses_fixed_physical_columns(self):
        first = _Page(_headers() + [("Gua", 270, 650), ("54101", 370, 650)])
        second = _Page([("Saza", 270, 650), ("54105", 370, 650), ("53830", 430, 650)])
        rows = self._parse([first, second])
        self.assertEqual([r["code"] for r in rows], ["54101", "54105"])
        self.assertIn("pdf:page:2/", rows[1]["source_locator"])

    def test_old_code_left_of_centred_header_is_excluded(self):
        page = _Page(_headers() + [("Babayu", 270, 650), ("41322", 370, 650),
                                    ("41429", 414, 650)])
        self.assertEqual([r["code"] for r in self._parse([page])], ["41322"])

    def test_malformed_current_value_retained_as_anomaly(self):
        page = _Page(_headers() + [("Kilosampepo", 270, 650), ("678010", 370, 650),
                                    ("67622", 430, 650)])
        rows = self._parse([page])
        self.assertEqual(rows[0]["code"], "678010")
        self.assertEqual(rows[0]["code_kind"], "source_anomaly")
        self.assertEqual(len(rows), 1)

    def test_body_current_code_can_start_left_of_header(self):
        page = _Page(_headers() + [("Wino", 270, 650), ("57210", 357.48, 650)])
        self.assertEqual(self._parse([page])[0]["code"], "57210")

    def test_reviewed_katavi_wrap_keeps_both_source_fragments(self):
        first = _Page(_headers() + [("Kawajense", 270, 650), ("50101", 370, 650)])
        second = _Page([("Uwanja wa", 270, 650), ("50111", 370, 650),
                        ("ndege", 270, 636.89)])
        source = {"format": "official_postal_source", "adapter": "tz_tcra_ward_pdf",
                  "expected_country": "TZ", "region_name": "Katavi"}
        row = self._parse([first, second], source)[1]
        self.assertEqual(row["place_name"], "Uwanja wa ndege")
        self.assertEqual(row["source_ward_label_line"], "Uwanja wa")
        self.assertEqual(row["source_ward_label_fragments"], "Uwanja wa\nndege")

    def test_unknown_format_rejected(self):
        with self.assertRaises(ValueError):
            self._parse([], {"adapter": "tz_tcra_ward_pdf", "expected_country": "TZ"})

    def test_cmap_verified_space_cleanup_keeps_raw_label(self):
        class CMap:
            def get_object(self):
                return self

            def get_data(self):
                return b"1 beginbfchar\n<0003> <00A0>\nendbfchar"

        class FontPage(_Page):
            def extract_text(self, visitor_text):
                for text, x, y in self.values:
                    visitor_text(text, [1, 0, 0, 1, 0, 0], [1, 0, 0, 1, x, y],
                                 {"/ToUnicode": CMap()}, 11)

        page = FontPage(_headers() + [("Kigoma\x03\x03", 270, 650), ("47101", 370, 650)])
        row = self._parse([page])[0]
        self.assertEqual(row["place_name"], "Kigoma")
        self.assertEqual(row["source_ward_label_line"], "Kigoma\x03\x03")

    def test_rotated_page_is_transformed_in_memory(self):
        page = _Page(_headers() + [("Kigoma", 270, 650), ("47101", 370, 650)], rotation=90)
        self.assertEqual(self._parse([page])[0]["code"], "47101")
        self.assertTrue(page.transferred)

    def test_missing_explicit_headers_rejected(self):
        with self.assertRaisesRegex(ValueError, "WARD header"):
            self._parse([_Page([("Gua", 270, 650), ("54101", 370, 650)])])

    def test_missing_label_rejected(self):
        with self.assertRaisesRegex(ValueError, "ward label"):
            self._parse([_Page(_headers() + [("54101", 370, 650)])])

    def test_duplicate_current_code_rejected(self):
        page = _Page(_headers() + [("Gua", 270, 650), ("54101", 370, 650),
                                    ("Other", 270, 600), ("54101", 370, 600)])
        with self.assertRaisesRegex(ValueError, "duplicate ward"):
            self._parse([page])

    def test_unknown_adapter_or_wrong_country_rejected(self):
        for source in ({"adapter": "other", "expected_country": "TZ"},
                       {"adapter": "tz_tcra_ward_pdf", "expected_country": "UG"}):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self._parse([], source)

    def test_no_current_assignments_rejected(self):
        with self.assertRaisesRegex(ValueError, "no ward assignments"):
            self._parse([_Page(_headers() + [("53814", 430, 650)])])

    def test_coordinates_include_content_transform(self):
        class Transformed:
            rotation = 0

            def extract_text(self, visitor_text):
                visitor_text("47101", [0, -1, 1, 0, 0, 612],
                             [0, 10, -10, 0, 159, 448], None, 1)
        self.assertEqual(_spans(Transformed()), [("47101", 448, 453, 1)])

    def test_column_width_change_requires_review(self):
        spans = [("WARD", 10, 1, 1), ("POSTCODE", 40, 1, 2),
                 ("MTAA/VILLAGE", 200, 1, 3)]
        with self.assertRaisesRegex(ValueError, "layout"):
            _columns(spans)


if __name__ == "__main__":
    unittest.main()
