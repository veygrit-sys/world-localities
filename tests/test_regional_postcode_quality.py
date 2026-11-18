"""Scope postcode syntax to the postal alphabet and the selected territory."""

import unittest

from addressing import (
    CaribbeanRegistry,
    CentralAmericaRegistry,
    EasternAfricaRegistry,
    NorthernAfricaRegistry,
    NorthernAmericaRegistry,
    WesternAfricaRegistry,
    render_northern_america_address,
)


class RegionalPostcodeQuality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.north_america = NorthernAmericaRegistry()
        cls.caribbean = CaribbeanRegistry()
        cls.east_africa = EasternAfricaRegistry()
        cls.north_africa = NorthernAfricaRegistry()
        cls.west_africa = WesternAfricaRegistry()

    def test_latin_letters_accept_ascii_lowercase_without_unicode_case_collisions(self):
        validate = self.north_america.validate_postcode
        self.assertTrue(validate("CA", " k1a 0b1 "))
        self.assertFalse(validate("CA", "K1A 0B1"))
        for code in ("ɪS 01", "İS 01", "ıS 01", "ſM 01"):
            with self.subTest(code=code):
                self.assertFalse(validate("BM", code))

    def test_country_selector_accepts_only_two_ascii_letters_before_case_conversion(self):
        central = CentralAmericaRegistry()
        for check, code, postcode in (
            (self.north_america.validate_postcode, "Uſ", "90210"),
            (self.caribbean.postcode_variant, "vı", "00801"),
            (central.postcode_variant, "ſV", "0110"),
            (self.caribbean.validate_postcode, "ﬄ", "97133"),
            (self.caribbean.validate_postcode, "zz", "00801"),
        ):
            with self.subTest(code=code), self.assertRaises(KeyError):
                check(code, postcode)
        with self.assertRaises(KeyError):
            render_northern_america_address({}, "Uſ", northern_america=self.north_america)
        self.assertTrue(self.north_america.validate_postcode("us", "90210"))
        self.assertEqual(self.caribbean.postcode_variant("vi", "00801"), "zip_5")
        self.assertEqual(central.postcode_variant("sv", "0110"), "current")

    def test_numeric_codes_reject_unrelated_digit_scripts(self):
        validate = self.north_america.validate_postcode
        self.assertTrue(validate("US", "02108-1234"))
        for invalid in ("০২১০৮", "０２１０８", "02١08", "𝟢𝟤𝟣𝟢𝟪", 2108):
            with self.subTest(invalid=invalid):
                self.assertFalse(validate("US", invalid))

    def test_arabic_script_forms_can_use_local_digits_including_fixed_routing_part(self):
        for value in ("٧٧١٠١", "۷۷۱۰۱", "77101"):
            self.assertTrue(self.east_africa.validate_postcode("DJ", value))
        self.assertFalse(self.east_africa.validate_postcode("DJ", "٧٨١٠١"))
        self.assertTrue(self.north_africa.validate_postcode("EG", "٣٧٥٩٩١٤"))
        self.assertFalse(self.north_africa.validate_postcode("EG", "٣٧٥٩٩١"))

    def test_somali_postal_field_remains_on_one_line(self):
        validate = self.east_africa.validate_postcode
        for separator in (" ", "  "):
            self.assertTrue(validate("SO", "jh" + separator + "٠٩٠١٠"))
        for separator in ("\n", "\r\n", "\t", "\u2028", "\u00a0"):
            with self.subTest(separator=separator):
                self.assertFalse(validate("SO", "JH" + separator + "09010"))
        self.assertFalse(validate("SO", "JH 09010\n"))

    def test_required_optional_and_no_system_absence(self):
        validate = self.east_africa.validate_postcode
        self.assertFalse(validate("DJ", None))
        self.assertTrue(validate("SC", None))
        self.assertTrue(validate("SC", "0000"))
        self.assertTrue(validate("BI", "  "))
        self.assertFalse(validate("BI", "0000"))
        self.assertFalse(validate("BI", "\n"))

    def test_sorting_office_code_retains_separate_policy(self):
        self.assertTrue(self.west_africa.validate_sorting_code("CI", "105"))
        self.assertFalse(self.west_africa.validate_postcode("CI", "105"))
        self.assertFalse(self.west_africa.validate_sorting_code("CI", "1５５"))
        self.assertFalse(self.west_africa.validate_sorting_code("CI", "105\r"))

    def test_puerto_rico_and_us_virgin_islands_require_distinct_zip_prefixes(self):
        for prefix, country in (("006", "PR"), ("007", "PR"), ("009", "PR"), ("008", "VI")):
            other = "PR" if country == "VI" else "VI"
            for suffix, variant in (("01", "zip_5"), ("01-1234", "zip_plus_4")):
                code = prefix + suffix
                with self.subTest(code=code, country=country):
                    self.assertEqual(self.caribbean.postcode_variant(country, code), variant)
                    self.assertIsNone(self.caribbean.postcode_variant(other, code))
        for country in ("PR", "VI"):
            self.assertFalse(self.caribbean.validate_postcode(country, "90210"))
