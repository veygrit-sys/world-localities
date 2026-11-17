"""Postal-source replay and scope checks use synthetic, local input archives."""

import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from localities import postal


def geonames_row(country, code, place):
    return [country, code, place, "State", "01", "County", "002",
            "Community", "0003", "40.1", "-75.2", "1"]


def csv_bytes(rows, delimiter=","):
    output = io.StringIO(newline="")
    csv.writer(output, delimiter=delimiter, lineterminator="\n").writerows(rows)
    return output.getvalue().encode("utf-8")


def zip_bytes(member, content):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, content)
    return output.getvalue()


class WorldPostcodeSources(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "countries").mkdir()
        (self.root / "postal/sources").mkdir(parents=True)
        self.scope = {
            "schema_version": 1,
            "countries": [
                {"code": "US", "name": "United States"},
                {"code": "CA", "name": "Canada"},
                {"code": "JP", "name": "Japan"},
                {"code": "TW", "name": "Taiwan"},
                {"code": "ZZ", "name": "Not collected"},
            ],
        }
        self.write_json("countries/catalog.json", self.scope)
        self.sources = []
        self.geo = self.add_source(
            "geonames-test", "geonames_tsv_zip", "sample.zip",
            zip_bytes("sample.txt", csv_bytes([
                geonames_row("US", "00301", "First place"),
                geonames_row("US", "00301", "Second place"),
                geonames_row("US", "12345", "Third place"),
                geonames_row("CA", "A0A", "Prefix place"),
            ], delimiter="\t")),
            member="sample.txt", country_code_kinds={"CA": "prefix"},
        )
        japan = [
            ["01101", "060  ", "0600000", "ホッカイドウ", "サッポロシ", "チョウ",
             "北海道", "札幌市中央区", "以下に掲載がない場合", "0", "0", "0", "0", "0", "0"],
            ["01102", "060  ", "0600000", "ホッカイドウ", "サッポロシ", "マチ",
             "北海道", "札幌市北区", "町", "0", "0", "0", "0", "0", "0"],
        ]
        self.jp = self.add_source(
            "japanpost-test", "japanpost_utf_zip", "japan.zip",
            zip_bytes("utf_ken_all.csv", csv_bytes(japan)),
            member="utf_ken_all.csv", default_code_kind="official_full",
        )
        self.tw = self.add_source(
            "taiwan-test", "taiwan_prefix_csv", "taiwan.csv",
            csv_bytes([
                ["country", "code", "entity_id", "code_kind"],
                ["TW", "300", "tw:test:1", "prefix"],
                ["TW", "300", "tw:test:2", "prefix"],
            ]),
            default_code_kind="prefix",
        )

    def write_json(self, path, data):
        self.root.joinpath(path).write_text(json.dumps(data), encoding="utf-8")

    def save_manifest(self):
        self.write_json("postal/sources.json", {
            "schema_version": 1,
            "snapshot_label": "20261118",
            "sources": self.sources,
        })

    def add_source(self, identifier, format_name, filename, content, **metadata):
        path = "postal/sources/" + filename
        self.root.joinpath(path).write_bytes(content)
        source = {
            "id": identifier, "format": format_name, "path": path,
            "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
            "licence": "Test fixture only", "default_code_kind": "source_reported",
            "country_code_kinds": {}, **metadata,
        }
        self.sources.append(source)
        self.save_manifest()
        return source

    def replace_source(self, source, content):
        self.root.joinpath(source["path"]).write_bytes(content)
        source.update(sha256=hashlib.sha256(content).hexdigest(), bytes=len(content))
        self.save_manifest()

    def test_source_strings_and_record_provenance_are_preserved(self):
        records = list(postal.iter_postal_records(self.geo, root=self.root))
        first = records[0]
        self.assertEqual(first["code"], "00301")
        self.assertEqual(first["admin_code1"], "01")
        self.assertEqual(first["source_id"], "geonames-test")
        self.assertEqual(first["source_row"], "1")
        self.assertEqual(first["latitude"], "40.1")
        self.assertTrue(all(isinstance(value, str) for value in first.values()))

    def test_japan_source_keeps_full_codes_original_text_and_rows(self):
        records = list(postal.iter_postal_records(self.jp, root=self.root))
        self.assertEqual([record["code"] for record in records], ["0600000", "0600000"])
        self.assertEqual(records[0]["code_kind"], "official_full")
        self.assertEqual(records[0]["place_name"], "以下に掲載がない場合")
        self.assertEqual(records[0]["admin_name1"], "北海道")
        self.assertEqual(records[1]["source_row"], "2")

    def test_tw_prefix_retains_independent_entity_associations(self):
        records = list(postal.iter_postal_records(self.tw, root=self.root))
        self.assertEqual([row["code_kind"] for row in records], ["prefix", "prefix"])
        self.assertEqual({row["entity_id"] for row in records}, {"tw:test:1", "tw:test:2"})

    def test_lookup_keeps_all_places_without_promoting_evidence(self):
        result = postal.lookup_postcode("US", "00301", root=self.root)
        self.assertEqual(result["total"], 2)
        self.assertEqual({row["place_name"] for row in result["rows"]}, {"First place", "Second place"})
        self.assertFalse(result["complete_postcode_verified"])
        self.assertFalse(result["deliverability_verified"])
        self.assertEqual(postal.lookup_postcode("US", "301", root=self.root)["total"], 0)

    def test_pagination_reports_complete_count_and_nonoverlapping_rows(self):
        first = postal.lookup_postcode("US", "00301", root=self.root, limit=1)
        second = postal.lookup_postcode("US", "00301", root=self.root, limit=1, offset=1)
        beyond = postal.lookup_postcode("US", "00301", root=self.root, limit=1, offset=2)
        self.assertEqual(first["total"], second["total"])
        self.assertTrue(first["has_more"])
        self.assertFalse(second["has_more"])
        self.assertNotEqual(first["rows"], second["rows"])
        self.assertEqual(beyond["rows"], [])

    def test_partial_codes_need_explicit_inclusion_and_never_expand(self):
        self.assertEqual(postal.lookup_postcode("CA", "A0A", root=self.root)["total"], 0)
        included = postal.lookup_postcode("CA", "A0A", root=self.root, include_partial=True)
        self.assertEqual(included["total"], 1)
        self.assertFalse(included["complete_postcode_verified"])
        self.assertEqual(postal.lookup_postcode("TW", "300001", root=self.root, include_partial=True)["total"], 0)

    def test_other_partial_kinds_are_not_returned_as_standard_codes(self):
        for kind in ("aggregated", "partial", "partial_or_legacy", "routing_or_unreviewed"):
            with self.subTest(kind=kind):
                self.geo["country_code_kinds"]["US"] = kind
                self.save_manifest()
                self.assertEqual(postal.lookup_postcode("US", "00301", root=self.root)["total"], 0)
                result = postal.lookup_postcode("US", "00301", root=self.root, include_partial=True)
                self.assertEqual(result["total"], 2)

    def test_catalog_keeps_uncollected_countries_without_inventing_absence(self):
        catalog = postal.build_postal_catalog(root=self.root)
        countries = {row["country_code"]: row for row in catalog["countries"]}
        self.assertEqual(set(countries), {"US", "CA", "JP", "TW", "ZZ"})
        self.assertEqual(countries["ZZ"]["collection_status"], "pending_source")
        self.assertEqual(countries["ZZ"]["postal_system_status"], "unreviewed")
        self.assertEqual(countries["ZZ"]["distinct_codes"], 0)
        self.assertFalse(any(row["national_completeness_verified"] for row in countries.values()))

    def test_catalog_counts_source_rows_separately_from_distinct_codes(self):
        catalog = postal.build_postal_catalog(root=self.root)
        countries = {row["country_code"]: row for row in catalog["countries"]}
        self.assertEqual(countries["US"]["source_rows"], 3)
        self.assertEqual(countries["US"]["distinct_codes"], 2)
        self.assertEqual(countries["JP"]["source_rows"], 2)
        self.assertEqual(countries["JP"]["distinct_codes"], 1)
        self.assertEqual(catalog["summary"]["source_rows"], 8)
        self.assertEqual(catalog["summary"]["country_code_pairs"], 5)

    def test_rebuild_is_deterministic_and_verification_detects_changed_catalog(self):
        expected = postal.build_postal_catalog(root=self.root)
        self.assertEqual(expected, postal.build_postal_catalog(root=self.root))
        self.write_json("postal/catalog.json", expected)
        self.assertEqual(postal.verify_postal_catalog(root=self.root)["status"], "passed")
        expected["countries"][0]["distinct_codes"] += 1
        self.write_json("postal/catalog.json", expected)
        with self.assertRaises(ValueError):
            postal.verify_postal_catalog(root=self.root)

    def test_tampered_source_bytes_and_incorrect_size_are_rejected(self):
        path = self.root.joinpath(self.geo["path"])
        original = path.read_bytes()
        path.write_bytes(original + b"tampered")
        with self.assertRaises(ValueError):
            list(postal.iter_postal_records(self.geo, root=self.root))
        path.write_bytes(original)
        self.geo["bytes"] += 1
        with self.assertRaises(ValueError):
            list(postal.iter_postal_records(self.geo, root=self.root))

    def test_geonames_column_width_is_strict(self):
        for width in (11, 13):
            with self.subTest(width=width):
                row = geonames_row("US", "00301", "Place")
                row = row[:width] if width < len(row) else row + ["extra"]
                self.replace_source(self.geo, zip_bytes("sample.txt", csv_bytes([row], delimiter="\t")))
                with self.assertRaises(ValueError):
                    list(postal.iter_postal_records(self.geo, root=self.root))

    def test_japan_column_width_is_strict(self):
        self.replace_source(self.jp, zip_bytes("utf_ken_all.csv", csv_bytes([["x"] * 14])))
        with self.assertRaises(ValueError):
            list(postal.iter_postal_records(self.jp, root=self.root))

    def test_malformed_source_country_and_blank_code_are_rejected(self):
        for country, code in (("us", "00301"), ("USA", "00301"), ("US", ""), ("US", " ")):
            with self.subTest(country=country, code=code):
                self.replace_source(self.geo, zip_bytes("sample.txt", csv_bytes([
                    geonames_row(country, code, "Place"),
                ], delimiter="\t")))
                with self.assertRaises(ValueError):
                    list(postal.iter_postal_records(self.geo, root=self.root))

    def test_source_country_outside_collection_scope_is_not_silently_added(self):
        self.replace_source(self.geo, zip_bytes("sample.txt", csv_bytes([
            geonames_row("DE", "01067", "Place"),
        ], delimiter="\t")))
        with self.assertRaises(ValueError):
            postal.build_postal_catalog(root=self.root)

    def test_source_path_cannot_escape_repository_root(self):
        for unsafe in ("../outside.zip", str(self.root / "postal/sources/sample.zip")):
            with self.subTest(path=unsafe):
                self.geo["path"] = unsafe
                self.save_manifest()
                with self.assertRaises(ValueError):
                    list(postal.iter_postal_records(self.geo, root=self.root))

    def test_missing_or_oversized_zip_member_is_rejected(self):
        self.geo["member"] = "missing.txt"
        with self.assertRaises((ValueError, KeyError)):
            list(postal.iter_postal_records(self.geo, root=self.root))
        self.geo["member"] = "sample.txt"
        with mock.patch.object(postal, "MAX_MEMBER_BYTES", 1):
            with self.assertRaises(ValueError):
                list(postal.iter_postal_records(self.geo, root=self.root))

    def test_unknown_or_unsupported_source_manifest_is_rejected(self):
        self.sources.append(dict(self.geo))
        self.save_manifest()
        with self.assertRaises(ValueError):
            postal.load_sources(root=self.root)
        self.sources.pop()
        self.geo["format"] = "arbitrary_python"
        self.save_manifest()
        with self.assertRaises(ValueError):
            postal.load_sources(root=self.root)

    def test_lookup_rejects_invalid_country_code_and_nonstring_postcode(self):
        for country, code in (("us", "00301"), ("USA", "00301"), ("DE", "01067"),
                              ("US", 301), ("US", None), ("US", ""), ("US", " ")):
            with self.subTest(country=country, code=code), self.assertRaises((ValueError, TypeError)):
                postal.lookup_postcode(country, code, root=self.root)

    def test_lookup_rejects_invalid_pagination_and_partial_flags(self):
        for kwargs in ({"limit": True}, {"limit": 0}, {"limit": 10001}, {"limit": 1.5},
                       {"offset": -1}, {"offset": True}, {"offset": 1.5},
                       {"include_partial": "yes"}):
            with self.subTest(kwargs=kwargs), self.assertRaises((ValueError, TypeError)):
                postal.lookup_postcode("US", "00301", root=self.root, **kwargs)


if __name__ == "__main__":
    unittest.main()
