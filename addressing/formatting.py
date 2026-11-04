"""Render canonical components using country and language profiles."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping

from .components import CanonicalAddress, canonicalize_components
from .profiles import AddressProfile, ProfileRegistry


FIRST = re.compile(r"{{#first}}(.*?){{/first}}", re.DOTALL)
PLACEHOLDER = re.compile(r"{{{([a-z0-9_]+)}}}")
SPACE = re.compile(r"[ \t]+")


def _python_replacement(value: str) -> str:
    return re.sub(r"\$(\d+)", r"\\g<\1>", value)


def _replace_placeholders(
    template: str, values: Mapping[str, str], used: set[str] | None = None
) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = values.get(key, "")
        if value and used is not None:
            used.add(key)
        return value

    return PLACEHOLDER.sub(replace, template)


def _render_first(
    template: str, values: Mapping[str, str], used: set[str] | None = None
) -> str:
    def choose(match: re.Match[str]) -> str:
        for alternative in match.group(1).split("||"):
            candidate_used: set[str] = set()
            rendered = _replace_placeholders(alternative, values, candidate_used)
            if rendered.strip(" ,\t\n-"):
                if used is not None:
                    used.update(candidate_used)
                return rendered
        return ""

    while FIRST.search(template):
        template = FIRST.sub(choose, template)
    return template


def _apply_component_replacements(
    values: dict[str, str], replacements: list[list[str]]
) -> None:
    for pattern, replacement in replacements:
        component_match = re.fullmatch(r"([a-z_]+)=(.*)", pattern)
        if component_match and component_match.group(1) in values:
            key, expression = component_match.groups()
            values[key] = re.sub(expression, _python_replacement(replacement), values[key])
            continue
        for key, value in list(values.items()):
            values[key] = re.sub(pattern, _python_replacement(replacement), value)


def _add_components(values: dict[str, str], specification: str | None) -> None:
    if not specification:
        return
    key, separator, value = specification.partition("=")
    if not separator:
        raise ValueError("invalid add_component address profile rule")
    values.setdefault(key, value)


def _expand_value(template: str, values: Mapping[str, str]) -> str:
    return re.sub(
        r"\$([a-z_]+)", lambda match: values.get(match.group(1), ""), template
    ).strip()


def _subpremise(values: Mapping[str, str]) -> str:
    if values.get("address_line2"):
        return values["address_line2"]
    if values.get("subpremise"):
        return values["subpremise"]
    return " ".join(
        values[key] for key in ("block", "entrance", "floor", "unit") if values.get(key)
    )


def _normalize_postcode(
    values: dict[str, str], replacements: list[list[str]]
) -> None:
    if not values.get("postcode"):
        return
    candidate = " " + values["postcode"] + "\n"
    for pattern, replacement in replacements:
        candidate = re.sub(pattern, _python_replacement(replacement), candidate)
    normalized = candidate.strip()
    if normalized and "\n" not in normalized:
        values["postcode"] = normalized


def _clean_lines(text: str) -> tuple[str, ...]:
    result = []
    for source_line in text.splitlines():
        line = SPACE.sub(" ", source_line).strip()
        line = re.sub(r"\s+([,;])", r"\1", line).strip(" ,;-")
        if line:
            result.append(line)
    return tuple(result)


@dataclass(frozen=True)
class RenderedAddress:
    text: str
    lines: tuple[str, ...]
    profile_key: str
    country_code: str
    components: dict[str, str]
    extras: dict[str, str]
    unrendered_components: dict[str, str]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "lines": list(self.lines),
            "profile": self.profile_key,
            "country_code": self.country_code,
            "components": dict(self.components),
            "extras": dict(self.extras),
            "unrendered_components": dict(self.unrendered_components),
            "warnings": list(self.warnings),
        }


def render_address(
    components: Mapping[str, str | None] | CanonicalAddress,
    country_code: str,
    *,
    language: str | None = None,
    international: bool = False,
    registry: ProfileRegistry | None = None,
) -> RenderedAddress:
    registry = registry or ProfileRegistry()
    profile: AddressProfile = registry.select(
        country_code, language=language, international=international
    )
    canonical = (
        components
        if isinstance(components, CanonicalAddress)
        else canonicalize_components(components)
    )
    values = dict(canonical.values)
    warnings: list[str] = []
    supplied_country = values.get("country_code")
    if supplied_country and supplied_country != profile.country_code:
        raise ValueError("component country_code does not match selected profile")
    values["country_code"] = profile.country_code
    if values.get("recipient") and not values.get("attention"):
        # address-formatting historically names the addressee slot "attention".
        # Preserve the clearer public component without dropping it.
        values["attention"] = values["recipient"]
    if values.get("address_line1") and not any(
        values.get(key) for key in ("road", "house_number", "house")
    ):
        values["road"] = values["address_line1"]
        warnings.append("opaque_address_line1_rendered_in_delivery_line")
    values["subpremise"] = _subpremise(values)
    _add_components(values, profile.config.get("add_component"))
    _apply_component_replacements(values, profile.config.get("replace", []))
    code_countries = tuple(
        dict.fromkeys(
            value
            for value in (profile.country_code, profile.inherited_from)
            if value
        )
    )
    if values.get("state") and not values.get("state_code"):
        state_code = registry.subdivision_code(code_countries, values["state"])
        if state_code:
            values["state_code"] = state_code
    if values.get("county") and not values.get("county_code"):
        county_code = registry.subdivision_code(
            code_countries, values["county"], kind="county"
        )
        if county_code:
            values["county_code"] = county_code
    if profile.config.get("change_country"):
        values["country"] = _expand_value(profile.config["change_country"], values)
    _normalize_postcode(values, profile.config.get("postformat_replace", []))

    template = profile.template
    if values.get("subpremise") and "{{{subpremise}}}" not in template:
        if "{{{house}}}" in template:
            template = template.replace(
                "{{{house}}}", "{{{house}}}\n{{{subpremise}}}", 1
            )
        else:
            template = "{{{subpremise}}}\n" + template
        warnings.append("generic_subpremise_placement")
    used: set[str] = set()
    rendered = _replace_placeholders(_render_first(template, values, used), values, used)
    for pattern, replacement in profile.config.get("postformat_replace", []):
        rendered = re.sub(pattern, _python_replacement(replacement), rendered)
    lines = _clean_lines(rendered)
    if canonical.extras:
        warnings.append("unrendered_extra_components")
    handled_aliases = {
        "address_line1": "road",
        "address_line2": "subpremise",
        "block": "subpremise",
        "entrance": "subpremise",
        "floor": "subpremise",
        "recipient": "attention",
        "state": "state_code",
        "unit": "subpremise",
    }
    unrendered = {
        key: value
        for key, value in canonical.values.items()
        if key not in {"country_code", "language", "script"}
        and key not in used
        and handled_aliases.get(key) not in used
    }
    if unrendered:
        warnings.append("unrendered_known_components")
    return RenderedAddress(
        text="\n".join(lines),
        lines=lines,
        profile_key=profile.key,
        country_code=profile.country_code,
        components=dict(sorted(values.items())),
        extras=dict(canonical.extras),
        unrendered_components=dict(sorted(unrendered.items())),
        warnings=tuple(warnings),
    )
