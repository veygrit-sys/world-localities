"""Offline guardrails for Azerbaijan government's 8-digit 2024 source format."""
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import azstat_2024_official_admin as az

SAMPLE=(
    "<html><body><table><tr><th>Kod</th><th>Ad</th></tr>"
    "<tr><td>00000002</td><td>BAKI ŞƏHƏRİ</td></tr>"
    "<tr><td>00100003</td><td>I. Binəqədi rayonu</td></tr>"
    "<tr><td>00102005</td><td>3. Biləcəri qəsəbə iəd</td></tr>"
    "<tr><td>00102016</td><td>B i l ə c ə r i q.</td></tr>"
    "<tr><td>20000002</td><td>GƏNCƏ ŞƏHƏRİ</td></tr></table></body></html>"
).encode("utf-8")

class Classification(unittest.TestCase):
    def test_original_8_digit_lexical_id_and_status_parts(self):
        rows=az.parse(SAMPLE,minimum=5)
        self.assertEqual(len(rows),5)
        self.assertEqual(rows[0]["code"],"00000002")
        self.assertEqual(rows[0]["admin1_prefix"],"000")
        self.assertEqual(rows[3]["status_digit"],"6")
        self.assertEqual(rows[3]["admin2_slice"],"02")
        self.assertFalse(any(r["official_to_geonames_verified"] for r in rows))

    def test_spaced_native_label_only_for_candidate_search(self):
        self.assertIn("biləcəri",az.variants("B i l ə c ə r i q."))
        self.assertIn("binəgədi",az.variants("I. Binəgədi rayonu"))
        self.assertEqual(az.parse(SAMPLE)[3]["name_az_source"],"B i l ə c ə r i q.")

    def test_collisions_and_source_html_schema_fail_closed(self):
        with self.assertRaises(ValueError):az.parse(SAMPLE+SAMPLE,minimum=5)
        with self.assertRaises(ValueError):az.parse(b"<html><p>No table</p></html>")
        with self.assertRaises(ValueError):az.parse(SAMPLE,minimum=100)

    def test_no_postal_ids_generated(self):
        sample_gn=[{"id":"gn:1","kind":"locality","name":"Biləcəri","asciiname":"Bilacari","alternatenames":""}]
        report=az.audit(SAMPLE,minimum=5,geonames=sample_gn)
        self.assertEqual(report["official_code_to_geonames_verified"],0)
        self.assertEqual(report["official_code_to_postcode_verified"],0)
        self.assertFalse(report["is_postcode_source"])
        self.assertGreaterEqual(report["geonames_review_candidates"]["unique_unreviewed"],1)

if __name__=="__main__":unittest.main()
