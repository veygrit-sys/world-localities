"""Bounded physical addresses published by the named public institutions."""
from functools import cache
import hashlib
import json
from pathlib import Path

from ..published_points import key


@cache
def _load():
    directory = Path(__file__).parent
    manifest = json.loads((directory / "source.json").read_bytes())
    projection = (directory / "offices.json").read_bytes()
    if hashlib.sha256(projection).hexdigest() != manifest["projection_sha256"]:
        raise ValueError("regional office projection checksum mismatch")
    by_country = {}
    for row in json.loads(projection):
        by_country.setdefault(row["country"], []).append(row)
    return by_country, manifest


def _matches(value, observed):
    labels = observed if isinstance(observed, list) else [observed]
    return any(key(value) == key(label) for label in labels)


def _evidence(row, manifest):
    evidence = dict(manifest["publishers"][row["publisher"]], url=row["url"],
                    record_id=row["id"], snapshot=manifest["snapshot"],
                    projection_sha256=manifest["projection_sha256"])
    if "corroborating_url" in row:
        evidence["corroborating_url"] = row["corroborating_url"]
    return evidence


def validate_office(country, values, result):
    """A physical location requires a named facility, locality and matching primary address."""
    if "po_box" in values or not ({"house", "organization", "address_line2"} & values.keys()):
        return None
    by_country, manifest = _load()
    candidates = []
    conflicts = []
    for row in by_country.get(country, ()):
        observed = row["fields"]
        checked = {field for field in observed.keys() & values.keys()
                   if _matches(values[field], observed[field])}
        # A wallet's supplementary line may name the institution/building.
        # Compare the entire value on this same source record; unit text and
        # arbitrary notes cannot satisfy the facility-name discriminator.
        named = bool({"house", "organization"} & checked)
        if "address_line2" in values and any(_matches(values["address_line2"], observed[field])
                                             for field in ("house", "organization") if field in observed):
            checked.add("address_line2")
            named = True
        # Some countries print a suburb as the postal locality. A wallet
        # locality may use that name when the publisher omits a distinct city.
        if "city" in values and "city" not in observed and "suburb" in observed and _matches(values["city"], observed["suburb"]):
            checked.add("city")
        if "state" in values and "state" not in observed and "state_code" in observed and _matches(values["state"], observed["state_code"]):
            checked.add("state")
        if not named or not ({"city", "suburb"} & checked):
            continue
        has_address = "address_line1" in checked or (
            "road" in checked and ("house_number" not in observed or "house_number" in checked))
        if not has_address:
            continue
        # A house number on a source that names only a road cannot identify this office.
        if "house_number" in values and "house_number" not in observed:
            continue
        evidence = _evidence(row, manifest)
        if (observed.keys() & values.keys()) - checked:
            conflicts.append(evidence)
            continue
        candidates.append((checked, evidence, set(row.get("withheld", ()))))
    if not candidates:
        if conflicts:
            return result("conflict", issues=["published_office_component_conflict"],
                          evidence=conflicts, candidate_count=0)
        return None
    checked = set.intersection(*(fields for fields, _, _ in candidates))
    status = "matched" if len(candidates) == 1 else "ambiguous"
    issues = ["office_sources_disagree_on_supplied_fields"] if any(
        withheld & values.keys() for _, _, withheld in candidates) else []
    return result(status, scope="published_office_address", checked=checked, issues=issues,
                  evidence=[item for _, item, _ in candidates], candidate_count=len(candidates))
