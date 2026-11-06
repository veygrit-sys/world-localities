"""Audit imported 2020 Kenya and 2019 Ghana geoBoundaries name/shape layers."""
import csv
import json
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "reference-boundaries"
COUNTS = {"KEN-ADM1":47, "KEN-ADM2":290, "GHA-ADM1":16, "GHA-ADM2":260}

class LicenseAndDerivedData(unittest.TestCase):
    def test_pinned_shape_data_and_original_source_receipts(self):
        receipts = json.loads((ROOT / "source_receipts.json").read_text(encoding="utf-8"))
        self.assertFalse(receipts["legal_admin_crosswalk_approved"])
        self.assertFalse(receipts["geonames_modified"])
        self.assertEqual(receipts["release"], "9469f09")
        all_rows = {}
        for layer, n in COUNTS.items():
            source = receipts["sources"][layer]
            self.assertEqual(source["rows"], n)
            self.assertEqual(len(source["sha256"]), 64)
            with (ROOT / f"{layer}-source-units.csv").open(encoding="utf-8",newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), n)
            self.assertEqual(len({r["boundary_shape_id"] for r in rows}), n)
            self.assertTrue(all(r["source_sha256"] == source["sha256"] for r in rows))
            if layer.endswith("ADM2"):
                self.assertEqual(sum(bool(r["parent_shape_id"]) for r in rows), n)
            all_rows[layer] = rows
        for iso in ("KEN", "GHA"):
            states = {r["boundary_shape_id"] for r in all_rows[f"{iso}-ADM1"]}
            self.assertTrue(all(r["parent_shape_id"] in states
                                for r in all_rows[f"{iso}-ADM2"]))

    def test_unresolved_cases_remain_review_only(self):
        report = json.loads((ROOT / "unresolved-spatial-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(report["approved_administrative_parent_links"], 0)
        self.assertFalse(report["original_geonames_changed"])
        self.assertEqual(report["input_unresolved_cases"], {"KE":69,"GH":11})
        with (ROOT/"unresolved-spatial-review.csv").open(encoding="utf-8", newline="") as stream:
            cases=list(csv.DictReader(stream))
        self.assertEqual(len(cases),80)
        self.assertEqual(Counter(r["country"] for r in cases), {"KE":69,"GH":11})
        self.assertTrue(all(r["approved_administrative_parent"] == "false" for r in cases))
        self.assertEqual(sum(r["finding"]=="name_and_spatial_area_candidate" for r in cases), 3)
        self.assertEqual(sum(r["finding"]=="source_state_conflicts_with_spatial_area" for r in cases), 6)

if __name__=="__main__":
    unittest.main()
