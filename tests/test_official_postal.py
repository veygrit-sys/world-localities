"""Source replay and ambiguity checks; not a delivery-quality benchmark."""
import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'official-registry'))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'official-registry' / filename)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


BUILD = load('official_build', 'build.py')
QUERY = load('official_query', 'query.py')
ROMAN = load('official_roman', 'romanize.py')


class OfficialPostalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.jp = list(QUERY.read_csv(ROOT / 'official-registry/JP/postal_rows.csv.gz'))

    def test_official_code_identity_and_unique_associations(self):
        entities = {r['entity_id']: r for r in QUERY.read_csv(ROOT / 'official-registry/JP/entities.csv.gz')}
        for r in self.jp:
            self.assertEqual(r['jis_code'], entities[r['entity_id']]['lg_code'][:5])
            self.assertTrue(BUILD.valid_lg(entities[r['entity_id']]['lg_code']))
            self.assertRegex(r['code'], '^[0-9]{7}$')
            self.assertEqual(r['code_kind'], 'full')
        self.assertEqual(len(self.jp), len({r['association_id'] for r in self.jp}))

    def test_leading_zero_and_language_switch(self):
        ja = QUERY.lookup('JP', '060-0000', 'ja'); latin = QUERY.lookup('JP', '0600000', 'ja-Latn')
        self.assertEqual(ja['input_code'], '0600000'); self.assertTrue(ja['candidates'])
        self.assertEqual([r['entity_id'] for r in ja['candidates']], [r['entity_id'] for r in latin['candidates']])
        en = QUERY.lookup('JP', '0600000', 'en')
        self.assertTrue(all(r['name_status'] == 'missing_requested_language' for r in en['candidates']))

    def test_real_ambiguous_reading_is_preserved(self):
        rows = [r for r in self.jp if r['jis_code'] == '28203' and r['code'] == '6730012' and r['town_ja'] == '和坂']
        self.assertEqual(len(rows), 2); self.assertEqual(len({r['town_kana'] for r in rows}), 2)
        self.assertTrue(all(r['roman_match_status'] == 'ambiguous' and not r['town_roman'] for r in rows))

    def test_postal_instructions_are_not_town_names(self):
        rows = [r for r in self.jp if r['town_ja'] == '以下に掲載がない場合']
        self.assertTrue(rows); self.assertTrue(all(r['town_is_postal_instruction'] == 'true' for r in rows))

    def test_shared_postcode_returns_all_municipalities(self):
        groups = {}
        for r in self.jp:
            groups.setdefault(r['code'], set()).add(r['entity_id'])
        code, ids = next((k, v) for k, v in groups.items() if len(v) > 1)
        self.assertEqual({r['entity_id'] for r in QUERY.lookup('JP', code, 'ja')['candidates']}, ids)

    def test_join_keeps_qualifiers_and_postcode(self):
        native = ['11111', '', '0010001', '', '', '', '県', '市区', '町（１丁目）']
        roman = ['0010001', '県', '市　区', '町（１丁目）', 'P', 'C', 'T']
        self.assertEqual(BUILD.roman_match(native, BUILD.roman_index([roman]))[0], 'matched_unique')
        for changed in [roman[:3] + ['町'] + roman[4:], ['0010002'] + roman[1:]]:
            self.assertEqual(BUILD.roman_match(native, BUILD.roman_index([changed]))[0], 'unmatched')

    def test_prefix_is_not_a_complete_code(self):
        with self.assertRaisesRegex(ValueError, 'prefix'):
            QUERY.lookup('TW', '300', 'en')
        result = QUERY.lookup('TW', '300001', 'en', include_prefix=True)
        self.assertEqual(len(result['candidates']), 3)
        self.assertFalse(result['complete_postcode_verified'])
        self.assertTrue(all(r['names'] for r in result['candidates']))

    def test_bilingual_labels_share_ids(self):
        groups = {}
        for r in QUERY.read_csv(ROOT / 'official-registry/TW/names.csv'):
            groups.setdefault(r['entity_id'], set()).add(r['language'])
        self.assertEqual(len(groups), 371)
        self.assertTrue(all(v == {'zh-Hant', 'en'} for v in groups.values()))

    def test_checksums(self):
        for cc in ['JP', 'TW']:
            self.assertEqual(BUILD.verify(ROOT / 'official-registry' / cc)['checksums'], 'passed')

    def test_all_matched_roman_fields_replay_exactly(self):
        source = BUILD.zip_csv(ROOT / 'official-registry/JP/sources/postal-roman.zip', 'cp932', 7)
        count = 0
        for r in self.jp:
            if r['roman_match_status'] == 'matched_unique':
                expanded = QUERY.expand_roman(r)
                self.assertEqual([expanded[k + '_roman'] for k in BUILD.ROLES], source[int(r['roman_row']) - 1][4:7])
                count += 1
        self.assertEqual(count, 121867)

    def test_generator_is_explicit_and_source_wins(self):
        for kana, expected in [('ナンバ', 'NAMBA'), ('エッチュウ', 'ETCHU'), ('ホッカイドウ', 'HOKKAIDO')]:
            self.assertEqual(ROMAN.convert(kana), expected)
        self.assertEqual(ROMAN.convert('ﾄｳｷｮｳﾄ', '東京都', 'prefecture'), 'TOKYO TO')
        self.assertIsNone(ROMAN.convert('京都'))
        self.assertEqual(ROMAN.choose('ナンバ')['status'], 'unavailable')
        self.assertEqual(ROMAN.choose('ナンバ', allow_generated=True)['status'], 'generated_unreviewed')
        self.assertEqual(ROMAN.choose('ナンバ', official='SOURCE EXCEPTION', allow_generated=True)['text'], 'SOURCE EXCEPTION')


if __name__ == '__main__':
    unittest.main()
