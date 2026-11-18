"""Scoped validation of preserved Americas source roles through the public entry points."""

import json
from pathlib import Path
import subprocess
import sys
import unicodedata
import unittest

from registries.americas.validate_locality import validate_locality

ROOT = Path(__file__).resolve().parents[1]


class AmericasLocalityQuality(unittest.TestCase):
    def test_positive_localities_preserve_sources_and_codes(self):
        cases = [
            ('US', 'Springfield city', 'IL', '1772000'),
            ('CA', 'Toronto', 'CA-ON', '3520005'),
            ('MX', 'Jesús María', 'MX-AGU', '01005'),
            ('BR', 'São Paulo', 'BR-SP', '3550308'),
        ]
        for country, locality, region, code in cases:
            with self.subTest(country=country):
                result = validate_locality(country, locality, region=region)
                self.assertEqual(result['status'], 'matched')
                self.assertEqual(result['match_count'], 1)
                row, = result['candidates']
                self.assertEqual((row['name'], row['source_code']), (locality, code))
                self.assertTrue((ROOT / row['reference']).is_file())
                self.assertEqual(len(row['shard_sha256']), 64)
                self.assertTrue(result['source_observed_at'])
                self.assertFalse(result['postal_assignment_verified'])
                self.assertFalse(result['premise_verified'])
                self.assertFalse(result['deliverability_verified'])

    def test_ambiguous_after_truncation_even_in_one_region(self):
        # Taber has two distinct census subdivision codes within Alberta.
        for country, locality, region, expected in [
            ('CA', 'Taber', 'AB', 2), ('BR', 'Rio Branco', None, 2),
            ('MX', 'Jesús María', None, 2), ('US', 'Springfield city', None, 13),
        ]:
            with self.subTest(country=country):
                result = validate_locality(country, locality, region=region, limit=1)
                self.assertEqual(result['status'], 'ambiguous')
                self.assertEqual(result['match_count'], expected)
                self.assertEqual(len(result['candidates']), 1)
                self.assertTrue(result['truncated'])
        one = validate_locality('CA', 'Taber', region='AB', source_code='4802022')
        self.assertEqual(one['status'], 'matched')
        self.assertEqual(one['candidates'][0]['source_code'], '4802022')

    def test_wrong_region_retains_alternatives_outside_accepted_results(self):
        result = validate_locality('CA', 'Toronto', region='QC')
        self.assertEqual(result['status'], 'outside_requested_region')
        self.assertEqual(result['alternative_region_codes'], ['CA-ON'])
        self.assertEqual((result['match_count'], result['candidates']), (0, []))
        # Competing evidence (a real code for a different name) cannot accept either input.
        conflict = validate_locality('MX', 'Guadalajara', region='JAL', source_code='01005')
        self.assertEqual(conflict['status'], 'no_match_in_snapshot')

    def test_unicode_equivalent_spelling_but_not_substrings_or_different_accents(self):
        nfd = unicodedata.normalize('NFD', 'sÃO PAULO')
        self.assertEqual(validate_locality('BR', nfd, region='SP')['status'], 'matched')
        for text in ('São Pau', 'Sao Paulo'):
            with self.subTest(text=text):
                self.assertEqual(validate_locality('BR', text, region='SP')['status'], 'no_match_in_snapshot')

    def test_case_matching_does_not_expand_compatibility_characters(self):
        self.assertEqual(validate_locality('US', 'SPRINGFIELD CITY', region='IL')['status'], 'matched')
        for text in ('ſpringfield city', 'Springﬁeld city'):
            with self.subTest(text=text):
                result = validate_locality('US', text, region='IL')
                self.assertEqual(result['status'], 'no_match_in_snapshot')
                self.assertEqual(result['candidates'], [])

    def test_non_candidates_and_external_areas(self):
        role = validate_locality('US', 'County subdivisions not defined', region='CT', source_code='0912000000')
        self.assertEqual(role['status'], 'no_match_in_snapshot')
        for country, region in [('US', 'US-PR'), ('CA', 'US-IL'), ('PR', None), ('uſ', None), ('US', 'Uſ-CA')]:
            with self.subTest(country=country, region=region), self.assertRaises(ValueError):
                validate_locality(country, 'Example', region=region)

    def test_normal_cli_and_input_types(self):
        for command in (['-m', 'registries.americas.validate_locality'],
                        ['registries/americas/validate_locality.py']):
            run = subprocess.run([sys.executable, *command, '--country', 'MX', '--region', 'JAL',
                                  '--locality', 'Guadalajara'], cwd=ROOT, capture_output=True,
                                 text=True, check=True)
            self.assertEqual(json.loads(run.stdout)['candidates'][0]['source_code'], '14039')
        for kwargs in ({'source_code': 1005}, {'source_code': '０１００５'}, {'region': ''}, {'limit': True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                validate_locality('MX', 'Jesús María', **kwargs)
