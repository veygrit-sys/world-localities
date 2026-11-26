"""Typed number references for four Wakayama City towns and four housing sites."""
from collections import defaultdict
import csv
from functools import cache
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parent
CITY = "和歌山市"
PREF = "和歌山県"
TOWNS = {"今福2丁目": ("0023002", "frontage"), "今福3丁目": ("0023003", "frontage"),
         "男野芝丁": ("0058000", "parcel"), "八番丁": ("0304000", "parcel")}
# FY2026 prefectural housing guide, printed page 29. These independent entries
# attest to the estate address, even when ABR itself gives only a frontage.
SITES = {("0023002", "frontage", "3-45"): "今福第一", ("0023003", "frontage", "6-22"): "今福第二",
         ("0058000", "parcel", "3"): "雄湊", ("0304000", "parcel", "8"): "城北"}
_NUMBER = re.compile(r"[0-9]+(?:-[0-9]+){0,2}")


def _norm(s):
    s = unicodedata.normalize("NFKC", s).replace(" ", "").replace("−", "-").replace("‐", "-")
    return s.replace("今福二丁目", "今福2丁目").replace("今福三丁目", "今福3丁目")


def _parts(text, force_lot=False):
    text = _norm(text).removeprefix(PREF).removeprefix(CITY)
    text = re.sub(r"^今福([23])-", r"今福\1丁目", text)
    for name, (town_id, default_kind) in TOWNS.items():
        if not text.startswith(name):
            continue
        tail = text[len(name):]
        kind = "parcel" if force_lot or "番地" in tail else default_kind
        if kind == "parcel":
            match = re.fullmatch(r"([0-9]+)番地(?:の?([0-9]+)(?:の([0-9]+))?)?", tail)
        else:
            match = re.fullmatch(r"([0-9]+)番([0-9]+(?:-[0-9]+)?)号", tail)
        number = "-".join(v for v in match.groups() if v) if match else tail
        if _NUMBER.fullmatch(number):
            return town_id, kind, number
    return None


@cache
def _reference():
    by_key = defaultdict(list)
    sources = json.loads((ROOT / "sources.json").read_text(encoding="utf-8"))
    archive = (ROOT / "numbers.csv.gz").read_bytes()
    if hashlib.sha256(archive).hexdigest() != sources["projection_sha256"]:
        raise ValueError("Wakayama projection checksum mismatch")
    with io.StringIO(gzip.decompress(archive).decode("utf-8")) as file:
        for row in csv.DictReader(file):
            by_key[row["machiaza_id"], row["kind"], row["number"]].append(row["official_key"])
    return by_key, sources


def validate_wakayama(values, result):
    line = _norm(values.get("address_line1", ""))
    cities = {"city", "municipality"} & values.keys()
    if not any(_norm(values[k]) == CITY for k in cities) and not line.startswith((CITY, PREF + CITY)):
        return None
    towns = {"town", "neighbourhood"} & values.keys()
    numbers = {"house_number", "lot"} & values.keys()
    representations = []
    if line:
        representations.append(_parts(line, "lot" in numbers))
    for town in sorted(towns):
        for field in sorted(numbers):
            tail = _norm(values[field])
            if field == "house_number" and "block" in values:
                tail = _norm(values["block"]).removesuffix("番") + "番" + tail.removesuffix("号") + "号"
            representations.append(_parts(values[town] + tail, field == "lot"))
    known = {rep for rep in representations if rep is not None}
    if not known:
        return None
    if len(known) > 1 or None in representations:
        return result("conflict", issues=["inconsistent_street_representations"])
    town_id, kind, number = known.pop()
    name = next(name for name, (key, _) in TOWNS.items() if key == town_id)
    if (any(_norm(values[k]) != CITY for k in cities)
            or any(_norm(values[k]) != PREF for k in {"state", "prefecture"} & values.keys())
            or any(_norm(values[k]) not in {name, re.sub(r"[23]丁目$", "", name)} for k in towns)):
        return result("conflict", issues=["municipal_address_component_conflict"])
    # If Line1 is the only complete representation, additional numerical fields
    # still have to agree. Never check a structured number based on Line1 alone.
    if "block" in values and (kind != "frontage" or _norm(values["block"]).removesuffix("番") != number.split("-")[0]):
        return result("conflict", issues=["inconsistent_street_representations"])
    if numbers and not towns:
        for field in numbers:
            test = _parts(name + str(values[field]), field == "lot")
            if test != (town_id, kind, number):
                return result("conflict", issues=["inconsistent_street_representations"])
    by_key, sources = _reference()
    keys = by_key.get((town_id, kind, number))
    if not keys:
        return None
    checked = cities | towns | ({"state", "prefecture"} & values.keys())
    reference = sources["abr"][kind]
    evidence = [{k: reference[k] for k in ("source_id", "url", "snapshot", "attribution", "license")} |
                {"record_id": ":".join(("302015", town_id, key)), "number_kind": kind} for key in keys]
    if "postcode" in values:
        code, row = sources["town_postcodes"][town_id]
        postal_evidence = dict(sources["postal"], record_id=str(row), postal_scope="ordinary_town")
        if _norm(values["postcode"]).replace("-", "") != code:
            return result("conflict", issues=["postcode_differs_from_published_ordinary_town"],
                          evidence=[*evidence, postal_evidence])
        checked.add("postcode")
        evidence.append(postal_evidence)
    # A lot is never an identity claim for the building, even if a housing
    # estate happens to occupy that particular parcel.
    site = SITES.get((town_id, kind, number))
    if site and len(keys) == 1 and "lot" not in values:
        if "house" in values and _norm(values["house"]) != site:
            return result("conflict", issues=["housing_site_name_conflict"], evidence=evidence)
        checked |= {"address_line1", "house_number", "house"} & values.keys()
        if "block" in values and kind == "frontage" and _norm(values["block"]).removesuffix("番") == number.split("-")[0]:
            checked.add("block")
        if _norm(values.get("address_line2", "")) == site:
            checked.add("address_line2")
        evidence.insert(0, dict(sources["housing"], record_id="p29:" + site, record_scope="residential_estate"))
        return result("matched", scope="published_address_point", checked=checked,
                      issues=["housing_estate_address_only"], evidence=evidence, candidate_count=1)
    if kind == "parcel":
        checked |= {"lot"} & values.keys()
        scope, issue = "published_land_parcel", "parcel_is_not_building_evidence"
    else:
        if "block" in values and _norm(values["block"]).removesuffix("番") == number.split("-")[0]:
            checked.add("block")
        scope, issue = "published_street_block", "frontage_is_not_assigned_residence"
    return result("partial", scope=scope, checked=checked, issues=[issue], evidence=evidence)
