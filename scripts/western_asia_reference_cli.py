"""Inspect and validate nine Western Asian official-reference formats without network access."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from addressing.western_asia_reference import (
    inspect_western_asia_reference, validate_western_asia_reference
)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--country", required=True, choices=["TR", "CY", "KW", "AE", "SA", "BH", "QA", "OM", "PS"])
    check = sub.add_parser("validate")
    check.add_argument("--country", required=True, choices=["TR", "CY", "KW", "AE", "SA", "BH", "QA", "OM", "PS"])
    check.add_argument("--postcode")
    check.add_argument("--delivery-mode", default="home", choices=["home", "po_box"])
    check.add_argument("--direction", default="domestic", choices=["domestic", "inbound"])
    check.add_argument("--emirate")
    check.add_argument("--block")
    check.add_argument("--po-box")
    check.add_argument("--makani")
    check.add_argument("--onwani-postcode")
    for field in ("building-number", "additional-number", "short-address",
                  "road", "district", "city", "locality",
                  "zone", "street-number", "phone"):
        check.add_argument("--" + field)
    check.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    if args.command == "inspect":
        value = inspect_western_asia_reference(args.country)
    else:
        value = validate_western_asia_reference(
            args.country, postcode=args.postcode,
            delivery_mode=args.delivery_mode, direction=args.direction,
            emirate=args.emirate, block=args.block, po_box=args.po_box,
            makani=args.makani, onwani_postcode=args.onwani_postcode,
            building_number=args.building_number,
            additional_number=args.additional_number,
            short_address=args.short_address, road=args.road,
            district=args.district, city=args.city, locality=args.locality,
            zone=args.zone, street_number=args.street_number,
            phone=args.phone, require_complete=args.require_complete,
        )
    print(json.dumps(value, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
