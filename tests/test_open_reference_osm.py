import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from localities.open_reference import osm


class OpenMapReferenceTests(unittest.TestCase):
    def test_pinned_projection_and_provenance(self):
        folder = Path(osm.__file__).resolve().parent
        source = json.loads((folder / "source.json").read_bytes())
        data = (folder / "records.jsonl").read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), source["projection_sha256"])
        rows = [json.loads(line) for line in data.splitlines()]
        self.assertEqual(source["record_count"], 76)
        self.assertEqual(len(rows), source["record_count"])
        self.assertEqual(len({(row["osm_type"], row["osm_id"]) for row in rows}), len(rows))
        for row in rows:
            self.assertGreater(row["osm_version"], 0)
            self.assertLessEqual(row["osm_timestamp"], source["replication_timestamp"])
            tags = row["tags"]
            self.assertEqual(tags["addr:state"], "DC")
            self.assertTrue(tags.get("addr:housenumber") and tags.get("addr:street"))
            self.assertEqual("position" in row, row["osm_type"] == "node")

    def test_source_address_on_one_object(self):
        record, = osm.lookup(" 1250 New York AVENUE   Northwest ")
        self.assertEqual(record["record_id"], "osm:node:367144504")
        self.assertEqual(record["tags"]["addr:postcode"], "20005")
        self.assertEqual(record["matched_fields"], ["addr:housenumber+addr:street"])
        self.assertEqual(record["license"], "ODbL-1.0")
        self.assertEqual(record["attribution"], "© OpenStreetMap contributors")
        self.assertEqual(record["country_code"], "US")
        self.assertEqual(record["object_version_url"].split("/")[-1], str(record["osm_version"]))
        self.assertEqual(osm.lookup(record["name"])[0]["record_id"], record["record_id"])
        self.assertEqual(osm.lookup(record["record_id"])[0]["tags"], record["tags"])
        self.assertEqual(osm.lookup("1251 New York Avenue Northwest"), [])
        self.assertEqual(osm.lookup("  "), [])
        self.assertEqual(osm.lookup("1250"), [])

    def test_address_components_as_independent_evidence(self):
        record_id = "osm:node:367144504"
        for query, field in (("New York Avenue Northwest", "addr:street"),
                             ("20005", "addr:postcode"), ("Washington", "addr:city"),
                             ("DC", "addr:state")):
            found = {record["record_id"]: record for record in osm.lookup(query)}
            self.assertEqual(found[record_id]["matched_fields"], [field])
        self.assertNotIn(record_id, [record["record_id"] for record in osm.lookup("20001")])
        self.assertEqual(osm.lookup("99999"), [])
        missing_city, = osm.lookup("osm:way:67100670")
        self.assertNotIn("addr:city", missing_city["tags"])
        city_matches = {record["record_id"] for record in osm.lookup("Washington")}
        self.assertNotIn(missing_city["record_id"], city_matches)

    def test_result_mutation_does_not_modify_cached_snapshot(self):
        record, = osm.lookup("osm:node:367144504")
        record["tags"]["addr:postcode"] = "00000"
        record["position"]["lat"] = 0
        record["matched_fields"].clear()
        clean, = osm.lookup("osm:node:367144504")
        self.assertEqual(clean["tags"]["addr:postcode"], "20005")
        self.assertNotEqual(clean["position"]["lat"], 0)
        self.assertEqual(clean["matched_fields"], ["record_id"])

    def test_first_read_detects_projection_corruption(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            folder.joinpath("source.json").write_bytes((osm._DATA / "source.json").read_bytes())
            folder.joinpath("records.jsonl").write_bytes(b"{}")
            osm._snapshot.cache_clear()
            self.addCleanup(osm._snapshot.cache_clear)
            with patch.object(osm, "_DATA", folder):
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    osm.lookup("Washington")


    def test_shared_address_preserves_candidates(self):
        matches = osm.lookup("1849 C Street Northwest")
        self.assertEqual({match["name"] for match in matches}, {"Interior Library", "Interior Museum"})

    def test_source_language_variants_resolve_to_same_object(self):
        zh, = osm.lookup("美国国家航空航天博物馆")
        self.assertEqual(zh["matched_fields"], ["name:zh", "name:zh-Hans"])
        self.assertEqual(zh["record_id"], "osm:relation:16159112")
        self.assertEqual(zh["name"], "National Air and Space Museum")
        ja, = osm.lookup(zh["tags"]["name:ja"])
        self.assertEqual(ja["record_id"], zh["record_id"])
        self.assertNotIn("position", ja)
