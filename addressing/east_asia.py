"""Strict native/English address selection for East Asian profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .localized import (
    BilingualAddressResult,
    LocalizedAddress,
    MissingLocalizedComponents,
    RegionalAddressRegistry,
    SelectedComponents,
    canonicalize_localized_components,
    normalize_language_tag,
    render_regional_bilingual_address,
    select_localized_components,
)
from .profiles import ProfileRegistry


CONFIG_PATH = Path(__file__).with_name("east_asia_profiles.json")
COUNTRIES = {"CN", "HK", "JP", "KP", "KR", "MN", "MO", "TW"}


class EastAsiaRegistry(RegionalAddressRegistry):
    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Eastern Asia",
            expected_countries=COUNTRIES,
        )


def render_bilingual_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    east_asia: EastAsiaRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=east_asia or EastAsiaRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = [
    "BilingualAddressResult",
    "EastAsiaRegistry",
    "LocalizedAddress",
    "MissingLocalizedComponents",
    "SelectedComponents",
    "canonicalize_localized_components",
    "normalize_language_tag",
    "render_bilingual_address",
    "select_localized_components",
]
