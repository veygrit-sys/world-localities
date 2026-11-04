"""Explicit validation and coordinate-precision result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any


class ValidationLevel(IntEnum):
    FORMAT = 0
    PARSED = 1
    LOCALITY = 2
    POSTAL = 3
    STREET = 4
    PREMISE = 5
    SUBPREMISE = 6
    DELIVERABILITY = 7


class LocationPrecision(str, Enum):
    ENTRANCE = "entrance"
    ROOFTOP = "rooftop"
    BUILDING = "building"
    PARCEL = "parcel"
    INTERPOLATED = "interpolated"
    STREET = "street"
    POSTAL_AREA = "postal_area"
    LOCALITY = "locality"
    ADMINISTRATIVE = "administrative"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ValidationResult:
    status: str
    level: ValidationLevel
    confidence: float
    components: dict[str, str]
    evidence: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    location_precision: LocationPrecision = LocationPrecision.UNKNOWN

    def __post_init__(self) -> None:
        if self.status not in {"verified", "corrected", "ambiguous", "unsupported", "no_match"}:
            raise ValueError("invalid validation status")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between zero and one")
        if self.level == ValidationLevel.DELIVERABILITY and not any(
            item.get("evidence_type") in {"postal_operator", "carrier"}
            for item in self.evidence
        ):
            raise ValueError("deliverability requires postal-operator or carrier evidence")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "verification_level": self.level.name.lower(),
            "verification_level_number": int(self.level),
            "confidence": self.confidence,
            "components": dict(self.components),
            "evidence": [dict(item) for item in self.evidence],
            "warnings": list(self.warnings),
            "location_precision": self.location_precision.value,
        }
