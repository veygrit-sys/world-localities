"""Strict native/English address selection for Northern European profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .localized import (
    BilingualAddressResult,
    RegionalAddressRegistry,
    render_regional_bilingual_address,
)
from .profiles import ProfileRegistry


CONFIG_PATH = Path(__file__).with_name("northern_europe_profiles.json")
COUNTRIES = {
    "AX",
    "DK",
    "EE",
    "FI",
    "FO",
    "GB",
    "GG",
    "IE",
    "IM",
    "IS",
    "JE",
    "LT",
    "LV",
    "NO",
    "SE",
    "SJ",
}


class NorthernEuropeRegistry(RegionalAddressRegistry):
    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Northern Europe",
            expected_countries=COUNTRIES,
        )


def render_northern_europe_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    northern_europe: NorthernEuropeRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=northern_europe or NorthernEuropeRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["NorthernEuropeRegistry", "render_northern_europe_address"]
