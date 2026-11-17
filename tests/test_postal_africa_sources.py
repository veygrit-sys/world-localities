"""Mauritius CSV replay keeps source anomalies and rejects schema drift."""

import csv
import gzip
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from localities.postal_africa_sources import iter_africa_records


class MauritiusPostalSources(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "source.csv"
        self.source = {
            "format": "official_postal_source", "adapter": "mu_postal_csv4", "expected_country": "MU",
            "encoding": "utf-8-sig",
        }

    def records(self, rows, *, encoding=None):
        text = io.StringIO(newline="")
        csv.writer(text).writerows(rows)
        self.path.write_bytes(text.getvalue().encode(encoding or self.source["encoding"]))
        return list(iter_africa_records(self.source, self.path))

    def test_mainland_csv4_retains_original_code_and_fields(self):
        records = self.records([
            ["Locality", "Sub_locality", "Street", "Code"],
            ["Rose_Hill", "ROCHE BRUNES_PLAISANCE", "Berthe Street", "712547"],
            ["Rose_Hill", "ROCHE BRUNES_PLAISANCE", "Bois Noir Street", "712547"],
        ])
        self.assertEqual(len(records), 2)
        self.assertEqual([row["code"] for row in records], ["712547", "712547"])
        self.assertEqual(records[0]["place_name"], "Rose_Hill")
        self.assertEqual(records[0]["source_sublocality"], "ROCHE BRUNES_PLAISANCE")
        self.assertEqual(records[0]["source_street"], "Berthe Street")
        self.assertEqual(records[0]["source_col_4"], "712547")
        self.assertEqual(records[0]["code_kind"], "source_anomaly")
        self.assertEqual(records[0]["observation_status"], "unreviewed_code_shape")
        self.assertEqual(records[0]["source_locator"], "csv:record:2")
        self.assertEqual(records[0]["country_code"], "MU")
        self.assertEqual(records[0]["admin_name1"], "")
        self.assertEqual(records[0]["postal_use"], "source_reported_postcode")

    def test_island_csv4_preserves_alphanumeric_code(self):
        records = self.records([
            ["locality", "sublocality", "street", "code"],
            ["Agalega", "OIDC_office", "", "A1102"],
            ["Grand Montagne", "Anse Ally_Fumier", "", "R6401"],
        ])
        self.assertEqual([row["code"] for row in records], ["A1102", "R6401"])
        self.assertEqual(records[0]["source_street"], "")
        self.assertNotIn("code_kind", records[0])

    def test_csv3_cp1252_and_short_code_are_not_repaired(self):
        self.source.update(adapter="mu_postal_csv3", encoding="cp1252")
        records = self.records([
            ["Locality", "Sublocality", "PostCode"],
            ["RIVIERE COCO", "Cité de l’Est", "R251"],
        ])
        self.assertEqual(records[0]["code"], "R251")
        self.assertEqual(records[0]["source_col_2"], "Cité de l’Est")
        self.assertEqual(records[0]["source_street"], "")

    def test_gzip_cp1252_snapshot_replays_original_bytes(self):
        self.source.update(adapter="mu_postal_csv3", encoding="cp1252")
        expected = self.records([
            ["Locality", "Sublocality", "PostCode"],
            ["RIVIERE COCO", "Cité de l’Est", "R251"],
        ])
        original = self.path.read_bytes()
        self.source.update(
            compression="gzip", uncompressed_bytes=len(original),
            uncompressed_sha256=hashlib.sha256(original).hexdigest(),
        )
        self.path.write_bytes(gzip.compress(original, mtime=0))
        self.assertEqual(list(iter_africa_records(self.source, self.path)), expected)
        self.assertEqual(gzip.decompress(self.path.read_bytes()), original)

    def test_csv3_agalega_schema(self):
        self.source.update(adapter="mu_postal_csv3", encoding="cp1252")
        records = self.records([
            ["Island", "Sublocalities/Office", "Code"],
            ["Agalega", "OIDC (office)", "A1102"],
        ])
        self.assertEqual(records[0]["source_col_3"], "A1102")

    def test_missing_legacy_assignment_is_omitted_without_shifting_locators(self):
        self.source["adapter"] = "mu_postal_csv3"
        self.source["skip_blank_code_rows"] = [2]
        records = self.records([
            ["Locality", "Sublocality", "PostCode"],
            ["GOODLANDS", "Mamzelle Jeanne (Wlk III)", ""],
            ["GOODLANDS", "Other locality", " 30701 "],
        ])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source_locator"], "csv:record:3")
        self.assertEqual(records[0]["code"], " 30701 ")

    def test_blank_legacy_codes_need_exact_explicit_declaration(self):
        self.source["adapter"] = "mu_postal_csv3"
        rows = [["Locality", "Sublocality", "PostCode"], ["GOODLANDS", "Mamzelle Jeanne (Wlk III)", ""]]
        with self.assertRaisesRegex(ValueError, "empty.*code"):
            self.records(rows)
        for declared in ([3], [2, 2], [True], ["2"]):
            self.source["skip_blank_code_rows"] = declared
            with self.subTest(declared=declared), self.assertRaises(ValueError):
                self.records(rows)
        self.source["skip_blank_code_rows"] = [2]
        with self.assertRaisesRegex(ValueError, "not blank"):
            self.records([rows[0], ["GOODLANDS", "Other", "30701"]])
        self.source["skip_blank_code_rows"] = [3]
        with self.assertRaisesRegex(ValueError, "not found"):
            self.records([rows[0]])

    def test_official_source_selects_the_declared_adapter(self):
        self.source.update(format="official_postal_source", adapter="mu_postal_csv4")
        records = self.records([
            ["locality", "sublocality", "street", "code"],
            ["Agalega", "La Fourche", "", "A1101"],
        ])
        self.assertEqual(records[0]["code"], "A1101")

    def test_empty_csv4_code_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "empty.*code"):
            self.records([
                ["locality", "sublocality", "street", "code"],
                ["Agalega", "La Fourche", "", ""],
            ])

    def test_schema_drift_is_rejected(self):
        for header in (
            ["Locality", "Sub_locality", "Code", "Street"],
            ["Locality", "Locality", "Street", "Code"],
            ["locality", "Sub_locality", "street", "code"],
            ["Locality", "Sub_locality", "Street", "Code", "extra"],
        ):
            with self.subTest(header=header), self.assertRaisesRegex(ValueError, "header"):
                self.records([header])

    def test_each_adapter_rejects_the_other_schema(self):
        with self.assertRaisesRegex(ValueError, "header"):
            self.records([["Locality", "Sublocality", "PostCode"]])
        self.source["adapter"] = "mu_postal_csv3"
        with self.assertRaisesRegex(ValueError, "header"):
            self.records([["Locality", "Sub_locality", "Street", "Code"]])

    def test_wrong_row_width_is_rejected(self):
        for row in (["Agalega", "La Fourche", "A1101"], ["Agalega", "La Fourche", "", "A1101", "x"]):
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, "width"):
                self.records([["locality", "sublocality", "street", "code"], row])

    def test_country_and_encoding_must_be_explicitly_supported(self):
        for change in ({"expected_country": "NA"}, {"expected_country": None}, {"encoding": "utf-8"}, {"encoding": None}):
            with self.subTest(change=change):
                source = {**self.source, **change}
                with self.assertRaises(ValueError):
                    list(iter_africa_records(source, self.path))

    def test_invalid_utf8_and_unclosed_csv_are_rejected(self):
        self.path.write_bytes(b"\xff")
        with self.assertRaises(ValueError):
            list(iter_africa_records(self.source, self.path))
        self.path.write_text('locality,sublocality,street,code\n"Agalega,La Fourche,,A1101\n', encoding="utf-8")
        with self.assertRaises(ValueError):
            list(iter_africa_records(self.source, self.path))

    def test_quoted_newlines_do_not_shift_logical_record_locator(self):
        records = self.records([
            ["locality", "sublocality", "street", "code"],
            ["Agalega", "La\nFourche", "", "A1101"],
            ["Agalega", "OIDC_office", "", "A1102"],
        ])
        self.assertEqual(records[0]["source_col_2"], "La\nFourche")
        self.assertEqual(records[1]["source_locator"], "csv:record:3")


if __name__ == "__main__":
    unittest.main()
