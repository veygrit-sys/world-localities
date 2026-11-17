"""Regression cases for silently lost delivery-point details."""

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from addressing import ProfileRegistry, render_address


class RenderingIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ProfileRegistry()

    def render(self, components, country="US"):
        return render_address(components, country, registry=self.registry)

    def test_address2_does_not_hide_room_number(self):
        result = self.render({
            "road": "Example Road", "house_number": "1",
            "address2": "Building B", "unit": "101",
        })
        self.assertIn("Building B 101", result.text)
        self.assertFalse(result.unrendered_components)
        self.assertIn("combined_subpremise_components", result.warnings)

    def test_all_explicit_subpremise_details_survive(self):
        supplied = {
            "address2": "Building B", "subpremise": "West Wing",
            "block": "Block C", "entrance": "Rear entrance",
            "floor": "Floor 2", "unit": "Unit 101",
        }
        result = self.render(supplied)
        self.assertIn(
            "Building B West Wing Block C Rear entrance Floor 2 Unit 101",
            result.text,
        )
        self.assertFalse(result.unrendered_components)
        self.assertEqual(supplied["subpremise"], "West Wing")

    def test_equal_floor_and_unit_are_not_deduplicated(self):
        result = self.render({"floor": "2", "unit": "2"})
        self.assertEqual(result.components["subpremise"], "2 2")

    def test_identical_opaque_subpremise_slots_are_not_duplicated(self):
        result = self.render({"address2": "Apt 101", "subpremise": "Apt 101"})
        self.assertEqual(result.text.count("Apt 101"), 1)

    def test_address1_with_explicit_road_is_reported_if_not_used(self):
        result = self.render({"address1": "Original delivery line", "road": "Road"})
        self.assertEqual(result.unrendered_components["address_line1"], "Original delivery line")
        self.assertIn("unrendered_known_components", result.warnings)

    def test_recipient_is_reported_when_attention_is_a_different_person(self):
        result = self.render({"recipient": "Recipient", "attention": "Attention"})
        self.assertIn("Attention", result.text)
        self.assertEqual(result.unrendered_components["recipient"], "Recipient")

    def test_synthesized_delivery_line_and_recipient_are_tracked(self):
        result = self.render({"address1": "1 Example Road", "recipient": "Recipient"})
        self.assertIn("1 Example Road", result.text)
        self.assertIn("Recipient", result.text)
        self.assertFalse(result.unrendered_components)

    def test_conflicting_state_is_not_hidden_by_explicit_code(self):
        result = self.render({"state": "California", "state_code": "NY", "city": "Example"})
        self.assertEqual(result.unrendered_components["state"], "California")
        self.assertIn("conflicting_state_and_state_code", result.warnings)

    def test_equivalent_state_name_and_code_are_tracked(self):
        result = self.render({"state": "California", "state_code": "CA", "city": "Example"})
        self.assertFalse(result.unrendered_components)
        self.assertNotIn("conflicting_state_and_state_code", result.warnings)

    def test_unknown_state_name_with_code_is_reported_as_unrendered(self):
        result = self.render({"state": "Unknown state", "state_code": "CA", "city": "Example"})
        self.assertEqual(result.unrendered_components["state"], "Unknown state")

    def test_all_country_templates_keep_combined_details(self):
        for country in self.registry.country_codes:
            with self.subTest(country=country):
                result = self.render({
                    "address2": "BuildingMarker", "floor": "FloorMarker",
                    "unit": "UnitMarker",
                }, country)
                for text in ("BuildingMarker", "FloorMarker", "UnitMarker"):
                    self.assertIn(text, result.text)
                self.assertFalse(result.unrendered_components)


if __name__ == "__main__":
    unittest.main()
