#!/usr/bin/env python3
"""Read-only evidence, provenance, uniqueness and grain checks for African expansion.

All tables are separate source layers. Checks do not assert current legal
administrative parent IDs or postal deliverability. No original GeoNames edit.
"""
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
from collections import Counter

ROOT=Path(__file__).resolve().parent

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def digest(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):
            h.update(b)
    return h.hexdigest()

def blob(path):
    data=path.read_bytes()
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def rows(path):
    with path.open("rt",encoding="utf-8-sig",newline="") as f:
        return list(csv.DictReader(f))

def key_check(data,fields,label):
    if not data:raise ValueError(label+" empty")
    if any(any(not r.get(k,"").strip() for k in fields) for r in data):
        raise ValueError(label+" missing required key")
    keys=[tuple(r[k] for k in fields) for r in data]
    if len(keys)!=len(set(keys)):
        raise ValueError(label+" duplicate source keys")

def verify():
    problems=[]
    report={}
    def check(code,action):
        try:report[code]=action()
        except (ValueError,OSError,KeyError,AssertionError,TypeError) as exc:
            problems.append(f"{code}: {exc}")
    d=ROOT/"official-references"
    e=ROOT/"extended-boundaries"
    a=ROOT/"reference-boundaries"
    o=ROOT/"osm-localities"

    def rwanda():
        meta=load(d/"RW-NISR-2022-villages.source.json")
        path=d/"RW-NISR-2022-villages.csv"
        if digest(path)!=meta["derived_csv_sha256"] or path.stat().st_size!=meta["derived_csv_bytes"]:
            raise ValueError("RW SHA/size source receipt mismatch")
        data=rows(path)
        if len(data)!=14823 or len(data)!=meta["record_count"]:
            raise ValueError("RW NISR 2022 village row count changed")
        key_check(data,["village_id"],"RW villages")
        for child,parent in (("village_id","cell_id"),("cell_id","sector_id"),("sector_id","district_id")):
            if any(not r[child].startswith(r[parent]) for r in data):
                raise ValueError("NISR hierarchical code prefix inconsistency")
        for field,expected in (("cell_id",2148),("sector_id",416),("district_id",30),("province_id",5)):
            if len(set(r[field] for r in data))!=expected:
                raise ValueError(f"NISR {field} distinct count drift")
        return {"rows":len(data),"source_year":2022,"verified_source_hash":True,
                "current_admin_validated":False}

    def morocco():
        path=d/"MA-HCP-2024-communes.csv"
        if blob(path)!="6d76b6b085ff5e7e6e08b8a6af4916b2f9e65d89":
            raise ValueError("Morocco derived CSV Git blob identity differs")
        data=rows(path)
        if len(data)!=1503:raise ValueError("RGPH 2024 commune count drift")
        key_check(data,["code24"],"MA 2024 communes")
        if any(not x["name_fr"] or not x["name_ar"] or not x["province_name_fr"] for x in data):
            raise ValueError("missing bilingual commune/province fields")
        if any(x["legal_parent_code_verified"]!="false" for x in data):
            raise ValueError("unreviewed province legal parent code was promoted")
        return {"rows":1503,"source_year":2024,"verified_derived_blob":True,
                "province_legal_codes_verified":False}

    def algeria():
        p=d/"DZ-2026-wilayas.csv"
        q=d/"DZ-2026-communes.csv"
        if blob(p)!="97a57084c54ca51d45b1cf4e32fc05568406b38b":
            raise ValueError("wilaya names table changed")
        if blob(q)!="760cfd024ae436cc025fcf76d2475f1123ca9675":
            raise ValueError("commune names table changed")
        prov,comm=rows(p),rows(q)
        if len(prov)!=69 or len(comm)!=1541:
            raise ValueError("2026 administrative count differs")
        key_check(prov,["wilaya_code"],"DZ provinces")
        codes={x["wilaya_code"] for x in prov}
        if any(c["wilaya_code"] not in codes or
               c["has_official_commune_code"]!="false" for c in comm):
            raise ValueError("commune member without province or false official code claim")
        if any(not r["commune_name_ar"] or not r["commune_name_latin"] for r in comm):
            raise ValueError("missing Arabic/Latin DZ names")
        return {"wilayas":len(prov),"communes":len(comm),
                "source_year":2026,"true_commune_codes_available":False}

    def egypt():
        m=load(d/"EG-CAPMAS-OCHA-2020-ADM2.source.json")
        p=d/"EG-CAPMAS-OCHA-2020-ADM2.csv"
        if digest(p)!=m["derived_csv_sha256"] or p.stat().st_size!=m["derived_csv_bytes"]:
            raise ValueError("Egypt original-derived CSV checksum mismatch")
        records=rows(p)
        if len(records)!=365 or len(records)!=m["count"]:
            raise ValueError("Egypt source units count drift")
        key_check(records,["source_shape_id"],"Egypt source shape")
        return {"rows":len(records),"source_year":2020,
                "current_admin_codes_verified":False}

    def za_ng():
        m=load(e/"source_receipts.json")
        expected={"NGA-ADM1":37,"NGA-ADM2":774,
                  "ZAF-ADM1":9,"ZAF-ADM2":52,"ZAF-ADM3":213}
        if set(m["sources"])!=set(expected) or m["records"]!=1085:
            raise ValueError("NA/ZA source manifest/total changed")
        for group,count in expected.items():
            source=m["sources"][group]
            p=e/(group+"-source-units.csv")
            if digest(p)!=source["derived_csv_sha256"] or p.stat().st_size!=source["derived_csv_bytes"]:
                raise ValueError("derived source bytes changed: "+group)
            data=rows(p)
            if len(data)!=count:raise ValueError("records differ "+group)
            key_check(data,["shape_id"],group+" original IDs")
            if group.endswith(("ADM2","ADM3")) and any(not r["parent_shape_id"] for r in data):
                raise ValueError("source year associations dropped "+group)
            if any(r["source_sha256"]!=source["sha256"] for r in data):
                raise ValueError("original source hash provenance mismatch "+group)
        if m["official_legal_parent_links_certified"]!=0:raise ValueError("False legal certification")
        return {"rows":1085,"layers":expected,"current_legal_admin_parent_links_approved":0}

    def prior_gaps():
        s=load(a/"unresolved-spatial-summary.json")
        if s["input_unresolved_cases"]!={"KE":69,"GH":11} or s["approved_administrative_parent_links"]!=0:
            raise ValueError("previous 80 GeoNames direct parent gaps count mismatch")
        if s["source_year_spatial_memberships"]!=66:
            raise ValueError("dated secondary spatial overlay count drift")
        return {"original_missing_geonames_parent_ids":80,
                "spatial_memberships_source_year":66,
                "original_parent_ids_officially_repaired":0}

    def osm(country):
        d=o/country
        p=d/"place-nodes.csv.gz"
        receipt=load(d/"source-receipt.json")
        if digest(p)!=receipt["derived_sha256"]:
            raise ValueError("OSM compressed CSV source SHA drift")
        with gzip.open(p,"rt",encoding="utf-8",newline="") as source:
            reader=csv.DictReader(source)
            ids=set()
            count=0
            for row in reader:
                if row["country"]!=country or not row["name"] or not row["osm_id"].startswith("osm:node:"):
                    raise ValueError("OSM source identity or name malformed")
                if row["osm_id"] in ids:raise ValueError("OSM duplicate node ID")
                ids.add(row["osm_id"])
                count+=1
        if count!=receipt["place_node_rows"]:raise ValueError("OSM source place count drift")
        if receipt["source_license"]!="Open Database License 1.0 (ODbL)":
            raise ValueError("OSM licence mismatch")
        return {"rows":count,"source_md5":receipt["source_md5"],
                "original_country_pbf_bytes":receipt["source_bytes"],
                "original_administrative_parent_links_approved":0}

    for code,fn in (("RW",rwanda),("MA",morocco),("DZ",algeria),
                    ("EG",egypt),("ZA-NG",za_ng),("KE-GH-gaps",prior_gaps)):
        check(code,fn)
    for code in ("ZA","NG","KE","GH"):
        if (o/code/"source-receipt.json").is_file():
            check("OSM-"+code,lambda code=code:osm(code))
        else:
            report["OSM-"+code]={"status":"not_yet_imported"}
    return {"scope":"source-provenance, record-grain and temporal QA; NOT legal address/delivery verification",
            "reports":report,"errors":problems,
            "source_layers_are_distinct":True,
            "deliverability_verified":False}

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("--check",action="store_true")
    args=parser.parse_args()
    result=verify()
    print(json.dumps(result,ensure_ascii=False,sort_keys=True,indent=2))
    if result["errors"] and args.check:raise SystemExit(1)

if __name__=="__main__":main()
