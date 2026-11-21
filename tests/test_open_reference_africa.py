import csv
import json
import unittest
import unicodedata

from localities.open_reference import africa
from localities.open_reference.africa.verify_mu_offices import project, verify


class MauritiusPostalOfficeTests(unittest.TestCase):
    def test_snapshot_integrity_and_independent_ids(self):
        counts = verify()
        self.assertEqual(counts, {"mu-mdpa-office-address": 105, "mu-mdpa-office-location": 102})
        manifest = json.loads((africa.DIRECTORY / "sources.json").read_text(encoding="utf-8"))
        identifiers = set()
        for source in manifest["sources"]:
            with (africa.DIRECTORY / source["file"]).open(encoding="utf-8", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), source["records"])
            for row in rows:
                matches = [m for m in africa.lookup(row["office_name"])
                           if m["source_id"] == source["id"]]
                self.assertEqual(len(matches), 1)
                match = matches[0]
                self.assertEqual(match["source_row"], int(row["source_row"]))
                self.assertNotIn(match["record_id"], identifiers)
                identifiers.add(match["record_id"])
        self.assertEqual(len(identifiers), 207)

    def test_postcode_retains_both_observations(self):
        rows = africa.lookup("71504")
        self.assertEqual([r["office_name"] for r in rows], ["Beau Bassin", "Beau Bassin Post Office"])
        self.assertEqual({r["address"] for r in rows}, {"Royal Road Beau Bassin"})
        self.assertNotIn("latitude", rows[0])
        self.assertEqual((rows[1]["longitude"], rows[1]["latitude"]), ("57.4675858", "-20.2266715"))
        self.assertEqual([r["record_id"] for r in rows], [r["record_id"] for r in africa.lookup("royal ROAD   Beau Bassin")])
        rows[0]["address"] = "caller edit"
        self.assertEqual(africa.lookup("71504")[0]["address"], "Royal Road Beau Bassin")

    def test_no_fuzzy_names_or_blank_field_matches(self):
        self.assertEqual(africa.lookup(unicodedata.normalize("NFD", "Bois Chéri"))[0]["postcode"], "60203")
        self.assertEqual(africa.lookup("Souillac")[0]["postcode"], "")
        self.assertEqual(africa.lookup("Post de Flacq Post Office")[0]["address"], "")
        for query in ("", "   ", "7150", "Nonexistent Office X", "071504"):
            self.assertEqual(africa.lookup(query), [])

    def test_changed_upstream_is_not_accepted(self):
        m = json.loads((africa.DIRECTORY / "sources.json").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "Source changed"):
            project(b"Post Office,Address\n", m["sources"][0])
