"""Source-attributed province display labels for the mainland CN address profile."""

from functools import cache
import json
from pathlib import Path
import re

from .china_reference import load_statistical_provinces

DATA = Path(__file__).with_name("china_reference") / "cldr-subdivision-names.json"


@cache
def subdivision_catalog():
    return json.loads(DATA.read_text(encoding="utf-8"))


def _source_language(tag):
    if tag in {"und", "zh", "zh-CN", "zh-Hans"} or tag.startswith("zh-Hans-"):
        return "zh"
    if re.fullmatch(r"en(?:-Latn)?(?:-(?:[A-Z]{2}|[0-9]{3}))?", tag):
        return "en"
    return None


def _code_subdivision(value, subdivisions):
    code = re.fullmatch(r"(?:CN-?)?([A-Z]{2})", value, re.IGNORECASE | re.ASCII)
    if code:
        key = "cn" + code.group(1).lower()
        return key if key in subdivisions else None
    if re.fullmatch(r"[0-9]{2}", value):
        # Join on a unique exact Chinese label across the two fixed datasets.
        province = load_statistical_provinces().get(value)
        if province:
            keys = [key for key, row in subdivisions.items() if row["zh"] == province["name"]]
            if len(keys) == 1:
                return keys[0]
    return None


def supply_state_labels(
    state: dict[str, str],
    state_codes: dict[str, str],
    missing_languages: list[str],
) -> tuple[tuple[dict[str, str], ...], tuple[str, ...]]:
    """Fill only an exact match; report conflicts between independently recognized inputs."""
    catalog = subdivision_catalog()
    subdivisions = catalog["subdivisions"]
    observed = []
    matched_codes = set()
    all_known = True
    for tag, value in state.items():
        language = _source_language(tag)
        keys = [
            code for code, row in subdivisions.items()
            if language is not None and row[language] == value
        ]
        if len(keys) != 1:
            all_known = False
            continue
        observed.append((language, value))
        matched_codes.add(keys[0])

    warnings = []
    if len(matched_codes) > 1:
        warnings.append("conflicting_province_labels:state")
    for value in set(state_codes.values()):
        code = _code_subdivision(value, subdivisions)
        if code is None:
            all_known = False
        elif matched_codes - {code}:
            warnings.append("conflicting_state_and_state_code")
    if warnings or not all_known or not matched_codes or not missing_languages:
        return (), tuple(warnings)

    code, = matched_codes
    row = subdivisions[code]
    evidence = []
    source_url = f"{catalog['repository']}/blob/{catalog['revision']}/"
    for tag in missing_languages:
        language = "zh" if tag == "zh-Hans" else "en"
        state[tag] = row[language]
        matched_language = next((lang for lang, _ in observed if lang != language), observed[0][0])
        evidence.append({
            "component": "state",
            "language": tag,
            "value": row[language],
            "source_id": catalog["source_id"],
            "source_version": catalog["release"],
            "subdivision_id": code,
            "source_draft_status": row[language + "_draft_status"],
            "reference": source_url + catalog["source_files"][language]["path"],
            "matched_source_locale": matched_language,
            "matched_source_draft_status": row[matched_language + "_draft_status"],
            "matched_reference": source_url + catalog["source_files"][matched_language]["path"],
        })
    return tuple(evidence), ()
