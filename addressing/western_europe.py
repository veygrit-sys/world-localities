"""Strict native/English address selection for Western European profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .localized import (
    BilingualAddressResult,
    RegionalAddressRegistry,
    render_regional_bilingual_address,
)
from .profiles import ProfileRegistry


CONFIG_PATH = Path(__file__).with_name("western_europe_profiles.json")
COUNTRIES = {"AT", "BE", "CH", "DE", "FR", "LI", "LU", "MC", "NL"}


class WesternEuropeRegistry(RegionalAddressRegistry):
    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Western Europe",
            expected_countries=COUNTRIES,
        )


def render_western_europe_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    western_europe: WesternEuropeRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=western_europe or WesternEuropeRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["WesternEuropeRegistry", "render_western_europe_address"]
