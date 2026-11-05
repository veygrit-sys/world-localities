"""Small synthetic contract fixtures; no real-world address accuracy claims."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import europe_priority_ingest as subject


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class EuropeanPriorityIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def args(self, country, source, output=None, **extra):
        return argparse.Namespace(country=country, input=source, sha256=digest(source),
                                  source_date='2026-10-31', output=output or self.root / 'rows.jsonl',
                                  entity=extra.get('entity'), mode=extra.get('mode', 'current'),
                                  delimiter=extra.get('delimiter', ','),
                                  encoding=extra.get('encoding', 'utf-8-sig'))

    def cz_csv(self, id='11915692', postcode='03647', municipality='Březová'):
        record = dict.fromkeys(subject.CZ_REQUIRED, '')
        record.update({'Kód ADM': id, 'Kód obce': '005001', 'Název obce': municipality,
                       'Kód části obce': '0077', 'Název části obce': 'Dědina',
                       'Kód ulice': '', 'Název ulice': '', 'Typ SO': 'č.ev.',
                       'Číslo domovní': '007', 'Číslo orientační': '',
                       'Znak čísla orientačního': '', 'PSČ': postcode,
                       'Souřadnice Y': '835804.84', 'Souřadnice X': '1019584.24',
                       'Platí Od': '2026-01-01T00:00:00'})
        string = io.StringIO(newline='')
        writer = csv.DictWriter(string, fieldnames=subject.CZ_REQUIRED, delimiter=';')
        writer.writeheader()
        writer.writerow(record)
        return string.getvalue().encode('cp1250')

    def test_cz_archived_national_csv_preserves_codes_and_sjtsk(self):
        archive = self.root / 'ruian.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('CSV/OB_005001_ADR.csv', self.cz_csv())
        args = self.args('CZ', archive)
        receipt = subject.normalize(args)
        self.assertEqual(receipt['records'], 1)
        self.assertEqual(receipt['members'], 1)
        self.assertFalse(receipt['national_completeness_verified'])
        record = json.loads(args.output.read_text().splitlines()[0])
        self.assertEqual(record['municipality']['id'], '005001')
        self.assertEqual(record['house']['building_number'], '007')
        self.assertEqual(record['postcode'], '03647')
        self.assertEqual(record['source_point']['crs'], 'S-JTSK')
        self.assertEqual(record['municipality']['name'], 'Březová')
        self.assertEqual(record['qualified_id'], 'CZ:RUIAN:11915692')
        self.assertNotIn('latitude', record['source_point'])
        self.assertEqual(record['valid_from_source'], '2026-01-01T00:00:00')

    def test_cz_absent_street_and_geometry_are_not_fabricated(self):
        row = self.cz_csv().decode('cp1250').splitlines()
        hdr = next(csv.DictReader(io.StringIO('\n'.join(row)), delimiter=';'))
        hdr['Souřadnice Y'] = ''
        hdr['Souřadnice X'] = ''
        record = subject.cz_record(hdr, 'file', 2)
        self.assertIsNone(record['source_point']['x_m'])
        self.assertEqual(record['street']['name'], '')

    def test_duplicate_source_ids_abort_without_partial_publication(self):
        archive = self.root / 'dups.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('CSV/A.csv', self.cz_csv())
            z.writestr('CSV/B.csv', self.cz_csv())
        args = self.args('CZ', archive)
        with self.assertRaisesRegex(ValueError, 'Duplicate source-qualified'):
            subject.normalize(args)
        self.assertFalse(args.output.exists())
        self.assertFalse(args.output.with_name(args.output.name + '.partial').exists())

    def test_wrong_hash_and_bad_postcode_fail_closed(self):
        raw = self.root / 'sample.csv'
        raw.write_bytes(self.cz_csv(postcode='unexpected'))
        args = self.args('CZ', raw)
        with self.assertRaisesRegex(ValueError, 'postcode'):
            subject.normalize(args)
        self.assertFalse(args.output.exists())
        args.sha256 = '0' * 64
        with self.assertRaisesRegex(ValueError, 'SHA-256'):
            subject.normalize(args)

    def test_rejects_overwrite_and_partial_reuse(self):
        raw = self.root / 'input.csv'
        raw.write_bytes(self.cz_csv())
        args = self.args('CZ', raw)
        args.output.write_text('existing')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            subject.normalize(args)
        self.assertEqual(args.output.read_text(), 'existing')
        args.output.unlink()
        partial = args.output.with_name(args.output.name + '.partial')
        partial.write_text('prior')
        with self.assertRaisesRegex(ValueError, 'incomplete prior'):
            subject.normalize(args)
        self.assertEqual(partial.read_text(), 'prior')

    def test_rejects_zip_traversal_and_duplicate_names(self):
        archive = self.root / 'bad.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('../escape.csv', self.cz_csv())
        with self.assertRaisesRegex(ValueError, 'Unsafe'):
            subject.normalize(self.args('CZ', archive))
        duplicate = self.root / 'dupnames.zip'
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            with zipfile.ZipFile(duplicate, 'w') as z:
                z.writestr('same.csv', self.cz_csv())
                z.writestr('same.csv', self.cz_csv())
        with self.assertRaisesRegex(ValueError, 'Duplicate ZIP'):
            subject.normalize(self.args('CZ', duplicate))

    def test_dk_entity_keeps_relationships_without_join(self):
        file = self.root / 'DAR.csv'
        file.write_text('id_lokalId,husnummer,etagebetegnelse,dørbetegnelse\n'
                        '1234-uuid,house-001,01,th\n', encoding='utf-8')
        args = self.args('DK', file, entity='Adresse')
        report = subject.normalize(args)
        self.assertEqual(report['records'], 1)
        row = json.loads(args.output.read_text().strip())
        self.assertEqual(row['references']['husnummer'], 'house-001')
        self.assertFalse(row['temporal_join_verified'])
        self.assertEqual(row['entity'], 'Adresse')
        self.assertNotIn('postcode', row)

    def test_dk_requires_known_schema_and_entity(self):
        file = self.root / 'DAR.csv'
        file.write_text('id_lokalId,postnummer\n1,1000\n', encoding='utf-8')
        args = self.args('DK', file, entity='Adresse')
        with self.assertRaisesRegex(ValueError, 'header'):
            subject.normalize(args)
        args.entity = 'Bad'
        with self.assertRaisesRegex(ValueError, 'DAR entity'):
            subject.normalize(args)

    def test_polish_gml_is_survey_only_with_namespace_counts(self):
        data = (b'<?xml version="1.0" encoding="UTF-8"?>'
                b'<g:collection xmlns:g="http://www.opengis.net/gml/3.2" '
                b'xmlns:p="https://geoportal.gov.pl/schemas/prgad/1.0">'
                b'<p:point><p:identifier>123</p:identifier></p:point></g:collection>')
        file = self.root / 'poland.gml'
        file.write_bytes(data)
        report = subject.survey_pl(self.args('PL', file))
        self.assertEqual(report['address_rows_normalized'], 0)
        self.assertEqual(report['files'][0]['root_qname'], '{http://www.opengis.net/gml/3.2}collection')
        self.assertEqual(report['xml_elements_by_qname']['{https://geoportal.gov.pl/schemas/prgad/1.0}point'], 1)

    def test_polish_dtd_is_rejected(self):
        file = self.root / 'poland.gml'
        file.write_bytes(b'<!DOCTYPE a [<!ENTITY e "BAD">]><a>&e;</a>')
        with self.assertRaisesRegex(ValueError, 'DTD'):
            subject.survey_pl(self.args('PL', file))


if __name__ == '__main__':
    unittest.main()

