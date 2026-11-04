"""Strict domestic-language and English address selection for Middle Africa."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .localized import (
    BilingualAddressResult,
    PostcodeRegionalAddressRegistry,
    render_regional_bilingual_address,
)
from .profiles import ProfileRegistry


CONFIG_PATH = Path(__file__).with_name("middle_africa_profiles.json")
COUNTRIES = {"AO", "CD", "CF", "CG", "CM", "GA", "GQ", "ST", "TD"}


class MiddleAfricaRegistry(PostcodeRegionalAddressRegistry):
    """Address policies for every UN M49 Middle Africa country."""

    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Middle Africa",
            expected_countries=COUNTRIES,
        )
        self.locality_registry = self.payload["locality_registry"]
        self.verify_postcode_policies()


def render_middle_africa_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    middle_africa: MiddleAfricaRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=middle_africa or MiddleAfricaRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["MiddleAfricaRegistry", "render_middle_africa_address"]
