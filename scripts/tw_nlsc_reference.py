"""Preserve NLSC code replies and their explicit request-parent bindings."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from east_asia_sources import canonical, request, safe_path, file_hash

API = 'https://api.nlsc.gov.tw/other/'


def parse(data, level):
    if len(data) > 4 * 1024 * 1024 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Oversized or unsafe XML')
    root = ET.fromstring(data)
    schema = {'county': ('countyItems', 'countyItem', ['countycode', 'countyname', 'countycode01']),
              'town': ('townItems', 'townItem', ['towncode', 'towncode01', 'townname']),
              'village': ('villages', 'village', ['villageId', 'villageName'])}
    root_name, row_name, columns = schema[level]
    if root.tag != root_name: raise ValueError('NLSC response schema differs')
    result = []
    for item in root:
        if item.tag != row_name or [x.tag for x in item] != columns: raise ValueError('NLSC fields differ')
        row = {field.tag: field.text or '' for field in item}
        if not row[columns[0]]: raise ValueError('Missing source code')
        result.append(row)
    return result


def acquire(root, resume_incomplete=False):
    root = Path(root)
    if root.exists() and (not resume_incomplete or (root / 'source-manifest.json').exists()):
        raise ValueError('Use a new NLSC snapshot directory or explicitly resume an incomplete cache')
    (root / 'responses').mkdir(parents=True, exist_ok=True)
    def fetch(job):
        level, suffix, parent = job
        name = suffix.replace('/', '_') + '.xml'
        path = root / 'responses' / name
        cached = path.exists()
        if cached:
            data = path.read_bytes()
        else:
            with request(API + suffix) as response: data = response.read(4 * 1024 * 1024 + 1)
            parse(data, level)
            path.write_bytes(data)
        rows = parse(data, level)
        pin = {'level': level, 'url': API + suffix, 'path': 'responses/' + name,
               'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
               'parent_id': parent,
               'retrieved_at': None if cached else datetime.now(timezone.utc).isoformat(),
               'reused_incomplete_reply_cache': cached}
        return pin, rows
    first, counties = fetch(('county', 'ListCounty', None)); pins = [first]
    with ThreadPoolExecutor(max_workers=4) as pool:
        towns = list(pool.map(fetch, [('town', 'ListTown1/' + row['countycode'], 'county:' + row['countycode']) for row in counties]))
        pins.extend(pin for pin, _ in towns)
        jobs = []
        for pin, rows in towns:
            county = pin['parent_id'].split(':', 1)[1]
            jobs.extend(('village', 'ListVillage/' + county + '/' + row['towncode01'], 'town:' + row['towncode']) for row in rows)
        for i, (pin, _) in enumerate(pool.map(fetch, jobs), 1):
            pins.append(pin)
            if i % 50 == 0: print('Village replies:', i, flush=True)
    manifest = {'source_id': 'TW-NLSC', 'licence': 'OGDL-1.0', 'responses': pins,
                'legal_effective_date': None, 'atomic_snapshot': False, 'national_completeness_verified': False}
    (root / 'source-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return build(root, manifest)


def build(root, manifest):
    root = Path(root); records = []; seen = set(); counts = Counter()
    for pin in manifest['responses']:
        path = safe_path(root, pin['path'])
        if path.stat().st_size != pin['bytes'] or file_hash(path) != pin['sha256']: raise ValueError('XML source changed')
        level = pin['level']
        for raw in parse(path.read_bytes(), level):
            codekey, namekey = {'county': ('countycode', 'countyname'), 'town': ('towncode', 'townname'), 'village': ('villageId', 'villageName')}[level]
            identity = level + ':' + raw[codekey]
            if identity in seen: raise ValueError('Duplicate source-qualified code')
            seen.add(identity)
            named = bool(raw[namekey].strip())
            record = {'id': identity, 'source_namespace': 'TW-NLSC', 'level': level,
                      'parent_id': pin['parent_id'], 'raw': raw,
                      'record_kind': level + '_reference' if named else 'unnamed_api_reference',
                      'name_status': 'supplied' if named else 'not_supplied', 'source_response': pin['path']}
            records.append(record); counts[level] += 1
            if not named: counts['unnamed_' + level] += 1
    for row in records:
        if row['parent_id'] and row['parent_id'] not in seen: raise ValueError('Missing explicit request parent')
    expected = {None: 1}
    for row in records:
        if row['level'] in ('county', 'town'): expected[row['id']] = 1
    actual = Counter(pin['parent_id'] for pin in manifest['responses'])
    if actual != expected: raise ValueError('Missing or repeated API request coverage')
    lines = ''.join(canonical(row) + '\n' for row in records)
    return {'schema_version': 1, 'counts': dict(counts), 'observations': len(records),
            'ordered_rows_sha256': hashlib.sha256(lines.encode()).hexdigest(), 'records': records,
            'parent_assignment': 'original API request binding; no prefix inference', 'orphans': 0,
            'national_completeness_verified': False, 'legal_effective_date': None, 'atomic_snapshot': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['acquire', 'audit', 'replay', 'search', 'parents'])
    parser.add_argument('--data-root', type=Path, required=True); parser.add_argument('--id')
    parser.add_argument('--text', default=''); parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume-incomplete', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'acquire': result = acquire(args.data_root, args.resume_incomplete)
        else:
            manifest = json.loads((args.data_root / 'source-manifest.json').read_text())
            result = build(args.data_root, manifest)
            if args.command == 'replay':
                accepted = json.loads((args.data_root / 'audit.json').read_text())
                if result != accepted: raise ValueError('Full XML replay differs')
                result = {'status': 'PASS', 'responses': len(manifest['responses']), 'observations': result['observations'], 'ordered_rows_sha256': result['ordered_rows_sha256']}
            elif args.command == 'search':
                if not 1 <= args.limit <= 100: raise ValueError('Limit must be 1..100')
                result = {'results': [r for r in result['records'] if (not args.id or r['id'] == args.id) and args.text in canonical(r['raw'])][:args.limit]}
            elif args.command == 'parents':
                index = {r['id']: r for r in result['records']}; chain = []; row = index.get(args.id)
                if row is None: raise ValueError('Unknown source-qualified ID')
                while row:
                    chain.append(row); row = index.get(row['parent_id'])
                result = {'chain': chain, 'parent_assignment': 'original API request binding'}
        text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.output: args.output.write_text(text)
        else: print(text, end='')
    except (OSError, ValueError, KeyError, ET.ParseError) as exc: parser.exit(2, str(exc) + '\n')


if __name__ == '__main__': main()
