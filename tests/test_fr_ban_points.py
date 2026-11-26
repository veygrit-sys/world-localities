"""Complete postal/street/number matches from French BAN snapshots."""

from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from addressing.address_ai import process_request
from localities.postal_picker import build_index


class FrenchAddressPoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        cls.index = Path(folder.name) / "fr.sqlite"
        with patch("localities.postal_picker._geonames", return_value=()):
            build_index(cls.index, ["FR"])

    def run_op(self, op, cc="FR", **params):
        return process_request(dict(operation=op, country=cc, **params), index_path=self.index)["result"]

    def test_picker_and_validation_share_published_id(self):
        for code, city, road, number, record_id in [
            ("48310", "Albaret-le-Comtal", "place de l'église", "2 bis", "a526bbd3-8f1d-489c-a359-bc12769ccb77"),
            ("90150", "Angeot", "Rue de la Combe", "4", "90002_0006_00004"),
        ]:
            with self.subTest(code=code):
                path = []
                for kind, label in (("area", city), ("street", road), ("house_number", number)):
                    response = self.run_op("suggest", postcode=code, path=path, query=label)
                    chosen = next(x for x in response["options"] if x["kind"] == kind and x["label"] == label)
                    self.assertIn("fr-ban-48-90", chosen["supporting_sources"])
                    path.append(chosen["id"])
                values = dict(postcode=code, city=city, road=road, house_number=number)
                ok = self.run_op("validate", components=values)
                raw = self.run_op("validate", components=dict(postcode=code, city=city, line1=number + " " + road))
                self.assertEqual(raw["address1_decision"]["status"], "verified")
                self.assertEqual(raw["evidence"][0]["record_id"], record_id)
                self.assertEqual(ok["matched_scope"], "published_address_point")
                self.assertEqual(set(ok["verified_fields"]), values.keys())
                self.assertEqual(ok["evidence"][0]["record_id"], record_id)
                self.assertEqual(ok["evidence"][0]["source_updated_on"], "2026-11-18")
                self.assertFalse(ok["deliverability_verified"])
                for change in (dict(city="Paris"), dict(house_number="9999999")):
                    bad = self.run_op("validate", components=values | change)
                    self.assertNotIn("house_number", bad["verified_fields"])

    def test_routing_confirmed_on_the_same_commune(self):
        vals = dict(postcode="90150", city="Angeot", road="Rue de la Combe", house_number="4")
        for extra in (dict(town="Angeot"), dict(postal_city="ANGEOT"),
                      dict(town="Angeot", postal_city="ANGEOT", address_line1="4 rue de la Combe")):
            result = self.run_op("validate", components=vals | extra)
            self.assertEqual(result["status"], "matched")
            self.assertEqual(result["matched_scope"], "published_address_point")
            self.assertEqual(set(result["verified_fields"]), set(vals | extra))
            self.assertEqual([r["source_id"] for r in result["evidence"]], ["fr-ban-48-90", "fr-laposte-hexasmal"])
            self.assertEqual(result["evidence"][0]["insee_code"], "90002")
            decision = result["address1_decision"]
            self.assertEqual((decision["status"], decision["level"], decision["candidate_count"]),
                             ("verified", "premise", 1))
        for extra in (dict(postal_city="FONTAINE"), dict(town="Fontaine"),
                      dict(address_line1="6 Rue de la Combe"), dict(address_line1="4 Rue de Belfort")):
            result = self.run_op("validate", components=vals | extra)
            self.assertNotIn("house_number", result["verified_fields"])

    def test_line_five_is_not_bound_to_a_specific_address(self):
        vals = dict(postcode="48000", city="Monts-de-Randon", road="Baraque de La Grange", house_number="10")
        for extra in (dict(neighbourhood="SERVIERES"), dict(town="SERVIERES")):
            result = self.run_op("validate", components=vals | extra)
            self.assertNotIn("house_number", result["verified_fields"])

    def test_older_index_without_commune_identifiers(self):
        with tempfile.TemporaryDirectory() as folder:
            legacy = Path(folder) / "legacy.sqlite"
            with sqlite3.connect(self.index) as original, sqlite3.connect(legacy) as db:
                original.backup(db)
                db.execute("DROP TABLE point_communes")
            vals = dict(postcode="90150", city="Angeot", road="Rue de la Combe",
                        house_number="4", postal_city="ANGEOT")
            result = process_request(dict(operation="validate", country="FR", components=vals),
                                     index_path=legacy)["result"]
            self.assertEqual(result["matched_scope"], "postal_locality")
            self.assertNotIn("house_number", result["verified_fields"])

    def test_routing_and_outside_coverage_still_use_postal_evidence(self):
        vals = dict(postcode="90150", city="Angeot", road="Rue de la Combe", house_number="4")
        wrong = self.run_op("validate", components=vals | {"postal_city": "LYON"})
        self.assertTrue(wrong["blocking_conflict"])
        self.assertNotIn("house_number", wrong["verified_fields"])
        for cc, code in [("FR", "75007"), ("MC", "98000"), ("RE", "97400")]:
            result = self.run_op("validate", cc=cc, components=dict(postcode=code, road="Rue de la Combe", house_number="4"))
            self.assertIn("postcode", result["verified_fields"])
            self.assertNotIn("road", result["verified_fields"])
        # The older French validator also works for consumers who have no picker index.
        before = process_request(dict(operation="validate", country="FR", components=vals))["result"]
        self.assertNotIn("house_number", before["verified_fields"])
