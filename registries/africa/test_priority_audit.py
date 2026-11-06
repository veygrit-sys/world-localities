"""Offline regression checks for Africa priority waves and safe crosswalks."""
import unittest

from priority_audit import audit
from reconcile_official import build_candidates, normalize_name


def official(oid, name, level, parent=""):
    return dict(official_id=oid, name=name, admin_level=str(level),
                parent_official_id=parent)


def admin(gid, name, level, parent=""):
    return dict(id="gn:" + str(gid), kind="admin_subdivision", name=name,
                asciiname=name, admin_level=str(level), parent_id=parent)


class PriorityAuditTests(unittest.TestCase):
    def test_source_integrity_and_wave_order(self):
        report = audit()
        self.assertEqual(report["integrity_errors"], [])
        self.assertEqual([[c["country"] for c in w["countries"]] for w in report["waves"]],
                         [["ZA", "NG", "KE", "GH"], ["RW", "EG", "MA", "DZ"]])

    def test_existing_and_missing_country_are_distinct(self):
        report = audit()
        by_code = {c["country"]: c for w in report["waves"] for c in w["countries"]}
        for code in ("ZA", "KE", "GH", "RW", "EG", "DZ"):
            self.assertEqual(by_code[code]["status"], "source_snapshot_present")
        for code in ("NG", "MA"):
            self.assertIn(by_code[code]["status"],
                          ("source_snapshot_present", "not_migrated_from_pinned_source"))
            if by_code[code]["status"] == "not_migrated_from_pinned_source":
                self.assertTrue(by_code[code]["source_blob_sha"])
        self.assertTrue(all(not c["official_hierarchy_verified"]
                            and not c["postal_address_validated"]
                            and not c["deliverability_validated"]
                            for w in report["waves"] for c in w["countries"]))


class CandidateCrosswalkTests(unittest.TestCase):
    def setUp(self):
        self.registry = [
            admin(1, "Nairobi", 1),
            admin(2, "Westlands", 2, "gn:1"),
            admin(3, "Westlands", 2, "gn:other"),
        ]
        self.official = [official("CNT-1", "Nairobi", 1),
                         official("SUB-1", "Westlands", 2, "CNT-1")]

    def test_without_approved_parent_remains_ambiguous(self):
        result = build_candidates(self.official, self.registry)
        self.assertEqual(result[0]["status"], "unique_country_scoped_candidate")
        self.assertEqual(result[1]["status"], "ambiguous_candidates")
        self.assertFalse(result[0]["approved"])
        self.assertFalse(result[1]["approved"])

    def test_verified_parent_can_disambiguate_but_never_approves(self):
        result = build_candidates(self.official, self.registry, {"CNT-1": "gn:1"})
        self.assertEqual(result[1]["status"], "unique_parent_scoped_candidate")
        self.assertEqual(result[1]["candidate_geonames_ids"], ["gn:2"])
        self.assertFalse(result[1]["approved"])

    def test_name_normalization_preserves_distinct_accents(self):
        self.assertNotEqual(normalize_name("Sao"), normalize_name("São"))
        self.assertEqual(normalize_name("  Cape   Town "), "cape town")

    def test_duplicate_official_ids_fail_closed(self):
        with self.assertRaises(ValueError):
            build_candidates([self.official[0], self.official[0]], self.registry)

    def test_no_geoadmin_match_is_not_fabricated(self):
        result = build_candidates([official("X", "Fictional County", 1)], self.registry)
        self.assertEqual(result[0]["status"], "no_exact_name_candidate")
        self.assertEqual(result[0]["candidate_geonames_ids"], [])


if __name__ == "__main__":
    unittest.main()
