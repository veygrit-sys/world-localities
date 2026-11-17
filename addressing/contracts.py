"""Explicit validation and coordinate-precision result contracts.

Evidence is a caller-supplied declaration. Structural checks do not authenticate
an operator, establish freshness, or prove that a carrier accepted a shipment.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, IntEnum
import math
from types import MappingProxyType
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


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _freeze_json(value: Any, active: set[int] | None = None) -> Any:
    """Copy JSON-shaped evidence so callers cannot mutate a checked claim."""
    if value is None or type(value) in {str, bool, int}:
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, (Mapping, list, tuple)):
        active = active if active is not None else set()
        identity = id(value)
        if identity in active:
            raise ValueError("evidence must not contain circular references")
        active.add(identity)
        try:
            if isinstance(value, Mapping):
                if not all(isinstance(key, str) for key in value):
                    raise ValueError("evidence object keys must be strings")
                return MappingProxyType({
                    key: _freeze_json(item, active) for key, item in value.items()
                })
            return tuple(_freeze_json(item, active) for item in value)
        finally:
            active.remove(identity)
    raise ValueError("evidence must contain only finite JSON values")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True)
class ValidationResult:
    status: str
    level: ValidationLevel
    confidence: float
    components: Mapping[str, str]
    evidence: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    warnings: tuple[str, ...] = field(default_factory=tuple)
    location_precision: LocationPrecision = LocationPrecision.UNKNOWN

    def __post_init__(self) -> None:
        if not isinstance(self.status, str) or self.status not in {
            "verified", "corrected", "ambiguous", "unsupported", "no_match"
        }:
            raise ValueError("invalid validation status")
        if type(self.level) is not ValidationLevel:
            raise ValueError("level must be a ValidationLevel")
        if type(self.location_precision) is not LocationPrecision:
            raise ValueError("location_precision must be a LocationPrecision")
        if (
            type(self.confidence) not in {int, float}
            or not 0.0 <= self.confidence <= 1.0
            or not math.isfinite(self.confidence)
        ):
            raise ValueError("confidence must be a finite number between zero and one")
        if not isinstance(self.components, Mapping) or not all(
            _nonempty(key) and isinstance(value, str)
            for key, value in self.components.items()
        ):
            raise ValueError("components must map nonempty string keys to strings")
        if not isinstance(self.warnings, (tuple, list)) or not all(
            isinstance(item, str) for item in self.warnings
        ):
            raise ValueError("warnings must be a sequence of strings")
        if len(set(self.warnings)) != len(self.warnings):
            raise ValueError("warnings must be unique")
        if not isinstance(self.evidence, (tuple, list)) or not all(
            isinstance(item, Mapping) for item in self.evidence
        ):
            raise ValueError("evidence must be a sequence of objects")
        for item in self.evidence:
            for key in ("evidence_type", "source_id", "reference"):
                if key in item and not _nonempty(item[key]):
                    raise ValueError(f"evidence {key} must be a nonempty string")
        if self.level == ValidationLevel.DELIVERABILITY and not any(
            item.get("evidence_type") in {"postal_operator", "carrier"}
            and _nonempty(item.get("source_id"))
            and _nonempty(item.get("reference"))
            for item in self.evidence
        ):
            raise ValueError(
                "deliverability requires postal-operator or carrier evidence "
                "with source_id and reference"
            )
        object.__setattr__(self, "components", MappingProxyType(dict(self.components)))
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(
            self, "evidence", tuple(_freeze_json(item) for item in self.evidence)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "verification_level": self.level.name.lower(),
            "verification_level_number": int(self.level),
            "confidence": self.confidence,
            "components": dict(self.components),
            "evidence": [_thaw_json(item) for item in self.evidence],
            "warnings": list(self.warnings),
            "location_precision": self.location_precision.value,
        }
