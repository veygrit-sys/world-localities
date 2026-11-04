"""Cross-region native/English address selection for Central Europe."""

from __future__ import annotations

from typing import Mapping

from .eastern_europe import EasternEuropeRegistry
from .localized import (
    BilingualAddressResult,
    RegionalAddressRegistry,
    render_regional_bilingual_address,
)
from .profiles import ProfileRegistry
from .southern_europe import SouthernEuropeRegistry
from .western_europe import WesternEuropeRegistry


COUNTRY_PROFILE_ORIGINS = {
    "AT": "Western Europe",
    "CH": "Western Europe",
    "CZ": "Eastern Europe",
    "DE": "Western Europe",
    "HU": "Eastern Europe",
    "LI": "Western Europe",
    "PL": "Eastern Europe",
    "SI": "Southern Europe",
    "SK": "Eastern Europe",
}
COUNTRIES = set(COUNTRY_PROFILE_ORIGINS)


class CentralEuropeRegistry(RegionalAddressRegistry):
    """Compose the Central European core without copying country profiles."""

    def __init__(self):
        source_registries = {
            "Western Europe": WesternEuropeRegistry(),
            "Eastern Europe": EasternEuropeRegistry(),
            "Southern Europe": SouthernEuropeRegistry(),
        }
        countries = {
            code: source_registries[origin].get(code)
            for code, origin in COUNTRY_PROFILE_ORIGINS.items()
        }
        self.path = None
        self.region_name = "Central Europe"
        self.expected_countries = frozenset(COUNTRIES)
        self.profile_origins = dict(COUNTRY_PROFILE_ORIGINS)
        self.payload = {
            "schema_version": 1,
            "region": self.region_name,
            "reviewed_at": "2026-10-17",
            "purpose": (
                "A non-UN-M49 Central European core crosswalk that reuses "
                "reviewed country profiles from Western, Eastern and Southern "
                "Europe without duplicating templates or source records."
            ),
            "countries": countries,
            "profiles": {},
            "profile_status": {},
        }
        self.countries = countries
        self._verify()


def render_central_europe_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    central_europe: CentralEuropeRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=central_europe or CentralEuropeRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = [
    "COUNTRY_PROFILE_ORIGINS",
    "CentralEuropeRegistry",
    "render_central_europe_address",
]
