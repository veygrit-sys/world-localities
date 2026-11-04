"""Review Dutch name-register references, including streets without addresses."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import netherlands_bag as bag


def review(manifest, root):
    indexes, _ = bag.reference_index(manifest, root)
    gaps, samples = Counter(), {}
    locality_municipalities, public_space_municipalities = set(), set()

    def gap(reason, identity):
        gaps[reason] += 1
        if len(samples.setdefault(reason, [])) < 10:
            samples[reason].append(identity)

    for identity, row in indexes['localities'].items():
        link = indexes['municipality_locality_links'].get(identity)
        if link is None:
            gap('open_locality_without_open_gwr_helper', identity)
        elif link['municipality_id'] not in indexes['municipalities']:
            gap('open_locality_without_cbs_municipality', identity)
        else:
            locality_municipalities.add(link['municipality_id'])
    types = Counter()
    for identity, row in indexes['public_spaces'].items():
        types[row['public_space_type']] += 1
        locality = row['locality_id']
        if locality not in indexes['localities']:
            gap('open_public_space_without_open_locality', identity)
        link = indexes['municipality_locality_links'].get(locality)
        if link is None:
            gap('open_public_space_without_open_gwr_helper', identity)
        elif link['municipality_id'] not in indexes['municipalities']:
            gap('open_public_space_without_cbs_municipality', identity)
        else:
            public_space_municipalities.add(link['municipality_id'])
    support_only = sorted(set(indexes['municipality_locality_links']) - indexes['localities'].keys())
    expected = set(indexes['municipalities'])
    no_locality = sorted(expected - locality_municipalities)
    no_public_space = sorted(expected - public_space_municipalities)
    sources = [bag.source_by_role(manifest, role) for role in indexes]
    return {'schema_version': 1, 'country': 'NL', 'snapshot_date': manifest['snapshot_date'],
            'implementation_sha256': bag.shared.sha256(__file__),
            'reader_sha256': bag.shared.sha256(bag.__file__),
            'shared_helpers_sha256': bag.shared.sha256(bag.shared.__file__),
            'manifest_sha256': hashlib.sha256(bag.shared.canonical(manifest).encode()).hexdigest(),
            'source_pins': {s['id']: s['sha256'] for s in sources},
            'status': 'GAPS_REQUIRE_REVIEW' if gaps or no_locality or no_public_space else 'PASS_FOR_CHECKED_REFERENCES',
            'reference_scope': 'Every open OPR/WPL record, regardless of whether it has a NUM address; '
                               'open is the conservative snapshot predicate defined by the BAG reader.',
            'counts': {key: len(value) for key, value in indexes.items()},
            'open_public_space_types': dict(types), 'unresolved_reference_counts': dict(gaps),
            'unresolved_reference_examples': samples,
            'cbs_municipalities_without_open_locality': no_locality,
            'cbs_municipalities_without_open_public_space': no_public_space,
            'gwr_open_codes_without_open_wpl': {'count': len(support_only), 'codes': support_only,
                'interpretation': 'Unended helper relationships do not establish an active WPL object.'},
            'gwr_is_authentic_bag_attribute': False,
            'national_completeness_verified': False, 'all_physical_roads_complete': False,
            'deliverability_in_scope': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=bag.DEFAULT_MANIFEST)
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = review(bag.load_manifest(args.manifest), args.data_root)
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            args.output.write_text(rendered, encoding='utf-8')
        else:
            print(rendered, end='')
    except (OSError, ValueError, KeyError, bag.ET.ParseError, bag.zipfile.BadZipFile) as exc:
        parser.exit(2, str(exc) + '\n')


if __name__ == '__main__':
    main()
