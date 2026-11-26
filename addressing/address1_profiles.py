"""Classify the form of an address before displaying its evidence.

These are candidate-disambiguation hints. No rule here verifies a field,
assigns a house number or changes the user's country or original lines.
"""
from __future__ import annotations

from collections.abc import Mapping
import re


# Only explicit street/box mixes indicate two destinations: a recipient's
# organization and the town printed under a PO box are ordinary mailing data.
_POSTAL_FIELDS = {"po_box", "postal_box", "general_delivery", "locked_bag", "private_bag"}
_CIVIC_FIELDS = {"road", "lot", "block", "entrance"}
_PLACE_FIELDS = {"village", "hamlet", "island", "archipelago", "landmark", "place"}
_PACIFIC_VILLAGE = {"CK", "FJ", "KI", "PG", "SB", "TK", "TO", "TV", "VU", "WS"}

# A leading street name such as 'PO Box Road' must not become a postal box.
_BOX_ID = r"(?=[A-Z0-9-]*[0-9])[A-Z0-9-]+\b"
_PO_BOX = re.compile(r"(?:P\.?\s*O\.?|POST OFFICE)\s*BOX\s*#?\s*" + _BOX_ID, re.I)
_US_ROUTE = re.compile(r"(?:RR|HC)\s*[0-9]+\s+BOX\s*" + _BOX_ID, re.I)
_APARTADO = re.compile(r"APARTADO(?:\s+POSTAL)?\s*#?\s*" + _BOX_ID, re.I)
_CAN_PO = re.compile(r"(?:CASE POSTALE|C\.?\s*P\.?)\s*" + _BOX_ID, re.I)
_CAN_ROUTE = re.compile(r"(?:RR|ROUTE RURALE)\s*[0-9]+\b|(?:GENERAL DELIVERY|POSTE RESTANTE)\b", re.I)
_BAG = re.compile(r"(?:PRIVATE (?:MAIL )?BAG|P\.?M\.?B\.?)\s*" + _BOX_ID, re.I)
_AU_POST = re.compile(r"(?:GPO BOX|LOCKED BAG)\s*" + _BOX_ID, re.I)
_COUNTRY_POST = {
    "US": (_US_ROUTE,), "PR": (_US_ROUTE, _APARTADO),
    "CA": (_CAN_PO, _CAN_ROUTE), "MX": (_APARTADO,),
    "AU": (_AU_POST, _BAG), "NZ": (_BAG,), "VU": (_BAG,),
}

# These are additional distinguishing components, not mandatory fields.
_HINTS = {
    "US": ("state", "postcode"), "PR": ("urbanization", "municipality"),
    "CA": ("municipality", "state"), "MX": ("neighbourhood", "municipality"),
    "AU": ("suburb", "state"), "NZ": ("municipality", "hamlet"),
    "JP": ("municipality", "town"), "CN": ("city", "city_district"),
}
_UNNUMBERED = re.compile(r"(?:S\s*/\s*N\.?|SIN N[ÚU]MERO)", re.I)
_CIVIC_START = re.compile(r"[0-9]+[A-Z]?(?:[-/][0-9]+[A-Z]?)?\s+[^\W\d_]", re.I)


def address1_profile(country: str, values: Mapping[str, str]) -> dict:
    """Return an input classification for already canonicalized, nonempty fields."""
    jurisdiction = country
    states = {values[k].strip().upper() for k in ("state", "state_code") if k in values}
    if country == "US" and states and states <= {"PR", "PUERTO RICO"}:
        jurisdiction = "PR"

    postal = bool(_POSTAL_FIELDS & values.keys())
    physical = bool(_CIVIC_FIELDS & values.keys())
    number = values.get("house_number", "")
    unnumbered = jurisdiction == "MX" and bool(_UNNUMBERED.fullmatch(number))
    physical |= bool(number and not unnumbered)

    postal_rules = (_PO_BOX, *_COUNTRY_POST.get(jurisdiction, ()))
    for key in ("address_line1", "address_line2"):
        for part in re.split("[,;]", values.get(key, "")):
            line = part.strip()
            if any(rule.match(line) for rule in postal_rules):
                postal = True
            elif _CIVIC_START.match(line):
                physical = True

    if postal:
        kind = "mixed" if physical else "postal_delivery"
    elif physical:
        kind = "physical"
    elif unnumbered or _PLACE_FIELDS & values.keys():
        kind = "locality_description"
    else:
        kind = "unspecified"

    hints = _HINTS.get(jurisdiction, ())
    if jurisdiction in _PACIFIC_VILLAGE:
        hints = ("island", "village")
    return {"jurisdiction": jurisdiction, "address_kind": kind,
            "disambiguation_fields": list(hints)}
