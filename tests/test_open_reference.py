import json
from pathlib import Path
import subprocess
import sys
import unittest

from addressing import lookup_reference


ROOT = Path(__file__).resolve().parents[1]


class OpenReferenceTests(unittest.TestCase):
    def test_address_and_postcode_must_share_the_published_record(self):
        address = "1600 Pennsylvania Avenue NW"
        result = lookup_reference("us", address, "20500", source="dc-mar")
        self.assertEqual(result["matching_records"], 1)
        self.assertEqual(result["records"][0]["record"]["record_id"], "US-DC-MAR:293211")
        self.assertFalse(result["deliverability_verified"])
        mismatch = lookup_reference("US", address, "20004", source="dc-mar")
        self.assertEqual(mismatch["status"], "no_common_record")
        self.assertEqual(mismatch["records"], [])

    def test_separate_publishers_cannot_jointly_satisfy_a_query(self):
        answer = lookup_reference("US", "US-DC-MAR:293211", "osm:node:367144504")
        self.assertEqual(answer["status"], "no_common_record")

    def test_homonyms_survive_and_limits_only_affect_display(self):
        result = lookup_reference("JP", "府中市", "Fuchu Shi", limit=1)
        self.assertEqual(result["matching_records"], 2)
        self.assertTrue(result["truncated"])
        self.assertEqual(len(result["records"]), 1)

    def test_unsupported_unobserved_and_invalid_input(self):
        self.assertEqual(lookup_reference("ZZ", "Example")["status"], "no_source_for_country")
        self.assertEqual(lookup_reference("JP", "架空例123456")["status"], "not_observed_in_snapshot")
        for args, kwargs in [
            (("ＪＰ", "網走市"), {}), (("JP", "網走市", ""), {}),
            (("JP", "a\nb"), {}), (("JP", "府中市"), {"source": "dc-mar"}),
            (("US", "Washington"), {"limit": 0}),
        ]:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                lookup_reference(*args, **kwargs)

    def test_public_cli_preserves_language_and_source_record(self):
        command = [sys.executable, "-m", "addressing", "reference", "--country", "CN",
                   "--query", "駐深圳聯絡處", "--also", "518033"]
        result = json.loads(subprocess.check_output(command, cwd=ROOT))
        self.assertEqual(result["status"], "observed")
        record, = result["records"]
        self.assertEqual(record["record"]["name"]["en"], "Shenzhen Liaison Unit")
        self.assertIn("zh-Hant", record["record"]["address"])

    def test_cities_do_not_cross_countries_or_identically_named_records(self):
        options = {"source": "un-urban-centres"}
        self.assertEqual(lookup_reference("CN", "Anping", **options)["matching_records"], 2)
        self.assertEqual(lookup_reference("JP", "Anping", **options)["matching_records"], 0)
        self.assertEqual(lookup_reference("CN", "Beijing", "un-wup2025:9020",
                                          **options)["matching_records"], 1)

    def test_postal_cli_keeps_input_roles_distinct(self):
        command = [sys.executable, "scripts/world_postcodes.py", "validate-place", "--source",
                   "la-poste", "--country", "FR", "--code", "75007", "--locality"]
        for city, expected in [("Paris", "matched"), ("Ajaccio", "no_match_in_source")]:
            with self.subTest(city=city):
                result = json.loads(subprocess.check_output([*command, city], cwd=ROOT))
                self.assertEqual(result["status"], expected)
