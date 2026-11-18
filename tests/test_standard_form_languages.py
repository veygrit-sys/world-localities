"""Input form languages and address display languages have distinct scopes."""

import unittest

from addressing import ProfileRegistry


class StandardFormLanguages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ProfileRegistry()

    def test_mainland_china_uses_simplified_chinese_for_the_form(self):
        self.assertEqual(self.registry.standard_form_languages("cn"), ("zh-Hans",))
        self.assertEqual(self.registry.select("CN", international=True).key, "CN_en")

    def test_indian_english_form_preserves_hindi_display_support(self):
        self.assertEqual(self.registry.standard_form_languages("IN"), ("en",))
        self.assertEqual(self.registry.select("IN", language="en").key, "IN_en")
        self.assertEqual(self.registry.select("IN").key, "IN_hi")

    def test_unreviewed_countries_do_not_inherit_a_form_policy(self):
        for country in ("JP", "HK", "TW", "MO"):
            with self.subTest(country=country):
                self.assertIsNone(self.registry.standard_form_languages(country))
        with self.assertRaises(KeyError):
            self.registry.standard_form_languages("ZZZ")

    def test_compiled_profiles_alone_do_not_imply_form_support(self):
        core = ProfileRegistry(extension_paths=())
        self.assertIsNone(core.standard_form_languages("CN"))
        self.assertIsNone(core.standard_form_languages("IN"))
