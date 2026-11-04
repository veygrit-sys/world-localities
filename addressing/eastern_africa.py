"""Strict domestic-language and English address selection for Eastern Africa."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .localized import (
    BilingualAddressResult,
    PostcodeRegionalAddressRegistry,
    render_regional_bilingual_address,
)
from .profiles import ProfileRegistry


CONFIG_PATH = Path(__file__).with_name("eastern_africa_profiles.json")
COUNTRIES = {
    "BI", "DJ", "ER", "ET", "IO", "KE", "KM", "MG", "MU", "MW", "MZ",
    "RE", "RW", "SC", "SO", "SS", "TF", "TZ", "UG", "YT", "ZM", "ZW",
}


class EasternAfricaRegistry(PostcodeRegionalAddressRegistry):
    """Address policies for every UN M49 Eastern Africa country or area."""

    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Eastern Africa",
            expected_countries=COUNTRIES,
        )
        self.locality_registry = self.payload["locality_registry"]
        self.verify_postcode_policies()


def render_eastern_africa_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    eastern_africa: EasternAfricaRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=eastern_africa or EasternAfricaRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["EasternAfricaRegistry", "render_eastern_africa_address"]
