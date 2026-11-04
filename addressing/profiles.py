"""Load and validate compiled worldwide address-format profiles."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any


PROFILE_PATH = Path(__file__).with_name("profiles.json")
EXTENSION_PATHS = (
    Path(__file__).with_name("east_asia_profiles.json"),
    Path(__file__).with_name("southeast_asia_profiles.json"),
    Path(__file__).with_name("south_asia_profiles.json"),
    Path(__file__).with_name("central_asia_profiles.json"),
    Path(__file__).with_name("western_asia_profiles.json"),
    Path(__file__).with_name("western_europe_profiles.json"),
    Path(__file__).with_name("southern_europe_profiles.json"),
    Path(__file__).with_name("northern_europe_profiles.json"),
    Path(__file__).with_name("eastern_europe_profiles.json"),
    Path(__file__).with_name("oceania_profiles.json"),
    Path(__file__).with_name("northern_africa_profiles.json"),
    Path(__file__).with_name("eastern_africa_profiles.json"),
    Path(__file__).with_name("middle_africa_profiles.json"),
    Path(__file__).with_name("western_africa_profiles.json"),
    Path(__file__).with_name("southern_africa_profiles.json"),
    Path(__file__).with_name("northern_america_profiles.json"),
    Path(__file__).with_name("central_america_profiles.json"),
    Path(__file__).with_name("caribbean_profiles.json"),
)
CONFIG_FIELDS = {
    "address_template",
    "fallback_template",
    "replace",
    "postformat_replace",
    "add_component",
    "change_country",
    "use_country",
}


@dataclass(frozen=True)
class AddressProfile:
    key: str
    country_code: str
    language: str | None
    config: dict[str, Any]
    inherited_from: str | None = None

    @property
    def template(self) -> str:
        return self.config["address_template"]


class ProfileRegistry:
    def __init__(
        self,
        path: Path = PROFILE_PATH,
        *,
        extension_paths: tuple[Path, ...] = EXTENSION_PATHS,
    ):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError("unsupported address profile schema")
        self.source = payload["source"]
        self.country_codes = tuple(payload["country_codes"])
        self.country_languages = payload["country_languages"]
        self.state_codes = payload["state_codes"]
        self.county_codes = payload["county_codes"]
        self._raw = dict(payload["profiles"])
        self.extensions: list[dict[str, Any]] = []
        self.default_languages: dict[str, str] = {}
        self._extension_new_profiles = 0
        self._extension_overrides = 0
        for extension_path in extension_paths:
            if not extension_path.is_file():
                continue
            extension = json.loads(extension_path.read_text(encoding="utf-8"))
            if extension.get("schema_version") != 1:
                raise ValueError("unsupported address profile extension schema")
            overrides = set(extension.get("overrides", []))
            profiles = extension.get("profiles", {})
            for country_code, policy in extension.get("countries", {}).items():
                default_language = policy.get("default_native_language")
                if default_language:
                    self.default_languages[country_code] = default_language
            if overrides - set(profiles):
                raise ValueError("address profile override missing replacement")
            for key, profile in profiles.items():
                exists = key in self._raw
                if exists != (key in overrides):
                    action = "undeclared override" if exists else "override target missing"
                    raise ValueError(f"{action}: {key}")
                self._raw[key] = profile
                if exists:
                    self._extension_overrides += 1
                else:
                    self._extension_new_profiles += 1
            self.extensions.append(extension)
        self._verify()

    def _resolved_config(self, key: str, seen: set[str] | None = None) -> dict[str, Any]:
        seen = set() if seen is None else set(seen)
        if key in seen:
            raise ValueError("cyclic address profile inheritance")
        seen.add(key)
        raw = self._raw[key]
        parent = raw.get("use_country")
        config = self._resolved_config(parent, seen) if parent else {}
        config.update({name: value for name, value in raw.items() if name in CONFIG_FIELDS})
        config.pop("use_country", None)
        return config

    def get(self, key: str) -> AddressProfile:
        if key not in self._raw:
            raise KeyError(f"unknown address profile: {key}")
        raw = self._raw[key]
        config = self._resolved_config(key)
        if "address_template" not in config:
            raise ValueError(f"address profile has no template: {key}")
        return AddressProfile(
            key=key,
            country_code=raw["country_code"],
            language=raw.get("language"),
            config=config,
            inherited_from=raw.get("use_country"),
        )

    def select(
        self,
        country_code: str,
        *,
        language: str | None = None,
        international: bool = False,
    ) -> AddressProfile:
        country_code = country_code.upper()
        if country_code not in self.country_codes:
            raise KeyError(f"unknown address country: {country_code}")
        language = language.split("-", 1)[0].lower() if language else None
        candidates = []
        if international:
            candidates.append(country_code + "_en")
        else:
            selected_language = language
            if selected_language is None:
                selected_language = self.default_languages.get(country_code)
                if selected_language is None:
                    selected_language = next(
                        iter(self.country_languages.get(country_code, [])), None
                    )
            if selected_language:
                candidates.append(
                    country_code + "_" + selected_language.split("-", 1)[0].lower()
                )
        candidates.append(country_code)
        return self.get(next(key for key in candidates if key in self._raw))

    @staticmethod
    def _code_names(value: str | dict[str, str]) -> tuple[str, ...]:
        if isinstance(value, str):
            return (value,)
        return tuple(value.values())

    def subdivision_code(
        self,
        country_codes: tuple[str, ...],
        value: str,
        *,
        kind: str = "state",
    ) -> str | None:
        mappings = self.state_codes if kind == "state" else self.county_codes
        folded = value.casefold()
        for country_code in country_codes:
            for code, names in mappings.get(country_code, {}).items():
                if folded == code.casefold() or folded in {
                    name.casefold() for name in self._code_names(names)
                }:
                    return code
        return None

    def report(self) -> dict[str, Any]:
        locale_profiles = sum("_" in key for key in self._raw)
        inherited_profiles = sum("use_country" in value for value in self._raw.values())
        return {
            "status": "passed",
            "country_profiles": len(self.country_codes),
            "locale_profiles": locale_profiles,
            "inherited_profiles": inherited_profiles,
            "extension_profiles": sum(
                len(extension["profiles"]) for extension in self.extensions
            ),
            "extension_new_profiles": self._extension_new_profiles,
            "extension_overrides": self._extension_overrides,
            "source_commit": self.source["commit"],
            "source_sha256": self.source["sha256"],
        }

    def _verify(self) -> None:
        if len(self.country_codes) != len(set(self.country_codes)):
            raise ValueError("duplicate address country code")
        if any(not re.fullmatch(r"[A-Z]{2}", code) for code in self.country_codes):
            raise ValueError("invalid address country code")
        if set(self.country_codes) - set(self._raw):
            raise ValueError("country profile missing")
        if any(
            country not in self.country_codes for country in self.country_languages
        ):
            raise ValueError("country-language mapping outside profile coverage")
        for key, raw in self._raw.items():
            if raw.get("country_code") not in self.country_codes:
                raise ValueError(f"profile country mismatch: {key}")
            unexpected = set(raw) - CONFIG_FIELDS - {"country_code", "language"}
            if unexpected:
                raise ValueError(f"unknown profile fields for {key}: {sorted(unexpected)}")
            self.get(key)
