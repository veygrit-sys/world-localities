"""Search preserves source values and reports observation counts honestly."""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from localities.official_expansion import search


class OfficialExpansionSearchTests(unittest.TestCase):
    def fixture(self, root):
        folder = Path(root) / 'registries/official/expansions/MY'
        folder.mkdir(parents=True)
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(['country', 'postcode', 'city'])
        writer.writerows([['MY', '01000', 'ＡＲＡＵ'], ['MY', '40160', 'Sungai Buloh'],
                          ['MY', '40160', 'Shah Alam']])
        raw = gzip.compress(stream.getvalue().encode(), mtime=0)
        (folder / 'records.csv.gz').write_bytes(raw)
        coverage = {'country': 'MY', 'rows': 3, 'record_file': 'records.csv.gz',
                    'search_fields': ['postcode', 'city'], 'scope': 'fixture postcode-city associations',
                    'files': {'records.csv.gz': {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}}
        (folder / 'coverage.json').write_text(json.dumps(coverage))
        return folder

    def test_leading_zero_and_multiple_associations_survive_pagination(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root)
            result = search('MY', '40160', field='postcode', exact=True, limit=1, root=root)
            self.assertEqual(result['matched_observations'], 2)
            self.assertEqual(result['returned_observations'], 1)
            self.assertTrue(result['truncated'])
            self.assertEqual(search('MY', '01000', field='postcode', exact=True, root=root)['results'][0]['postcode'], '01000')

    def test_normalization_is_search_only_and_source_values_survive(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root)
            result = search('MY', 'arau', field='city', exact=True, root=root)
            self.assertEqual(result['results'][0]['city'], 'ＡＲＡＵ')
            self.assertFalse(result['deliverability_verified'])
            self.assertIsNone(result['freshness_verified'])

    def test_tampered_payload_and_unlisted_field_are_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            folder = self.fixture(root)
            with self.assertRaises(ValueError):
                search('MY', 'x', field='nonexistent', root=root)
            with (folder / 'records.csv.gz').open('ab') as stream:
                stream.write(b'tampered')
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                search('MY', '40160', root=root)

    def test_scope_and_limit_must_be_explicit_supported_values(self):
        with tempfile.TemporaryDirectory() as root:
            self.fixture(root)
            for country, query, limit in [('ZZ', 'x', 20), ('MY', ' ', 20), ('MY', 'x', 0), ('MY', 'x', 101)]:
                with self.subTest(country=country, query=query, limit=limit), self.assertRaises(ValueError):
                    search(country, query, limit=limit, root=root)


if __name__ == '__main__':
    unittest.main()
