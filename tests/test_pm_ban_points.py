"""Both islands use one postal code; the BAN source row owns the commune and suffix."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from addressing.address_ai import process_request
from localities.open_reference.published_points import manifest
from localities.postal_picker import build_index
from scripts.project_fr_ban import project


class SaintPierreMiquelonAddressPoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(directory.cleanup)
        cls.index = Path(directory.name) / "pm.sqlite"
        with patch("localities.postal_picker._geonames", return_value=()):
            build_index(cls.index, ["PM"])

    def run_op(self, operation, country="PM", **args):
        return process_request(dict(operation=operation, country=country, **args), index_path=self.index)["result"]

    def test_point_source_uses_territory_code_and_complete_number(self):
        components = dict(postcode="97500", city="Miquelon-Langlade", road="Rue du Baron de l’Esperance",
                          house_number="70 bis")
        response = self.run_op("validate", components=components)
        self.assertEqual(response["matched_scope"], "published_address_point")
        self.assertEqual(response["evidence"][0]["record_id"], "97501_fuxbt0_00070_bis")
        self.assertEqual(response["evidence"][0]["source_id"], "pm-ban-975")
        for country, fields in [("FR", components), ("PM", components | {"house_number": "70 ter"}),
                                ("PM", components | {"city": "Saint-Pierre"}),
                                ("PM", {k: v for k, v in components.items() if k != "postcode"})]:
            self.assertNotIn("house_number", self.run_op("validate", country, components=fields)["verified_fields"])

    def test_postal_label_and_geographic_commune_have_distinct_roles(self):
        fields = dict(postcode="97500", city="Miquelon-Langlade", road="Rue Victor Briand", house_number="7 bis")
        good = self.run_op("validate", components=fields | {"postal_city": "ST PIERRE ET MIQUELON"})
        self.assertEqual(good["matched_scope"], "published_address_point")
        self.assertIn("postal_city", good["verified_fields"])
        self.assertEqual({e["source_id"] for e in good["evidence"]}, {"pm-ban-975", "fr-laposte-hexasmal"})
        for extra in ({"postal_city": "Miquelon-Langlade"}, {"city": "ST PIERRE ET MIQUELON"},
                      {"town": "Langlade"}):
            bad = self.run_op("validate", components=fields | extra)
            self.assertNotIn("house_number", bad["verified_fields"])

    def test_postcode_opens_two_distinct_communes(self):
        response = self.run_op("suggest", postcode="97500")
        places = {x["label"] for x in response["options"] if "pm-ban-975" in x["supporting_sources"]}
        self.assertEqual(places, {"Saint-Pierre", "Miquelon-Langlade"})

    def test_rebuild_preserves_ids_and_rejects_placeholder_numbers(self):
        data = manifest("PM")
        self.assertEqual(data["counts"]["retained_ids"], 3041)
        self.assertEqual(data["counts"]["non_premise_number"], 8)
        root = Path(__file__).resolve().parents[1] / "localities/open_reference/ban/PM"
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "rebuild"
            project(data, root / "raw", target)
            self.assertEqual((target / "points-01.csv.gz").read_bytes(), (root / "points-01.csv.gz").read_bytes())
