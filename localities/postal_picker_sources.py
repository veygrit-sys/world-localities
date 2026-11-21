"""Country-specific selection paths from pinned, locally verifiable publications."""

from collections.abc import Iterator
import re

from registries.official.postal_validation import JP_NUMBER_INSTRUCTION

from .open_reference import postal_eu
from .open_reference import us as dc_mar
from .postal import iter_postal_records, load_sources


Steps = tuple[tuple[str, str], ...]
Record = tuple[str, str, Steps, str]
_ZIP5 = re.compile(r"[0-9]{5}")
_JP_FLOOR = re.compile(r"(.+)（([０-９]+階|地階・階層不明)）")
# Mauritius publishes street names and descriptions of the portion covered in
# the same field. Only clearly named streets are transferable to an address.
_MU_STREET_TYPE = re.compile(
    r"\b(?:street|st|road|rd|avenue|ave|lane|impasse|imp|allée|allee|rue|boulevard|drive)\b", re.I
)
_MU_SEGMENT = re.compile(
    r"[^\w '\-]|_|\b(?:to|from|until|up|part|sides?|boundary|between|only|and|"
    r"junction|corner|opposite|near|except|end|towards|along|before|after)\b", re.I
)


def _jp_steps(row: dict[str, str]) -> Steps:
    municipality = row["admin_name2"]
    area = (("area", f"{row['admin_name1']} {municipality}"),)
    town = row["place_name"]
    if not town or town == "以下に掲載がない場合":
        return area
    whole_area = town.removesuffix("一円")
    if whole_area != town and whole_area and municipality.endswith(whole_area):
        return area
    if JP_NUMBER_INSTRUCTION.fullmatch(town):
        return area + (("qualifier", town),)
    # Greedy building match retains e.g. 名駅ミッドランドスクエア（高層棟）.
    floor = _JP_FLOOR.fullmatch(town)
    if floor:
        if floor[2] == "地階・階層不明":
            return area + (("building", floor[1]), ("qualifier", floor[2]))
        return area + (("building", town),)
    name, separator, qualifier = town.partition("（")
    if separator and name and qualifier.endswith("）"):
        return area + (("town", name), ("qualifier", qualifier[:-1]))
    return area + (("town", town),)


def _mu_steps(row: dict[str, str]) -> Steps:
    locality = row["source_locality"].strip()
    sublocality = row["source_sublocality"].strip()
    steps = (("area", locality),)
    if sublocality and sublocality.casefold() != locality.casefold():
        steps += (("town", sublocality),)
    street = row["source_street"].strip()
    if street:
        kind = "street" if _MU_STREET_TYPE.search(street) and not _MU_SEGMENT.search(street) else "qualifier"
        steps += ((kind, street),)
    return steps


def _french_records(countries) -> Iterator[Record]:
    # The source reader checks both La Poste's file and INSEE's overseas
    # crosswalk. Walk the postcode postings once, excluding all name aliases.
    for (country, key), rows in postal_eu._index(postal_eu.DIRECTORY).items():
        if country not in countries or not _ZIP5.fullmatch(key):
            continue
        for row in rows:
            if row["postcode"] != key:
                continue
            commune = row["locality"]
            steps = (("area", commune),)
            line5 = row["line_5"]
            if line5 and line5 != commune:
                steps += (("town", line5),)
            routing_name = row["routing_name"]
            if routing_name and routing_name != commune:
                steps += (("routing_name", routing_name),)
            yield country, key, steps, row["source_id"]


def _dc_steps(address: str) -> Steps:
    # MAR's citywide projection supplies the complete address. Its standard
    # assigns the fraction and REAR to the number. In "A CHESAPEAKE STREET"
    # vs "H R DRIVE" the first letter could be a suffix or the street name.
    parts = address.split()
    if len(parts) >= 4 and parts[0].isascii() and parts[0].isdigit() and parts[-1] in {"NW", "NE", "SW", "SE"}:
        suffix = parts[1] in {"1/2", "REAR"}
        ambiguous = len(parts[1]) == 1 and parts[1].isalpha() and len(parts) > 4
        boundary = 2 if suffix else 1
        if not ambiguous and len(parts) - boundary >= 3:
            return (("street", " ".join(parts[boundary:])), ("house_number", " ".join(parts[:boundary])))
    return (("address", address),)


def iter_extra_records(countries=None) -> Iterator[Record]:
    """Yield paths from single published rows for the selected country codes."""
    covered = {"JP", "US", "MU", *postal_eu.COUNTRIES}
    if countries is not None:
        covered.intersection_update([countries] if isinstance(countries, str) else countries)
    if covered & {"JP", "MU"}:
        for source in load_sources()["sources"]:
            country = source.get("expected_country")
            if country not in covered or not source.get("active_for_lookup", True):
                continue
            if source["format"] == "japanpost_utf_zip":
                for row in iter_postal_records(source):
                    yield country, row["code"], _jp_steps(row), source["id"]
            elif source.get("adapter") == "mu_postal_csv4":
                for row in iter_postal_records(source):
                    if row["code_kind"] == "official_full":
                        yield country, row["code"], _mu_steps(row), source["id"]
    if covered.intersection(postal_eu.COUNTRIES):
        yield from _french_records(covered)
    if "US" in covered:
        for record_id in dc_mar.lookup_ids("DC"):
            row = dc_mar.get_record(record_id)
            code = row["postal_code"]
            if row["state"] == "DC" and row["city"] == "WASHINGTON" and code and _ZIP5.fullmatch(code):
                steps = (("area", "Washington, DC"),) + _dc_steps(row["address"])
                yield "US", code, steps, row["source_id"]
