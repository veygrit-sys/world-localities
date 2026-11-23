"""Source-backed, offline address entry suggestions.

An operator builds an index once, then passes its path or a reusable PostalPicker
to suggest(). Queries use an exact country, full indexed postcode and previously
selected path. No submitted address is retained and no request goes online.
"""

import argparse
import json

from localities.postal_picker import IndexUnavailable, PostalPicker, build_index


def _similar(country, query, options):
    from .address_ranker import fuzzy_matches, supports_pool

    if not supports_pool(country, options, min_rows=1):
        return []
    return [row for row in options if fuzzy_matches(query, row["label"])]


def suggest(index, country, postcode, *, query="", path=(), after=None, limit=20):
    """Filter actual child labels before pagination and optionally rank the page.

    The cursor is an offset for this same country, postcode, path and query.
    Reset it when any input changes. A leaf ends the source's coverage; it
    neither certifies a delivery point nor rules out further address details.
    """
    picker = index if isinstance(index, PostalPicker) else PostalPicker(index)
    from .address_ranker import supports_country
    spelling = (supports_country(country) and isinstance(query, str) and 3 <= len(query.strip()) <= 96
                and all(ch.isalpha() or ch == " " for ch in query))
    result = picker.lookup(country, postcode, path, query=query, limit=limit, after=after,
                           similar_filter=_similar if spelling else None)
    result["spelling_notice"] = "confirm_suggested_spelling" if result["match_mode"] == "similar_spelling" else None
    result["auto_selected"] = False
    result["manual_entry_available"] = True
    result["ranking_scope"] = "source_order"
    if query.strip() and result["options"]:
        from .address_ranker import rank_candidates, supports_pool

        if supports_pool(result["country"], result["options"]):
            try:
                result["options"] = rank_candidates(
                    query, result["options"], country_code=result["country"], postcode=result["postcode"]
                )
            except (ValueError, OSError) as error:
                raise IndexUnavailable("address ranking resource unavailable") from error
            result["ranking_scope"] = "within_page"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="atomically build from local source snapshots")
    build.add_argument("--index", required=True)
    build.add_argument("--country", action="append", dest="countries",
                       help="ISO country code, repeatable; default: all eligible countries")
    lookup = commands.add_parser("lookup", help="query the local index")
    lookup.add_argument("--index", required=True)
    lookup.add_argument("--country", required=True)
    lookup.add_argument("--postcode", required=True)
    lookup.add_argument("--query", default="")
    lookup.add_argument("--select", action="append", dest="path", default=[])
    lookup.add_argument("--after", type=int)
    lookup.add_argument("--limit", type=int, default=20)
    args = vars(parser.parse_args(argv))
    command = args.pop("command")
    if command == "build":
        result = build_index(args["index"], args["countries"])
    else:
        result = suggest(**args)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
