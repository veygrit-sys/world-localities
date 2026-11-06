#!/usr/bin/env python3
"""Import official Rwanda 2022 village IDs/names, without personal addresses.

NISR FeatureServer explicitly provides an open-data village layer; this stores
only administrative attributes in a separate source-labelled CSV. No location
polygons, original GeoNames parent edits or postal/delivery claims.
"""
import argparse
import csv
import hashlib
import io
import json
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
ENDPOINT = ("https://gis-server.statistics.gov.rw/server/rest/services/Hosted/"
            "Village_Boundary_2022/FeatureServer/3")
FIELDS = ["objectid","province_id","province","district_id","district",
          "sector_id","sector","cell_id","cell","village_id","village"]
OUTPUT_FIELDS = ["province_id","province","district_id","district","sector_id",
                 "sector","cell_id","cell","village_id","village","source_objectid"]
BATCH = 1000

def request_json(url, query):
    uri = url + "?" + urlencode(query)
    last = None
    for attempt in range(3):
        try:
            req = Request(uri,headers={"User-Agent":"world-localities-nisr-open-data/1.0"})
            with urlopen(req, timeout=75) as response:
                data = response.read(8_000_000)
            answer = json.loads(data.decode("utf-8-sig"))
            if "error" in answer:
                raise ValueError(str(answer["error"]))
            return answer
        except (OSError, ValueError) as exc:
            last = exc
            if attempt < 2: time.sleep(2**attempt)
    raise RuntimeError("Rwanda NISR request failed") from last

def normalize(value):
    if value is None: return ""
    return str(value).strip()

def fetch():
    layer = request_json(ENDPOINT, {"f":"json"})
    available = {r["name"] for r in layer.get("fields",[])}
    if not set(FIELDS).issubset(available):
        raise ValueError("NISR service schema changed")
    if layer.get("copyrightText") != "Village boundary data have been produced by NISR in 2022":
        raise ValueError("Unexpected NISR provenance; re-review origin before importing")
    count = int(request_json(ENDPOINT+"/query", {"f":"json","where":"1=1",
                                                 "returnCountOnly":"true"})["count"])
    if not 13000 <= count <= 17000:
        raise ValueError(f"Village count outside documented range: {count}")
    found=[]
    for offset in range(0,count,BATCH):
        args={"f":"json","where":"1=1","outFields":",".join(FIELDS),
              "returnGeometry":"false","orderByFields":"objectid ASC",
              "resultOffset":offset,"resultRecordCount":BATCH}
        block = request_json(ENDPOINT+"/query", args)
        features = block.get("features",[])
        if len(features) != min(BATCH,count-offset):
            raise ValueError(f"Unexpected NISR page length at {offset}: {len(features)}")
        found.extend(x["attributes"] for x in features)
    if len(found) != count:
        raise ValueError("NISR feature count differs across requests")
    output=[]; seen=set(); ids=Counter()
    for feature in found:
        r={field:normalize(feature.get(field)) for field in FIELDS}
        r["source_objectid"]=r.pop("objectid")
        oid=r["source_objectid"]; village=r["village_id"]
        if not oid or oid in seen: raise ValueError("Duplicate or missing ObjectID")
        seen.add(oid)
        if not village or not r["village"]:
            raise ValueError("Official village name or village_id missing")
        if not (r["province_id"] and r["district_id"] and r["sector_id"] and r["cell_id"]):
            raise ValueError("Missing official parent codes")
        if not village.startswith(r["cell_id"]):
            raise ValueError("Village ID does not begin with reported Cell ID")
        if not r["cell_id"].startswith(r["sector_id"]) or not r["sector_id"].startswith(r["district_id"]):
            raise ValueError("Official hierarchical code prefix mismatch")
        ids[village] += 1
        output.append({k:r[k] for k in OUTPUT_FIELDS})
    if ids and max(ids.values())>1:
        raise ValueError("Duplicate village IDs are not uniquely addressable")
    output.sort(key=lambda x:(x["village_id"],x["source_objectid"]))
    return output, {"source_url": ENDPOINT, "source_layer":"Village Boundary 2022 (Open Data)",
                    "source_authority":"National Institute of Statistics of Rwanda",
                    "source_year":2022, "claimed_license":"NISR public open-data service; confirm redistribution terms",
                    "record_count":count, "distinct_villages":len(ids),
                    "distinct_cells":len({x["cell_id"] for x in output}),
                    "distinct_sectors":len({x["sector_id"] for x in output}),
                    "distinct_districts":len({x["district_id"] for x in output}),
                    "distinct_provinces":len({x["province_id"] for x in output}),
                    "original_geonames_changed":False,
                    "current_legal_parent_links_certified":False,
                    "postal_address_deliverability_verified":False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output",type=Path,default=ROOT/"official-references"/"RW-NISR-2022-villages.csv")
    args=p.parse_args()
    rows,receipt=fetch()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    fd=io.StringIO(newline="")
    writer=csv.DictWriter(fd,fieldnames=OUTPUT_FIELDS,lineterminator="\n")
    writer.writeheader();writer.writerows(rows)
    payload=fd.getvalue().encode("utf-8")
    args.output.write_bytes(payload)
    receipt["derived_csv_bytes"]=len(payload)
    receipt["derived_csv_sha256"]=hashlib.sha256(payload).hexdigest()
    reportpath=args.output.with_suffix(".source.json")
    reportpath.write_text(json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(receipt,ensure_ascii=False,sort_keys=True))

if __name__=="__main__":
    main()
