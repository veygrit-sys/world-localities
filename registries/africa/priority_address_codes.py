#!/usr/bin/env python3
"""Conservative priority-African address-code syntax diagnostics.

This is never a postcode assignment, real-address validator, NIPOST/GhanaPostGPS
API lookup or carrier deliverability certificate. Unknown cases remain unknown.
"""
import argparse
import json
import re

COUNTRIES = {"ZA", "NG", "KE", "GH", "RW", "EG", "MA", "DZ"}

RULES = {
    "ZA": [
        ("ZA-4digit", r"[0-9]{4}", "https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/zafEn.pdf"),
    ],
    "NG": [
        ("NG-legacy-6digit", r"[0-9]{6}",
         "https://nipost.gov.ng/wp-content/uploads/2024/09/NIGERIAN-NATIONAL-ADDRESSING-STANDARD-AND-GUIDELINES.pdf"),
        ("NG-NIPOST-2026-11character", r"[A-Z]{2}[0-9A-Z]{2}[A-Z0-9]{3}[A-Z0-9]{2}[A-Z0-9]{2}",
         "https://postcode.gov.ng/"),
    ],
    "KE": [
        ("KE-5digit",r"[0-9]{5}","https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/kenEn.pdf"),
    ],
    "GH": [
        ("GH-GhanaPostGPS-digital-address",r"[A-Z0-9]{2}-[0-9]{3}-[0-9]{4}",
         "https://nas.ghanapostgps.com/"),
    ],
    "RW": [],
    "EG": [
        ("EG-UPU-2023-7digit",r"[0-9]{7}",
         "https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/egyEn.pdf"),
    ],
    "MA": [
        ("MA-5digit",r"[0-9]{5}", "https://www.codepostal.ma/code_postal.aspx"),
    ],
    "DZ": [
        ("DZ-5digit",r"[0-9]{5}",
         "https://www.upu.int/UPU/media/upu/PostalEntitiesFiles/addressingUnit/dzaEn.pdf"),
    ],
}

def plausible(country, value):
    """Pure diagnostic: accept plausible syntax, never assert real location."""
    if country not in COUNTRIES: raise ValueError("country out of priority scope")
    if value is None or not str(value).strip():
        return {"country":country, "status":"not_supplied",
                "valid_address":None, "deliverability_verified":False,
                "detail":"Code absent; do not infer that the real address cannot exist"}
    original=str(value).strip()
    token=original.upper()
    possible = RULES[country]
    if country == "NG":
        compact = re.sub(r"[\s-]", "", token)
        token = compact if len(compact)==11 else token
    for name, pattern, source in possible:
        if re.fullmatch(pattern, token, flags=re.ASCII):
            return {"country":country, "status":"syntax_plausible",
                    "format":name,"source":source,"normalized":token,
                    "valid_address":None, "deliverability_verified":False,
                    "provider_verification_required":True}
    if not possible:
        return {"country":country, "status":"unassessed",
                "valid_address":None,"deliverability_verified":False,
                "detail":"No verified universal postal-code format for this country"}
    return {"country":country,"status":"syntax_not_recognized",
            "valid_address":None,"deliverability_verified":False,
            "detail":"Does not match the documented format(s); may be an alternate addressing scheme"}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--country",required=True,choices=sorted(COUNTRIES))
    p.add_argument("--code",default=None)
    a=p.parse_args()
    print(json.dumps(plausible(a.country,a.code),ensure_ascii=False,sort_keys=True))

if __name__=="__main__":
    main()
