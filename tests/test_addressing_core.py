"""Worldwide address profile, rendering and validation-contract tests."""

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import (
    LocationPrecision,
    ProfileRegistry,
    ValidationLevel,
    ValidationResult,
    canonicalize_components,
    render_address,
)


class AddressProfiles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ProfileRegistry()

    def test_complete_compiled_profile_inventory(self):
        self.assertEqual(
            self.registry.report(),
            {
                "status": "passed",
                "country_profiles": 251,
                "locale_profiles": 558,
                "inherited_profiles": 567,
                "extension_profiles": 782,
                "extension_new_profiles": 542,
                "extension_overrides": 240,
                "source_commit": "cbf23487c13ad437cadab0083ef79fe5f1d1823e",
                "source_sha256": "2ed532207d6cf8c8a1823f1e5531466c00e9d292b115c0ac837321989ba4b085",
            },
        )
        self.assertEqual(len(self.registry.country_codes), 251)

    def test_all_country_profiles_resolve_and_render(self):
        for country in self.registry.country_codes:
            with self.subTest(country=country):
                profile = self.registry.select(country)
                self.assertTrue(profile.template.strip())
                rendered = render_address(
                    {
                        "country": "Testland",
                        "country_code": country,
                        "state": "Test State",
                        "city": "Test City",
                        "road": "Test Road",
                        "house_number": "1",
                        "postcode": "12345",
                    },
                    country,
                    registry=self.registry,
                )
                self.assertEqual(rendered.country_code, country)
                self.assertTrue(rendered.lines)

    def test_domestic_and_international_profile_selection(self):
        self.assertEqual(self.registry.select("JP").key, "JP_ja")
        self.assertEqual(self.registry.select("JP", language="ja-JP").key, "JP_ja")
        self.assertEqual(self.registry.select("JP", international=True).key, "JP_en")
        self.assertEqual(self.registry.select("TW").key, "TW_zh")

    def test_unknown_country_is_rejected(self):
        with self.assertRaises(KeyError):
            self.registry.select("ZZZ")


class AddressComponentsAndRendering(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ProfileRegistry()

    def test_aliases_unicode_and_input_order_are_canonical(self):
        original = {
            "street_number": " 301 ",
            "street": "Hamilton  Avenue",
            "city": "Palo Alto",
            "province": "California",
            "postal_code": "94303",
            "country": "United States of America",
            "iso_country_code": "us",
        }
        reversed_input = dict(reversed(list(original.items())))
        first = canonicalize_components(original)
        second = canonicalize_components(reversed_input)
        self.assertEqual(first, second)
        self.assertEqual(first.values["country_code"], "US")
        self.assertEqual(first.values["road"], "Hamilton Avenue")

    def test_conflicting_alias_values_are_rejected(self):
        with self.assertRaises(ValueError):
            canonicalize_components({"street": "First", "road": "Second"})

    def test_japan_domestic_and_international_order(self):
        components = {
            "country": "日本",
            "postcode": "1000005",
            "state": "東京都",
            "city": "千代田区",
            "neighbourhood": "丸の内",
            "house_number": "1-1",
        }
        domestic = render_address(components, "JP", registry=self.registry)
        self.assertEqual(domestic.profile_key, "JP_ja")
        self.assertEqual(
            domestic.lines,
            ("日本", "100-0005", "東京都", "千代田区", "丸の内", "1-1"),
        )
        international = render_address(
            dict(components, country="Japan"),
            "JP",
            international=True,
            registry=self.registry,
        )
        self.assertEqual(international.profile_key, "JP_en")
        self.assertEqual(international.lines[-1], "Japan")
        self.assertTrue(international.lines[0].startswith("1-1"))

    def test_us_state_name_is_rendered_as_postal_code(self):
        rendered = render_address(
            {
                "country": "United States of America",
                "postcode": "94303",
                "state": "California",
                "city": "Palo Alto",
                "road": "Hamilton Avenue",
                "house_number": "301",
            },
            "US",
            registry=self.registry,
        )
        self.assertEqual(
            rendered.lines,
            (
                "301 Hamilton Avenue",
                "Palo Alto, CA 94303",
                "United States of America",
            ),
        )

    def test_dependent_territory_keeps_identity_in_reviewed_regional_profile(self):
        rendered = render_address(
            {
                "country": "Puerto Rico",
                "postcode": "00901",
                "city": "San Juan Antiguo",
                "road": "Calle San Francisco",
                "house_number": "252",
            },
            "PR",
            registry=self.registry,
        )
        self.assertEqual(rendered.country_code, "PR")
        self.assertEqual(rendered.profile_key, "PR_es")
        self.assertIn("San Juan Antiguo PR 00901", rendered.lines)
        self.assertEqual(rendered.lines[-1], "Puerto Rico")

    def test_address2_is_not_silently_dropped(self):
        rendered = render_address(
            {
                "country": "日本",
                "postcode": "1000005",
                "state": "東京都",
                "city": "千代田区",
                "house": "新丸ビル",
                "address2": "10階 1001号室",
            },
            "JP",
            language="ja",
            registry=self.registry,
        )
        self.assertIn("10階 1001号室", rendered.lines)
        self.assertNotIn("generic_subpremise_placement", rendered.warnings)
        self.assertFalse(rendered.unrendered_components)

    def test_opaque_address1_and_unknown_fields_are_reported(self):
        rendered = render_address(
            {
                "country": "France",
                "country_code": "FR",
                "address1": "17 Rue Exemple",
                "delivery_note": "rear gate",
            },
            "FR",
            registry=self.registry,
        )
        self.assertIn("17 Rue Exemple", rendered.text)
        self.assertEqual(rendered.extras, {"delivery_note": "rear gate"})
        self.assertIn("opaque_address_line1_rendered_in_delivery_line", rendered.warnings)
        self.assertIn("unrendered_extra_components", rendered.warnings)


class ValidationContract(unittest.TestCase):
    def test_delivery_claim_requires_external_evidence(self):
        with self.assertRaises(ValueError):
            ValidationResult(
                status="verified",
                level=ValidationLevel.DELIVERABILITY,
                confidence=1.0,
                components={"country_code": "JP"},
            )
        result = ValidationResult(
            status="verified",
            level=ValidationLevel.DELIVERABILITY,
            confidence=0.99,
            components={"country_code": "JP"},
            evidence=(
                {"evidence_type": "postal_operator", "source_id": "example"},
            ),
            location_precision=LocationPrecision.ENTRANCE,
        )
        payload = result.to_dict()
        self.assertEqual(payload["verification_level_number"], 7)
        self.assertEqual(payload["location_precision"], "entrance")
        json.dumps(payload)


if __name__ == "__main__":
    unittest.main()
