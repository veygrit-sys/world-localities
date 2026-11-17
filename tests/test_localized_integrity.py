"""Prevent language selection from changing identifiers or losing source input."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import render_bilingual_address
from addressing.localized import (
    BilingualAddressResult,
    LocalizedAddress,
    canonicalize_localized_components,
    select_localized_components,
)


class LanguageNeutralIntegrity(unittest.TestCase):
    def test_identifiers_cannot_vary_by_language(self):
        for key in ("country_code", "postcode", "sorting_code", "state_code",
                    "house_number", "lot"):
            with self.subTest(component=key):
                with self.assertRaisesRegex(ValueError, f"{key} cannot vary"):
                    canonicalize_localized_components({key: {"ja": "11", "en": "12"}})

    def test_aliases_cannot_hide_identifier_conflicts(self):
        with self.assertRaisesRegex(ValueError, "postcode cannot vary"):
            canonicalize_localized_components({
                "postal_code": {"ja": "1000001"},
                "postcode": {"en": "1000002"},
            })

    def test_direct_address_construction_cannot_bypass_the_check(self):
        address = LocalizedAddress(
            values={"house_number": {"ja": "1", "en": "2"}}, extras={}
        )
        for target in ("ja", "en", "fr"):
            with self.subTest(target=target):
                with self.assertRaisesRegex(ValueError, "house_number cannot vary"):
                    select_localized_components(address, target)

    def test_mutation_after_canonicalization_cannot_bypass_the_check(self):
        address = canonicalize_localized_components({"postcode": {"ja": "00123"}})
        address.values["postcode"]["en"] = "00456"
        with self.assertRaisesRegex(ValueError, "postcode cannot vary"):
            select_localized_components(address, "ja")

    def test_equivalent_normalized_identifiers_are_shared_with_leading_zeros(self):
        address = canonicalize_localized_components({
            "postcode": {"ja": " 00123 ", "en": "00123"},
            "house_number": {"ja": "01-02", "en": "01-02"},
        })
        for target in ("ja", "en", "fr"):
            with self.subTest(target=target):
                selected = select_localized_components(address, target)
                self.assertEqual(selected.values, {"house_number": "01-02", "postcode": "00123"})

    def test_numeric_or_postal_equivalence_is_not_guessed(self):
        for key, first, second in (
            ("house_number", "１２", "12"),
            ("postcode", "100-0001", "1000001"),
            ("lot", "01", "1"),
        ):
            with self.subTest(component=key):
                with self.assertRaisesRegex(ValueError, f"{key} cannot vary"):
                    canonicalize_localized_components({key: {"ja": first, "en": second}})


class LanguageVariantIntegrity(unittest.TestCase):
    def test_unspecified_script_does_not_pick_an_arbitrary_variant(self):
        address = canonicalize_localized_components({
            "city": {"sr-Cyrl": "Београд", "sr-Latn": "Beograd"}
        })
        selected = select_localized_components(address, "sr")
        self.assertEqual(selected.values, {})
        self.assertEqual(selected.missing, ("city",))
        self.assertIn("ambiguous_language_variants:city", selected.warnings)

    def test_unspecified_region_does_not_pick_different_place_names(self):
        address = canonicalize_localized_components({
            "city": {"en-GB": "London", "en-US": "Boston"}
        })
        selected = select_localized_components(address, "en")
        self.assertEqual(selected.missing, ("city",))
        self.assertIn("ambiguous_language_variants:city", selected.warnings)

    def test_exact_variant_and_explicit_base_language_remain_usable(self):
        address = canonicalize_localized_components({
            "city": {"sr": "Explicit", "sr-Cyrl": "Београд", "sr-Latn": "Beograd"}
        })
        self.assertEqual(select_localized_components(address, "sr").values["city"], "Explicit")
        self.assertEqual(select_localized_components(address, "sr-Latn").values["city"], "Beograd")

    def test_identical_variants_have_deterministic_fallback(self):
        first = LocalizedAddress(values={"city": {"en-US": "Paris", "en-GB": "Paris"}}, extras={})
        second = LocalizedAddress(values={"city": {"en-GB": "Paris", "en-US": "Paris"}}, extras={})
        self.assertEqual(select_localized_components(first, "en"), select_localized_components(second, "en"))
        self.assertEqual(select_localized_components(first, "en").values, {"city": "Paris"})


class BilingualSourceIntegrity(unittest.TestCase):
    def test_original_input_is_returned_before_alias_and_value_normalization(self):
        source = {
            "iso_country_code": "jp",
            "postal_code": " 1000005 ",
            "City": {"JA": " 千代田区 ", "en": "  Chiyoda-ku  "},
            "delivery_note": {"ja": "  裏口\n利用  ", "en": None},
            "unit": None,
        }
        result = render_bilingual_address(source, "JP")
        self.assertEqual(result.source_components, source)
        self.assertEqual(result.to_dict()["source_components"], source)
        self.assertEqual(result.native.components["city"], "千代田区")
        self.assertEqual(result.native.components["postcode"], "100-0005")
        self.assertNotIn("country", result.source_components)
        self.assertIn("delivery_note", result.untranslated_extras)

    def test_source_snapshot_and_serialized_snapshot_are_not_input_aliases(self):
        source = {"city": {"ja": "東京都", "en": "Tokyo"}, "postcode": "1000005"}
        result = render_bilingual_address(source, "JP")
        source["city"]["ja"] = "大阪市"
        source["postcode"] = "5300001"
        self.assertEqual(result.source_components["city"]["ja"], "東京都")
        self.assertEqual(result.source_components["postcode"], "1000005")
        payload = result.to_dict()
        payload["source_components"]["city"]["en"] = "Changed"
        self.assertEqual(result.source_components["city"]["en"], "Tokyo")

    def test_non_strict_output_retains_missing_language_source(self):
        source = {"city": {"ja": "千代田区"}, "house_number": "1-1"}
        result = render_bilingual_address(source, "JP", strict=False)
        self.assertEqual(result.source_components, source)
        self.assertIn("missing_english:city", result.warnings)

    def test_legacy_manual_construction_defaults_to_empty_source(self):
        result = render_bilingual_address({"house_number": "1"}, "JP")
        legacy = BilingualAddressResult(
            result.country_code, result.native_language, result.native,
            result.english, result.warnings, result.untranslated_extras,
        )
        self.assertEqual(legacy.source_components, {})
        self.assertEqual(legacy.to_dict()["source_components"], {})


if __name__ == "__main__":
    unittest.main()
