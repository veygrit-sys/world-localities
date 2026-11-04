"""Strict native/English address selection for Eastern European profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .localized import (
    BilingualAddressResult,
    RegionalAddressRegistry,
    render_regional_bilingual_address,
)
from .profiles import ProfileRegistry


CONFIG_PATH = Path(__file__).with_name("eastern_europe_profiles.json")
COUNTRIES = {
    "BG",
    "BY",
    "CZ",
    "HU",
    "MD",
    "PL",
    "RO",
    "RU",
    "SK",
    "UA",
}


class EasternEuropeRegistry(RegionalAddressRegistry):
    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Eastern Europe",
            expected_countries=COUNTRIES,
        )


def render_eastern_europe_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    eastern_europe: EasternEuropeRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=eastern_europe or EasternEuropeRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["EasternEuropeRegistry", "render_eastern_europe_address"]
