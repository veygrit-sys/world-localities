"""Protect original number strings, row identity, and pinned source validation."""
import csv
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import mx_address_evidence as evidence


class MexicoAddressEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.archive = Path(self.temporary.name) / 'source.zip'

    def fixture(self, overrides=None):
        base = dict(zip(evidence.COLUMNS, ['1', 'Aguascalientes', 'Aguascalientes', 'AVENIDA UNO', '001A', 'COLONIA', '21.9', '-102.2', '00123']))
        records = [base]
        for index, override in enumerate(overrides or [], 2):
            records.append({**base, 'gid': str(index), **override})
        text = io.StringIO(newline='')
        writer = csv.DictWriter(text, fieldnames=evidence.COLUMNS)
        writer.writeheader(); writer.writerows(records)
        with ZipFile(self.archive, 'w') as archive:
            archive.writestr(evidence.MEMBER, text.getvalue())
        return records

    def test_source_strings_and_csv_quoting_are_unchanged(self):
        records = self.fixture([{'hnum': '2-6', 'via': 'CALLE "A", B'}, {'hnum': 'SN'}, {'hnum': ''}])
        self.assertEqual(list(evidence.rows(self.archive)), records)

    def test_full_scan_distinguishes_placeholders_without_dropping_rows(self):
        self.fixture([{'hnum': 'SN'}, {'hnum': ''}, {'hnum': 'S/N'}, {'hnum': '0'}])
        with patch.object(evidence, 'verify_archive'):
            report = evidence.inspect(self.archive)
        self.assertEqual(report['counts']['source_rows'], 5)
        self.assertEqual(report['counts']['number_placeholder_rows'], 2)
        self.assertEqual(report['counts']['nonplaceholder_number_rows'], 2)
        self.assertTrue(report['gid_uniqueness_verified'])
        self.assertFalse(report['issuing_authority_assignment_verified'])
        self.assertFalse(report['national_completeness_verified'])

    def test_invalid_coordinates_and_repeated_keys_remain_visible(self):
        self.fixture([{'gid': '1', 'latitude': 'nan', 'longitude': ''}, {'latitude': '-90', 'longitude': '145.3', 'estado': '', 'cidade': ''}])
        with patch.object(evidence, 'verify_archive'):
            report = evidence.inspect(self.archive)
        self.assertEqual(report['counts']['invalid_or_missing_coordinate_rows'], 1)
        self.assertFalse(report['gid_sequential_from_one'])
        self.assertIsNone(report['gid_uniqueness_verified'])
        self.assertEqual(report['counts']['source_rows'], 3)
        self.assertEqual(report['counts']['world_valid_points_outside_broad_mexico_extent'], 1)
        self.assertEqual(report['counts']['empty_estado_rows'], 1)
        self.assertFalse(report['review_extent_is_legal_boundary_test'])

    def test_query_uses_source_namespace_and_preserves_originals(self):
        self.fixture([{'hnum': 'SN'}, {'estado': 'Jalisco'}])
        with patch.object(evidence, 'verify_archive'):
            report = evidence.query(self.archive, state='aguascalientes', text='sn', limit=1)
        self.assertEqual(len(report['results']), 1)
        self.assertEqual(report['results'][0]['id'], evidence.SOURCE_ID + ':row:2')
        self.assertEqual(report['results'][0]['original']['hnum'], 'SN')

    def test_hash_and_size_are_both_required(self):
        self.fixture()
        data = self.archive.read_bytes()
        evidence.verify_archive(self.archive, hashlib.sha256(data).hexdigest(), len(data))
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            evidence.verify_archive(self.archive, '0' * 64, len(data))
        with self.assertRaisesRegex(ValueError, 'byte count'):
            evidence.verify_archive(self.archive, hashlib.sha256(data).hexdigest(), len(data) + 1)

    def test_unexpected_zip_members_are_rejected(self):
        self.fixture()
        with ZipFile(self.archive, 'a') as archive: archive.writestr('../other.csv', 'x')
        data = self.archive.read_bytes()
        with self.assertRaisesRegex(ValueError, 'members'):
            evidence.verify_archive(self.archive, hashlib.sha256(data).hexdigest(), len(data))

    def test_malformed_row_and_changed_columns_are_rejected(self):
        for content in ['unexpected\n1\n', ','.join(evidence.COLUMNS) + '\n1,too,few\n']:
            with ZipFile(self.archive, 'w') as archive: archive.writestr(evidence.MEMBER, content)
            with self.assertRaises(ValueError): list(evidence.rows(self.archive))

    def test_accepted_source_is_not_overwritten(self):
        self.fixture(); original = self.archive.read_bytes()
        with self.assertRaisesRegex(ValueError, 'new source'):
            evidence.acquire(self.archive)
        self.assertEqual(self.archive.read_bytes(), original)


if __name__ == '__main__': unittest.main()
