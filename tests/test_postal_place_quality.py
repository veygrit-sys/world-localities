"""Postal place decisions must hold on at least one eligible source row."""

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from localities.postal_places import validate_postal_places


class PostalPlaceQuality(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "postal").mkdir()
        (self.root / "countries").mkdir()
        (self.root / "countries/catalog.json").write_text(json.dumps({
            "schema_version": 1, "countries": [{"code": c, "name": c} for c in ("CA", "FR", "GB", "NL", "US", "CN", "IN")],
        }))
        self.sources = []

    def add_source(self, rows, **kwargs):
        index = str(len(self.sources))
        path = self.root / "postal" / (index + ".zip")
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("places.txt", "".join("\t".join([*row, *([""] * (12 - len(row)))]) + "\n" for row in rows))
        data = path.read_bytes()
        self.sources.append({
            "id": index, "path": str(path.relative_to(self.root)), "format": "geonames_tsv_zip",
            "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "licence": "test fixture",
            "default_code_kind": "source_reported", **kwargs,
        })
        (self.root / "postal/sources.json").write_text(json.dumps({"schema_version": 1, "sources": self.sources}))

    def run_requests(self, *requests, limit=20):
        return validate_postal_places(list(requests), root=self.root, limit=limit)

    def test_evaluate_whole_source_even_if_only_one_candidate_is_shown(self):
        self.add_source([["FR", "75007", "Paris 07"], ["FR", "75007", "Paris"]])
        result, = self.run_requests({"country": "fr", "code": "75007", "locality": "PARIS"}, limit=1)
        self.assertEqual((result["status"], result["matching_rows"], result["postcode_rows"]), ("matched", 1, 2))
        self.assertTrue(result["truncated"])
        self.assertEqual(result["candidates"][0]["source_row"], "2")

    def test_fields_from_different_rows_never_combine_and_duplicates_keep_origins(self):
        self.add_source([["US", "00123", "Town A", "West", "01"], ["US", "00123", "Town B", "East", "02"],
                         ["US", "00123", "Town B", "East", "02"]])
        request = {"country": "US", "code": "00123", "locality": "Town A", "region_code": "02"}
        conflict, match = self.run_requests(request, dict(request, locality="Town B"))
        self.assertEqual(conflict["status"], "no_match_in_source")
        self.assertEqual((match["status"], match["matching_rows"], match["distinct_matching_localities"]), ("matched", 2, 1))

    def test_missing_fields_and_distinct_source_roles_are_never_resolved_by_row_order(self):
        self.add_source([["US", "00001", "Town A", "West"], ["US", "00001", "Town B", "West"],
                         ["US", "00002", "Town A"]])
        ambiguous, missing = self.run_requests({"country": "US", "code": "00001", "region": "West"},
                                               {"country": "US", "code": "00002", "locality": "Town A", "region": "West"})
        self.assertEqual((ambiguous["status"], missing["status"]), ("ambiguous", "insufficient_evidence"))
        self.assertFalse(ambiguous["deliverability_verified"])

    def test_restricted_source_or_absent_country_is_not_a_negative_address_result(self):
        self.add_source([["CA", "A1A", "Town A"], ["CN", "010000", "Town B"], ["US", "00123", "A"]],
                        country_code_kinds={"CA": "prefix", "CN": "aggregated"})
        self.add_source([["CA", "A1A 1A1", "Town A"]], expected_country="CA", active_for_lookup=False)
        requests = [{"country": c, "code": p, "locality": "Town A"} for c, p in
                    (("CA", "A1A"), ("CN", "010000"), ("IN", "123456"), ("US", "00000"))]
        results = self.run_requests(*requests)
        self.assertEqual([x["status"] for x in results], ["no_eligible_source"] * 3 + ["postcode_not_observed"])

    def test_compact_full_codes_preserve_raw_input_without_guessing_other_characters(self):
        for country, source, user in [("CA", "K1A 0B1", "k1a0b1"), ("GB", "SW7 2DD", "sw72dd"), ("NL", "1071 XX", "1071xx")]:
            self.add_source([[country, source, "Café"]], expected_country=country, default_code_kind="source_full")
            request = {"country": country, "code": user, "locality": "Cafe\u0301"}
            match, wrong, split = self.run_requests(request, dict(request, locality="Cafe"), dict(request, code=user[:1]+" "+user[1:]))
            self.assertEqual((match["input"], match["lookup_code"], match["status"]), (request, source, "matched"))
            self.assertEqual((wrong["status"], split["status"]), ("no_match_in_source", "postcode_not_observed"))
        result, = self.run_requests({"country": "CA", "code": "K1A 0B1", "locality": "Café"})
        self.assertEqual(result["status"], "postcode_not_observed")

    def test_invalid_inputs_and_corrupt_source(self):
        self.add_source([["US", "00001", "A"]])
        request = {"country": "US", "code": "00001", "locality": "A"}
        for overrides in ({"country": "Uſ"}, {"code": 1}, {"locality": "a\nb"}, {"extra": "x"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.run_requests(dict(request, **overrides))
        (self.root / "postal/0.zip").write_bytes(b"damaged")
        with self.assertRaisesRegex(ValueError, "size mismatch"):
            self.run_requests(request)
