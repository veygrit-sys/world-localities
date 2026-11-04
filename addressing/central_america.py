"""Strict domestic-language and English address selection for Central America."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Mapping

from .localized import (
    BilingualAddressResult,
    PostcodeRegionalAddressRegistry,
    render_regional_bilingual_address,
)
from .profiles import ProfileRegistry


CONFIG_PATH = Path(__file__).with_name("central_america_profiles.json")
COUNTRIES = {"BZ", "CR", "GT", "HN", "MX", "NI", "PA", "SV"}


class CentralAmericaRegistry(PostcodeRegionalAddressRegistry):
    """Address policies for every UN M49 Central America country."""

    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Central America",
            expected_countries=COUNTRIES,
        )
        self.locality_registry = self.payload["locality_registry"]
        self.verify_postcode_policies()

    def postcode_variant(self, country_code: str, postcode: str | None) -> str | None:
        """Classify documented transition forms after syntax validation."""

        country_code = country_code.upper()
        if not postcode or not self.validate_postcode(country_code, postcode):
            return None
        compact = postcode.strip().upper()
        if country_code == "HN":
            return (
                "current_numeric"
                if re.fullmatch(r"\d{5}", compact)
                else "legacy_alphanumeric"
            )
        if country_code == "PA":
            if re.fullmatch(r"\d{4}", compact):
                return "legacy_four_digit"
            if re.fullmatch(r"[A-Z0-9]{8}", compact):
                return "geolocated_grid"
            return "geolocated_full"
        return "current"


def render_central_america_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    central_america: CentralAmericaRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=central_america or CentralAmericaRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["CentralAmericaRegistry", "render_central_america_address"]
