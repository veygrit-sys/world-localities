"""Observed Uruguay door numbers, locality/department roles and source receipts."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from addressing.address_ai import process_request
from localities.postal_picker import build_index
from scripts.project_uy_addresses import project_row


class UruguayAddressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.index = Path(cls.temp.name) / "uy.sqlite"
        with patch("localities.postal_picker._geonames", return_value=()):
            build_index(cls.index, ["UY"])

    def api(self, operation, **args):
        return process_request(dict(operation=operation, country="UY", **args),
                               index_path=self.index)["result"]

    def test_suggest_and_validate_agree_on_published_row(self):
        address = dict(postcode="65000", city="FRAY BENTOS", road="ESPAÑA", house_number="111")
        path = []
        for kind, value in (("area", address["city"]), ("street", address["road"]),
                            ("house_number", address["house_number"])):
            result = self.api("suggest", postcode=address["postcode"], query=value, path=path)
            option = next(o for o in result["options"] if (o["kind"], o["label"]) == (kind, value))
            self.assertIn("uy-ide-direcciones", option["supporting_sources"])
            path.append(option["id"])
        matched = self.api("validate", components=address | {"state": "Rio Negro", "unit": "8"})
        self.assertEqual(matched["matched_scope"], "published_address_point")
        self.assertIn("state", matched["verified_fields"])
        self.assertIn("unit", matched["unverified_fields"])
        self.assertFalse(matched["deliverability_verified"])
        self.assertIn("RIO NEGRO:2", [r["record_id"] for r in matched["evidence"]])
        self.assertIn("IDE", matched["evidence"][0]["attribution"])

    def test_door_suffix_and_unobserved_combinations(self):
        address = dict(postcode="85000", city="TRINIDAD", road="BRASIL", house_number="602 BIS")
        valid = self.api("validate", components=address)
        self.assertIn("FLORES:8074", [r["record_id"] for r in valid["evidence"]])
        for change in ({"house_number": "602 BIS-99999"}, {"city": "FRAY BENTOS"}, {"state": "SALTO"}):
            with self.subTest(change=change):
                r = self.api("validate", components=address | change)
                self.assertNotIn("house_number", r["verified_fields"])

    def test_multiple_access_points_stay_ambiguous(self):
        address = dict(postcode="95500", city="MENDOZA", road="FLORIDA", house_number="150")
        result = self.api("validate", components=address)
        self.assertEqual(result["status"], "ambiguous")
        self.assertGreater(result["evidence_count"], 1)
        self.assertFalse(result["deliverability_verified"])

    def test_omitted_and_unspecified_fields_are_never_inferred(self):
        source = dict(departamento="FLORES", codigo_postal="85000", localidad="TRINIDAD",
                      nombre_via="BRASIL", num_puerta="602", letra_puerta="BIS", km="N/A")
        for update in ({"codigo_postal":"N/A"}, {"num_puerta":"0"}, {"letra_puerta":"S/N"},
                       {"km":"9"}, {"localidad":"N/A"}, {"nombre_via":"SIN NOMBRE"},
                       {"nombre_via":"UYCALDS_SN_003"}, {"nombre_via":"SERVIDUMBRE"}, {"num_puerta":"9999"}):
            with self.subTest(update=update):
                self.assertIsNone(project_row(source | update, "FLORES", 5)[1])
