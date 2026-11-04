"""Strict domestic-language and English address selection for Northern Africa."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .localized import (
    BilingualAddressResult,
    PostcodeRegionalAddressRegistry,
    render_regional_bilingual_address,
)
from .profiles import ProfileRegistry


CONFIG_PATH = Path(__file__).with_name("northern_africa_profiles.json")
COUNTRIES = {"DZ", "EG", "EH", "LY", "MA", "SD", "TN"}


class NorthernAfricaRegistry(PostcodeRegionalAddressRegistry):
    """Address policies for every UN M49 Northern Africa country or area."""

    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Northern Africa",
            expected_countries=COUNTRIES,
        )
        self.locality_registry = self.payload["locality_registry"]
        self.verify_postcode_policies()


def render_northern_africa_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    northern_africa: NorthernAfricaRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=northern_africa or NorthernAfricaRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["NorthernAfricaRegistry", "render_northern_africa_address"]
