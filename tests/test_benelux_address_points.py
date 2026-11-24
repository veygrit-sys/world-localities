"""Address-point evidence must survive the picker, index and public API together."""

from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from addressing.address_ai import process_request
from localities.postal_picker import build_index


class BeneluxPointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(tmp.cleanup)
        cls.db = Path(tmp.name) / "points.sqlite"
        # Exercise genuine embedded snapshots; leave the unrelated GeoNames archive out.
        with patch("localities.postal_picker._geonames", return_value=()):
            build_index(cls.db, ["LU", "NL"])

    def request(self, op, country, **fields):
        return process_request(dict(operation=op, country=country, **fields), index_path=self.db)["result"]

    def test_published_addresses_round_trip(self):
        for country, postcode, city, street, number in [
            ("LU", "9755", "Hupperdange", "Kaesfurterstrooss", "20"),
            ("NL", "9161BE", "Hollum", "Schoolstraat", "22"),
        ]:
            with self.subTest(country=country):
                path = []
                for kind, label in (("area", city), ("street", street), ("house_number", number)):
                    choices = self.request("suggest", country, postcode=postcode, query=label, path=path)
                    match = next(o for o in choices["options"] if (o["kind"], o["label"]) == (kind, label))
                    path.append(match["id"])
                components = dict(postcode=postcode, city=city, road=street, house_number=number)
                result = self.request("validate", country, components=components)
                self.assertEqual(result["matched_scope"], "published_address_point")
                self.assertEqual(set(result["verified_fields"]), components.keys())
                self.assertTrue(result["evidence"][0]["record_id"])
                self.assertFalse(result["deliverability_verified"])
                for update in (dict(city="Unlisted Town"), dict(house_number="999999")):
                    miss = self.request("validate", country, components=components | update)
                    self.assertNotIn("house_number", miss["verified_fields"])

    def test_suffix_and_unobserved_unit(self):
        c = dict(postcode="9166 PW", road="Reeweg", city="Schiermonnikoog", house_number="1-R33", unit="7")
        checked = self.request("validate", "NL", components=c)
        self.assertEqual(checked["matched_scope"], "published_address_point")
        self.assertIn("unit", checked["unverified_fields"])
        self.assertFalse(checked["deliverability_verified"])
        miss = self.request("validate", "NL", components=c | {"house_number": "1-R999999"})
        self.assertNotIn("house_number", miss["verified_fields"])

    def test_country_roles_and_legacy_v2_index(self):
        c = dict(postcode="L-9755", road="Kaesfurterstrooss", house_number="20", municipality="Clervaux")
        self.assertIn("municipality", self.request("validate", "LU", components=c)["verified_fields"])
        wrong = self.request("validate", "LU", components=c | {"municipality": "Hupperdange"})
        self.assertNotIn("road", wrong["verified_fields"])
        with tempfile.TemporaryDirectory() as folder:
            legacy = Path(folder) / "legacy.sqlite"
            with sqlite3.connect(self.db) as source, sqlite3.connect(legacy) as target:
                source.backup(target)
                target.execute("DROP TABLE official_points")
            result = process_request(dict(operation="validate", country="LU", components=c),
                                     index_path=legacy)["result"]
            self.assertEqual(result["verified_fields"], ["postcode"])
