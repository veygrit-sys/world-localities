"""Fetch pinned public postal inputs, then deterministically rebuild JP/TW."""
import argparse
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCES = {
    'JP/sources/postal-utf.zip': {
        'url': 'https://www.post.japanpost.jp/service/search/zipcode/download/utf/zip/utf_ken_all.zip',
        'sha256': '444881769a631d2c36c644fc041e5ce62fe65d204ff498a601641ba1e66b5955',
        'bytes': 2135514, 'published_on': '2026-09-30'},
    'JP/sources/postal-roman.zip': {
        'url': 'https://www.post.japanpost.jp/service/search/zipcode/download/roman/KEN_ALL_ROME.zip',
        'sha256': '9764834dfd1d0148600c38b7fc4c00feae8443e81e68da3a49469447cd97707d',
        'bytes': 1759193, 'published_on': '2025-06-18', 'reference_month': '2025-06'},
    'TW/sources/names.xml': {
        'url': 'https://www.post.gov.tw/post/download/County_h_10906.xml',
        'sha256': '24acfe52023f0ddc2149a2f8368910cd0968584913f3ac17678abb3048cba1b9',
        'bytes': 55902, 'published_on': '2020-06-12'}
}


def fetch():
    for relative, spec in SOURCES.items():
        path = ROOT / relative
        if path.exists():
            data = path.read_bytes()
        else:
            with urllib.request.urlopen(spec['url'], timeout=45) as response:
                data = response.read(20_000_001)
        if len(data) != spec['bytes'] or hashlib.sha256(data).hexdigest() != spec['sha256']:
            raise ValueError('Source version changed; review before updating: ' + relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        print('Verified public source:', relative, len(data), flush=True)


if __name__ == '__main__':
    fetch()
