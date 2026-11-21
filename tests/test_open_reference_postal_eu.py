import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from localities.open_reference.postal_eu import COUNTRIES, DIRECTORY, SOURCE, _index, lookup, validate_place, verified_bytes


class LaPosteReferenceTests(unittest.TestCase):
    def test_complete_scoped_publisher_rows_and_unique_ids(self):
        total = 0
        all_ids = set()
        for iso in COUNTRIES:
            counts = SOURCE["country_counts"][iso]
            postal_keys = [key for country, key in _index(DIRECTORY)
                           if country == iso and len(key) == 5 and key.isascii() and key.isdigit()]
            rows = [row for key in postal_keys for row in lookup(key, country=iso)]
            self.assertEqual(len(postal_keys), counts["postcodes"])
            self.assertEqual(len(rows), counts["rows"])
            self.assertEqual(len({row["insee_code"] for row in rows}), counts["insee_codes"])
            self.assertEqual(len({row["source_row"] for row in rows}), len(rows))
            total += len(rows)
            all_ids.update(row["record_id"] for row in rows)
        self.assertEqual(len(all_ids), total)
        self.assertEqual(total, 39191)
        self.assertEqual(total + len(SOURCE["excluded_rows"]), SOURCE["source_row_count"])

    def test_routing_label_matches_same_row_but_not_other_commune(self):
        row, = lookup("75007")
        self.assertEqual((row["locality"], row["routing_name"], row["source_row"]), ("PARIS 07", "PARIS", 32615))
        self.assertIn(row, lookup("  Paris  "))
        self.assertIn(row, lookup("Paris 07"))
        self.assertNotIn(row, lookup("Ajaccio"))
        self.assertFalse(lookup("Paris 7e"))

    def test_corsica_retains_leading_code_and_line_five(self):
        ajaccio = lookup("insee:2a004")
        self.assertEqual({row["postcode"] for row in ajaccio}, {"20000", "20090", "20167"})
        row, = lookup("mezzavia")
        self.assertIn(row, ajaccio)
        self.assertEqual(row["postcode"], "20167")

    def test_numeric_namespaces_and_multiplicity(self):
        self.assertEqual({row["locality"] for row in lookup("13001")}, {"MARSEILLE 01"})
        self.assertEqual({row["locality"] for row in lookup("insee:13001")}, {"AIX EN PROVENCE"})
        self.assertEqual(lookup("insee:01001")[0]["postcode"], "01400")
        self.assertGreater(len(lookup("01400")), 1)
        self.assertFalse(lookup("1400"))

    def test_scope_and_independent_return_values(self):
        self.assertFalse(lookup("98000"))
        self.assertFalse(lookup("97100"))
        self.assertFalse(lookup(""))
        lookup("75007")[0]["locality"] = "changed"
        self.assertEqual(lookup("75007")[0]["locality"], "PARIS 07")
        with self.assertRaises(ValueError):
            verified_bytes(b"changed")


    def test_overseas_are_separate_even_when_postal_prefix_is_shared(self):
        for country, postcode, name in [
            ("BL", "97133", "ST BARTHELEMY"), ("MF", "97150", "ST MARTIN"),
            ("GP", "97139", "LES ABYMES"), ("MC", "98000", "MONACO"),
            ("GF", "97353", "KAW"), ("YT", "97680", "COMBANI"), ("WF", "98600", "UVEA"),
            ("PF", "98760", "TUUHORA"), ("NC", "98883", "OUACO"),
        ]:
            with self.subTest(country=country):
                r = validate_place(country, postcode, name)
                self.assertEqual(r["status"], "matched")
                self.assertEqual(r["matching_rows"], 1)
                self.assertEqual(r["candidates"][0]["country"], country)
                self.assertFalse(lookup(postcode, country="FR"))
        self.assertFalse(lookup("97133", country="GP"))
        self.assertFalse(lookup("97150", country="GP"))
        self.assertFalse(lookup("98799", country="PF"))
        self.assertFalse(lookup("insee:98901", country="FR"))

    def test_typed_same_row_states_and_limit(self):
        self.assertEqual(validate_place("FR", "75007", "Paris")["status"], "matched")
        self.assertEqual(validate_place("FR", "75007", "Ajaccio")["status"], "no_match_in_source")
        self.assertEqual(validate_place("FR", "00000", "Paris")["status"], "postcode_not_observed")
        self.assertEqual(validate_place("DE", "75007", "Paris")["status"], "no_eligible_source")
        result = validate_place("PM", "97500", "ST PIERRE ET MIQUELON", limit=1)
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["matching_rows"], 3)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertTrue(result["truncated"])
        for bad in ("", "75007", "insee:75107", "2A004", "Paris\n"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_place("FR", "75007", bad)
        with self.assertRaises(ValueError):
            validate_place("FR", "７５００７", "Paris")
        with self.assertRaises(ValueError):
            validate_place("FR", "75007", "Paris", limit=0)


    def test_explicit_directory_verifies_bundled_inputs(self):
        with TemporaryDirectory() as temp:
            directory = Path(temp)
            snapshot = SOURCE["stored_file"]
            crosswalk = SOURCE["territory_reference"]["projection_file"]
            shutil.copy(DIRECTORY / snapshot, directory)
            (directory / crosswalk).write_text("changed")
            with self.assertRaisesRegex(ValueError, "crosswalk"):
                validate_place("MF", "97150", "ST MARTIN", directory=directory)
            shutil.copy(DIRECTORY / crosswalk, directory)
            self.assertEqual(validate_place("MF", "97150", "ST MARTIN", directory=directory)["status"], "matched")
