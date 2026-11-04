"""Language-safe regional address selection and bilingual rendering."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import unicodedata
from typing import Mapping

from .components import COMPONENTS, normalize_key, normalize_value
from .formatting import RenderedAddress, render_address
from .profiles import ProfileRegistry


LANGUAGE_NEUTRAL_COMPONENTS = {
    "country_code",
    "postcode",
    "sorting_code",
    "state_code",
    "house_number",
    "lot",
}
EVIDENCE_STATUSES = {
    "official_guidance",
    "source_derived_domestic",
    "provisional",
}
DANGEROUS_BIDI_CONTROLS = re.compile("[\u202a-\u202e\u2066-\u2069]")
LATIN_APOSTROPHE_LETTERS = {"\u00aa", "\u00ba", "\u02bb", "\u02bc"}
SCRIPT_UNICODE_NAMES = {
    "Arab": "ARABIC",
    "Armn": "ARMENIAN",
    "Beng": "BENGALI",
    "Cyrl": "CYRILLIC",
    "Deva": "DEVANAGARI",
    "Ethi": "ETHIOPIC",
    "Geor": "GEORGIAN",
    "Grek": "GREEK",
    "Hebr": "HEBREW",
    "Sinh": "SINHALA",
    "Taml": "TAMIL",
    "Thaa": "THAANA",
    "Tibt": "TIBETAN",
    "Tfng": "TIFINAGH",
}


def normalize_language_tag(tag: str) -> str:
    parts = tag.strip().replace("_", "-").split("-")
    if not parts or not re.fullmatch(r"[A-Za-z]{2,3}|und", parts[0]):
        raise ValueError(f"invalid language tag: {tag}")
    normalized = [parts[0].lower()]
    for part in parts[1:]:
        if re.fullmatch(r"[A-Za-z]{4}", part):
            normalized.append(part.title())
        elif re.fullmatch(r"[A-Za-z]{2}|[0-9]{3}", part):
            normalized.append(part.upper())
        elif re.fullmatch(r"[A-Za-z0-9]{4,8}", part):
            normalized.append(part.lower())
        else:
            raise ValueError(f"invalid language tag: {tag}")
    return "-".join(normalized)


def base_language(tag: str) -> str:
    return normalize_language_tag(tag).split("-", 1)[0]


def _script_subtag(tag: str) -> str | None:
    for part in normalize_language_tag(tag).split("-")[1:]:
        if re.fullmatch(r"[A-Z][a-z]{3}", part):
            return part
    return None


def _latin_only(value: str) -> bool:
    return all(
        not unicodedata.category(character).startswith("L")
        or character in LATIN_APOSTROPHE_LETTERS
        or "LATIN" in unicodedata.name(character, "")
        for character in value
    )


def _uses_script(value: str, script: str) -> bool:
    if script == "Latn":
        return _latin_only(value)
    marker = SCRIPT_UNICODE_NAMES.get(script)
    if marker is None:
        raise ValueError(f"unsupported script validation: {script}")
    return all(
        not unicodedata.category(character).startswith("L")
        or marker in unicodedata.name(character, "")
        for character in value
    )


@dataclass(frozen=True)
class LocalizedAddress:
    values: dict[str, dict[str, str]]
    extras: dict[str, dict[str, str]]


@dataclass(frozen=True)
class SelectedComponents:
    values: dict[str, str]
    missing: tuple[str, ...]
    warnings: tuple[str, ...]


class MissingLocalizedComponents(ValueError):
    def __init__(self, language: str, components: tuple[str, ...]):
        self.language = language
        self.components = components
        super().__init__(
            f"missing {language} values for address components: "
            + ", ".join(components)
        )


def canonicalize_localized_components(
    components: Mapping[str, str | None | Mapping[str, str | None]],
) -> LocalizedAddress:
    values: dict[str, dict[str, str]] = {}
    extras: dict[str, dict[str, str]] = {}
    for supplied_key, supplied_value in components.items():
        if supplied_value is None:
            continue
        key = normalize_key(supplied_key)
        if not isinstance(supplied_value, (str, Mapping)):
            raise TypeError("localized component must be a string or language mapping")
        localized = (
            {"und": supplied_value}
            if isinstance(supplied_value, str)
            else dict(supplied_value)
        )
        target = values if key in COMPONENTS else extras
        destination = target.setdefault(key, {})
        for supplied_language, supplied_text in localized.items():
            if supplied_text is None:
                continue
            language = normalize_language_tag(str(supplied_language))
            text = normalize_value(supplied_text)
            if not text:
                continue
            if DANGEROUS_BIDI_CONTROLS.search(text):
                raise ValueError(
                    f"dangerous bidirectional control in address component: {key}"
                )
            if language in destination and destination[language] != text:
                raise ValueError(
                    f"conflicting {language} values for address component: {key}"
                )
            destination[language] = text
        if not destination:
            target.pop(key, None)
    country = values.get("country_code")
    if country:
        distinct = set(country.values())
        if len(distinct) != 1:
            raise ValueError("country_code cannot vary by language")
        code = next(iter(distinct)).upper()
        if not re.fullmatch(r"[A-Z]{2}", code):
            raise ValueError("country_code must be a two-letter code")
        values["country_code"] = {"und": code}
    return LocalizedAddress(
        values={key: dict(sorted(item.items())) for key, item in sorted(values.items())},
        extras={key: dict(sorted(item.items())) for key, item in sorted(extras.items())},
    )


def _choose_language_value(
    localized: Mapping[str, str],
    target_language: str,
    *,
    source_language: str | None,
    neutral: bool,
) -> tuple[str | None, str | None]:
    target = normalize_language_tag(target_language)
    base = base_language(target)
    target_script = _script_subtag(target)
    if target in localized:
        return localized[target], None
    if not target_script and base in localized:
        return localized[base], None
    for language, value in localized.items():
        if base_language(language) != base:
            continue
        candidate_script = _script_subtag(language)
        if target_script and candidate_script != target_script:
            continue
        return value, f"language_variant_fallback:{language}"
    if neutral:
        language, value = next(iter(localized.items()))
        return value, f"language_neutral_fallback:{language}"
    if "und" in localized and source_language:
        source = normalize_language_tag(source_language)
        if base_language(source) == base and (
            not target_script or _script_subtag(source) == target_script
        ):
            return localized["und"], "unlabelled_source_language"
    return None, None


def select_localized_components(
    address: LocalizedAddress,
    target_language: str,
    *,
    source_language: str | None = None,
    expected_script: str | None = None,
) -> SelectedComponents:
    values: dict[str, str] = {}
    missing: list[str] = []
    warnings: list[str] = []
    for key, localized in address.values.items():
        value, warning = _choose_language_value(
            localized,
            target_language,
            source_language=source_language,
            neutral=key in LANGUAGE_NEUTRAL_COMPONENTS,
        )
        if value is None:
            missing.append(key)
            continue
        if base_language(target_language) == "en" and not _latin_only(value):
            raise ValueError(f"English address component is not Latin-script: {key}")
        if expected_script and key not in LANGUAGE_NEUTRAL_COMPONENTS:
            if not _uses_script(value, expected_script):
                raise ValueError(
                    f"{target_language} address component is not "
                    f"{expected_script}-script: {key}"
                )
        values[key] = value
        if warning:
            warnings.append(f"{warning}:{key}")
    return SelectedComponents(
        values=dict(sorted(values.items())),
        missing=tuple(sorted(missing)),
        warnings=tuple(sorted(warnings)),
    )


class RegionalAddressRegistry:
    """Validated policy and profile registry for one geographic region."""

    def __init__(
        self,
        path: Path,
        *,
        region_name: str,
        expected_countries: set[str],
    ):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != 1:
            raise ValueError(f"unsupported {region_name} addressing schema")
        if payload.get("region") != region_name:
            raise ValueError(f"{region_name} region label mismatch")
        self.path = path
        self.region_name = region_name
        self.expected_countries = frozenset(expected_countries)
        self.payload = payload
        self.countries = payload["countries"]
        self._verify()

    def get(self, country_code: str) -> dict[str, object]:
        country_code = country_code.upper()
        if country_code not in self.countries:
            raise KeyError(
                f"country is outside {self.region_name} profile: {country_code}"
            )
        return self.countries[country_code]

    def report(self) -> dict[str, object]:
        provisional = sorted(
            code
            for code, item in self.countries.items()
            if item["evidence_status"] == "provisional"
        )
        return {
            "status": "passed",
            "reviewed_at": self.payload["reviewed_at"],
            "countries": len(self.countries),
            "native_language_variants": sum(
                len(item["native_languages"]) for item in self.countries.values()
            ),
            "english_profiles": sum(
                item["english_profile"].endswith("_en")
                for item in self.countries.values()
            ),
            "provisional_countries": provisional,
        }

    def _verify(self) -> None:
        profiles = ProfileRegistry()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.payload.get("reviewed_at", "")):
            raise ValueError(f"invalid {self.region_name} review date")
        if set(self.countries) != self.expected_countries:
            raise ValueError(f"{self.region_name} country coverage mismatch")
        profile_status = self.payload.get("profile_status", {})
        if set(profile_status) != set(self.payload.get("profiles", {})):
            raise ValueError(f"{self.region_name} profile status coverage mismatch")
        if set(profile_status.values()) - EVIDENCE_STATUSES:
            raise ValueError(f"invalid {self.region_name} profile evidence status")
        for code, item in self.countries.items():
            native = item["default_native_language"]
            native_languages = item["native_languages"]
            if native not in native_languages:
                raise ValueError(f"invalid default native language: {code}")
            expected_profiles = item.get("native_profiles", {})
            if set(expected_profiles) != set(native_languages):
                raise ValueError(f"native profile coverage mismatch: {code}")
            for language, profile_key in expected_profiles.items():
                if profiles.select(code, language=language).key != profile_key:
                    raise ValueError(
                        f"native profile selection mismatch: {code}/{language}"
                    )
            if item.get("native_profile") != expected_profiles[native]:
                raise ValueError(f"default native profile mismatch: {code}")
            if profiles.select(code, international=True).key != item["english_profile"]:
                raise ValueError(f"English profile selection mismatch: {code}")
            if "en" not in item["country_names"]:
                raise ValueError(f"English country name missing: {code}")
            for language in native_languages:
                if language not in item["country_names"]:
                    raise ValueError(f"native country name missing: {code}/{language}")
            if item["evidence_status"] not in EVIDENCE_STATUSES:
                raise ValueError(f"invalid country evidence status: {code}")
            native_scripts = item.get("native_scripts", {})
            if native_scripts and set(native_scripts) != set(native_languages):
                raise ValueError(f"native script coverage mismatch: {code}")
            if set(native_scripts.values()) - ({"Latn"} | set(SCRIPT_UNICODE_NAMES)):
                raise ValueError(f"unsupported native script: {code}")
            if not item["romanization_policy"]:
                raise ValueError(f"romanization policy missing: {code}")
            if not item["sources"]:
                raise ValueError(f"address sources missing: {code}")
            for source in item["sources"]:
                if set(source) != {"authority", "url", "scope"}:
                    raise ValueError(f"invalid address source fields: {code}")
                if not source["url"].startswith("https://"):
                    raise ValueError(f"non-HTTPS address source: {code}")


class PostcodeRegionalAddressRegistry(RegionalAddressRegistry):
    """Regional policies with explicit postcode syntax and requirement flags."""

    def verify_postcode_policies(self) -> None:
        for country_code, policy in self.countries.items():
            if "postcode_pattern" not in policy:
                raise ValueError(f"postcode policy missing: {country_code}")
            pattern = policy["postcode_pattern"]
            if pattern is not None:
                re.compile(str(pattern))
            if not isinstance(policy.get("postcode_required"), bool):
                raise ValueError(f"postcode requirement missing: {country_code}")

    def validate_postcode(self, country_code: str, postcode: str | None) -> bool:
        """Check syntax only; this does not assert that a code was assigned."""

        policy = self.get(country_code)
        if postcode is None or not postcode.strip():
            return not policy["postcode_required"]
        pattern = policy["postcode_pattern"]
        if pattern is None:
            return False
        return re.fullmatch(str(pattern), postcode.strip(), re.IGNORECASE) is not None


@dataclass(frozen=True)
class BilingualAddressResult:
    country_code: str
    native_language: str
    native: RenderedAddress
    english: RenderedAddress
    warnings: tuple[str, ...]
    untranslated_extras: dict[str, dict[str, str]]

    def to_dict(self) -> dict[str, object]:
        return {
            "country_code": self.country_code,
            "native_language": self.native_language,
            "native": self.native.to_dict(),
            "english": self.english.to_dict(),
            "warnings": list(self.warnings),
            "untranslated_extras": self.untranslated_extras,
        }


def render_regional_bilingual_address(
    components: Mapping[str, str | None | Mapping[str, str | None]],
    country_code: str,
    *,
    region: RegionalAddressRegistry,
    native_language: str | None = None,
    strict: bool = True,
    registry: ProfileRegistry | None = None,
) -> BilingualAddressResult:
    registry = registry or ProfileRegistry()
    country_code = country_code.upper()
    policy = region.get(country_code)
    native_language = normalize_language_tag(
        native_language or str(policy["default_native_language"])
    )
    if native_language not in policy["native_languages"]:
        raise ValueError(f"unsupported native language for {country_code}")
    localized = canonicalize_localized_components(components)
    values = {key: dict(item) for key, item in localized.values.items()}
    supplied_code = values.get("country_code", {}).get("und")
    if supplied_code and supplied_code != country_code:
        raise ValueError("component country_code does not match selected country")
    values["country_code"] = {"und": country_code}
    values.setdefault("country", {}).update(
        {
            language: value
            for language, value in policy["country_names"].items()
            if language not in values.get("country", {})
        }
    )
    localized = LocalizedAddress(values=values, extras=localized.extras)
    native = select_localized_components(
        localized,
        native_language,
        source_language=native_language,
        expected_script=policy.get("native_scripts", {}).get(native_language),
    )
    english = select_localized_components(localized, "en")
    if strict and native.missing:
        raise MissingLocalizedComponents(native_language, native.missing)
    if strict and english.missing:
        raise MissingLocalizedComponents("en", english.missing)
    native_rendered = render_address(
        native.values,
        country_code,
        language=base_language(native_language),
        registry=registry,
    )
    english_rendered = render_address(
        english.values,
        country_code,
        language="en",
        international=True,
        registry=registry,
    )
    warnings = list(native.warnings + english.warnings)
    warnings.extend(f"missing_native:{key}" for key in native.missing)
    warnings.extend(f"missing_english:{key}" for key in english.missing)
    if localized.extras:
        warnings.append("localized_extra_components_not_rendered")
    if policy["evidence_status"] == "provisional":
        warnings.append("provisional_country_profile")
    return BilingualAddressResult(
        country_code=country_code,
        native_language=native_language,
        native=native_rendered,
        english=english_rendered,
        warnings=tuple(sorted(set(warnings))),
        untranslated_extras=localized.extras,
    )
