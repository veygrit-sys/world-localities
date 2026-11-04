#!/usr/bin/env python3
"""Snapshot source-tagged place names and country address templates."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen
import zipfile

COUNTRIES = 'AS AU CC CK CX FJ FM GU HM KI MH MP NC NF NR NU NZ PF PG PN PW SB TK TO TV UM VU WF WS'.split()


def download(root, kind, cc):
    if kind == 'alternatenames':
        url = f'https://download.geonames.org/export/dump/alternatenames/{cc}.zip'
        path = root / kind / (cc + '.zip')
    else:
        url = 'https://chromium-i18n.appspot.com/ssl-address/data/' + cc
        path = root / kind / (cc + '.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    meta_path = path.with_name(path.name + '.download.json')
    if path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if hashlib.sha256(path.read_bytes()).hexdigest() == meta['sha256']:
            return {'file': str(path.relative_to(root)), 'cached': True}
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers={'User-Agent': 'WorldAddress-Oceania/1.1'}), timeout=45) as response:
                data = response.read()
                meta = {'url': url, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                        'last_modified': response.headers.get('Last-Modified'),
                        'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
            temp = path.with_suffix(path.suffix + '.part')
            temp.write_bytes(data)
            if kind == 'alternatenames':
                with zipfile.ZipFile(temp) as archive:
                    if cc + '.txt' not in archive.namelist() or archive.testzip():
                        raise ValueError('invalid alternate-name archive')
            else:
                record = json.loads(data)
                if record.get('id') != 'data/' + cc:
                    raise ValueError('unexpected address metadata identifier')
            temp.replace(path)
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n')
            return {'file': str(path.relative_to(root)), 'bytes': len(data)}
        except Exception as error:
            if attempt == 2:
                return {'file': str(path.relative_to(root)), 'error': str(error)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, required=True)
    args = parser.parse_args()
    jobs = [('alternatenames', cc) for cc in COUNTRIES]
    jobs += [('address-templates', cc) for cc in COUNTRIES + ['ZZ']]
    errors = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        for future in as_completed([executor.submit(download, args.cache, *job) for job in jobs]):
            result = future.result()
            print(json.dumps(result), flush=True)
            if 'error' in result:
                errors.append(result)
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
