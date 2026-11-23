"""A failed source must remain visible without hiding the other attempts."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import crown_four_localities as crown, europe_microstates as micro
from scripts.source_recovery import download_europe, load_inventory, select_entries, verify_saved_snapshots


class SourceRecovery(unittest.TestCase):
    def test_saved_raw_sources_and_compressed_indexes_replay(self):
        report = verify_saved_snapshots()
        self.assertEqual(report["microstates"]["records"], 63870)
        self.assertEqual(report["crown"]["records"], 27104)

    def test_review_keeps_every_historical_deferred_postal_decision(self):
        doc = load_inventory()
        refs = [ref for entry in doc["entries"] for ref in entry["previous_decisions"]]
        self.assertEqual(len(refs), 38)
        self.assertEqual(len({(ref["path"], ref["key"], ref["index"]) for ref in refs}), 38)

    def test_country_filter_keeps_permission_blocker(self):
        selected = select_entries(load_inventory(), country="VN", status="permission_review")
        self.assertEqual(len(selected), 1)
        self.assertFalse(selected[0]["commercial_use_cleared"])
        self.assertEqual(select_entries(load_inventory(), country="VN", status="recovered"), [])

    def test_failure_is_reported_and_every_other_source_is_attempted(self):
        with TemporaryDirectory() as tmp:
            directory = Path(tmp)
            def acquire(source, root):
                if source == "AD":
                    raise OSError("temporary upstream failure")
                return {"country": source, "sha256": "a" * 64}
            with patch.object(micro, "download", side_effect=acquire) as call:
                report = download_europe("microstates", directory, directory / "report.json")
            self.assertEqual([item.args[0] for item in call.call_args_list], list(micro.CODES))
            self.assertEqual(report["failed"], 1)
            self.assertEqual(report["successful"], 5)
            self.assertTrue(report["completed"])
            self.assertFalse(report["index_built"])
            self.assertEqual(report, json.loads((directory / "report.json").read_text()))
            self.assertEqual(report["results"][0]["status"], "failed")

    def test_report_records_partial_progress_if_interrupted(self):
        with TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"
            with patch.object(crown, "download", side_effect=[{"source_id": "guernsey-jersey"},
                                                               KeyboardInterrupt()]):
                with self.assertRaises(KeyboardInterrupt):
                    download_europe("crown", Path(tmp), report_path)
            self.assertFalse(json.loads(report_path.read_text())["completed"])
            self.assertEqual(len(json.loads(report_path.read_text())["results"]), 1)

    def test_existing_receipt_is_not_overwritten(self):
        with TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            report.write_text("previous snapshot")
            with patch.object(crown, "download") as call:
                with self.assertRaises(ValueError):
                    download_europe("crown", Path(tmp), report)
            call.assert_not_called()
            self.assertEqual(report.read_text(), "previous snapshot")


if __name__ == "__main__":
    unittest.main()
