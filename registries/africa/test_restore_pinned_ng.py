"""Pinned Nigeria source restoration safety invariants."""
import json
import unittest
from pathlib import Path

from restore_pinned_ng import AFRICA, git_blob_sha, EXPECTED_NG_ROWS, EXPECTED_RESTORED_ROWS


class PinnedNigeriaRestore(unittest.TestCase):
    def test_git_blob_sha_matches_git_hash_object_contract(self):
        self.assertEqual(git_blob_sha(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")

    def test_restore_expected_rows_and_original_provenance(self):
        migration = json.loads((AFRICA / "migration.json").read_text(encoding="utf-8"))
        upstream = json.loads((AFRICA / "upstream/verification.json").read_text(encoding="utf-8"))
        ng = next(x for x in upstream["reports"] if x["country"] == "NG")
        missing = next(x for x in migration["missing_source_files"]
                       if x["path"].endswith("/NG/entities.csv.gz"))
        self.assertEqual(ng["rows"], EXPECTED_NG_ROWS)
        self.assertEqual(migration["records"] + EXPECTED_NG_ROWS, EXPECTED_RESTORED_ROWS)
        self.assertEqual(missing["size"], 2141219)
        self.assertEqual(missing["sha"], "f47e339f54fd7d34162d16dc1fd73d92c02d1087")
        # Works before and after a validated source restore. The receipt is
        # mandatory when NG has joined the current active source registry.
        if (AFRICA / "countries/NG").exists():
            receipt = AFRICA / "restorations/NG-pinned-source.json"
            self.assertTrue(receipt.is_file())
            restored = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(restored["source_rows"], EXPECTED_NG_ROWS)


if __name__ == "__main__":
    unittest.main()
