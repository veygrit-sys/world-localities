import csv
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from localities.open_reference import jp


class JapaneseGazetteerTests(unittest.TestCase):
    def test_source_projection(self):
        directory = Path(jp.__file__).resolve().parent
        source = json.loads((directory / "source.json").read_text(encoding="utf-8"))
        data = (directory / "names.csv").read_bytes()
        rows = list(csv.DictReader(data.decode("utf-8").splitlines()))
        summary = source["projection"]
        self.assertEqual(sha256(data).hexdigest(), summary["sha256"])
        self.assertEqual(len(rows), len({r["source_row"] for r in rows}))
        self.assertEqual(len(rows), summary["records"])
        self.assertEqual(Counter(r["classification"] for r in rows), summary["classes"])
        self.assertEqual(sum(not r["kanji"] for r in rows), summary["missing_extracted_kanji"])

    def test_changed_snapshot_is_rejected_before_lookup(self):
        source = Path(jp.__file__).resolve().parent
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            (directory / "source.json").write_bytes((source / "source.json").read_bytes())
            (directory / "names.csv").write_bytes((source / "names.csv").read_bytes() + b"\n")
            with patch.object(jp, "_DIRECTORY", directory):
                jp._index.cache_clear()
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    jp.lookup("網走市")

    def test_same_record_can_be_found_using_three_scripts(self):
        results = jp.lookup("網走市")
        self.assertEqual(results, jp.lookup("あばしりし"))
        self.assertEqual(results, jp.lookup(" abashiri   SHI "))
        self.assertEqual(len(results), 1)
        record = results[0]
        self.assertIn("国土地理院・海上保安庁", record["attribution"])
        self.assertTrue(record["terms_url"].startswith("https://www.gsi.go.jp/"))
        self.assertEqual(record["source_row"], 3)
        self.assertTrue(record["source_url"].endswith("#page=8"))
        self.assertEqual(jp.lookup(record["record_id"]), results)

    def test_ambiguous_city_is_preserved(self):
        rows = jp.lookup("府中市")
        self.assertEqual(rows, jp.lookup("Fuchu Shi"))
        self.assertEqual({r["source_grid"] for r in rows}, {"5339", "5133"})
        self.assertEqual(len({r["record_id"] for r in rows}), 2)

    def test_unextractable_kanji_and_unsupported_inputs(self):
        self.assertIsNone(jp.lookup("Ashiya Shi")[0]["kanji"])
        for query in ("", "網走", "053-0000", "6644", "Ariake Kai"):
            self.assertEqual(jp.lookup(query), [])

    def test_returned_values_do_not_mutate_snapshot(self):
        jp.lookup("府中市")[0]["source_grid"] = "0000"
        self.assertNotEqual(jp.lookup("府中市")[0]["source_grid"], "0000")
