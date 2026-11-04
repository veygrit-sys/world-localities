"""Country-profiled address compatibility and validation contracts."""

from .components import CanonicalAddress, canonicalize_components
from .central_asia import CentralAsiaRegistry, render_central_asia_address
from .central_america import (
    CentralAmericaRegistry,
    render_central_america_address,
)
from .caribbean import CaribbeanRegistry, render_caribbean_address
from .central_europe import CentralEuropeRegistry, render_central_europe_address
from .contracts import LocationPrecision, ValidationLevel, ValidationResult
from .east_asia import (
    BilingualAddressResult,
    EastAsiaRegistry,
    LocalizedAddress,
    MissingLocalizedComponents,
    canonicalize_localized_components,
    render_bilingual_address,
    select_localized_components,
)
from .eastern_africa import EasternAfricaRegistry, render_eastern_africa_address
from .eastern_europe import EasternEuropeRegistry, render_eastern_europe_address
from .formatting import RenderedAddress, render_address
from .localized import (
    PostcodeRegionalAddressRegistry,
    RegionalAddressRegistry,
    render_regional_bilingual_address,
)
from .middle_africa import MiddleAfricaRegistry, render_middle_africa_address
from .northern_america import (
    NorthernAmericaRegistry,
    render_northern_america_address,
)
from .northern_africa import (
    NorthernAfricaRegistry,
    render_northern_africa_address,
)
from .northern_europe import NorthernEuropeRegistry, render_northern_europe_address
from .oceania import OceaniaRegistry, render_oceania_address
from .profiles import AddressProfile, ProfileRegistry
from .south_asia import SouthAsiaRegistry, render_south_asia_address
from .southern_africa import SouthernAfricaRegistry, render_southern_africa_address
from .southern_europe import SouthernEuropeRegistry, render_southern_europe_address
from .southeast_asia import SoutheastAsiaRegistry, render_southeast_asia_address
from .western_asia import WesternAsiaRegistry, render_western_asia_address
from .western_africa import WesternAfricaRegistry, render_western_africa_address
from .western_europe import WesternEuropeRegistry, render_western_europe_address

__all__ = [
    "AddressProfile",
    "CanonicalAddress",
    "BilingualAddressResult",
    "CentralAsiaRegistry",
    "CentralAmericaRegistry",
    "CaribbeanRegistry",
    "CentralEuropeRegistry",
    "EastAsiaRegistry",
    "EasternAfricaRegistry",
    "EasternEuropeRegistry",
    "LocalizedAddress",
    "LocationPrecision",
    "MissingLocalizedComponents",
    "MiddleAfricaRegistry",
    "NorthernAmericaRegistry",
    "NorthernAfricaRegistry",
    "NorthernEuropeRegistry",
    "OceaniaRegistry",
    "PostcodeRegionalAddressRegistry",
    "ProfileRegistry",
    "RegionalAddressRegistry",
    "RenderedAddress",
    "SoutheastAsiaRegistry",
    "SouthAsiaRegistry",
    "SouthernAfricaRegistry",
    "SouthernEuropeRegistry",
    "ValidationLevel",
    "ValidationResult",
    "WesternAsiaRegistry",
    "WesternAfricaRegistry",
    "WesternEuropeRegistry",
    "canonicalize_components",
    "canonicalize_localized_components",
    "render_address",
    "render_bilingual_address",
    "render_central_asia_address",
    "render_central_america_address",
    "render_caribbean_address",
    "render_central_europe_address",
    "render_eastern_africa_address",
    "render_eastern_europe_address",
    "render_middle_africa_address",
    "render_northern_america_address",
    "render_northern_africa_address",
    "render_northern_europe_address",
    "render_oceania_address",
    "render_regional_bilingual_address",
    "render_south_asia_address",
    "render_southern_africa_address",
    "render_southern_europe_address",
    "render_southeast_asia_address",
    "render_western_asia_address",
    "render_western_africa_address",
    "render_western_europe_address",
    "select_localized_components",
]
