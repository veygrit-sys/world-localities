"""ID-preserving place-label selection, postal evidence, and country formatting.

Source names are selected, never translated by splitting or reversing strings.
Run ``python -m addresskit.region_names --help`` for the standalone pack CLI.
"""
import argparse
import base64
from collections import defaultdict
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata
import zipfile


MODES = {'local', 'international_english', 'domestic_english'}
FIELDS = {'N': 'recipient', 'O': 'organization', 'A': 'address_lines',
          'D': 'dependent_locality', 'C': 'locality', 'S': 'administrative_area',
          'Z': 'postal_code', 'X': 'sorting_code'}


def language_tag(value):
    return value.replace('_', '-').lower()


def name_key(value):
    # Keep accents and macrons; a loose search match must not become an ID join.
    return ' '.join(unicodedata.normalize('NFC', value).casefold().split())


def postal_key(value):
    if not isinstance(value, str):
        raise TypeError('postal_code must be a string (leading zeros matter)')
    return ' '.join(unicodedata.normalize('NFC', value).upper().split())


def open_split_archive(root, entry):
    """Read only the listed parts, rejecting corruption and paths outside root."""
    root = Path(root).resolve()
    parts = []
    for part in entry['parts']:
        path = (root / part['path']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('archive part escapes pack directory')
        content = path.read_bytes()
        if part.get('storage_encoding') == 'base64':
            if len(content) != part['stored_bytes'] or hashlib.sha256(content).hexdigest() != part['stored_sha256']:
                raise ValueError('encoded archive part checksum mismatch: ' + part['path'])
            content = base64.b64decode(content.strip(), validate=True)
        elif part.get('storage_encoding', 'raw') != 'raw':
            raise ValueError('unsupported archive part encoding')
        if len(content) != part['bytes'] or hashlib.sha256(content).hexdigest() != part['sha256']:
            raise ValueError('archive part checksum mismatch: ' + part['path'])
        parts.append(content)
    content = b''.join(parts)
    if len(content) != entry['archive_bytes'] or hashlib.sha256(content).hexdigest() != entry['archive_sha256']:
        raise ValueError('combined archive checksum mismatch')
    return zipfile.ZipFile(io.BytesIO(content))


def current_name(row):
    if row.get('historic'):
        return False
    for field in ('valid_from', 'valid_to'):
        value = row.get(field, '')
        if not value:
            continue
        if not re.fullmatch(r'\d{4}(-\d{2})?(-\d{2})?', value):
            return False  # Retain uninterpretable periods for review, not selection.
        try:
            parts = list(map(int, value.split('-')))
            boundary = date(*(parts + [1] * (3 - len(parts))))
            if field == 'valid_from' and boundary > date.today():
                return False
            # A partial end date includes the entire indicated month or year.
            if field == 'valid_to' and date.today().isoformat()[:len(value)] > value:
                return False
        except ValueError:
            return False
    return True


def choose_label(entity, labels, *, locale, usage='local'):
    """Return an auditable label and fallback status without changing the ID."""
    if usage not in MODES:
        raise ValueError('unknown usage: ' + usage)
    wanted = language_tag(locale)
    generic = wanted.split('-')[0]
    languages = list(dict.fromkeys([wanted, generic]))
    candidates = []
    for row in labels:
        if not current_name(row) or row.get('colloquial'):
            continue
        lang = language_tag(row.get('language', 'und'))
        context = row.get('usage', 'generic')
        if lang not in languages or context not in ('generic', usage):
            continue
        quality = {'verified': 0, 'source_attested': 1, 'reviewed_transliteration': 2, 'generated': 3}
        rank = (quality.get(row.get('status', 'source_attested'), 4),
                languages.index(lang), context != usage, not row.get('preferred', False),
                bool(row.get('short', False)))
        candidates.append((rank, row))
    if candidates:
        best_rank = min(rank for rank, _ in candidates)
        best = sorted((row for rank, row in candidates if rank == best_rank),
                      key=lambda r: (name_key(r['text']), r['text'], r['id']))
        row = best[0]
        actual = language_tag(row['language'])
        texts = sorted({r['text'] for r in best})
        return {'entity_id': entity['id'], 'text': row['text'],
                'requested_language': wanted, 'language': actual,
                'requested_usage': usage, 'usage': row.get('usage', 'generic'),
                'language_match': actual == wanted,
                'usage_match': row.get('usage') == usage,
                'fallback': actual != wanted or row.get('usage') != usage,
                'ambiguous_label': len(texts) > 1, 'alternatives': texts,
                'label_id': row['id'], 'source': row.get('source'),
                'status': row.get('status', 'source_attested')}
    return {'entity_id': entity['id'], 'text': entity['name'],
            'requested_language': wanted, 'language': entity.get('name_language', 'und'),
            'requested_usage': usage, 'usage': 'unclassified',
            'language_match': False, 'usage_match': False, 'fallback': True,
            'ambiguous_label': False, 'alternatives': [], 'label_id': None,
            'source': entity.get('source', 'GeoNames'), 'status': 'untranslated_fallback'}


class RegionCatalog:
    """Many names and postal relations per entity; no name-based ID replacement."""

    def __init__(self, entities, names, postal_links, profiles):
        self.entities = {}
        for entity in entities:
            if entity['id'] in self.entities:
                raise ValueError('duplicate entity ID: ' + entity['id'])
            self.entities[entity['id']] = entity
        self.profiles = profiles
        self.names = defaultdict(list)
        self.postal = defaultdict(list)
        self.search_index = defaultdict(set)
        for row in names:
            if row['entity_id'] not in self.entities:
                raise ValueError('orphan name: ' + row['id'])
            self.names[row['entity_id']].append(row)
            if current_name(row):
                cc = self.entities[row['entity_id']]['country_code']
                self.search_index[(cc, name_key(row['text']))].add(row['entity_id'])
        for entity in self.entities.values():
            self.search_index[(entity['country_code'], name_key(entity['name']))].add(entity['id'])
        for row in postal_links:
            entity = self.entities.get(row['entity_id'])
            if entity is None or entity['country_code'] != row['country_code']:
                raise ValueError('postal link has missing or cross-country entity')
            if current_name(row) and entity.get('kind') not in ('historical_administrative_area', 'noncurrent_populated_place'):
                self.postal[(row['country_code'], postal_key(row['postal_code']))].append(row)

    @classmethod
    def from_pack(cls, root, country=None):
        root = Path(root)
        entities = []
        if (root / 'pack_manifest.json').exists():
            manifest = json.loads((root / 'pack_manifest.json').read_text())
            countries = json.loads((root / 'countries.json').read_text())
            countries = [c for c in countries if country is None or c['country_code'] == country.upper()]
            if not countries:
                raise ValueError('country is not in this pack')
            names, links = [], []
            for c in countries:
                entities.append({'id': c['id'], 'country_code': c['country_code'],
                                 'name': c['name_en'], 'name_language': 'en',
                                 'kind': 'country', 'parent_id': None, 'source': 'UN M49'})
                entry = manifest['countries'][c['country_code']]
                with open_split_archive(root, entry) as archive:
                    for destination, member in [(entities, entry['places_member']),
                                                (names, 'locale/names.jsonl'),
                                                (links, 'locale/postal_links.jsonl')]:
                        destination.extend(json.loads(line) for line in archive.read(member).decode('utf-8').splitlines())
            profiles = json.loads((root / 'country_profiles.json').read_text())
            return cls(entities, names, links, profiles)
        if country is not None:
            raise ValueError('country-specific loading requires the split pack')
        with zipfile.ZipFile(root / 'oceania_dataset_20260927.zip') as archive:
            prefix = 'oceania_dataset_20260927/'
            countries = json.loads(archive.read(prefix + 'countries.json'))
            entities.extend({'id': c['id'], 'country_code': c['country_code'],
                             'name': c['name_en'], 'name_language': 'en',
                             'kind': 'country', 'parent_id': None, 'source': 'UN M49'}
                            for c in countries)
            for name in sorted(archive.namelist()):
                if name.startswith(prefix + 'data/') and name.endswith('/places.jsonl'):
                    entities.extend(json.loads(line) for line in archive.read(name).decode('utf-8').splitlines())
        with zipfile.ZipFile(root / 'locale_data.zip') as archive:
            names = [json.loads(line) for line in archive.read('names.jsonl').decode('utf-8').splitlines()]
            links = [json.loads(line) for line in archive.read('postal_links.jsonl').decode('utf-8').splitlines()]
            profiles = json.loads(archive.read('country_profiles.json'))
        return cls(entities, names, links, profiles)

    def label(self, entity_id, *, mode='local', locale=None):
        entity = self.entities[entity_id]
        cc = entity['country_code']
        if mode == 'local' and not locale:
            raise ValueError('local mode requires an explicit language; countries may have many')
        if mode == 'international_english':
            locale = 'en'
        elif mode == 'domestic_english':
            locale = 'en-' + cc
        return choose_label(entity, self.names[entity_id], locale=locale or '', usage=mode)

    def postal_candidates(self, country, postal_code):
        cc = country.upper()
        key = postal_key(postal_code)
        rows = self.postal.get((cc, key), [])
        ids = sorted({r['entity_id'] for r in rows})
        return {'country_code': cc, 'postal_code': key, 'entity_ids': ids,
                'status': 'ambiguous' if len(ids) > 1 else 'source_association' if ids else 'unverified',
                'evidence': rows, 'delivery_validated': False}

    def resolve(self, country, name, *, parent_id=None, postal_code=None):
        cc = country.upper()
        candidates = self.search_index.get((cc, name_key(name)), set()).copy()
        candidates = {eid for eid in candidates if self.entities[eid].get('kind') not in
                      ('historical_administrative_area', 'noncurrent_populated_place')}
        if parent_id:
            parent = self.entities.get(parent_id)
            if not parent or parent['country_code'] != cc:
                raise ValueError('unknown or cross-country parent')
            candidates = {eid for eid in candidates if self.entities[eid].get('parent_id') == parent_id}
        postal_status = None
        if postal_code is not None:
            postal = self.postal_candidates(cc, postal_code)
            postal_status = postal['status']
            candidates &= set(postal['entity_ids'])
        ids = sorted(candidates)
        return {'entity_ids': ids, 'status': 'resolved' if len(ids) == 1 else 'ambiguous' if ids else 'unresolved',
                'postal_status': postal_status, 'match_method': 'exact_country_name_and_optional_evidence'}

    def render(self, address, *, mode='local', locale=None, international=False):
        """Render typed fields using the destination template, preserving input.

        Geographic roles are explicit: an admin ancestor is not necessarily a
        postal town. This is a formatter with source checks, not carrier validation.
        """
        cc = address['country_code'].upper()
        profile = self.profiles[cc]
        if mode not in MODES:
            raise ValueError('unknown usage: ' + mode)
        if mode == 'local' and not locale:
            raise ValueError('local mode requires locale')
        template = profile['fmt']
        # lfmt means Latin-script formatting, not a different English vocabulary.
        if mode.endswith('english') and profile.get('lfmt'):
            template = profile['lfmt']
        values, selected = {}, {}
        for token, field in FIELDS.items():
            if token in 'DCS' and address.get(field + '_id'):
                eid = address[field + '_id']
                entity = self.entities[eid]
                if entity['country_code'] != cc:
                    raise ValueError('cross-country geographic field: ' + field)
                if entity.get('kind') in ('historical_administrative_area', 'noncurrent_populated_place'):
                    raise ValueError('noncurrent entity cannot be used for a current address')
                selected[field] = self.label(eid, mode=mode, locale=locale)
                values[token] = selected[field]['text']
            else:
                value = address.get(field, '')
                if token == 'A' and isinstance(value, list):
                    if not all(isinstance(line, str) for line in value):
                        raise TypeError('address_lines must contain strings')
                    value = '\n'.join(value)
                if not isinstance(value, str):
                    raise TypeError(field + ' must be a string')
                if token != 'A' and ('\n' in value or '\r' in value):
                    raise ValueError('unexpected newline in ' + field)
                values[token] = postal_key(value) if token == 'Z' else value.strip()
        missing = [FIELDS[key] for key in profile['require'] if not values.get(key)]
        allowed = set(re.findall(r'%([NOADCSZX])', template))
        omitted = [FIELDS[key] for key in FIELDS if values.get(key) and key not in allowed]
        for key in profile.get('upper', ''):
            if key in values:
                values[key] = values[key].upper()
        lines = []
        for part in template.split('%n'):
            keys = re.findall(r'%([NOADCSZX])', part)
            if keys and not any(values.get(key) for key in keys):
                continue
            # If an optional field is absent, remove punctuation next to it.
            for key in keys:
                if not values.get(key):
                    part = re.sub(r'%' + key + r'[, ]*', '', part)
            line = re.sub(r'%([NOADCSZX])', lambda match: values.get(match[1], ''), part)
            for fragment in line.splitlines():
                fragment = re.sub(r'[ \t]+', ' ', fragment).strip(' ,')
                if fragment:
                    lines.append(fragment)
        if international:
            lines.append(profile['country_name_en'].upper())
        postal = self.postal_candidates(cc, values['Z']) if values['Z'] else None
        locality_id = address.get('locality_id')
        if postal is not None and locality_id:
            postal['locality_association'] = ('source_association' if locality_id in postal['entity_ids']
                                             else 'unverified')
        pattern = profile.get('zip')
        postal_shape = None
        if values['Z'] and pattern:
            try:
                postal_shape = bool(re.fullmatch(pattern, values['Z'], flags=re.ASCII))
            except re.error:
                postal_shape = None
        return {'lines': lines, 'text': '\n'.join(lines), 'selected_labels': selected,
                'missing_required': missing, 'omitted_from_display': omitted,
                'postal_code_shape_match': postal_shape, 'postal_evidence': postal,
                'template_source': profile['source'], 'template_status': profile['template_status'],
                'input': address, 'delivery_validated': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pack', type=Path, required=True)
    sub = parser.add_subparsers(dest='command', required=True)
    label = sub.add_parser('label')
    label.add_argument('entity_id')
    for command in [label, sub.add_parser('render')]:
        command.add_argument('--mode', choices=sorted(MODES), default='international_english')
        command.add_argument('--locale')
        if command.prog.endswith('render'):
            command.add_argument('--input', type=Path, required=True)
            command.add_argument('--international', action='store_true')
    postal = sub.add_parser('postal')
    postal.add_argument('country')
    postal.add_argument('postal_code')
    args = parser.parse_args()
    catalog = RegionCatalog.from_pack(args.pack)
    if args.command == 'label':
        result = catalog.label(args.entity_id, mode=args.mode, locale=args.locale)
    elif args.command == 'postal':
        result = catalog.postal_candidates(args.country, args.postal_code)
    else:
        result = catalog.render(json.loads(args.input.read_text()), mode=args.mode,
                                locale=args.locale, international=args.international)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
