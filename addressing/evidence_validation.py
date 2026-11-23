"""Offline, role-aware validation of the supplied fields against pinned observations.

A match names its maximum scope. A source miss is never evidence of nonexistence;
no bundled source can certify carrier deliverability.
"""
from __future__ import annotations

from collections import defaultdict, namedtuple
from collections.abc import Mapping
from functools import cache
import json
from pathlib import Path
import re
from threading import Lock
import unicodedata

from localities.open_reference import cn, postal_eu, us
from localities.postal import ROOT, iter_postal_records, load_sources
from registries.official.postal_validation import _jp_ward_labels, _jp_wards, JP_NUMBER_INSTRUCTION
from .components import canonicalize_components, normalize_key


_IDENTITY = {"recipient", "attention", "organization", "language", "script"}
_MUNICIPAL = {"city", "municipality", "postal_city"}
_BLOCKING = {"conflict", "invalid_format"}
_EVIDENCE_LIMIT = 8
_mar_lock = Lock()


def _key(value):
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


@cache
def _country_names():
    names = defaultdict(set)
    for row in json.loads((ROOT / "countries/catalog.json").read_bytes())["countries"]:
        for name in (row["name"], row["code"]):
            names[_key(name)].add(row["code"])
    for path in Path(__file__).parent.glob("*_profiles.json"):
        for code, profile in json.loads(path.read_bytes()).get("countries", {}).items():
            for name in profile.get("country_names", {}).values():
                names[_key(name)].add(code)
    for name, code in (("USA", "US"), ("United States of America", "US"), ("中國", "CN")):
        names[_key(name)].add(code)
    return names


def _result(country, values, status, *, scope=None, checked=(), issues=(), evidence=(), total=None):
    # Company is identity except where a named Japan Post business assignment
    # explicitly requires and verifies that same company.
    considered = (set(values) - _IDENTITY) | (set(values) & set(checked) & {"organization"})
    checked = set(checked) & considered
    unverified = considered - checked
    if status == "matched" and unverified:
        status = "partial"
    return {
        "country": country, "status": status, "matched_scope": scope,
        "verified_fields": sorted(checked), "unverified_fields": sorted(unverified),
        "ignored_fields": sorted((set(values) & _IDENTITY) - checked), "issues": sorted(set(issues)),
        "evidence": list(evidence)[:_EVIDENCE_LIMIT],
        "evidence_count": len(evidence) if total is None else total,
        "blocking_conflict": status in _BLOCKING, "deliverability_verified": False,
    }


@cache
def _mar_source():
    source = json.loads((Path(us.__file__).parent / "citywide/citywide.json").read_bytes())
    return {"source_id": source["source_id"], "snapshot": source["retrieved_utc"],
            "url": source["catalog_url"], "sha256": source["sources"]["all.csv"]["sha256"],
            "attribution": source["publisher"], "license": source["license"]}


def _us(values, result):
    # A generic street can exist in other states. Require a DC discriminator
    # before reporting a point/conflict from this city-specific source.
    state_fields = {"state_code", "state"} & values.keys()
    dc = {"dc", "district of columbia", "d.c."}
    dc_fields = {k for k in state_fields if _key(values[k]) in dc}
    if dc_fields and dc_fields != state_fields:
        return result("conflict", issues=["inconsistent_state_fields"])
    postcode = values.get("postcode", "")
    if not dc_fields and (state_fields or not postcode):
        return None
    structured = ("house_number" in values and "road" in values)
    line = values.get("address_line1")
    if structured:
        assembled = values["house_number"] + " " + values["road"]
        if line and us._key(assembled) != us._key(line):
            # A freeform line can include extra unit/building information.
            # Do not guess its meaning or silently prefer one representation.
            return result("conflict", issues=["inconsistent_street_representations"])
        line = assembled
    # A postcode, city, or namespaced record ID must never satisfy the address slot.
    if not line or not re.match(r"^[0-9]+\S*\s+\S", line):
        return None
    with _mar_lock:
        ids = us.lookup_ids(line)
    matches = [us.get_record(i) for i in ids]
    rows = [r for r in matches if us._key(r["address"]) == us._key(line)]
    if not rows:
        return result("not_observed", issues=["address_point_not_observed"]) if dc_fields else None
    if not dc_fields and not any(r["postal_code"] == postcode[:5] for r in rows):
        return None
    fields = dc_fields | ({"address_line1"} & values.keys())
    cities = _MUNICIPAL & values.keys()
    filtered = [r for r in rows if all(_key(values[k]) == _key(r["city"]) for k in cities)
                and not (postcode and r["postal_code"] and postcode[:5] != r["postal_code"])]
    if not filtered:
        return result("conflict", issues=["address_point_component_conflict"],
                      evidence=[dict(_mar_source(), record_id=r["record_id"]) for r in rows])
    # Joining values into the right string cannot establish the boundary
    # between the street and number. MAR fractions, REAR and ambiguous letter
    # prefixes require the same conservative parser used by the address picker.
    from localities.postal_picker_sources import _dc_steps
    compared = {"road", "house_number"} & values.keys()
    compatible = []
    for r in filtered:
        parts = dict(_dc_steps(r["address"]))
        if "house_number" not in parts:
            compatible.append((r, set()))
            continue
        expected = {"house_number": _key(parts["house_number"]), "road": us._key("1 " + parts["street"])}
        if all((_key(values[k]) if k == "house_number" else us._key("1 " + values[k])) == expected[k]
               for k in compared):
            compatible.append((r, compared))
    if not compatible:
        return result("conflict", issues=["inconsistent_street_representations"])
    fields.update(set.intersection(*(c[1] for c in compatible)))
    filtered = [c[0] for c in compatible]
    fields.update(cities)
    if postcode and len(postcode) == 5 and all(r["postal_code"] == postcode for r in filtered):
        fields.add("postcode")
    return result("matched" if len(filtered) == 1 else "ambiguous", scope="published_address_point",
                  checked=fields, issues=["zip_plus_four_unverified"] if len(postcode) > 5 else (),
                  evidence=[dict(_mar_source(), record_id=r["record_id"]) for r in filtered])


def _cn(values, result):
    line = values.get("address_line1")
    if not line:
        return None
    rows = [r for r in cn.lookup(line) if any(_key(v) == _key(line) for v in r["address"].values())]
    if not rows:
        return result("not_observed", issues=["published_office_address_not_observed"])
    code = values.get("postcode")
    eligible = [r for r in rows if not code or r["postcode"] == code]
    def evidence(rows):
        return [{"source_id": r["source_id"], "record_id": r["record_id"], "url": r["source_url"],
                 "snapshot": r["source_updated_on"], "attribution": r["attribution"],
                 "terms_url": r["terms_url"]} for r in rows]
    if not eligible:
        return result("conflict", issues=["office_postcode_conflict"], evidence=evidence(rows))
    return result("matched" if len(eligible) == 1 else "ambiguous", scope="published_office_address",
                  checked={"address_line1", "postcode"}, evidence=evidence(eligible))


# Keep a compact postcode posting list once per process, not a nationwide scan
# per request or a cache keyed by user addresses. The lock bounds cold-start memory.
_jp_lock = Lock()


_JpPosting = namedtuple("_JpPosting", "source_id row prefecture municipality district town organization ward_ref postal_use detail")
# Only parcels whose published business detail is a single three-part number
# can be promoted. Building descriptions, subarea ranges, PO boxes and chome
# alone remain usable as postal locality evidence.
_JP_PREMISE = re.compile(r"(?:[0-9]+丁目[0-9]+(?:-|番)[0-9]+号?|[0-9]+-[0-9]+-[0-9]+)")
_JP_WIDTH = str.maketrans("０１２３４５６７８９－", "0123456789-")


def _jp_detail(value):
    return value.translate(_JP_WIDTH)


@cache
def _jp_index():
    postings = defaultdict(list)
    wards, ward_source = _jp_wards(ROOT)
    sources = {}
    areas = {}
    def intern_labels(labels):
        key = tuple(labels)
        return areas.setdefault(key, key)
    for s in load_sources()["sources"]:
        if s["format"] not in {"japanpost_utf_zip", "japanpost_business_zip"} or not s.get("active_for_lookup", True):
            continue
        sources[s["id"]] = {"source_id": s["id"], "url": s["download_url"], "sha256": s["sha256"],
                            "snapshot": s["published_on"], "attribution": s["provider"], "terms_url": s["terms"]}
        for r in iter_postal_records(s):
            ordinary = s["format"] == "japanpost_utf_zip"
            fields = {"prefecture": [r["admin_name1"]], "municipality": [r["admin_name2"]]}
            if ordinary:
                fields["prefecture"].append(r["source_col_4"])
                fields["municipality"].append(r["source_col_5"])
            ward = _jp_ward_labels(wards.get(r["admin_code2"]), r, fields)
            town = r["place_name"]
            whole = town.removesuffix("一円")
            instruction = (town == "以下に掲載がない場合" or JP_NUMBER_INSTRUCTION.fullmatch(town)
                           or (whole and whole != town and r["admin_name2"].endswith(whole)))
            # Intern repeated administrative labels in this fixed publisher snapshot.
            area = intern_labels(fields["prefecture"])
            municipality = intern_labels(fields["municipality"])
            district = intern_labels(fields.get("city_district", ()))
            town_labels = () if instruction or not town else (town, r["source_col_6"]) if ordinary else (town,)
            postings[r["code"]].append(_JpPosting(
                s["id"], r["source_row"], area, municipality, district, town_labels,
                r.get("organization"), ward and ward["source_row"], r.get("postal_use", "ordinary"),
                r.get("source_col_7", "") if not ordinary else "",
            ))
    if not postings:
        raise ValueError("no active Japan Post observation sources")
    return postings, sources, ward_source


def _jp(values, result):
    if not values.get("postcode"):
        return result("insufficient_input", issues=["postcode_required_for_reference"])
    with _jp_lock:
        postings, sources, ward_source = _jp_index()
    rows = postings.get(_jp_detail(values["postcode"]).replace("-", ""), ())
    if not rows:
        return result("not_observed", issues=["postcode_not_observed"])
    query = {"state": "prefecture", "prefecture": "prefecture", "city": "municipality",
             "municipality": "municipality", "postal_city": "municipality", "city_district": "district",
             "town": "town", "neighbourhood": "town"}
    candidates = []
    for row in rows:
        checked = {"postcode"}
        issues = set()
        for k, slot in query.items():
            if k not in values:
                continue
            value = _key(values[k])
            labels = [_key(label) for label in getattr(row, slot)]
            # Latin aliases are not attested by these Japanese snapshots.
            if value in labels:
                if slot == "town" and any("（" in lbl for lbl in labels):
                    issues.add("postal_qualifier_unverified")
                else:
                    checked.add(k)
            elif not labels or (any("LATIN" in unicodedata.name(c, "") for c in value)
                                and not any(any("LATIN" in unicodedata.name(c, "") for c in lbl) for lbl in labels)):
                issues.add("place_label_unverified")
            elif slot == "town" and any(label.partition("（")[0] == value for label in labels):
                issues.add("postal_qualifier_unverified")
            else:
                break
        else:
            office = False
            if row.organization:
                if "organization" not in values:
                    issues.add("assigned_organization_unverified")
                elif _key(values["organization"]) != _key(row.organization):
                    continue
                else:
                    checked.add("organization")
                detail = _jp_detail(row.detail)
                # A city name alone omits the ward in designated cities.
                full_city = any(_key(values[k]) == _key(row.municipality[0]) for k in checked & _MUNICIPAL)
                city_ward = bool(checked & _MUNICIPAL) and "city_district" in checked
                qualified = (row.postal_use == "business" and "organization" in checked and row.town
                             and _JP_PREMISE.fullmatch(detail) and not issues
                             and bool(checked & {"prefecture", "state"}) and (full_city or city_ward))
                if qualified:
                    # Validate both representations independently if both are supplied.
                    # Never treat an apartment, range, agency PO box or building prefix as an exact number.
                    local_line = row.town[0] + detail
                    if "house_number" in values:
                        if _jp_detail(values["house_number"]) != detail:
                            continue
                        checked.add("house_number")
                    if "address_line1" in values:
                        entered = _jp_detail(values["address_line1"])
                        if entered == local_line or entered == row.prefecture[0] + row.municipality[0] + local_line:
                            checked.add("address_line1")
                        elif re.fullmatch(r".*[0-9]", entered):
                            continue
                    office = "address_line1" in checked or ("house_number" in checked and bool(checked & {"town", "neighbourhood"}))
            receipt = dict(sources[row.source_id], record_id=f"{row.source_id}:{row.row}")
            postal_city_labels = {_key(v) for v in row.municipality[:2 if row.postal_use == "ordinary" else 1]}
            uses_ward_projection = ("city_district" in checked or
                                    any(_key(values[k]) not in postal_city_labels for k in checked & _MUNICIPAL))
            if row.ward_ref and uses_ward_projection:
                receipt["ward_reference"] = {
                    "source_id": "jp-abr-snapshot", "source_row": row.ward_ref, "sha256": ward_source["sha256"],
                    "attribution": ward_source["provider"], "license": ward_source["licence"],
                    "url": ward_source["repository"], "terms_url": ward_source["terms"],
                }
            candidates.append((checked, issues, receipt, office))
    if not candidates:
        return result("conflict", issues=["postal_component_conflict"],
                      evidence=[dict(sources[r.source_id], record_id=f"{r.source_id}:{r.row}") for r in rows[:_EVIDENCE_LIMIT]],
                      total=len(rows))
    fields = set.intersection(*(c[0] for c in candidates))
    issues = set.union(*(c[1] for c in candidates))
    status = "ambiguous" if len(candidates) > 1 else "partial" if issues else "matched"
    scope = "postal_locality" if fields - {"postcode", "organization"} else "postcode_observation"
    if len(candidates) == 1 and candidates[0][3]:
        scope = "published_office_address"
    return result(status, scope=scope, checked=fields, issues=issues, evidence=[c[2] for c in candidates])


def _fr(country, values, result):
    if not values.get("postcode"):
        return result("insufficient_input", issues=["postcode_required_for_reference"])
    code = values["postcode"]
    rows = [r for r in postal_eu.lookup(code, country=country) if r["postcode"] == code]
    if not rows:
        return result("not_observed", issues=["postcode_not_observed"])
    mapped = {**{k: ("locality", "routing_name") for k in _MUNICIPAL},
              "town": ("locality", "line_5"), "neighbourhood": ("line_5",)}
    candidates = []
    for r in rows:
        checked = {"postcode"}
        for k, slots in mapped.items():
            if k not in values:
                continue
            labels = [_key(r[slot]) for slot in slots if r[slot]]
            if _key(values[k]) in labels:
                checked.add(k)
            elif labels:
                break
        else:
            candidates.append((r, checked))
    def evidence(rows):
        return [{"source_id": r["source_id"], "record_id": r["record_id"], "url": r["source_url"],
                 "snapshot": r["source_updated_at"], "sha256": postal_eu.SOURCE["raw_sha256"],
                 "attribution": r["attribution"], "license": postal_eu.SOURCE["license"],
                 **({"territory_attribution": r["territory_attribution"], "territory_source_url": r["territory_source_url"]}
                    if "territory_source_url" in r else {})} for r in rows[:_EVIDENCE_LIMIT]]
    if not candidates:
        return result("conflict", issues=["postal_component_conflict"], evidence=evidence(rows), total=len(rows))
    fields = set.intersection(*(checked for _, checked in candidates))
    return result("matched" if len(candidates) == 1 else "ambiguous",
                  scope="postal_locality" if fields - {"postcode"} else "postcode_observation",
                  checked=fields, evidence=evidence([r for r, _ in candidates]), total=len(candidates))


def validate_address(country: str, components: Mapping[str, str], *, index_path=None) -> dict:
    """Compare typed fields on one source record; expose verified and unchecked roles.

    An optional, trusted PostalPicker index can prove a complete postcode
    observation. Its display labels are not typed locality or premise evidence.
    Identity and presentation metadata do not participate in address validation.
    """
    if not isinstance(country, str) or not re.fullmatch("[A-Za-z]{2}", country):
        raise ValueError("country must contain two ASCII letters")
    country = country.upper()
    if not isinstance(components, Mapping) or len(components) > 64:
        raise ValueError("components must be a mapping of at most 64 fields")
    for k, v in components.items():
        if (not isinstance(k, str) or not k.isascii() or not re.fullmatch(r"[A-Za-z][A-Za-z_0-9 -]{0,63}", k)
                or not isinstance(v, str) or len(v) > 1024 or any(unicodedata.category(c) in {"Cc", "Zl", "Zp"} for c in v)):
            raise ValueError("component keys and values must be bounded single-line strings")
    try:
        normalized = canonicalize_components(components)
    except ValueError:
        return _result(country, {normalize_key(k) for k in components}, "conflict", issues=["incompatible_component_values"])
    values = normalized.values | normalized.extras
    country_fields = set()
    if "country_code" in values:
        if values["country_code"] != country:
            return _result(country, values, "conflict", issues=["country_code_conflict"])
        country_fields.add("country_code")
    if "country" in values:
        codes = _country_names().get(_key(values["country"]), set())
        if codes and country not in codes:
            return _result(country, values, "conflict", issues=["country_name_conflict"])
        if codes == {country}:
            country_fields.add("country")

    def result(status, *, checked=(), **kw):
        return _result(country, values, status, checked=country_fields | set(checked), **kw)

    code = values.get("postcode")
    pattern = {"JP": r"[0-9]{3}-?[0-9]{4}", "US": r"[0-9]{5}(-[0-9]{4})?",
               "CN": r"[0-9]{6}"}.get(country)
    if country in postal_eu.COUNTRIES:
        pattern = r"[0-9]{5}"
    if code and pattern and not re.fullmatch(pattern, _jp_detail(code) if country == "JP" else code):
        return result("invalid_format", issues=["invalid_postcode_format"])
    if country == "JP":
        return _jp(values, result)
    if country in postal_eu.COUNTRIES:
        return _fr(country, values, result)
    if country in ("US", "CN"):
        scoped = _us(values, result) if country == "US" else _cn(values, result)
        if scoped is not None:
            return scoped
    if index_path is not None and code:
        from localities.postal_picker import PostalPicker

        found = PostalPicker(index_path).lookup(country, code, limit=1)
        if found["status"] == "options":
            return result("matched", scope="postcode_observation", checked=["postcode"],
                          evidence=[dict(found.get("source_details", {}).get(s, {}), source_id=s,
                                         reference="postal_picker:country/postcode") for s in found["sources"]])
        if found["status"] != "unsupported_country":
            return result("not_observed", issues=["postcode_not_observed"])
    return result("insufficient_input" if country in ("US", "CN") and not code else "unsupported",
                  issues=["no_applicable_reference"])
