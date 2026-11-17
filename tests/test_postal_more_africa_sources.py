from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from localities.postal_more_africa_sources import iter_more_africa_records


class MoreAfricaPostalSourcesTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "source"

    def records(self, adapter, country, text, **extra):
        self.path.write_text(text, encoding="utf-8")
        return list(iter_more_africa_records({
            "format": "official_postal_source", "adapter": adapter,
            "expected_country": country, **extra,
        }, self.path))

    @staticmethod
    def eswatini():
        tables = []
        for region, rows in [
            ("HHOHHO REGION", [("Swazi Plaza", "H103"), ("Eveni", "H103")]),
            ("MANZINI REGION", [("Manzini", "M200")]),
            ("SHISELWENI REGION", [("Nhlangano", "S400")]),
            ("LUBOMBO REGION", [("Siteki", "L300")]),
        ]:
            body = "".join(f"<tr><td>{name}</td><td>{code}</td></tr>" for name, code in rows)
            tables.append(f"<table><tr><th>{region} </th><th>CODE </th></tr>{body}</table>")
        return "<p>Contact H999, 24052000</p>" + "".join(tables)

    @staticmethod
    def senegal(records):
        return "// Source publication\r\nconst PE_ALL_POSTAL_CODES = " + json.dumps(records) + ";\n"

    def test_eswatini_keeps_shared_codes_and_region_and_ignores_contacts(self):
        rows = self.records("sz_eswatinipost_html", "SZ", self.eswatini())
        self.assertEqual(len(rows), 5)
        self.assertEqual([row["code"] for row in rows[:2]], ["H103", "H103"])
        self.assertEqual(rows[1]["place_name"], "Eveni")
        self.assertEqual(rows[-1]["admin_name1"], "LUBOMBO REGION")
        self.assertTrue(rows[-1]["source_locator"].startswith("table:4/row:2/html_line:"))

    def test_eswatini_rejects_unexpected_region_table(self):
        with self.assertRaisesRegex(ValueError, "region header"):
            self.records("sz_eswatinipost_html", "SZ", self.eswatini().replace("MANZINI REGION", "OTHER"))

    def test_eswatini_rejects_code_from_wrong_region(self):
        with self.assertRaisesRegex(ValueError, "assignment row"):
            self.records("sz_eswatinipost_html", "SZ", self.eswatini().replace("M200", "H200"))

    def test_eswatini_rejects_truncated_table(self):
        with self.assertRaises(ValueError):
            self.records("sz_eswatinipost_html", "SZ", self.eswatini().removesuffix("</table>"))

    def test_eswatini_rejects_added_table(self):
        with self.assertRaisesRegex(ValueError, "four complete"):
            self.records("sz_eswatinipost_html", "SZ", self.eswatini() + "<table></table>")

    def test_senegal_keeps_literal_names_and_leading_zeroes(self):
        rows = self.records("sn_laposte_postal_js", "SN", self.senegal([
            {"name": "Thiès (Quartier, Région)", "code": "00123"},
            {"name": "Second locality", "code": "00123"},
        ]))
        self.assertEqual(rows[0]["place_name"], "Thiès (Quartier, Région)")
        self.assertEqual([row["code"] for row in rows], ["00123", "00123"])
        self.assertEqual(rows[1]["source_locator"], "json:PE_ALL_POSTAL_CODES/item:2")
        self.assertNotIn("code_kind", rows[0])

    def test_senegal_does_not_pad_source_anomalies(self):
        rows = self.records("sn_laposte_postal_js", "SN", self.senegal([
            {"name": "Short", "code": "36"}, {"name": "Zero", "code": "0"},
        ]))
        self.assertEqual([row["code"] for row in rows], ["36", "0"])
        self.assertTrue(all(row["code_kind"] == "source_anomaly" for row in rows))

    def test_senegal_rejects_duplicate_json_fields(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.records("sn_laposte_postal_js", "SN",
                         'const PE_ALL_POSTAL_CODES = [{"name":"A","code":"10000","code":"20000"}];')

    def test_senegal_does_not_evaluate_javascript(self):
        for text in [
            'const PE_ALL_POSTAL_CODES = [{"name":"A","code": String(10000)}];',
            self.senegal([{"name": "A", "code": "10000"}]) + "throw new Error();",
            'let PE_ALL_POSTAL_CODES = [{"name":"A","code":"10000"}];',
        ]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                self.records("sn_laposte_postal_js", "SN", text)

    def test_senegal_rejects_empty_or_wrong_shape_or_numeric_codes(self):
        for records in [[], [{"name": "A", "code": 10000}], [{"name": "A", "code": ""}],
                        [{"name": "A", "code": "10000", "extra": "ignored?"}]]:
            with self.subTest(records=records), self.assertRaises(ValueError):
                self.records("sn_laposte_postal_js", "SN", self.senegal(records))

    def test_country_and_adapter_are_bound(self):
        for adapter, country in [("sz_eswatinipost_html", "SN"), ("unknown", "SN")]:
            with self.subTest(adapter=adapter), self.assertRaises(ValueError):
                self.records(adapter, country, self.eswatini())

    def test_lossless_gzip_replay(self):
        original = self.senegal([{"name": "Dakar", "code": "10000"}]).encode()
        self.path.write_bytes(gzip.compress(original, mtime=0))
        rows = list(iter_more_africa_records({
            "format": "official_postal_source", "adapter": "sn_laposte_postal_js",
            "expected_country": "SN", "compression": "gzip",
            "uncompressed_bytes": len(original), "uncompressed_sha256": hashlib.sha256(original).hexdigest(),
        }, self.path))
        self.assertEqual(rows[0]["code"], "10000")


if __name__ == "__main__":
    unittest.main()
