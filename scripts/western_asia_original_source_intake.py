#!/usr/bin/env python3
"""Source-pinned offline intake for published AZ GeoJSON and JO post-office CSV.

No original bytes are checked in; callers supply local files, exact SHA256 and
source-specific schema. Reports are aggregates, NOT authenticated postal links.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import io
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CATALOGUE = ROOT / "registries/official/western-asia/caucasus-levant/original-source-acquisition.json"
AZ_SOURCE = "AZ-IDDA-ADMIN-GEOJSON-2025"
JO_SOURCE = "JO-POST-OFFICES-2023"
ALLOWED_ENCODINGS = {"utf-8", "utf-8-sig", "cp1256"}


def load_catalogue(path: Path = CATALOGUE) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("status") != "source_catalogue_only_original_files_not_acquired":
        raise ValueError("Unexpected source provenance schema")
    entries = {item["id"]: item for item in data["entries"]}
    if len(entries) != len(data["entries"]) or not {AZ_SOURCE,JO_SOURCE}.issubset(entries):
        raise ValueError("Required original-source references missing")
    for item in data["entries"]:
        if item.get("downloaded") is not False or item.get("sha256") is not None:
            raise ValueError("Not permitted to claim source original was already acquired")
    return entries


def _source_bytes(path: Path, expected_sha256: str) -> bytes:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Exact SHA256 required for acquired source bytes")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("Input SHA256 mismatch")
    return raw


def geometry_points(node, *, depth=0):
    """Walk GeoJSON coordinate nesting; require valid lon/lat, no invented regions."""
    if depth > 16:
        raise ValueError("GeoJSON geometry nesting too deep")
    if not isinstance(node, list):
        raise ValueError("Unexpected coordinates shape")
    if len(node) >= 2 and all(type(x) in (int,float) for x in node[:2]):
        lon,lat=node[:2]
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise ValueError("Invalid WGS84 longitude/latitude")
        return 1
    return sum(geometry_points(child, depth=depth+1) for child in node)


def audit_geojson(raw: bytes) -> dict:
    data = json.loads(raw.decode("utf-8-sig"))
    if data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ValueError("Expected original GeoJSON FeatureCollection")
    features = data["features"]
    if not features:
        raise ValueError("Empty source GeoJSON")
    geometry_counts = Counter()
    properties = Counter()
    observed_ids = set()
    duplicate_ids = 0
    missing_ids = 0
    no_geometry = 0
    coordinates_checked = 0
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("Invalid GeoJSON feature")
        props=feature.get("properties")
        if not isinstance(props,dict):
            raise ValueError("Expected feature properties dictionary")
        properties.update(props.keys())
        fid=feature.get("id")
        if fid is None:
            missing_ids+=1
        else:
            key=str(fid)
            if key in observed_ids:
                duplicate_ids+=1
            observed_ids.add(key)
        geo=feature.get("geometry")
        if geo is None:
            no_geometry+=1
            continue
        geo_type=geo.get("type") if isinstance(geo,dict) else None
        if geo_type not in {"Point","MultiPoint","LineString","MultiLineString",
                            "Polygon","MultiPolygon"}:
            raise ValueError("Unsupported geometry type")
        geometry_counts[geo_type]+=1
        coordinates_checked+=geometry_points(geo["coordinates"])
    return {
        "format": "GeoJSON", "feature_count": len(features),
        "geometry_types": dict(sorted(geometry_counts.items())),
        "source_feature_ids_missing": missing_ids,
        "source_feature_ids_duplicated": duplicate_ids,
        "property_name_presence": dict(sorted(properties.items())),
        "coordinate_pairs_checked": coordinates_checked,
        "features_without_geometry": no_geometry,
        "source_property_ids_legally_verified": False,
        "country_membership_inferred_from_coordinates": False,
        "government_to_geonames_links_verified": 0,
        "postcode_links_verified": 0,
    }


def audit_jordan_csv(raw: bytes, *, encoding: str = "utf-8-sig",
                     postcode_field: str | None = None,
                     office_field: str | None = None) -> dict:
    if encoding not in ALLOWED_ENCODINGS:
        raise ValueError("Unapproved source encoding")
    decoded = raw.decode(encoding)
    csv.field_size_limit(2_000_000)
    source = csv.DictReader(io.StringIO(decoded, newline=""))
    headers = source.fieldnames
    if not headers or len(headers) != len(set(headers)):
        raise ValueError("Missing/duplicate official CSV headers")
    if postcode_field and postcode_field not in headers:
        raise ValueError("Chosen postcode field not in original file")
    if office_field and office_field not in headers:
        raise ValueError("Chosen post-office field not in original file")
    counts = Counter()
    postcodes = defaultdict(set)
    first_warning = None
    for row in source:
        counts["source_rows"] += 1
        if any(value is None for value in row.values()):
            counts["incomplete_source_csv_rows"] += 1
        if postcode_field:
            raw_code = (row[postcode_field] or "").strip()
            if not raw_code:
                counts["missing_postcode"]+=1
            elif re.fullmatch(r"[0-9]{5}",raw_code):
                counts["valid_five_digit_postcode_syntax"]+=1
                if office_field:
                    office=(row[office_field] or "").strip()
                    if office:
                        postcodes[raw_code].add(office)
            else:
                counts["invalid_postcode_syntax"]+=1
        else:
            first_warning = "postal_column_unmapped_no_postcode_verification_attempted"
    if counts["source_rows"] == 0:
        raise ValueError("Empty official Jordan Post CSV")
    return {
        "format": "CSV", "source_rows": counts["source_rows"],
        "source_field_names": list(headers),
        "encoding":encoding,
        "postcode_field":postcode_field,
        "office_field":office_field,
        "counts":dict(sorted(counts.items())),
        "distinct_mapped_postcodes": len(postcodes),
        "postcodes_for_multiple_offices": sum(len(s)>1 for s in postcodes.values()),
        "warning":first_warning,
        "postcode_to_government_office_id_verified": False,
        "postcode_to_geonames_id_verified": False,
        "building_or_deliverability_verified": False,
        "source_rows_published_by_audit": 0,
    }


def audit_file(source_id: str, file: Path, expected_sha256: str, *,
               encoding: str="utf-8-sig",
               postcode_field: str | None=None, office_field: str | None=None,
               catalogue: dict | None=None) -> dict:
    catalogue = catalogue or load_catalogue()
    if source_id not in (AZ_SOURCE,JO_SOURCE):
        raise ValueError("Only AZ GeoJSON and JO post-office CSV parsers available")
    if source_id not in catalogue:
        raise ValueError("Unknown source")
    raw = _source_bytes(file,expected_sha256)
    if source_id == AZ_SOURCE:
        if postcode_field or office_field:
            raise ValueError("Azerbaijan administrative GeoJSON is not a postal dataset")
        output = audit_geojson(raw)
    else:
        output = audit_jordan_csv(raw, encoding=encoding,
                                  postcode_field=postcode_field,
                                  office_field=office_field)
    return {
        "source_id":source_id,"country":catalogue[source_id]["country"],
        "original_source_url":catalogue[source_id]["url"],
        "original_publisher":catalogue[source_id]["publisher"],
        "published_date":catalogue[source_id]["last_updated"],
        "original_file_sha256":expected_sha256,
        "original_file_bytes":len(raw),
        "file_pinned_and_parsed":True,
        "original_source_committed_to_repo":False,
        "source_license_review_required":not catalogue[source_id]["license_reviewed"],
        "source_approved_official_id_links":0,
        **output
    }


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",choices=("inventory","audit"))
    p.add_argument("--source-id",choices=(AZ_SOURCE,JO_SOURCE))
    p.add_argument("--file",type=Path)
    p.add_argument("--sha256")
    p.add_argument("--postcode-field")
    p.add_argument("--office-field")
    p.add_argument("--encoding",choices=sorted(ALLOWED_ENCODINGS),default="utf-8-sig")
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    if args.command=="inventory":
        ref=load_catalogue()
        output={"sources":[ref[k] for k in (AZ_SOURCE,JO_SOURCE)],
                "originals_acquired_in_repo":False}
    else:
        if not args.source_id or not args.file or not args.sha256:
            p.error("Provide source-id, file, and SHA256 before audit")
        output=audit_file(args.source_id,args.file,args.sha256,
                          encoding=args.encoding,postcode_field=args.postcode_field,
                          office_field=args.office_field)
    serialized=json.dumps(output,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(serialized,encoding="utf-8")
    else:
        print(serialized,end="")


if __name__=="__main__":
    main()
