"""Strict domestic-language and English address selection for Southern Africa."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .localized import (
    BilingualAddressResult,
    PostcodeRegionalAddressRegistry,
    render_regional_bilingual_address,
)
from .profiles import ProfileRegistry


CONFIG_PATH = Path(__file__).with_name("southern_africa_profiles.json")
COUNTRIES = {"BW", "LS", "NA", "SZ", "ZA"}


class SouthernAfricaRegistry(PostcodeRegionalAddressRegistry):
    """Address policies for every UN M49 Southern Africa country."""

    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Southern Africa",
            expected_countries=COUNTRIES,
        )
        self.locality_registry = self.payload["locality_registry"]
        self.verify_postcode_policies()


def render_southern_africa_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    southern_africa: SouthernAfricaRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=southern_africa or SouthernAfricaRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["SouthernAfricaRegistry", "render_southern_africa_address"]
