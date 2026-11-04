"""Strict domestic-language and English address selection for the Caribbean."""

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


CONFIG_PATH = Path(__file__).with_name("caribbean_profiles.json")
COUNTRIES = {
    "AG",
    "AI",
    "AW",
    "BB",
    "BL",
    "BQ",
    "BS",
    "CU",
    "CW",
    "DM",
    "DO",
    "GD",
    "GP",
    "HT",
    "JM",
    "KN",
    "KY",
    "LC",
    "MF",
    "MQ",
    "MS",
    "PR",
    "SX",
    "TC",
    "TT",
    "VC",
    "VG",
    "VI",
}


class CaribbeanRegistry(PostcodeRegionalAddressRegistry):
    """Address policies for every UN M49 Caribbean country or area."""

    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Caribbean",
            expected_countries=COUNTRIES,
        )
        self.locality_registry = self.payload["locality_registry"]
        self.verify_postcode_policies()

    def postcode_variant(self, country_code: str, postcode: str | None) -> str | None:
        """Classify fixed, extended and ordinary forms after syntax validation."""

        country_code = country_code.upper()
        if not postcode or not self.validate_postcode(country_code, postcode):
            return None
        compact = postcode.strip().upper()
        if country_code in {"AI", "TC"}:
            return "territory_fixed"
        if country_code in {"PR", "VI"}:
            return "zip_plus_4" if re.fullmatch(r"\d{5}-\d{4}", compact) else "zip_5"
        return "current"

    def validate_cayman_island_route(
        self, postcode: str | None, island: str | None
    ) -> bool:
        """Check the KY island digit against an explicitly supplied island name."""

        if not postcode or not island or not self.validate_postcode("KY", postcode):
            return False
        island_codes = {
            "grand cayman": "1",
            "cayman brac": "2",
            "little cayman": "3",
        }
        expected = island_codes.get(island.strip().casefold())
        match = re.fullmatch(r"KY([1-3])-\d{4}", postcode.strip(), re.IGNORECASE)
        return bool(expected and match and match.group(1) == expected)


def render_caribbean_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    caribbean: CaribbeanRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=caribbean or CaribbeanRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["CaribbeanRegistry", "render_caribbean_address"]
