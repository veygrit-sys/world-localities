"""Taiwan MOI street names joined to Chunghwa Post's published area prefixes."""

import csv
from dataclasses import dataclass, field
from functools import cache
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parent
POST = ROOT.parents[2] / "registries/official/TW"
POST_ID = "tw-chunghwa-names"
ROAD_ID = "tw-moi-road-names-115"
JOIN_ID = "tw-postal-areas-moi-roads-115"


@dataclass
class Area:
    prefix: str
    label: str
    city: str
    district: str
    post_row: int
    roads: dict = field(default_factory=dict)


@cache
def descriptors():
    road = json.loads((ROOT / "source.json").read_text(encoding="utf-8"))
    postal = json.loads((POST / "sources.json").read_text(encoding="utf-8"))
    published = postal["sources"][POST_ID]
    post = {"source_id": POST_ID, "attribution": "中華郵政股份有限公司「縣市鄉鎮中英對照檔」，World Localities 整理。",
            "license": published["licence"], "terms_url": published["terms"], "source_url": published["catalogue"],
            "download_url": published["url"], "sha256": published["sha256"], "published_on": published["published_on"],
            "retrieved": postal["observed_on"], "scope": "Published three-digit postal area only."}
    combined = {"source_id": JOIN_ID, "attribution": road["attribution"] + " " + post["attribution"],
                "license": road["license"], "terms_url": road["terms_url"], "source_url": road["source_url"],
                "constituent_sources": [post, road],
                "scope": "MOI road in a district sharing the published three-digit postal area; final digits unchecked."}
    return {POST_ID: post, ROAD_ID: road, JOIN_ID: combined}


@cache
def areas():
    info = descriptors()
    raw = (POST / "sources/names.xml").read_bytes()
    if hashlib.sha256(raw).hexdigest() != info[POST_ID]["sha256"]:
        raise RuntimeError("Chunghwa Post postal-area snapshot checksum mismatch")
    by_label = {}
    for n, el in enumerate(ElementTree.fromstring(raw), 1):
        prefix, label = el.findtext("欄位1"), el.findtext("欄位2")
        if not re.fullmatch(r"[0-9]{3}", prefix) or not label or label in by_label:
            raise RuntimeError("invalid Chunghwa Post area record")
        parts = re.fullmatch(r"([^市縣]+[市縣])(.+)", label)
        city, district = parts.groups() if parts else ("", "")
        by_label[label] = Area(prefix, label, city, district, n)
    with gzip.open(ROOT / "roads-115.csv.gz", "rb") as f:
        raw = f.read()
    if hashlib.sha256(raw).hexdigest() != info[ROAD_ID]["sha256"]:
        raise RuntimeError("Taiwan MOI street snapshot checksum mismatch")
    records = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    if records.fieldnames != ["city", "site_id", "road"]:
        raise RuntimeError("unexpected MOI road columns")
    for n, row in enumerate(records, 1):
        # The publisher pads twelve district names such as 東　區 with U+3000.
        area = by_label.get(row["site_id"].replace("\u3000", ""))
        road = row["road"].strip()
        if not area or area.city != row["city"] or not road:
            raise RuntimeError("unresolved MOI city/district/road")
        area.roads.setdefault(road, []).append(n)
    return tuple(by_label.values())


def picker_records():
    for area in areas():
        steps = (("area", area.city), ("town", area.district)) if area.city else (("area", area.label),)
        yield "TW", area.prefix, steps, POST_ID
        for road in area.roads:
            yield "TW", area.prefix, steps + (("street", road),), JOIN_ID


def postcode_context(code):
    """Identify the three-digit lookup scope without upgrading or verifying an entered suffix."""
    if not re.fullmatch(r"[0-9]{3}(?:[0-9]{2,3})?", code):
        return {}
    context = {"lookup_prefix": code[:3], "postcode_scope": "area_prefix_only", "postcode_verified": False}
    if len(code) == 5:
        context.update(postcode_format="legacy_3_plus_2", postcode_notice="confirm_current_six_digit_postcode")
    return context


def validate(values, result):
    code = unicodedata.normalize("NFKC", values.get("postcode", ""))
    context = postcode_context(code)
    if code and not context:
        return result("invalid_format", issues=["invalid_postcode_format"])
    city_fields = {"city", "county", "municipality"} & values.keys()
    district_fields = {"city_district", "neighbourhood"} & values.keys()
    if not code and not (city_fields and district_fields):
        return result("insufficient_input", issues=["postal_prefix_or_city_and_district_required"])

    # Global aliases map district/ward to neighbourhood. Use their values to constrain the
    # search; the source cannot independently establish a neighbourhood below the district.
    checked = city_fields | ({"city_district"} & district_fields)
    eligible = [a for a in areas() if (not code or a.prefix == code[:3])
                and all(a.city == values[k] for k in city_fields)
                and ("county" not in city_fields or a.city.endswith("縣"))
                and ("municipality" not in city_fields or a.city.endswith("市"))
                and all(a.district == values[k] for k in district_fields)]
    if not eligible:
        return result("not_observed", issues=["postal_area_not_observed"]) | context
    road = values.get("road")
    streets = [a for a in eligible if road in a.roads] if road else []
    issues = ["only_three_digit_postal_area_available"] if code else []
    if road and not streets:
        issues.append("road_not_observed_in_entered_area")
    if streets:
        checked.add("road")
    receipts = []
    post = descriptors()[POST_ID]
    moi = descriptors()[ROAD_ID]
    for area in streets or eligible:
        receipts.append({"source_id": POST_ID, "record_id": f"{POST_ID}:{area.post_row}",
                         "url": post["source_url"], "sha256": post["sha256"], "source_row": area.post_row,
                         "terms_url": post["terms_url"], "attribution": post["attribution"], "area_prefix": area.prefix})
        if streets:
            for n in area.roads[road]:
                receipts.append({"source_id": ROAD_ID, "record_id": f"{ROAD_ID}:{n}", "source_row": n,
                                 "url": moi["source_url"], "sha256": moi["sha256"], "terms_url": moi["terms_url"],
                                 "attribution": moi["attribution"]})
    status = "ambiguous" if len(streets or eligible) > 1 else "matched"
    return result(status, scope="published_district_street" if streets else "published_postal_area",
                  checked=checked, evidence=receipts, issues=issues) | context
