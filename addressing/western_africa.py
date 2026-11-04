"""Strict domestic-language and English address selection for Western Africa."""

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


CONFIG_PATH = Path(__file__).with_name("western_africa_profiles.json")
COUNTRIES = {
    "BF",
    "BJ",
    "CI",
    "CV",
    "GH",
    "GM",
    "GN",
    "GW",
    "LR",
    "ML",
    "MR",
    "NE",
    "NG",
    "SH",
    "SL",
    "SN",
    "TG",
}


class WesternAfricaRegistry(PostcodeRegionalAddressRegistry):
    """Address policies for every UN M49 Western Africa country or area."""

    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Western Africa",
            expected_countries=COUNTRIES,
        )
        self.locality_registry = self.payload["locality_registry"]
        self.verify_postcode_policies()
        self._verify_sorting_code_policies()

    def _verify_sorting_code_policies(self) -> None:
        for country_code, policy in self.countries.items():
            if "sorting_code_pattern" not in policy:
                raise ValueError(f"sorting-code policy missing: {country_code}")
            pattern = policy["sorting_code_pattern"]
            if pattern is not None:
                re.compile(str(pattern))
            if not isinstance(policy.get("sorting_code_required"), bool):
                raise ValueError(f"sorting-code requirement missing: {country_code}")

    def validate_sorting_code(
        self, country_code: str, sorting_code: str | None
    ) -> bool:
        """Check delivery-office code syntax without asserting assignment."""

        policy = self.get(country_code)
        if sorting_code is None or not sorting_code.strip():
            return not policy["sorting_code_required"]
        pattern = policy["sorting_code_pattern"]
        if pattern is None:
            return False
        return (
            re.fullmatch(str(pattern), sorting_code.strip(), re.IGNORECASE)
            is not None
        )


def render_western_africa_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    western_africa: WesternAfricaRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=western_africa or WesternAfricaRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["WesternAfricaRegistry", "render_western_africa_address"]
