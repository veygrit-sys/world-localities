#!/usr/bin/env python3
"""Import source-year 2020 Egypt ADM2 marakiz/aqsam gazetteer (OCHA/CAPMAS).

No implied current ADM1 parent, postal code, or delivery coverage.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"official-references"
URL=("https://media.githubusercontent.com/media/wmgeolab/geoBoundaries/9469f09/"
     "releaseData/gbOpen/EGY/ADM2/geoBoundaries-EGY-ADM2.geojson")
SHA="d5a319adf69ea1179d7ba5462600c72ea9c54f46b762ffcf984a03c692b913a9"
BYTES=7981864
ROWS=365
FIELDS=["source_shape_id","name","admin_level","source_year","canonical","source_sha256","parent_official_id"]

def main():
    req=Request(URL,headers={"User-Agent":"world-localities-egypt/1.0"})
    with urlopen(req,timeout=120) as response:
        payload=response.read(BYTES+1)
    if len(payload)!=BYTES or hashlib.sha256(payload).hexdigest()!=SHA:
        raise ValueError("source GeoJSON SHA or size mismatch; do not ingest")
    featurecollection=json.loads(payload)
    if featurecollection.get("type")!="FeatureCollection":
        raise ValueError("source type unexpected")
    features=featurecollection.get("features",[])
    if len(features)!=ROWS:raise ValueError("unexpected government-origin district counts")
    rows=[];seen=set()
    for f in features:
        p=f.get("properties",{})
        key=str(p.get("shapeID") or "").strip()
        name=str(p.get("shapeName") or "").strip()
        if not key or key in seen or not name:raise ValueError("invalid original feature identity")
        seen.add(key)
        rows.append({
            "source_shape_id":key,"name":name,"admin_level":"ADM2",
            "source_year":"2020","canonical":"marakiz and aqsam","source_sha256":SHA,
            "parent_official_id":"",
        })
    buf=io.StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    w.writeheader();w.writerows(sorted(rows,key=lambda r:(r["name"],r["source_shape_id"])))
    payload_csv=buf.getvalue().encode("utf-8")
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/"EG-CAPMAS-OCHA-2020-ADM2.csv"
    path.write_bytes(payload_csv)
    receipt={"source_url":URL,"source_sha256":SHA,"source_bytes":BYTES,
             "source_year":2020,"source_original":"OCHA ROMENA / CAPMAS, via geoBoundaries",
             "original_license":"CC BY 3.0 IGO","count":len(rows),
             "derived_csv_sha256":hashlib.sha256(payload_csv).hexdigest(),
             "derived_csv_bytes":len(payload_csv),
             "legal_current_parent_ids_verified":False,"postcode_or_delivery_verified":False}
    (OUT/"EG-CAPMAS-OCHA-2020-ADM2.source.json").write_text(
        json.dumps(receipt,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(receipt,ensure_ascii=False))

if __name__=="__main__":main()
