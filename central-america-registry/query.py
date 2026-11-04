#!/usr/bin/env python3
"""Query one country without installing dependencies or building a database."""
import argparse
import json
from build import ROOT, read_csv
from name_labels import select_label
from localities.materialize import materialize_country
from localities.query import matching_rows, page, validate_country_code


def select(country, kind=None, level=None, state=None, parent=None, text=None, include_other=False):
    validate_country_code(country)
    yield from matching_rows(
        read_csv(ROOT / 'countries' / country / 'entities.csv.gz'),
        kind=kind,
        level=level,
        state=state,
        parent=parent,
        text=text,
        include_other=include_other,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--country', required=True)
    p.add_argument('--kind', choices=['locality', 'admin_subdivision', 'other_admin_feature'])
    p.add_argument('--level', type=int, choices=range(1, 6))
    p.add_argument('--state', help='GeoNames ADM1 identity, e.g. gn:3582676')
    p.add_argument('--parent', help='Exact direct source parent identity')
    p.add_argument('--text')
    p.add_argument('--language', help='Explicit requested source-label locale, e.g. es or en. Untagged source fallback is disclosed.')
    p.add_argument('--include-other', action='store_true')
    p.add_argument('--limit', type=int, default=20)
    p.add_argument('--offset', type=int, default=0)
    args = p.parse_args()
    if not 1 <= args.limit <= 10000 or args.offset < 0:
        p.error('limit must be 1..10000; offset must be nonnegative')
    materialize_country(ROOT, args.country)
    matches = select(args.country, args.kind, args.level, args.state, args.parent,
                     args.text, args.include_other)
    total, out = page(matches, args.offset, args.limit)
    if args.language:
        names=list(read_csv(ROOT / 'countries' / args.country / 'names.csv.gz'))
        out=[dict(r, **select_label(r['id'], r['name'], args.language, names)) for r in out]
    meta = json.loads((ROOT / 'countries' / args.country / 'metadata.json').read_text(encoding='utf-8'))
    print(json.dumps({'country': args.country, 'total': total, 'offset': args.offset,
                      'current_official_hierarchy_verified': meta['current_official_hierarchy_verified'],
                      'known_issues': meta['known_issues'],
                      'results': out}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
