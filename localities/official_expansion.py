"""Offline verification and evidence-qualified search of explicit official layers."""
from __future__ import annotations

import csv
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
IMPORTERS = {'HK': 'import_hk_official.py', 'KR': 'import_kr_official.py',
             'MY': 'import_my_official.py', 'TW': 'import_tw_official.py'}


def folder_for(country, root=ROOT):
    if country not in IMPORTERS:
        raise ValueError('official expansion is not installed for this collection code')
    folder = Path(root) / 'registries/official/expansions' / country
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError('missing or unsafe official expansion')
    return folder


def _safe(folder, name):
    relative = Path(name)
    if (not name or relative.is_absolute() or '..' in relative.parts
            or '\\' in name or ':' in name):
        raise ValueError('unsafe official layer path')
    path = folder / relative
    if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
        raise ValueError('unsafe official layer file')
    return path


def verify(country, root=ROOT):
    folder = folder_for(country, root)
    path = Path(root) / 'scripts' / IMPORTERS[country]
    name = 'official_expansion_' + country
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    result = module.verify(folder)
    if result.get('status') != 'passed':
        raise ValueError('official importer did not report successful verification')
    return result


def _fold(value):
    return unicodedata.normalize('NFKC', value).casefold()


def search(country, text, field=None, exact=False, limit=20, root=ROOT):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('search text must be nonempty')
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit must be between 1 and 100')
    folder = folder_for(country, root)
    coverage = json.loads((folder / 'coverage.json').read_text())
    if coverage.get('country') != country:
        raise ValueError('official layer country mismatch')
    record_file = coverage.get('record_file', 'records.csv.gz')
    path = _safe(folder, record_file)
    spec = coverage['files'][record_file]
    raw = path.read_bytes()
    if len(raw) != spec['bytes'] or hashlib.sha256(raw).hexdigest() != spec['sha256']:
        raise ValueError('official search data checksum mismatch')
    fields = coverage['search_fields']
    if not fields or len(fields) != len(set(fields)) or not all(isinstance(x, str) for x in fields):
        raise ValueError('invalid official search fields')
    if field is not None:
        if field not in fields:
            raise ValueError('field is not an allowed search field')
        fields = [field]
    needle = _fold(text)
    results = []
    matches = observations = 0
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None or any(name not in reader.fieldnames for name in fields):
            raise ValueError('official search columns differ from declared fields')
        for row in reader:
            observations += 1
            if None in row or any(value is None for value in row.values()):
                raise ValueError('invalid official search CSV row')
            if 'country' in row and row['country'] != country:
                raise ValueError('official search row belongs to another country')
            values = [_fold(row[key]) for key in fields]
            if any((needle == value if exact else needle in value) for value in values):
                matches += 1
                if len(results) < limit:
                    results.append(row)
    if type(coverage.get('rows')) is not int or observations != coverage['rows']:
        raise ValueError('official search row count differs from coverage')
    return {'country': country, 'query': text, 'field': field, 'exact': exact,
            'source_observations': observations,
            'matched_observations': matches, 'returned_observations': len(results),
            'truncated': matches > limit, 'results': results,
            'integrity_scope': 'stored record-file bytes and declared columns; no live-source lookup',
            'data_scope': coverage.get('scope', coverage.get('layer_kind')),
            'national_completeness_verified': False, 'freshness_verified': None,
            'deliverability_verified': False}


def add_cli(commands):
    parser = commands.add_parser('official', help='search installed source-qualified official expansions')
    sub = parser.add_subparsers(dest='official_command', required=True)
    query = sub.add_parser('search')
    query.add_argument('--country', required=True, choices=sorted(IMPORTERS))
    query.add_argument('--text', required=True)
    query.add_argument('--field')
    query.add_argument('--exact', action='store_true')
    query.add_argument('--limit', type=int, default=20)
