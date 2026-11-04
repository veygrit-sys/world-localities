"""Strict domestic-language and English address selection for Oceania."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .localized import (
    BilingualAddressResult,
    PostcodeRegionalAddressRegistry,
    render_regional_bilingual_address,
)
from .profiles import ProfileRegistry


CONFIG_PATH = Path(__file__).with_name("oceania_profiles.json")
COUNTRIES = {
    "AS",
    "AU",
    "CC",
    "CK",
    "CX",
    "FJ",
    "FM",
    "GU",
    "HM",
    "KI",
    "MH",
    "MP",
    "NC",
    "NF",
    "NR",
    "NU",
    "NZ",
    "PF",
    "PG",
    "PN",
    "PW",
    "SB",
    "TK",
    "TO",
    "TV",
    "UM",
    "VU",
    "WF",
    "WS",
}


class OceaniaRegistry(PostcodeRegionalAddressRegistry):
    """Address policies for every UN M49 Oceania country or territory."""

    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Oceania",
            expected_countries=COUNTRIES,
        )
        self.locality_registry = self.payload["locality_registry"]
        self.verify_postcode_policies()


def render_oceania_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    oceania: OceaniaRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=oceania or OceaniaRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["OceaniaRegistry", "render_oceania_address"]
