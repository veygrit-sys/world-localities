#!/usr/bin/env python3
"""Reconstruct only two pinned HK data files; preserve reviewed seed metadata."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SEED = ROOT / 'registries/official/expansions/HK'
URL = 'https://www.als.gov.hk/data/ALS-GeoJSON.zip'
SOURCE_SHA256 = '4549e4f774224abdef062cb6ffaa7e75f0d8dc02187a64bc6c05434472b6f577'
SOURCE_BYTES = 20_777_483
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024
DATA_FILES = ('records.csv.gz', 'sources/ALS-GeoJSON.zip')
SMALL_FILES = ('coverage.json', 'sources.json', 'sources/als-geojson.schema.json', 'sources/data-gov-hk-terms.html')


def require(value, message):
    if not value:
        raise ValueError(message)


def receipt(path):
    digest = hashlib.sha256()
    count = 0
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
            count += len(chunk)
    return {'bytes': count, 'sha256': digest.hexdigest()}


def check(path, expected):
    require(not Path(path).is_symlink(), f'Symlinks are not accepted: {path}')
    actual = receipt(path)
    require(all(actual[key] == expected[key] for key in ('bytes', 'sha256')), f'Pinned byte receipt mismatch: {path}')


def download(path):
    # An ordinary HTTPS GET only; use inherited networking and TLS verification.
    with urllib.request.urlopen(URL, timeout=120) as response, path.open('xb') as target:
        require(response.geturl() == URL, 'Unexpected source redirect')
        count = 0
        for chunk in iter(lambda: response.read(1024 * 1024), b''):
            count += len(chunk)
            require(count <= MAX_DOWNLOAD_BYTES, 'Official download exceeds size ceiling')
            target.write(chunk)


def materialize(source=None, output=None, seed=SEED):
    seed = Path(seed)
    snapshots = {name: (seed / name).read_bytes() for name in SMALL_FILES}
    coverage = json.loads(snapshots['coverage.json'])
    sources = json.loads(snapshots['sources.json'])
    source_spec = sources['sources']['hk-dpo-als-district-2d']
    require(source_spec['url'] == URL, 'Seed official URL differs from approved source')
    require(source_spec['source_sha256'] == SOURCE_SHA256 and source_spec['source_bytes'] == SOURCE_BYTES, 'Seed source pin differs from approved bytes')
    pins = dict(sources['bundled_files'])
    for name, spec in coverage['files'].items():
        if name in pins:
            require(all(pins[name][key] == spec[key] for key in ('bytes', 'sha256')), 'Seed receipt conflict')
        pins[name] = spec
    require(all(name in pins for name in DATA_FILES), 'Both data file receipts are required')
    require(pins[DATA_FILES[1]]['sha256'] == SOURCE_SHA256 and pins[DATA_FILES[1]]['bytes'] == SOURCE_BYTES, 'ZIP receipt is not approved')
    for name in SMALL_FILES[2:]:
        check(seed / name, pins[name])
    destination = Path(output) if output is not None else seed
    require(output is None or not destination.exists(), 'Proof output must be a new directory')
    if source is not None:
        check(Path(source), {'bytes': SOURCE_BYTES, 'sha256': SOURCE_SHA256})
    # Reject existing conflicting files before doing any target writes.
    for name in DATA_FILES:
        if (destination / name).exists() or (destination / name).is_symlink():
            check(destination / name, pins[name])
    spec = importlib.util.spec_from_file_location('hk_pinned_importer', ROOT / 'scripts/import_hk_official.py')
    importer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(importer)
    with tempfile.TemporaryDirectory(prefix='hk-materialize-') as temporary:
        staging = Path(temporary)
        archive = Path(source) if source is not None else staging / 'ALS-GeoJSON.zip'
        if source is None:
            download(archive)
        check(archive, {'bytes': SOURCE_BYTES, 'sha256': SOURCE_SHA256})
        generated = staging / 'generated'
        retrieved = sources.get('retrieved_at', source_spec.get('retrieved_at'))
        require(isinstance(retrieved, str) and retrieved, 'Seed retrieval observation missing')
        importer.build(archive, generated,
                       schema=seed / SMALL_FILES[2], terms=seed / SMALL_FILES[3],
                       retrieved_at=retrieved)
        for name in DATA_FILES:
            check(generated / name, pins[name])
        # Verification uses exact reviewed metadata, never freshly generated claims.
        for name, original in snapshots.items():
            (generated / name).write_bytes(original)
        report = importer.verify(generated)
        require(report.get('status') == 'passed', 'HK verification did not pass')
        require(report.get('source_replay') == 'passed_all_selected_district_2d_source_rows', 'Full original-source replay is required')
        require(report.get('rows') == coverage['rows'], 'Seed row count mismatch')
        destination.mkdir(parents=True, exist_ok=True)
        installed = []
        for name in DATA_FILES:
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                check(target, pins[name])
                continue
            with (generated / name).open('rb') as stream, target.open('xb') as out:
                shutil.copyfileobj(stream, out)
            check(target, pins[name])
            installed.append(name)
        if output is not None:
            for name, original in snapshots.items():
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as out:
                    out.write(original)
        require(all((seed / name).read_bytes() == original for name, original in snapshots.items()), 'Seed metadata changed during materialization')
        return {'country': 'HK', 'status': 'passed', 'source_sha256': SOURCE_SHA256,
                'rows': report['rows'], 'source_replay': report['source_replay'],
                'installed_files': installed, 'destination': str(destination),
                'seed_metadata': 'preserved_byte_identical',
                'scope': 'two pinned local data files; no upstream freshness or completeness claim'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Use an existing pinned archive instead of downloading')
    parser.add_argument('--output', type=Path, help='Create a separate proof directory instead of installing seed data')
    args = parser.parse_args()
    print(json.dumps(materialize(args.source, args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
