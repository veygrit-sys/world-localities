"""Offline lookup in separately attributed snapshots of open address sources."""

from importlib import import_module
import re
import unicodedata


# Keep each publisher's records independent, including when two cover the same street.
LOCAL_SOURCES = {
    "JP": {"gsi": "jp"},
    "TW": {"taipei-doorplates": "taipei"},
    "CN": {"hk-mainland-offices": "cn"},
    "US": {"dc-mar": "us", "osm-dc": "osm"},
    "MU": {"mu-post-offices": "africa"},
}


def sources_for_country(country_code: str) -> dict[str, str]:
    """Return CLI source keys and their bundled adapters for a destination."""
    from .postal_eu import COUNTRIES as postal_countries
    from .un_cities import COUNTRIES as urban_countries

    if not isinstance(country_code, str) or not re.fullmatch(r"[A-Za-z]{2}", country_code):
        raise ValueError("country must contain two ASCII letters")
    country = country_code.upper()
    sources = dict(LOCAL_SOURCES.get(country, {}))
    if country in postal_countries:
        sources["la-poste"] = "postal_eu"
    if country in urban_countries:
        sources["un-urban-centres"] = "un_cities"
    return sources


def _valid_term(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip()) and all(
        unicodedata.category(char) not in {"Cc", "Zl", "Zp"} for char in value
    )


def lookup_reference(country_code: str, query: str, *also: str,
                     source: str | None = None, limit: int = 20) -> dict:
    """Find all terms on the same record of one publisher; only then limit the output."""
    adapters = sources_for_country(country_code)
    if not all(_valid_term(term) for term in (query, *also)):
        raise ValueError("each lookup term must be a nonempty single line of text")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer from 1 to 1000")
    country = country_code.upper()
    if source is not None:
        if source not in adapters:
            raise ValueError(f"source {source!r} is unavailable for {country}")
        adapters = {source: adapters[source]}

    terms = list(dict.fromkeys((query, *also)))
    observed_terms = set()
    records = []
    matched_count = 0
    for key, module_name in adapters.items():
        adapter = import_module(f"{__name__}.{module_name}")
        common = {}
        for index, term in enumerate(terms):
            if module_name == "us":
                # A Washington, DC city query alone matches the whole district.
                found = dict.fromkeys(adapter.lookup_ids(term))
            else:
                candidates = (adapter.lookup(term, country=country) if module_name in {"postal_eu", "un_cities"}
                              else adapter.lookup(term))
                found = {row["record_id"]: row for row in candidates}
            if found:
                observed_terms.add(term)
            if index == 0:
                common = found
            else:
                common = {rid: row for rid, row in common.items() if rid in found}
        matched_count += len(common)
        for rid, row in common.items():
            if len(records) == limit:
                break
            records.append({"source": key, "record": adapter.get_record(rid) if row is None else row})

    if matched_count:
        status = "observed"
    elif not adapters:
        status = "no_source_for_country"
    elif len(observed_terms) == len(terms):
        status = "no_common_record"
    else:
        status = "not_observed_in_snapshot"
    return {
        "country": country, "terms": [query, *also], "sources_checked": list(adapters),
        "status": status, "matching_records": matched_count, "records": records,
        "truncated": matched_count > len(records), "deliverability_verified": False,
    }
