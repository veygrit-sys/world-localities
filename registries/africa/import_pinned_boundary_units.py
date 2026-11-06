#!/usr/bin/env python3
"""Ingest pinned CC-licensed authoritative-source boundary gazetteers.

GeoBoundaries gbOpen mirrors source datasets including IEBC/OCHA Kenya and
Ghana Statistical Service/USAID Ghana. Source vintages differ. Derived rows
are a SEPARATE layer: not current legal administration, not GeoNames parents.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent
RELEASE = "9469f09"
SOURCES = {
    ("KEN", "ADM1"): ("a3e073594494eb740e42fadec63acda982f6a745bb64ee4aa152453ccc46f94e", 7956137, 47,
                       "2020", "IEBC, OCHA ROSEA", "CC BY 3.0 IGO"),
    ("KEN", "ADM2"): ("af9fd77ad3df64f3efbbea350b8664e5191cb5381cf7eea247507ac2c906bc24", 10884536, 290,
                       "2020", "IEBC, OCHA ROSEA", "CC BY 3.0 IGO"),
    ("GHA", "ADM1"): ("ee73028cfcfbfc5a5bb851c118d47136086de499d23a5e0e27dc2876b6796bca", 2093457, 16,
                       "2019", "Ghana Statistical Service, USAID Ghana HPNO", "CC BY 4.0"),
    ("GHA", "ADM2"): ("242adc67f4e4b04df800da06650af20487dbef99cf2b155702529ffa705dc80f", 27442126, 260,
                       "2019", "Ghana Statistical Service, USAID Ghana HPNO", "CC BY 4.0"),
}
HEADERS = ["country", "admin_level", "boundary_shape_id", "name", "parent_shape_id",
           "parent_assignment", "source_year", "source_origin", "license", "source_sha256"]

def sha(data):
    return hashlib.sha256(data).hexdigest()

def url_for(iso, level):
    return (f"https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/{RELEASE}/"
            f"releaseData/gbOpen/{iso}/{level}/geoBoundaries-{iso}-{level}.geojson")

def source_file(iso, level):
    return f"geoBoundaries-{iso}-{level}.geojson"

def acquire(iso, level, cache):
    expected_hash, size, expected_count, year, origin, license_name = SOURCES[(iso, level)]
    path = cache / source_file(iso, level)
    if path.exists():
        payload = path.read_bytes()
    else:
        request = urllib.request.Request(url_for(iso, level),
                                         headers={"User-Agent": "Veygrit-world-localities/1.0"})
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read(size+1)
        if len(payload) <= size and sha(payload) == expected_hash:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
    if len(payload) != size or sha(payload) != expected_hash:
        raise ValueError(f"{iso}/{level}: original download has unexpected size or SHA-256; "
                         "source may be an LFS pointer. Only the pinned original is accepted.")
    data = json.loads(payload)
    features = data.get("features", [])
    if data.get("type") != "FeatureCollection" or len(features) != expected_count:
        raise ValueError(f"{iso}/{level}: unexpected feature count {len(features)}")
    return features, {"url": url_for(iso, level), "sha256": expected_hash,
                      "bytes": size, "rows": expected_count, "vintage_year": year,
                      "origin": origin, "license": license_name}

def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=HEADERS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

def generate(cache, output):
    try:
        from shapely.geometry import shape
    except ImportError as exc:
        raise RuntimeError("pip install shapely==2.1.2") from exc

    records = {}
    summaries = {}
    for key in SOURCES:
        feats, summary = acquire(*key, cache)
        rows, seen_ids = [], set()
        for feature in feats:
            props = feature["properties"]
            gid = str(props.get("shapeID") or "").strip()
            name = str(props.get("shapeName") or "").strip()
            if not gid or not name or gid in seen_ids:
                raise ValueError(f"{key}: duplicate or missing shape id/name")
            seen_ids.add(gid)
            polygon = shape(feature["geometry"])
            if polygon.is_empty or not polygon.is_valid:
                raise ValueError(f"{key}: empty or invalid geometry {gid}")
            rows.append({"shapeID": gid, "name": name, "geometry": polygon,
                         "parent_id": None, "parent_assignment": "not_applicable"})
        records[key] = rows
        summaries[f"{key[0]}-{key[1]}"] = summary

    for iso in ("KEN", "GHA"):
        parents = records[(iso, "ADM1")]
        children = records[(iso, "ADM2")]
        for child in children:
            representative = child["geometry"].representative_point()
            hits = [parent for parent in parents if parent["geometry"].covers(representative)]
            if len(hits) == 1:
                child["parent_id"] = hits[0]["shapeID"]
                child["parent_assignment"] = "single_representative_point_in_ADM1"
            else:
                child["parent_assignment"] = f"unresolved_{len(hits)}_ADM1_candidates"

    output.mkdir(parents=True, exist_ok=True)
    for (iso, level), data in records.items():
        s = summaries[f"{iso}-{level}"]
        rows = []
        for r in sorted(data, key=lambda d: (d["name"], d["shapeID"])):
            rows.append({
                "country": iso, "admin_level": level,
                "boundary_shape_id": r["shapeID"], "name": r["name"],
                "parent_shape_id": r["parent_id"] or "",
                "parent_assignment": r["parent_assignment"],
                "source_year": s["vintage_year"], "source_origin": s["origin"],
                "license": s["license"], "source_sha256": s["sha256"],
            })
        target = output / f"{iso}-{level}-source-units.csv"
        write_csv(target, rows)
        s["derived_csv_sha256"] = sha(target.read_bytes())
        s["derived_csv_bytes"] = target.stat().st_size
        s["assigned_parent_count"] = sum(bool(r["parent_id"]) for r in data)
        s["parent_count_method"] = "representative point in own-source ADM1 polygon (NOT legally certified parent)"

    (output / "source_receipts.json").write_text(
        json.dumps({"schema_version":1, "release":RELEASE, "sources":summaries,
                    "legal_admin_crosswalk_approved": False,
                    "geonames_modified": False,
                    "caveat": "Source vintages and administrative systems differ; do not equate historical election geographies to current Kenya national administrative units. Parent assignments are spatial-only."},
                   indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    return records, summaries

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache", type=Path, default=ROOT / ".cache/gb-pinned")
    p.add_argument("--output", type=Path, default=ROOT / "reference-boundaries")
    args = p.parse_args()
    records, summary = generate(args.cache, args.output)
    print(json.dumps({k: {"rows": len(records[(k[:3],k[4:])]),
                          "sha256": value["sha256"]}
                      for k, value in summary.items()}, sort_keys=True))

if __name__ == "__main__":
    main()
