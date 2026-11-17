#!/usr/bin/env python3
"""Ingest pinned 2020 South Africa and 2022 Nigeria administrative units.

Inputs are separate, authority-origin gbOpen LFS GeoJSON blobs. Derived CSV
preserves source names/IDs, dated geometric parent associations and provenance.
Original GeoNames IDs and national legal parent links are NOT modified.
"""
import csv
import hashlib
import io
import json
import time
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "extended-boundaries"
REF = "9469f09"
SOURCES = {
    "ZAF-ADM1": {"sha256":"5d82ed95b034f50d69d96c9b7136e9b5868a5fb4ef2d8905a6a6ac3715fef452","bytes":19806654,"rows":9,"year":2020,"origin":"OCHA ROSEA, South African Municipal Demarcation Board","license":"CC BY 3.0 IGO","canonical":"Province"},
    "ZAF-ADM2": {"sha256":"6cc504ad835b37823da687a3fd3f0cab63608a6c8a5ad906e1011f1554bbbbdd","bytes":32530325,"rows":52,"year":2020,"origin":"OCHA ROSEA, South African Municipal Demarcation Board","license":"CC BY 3.0 IGO","canonical":"District municipality"},
    "ZAF-ADM3": {"sha256":"74e489fd4370972403950719026a317abba443668cea7d49f4b36c61637958f1","bytes":50705428,"rows":213,"year":2020,"origin":"OCHA ROSEA, South African Municipal Demarcation Board","license":"CC BY 3.0 IGO","canonical":"Local municipality"},
    "NGA-ADM1": {"sha256":"64fa218ac3d453cc1e66412ff461c5dfa1a4a1ade0da93b239a9891b587d28f9","bytes":2289696,"rows":37,"year":2022,"origin":"GRID3 Nigeria","license":"CC BY 4.0","canonical":"State/FCT"},
    "NGA-ADM2": {"sha256":"bef7f2cfa45e012f4772eaa61c7b99e5188aeba4d5c6badae7e9f9aae8c02fcd","bytes":9422551,"rows":774,"year":2022,"origin":"GRID3 Nigeria","license":"CC BY 4.0","canonical":"Local Government Area"},
}
FIELDS = ["country","adm_level","shape_id","name","parent_shape_id",
          "parent_assignment","source_year","canonical","origin","license","source_sha256"]

def url(key):
    iso,level=key.split("-")
    return (f"https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/{REF}/"
            f"releaseData/gbOpen/{iso}/{level}/geoBoundaries-{iso}-{level}.geojson")

def sha(payload):
    return hashlib.sha256(payload).hexdigest()

def load(key, cache):
    conf=SOURCES[key]
    path=cache/(key+".geojson")
    if path.exists():
        payload=path.read_bytes()
    else:
        last=None
        for attempt in range(3):
            try:
                req=Request(url(key),headers={"User-Agent":"world-localities-gbopen-pinned/1.0"})
                with urlopen(req, timeout=180) as response:
                    payload=response.read(conf["bytes"]+1)
                break
            except OSError as exc:
                last=exc
                if attempt<2: time.sleep(2**attempt)
        else: raise RuntimeError(f"{key}: source unavailable") from last
        if len(payload)==conf["bytes"] and sha(payload)==conf["sha256"]:
            cache.mkdir(parents=True,exist_ok=True)
            path.write_bytes(payload)
    if len(payload)!=conf["bytes"] or sha(payload)!=conf["sha256"]:
        raise ValueError(f"{key}: original pinned GeoJSON SHA/size differs; no fallback")
    data=json.loads(payload)
    if data.get("type")!="FeatureCollection" or len(data.get("features",[]))!=conf["rows"]:
        raise ValueError(f"{key}: unexpected number or type of source features")
    seen=set(); entries=[]
    try:
        from shapely.geometry import shape
    except ImportError as exc:
        raise RuntimeError("Install shapely==2.1.2 first") from exc
    for feature in data["features"]:
        prop=feature["properties"]
        gid=str(prop.get("shapeID") or "").strip()
        name=str(prop.get("shapeName") or "").strip()
        if not gid or not name or gid in seen:
            raise ValueError(f"{key}: empty/duplicate source geographic ID or name")
        seen.add(gid)
        polygon=shape(feature["geometry"])
        if polygon.is_empty:
            raise ValueError(f"{key}: empty geometry")
        entries.append({"id":gid,"name":name,"geometry":polygon,"parent_id":"",
                        "parent_relation":"not_applicable"})
    return entries

def build(cache, output=BASE):
    records={key:load(key,cache) for key in SOURCES}
    for iso, parent_level, child_level in (("ZAF","ADM1","ADM2"),
                                            ("ZAF","ADM2","ADM3"),
                                            ("NGA","ADM1","ADM2")):
        parents=records[f"{iso}-{parent_level}"]
        children=records[f"{iso}-{child_level}"]
        for child in children:
            point=child["geometry"].representative_point()
            matches=[p for p in parents if p["geometry"].covers(point)]
            if len(matches)==1:
                child["parent_id"]=matches[0]["id"]
                child["parent_relation"]="unique_source_year_spatial_parent"
            else:
                child["parent_relation"]=f"unresolved_{len(matches)}_candidate_parents"
    output.mkdir(parents=True,exist_ok=True)
    sources={}
    for key,items in records.items():
        conf=SOURCES[key]
        iso,level=key.split("-")
        rows=[{
            "country":iso,"adm_level":level,"shape_id":r["id"],
            "name":r["name"],"parent_shape_id":r["parent_id"],
            "parent_assignment":r["parent_relation"],
            "source_year":str(conf["year"]),"canonical":conf["canonical"],
            "origin":conf["origin"],"license":conf["license"],"source_sha256":conf["sha256"]
        } for r in sorted(items,key=lambda x:(x["name"],x["id"]))]
        f=io.StringIO(newline="");w=csv.DictWriter(f,fieldnames=FIELDS,lineterminator="\n")
        w.writeheader();w.writerows(rows)
        payload=f.getvalue().encode("utf-8")
        (output/(key+"-source-units.csv")).write_bytes(payload)
        sources[key]={**conf,"original_url":url(key),
                      "derived_csv_bytes":len(payload),
                      "derived_csv_sha256":sha(payload),
                      "parent_spatial_assignments":sum(bool(x["parent_id"]) for x in items),
                      "parent_association_valid_for_source_year_only":True}
    summary={"schema_version":1,"source_revision":REF,"sources":sources,
             "records":sum(s["rows"] for s in sources.values()),
             "original_geonames_untouched":True,
             "official_legal_parent_links_certified":0,
             "postcode_or_deliverability_confirmed":False,
             "notes":"GB source shapeIDs are not postal/official codes. Dated spatial parent relations are not legal administrative parent certifications."}
    (output/"source_receipts.json").write_text(json.dumps(summary,sort_keys=True,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    return summary

def main():
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cache",type=Path,default=ROOT/".cache"/"gbopen-expanded")
    p.add_argument("--output",type=Path,default=BASE)
    args=p.parse_args()
    result=build(args.cache,args.output)
    print(json.dumps({"records":result["records"],
                      "sources":{k:{"rows":v["rows"],"parents":v["parent_spatial_assignments"]}
                                 for k,v in result["sources"].items()}},sort_keys=True))

if __name__=="__main__":
    main()
