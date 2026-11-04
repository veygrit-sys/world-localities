"""Strict native/English address selection for Southeast Asian profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .localized import (
    BilingualAddressResult,
    RegionalAddressRegistry,
    render_regional_bilingual_address,
)
from .profiles import ProfileRegistry


CONFIG_PATH = Path(__file__).with_name("southeast_asia_profiles.json")
COUNTRIES = {"BN", "KH", "ID", "LA", "MY", "MM", "PH", "SG", "TH", "TL", "VN"}


class SoutheastAsiaRegistry(RegionalAddressRegistry):
    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="South-eastern Asia",
            expected_countries=COUNTRIES,
        )


def render_southeast_asia_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    southeast_asia: SoutheastAsiaRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=southeast_asia or SoutheastAsiaRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["SoutheastAsiaRegistry", "render_southeast_asia_address"]
