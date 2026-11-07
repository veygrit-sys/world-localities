#!/usr/bin/env python3
"""Extract ODbL OpenStreetMap place nodes, preserving source identity.

Independent from GeoNames and official administration. Never auto-merge names,
do not geocode private users, infer official jurisdiction or claim deliverability.
Inputs: public Geofabrik country PBFs, with published MD5 verified.
"""
import argparse
import csv
import gzip
import hashlib
import io
import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

import osmium

ROOT=Path(__file__).resolve().parent
COUNTRIES={
    "ZA":("south-africa","ZAF"),
    "NG":("nigeria","NGA"),
    "KE":("kenya","KEN"),
    "GH":("ghana","GHA"),
}
PLACE_TYPES={"city","town","village","hamlet","suburb","neighbourhood","quarter","locality"}
HEADERS=["country","osm_id","place_type","name","name_en","name_fr","name_ar",
         "name_sw","name_zu","name_af","longitude","latitude","source_license"]
MAX_PBF_BYTES=1_100_000_000

def sha_file(path,kind):
    h=hashlib.new(kind)
    with path.open("rb") as src:
        for block in iter(lambda:src.read(4*1024*1024),b""):h.update(block)
    return h.hexdigest()

def download(country, cache):
    filename,iso=COUNTRIES[country]
    base="https://download.geofabrik.de/africa/"+filename+"-latest.osm.pbf"
    cache.mkdir(parents=True,exist_ok=True)
    req=Request(base+".md5",headers={"User-Agent":"world-localities-osm-place-extract/1.0"})
    with urlopen(req,timeout=90) as rsp: sidecar=rsp.read(500).decode("ascii")
    m=re.search(r"\b([0-9a-fA-F]{32})\b",sidecar)
    if not m: raise ValueError("Geofabrik checksum sidecar unavailable")
    expected=m[1].lower()
    p=cache/(filename+"-"+expected[:10]+".osm.pbf")
    if not p.is_file():
        req=Request(base,headers={"User-Agent":"world-localities-osm-place-extract/1.0"})
        with urlopen(req,timeout=300) as rsp,p.open("wb") as out:
            length=0
            while True:
                block=rsp.read(4*1024*1024)
                if not block:break
                length+=len(block)
                if length>MAX_PBF_BYTES:raise ValueError("unexpected oversize Geofabrik file")
                out.write(block)
    if sha_file(p,"md5")!=expected:
        raise ValueError("PBF checksum differs from Geofabrik; never parse")
    return p,base,expected

class PlaceNodes(osmium.SimpleHandler):
    def __init__(self,country,writer):
        super().__init__()
        self.country=country
        self.writer=writer
        self.count=0
        self.counts={}
    def node(self,n):
        t=n.tags
        place=t.get("place")
        if place not in PLACE_TYPES:return
        name=t.get("name")
        if not name or not n.location.valid():return
        def take(key):
            s=t.get(key)
            return s if s is not None else ""
        self.writer.writerow({
            "country":self.country,
            "osm_id":"osm:node:"+str(n.id),
            "place_type":place,
            "name":name,
            "name_en":take("name:en"),
            "name_fr":take("name:fr"),
            "name_ar":take("name:ar"),
            "name_sw":take("name:sw"),
            "name_zu":take("name:zu"),
            "name_af":take("name:af"),
            "longitude":f"{n.location.lon:.7f}",
            "latitude":f"{n.location.lat:.7f}",
            "source_license":"ODbL-1.0",
        })
        self.count+=1
        self.counts[place]=self.counts.get(place,0)+1

def extract(country,pbf,outroot,source_url,source_md5):
    outdir=outroot/country
    outdir.mkdir(parents=True,exist_ok=True)
    rawpath=outdir/"place-nodes.csv.gz"
    with rawpath.open("wb") as out:
        with gzip.GzipFile(fileobj=out,mode="wb",filename="",mtime=0,compresslevel=9) as gz:
            with io.TextIOWrapper(gz,encoding="utf-8",newline="",write_through=True) as handle:
                writer=csv.DictWriter(handle,fieldnames=HEADERS,lineterminator="\n")
                writer.writeheader()
                places=PlaceNodes(country,writer)
                places.apply_file(str(pbf),locations=False)
                handle.flush()
    if places.count<100:
        raise ValueError(f"{country}: unexpectedly few OSM populated place nodes")
    receipt={
        "country":country,
        "source_url":source_url,"source_md5":source_md5,
        "source_sha256":sha_file(pbf,"sha256"),
        "source_bytes":pbf.stat().st_size,
        "derived_file":"place-nodes.csv.gz",
        "derived_sha256":sha_file(rawpath,"sha256"),
        "derived_bytes":rawpath.stat().st_size,
        "place_node_rows":places.count,
        "by_type":dict(sorted(places.counts.items())),
        "source_license":"Open Database License 1.0 (ODbL)",
        "license_url":"https://www.openstreetmap.org/copyright",
        "original_source_namespace":"osm:node:",
        "geofabrik_contributor_metadata_excluded":True,
        "features_included":"named place nodes only; not ways/relations, streets, housenumbers or postal addresses",
        "postal_address_or_delivery_verified":False,
        "official_admin_parent_verified":False,
    }
    (outdir/"source-receipt.json").write_text(
        json.dumps(receipt,ensure_ascii=False,sort_keys=True,indent=2)+"\n",
        encoding="utf-8")
    return receipt

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--country",choices=sorted(COUNTRIES),required=True)
    p.add_argument("--cache",type=Path,default=ROOT/".cache/geofabrik")
    p.add_argument("--output",type=Path,default=ROOT/"osm-localities")
    args=p.parse_args()
    file,url,md5=download(args.country,args.cache)
    print(json.dumps(extract(args.country,file,args.output,url,md5),ensure_ascii=False))

if __name__=="__main__":main()
