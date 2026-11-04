"""Strict native/English address selection for Southern European profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .localized import (
    BilingualAddressResult,
    RegionalAddressRegistry,
    render_regional_bilingual_address,
)
from .profiles import ProfileRegistry


CONFIG_PATH = Path(__file__).with_name("southern_europe_profiles.json")
COUNTRIES = {
    "AD",
    "AL",
    "BA",
    "ES",
    "GI",
    "GR",
    "HR",
    "IT",
    "ME",
    "MK",
    "MT",
    "PT",
    "RS",
    "SI",
    "SM",
    "VA",
}


class SouthernEuropeRegistry(RegionalAddressRegistry):
    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Southern Europe",
            expected_countries=COUNTRIES,
        )


def render_southern_europe_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    southern_europe: SouthernEuropeRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=southern_europe or SouthernEuropeRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["SouthernEuropeRegistry", "render_southern_europe_address"]
