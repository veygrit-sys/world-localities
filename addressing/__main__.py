"""Command line interface for worldwide address profiles and rendering."""

from __future__ import annotations

import argparse
import json

from .central_asia import CentralAsiaRegistry, render_central_asia_address
from .central_america import CentralAmericaRegistry, render_central_america_address
from .caribbean import CaribbeanRegistry, render_caribbean_address
from .central_europe import CentralEuropeRegistry, render_central_europe_address
from .formatting import render_address
from .east_asia import EastAsiaRegistry, render_bilingual_address
from .eastern_africa import EasternAfricaRegistry, render_eastern_africa_address
from .eastern_europe import EasternEuropeRegistry, render_eastern_europe_address
from .northern_africa import NorthernAfricaRegistry, render_northern_africa_address
from .middle_africa import MiddleAfricaRegistry, render_middle_africa_address
from .northern_america import NorthernAmericaRegistry, render_northern_america_address
from .northern_europe import NorthernEuropeRegistry, render_northern_europe_address
from .oceania import OceaniaRegistry, render_oceania_address
from .profiles import ProfileRegistry
from .south_asia import SouthAsiaRegistry, render_south_asia_address
from .southern_africa import SouthernAfricaRegistry, render_southern_africa_address
from .southern_europe import SouthernEuropeRegistry, render_southern_europe_address
from .southeast_asia import SoutheastAsiaRegistry, render_southeast_asia_address
from .western_asia import WesternAsiaRegistry, render_western_asia_address
from .western_africa import WesternAfricaRegistry, render_western_africa_address
from .western_europe import WesternEuropeRegistry, render_western_europe_address


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("verify", help="verify all compiled country profiles")
    commands.add_parser("east-asia", help="report native/English East Asia coverage")
    commands.add_parser(
        "southeast-asia", help="report native/English Southeast Asia coverage"
    )
    commands.add_parser(
        "south-asia", help="report native/English Southern Asia coverage"
    )
    commands.add_parser(
        "central-asia", help="report native/English Central Asia coverage"
    )
    commands.add_parser(
        "western-asia", help="report native/English Western Asia coverage"
    )
    commands.add_parser(
        "western-europe", help="report native/English Western Europe coverage"
    )
    commands.add_parser(
        "southern-europe", help="report native/English Southern Europe coverage"
    )
    commands.add_parser(
        "northern-europe", help="report native/English Northern Europe coverage"
    )
    commands.add_parser(
        "eastern-europe", help="report native/English Eastern Europe coverage"
    )
    commands.add_parser(
        "central-europe", help="report native/English Central Europe coverage"
    )
    commands.add_parser(
        "oceania", help="report domestic-language/English Oceania coverage"
    )
    commands.add_parser(
        "northern-africa",
        help="report domestic-language/English Northern Africa coverage",
    )
    commands.add_parser(
        "eastern-africa",
        help="report domestic-language/English Eastern Africa coverage",
    )
    commands.add_parser(
        "middle-africa",
        help="report domestic-language/English Middle Africa coverage",
    )
    commands.add_parser(
        "western-africa",
        help="report domestic-language/English Western Africa coverage",
    )
    commands.add_parser(
        "southern-africa",
        help="report domestic-language/English Southern Africa coverage",
    )
    commands.add_parser(
        "northern-america",
        help="report domestic-language/English Northern America coverage",
    )
    commands.add_parser(
        "central-america",
        help="report domestic-language/English Central America coverage",
    )
    commands.add_parser(
        "caribbean",
        help="report domestic-language/English Caribbean coverage",
    )
    profile = commands.add_parser("profile", help="show a selected profile")
    render = commands.add_parser("render", help="render structured address JSON")
    for command in (profile, render):
        command.add_argument("--country", required=True)
        command.add_argument("--language")
        command.add_argument("--international", action="store_true")
    render.add_argument("--components-json", required=True)
    bilingual = commands.add_parser(
        "render-bilingual", help="render strict native and English East Asia output"
    )
    bilingual.add_argument("--country", required=True)
    bilingual.add_argument("--native-language")
    bilingual.add_argument("--components-json", required=True)
    bilingual.add_argument("--allow-incomplete", action="store_true")
    southeast = commands.add_parser(
        "render-southeast-asia",
        help="render strict native and English Southeast Asia output",
    )
    southeast.add_argument("--country", required=True)
    southeast.add_argument("--native-language")
    southeast.add_argument("--components-json", required=True)
    southeast.add_argument("--allow-incomplete", action="store_true")
    south = commands.add_parser(
        "render-south-asia",
        help="render strict native and English Southern Asia output",
    )
    south.add_argument("--country", required=True)
    south.add_argument("--native-language")
    south.add_argument("--components-json", required=True)
    south.add_argument("--allow-incomplete", action="store_true")
    central = commands.add_parser(
        "render-central-asia",
        help="render strict native and English Central Asia output",
    )
    central.add_argument("--country", required=True)
    central.add_argument("--native-language")
    central.add_argument("--components-json", required=True)
    central.add_argument("--allow-incomplete", action="store_true")
    western = commands.add_parser(
        "render-western-asia",
        help="render strict native and English Western Asia output",
    )
    western.add_argument("--country", required=True)
    western.add_argument("--native-language")
    western.add_argument("--components-json", required=True)
    western.add_argument("--allow-incomplete", action="store_true")
    western_europe = commands.add_parser(
        "render-western-europe",
        help="render strict native and English Western Europe output",
    )
    western_europe.add_argument("--country", required=True)
    western_europe.add_argument("--native-language")
    western_europe.add_argument("--components-json", required=True)
    western_europe.add_argument("--allow-incomplete", action="store_true")
    southern_europe = commands.add_parser(
        "render-southern-europe",
        help="render strict native and English Southern Europe output",
    )
    southern_europe.add_argument("--country", required=True)
    southern_europe.add_argument("--native-language")
    southern_europe.add_argument("--components-json", required=True)
    southern_europe.add_argument("--allow-incomplete", action="store_true")
    northern_europe = commands.add_parser(
        "render-northern-europe",
        help="render strict native and English Northern Europe output",
    )
    northern_europe.add_argument("--country", required=True)
    northern_europe.add_argument("--native-language")
    northern_europe.add_argument("--components-json", required=True)
    northern_europe.add_argument("--allow-incomplete", action="store_true")
    eastern_europe = commands.add_parser(
        "render-eastern-europe",
        help="render strict native and English Eastern Europe output",
    )
    eastern_europe.add_argument("--country", required=True)
    eastern_europe.add_argument("--native-language")
    eastern_europe.add_argument("--components-json", required=True)
    eastern_europe.add_argument("--allow-incomplete", action="store_true")
    central_europe = commands.add_parser(
        "render-central-europe",
        help="render strict native and English Central Europe output",
    )
    central_europe.add_argument("--country", required=True)
    central_europe.add_argument("--native-language")
    central_europe.add_argument("--components-json", required=True)
    central_europe.add_argument("--allow-incomplete", action="store_true")
    oceania = commands.add_parser(
        "render-oceania",
        help="render strict domestic-language and English Oceania output",
    )
    oceania.add_argument("--country", required=True)
    oceania.add_argument("--native-language")
    oceania.add_argument("--components-json", required=True)
    oceania.add_argument("--allow-incomplete", action="store_true")
    northern_africa = commands.add_parser(
        "render-northern-africa",
        help="render strict domestic-language and English Northern Africa output",
    )
    northern_africa.add_argument("--country", required=True)
    northern_africa.add_argument("--native-language")
    northern_africa.add_argument("--components-json", required=True)
    northern_africa.add_argument("--allow-incomplete", action="store_true")
    eastern_africa = commands.add_parser(
        "render-eastern-africa",
        help="render strict domestic-language and English Eastern Africa output",
    )
    eastern_africa.add_argument("--country", required=True)
    eastern_africa.add_argument("--native-language")
    eastern_africa.add_argument("--components-json", required=True)
    eastern_africa.add_argument("--allow-incomplete", action="store_true")
    middle_africa = commands.add_parser(
        "render-middle-africa",
        help="render strict domestic-language and English Middle Africa output",
    )
    middle_africa.add_argument("--country", required=True)
    middle_africa.add_argument("--native-language")
    middle_africa.add_argument("--components-json", required=True)
    middle_africa.add_argument("--allow-incomplete", action="store_true")
    western_africa = commands.add_parser(
        "render-western-africa",
        help="render strict domestic-language and English Western Africa output",
    )
    western_africa.add_argument("--country", required=True)
    western_africa.add_argument("--native-language")
    western_africa.add_argument("--components-json", required=True)
    western_africa.add_argument("--allow-incomplete", action="store_true")
    southern_africa = commands.add_parser(
        "render-southern-africa",
        help="render strict domestic-language and English Southern Africa output",
    )
    southern_africa.add_argument("--country", required=True)
    southern_africa.add_argument("--native-language")
    southern_africa.add_argument("--components-json", required=True)
    southern_africa.add_argument("--allow-incomplete", action="store_true")
    northern_america = commands.add_parser(
        "render-northern-america",
        help="render strict domestic-language and English Northern America output",
    )
    northern_america.add_argument("--country", required=True)
    northern_america.add_argument("--native-language")
    northern_america.add_argument("--components-json", required=True)
    northern_america.add_argument("--allow-incomplete", action="store_true")
    central_america = commands.add_parser(
        "render-central-america",
        help="render strict domestic-language and English Central America output",
    )
    central_america.add_argument("--country", required=True)
    central_america.add_argument("--native-language")
    central_america.add_argument("--components-json", required=True)
    central_america.add_argument("--allow-incomplete", action="store_true")
    caribbean = commands.add_parser(
        "render-caribbean",
        help="render strict domestic-language and English Caribbean output",
    )
    caribbean.add_argument("--country", required=True)
    caribbean.add_argument("--native-language")
    caribbean.add_argument("--components-json", required=True)
    caribbean.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    registry = ProfileRegistry()
    if args.command == "verify":
        print(json.dumps(registry.report(), sort_keys=True))
        return
    if args.command == "east-asia":
        print(json.dumps(EastAsiaRegistry().report(), sort_keys=True))
        return
    if args.command == "southeast-asia":
        print(json.dumps(SoutheastAsiaRegistry().report(), sort_keys=True))
        return
    if args.command == "south-asia":
        print(json.dumps(SouthAsiaRegistry().report(), sort_keys=True))
        return
    if args.command == "central-asia":
        print(json.dumps(CentralAsiaRegistry().report(), sort_keys=True))
        return
    if args.command == "western-asia":
        print(json.dumps(WesternAsiaRegistry().report(), sort_keys=True))
        return
    if args.command == "western-europe":
        print(json.dumps(WesternEuropeRegistry().report(), sort_keys=True))
        return
    if args.command == "southern-europe":
        print(json.dumps(SouthernEuropeRegistry().report(), sort_keys=True))
        return
    if args.command == "northern-europe":
        print(json.dumps(NorthernEuropeRegistry().report(), sort_keys=True))
        return
    if args.command == "eastern-europe":
        print(json.dumps(EasternEuropeRegistry().report(), sort_keys=True))
        return
    if args.command == "central-europe":
        print(json.dumps(CentralEuropeRegistry().report(), sort_keys=True))
        return
    if args.command == "oceania":
        print(json.dumps(OceaniaRegistry().report(), sort_keys=True))
        return
    if args.command == "northern-africa":
        print(json.dumps(NorthernAfricaRegistry().report(), sort_keys=True))
        return
    if args.command == "eastern-africa":
        print(json.dumps(EasternAfricaRegistry().report(), sort_keys=True))
        return
    if args.command == "middle-africa":
        print(json.dumps(MiddleAfricaRegistry().report(), sort_keys=True))
        return
    if args.command == "western-africa":
        print(json.dumps(WesternAfricaRegistry().report(), sort_keys=True))
        return
    if args.command == "southern-africa":
        print(json.dumps(SouthernAfricaRegistry().report(), sort_keys=True))
        return
    if args.command == "northern-america":
        print(json.dumps(NorthernAmericaRegistry().report(), sort_keys=True))
        return
    if args.command == "central-america":
        print(json.dumps(CentralAmericaRegistry().report(), sort_keys=True))
        return
    if args.command == "caribbean":
        print(json.dumps(CaribbeanRegistry().report(), sort_keys=True))
        return
    if args.command == "render-bilingual":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_bilingual_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-southeast-asia":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_southeast_asia_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-south-asia":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_south_asia_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-central-asia":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_central_asia_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-western-asia":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_western_asia_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-western-europe":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_western_europe_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-southern-europe":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_southern_europe_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-northern-europe":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_northern_europe_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-eastern-europe":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_eastern_europe_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-central-europe":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_central_europe_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-oceania":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_oceania_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-northern-africa":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_northern_africa_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-eastern-africa":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_eastern_africa_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-middle-africa":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_middle_africa_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-western-africa":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_western_africa_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-southern-africa":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_southern_africa_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-northern-america":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_northern_america_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-central-america":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_central_america_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    if args.command == "render-caribbean":
        components = json.loads(args.components_json)
        if not isinstance(components, dict):
            parser.error("--components-json must contain a JSON object")
        result = render_caribbean_address(
            components,
            args.country,
            native_language=args.native_language,
            strict=not args.allow_incomplete,
            registry=registry,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
        return
    selected = registry.select(
        args.country, language=args.language, international=args.international
    )
    if args.command == "profile":
        print(
            json.dumps(
                {
                    "key": selected.key,
                    "country_code": selected.country_code,
                    "language": selected.language,
                    "inherited_from": selected.inherited_from,
                    "config": selected.config,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return
    components = json.loads(args.components_json)
    if not isinstance(components, dict):
        parser.error("--components-json must contain a JSON object")
    result = render_address(
        components,
        args.country,
        language=args.language,
        international=args.international,
        registry=registry,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
