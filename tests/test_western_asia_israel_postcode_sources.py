"""Offline provenance and data-quality checks for source-pinned Israel files."""
from pathlib import Path
import hashlib
import io
import json
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import western_asia_israel_postcode_sources as il


def simple_xlsx(values: list[list[str]]) -> bytes:
    # Minimal valid OOXML worksheet with inline strings, no office automation.
    import xml.sax.saxutils as sx
    rows = []
    for i, fields in enumerate(values, 1):
        cells = []
        for j, field in enumerate(fields):
            col = chr(65+j)
            cells.append('<c r="%s%d" t="inlineStr"><is><t>%s</t></is></c>' %
                         (col, i, sx.escape(field)))
        rows.append('<row r="%d">%s</row>' % (i, "".join(cells)))
    content = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
               '<sheetData>%s</sheetData></worksheet>' % "".join(rows))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/worksheets/sheet1.xml", content)
    return out.getvalue()


FIELDS = ["LocationID", "Location Name", "StreetID", "Street Name",
          "House Number", "Entrance", "ZIP 5", "ZIP 7", "Remark", "Updated"]


class IsraelHistoricalPostalAudit(unittest.TestCase):
    def test_manifest_explicitly_marks_originals_unacquired(self):
        x = il.read_catalogue()
        self.assertFalse(x[il.XLSX_SOURCE]["downloaded"])
        self.assertFalse(x[il.XLSX_SOURCE]["authoritative_current_postal_operator_dataset"])
        self.assertFalse(x[il.STREETS_SOURCE]["downloaded"])

    def test_house_number_entrance_and_zip7_preserved(self):
        raw = simple_xlsx([FIELDS,
            ["123", "City", "85", "Street", "7", "A", "12345", "1234567", "", "2020"],
            ["123", "City", "85", "Street", "7", "B", "12345", "1234568", "", "2020"]])
        out = il.audit_house_workbook(raw)
        self.assertEqual(out["source_rows"], 2)
        self.assertEqual(out["counts"]["valid_zip7_shape"], 2)
        self.assertEqual(out["distinct_valid_zip7"], 2)
        self.assertEqual(out["unique_source_address_keys"], 2)
        self.assertFalse(out["current_israel_post_official_verification"])
        self.assertEqual(out["raw_address_rows_exported"], 0)

    def test_missing_leading_zero_never_silently_corrected(self):
        raw = simple_xlsx([FIELDS, ["23","City","1","Street","5","","12345","123456","",""]])
        out = il.audit_house_workbook(raw)
        self.assertEqual(out["counts"]["invalid_zip7_length_or_encoding"],1)
        self.assertEqual(out["counts"]["may_have_lost_leading_zero_in_excel"],1)
        self.assertEqual(out["distinct_valid_zip7"],0)

    def test_duplicate_house_key_conflicting_zip7_reported(self):
        raw = simple_xlsx([FIELDS,
            ["23","City","1","Street","5","A","12345","1234567","",""],
            ["23","City","1","Street","5","A","12345","1234568","",""]])
        out = il.audit_house_workbook(raw)
        self.assertEqual(out["counts"]["repeat_address_key"],1)
        self.assertEqual(out["counts"]["conflicting_zip7_for_same_address_key"],1)

    def test_archive_checksum_and_missing_headers(self):
        raw = simple_xlsx([FIELDS, ["23","City","1","Street","5","","","1234567","",""]])
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/"historical.xlsx"
            p.write_bytes(raw)
            got = il.audit_file(p, hashlib.sha256(raw).hexdigest(), il.XLSX_SOURCE)
            self.assertEqual(got["source_id"], il.XLSX_SOURCE)
            with self.assertRaisesRegex(ValueError, "SHA256"):
                il.audit_file(p, "0"*64, il.XLSX_SOURCE)
            with self.assertRaises(ValueError):
                il.audit_house_workbook(simple_xlsx([["FOO"],["bar"]]))

    def test_gov_street_code_is_not_postcode(self):
        csv = ("city_code,street_code,street_name,street_name_status,official_code\n"
               "10,101,רחוב,official,101\n"
               "10,9521,רחוב נוסף,synonym of 101,101\n"
               "11,101,Other,official,101\n").encode()
        out = il.audit_street_csv(csv)
        self.assertEqual(out["source_rows"],3)
        self.assertEqual(out["distinct_city_codes"],2)
        self.assertEqual(out["counts"]["synonym_rows"],1)
        self.assertEqual(out["counts"]["synonym_missing_canonical_in_csv"],0)
        self.assertTrue(out["street_code_is_not_postcode"])
        self.assertFalse(out["location_id_equivalent_to_2020_zip_source_verified"])

    def test_street_csv_orphan_synonym_detected(self):
        csv = ("city_code,street_code,street_name,street_name_status,official_code\n"
               "10,9521,הערבה,synonym of 101,101\n").encode()
        out = il.audit_street_csv(csv)
        self.assertEqual(out["counts"]["synonym_missing_canonical_in_csv"],1)

    def test_scope_israel_only_and_not_all_formats(self):
        with self.assertRaises(ValueError):
            il.audit_file(Path("anything"),"0"*64,"IL-UNKNOWN")
        with self.assertRaises(ValueError):
            il.audit_house_workbook(b"bad format")

    def test_bad_bidi_control_is_rejected(self):
        csv = ("city_code,street_code,street_name,street_name_status,official_code\n"
               "10,1,a\u202e,official,1\n").encode()
        with self.assertRaises(ValueError):
            il.audit_street_csv(csv)


if __name__ == "__main__":
    unittest.main()
