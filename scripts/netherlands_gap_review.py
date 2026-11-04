"""Explain strict snapshot-reference gaps without replacing source observations."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile

import netherlands_bag as bag


def valid_time_candidate(row, snapshot):
    h = row['history']
    return (row['status'] == 'Naamgeving uitgegeven' and h['beginGeldigheid'] <= snapshot
            and (not h.get('eindGeldigheid') or h['eindGeldigheid'] > snapshot)
            and not any(h.get(k) for k in ('tijdstipInactief', 'tijdstipInactiefLV', 'tijdstipNietBagLV')))


def review(manifest, root, accepted):
    if (accepted['implementation_sha256'] != bag.shared.sha256(bag.__file__)
            or accepted['manifest_sha256'] != hashlib.sha256(bag.shared.canonical(manifest).encode()).hexdigest()):
        raise ValueError('Source audit and current reader differ')
    indexes, _ = bag.reference_index(manifest, root)
    source = bag.source_by_role(manifest, 'public_spaces')
    candidates = {}
    for row in bag.records(source, root, manifest['snapshot_date']):
        if row['source_id'] not in indexes['public_spaces'] and valid_time_candidate(row, manifest['snapshot_date']):
            candidates.setdefault(row['source_id'], []).append({k: row[k] for k in (
                'source_id', 'source_qualified_id', 'street_names', 'locality_id', 'status', 'history')})
    markers = [identity.encode() for identity in candidates]
    source = bag.source_by_role(manifest, 'number_designations')
    path = bag.shared.verify_pin(source, root)
    affected, counts, selected_files = [], Counter(), 0
    with zipfile.ZipFile(path) as archive:
        bag.check_members(archive)
        for member in archive.namelist():
            data = archive.read(member)
            # Plain identifiers may occur under any XML prefix. Entity/CDATA
            # encodings force a semantic parse so that this prefilter cannot
            # silently skip encoded identifiers.
            if not any(marker in data for marker in markers) and b'&#' not in data and b'<![CDATA[' not in data:
                continue
            selected_files += 1
            for row in bag.xml_records(bag.io.BytesIO(data), source, member, manifest['snapshot_date'], 'main'):
                if not row['registry_open_at_snapshot'] or row['street_id'] not in candidates:
                    continue
                space, locality, link, municipality = bag.address_references(row, indexes)
                if space is not None:
                    raise ValueError('Candidate unexpectedly has a strict open reference')
                counts['open_number_without_open_public_space'] += 1
                if locality is None:
                    counts['open_number_without_open_locality'] += 1
                if link is None:
                    counts['open_number_without_open_gwr_helper_link'] += 1
                if municipality is None:
                    counts['open_number_without_cbs_municipality'] += 1
                affected.append({'source_id': row['source_id'], 'source_qualified_id': row['source_qualified_id'],
                                 'public_space_id': row['street_id'], 'locality_override_id': row['locality_override_id'],
                                 'valid_time_candidate_versions': len(candidates[row['street_id']]),
                                 'source_number_status': row['status']})
    expected = accepted['unresolved_reference_counts'].get('open_number_without_open_public_space', 0)
    distinct = len({r['source_id'] for r in affected})
    if len(affected) != expected or distinct != expected:
        raise ValueError('Candidate review does not account for every strict public-space gap')
    # Inspect any illustrated extra locality gap separately, without discarding
    # or replacing its explicit source override with the street's locality.
    extra = []
    seen = {r['source_qualified_id'] for r in affected}
    with zipfile.ZipFile(path) as archive:
        for ref in accepted['unresolved_reference_examples'].get('open_number_without_open_locality', []):
            if ref in seen:
                continue
            _, member, position = ref.split(':')
            with archive.open(member) as stream:
                for row in bag.xml_records(stream, source, member, manifest['snapshot_date'], 'main'):
                    if row['ordinal'] == int(position):
                        space, locality, link, municipality = bag.address_references(row, indexes)
                        extra.append({'source_id': row['source_id'], 'source_qualified_id': ref,
                                      'source_locality_override_id': row['locality_override_id'],
                                      'public_space_id': row['street_id'],
                                      'public_space_open_locality_id': (space or {}).get('locality_id'),
                                      'override_has_open_wpl': locality is not None})
                        break
    extra_ids = {r['source_locality_override_id'] for r in extra}
    locality_versions = {identity: [] for identity in extra_ids}
    for row in bag.records(bag.source_by_role(manifest, 'localities'), root, manifest['snapshot_date']):
        if row['source_id'] in extra_ids:
            locality_versions[row['source_id']].append({k: row[k] for k in (
                'source_id', 'source_qualified_id', 'name', 'status', 'registry_open_at_snapshot', 'history')})
    locality_expected = accepted['unresolved_reference_counts'].get('open_number_without_open_locality', 0)
    extra_complete = counts['open_number_without_open_locality'] + len(extra) == locality_expected
    return {'schema_version': 1, 'country': 'NL', 'snapshot_date': manifest['snapshot_date'],
            'implementation_sha256': bag.shared.sha256(__file__), 'reader_sha256': bag.shared.sha256(bag.__file__),
            'manifest_sha256': accepted['manifest_sha256'],
            'status': 'STRICT_GAPS_EXPLAINED_WITHOUT_REWRITING_SOURCE' if extra_complete else 'ADDITIONAL_REVIEW_REQUIRED',
            'public_space_candidate_basis': 'Assigned public-space history whose valid-time interval includes the snapshot, '
                'with no inactive/not-BAG marker, but excluded by the stricter registration-open predicate. '
                'Candidates are evidence only; no source dates, statuses or reference IDs are replaced.',
            'public_space_candidates': candidates,
            'strict_public_space_gap_rows': expected, 'accounted_unique_number_ids': distinct,
            'all_strict_public_space_gaps_accounted': True,
            'strict_locality_gap_rows': locality_expected, 'all_strict_locality_gaps_accounted': extra_complete,
            'candidate_number_rows': affected, 'additional_locality_examples': extra,
            'related_locality_versions': locality_versions, 'semantically_parsed_number_files': selected_files,
            'all_number_zip_members_crc_checked': True, 'source_values_modified': False,
            'national_completeness_verified': False, 'deliverability_in_scope': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--accepted', type=Path, default=bag.DEFAULT_MANIFEST.parent / 'validation.json')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = review(bag.load_manifest(), args.data_root, json.loads(args.accepted.read_text()))
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            args.output.write_text(rendered, encoding='utf-8')
        else:
            print(rendered, end='')
    except (OSError, ValueError, KeyError, bag.ET.ParseError, zipfile.BadZipFile) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
