"""Behavioral regressions for ID-based multilingual address formatting."""
import copy
import base64
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from addresskit.region_names import RegionCatalog, current_name, open_split_archive


def label(eid, text, lang, **extra):
    return {'id': eid + ':' + lang + ':' + text, 'entity_id': eid, 'text': text,
            'language': lang, 'usage': 'generic', 'source': 'test-fixture', **extra}


def catalog():
    # Synthetic fixtures deliberately include homonyms and conflicting postcodes.
    entities = [
        {'id': 'a', 'country_code': 'AU', 'parent_id': 'state', 'name': 'Same', 'kind': 'populated_place'},
        {'id': 'b', 'country_code': 'AU', 'parent_id': 'state', 'name': 'Same', 'kind': 'populated_place'},
        {'id': 'state', 'country_code': 'AU', 'name': 'State', 'kind': 'administrative_area'},
        {'id': 'nz', 'country_code': 'NZ', 'name': 'Local', 'ascii_name': 'ASCII is not English', 'kind': 'populated_place'},
        {'id': 'pf', 'country_code': 'PF', 'name': 'Ville', 'kind': 'populated_place'},
    ]
    names = [label('a', 'International Name', 'en'),
             label('a', 'Domestic Name', 'en-AU'), label('a', '現地名', 'ja'),
             label('a', '古い地名', 'ja', historic=True), label('state', 'Test State', 'en'),
             label('pf', 'Ville', 'fr')]
    links = [{'id': 'postal:' + eid, 'entity_id': eid, 'country_code': 'AU', 'postal_code': '0800'}
             for eid in ['a', 'b']]
    profiles = {cc: {'fmt': fmt, 'require': require, 'upper': '', 'zip': r'\d{4}',
                    'country_name_en': name, 'source': 'test-fixture', 'template_status': 'country_specific'}
                for cc, fmt, require, name in [
                    ('AU', '%N%n%A%n%C %S %Z', 'ACSZ', 'Australia'),
                    ('NZ', '%N%n%A%n%D%n%C %Z', 'ACZ', 'New Zealand'),
                    ('PF', '%N%n%A%n%Z %C %S', 'ACZ', 'French Polynesia')]}
    return RegionCatalog(entities, names, links, profiles)


class RegionNamesTests(unittest.TestCase):
    def setUp(self):
        self.cat = catalog()

    def test_modes_keep_the_same_entity_id(self):
        intl = self.cat.label('a', mode='international_english')
        domestic = self.cat.label('a', mode='domestic_english')
        local = self.cat.label('a', mode='local', locale='ja')
        self.assertEqual([r['entity_id'] for r in [intl, domestic, local]], ['a'] * 3)
        self.assertEqual([r['text'] for r in [intl, domestic, local]],
                         ['International Name', 'Domestic Name', '現地名'])

    def test_generic_english_does_not_claim_domestic_attestation(self):
        result = self.cat.label('state', mode='domestic_english')
        self.assertEqual(result['language'], 'en')
        self.assertFalse(result['usage_match'])
        self.assertTrue(result['fallback'])

    def test_local_language_is_explicit(self):
        with self.assertRaises(ValueError):
            self.cat.label('a', mode='local')

    def test_ascii_is_not_relabelled_as_english(self):
        result = self.cat.label('nz', mode='international_english')
        self.assertEqual(result['text'], 'Local')
        self.assertEqual(result['language'], 'und')
        self.assertEqual(result['status'], 'untranslated_fallback')

    def test_same_name_requires_disambiguation(self):
        self.assertEqual(self.cat.resolve('AU', 'Same')['status'], 'ambiguous')
        self.assertEqual(self.cat.resolve('NZ', 'Same')['entity_ids'], [])

    def test_postcodes_are_many_to_many_and_retain_zero(self):
        result = self.cat.postal_candidates('AU', '0800')
        self.assertEqual(result['entity_ids'], ['a', 'b'])
        self.assertEqual(result['status'], 'ambiguous')
        self.assertFalse(result['delivery_validated'])
        with self.assertRaises(TypeError):
            self.cat.postal_candidates('AU', 800)

    def test_unknown_postcode_does_not_guess(self):
        result = self.cat.resolve('AU', 'International Name', postal_code='9999')
        self.assertEqual(result['status'], 'unresolved')
        self.assertEqual(result['postal_status'], 'unverified')

    def test_postcode_evidence_and_name_intersect(self):
        result = self.cat.resolve('AU', 'International Name', postal_code='0800')
        self.assertEqual(result['entity_ids'], ['a'])

    def test_country_templates_sort_typed_fields(self):
        au = {'country_code': 'AU', 'address_lines': ['12 Test Road'], 'locality_id': 'a',
              'administrative_area_id': 'state', 'postal_code': '0800'}
        before = copy.deepcopy(au)
        result = self.cat.render(au, mode='international_english', international=True)
        self.assertEqual(result['lines'], ['12 Test Road', 'International Name Test State 0800', 'AUSTRALIA'])
        self.assertEqual(au, before)
        pf = {'country_code': 'PF', 'address_lines': ['12 rue exemple'], 'locality_id': 'pf', 'postal_code': '98701'}
        self.assertEqual(self.cat.render(pf, locale='fr')['lines'][-1], '98701 Ville')

    def test_nz_omits_region_only_from_display(self):
        address = {'country_code': 'NZ', 'address_lines': ['1 Example Lane'], 'locality_id': 'nz',
                   'administrative_area': 'Region kept in input', 'postal_code': '0123'}
        result = self.cat.render(address, mode='international_english')
        self.assertEqual(result['lines'][-1], 'Local 0123')
        self.assertEqual(result['omitted_from_display'], ['administrative_area'])
        self.assertEqual(result['input']['administrative_area'], 'Region kept in input')

    def test_required_fields_reported(self):
        result = self.cat.render({'country_code': 'AU', 'locality_id': 'a'}, mode='international_english')
        self.assertEqual(result['missing_required'], ['address_lines', 'administrative_area', 'postal_code'])

    def test_cross_country_region_is_rejected(self):
        with self.assertRaises(ValueError):
            self.cat.render({'country_code': 'AU', 'locality_id': 'nz'}, mode='international_english')

    def test_newline_in_locality_is_rejected(self):
        with self.assertRaises(ValueError):
            self.cat.render({'country_code': 'AU', 'locality': 'X\nFake Country'}, mode='international_english')

    def test_ambiguous_labels_are_exposed(self):
        self.cat.names['state'].append(label('state', 'Another State', 'en'))
        result = self.cat.label('state', mode='international_english')
        self.assertTrue(result['ambiguous_label'])
        self.assertEqual(len(result['alternatives']), 2)

    def test_accents_do_not_collapse_for_id_resolution(self):
        self.cat.search_index[('NZ', 'māori')].add('nz')
        self.assertEqual(self.cat.resolve('NZ', 'maori')['status'], 'unresolved')

    def test_effective_dates_and_historical_names(self):
        self.assertFalse(current_name({'historic': True}))
        self.assertFalse(current_name({'valid_to': '2000'}))
        self.assertFalse(current_name({'valid_from': '2999-01'}))
        self.assertFalse(current_name({'valid_from': 'unknown'}))
        self.assertTrue(current_name({'valid_from': '2000', 'valid_to': '2999'}))

    def test_unknown_format_is_flagged_and_uppercase_is_applied(self):
        self.cat.profiles['AU']['template_status'] = 'generic_fallback'
        self.cat.profiles['AU']['upper'] = 'CS'
        result = self.cat.render({'country_code': 'AU', 'locality_id': 'a'}, mode='international_english')
        self.assertEqual(result['text'], 'INTERNATIONAL NAME')
        self.assertEqual(result['template_status'], 'generic_fallback')

    def test_attested_english_precedes_generated_domestic_variant(self):
        self.cat.names['state'].append(label('state', 'Generated Name', 'en-AU', status='generated'))
        self.assertEqual(self.cat.label('state', mode='domestic_english')['text'], 'Test State')

    def test_split_archive_rejects_corruption(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as archive:
            archive.writestr('test.txt', 'complete')
        data = stream.getvalue()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'part.bin').write_bytes(data)
            meta = {'parts': [{'path': 'part.bin', 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}],
                    'archive_bytes': len(data), 'archive_sha256': hashlib.sha256(data).hexdigest()}
            with open_split_archive(root, meta) as archive:
                self.assertEqual(archive.read('test.txt'), b'complete')
            encoded = base64.b64encode(data) + b'\n'
            (root / 'part.b64').write_bytes(encoded)
            coded = copy.deepcopy(meta)
            coded['parts'][0].update({'path': 'part.b64', 'storage_encoding': 'base64',
                                     'stored_bytes': len(encoded), 'stored_sha256': hashlib.sha256(encoded).hexdigest()})
            with open_split_archive(root, coded) as archive:
                self.assertEqual(archive.read('test.txt'), b'complete')
            (root / 'part.b64').write_bytes(encoded + b'x')
            with self.assertRaises(ValueError):
                open_split_archive(root, coded)
            (root / 'part.bin').write_bytes(data[:-1])
            with self.assertRaises(ValueError):
                open_split_archive(root, meta)

    def test_split_archive_rejects_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            meta = {'parts': [{'path': '../outside.bin', 'bytes': 1, 'sha256': 'invalid'}]}
            with self.assertRaises(ValueError):
                open_split_archive(tmp, meta)


if __name__ == '__main__':
    unittest.main()
