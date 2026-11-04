"""Canonical, order-independent address component handling."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Mapping


COMPONENTS = {
    "recipient",
    "attention",
    "organization",
    "po_box",
    "house",
    "house_number",
    "road",
    "address_line1",
    "address_line2",
    "subpremise",
    "unit",
    "floor",
    "entrance",
    "block",
    "lot",
    "place",
    "hamlet",
    "village",
    "neighbourhood",
    "suburb",
    "city_district",
    "postal_city",
    "city",
    "town",
    "municipality",
    "county",
    "state_district",
    "postcode",
    "sorting_code",
    "state",
    "state_code",
    "region",
    "island",
    "archipelago",
    "country",
    "country_code",
    "continent",
    "language",
    "script",
}

ALIASES = {
    "name": "recipient",
    "addressee": "recipient",
    "organisation": "organization",
    "company": "organization",
    "building": "house",
    "street_number": "house_number",
    "housenumber": "house_number",
    "street": "road",
    "street_name": "road",
    "address1": "address_line1",
    "address_1": "address_line1",
    "address_line_1": "address_line1",
    "address2": "address_line2",
    "address_2": "address_line2",
    "address_line_2": "address_line2",
    "apartment": "unit",
    "room": "unit",
    "postcode": "postcode",
    "postal_code": "postcode",
    "zip": "postcode",
    "zip_code": "postcode",
    "province": "state",
    "territory": "state",
    "district": "neighbourhood",
    "quarter": "neighbourhood",
    "borough": "neighbourhood",
    "ward": "neighbourhood",
    "locality": "hamlet",
    "country_name": "country",
    "iso_country_code": "country_code",
}


def normalize_key(key: str) -> str:
    value = re.sub(r"[^0-9a-z]+", "_", key.strip().casefold()).strip("_")
    return ALIASES.get(value, value)


def normalize_value(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("address component values must be strings")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()


@dataclass(frozen=True)
class CanonicalAddress:
    """Canonical values are independent of input field and mapping order."""

    values: dict[str, str]
    extras: dict[str, str]

    def to_dict(self) -> dict[str, dict[str, str]]:
        return {"values": dict(self.values), "extras": dict(self.extras)}


def canonicalize_components(components: Mapping[str, str | None]) -> CanonicalAddress:
    values: dict[str, str] = {}
    extras: dict[str, str] = {}
    for supplied_key, supplied_value in components.items():
        if supplied_value is None:
            continue
        key = normalize_key(supplied_key)
        value = normalize_value(supplied_value)
        if not value:
            continue
        target = values if key in COMPONENTS else extras
        if key in target and target[key] != value:
            raise ValueError(f"conflicting values for address component: {key}")
        target[key] = value
    country_code = values.get("country_code")
    if country_code:
        country_code = country_code.upper()
        if not re.fullmatch(r"[A-Z]{2}", country_code):
            raise ValueError("country_code must be an uppercase two-letter code")
        values["country_code"] = country_code
    return CanonicalAddress(
        values=dict(sorted(values.items())), extras=dict(sorted(extras.items()))
    )
