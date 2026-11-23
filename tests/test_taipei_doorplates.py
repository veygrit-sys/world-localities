import csv
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from localities.open_reference import lookup_reference
from localities.open_reference.taipei import DISTRICTS, district_rows, source
from localities.open_reference.taipei.project_doorplates import HEADER, project


class TaipeiDoorplatesTests(unittest.TestCase):
    def test_municipal_building_and_district_scope(self):
        def lookup(q):
            return lookup_reference("TW", q, source="taipei-doorplates")
        half = lookup("台北市信義區市府路1號")
        self.assertEqual(half["matching_records"], 1)
        self.assertEqual(half["records"], lookup("信義區市府路１號")["records"])
        self.assertEqual(half["records"][0]["record"]["district_code"], "63000020")
        self.assertEqual(half["records"][0]["record"]["village"], "西村里")
        self.assertFalse(half["deliverability_verified"])
        for q in ("市府路1號", "新北市信義區市府路1號", "信義區市府路", "信義區市府路9999999號"):
            self.assertEqual(lookup(q)["status"], "not_observed_in_snapshot")

    def test_district_archives_match_pins_and_source_totals(self):
        meta = source()
        self.assertEqual(set(meta["districts"]), set(DISTRICTS))
        total = 0
        for code in DISTRICTS:
            rows = district_rows(code)
            self.assertTrue(all(a <= b for a, b in zip(rows, rows[1:])))
            n = sum(r[3] for r in rows)
            self.assertEqual(n, meta["districts"][code]["source_rows"])
            total += n
        self.assertEqual(total + meta["excluded_incomplete_rows"], meta["source_rows"])

    def test_rebuild_rejects_changed_input_and_preserves_duplicate_counts(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw = root / "example.csv"
            with raw.open("w", encoding="utf-8", newline="") as out:
                writer = csv.writer(out)
                writer.writerow(HEADER)
                for code in DISTRICTS:
                    writer.writerow(["63000", code, "里", "", "路", "", "", "", "１號", "1", "2"])
                writer.writerow(["63000", "63000010", "里", "", "路", "", "", "", "１號", "2", "3"])
                writer.writerow(["63000", "63000010", "里", "", "路", "", "", "", "", "3", "4"])
            meta = {"raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(), "source_rows": 14}
            built = project(raw, root / "first", meta)
            self.assertEqual(built["districts"]["63000010"]["source_rows"], 2)
            self.assertEqual(built["districts"]["63000010"]["labels"], 1)
            self.assertEqual(built["excluded_incomplete_rows"], 1)
            self.assertEqual(project(raw, root / "second", built), built)
            raw.write_bytes(raw.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                project(raw, root / "bad", built)
            self.assertFalse((root / "bad").exists())
