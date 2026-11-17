"""Complete-length source values stay distinct from prefixes and verified claims."""

import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from localities import postal


def _postal_row(country, code, place="Example place"):
    return [country, code, place, "State", "01", "County", "002",
            "Community", "0003", "40.1", "-75.2", "1"]


def _postal_zip(rows, delimiter="\t", encoding="utf-8", member="postal.txt"):
    text = io.StringIO(newline="")
    csv.writer(text, delimiter=delimiter, lineterminator="\n").writerows(rows)
    binary = io.BytesIO()
    with zipfile.ZipFile(binary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, text.getvalue().encode(encoding))
    return binary.getvalue()


class CompleteLengthPostalSources(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "countries").mkdir()
        (self.root / "postal/sources").mkdir(parents=True)
        self.sources = []
        self.write_json("countries/catalog.json", {
            "schema_version": 1,
            "countries": [{"code": code, "name": code}
                          for code in ("CA", "GB", "NL", "US", "JP")],
        })
        self.save_manifest()

    def write_json(self, path, value):
        (self.root / path).write_text(json.dumps(value), encoding="utf-8")

    def save_manifest(self):
        self.write_json("postal/sources.json", {
            "schema_version": 1, "snapshot_label": "test-only", "sources": self.sources,
        })

    def source(self, rows, **metadata):
        number = len(self.sources) + 1
        content = _postal_zip(rows)
        path = f"postal/sources/source-{number}.zip"
        (self.root / path).write_bytes(content)
        source = {
            "id": f"source-{number}", "format": "geonames_tsv_zip", "path": path,
            "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
            "licence": "Synthetic test fixture", "member": "postal.txt",
            "default_code_kind": "source_full",
            "country_code_kinds": {}, **metadata,
        }
        if source["default_code_kind"] == "source_full":
            source.setdefault("expected_country", "CA")
        self.sources.append(source)
        self.save_manifest()
        return source

    def records(self, source):
        return list(postal.iter_postal_records(source, root=self.root))

    def japan_source(self, rows, business=True):
        number = len(self.sources) + 1
        member = "JIGYOSYO.CSV" if business else "utf_ken_all.csv"
        content = _postal_zip(rows, delimiter=",", encoding="cp932" if business else "utf-8", member=member)
        path = f"postal/sources/japan-{number}.zip"
        (self.root / path).write_bytes(content)
        source = {
            "id": f"japan-{number}",
            "format": "japanpost_business_zip" if business else "japanpost_utf_zip",
            "path": path, "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content),
            "licence": "Synthetic test fixture", "member": member,
            "default_code_kind": "official_full", "expected_country": "JP",
            "country_code_kinds": {},
        }
        self.sources.append(source)
        self.save_manifest()
        return source

    @staticmethod
    def business_row(code="0600001", usage="0"):
        return ["01101", "カブシキガイシャシケン", "株式会社 試験", "北海道",
                "札幌市中央区", "架空町", "１番地", code, "060", "札幌中央", usage, "0", "0"]

    def test_supported_full_country_shapes_are_read_without_relabelling(self):
        for country, code in (("CA", "T0A 0A0"), ("GB", "GIR 0AA"), ("NL", "1234 AB")):
            with self.subTest(country=country):
                source = self.source([_postal_row(country, code)], expected_country=country)
                record = self.records(source)[0]
                self.assertEqual(record["country_code"], country)
                self.assertEqual(record["code"], code)
                self.assertEqual(record["code_kind"], "source_full")

    def test_source_full_is_in_standard_lookup_without_verification_promotion(self):
        self.source([_postal_row("CA", "T0A 0A0")])
        found = postal.lookup_postcode("CA", "T0A 0A0", root=self.root)
        self.assertEqual(found["total"], 1)
        self.assertFalse(found["complete_postcode_verified"])
        self.assertFalse(found["deliverability_verified"])
        country = postal.build_postal_catalog(self.root)["countries"][0]
        self.assertFalse(country["national_completeness_verified"])
        self.assertEqual(country["postal_system_status"], "unreviewed")

    def test_leading_zeros_and_original_spacing_remain_literal(self):
        source = self.source([_postal_row("CA", "T0A 0A0")])
        record = self.records(source)[0]
        self.assertEqual(record["code"], "T0A 0A0")
        self.assertEqual(record["admin_code1"], "01")
        self.assertEqual(record["admin_code2"], "002")
        self.assertEqual(postal.lookup_postcode("CA", "T0A0A0", root=self.root)["total"], 0)
        self.assertEqual(postal.lookup_postcode("CA", "t0a 0a0", root=self.root)["total"], 0)

    def test_missing_expected_country_cannot_claim_complete_length(self):
        source = self.source([_postal_row("CA", "T0A 0A0")])
        del source["expected_country"]
        self.save_manifest()
        with self.assertRaises(ValueError):
            postal.load_sources(self.root)

    def test_unsupported_expected_country_is_not_assigned_a_full_shape(self):
        for country in ("US", "ca", "ZZ", "", None):
            with self.subTest(country=country):
                source = self.source([_postal_row("CA", "T0A 0A0")], expected_country=country)
                with self.assertRaises(ValueError):
                    self.records(source)
                self.sources.pop()

    def test_non_geonames_format_cannot_claim_source_full(self):
        source = self.source([_postal_row("CA", "T0A 0A0")], format="japanpost_utf_zip")
        with self.assertRaises(ValueError):
            postal.load_sources(self.root)

    def test_source_full_does_not_accept_country_kind_overrides(self):
        source = self.source([_postal_row("CA", "T0A 0A0")],
                             country_code_kinds={"CA": "source_reported"})
        with self.assertRaises(ValueError):
            postal.load_sources(self.root)

    def test_country_override_cannot_promote_an_ordinary_source(self):
        for kind in ("source_reported", "prefix"):
            with self.subTest(kind=kind):
                source = self.source([_postal_row("CA", "T0A")],
                                     default_code_kind=kind,
                                     country_code_kinds={"CA": "source_full"})
                with self.assertRaises(ValueError):
                    self.records(source)
                self.sources.pop()

    def test_country_in_each_row_must_match_the_expected_full_country(self):
        source = self.source([_postal_row("GB", "GIR 0AA")], expected_country="CA")
        with self.assertRaises(ValueError):
            self.records(source)

    def test_prefixes_cannot_pass_as_complete_length_codes(self):
        for country, code in (("CA", "T0A"), ("GB", "AB1"), ("NL", "1234")):
            with self.subTest(country=country):
                source = self.source([_postal_row(country, code)], expected_country=country)
                with self.assertRaises(ValueError):
                    self.records(source)
                self.sources.pop()

    def test_wrong_case_or_spacing_is_not_repaired_to_fit_full_shape(self):
        for code in ("t0a 0a0", "T0A0A0", " T0A 0A0 ", "T0A  0A0"):
            with self.subTest(code=code):
                source = self.source([_postal_row("CA", code)])
                with self.assertRaises(ValueError):
                    self.records(source)
                self.sources.pop()

    def test_adding_full_source_does_not_replace_or_expand_prefix_observations(self):
        self.source([_postal_row("CA", "T0A")], default_code_kind="prefix")
        self.source([_postal_row("CA", "T0A 0A0")])
        catalog = postal.build_postal_catalog(self.root)
        country = catalog["countries"][0]
        self.assertEqual(country["code_kinds"], {"prefix": 1, "source_full": 1})
        self.assertEqual(country["distinct_codes_by_kind"], {"prefix": 1, "source_full": 1})
        self.assertEqual(postal.lookup_postcode("CA", "T0A", root=self.root)["total"], 0)
        self.assertEqual(postal.lookup_postcode("CA", "T0A", root=self.root,
                                             include_partial=True)["total"], 1)

    def test_many_to_many_source_rows_and_unique_code_counts_are_separate(self):
        source = self.source([
            _postal_row("CA", "T0A 0A0", "First"),
            _postal_row("CA", "T0A 0A0", "Second"),
            _postal_row("CA", "T0A 0A1", "Third"),
        ])
        catalog = postal.build_postal_catalog(self.root)
        country = catalog["countries"][0]
        self.assertEqual(country["source_rows"], 3)
        self.assertEqual(country["distinct_codes"], 2)
        self.assertEqual(country["distinct_codes_by_kind"], {"source_full": 2})
        report = next(item for item in catalog["sources"] if item["id"] == source["id"])
        self.assertEqual(report["source_rows"], 3)
        self.assertEqual(report["distinct_codes"], 2)
        self.assertEqual(report["distinct_codes_by_kind"], {"source_full": 2})
        self.assertEqual(postal.lookup_postcode("CA", "T0A 0A0", root=self.root)["total"], 2)

    def test_source_uniqueness_includes_country_and_does_not_merge_same_literal(self):
        self.source([_postal_row("CA", "0000"), _postal_row("US", "0000"),
                     _postal_row("US", "0000", "Second")],
                    default_code_kind="source_reported")
        report = postal.build_postal_catalog(self.root)["sources"][0]
        self.assertEqual(report["source_rows"], 3)
        self.assertEqual(report["distinct_codes"], 2)
        self.assertEqual(report["distinct_codes_by_kind"], {"source_reported": 2})

    def test_distinct_counts_are_deterministic_across_rebuild_and_saved_verification(self):
        self.source([_postal_row("CA", "T0A 0A1"), _postal_row("CA", "T0A 0A0")])
        first = postal.build_postal_catalog(self.root)
        self.assertEqual(first, postal.build_postal_catalog(self.root))
        self.write_json("postal/catalog.json", first)
        self.assertEqual(postal.verify_postal_catalog(self.root)["status"], "passed")

    def test_business_archive_preserves_cp932_fields_source_columns_and_postal_use(self):
        rows = [self.business_row(), self.business_row(code="0600002", usage="1")]
        records = self.records(self.japan_source(rows))
        self.assertEqual([row["postal_use"] for row in records], ["business", "po_box"])
        self.assertEqual(records[0]["organization"], "株式会社 試験")
        self.assertEqual(records[0]["postal_office"], "札幌中央")
        self.assertEqual(records[0]["place_name"], "架空町")
        self.assertEqual(records[0]["admin_code2"], "01101")
        self.assertEqual(records[0]["code"], "0600001")
        for record, original in zip(records, rows):
            self.assertEqual([record[f"source_col_{i}"] for i in range(1, 14)], original)

    def test_business_archive_rejects_unknown_use_or_nonseven_digit_code(self):
        for row in (self.business_row(usage="2"), self.business_row(code="600001"),
                    self.business_row(code="060-0001")):
            with self.subTest(row=row):
                source = self.japan_source([row])
                with self.assertRaises(ValueError):
                    self.records(source)
                self.sources.pop()

    def test_business_archive_requires_thirteen_columns(self):
        source = self.japan_source([self.business_row()[:-1]])
        with self.assertRaises(ValueError):
            self.records(source)

    def test_existing_japan_utf_format_still_preserves_all_fifteen_columns(self):
        row = ["01101", "060  ", "0600000", "ホッカイドウ", "サッポロシ", "チョウ",
               "北海道", "札幌市中央区", "町", "0", "0", "0", "0", "0", "0"]
        record = self.records(self.japan_source([row], business=False))[0]
        self.assertEqual(record["code"], "0600000")
        self.assertEqual([record[f"source_col_{i}"] for i in range(1, 16)], row)

    def test_inactive_sources_require_explicit_historical_lookup(self):
        old = self.source([_postal_row("CA", "T0A 0A0", "Old")], active_for_lookup=False)
        current = self.source([_postal_row("CA", "T0A 0A0", "Current")])
        self.source([_postal_row("CA", "T0A", "Prefix 1"),
                     _postal_row("CA", "T0A", "Prefix 2")], default_code_kind="prefix")
        found = postal.lookup_postcode("CA", "T0A 0A0", root=self.root)
        self.assertEqual(found["total"], 1)
        self.assertEqual(found["rows"][0]["source_id"], current["id"])
        self.assertFalse(found["include_historical"])
        historical = postal.lookup_postcode("CA", "T0A 0A0", root=self.root, include_historical=True)
        self.assertEqual(historical["total"], 2)
        self.assertTrue(historical["include_historical"])
        catalog = postal.build_postal_catalog(self.root)
        self.assertEqual(catalog["countries"][0]["source_rows"], 4)
        self.assertEqual(catalog["countries"][0]["lookup_source_rows"], 3)
        self.assertEqual(catalog["summary"]["lookup_source_rows"], 3)
        old_report = next(row for row in catalog["sources"] if row["id"] == old["id"])
        self.assertIs(old_report["active_for_lookup"], False)

    def test_historical_and_source_activity_flags_require_booleans(self):
        source = self.source([_postal_row("CA", "T0A 0A0")])
        for invalid in ("false", 0, 1, None):
            with self.subTest(flag=invalid):
                source["active_for_lookup"] = invalid
                self.save_manifest()
                with self.assertRaises(ValueError):
                    postal.load_sources(self.root)
                source.pop("active_for_lookup")
                self.save_manifest()
                with self.assertRaises(ValueError):
                    postal.lookup_postcode("CA", "T0A 0A0", root=self.root, include_historical=invalid)


if __name__ == "__main__":
    unittest.main()
