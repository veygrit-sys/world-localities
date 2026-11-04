"""Strict native/English address selection for Western Asian profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .localized import (
    BilingualAddressResult,
    RegionalAddressRegistry,
    render_regional_bilingual_address,
)
from .profiles import ProfileRegistry


CONFIG_PATH = Path(__file__).with_name("western_asia_profiles.json")
COUNTRIES = {
    "AE",
    "AM",
    "AZ",
    "BH",
    "CY",
    "GE",
    "IL",
    "IQ",
    "JO",
    "KW",
    "LB",
    "OM",
    "PS",
    "QA",
    "SA",
    "SY",
    "TR",
    "YE",
}


class WesternAsiaRegistry(RegionalAddressRegistry):
    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Western Asia",
            expected_countries=COUNTRIES,
        )


def render_western_asia_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    western_asia: WesternAsiaRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=western_asia or WesternAsiaRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["WesternAsiaRegistry", "render_western_asia_address"]
