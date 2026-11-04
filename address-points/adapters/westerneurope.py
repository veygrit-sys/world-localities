"""Expose pinned Western Europe registers through the regional CLI."""
from pathlib import Path
import argparse
import json
import os
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import western_europe_sources
import netherlands_bag


def main():
    if '--data-root' not in sys.argv and os.environ.get('WORLD_LOCALITIES_ADDRESS_ROOT'):
        sys.argv.extend(['--data-root', os.environ['WORLD_LOCALITIES_ADDRESS_ROOT']])
    selector = argparse.ArgumentParser(add_help=False)
    selector.add_argument('command', nargs='?')
    selector.add_argument('--country')
    selector.add_argument('--manifest')
    selector.add_argument('--output', type=Path)
    known, _ = selector.parse_known_args()
    if known.country == 'NL':
        netherlands_bag.main()
    elif '--help' in sys.argv or '-h' in sys.argv:
        western_europe_sources.main()
    elif known.command == 'inventory' and known.manifest is None:
        legacy = western_europe_sources.load_manifest(western_europe_sources.DEFAULT_MANIFEST)
        dutch = netherlands_bag.load_manifest()
        result = {'scope_codes': list(western_europe_sources.SCOPE),
                  'm49_western_europe': list(western_europe_sources.M49),
                  'legacy_group_additions': ['GB', 'IE'],
                  'sources': (western_europe_sources.selected_sources(legacy, known.country)
                              if known.country else legacy['sources'] + dutch['sources']),
                  'source_sets': {'legacy': str(western_europe_sources.DEFAULT_MANIFEST.relative_to(western_europe_sources.ROOT)),
                                  'NL': str(netherlands_bag.DEFAULT_MANIFEST.relative_to(netherlands_bag.ROOT))},
                  'national_completeness_verified': False, 'deliverability_in_scope': False}
        rendered = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
        if known.output is not None:
            known.output.write_text(rendered, encoding='utf-8')
        else:
            print(rendered, end='')
    elif known.country is None and known.manifest is None and known.command in ('audit', 'replay', 'acquire'):
        selector.error('Select --country for regional operations. NL has its own pinned source manifest; '
                       'the legacy scripts/western_europe_sources.py interface is unchanged.')
    else:
        western_europe_sources.main()


if __name__ == '__main__':
    main()
