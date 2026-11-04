"""Versioned kana conversion. Source spellings always take priority.

Reference: Japan Post roman_shiyou.pdf. Unknown component boundaries and kanji
readings are not guessed. This is a project implementation, not certification.
"""
import unicodedata

METHOD = 'jp-postal-kana-v1'
REFERENCE = 'https://www.post.japanpost.jp/service/search/zipcode/download/roman_shiyou.pdf'
BASE = dict(zip(
    'アイウエオカキクケコサシスセソタチツテトナニヌネノハヒフヘホマミムメモヤユヨラリルレロワヲンガギグゲゴザジズゼゾダヂヅデドバビブベボパピプペポ',
    'A I U E O KA KI KU KE KO SA SHI SU SE SO TA CHI TSU TE TO NA NI NU NE NO HA HI FU HE HO MA MI MU ME MO YA YU YO RA RI RU RE RO WA O N GA GI GU GE GO ZA JI ZU ZE ZO DA JI ZU DE DO BA BI BU BE BO PA PI PU PE PO'.split()))
TABLE = dict(BASE)
for first, stem in [('キ', 'KY'), ('シ', 'SH'), ('チ', 'CH'), ('ニ', 'NY'), ('ヒ', 'HY'),
                    ('ミ', 'MY'), ('リ', 'RY'), ('ギ', 'GY'), ('ジ', 'J'), ('ビ', 'BY'), ('ピ', 'PY')]:
    for small, vowel in [('ャ', 'A'), ('ュ', 'U'), ('ョ', 'O')]:
        TABLE[first + small] = stem + vowel
for kana, latin in list(TABLE.items()):
    if latin.endswith('O'):
        TABLE[kana + 'ウ'] = latin
        TABLE[kana + 'オ'] = latin
    elif latin.endswith('U') and kana != 'ウ':
        TABLE[kana + 'ウ'] = latin
TABLE.update({'ヴ': 'BU', 'ヴァ': 'BUA', 'ヴィ': 'BUI', 'ヴゥ': 'BUU', 'ヴェ': 'BUE', 'ヴォ': 'BUO',
              'ヴォウ': 'BUO', 'ヴォオ': 'BUO', 'ファ': 'FUA', 'フィ': 'FUI', 'フゥ': 'FU',
              'フェ': 'FUE', 'フォ': 'FUO', 'フォウ': 'FUO', 'フォオ': 'FUO'})
SUFFIXES = {'都': ['ト'], '府': ['フ'], '県': ['ケン'], '市': ['シ'], '区': ['ク'],
            '郡': ['グン'], '町': ['チョウ', 'マチ'], '村': ['ムラ', 'ソン']}


def normalize(kana):
    kana = unicodedata.normalize('NFKC', kana)
    return ''.join(chr(ord(c) + 0x60) if 'ぁ' <= c <= 'ゖ' else c for c in kana)


def kana_ascii(value):
    value = normalize(value)
    parts = []; i = 0
    def token(position):
        for length in (3, 2, 1):
            key = value[position:position + length]
            if key in TABLE:
                return key, TABLE[key]
        return '', ''
    while i < len(value):
        char = value[i]
        if char in {'ン', 'ッ'}:
            _, nxt = token(i + 1)
            if char == 'ン':
                parts.append('M' if nxt[:1] in {'B', 'M', 'P'} else 'N')
            else:
                if not nxt or nxt[0] in 'AEIOUN':
                    return None
                parts.append('T' if nxt.startswith('CH') else nxt[0])
            i += 1
            continue
        if char == 'ー':
            if not parts or parts[-1][-1:] not in 'AEIOU':
                return None
            i += 1
            continue
        key, latin = token(i)
        if key:
            if i and value[i - 1].isascii() and value[i - 1].isalnum():
                parts.append('-')
            parts.append(latin); i += len(key)
        elif char in '、・':
            parts.append('.'); i += 1
        elif char.isascii() and (char.isalnum() or char in ' ()-.,/'):
            parts.append(char.upper()); i += 1
        else:
            return None
    return ''.join(parts) or None


def convert(kana, native='', role='town'):
    if not kana or role not in {'prefecture', 'municipality', 'town'}:
        return None
    kana = normalize(kana)
    if role == 'municipality' and ('郡' in native or ('市' in native and native.endswith('区'))):
        return None
    if role in {'prefecture', 'municipality'} and native:
        for suffix in SUFFIXES.get(native[-1], []):
            if kana.endswith(suffix) and len(kana) > len(suffix):
                stem = kana_ascii(kana[:-len(suffix)]); ending = kana_ascii(suffix)
                return stem + ' ' + ending if stem and ending else None
    return kana_ascii(kana)


def choose(kana, native='', role='town', official=None, allow_generated=False):
    if official:
        return {'text': official, 'language': 'ja-Latn', 'status': 'source_label', 'generated': False}
    value = convert(kana, native, role) if allow_generated else None
    return {'text': value, 'language': 'ja-Latn' if value else None,
            'status': 'generated_unreviewed' if value else 'unavailable',
            'generated': bool(value), 'method': METHOD if value else None}
