#!/usr/bin/env python3
"""Query one country without installing dependencies or building a database."""
import argparse
import json
from build import ROOT, country_rows


def select(country, kind=None, level=None, state=None, parent=None, text=None, include_other=False):
    if len(country) != 2 or not country.isalpha() or country != country.upper():
        raise ValueError('country must be an uppercase two-letter code')
    scope = json.loads((ROOT / 'scope.json').read_text(encoding='utf-8'))
    if country not in {c['country'] for c in scope['countries']}:
        raise ValueError('country outside documented scope')
    rows = country_rows(ROOT, country)
    for r in rows:
        if kind and r['kind'] != kind:
            continue
        if level and r['admin_level'] != str(level):
            continue
        if state and r['state_id'] != state:
            continue
        if parent and r['parent_id'] != parent:
            continue
        if not include_other and not kind and not level and r['address_candidate'] != '1':
            continue
        if text:
            labels = [r['name'], r['asciiname'], *r['alternatenames'].split(',')]
            if not any(text.casefold() in s.casefold() for s in labels):
                continue
        yield r


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--country', required=True)
    p.add_argument('--kind', choices=['locality', 'admin_subdivision', 'other_admin_feature'])
    p.add_argument('--level', type=int, choices=range(1, 6))
    p.add_argument('--state', help='GeoNames ADM1 identity from admin1.csv')
    p.add_argument('--parent', help='Exact direct source parent identity')
    p.add_argument('--text')
    p.add_argument('--include-other', action='store_true')
    p.add_argument('--limit', type=int, default=20)
    p.add_argument('--offset', type=int, default=0)
    args = p.parse_args()
    if not 1 <= args.limit <= 10000 or args.offset < 0:
        p.error('limit must be 1..10000; offset must be nonnegative')
    matches = select(args.country, args.kind, args.level, args.state, args.parent,
                     args.text, args.include_other)
    total, out = 0, []
    for r in matches:
        if args.offset <= total < args.offset + args.limit:
            out.append(r)
        total += 1
    meta = json.loads((ROOT / 'countries' / args.country / 'metadata.json').read_text(encoding='utf-8'))
    print(json.dumps({'country': args.country, 'total': total, 'offset': args.offset,
                      'current_official_hierarchy_verified': meta['current_official_hierarchy_verified'],
                      'known_issues': meta['known_issues'],
                      'results': out}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
