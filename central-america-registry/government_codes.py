#!/usr/bin/env python3
"""Government-published canton codes, separate from GeoNames and legal boundaries.

The Ministry of Health FHIR guide is 1.1.0-ballot; resource status/date and
publisher are preserved. No GeoNames same_as links or legal currentness are
inferred. This imports administrative codes, not any patient or medical data.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import urllib.request
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = 'central-america-registry/government-reference/CR'
URL = 'https://www.ministeriodesalud.go.cr/fhir/CodeSystem-cantones-cs.json'
CANONICAL = 'https://ministeriodesalud.go.cr/fhir/CodeSystem/cantones-cs'
_spec = importlib.util.spec_from_file_location('cr_code_validation', ROOT / 'north-america-registry/validation.py')
v = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(v)


def parsed_codes(source):
    v.require(source['resourceType'] == 'CodeSystem' and source['url'] == CANONICAL,
              'unexpected government code system')
    v.require(source['publisher'] == 'Ministerio de Salud de Costa Rica', 'unexpected code publisher')
    v.require(source['version'] and source['date'] and source['status'] == 'active', 'unsupported source edition/status')
    concepts = v.unique_rows(source['concept'], 'code', 'canton code system')
    v.require(source['count'] == len(concepts) == 84 and source['content'] == 'complete',
              'canton source count changed; review the new edition')
    result = []
    for code, concept in sorted(concepts.items()):
        v.require(re.fullmatch('[1-7][0-9]{2}', code) and concept['display'].strip(), 'invalid canton code/name')
        result.append({'id': 'admin:cr:minsa:canton:' + code, 'country': 'CR', 'code': code,
                       'code_system': CANONICAL, 'name': concept['display'],
                       'language': source.get('language', 'und'), 'kind': 'canton_code_system_entry',
                       'source_version': source['version'], 'source_date': source['date'],
                       'source_status': source['status'], 'geonames_id': None,
                       'current_legal_boundary_verified': False, 'delivery_verified': False})
    v.require(concepts['612']['display'] == 'Monteverde' and concepts['613']['display'] == 'Puerto Jiménez',
              'new-canton code/name mismatch')
    return result


def verify(root=ROOT):
    directory = Path(root) / DIRECTORY
    manifest = v.load_json(directory, 'manifest.json')
    v.require(manifest['source_url'] == URL and manifest['schema_version'] == 1, 'government manifest mismatch')
    v.require(manifest['official_currentness_verified'] is False and manifest['geonames_crosswalk_verified'] is False,
              'unsupported government-currentness claim')
    files = manifest['files']
    v.require(set(files) == {'source.json', 'cantons.json'}, 'government source file inventory mismatch')
    actual = {p.name for p in directory.iterdir()}
    v.require(actual == set(files) | {'manifest.json'}, 'unexpected government source files')
    source = v.decode_json(v.verified_bytes(directory, 'source.json', files['source.json']))
    rows = v.decode_json(v.verified_bytes(directory, 'cantons.json', files['cantons.json']))
    v.require(rows == parsed_codes(source), 'government code source replay mismatch')
    return {'status': 'passed', 'source_replay': 'exact', 'cantons': len(rows),
            'source_version': source['version'], 'source_date': source['date'],
            'source_status': source['status'], 'manifest_sha256': v.digest(v.safe_file(directory, 'manifest.json').read_bytes()),
            'note': 'Complete listed CodeSystem, not verification of current legal boundaries or streets.'}


class PublisherRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        parsed = urlsplit(newurl)
        v.require(parsed.scheme == 'https' and parsed.hostname in ('ministeriodesalud.go.cr', 'www.ministeriodesalud.go.cr'),
                  'unexpected government source redirect')
        return super().redirect_request(request, fp, code, message, headers, newurl)


def import_once(root=ROOT):
    directory = Path(root).resolve() / DIRECTORY
    v.require(not directory.is_symlink() and not directory.parent.is_symlink(), 'unsafe government output')
    if directory.exists():
        return verify(root)
    opener = urllib.request.build_opener(PublisherRedirects())
    request = urllib.request.Request(URL, headers={'User-Agent': 'world-localities-government-code-review/1.0'})
    with opener.open(request, timeout=90) as response:
        data = response.read(2 * 1024 * 1024 + 1)
        v.require(0 < len(data) <= 2 * 1024 * 1024, 'government source exceeds size bound')
        headers = {'last_modified': response.headers.get('Last-Modified'), 'etag': response.headers.get('ETag')}
    source = v.decode_json(data)
    rows = parsed_codes(source)
    directory.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.cr-cantons-', dir=directory.parent) as temporary:
        output = Path(temporary) / 'output'
        output.mkdir()
        (output / 'source.json').write_bytes(data)
        (output / 'cantons.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        manifest = {'schema_version': 1, 'source_url': URL, 'publisher': source['publisher'],
            'retrieved_at': datetime.now(timezone.utc).isoformat(), 'http': headers,
            'source_version': source['version'], 'source_date': source['date'],
            'license': None,
            'licensing_note': 'Government-published administrative naming/code facts. Publisher conditions are not replaced by GeoNames CC BY or the repository code licence. No clinical or personal data are included.',
            'official_currentness_verified': False, 'geonames_crosswalk_verified': False,
            'files': {p.name: v.digest(p.read_bytes()) for p in output.iterdir()}}
        (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        v.require(not directory.exists(), 'government output appeared concurrently')
        output.rename(directory)
    return verify(root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('import', 'verify', 'query'))
    parser.add_argument('--code')
    parser.add_argument('--root', type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        report = import_once(args.root) if args.command == 'import' else verify(args.root)
        if args.command == 'query':
            rows = v.load_json(args.root / DIRECTORY, 'cantons.json')
            report['results'] = [r for r in rows if not args.code or r['code'] == args.code]
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(2, f'error: {exc}\n')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
