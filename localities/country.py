"""Offline country inspection, integrity checks and explicit-output restoration.

A source layer is not a unique address inventory. The adapters below are an
allowlist of existing validators; the catalog never supplies executable code.
"""
from __future__ import annotations

import contextlib
import csv
import gzip
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
KINDS = {'gazetteer_directory', 'country_archive', 'split_archive', 'official_overlay',
         'shared_records', 'address_format', 'reference_csv', 'source_snapshot'}
ADAPTERS = {'metadata_integrity', 'europe_replay', 'asia_archive_replay',
            'oceania_archive_integrity', 'official_integrity', 'shared_admin_selection',
            'profile_selection', 'reference_csv_integrity', 'western_asia_source_replay'}
MAX_ARCHIVE_BYTES = 100_000_000


def _json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _path(root, name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('invalid catalog path')
    rel = PurePosixPath(name)
    if rel.is_absolute() or any(p in {'', '.', '..'} for p in name.split('/')):
        raise ValueError('unsafe catalog path: ' + name)
    root = Path(root).resolve()
    current = root
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('symlink catalog path: ' + name)
    return current


def load_modules(root=ROOT):
    data = _json(Path(root) / 'countries/modules.json')
    if data.get('schema_version') != 1:
        raise ValueError('unsupported country module schema')
    return data


def _country(code, root):
    if not re.fullmatch(r'[A-Z]{2}', code or ''):
        raise ValueError('country must be an exact uppercase collection code')
    matches = [e for e in load_modules(root)['countries'] if e['code'] == code]
    if len(matches) != 1:
        raise ValueError('unknown or duplicate country: ' + code)
    return matches[0]


def validate_catalog(root=ROOT):
    root = Path(root)
    data = load_modules(root)
    original = _json(root / 'countries/catalog.json')
    countries = data.get('countries', [])
    codes = [e['code'] for e in countries]
    if len(codes) != len(set(codes)) or set(codes) != {e['code'] for e in original['countries']}:
        raise ValueError('semantic catalog scope differs from country inventory')
    registry_defs = data['registries']
    count = 0
    for definition in registry_defs.values():
        if not _path(root, definition['path']).is_dir():
            raise ValueError('missing registry directory')
        for field in ('source_refs', 'notice_refs', 'test_refs'):
            for name in definition[field]:
                if not _path(root, name).is_file():
                    raise ValueError('missing registry dependency: ' + name)
    for entry in countries:
        if not re.fullmatch(r'[A-Z]{2}', entry['code']) or not entry.get('next_action'):
            raise ValueError('invalid country entry')
        ids = [layer['id'] for layer in entry['layers']]
        if len(ids) != len(set(ids)):
            raise ValueError('duplicate country layer')
        for layer in entry['layers']:
            if layer['kind'] not in KINDS or layer['verifier'] not in ADAPTERS:
                raise ValueError('unknown country layer or verifier')
            if layer['registry'] not in registry_defs:
                raise ValueError('unknown layer registry')
            for field in ('data', 'metadata', 'manifest'):
                if field in layer and not _path(root, layer[field]).exists():
                    raise ValueError('missing country dependency: ' + layer[field])
            selector = layer['selector']
            selected = selector.get('country', selector.get('value', selector.get('key')))
            if selected != entry['code']:
                raise ValueError('country selector mismatch')
            if layer['kind'] == 'shared_records':
                values = _json(_path(root, layer['data']))[selector['collection']]
                if not any(row.get(selector['field']) == selector['value'] for row in values):
                    raise ValueError('shared country selector has no observations')
            if layer['kind'] == 'address_format':
                if selector['key'] not in _json(_path(root, layer['data']))[selector['collection']]:
                    raise ValueError('country format selector missing')
            count += 1
    return {'status': 'passed', 'countries': len(countries), 'source_layers': count,
            'scope': 'semantic dependency and selector integrity; no address accuracy claim'}


def _select_archive(layer, code, root):
    doc = _json(_path(root, layer['manifest']))
    if layer['kind'] == 'country_archive':
        rows = [e for e in doc['archives'] if e['country'] == code]
        if len(rows) != 1:
            raise ValueError('country archive selection failed')
        return rows[0]
    try:
        return doc['countries'][code]
    except KeyError as error:
        raise ValueError('split archive country missing') from error


def _verify_bytes(content, info, name):
    size = info.get('bytes', info.get('stored_bytes'))
    digest = info.get('sha256', info.get('stored_sha256'))
    if size is not None and len(content) != size:
        raise ValueError('size mismatch: ' + name)
    if digest and hashlib.sha256(content).hexdigest() != digest:
        raise ValueError('checksum mismatch: ' + name)


def _archive_bytes(layer, code, root):
    entry = _select_archive(layer, code, root)
    if layer['kind'] != 'country_archive':
        raise ValueError('not an Asia archive')
    base = _path(root, 'registries/asia')
    chunks = []
    for part in entry['parts']:
        content = _path(base, part['path']).read_bytes()
        _verify_bytes(content, part, part['path'])
        chunks.append(content)
    payload = b''.join(chunks)
    if len(payload) > MAX_ARCHIVE_BYTES:
        raise ValueError('country archive too large')
    _verify_bytes(payload, entry, code)
    return payload, entry


def _module(path, key):
    spec = importlib.util.spec_from_file_location('country_adapter_' + key, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _archive_metadata(layer, code, root):
    payload, entry = _archive_bytes(layer, code, root)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        name = code + '/metadata.json'
        if archive.namelist().count(name) != 1 or archive.getinfo(name).file_size > 5_000_000:
            raise ValueError('invalid archive metadata member')
        content = archive.read(name)
        _verify_bytes(content, entry['members'][name], name)
        return json.loads(content)


def _date_evidence(meta):
    result = {}
    for key in ('retrieved_at', 'retrieved_on', 'observed_on', 'created_on', 'as_of',
                'source_modified_min', 'source_modified_max', 'base_snapshot', 'curated_on'):
        if key in meta:
            result[key] = meta[key]
    source = meta.get('source_file')
    if isinstance(source, dict):
        result['source_file'] = {k: source[k] for k in ('retrieved_at', 'retrieved_on', 'last_modified', 'url') if k in source}
    if isinstance(meta.get('sources'), dict):
        result['sources'] = {k: {a: v[a] for a in ('published_on', 'source_observed_on', 'as_of', 'reference_month') if a in v}
                             for k, v in meta['sources'].items() if isinstance(v, dict)}
    return result


def inspect_country(code, root=ROOT):
    root = Path(root)
    country = _country(code, root)
    definitions = load_modules(root)['registries']
    reports = []
    for layer in country['layers']:
        definition = definitions[layer['registry']]
        report = dict(layer)
        report.update(source_refs=definition['source_refs'], notice_refs=definition['notice_refs'],
                      test_refs=definition['test_refs'])
        meta = {}
        if layer.get('metadata'):
            meta = _json(_path(root, layer['metadata']))
        elif layer['kind'] == 'country_archive':
            meta = _archive_metadata(layer, code, root)
        elif layer['kind'] == 'split_archive':
            meta = _select_archive(layer, code, root)
        elif layer['kind'] == 'shared_records':
            shared = _json(_path(root, layer['data']))
            selector = layer['selector']
            rows = [e for e in shared[selector['collection']] if e.get(selector['field']) == code]
            report['selected_observations'] = len(rows)
            meta = shared
        report['counts'] = meta.get('counts', {})
        report['source_dates'] = _date_evidence(meta)
        report['known_issues'] = meta.get('known_issues', [])
        if layer['verifier'] == 'western_asia_source_replay':
            sources = _json(_path(root, layer['manifest']))
            selected = [s for s in sources['sources'] if s['country'] == code]
            report['counts'] = {'source_records': sum(s['normalized']['records'] for s in selected),
                                'acquired_original_files': sum('original' in s for s in selected),
                                'reused_community_snapshots': sum('repository_files' in s for s in selected)}
            report['source_dates'] = {'reviewed_at': sources['reviewed_at']}
            report['source_refs'] = [layer['manifest']]
            report['notice_refs'] = [layer['data'] + '/NOTICE.md']
            status = _json(_path(root, layer['data'] + '/country-status.json'))
            report['known_issues'] = [next(c['remaining_work_ja'] for c in status['countries'] if c['country'] == code)]
        if layer['kind'] == 'reference_csv':
            source_layer = layer['selector']['source_layer']
            source = meta.get('sources', {}).get(source_layer)
            if not source:
                raise ValueError('referenced boundary layer missing provenance')
            report['counts'] = {'records': source['rows']}
            report['source_dates'] = {'vintage_year': source['vintage_year']}
            report['known_issues'] = [meta.get('caveat', 'historical boundary reference only')]
        if layer['kind'] == 'official_overlay':
            report['recorded_quality'] = {k: v for k, v in meta.items() if k not in {'files', 'columns', 'country'}}
            sourcepath = _path(root, layer['data'] + '/sources.json')
            if sourcepath.is_file():
                report['source_dates'].update(_date_evidence(_json(sourcepath)))
        report['freshness_verified'] = None
        report['national_completeness_verified'] = False
        report['deliverability_verified'] = False
        reports.append(report)
    bundle_evidence = None
    if country.get('local_bundle_evidence'):
        record = _json(_path(root, country['local_bundle_evidence']))
        if record.get('country') != code:
            raise ValueError('bundle evidence country mismatch')
        bundle_evidence = {key: record[key] for key in
            ('status', 'source_commit', 'payload_file_count', 'bundle_sha256', 'public_release')}
        bundle_evidence['record'] = country['local_bundle_evidence']
    return {'country': code, 'name': country['name'], 'inventory_state': country['inventory_state'],
            'next_action': country['next_action'], 'layers': reports,
            'local_bundle_evidence': bundle_evidence,
            'counts_policy': 'per-source layer counts; do not sum overlapping sources or call them unique addresses',
            'freshness_verified': None, 'national_completeness_verified': False,
            'deliverability_verified': False}


def _managed_bytes(registry, relative):
    path = _path(registry, relative)
    if path.is_file():
        return path.read_bytes()
    split = registry / 'split_manifest.json'
    if split.is_file():
        entries = [e for e in _json(split)['files'] if e['path'] == relative]
        if len(entries) == 1:
            entry = entries[0]
            chunks = []
            for part in entry['parts']:
                content = _path(registry, part['path']).read_bytes()
                _verify_bytes(content, part, part['path'])
                chunks.append(content)
            content = b''.join(chunks)
            _verify_bytes(content, entry, relative)
            return content
    raise ValueError('missing source data: ' + relative)


def _directory_integrity(layer, code, root):
    folder = _path(root, layer['data'])
    registry = _path(root, 'registries/' + layer['registry'])
    meta = _json(_path(root, layer['metadata']))
    manifest = registry / 'manifest.json'
    if manifest.is_file():
        matches = [e for e in _json(manifest).get('countries', []) if e.get('country') == code]
        if len(matches) == 1 and matches[0].get('metadata_sha256'):
            _verify_bytes(_path(root, layer['metadata']).read_bytes(),
                          {'sha256': matches[0]['metadata_sha256']}, layer['metadata'])
    recorded_country = meta.get('country')
    if isinstance(recorded_country, dict):
        recorded_country = recorded_country.get('country')
    if recorded_country != code:
        raise ValueError('metadata country differs from selected country')
    checked = 0
    for section in ('files', 'auxiliary_files', 'preview_files'):
        for name, info in meta.get(section, {}).items():
            relative = (folder / name).relative_to(registry).as_posix()
            payload = _managed_bytes(registry, relative)
            _verify_bytes(payload, info, relative)
            if info.get('uncompressed_sha256'):
                plain = gzip.decompress(payload) if name.endswith('.gz') else payload
                if hashlib.sha256(plain).hexdigest() != info['uncompressed_sha256']:
                    raise ValueError('uncompressed checksum mismatch: ' + relative)
            checked += 1
    if checked == 0:
        raise ValueError('metadata declares no data checksums')
    return checked


def _official_integrity(layer, root):
    folder = _path(root, layer['data'])
    if (folder / 'coverage.json').is_file():
        meta = _json(folder / 'coverage.json')
        specs = dict(meta['files'])
        sources = _json(folder / 'sources.json')
        specs.update(sources.get('bundled_files', {}))
    else:
        meta = _json(folder / 'manifest.json')
        specs = {name: {'sha256': digest} for name, digest in meta['sha256'].items()}
    for name, info in specs.items():
        _verify_bytes(_path(folder, name).read_bytes(), info, name)
    if not specs:
        raise ValueError('official layer has no pinned files')
    return len(specs)


def _verify_layer(layer, code, root):
    adapter = layer['verifier']
    if not __debug__ and adapter in {'asia_archive_replay', 'europe_replay'}:
        raise ValueError('country replay requires Python assertions enabled')
    result = {'id': layer['id'], 'adapter': adapter, 'inventory_integrity': 'passed',
              'source_integrity': 'not_checked', 'row_integrity': 'not_checked'}
    if adapter == 'profile_selection':
        selector = layer['selector']
        if selector['key'] not in _json(_path(root, layer['data']))[selector['collection']]:
            raise ValueError('missing country format profile')
        result['scope'] = 'format profile exists; address existence not checked'
    elif adapter == 'shared_admin_selection':
        selector = layer['selector']
        doc = _json(_path(root, layer['data']))
        rows = [e for e in doc[selector['collection']] if e.get(selector['field']) == code]
        if not rows or any(e.get('evidence_id') not in doc['source_evidence'] for e in rows):
            raise ValueError('missing selected administrative observations or evidence')
        result.update(selected_observations=len(rows), row_integrity='selected_evidence_references_passed',
                      scope='partial administrative naming observations only')
    elif adapter == 'asia_archive_replay':
        entry = _select_archive(layer, code, root)
        registry = _path(root, 'registries/asia')
        package = _module(registry / 'package.py', 'asia_package')
        build = _module(registry / 'build.py', 'asia_build')
        with tempfile.TemporaryDirectory(prefix='country-verify-') as temporary:
            target = Path(temporary)
            # Original verifier writes its report; this only occurs in the temporary tree.
            package.unpack_record(entry, root=registry, destination_root=target / 'countries')
            shutil.copyfile(registry / 'scope.json', target / 'scope.json')
            with contextlib.redirect_stdout(io.StringIO()):
                report = build.verify(target, country=code)
        result.update(source_integrity='passed', row_integrity='passed', rows=report['rows'],
                      scope='original Asia archive/member hashes and deterministic country replay')
    elif adapter in {'metadata_integrity', 'europe_replay'}:
        checked = _directory_integrity(layer, code, root)
        result.update(source_integrity='passed', checked_files=checked,
                      scope='pinned derived file hashes; live upstream not contacted')
        if adapter == 'europe_replay':
            build = _module(_path(root, 'registries/europe/build.py'), 'europe_build')
            report = build.verify_country(_path(root, 'registries/europe'), code)
            result.update(row_integrity='passed', rows=report['rows'], scope='original Europe deterministic country replay')
    elif adapter == 'reference_csv_integrity':
        if layer['kind'] != 'reference_csv':
            raise ValueError('reference_csv_integrity requires reference_csv kind')
        source_layer = layer['selector']['source_layer']
        meta = _json(_path(root, layer['metadata']))
        info = meta.get('sources', {}).get(source_layer)
        expected_country = {'KE': 'KEN', 'GH': 'GHA'}.get(code)
        if not info or not expected_country or not source_layer.startswith(expected_country + '-ADM'):
            raise ValueError('invalid official boundary source selection')
        payload = _path(root, layer['data']).read_bytes()
        _verify_bytes(payload, {'bytes': info['derived_csv_bytes'],
                                'sha256': info['derived_csv_sha256']}, layer['data'])
        data = list(csv.DictReader(io.StringIO(payload.decode('utf-8-sig'))))
        if len(data) != info['rows'] or len({r['boundary_shape_id'] for r in data}) != len(data):
            raise ValueError('boundary CSV count or source IDs mismatch')
        if any(r['country'] != expected_country or r['admin_level'] != source_layer.split('-')[1]
               or r['source_sha256'] != info['sha256'] for r in data):
            raise ValueError('boundary CSV source identity mismatch')
        result.update(source_integrity='passed', row_integrity='passed', rows=len(data),
                      scope='SHA-pinned, dated administrative source names and spatial associations; not current legal parent IDs or deliverability')
    elif adapter == 'official_integrity':
        result.update(source_integrity='passed', checked_files=_official_integrity(layer, root),
                      scope='official layer pinned file hashes; postcode/authority accuracy is separate')
    elif adapter == 'western_asia_source_replay':
        from scripts.western_asia_sources import verify_sources
        report = verify_sources(_path(root, layer['data']), country=code)
        result.update(source_integrity='passed', row_integrity='passed', rows=report['records'],
                      acquired_original_files=report['acquired_original_files'],
                      reused_community_snapshots=report['reused_community_snapshots'],
                      scope='selected country only: pinned raw-source replay and normalized rows; government, humanitarian and third-party sources remain distinct')
    elif adapter == 'oceania_archive_integrity':
        entry = _select_archive(layer, code, root)
        registry = _path(root, 'registries/oceania')
        module = _module(registry / 'addresskit/region_names.py', 'oceania_names')
        with module.open_split_archive(registry, entry) as archive:
            if set(archive.namelist()) != set(entry['members']):
                raise ValueError('Oceania member list mismatch')
            for name, info in entry['members'].items():
                _verify_bytes(archive.read(name), info, name)
        result.update(source_integrity='passed', scope='country archive parts/members only; regional row validation is separate')
    else:
        raise ValueError('verifier adapter is not allowed')
    return result


def verify_country(code, root=ROOT):
    root = Path(root)
    entry = _country(code, root)
    reports = []
    for layer in entry['layers']:
        try:
            report = _verify_layer(layer, code, root)
            report['status'] = 'passed'
        except (OSError, ValueError, KeyError, AssertionError, zipfile.BadZipFile) as error:
            report = {'id': layer['id'], 'status': 'failed', 'error': str(error)}
        reports.append(report)
    observations = [r for r, layer in zip(reports, entry['layers']) if layer['kind'] != 'address_format']
    if any(r['status'] == 'failed' for r in reports):
        status = 'failed'
    elif not observations:
        status = 'unsupported'
    else:
        status = 'passed'
    return {'country': code, 'status': status, 'layers': reports,
            'scope': 'only the explicitly reported integrity checks; not address accuracy, freshness or national completeness',
            'freshness_verified': None, 'national_completeness_verified': False, 'deliverability_verified': False}


def restore_country(code, output, root=ROOT):
    """Restore selected country data into a new explicit output; never change sources."""
    root = Path(root).resolve()
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('restore output must not already exist')
    for parent in [output.parent, *output.parents]:
        if parent.is_symlink():
            raise ValueError('restore output has a symlink parent')
    resolved = output.resolve()
    if resolved.is_relative_to(root) or root.is_relative_to(resolved):
        raise ValueError('restore output must be outside the source repository')
    verification = verify_country(code, root)
    if verification['status'] != 'passed':
        raise ValueError('country has failed or unsupported verification')
    modules = load_modules(root)
    entry = _country(code, root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.country-restore-', dir=output.parent) as temporary:
        stage = Path(temporary) / 'data'
        stage.mkdir()
        copied = set()
        def copy(name):
            source = _path(root, name)
            if not source.is_file():
                return
            destination = _path(stage, name)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            copied.add(name)
        for layer in entry['layers']:
            definition = modules['registries'][layer['registry']]
            for name in definition['source_refs'] + definition['notice_refs']:
                copy(name)
            if layer.get('metadata'):
                copy(layer['metadata'])
            if layer['kind'] == 'country_archive':
                registry = _path(root, 'registries/asia')
                package = _module(registry / 'package.py', 'restore_asia_package')
                archive_entry = _select_archive(layer, code, root)
                package.unpack_record(archive_entry, root=registry,
                    destination_root=stage / 'registries/asia/countries')
                for part in archive_entry['parts']:
                    copy('registries/asia/' + part['path'])
            elif layer['kind'] in {'gazetteer_directory', 'official_overlay'}:
                folder = _path(root, layer['data'])
                for path in folder.rglob('*'):
                    if path.is_file() and not path.is_symlink() and '__pycache__' not in path.parts:
                        copy(path.relative_to(root).as_posix())
                if layer['kind'] == 'gazetteer_directory':
                    registry = _path(root, 'registries/' + layer['registry'])
                    meta = _json(_path(root, layer['metadata']))
                    for section in ('files', 'auxiliary_files', 'preview_files'):
                        for name in meta.get(section, {}):
                            relative = (folder / name).relative_to(registry).as_posix()
                            target = _path(stage, layer['data'] + '/' + name)
                            if not target.exists():
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_bytes(_managed_bytes(registry, relative))
                                copied.add(target.relative_to(stage).as_posix())
            elif layer['kind'] == 'split_archive':
                archive_entry = _select_archive(layer, code, root)
                for part in archive_entry['parts']:
                    copy('registries/oceania/' + part['path'])
            elif layer['kind'] == 'source_snapshot':
                folder = layer['data']
                sources = _json(_path(root, layer['manifest']))
                copy(layer['manifest'])
                copy(folder + '/NOTICE.md')
                copy(folder + '/country-status.json')
                for source in sources['sources']:
                    if source['country'] != code:
                        continue
                    for field in ('original', 'normalized', 'catalogue_evidence'):
                        if source.get(field):
                            copy(folder + '/' + source[field]['path'])
                    for item in source.get('repository_files', []):
                        copy(item['path'])
            else:
                copy(layer['data'])
        evidence = {'country': code, 'verification': verification,
                    'scope': 'selected country source data and shared notices; not a standalone application or published dataset'}
        (stage / 'COUNTRY-RESTORE.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
        # Reserve the destination exclusively, then use exclusive file creation.
        # An output created after the initial check is never replaced.
        output.mkdir()
        for source in sorted(stage.rglob('*')):
            destination = output / source.relative_to(stage)
            if source.is_dir():
                destination.mkdir()
            else:
                with source.open('rb') as reader, destination.open('xb') as writer:
                    shutil.copyfileobj(reader, writer)
    return {'country': code, 'status': 'passed', 'output': str(output),
            'scope': 'selected data restored; source repository unchanged'}


def add_cli(commands):
    command = commands.add_parser('country', help='offline country inspection, verification and explicit-output restoration')
    sub = command.add_subparsers(dest='country_command', required=True)
    sub.add_parser('validate-catalog')
    for name in ('inspect', 'verify', 'restore'):
        item = sub.add_parser(name)
        item.add_argument('--country', required=True)
        if name == 'restore':
            item.add_argument('--output', type=Path, required=True)


def run_cli(args):
    if args.country_command == 'validate-catalog':
        return validate_catalog()
    if args.country_command == 'inspect':
        return inspect_country(args.country)
    if args.country_command == 'restore':
        return restore_country(args.country, args.output)
    return verify_country(args.country)
