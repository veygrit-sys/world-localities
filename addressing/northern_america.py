"""Strict domestic-language and English address selection for Northern America."""

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


CONFIG_PATH = Path(__file__).with_name("northern_america_profiles.json")
COUNTRIES = {"BM", "CA", "GL", "PM", "US"}


class NorthernAmericaRegistry(PostcodeRegionalAddressRegistry):
    """Address policies for every UN M49 Northern America country or area."""

    def __init__(self, path: Path = CONFIG_PATH):
        super().__init__(
            path,
            region_name="Northern America",
            expected_countries=COUNTRIES,
        )
        self.locality_registry = self.payload["locality_registry"]
        self.verify_postcode_policies()

    def validate_bermuda_po_box_route(
        self, postcode: str | None, po_box: str | None
    ) -> bool:
        """Check the repeated Bermuda delivery-office prefix without assigning it."""

        if not postcode or not po_box or not self.validate_postcode("BM", postcode):
            return False
        compact_postcode = re.sub(r"\s+", "", postcode).upper()
        if not re.fullmatch(r"[A-Z]{4}", compact_postcode):
            return False
        match = re.fullmatch(
            r"P\.?\s*O\.?\s+BOX\s+([A-Z]{2})\s+[A-Z0-9-]+",
            po_box.strip(),
            re.IGNORECASE,
        )
        return bool(match and match.group(1).upper() == compact_postcode[:2])


def render_northern_america_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
    northern_america: NorthernAmericaRegistry | None = None,
) -> BilingualAddressResult:
    return render_regional_bilingual_address(
        components,
        country_code,
        region=northern_america or NorthernAmericaRegistry(),
        native_language=native_language,
        strict=strict,
        registry=registry,
    )


__all__ = ["NorthernAmericaRegistry", "render_northern_america_address"]
