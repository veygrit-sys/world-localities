#!/usr/bin/env python3
"""Source-evidence candidate reconciliation for AM GE AZ IL JO.

Office postcodes, published address examples and localities have distinct grains.
No string or postcode match proves postal assignment, current boundaries, or delivery.
The packaged GeoNames archive is read with verified SHA-256 and IDs are unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import unicodedata
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "registries/official/western-asia/caucasus-levant/source_evidence.json"
ASIA = ROOT / "registries/asia"
COUNTRIES = ("AM","GE","AZ","IL","JO")
SCHEMES = {"AM":r"[0-9]{4}", "GE":r"[0-9]{4}", "AZ":r"AZ[0-9]{4}",
           "IL":r"[0-9]{7}", "JO":r"[0-9]{5}"}
NEEDED = {"id","country_code","name","asciiname","alternatenames",
          "kind","feature_code","admin_level","state_id","address_candidate"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def name_key(value: str) -> str:
    """NFC+casefold+whitespace only. Do NOT generate translations."""
    return " ".join(unicodedata.normalize("NFC",value).casefold().split())


def load_sources(path: Path = SOURCE) -> dict:
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("schema_version") != 1 or set(d.get("country_scope",())) != set(COUNTRIES):
        raise ValueError("Invalid five-country source inventory")
    if d.get("official_original_source_datasets_imported") != 0:
        raise ValueError("Source original-data import unsupported in this release")
    if d.get("official_postcode_to_geonames_links_verified") != 0:
        raise ValueError("Cannot claim unreviewed postal/GeoNames identity")
    for cc in COUNTRIES:
        p=d["country_administrations"][cc]
        if p["level"]!=1 or not p["url"].startswith("https://"):
            raise ValueError("Bad administrative source: "+cc)
        seen=set()
        for row in p["records"]:
            if not row["source_key"].startswith(cc+":") or row["source_key"] in seen:
                raise ValueError("Bad/duplicate administrative source key")
            seen.add(row["source_key"])
            if not row["name"] or row["legally_equivalent_to_geonames_verified"]:
                raise ValueError("Bad/overclaimed government names")
    counts=Counter()
    ids=set()
    for id,spec in d["postal_sources"].items():
        if spec["country"] not in COUNTRIES or not spec["url"].startswith("https://"):
            raise ValueError("Bad postal source")
        if spec["original_sha256"] is not None or not spec["republication"]:
            raise ValueError("Undownloaded source hash or missing reuse review")
    known={cc:{r["name"] for r in d["country_administrations"][cc]["records"]}
           for cc in COUNTRIES}
    for row in d["postal_evidence"]:
        cc=row["country"]
        if cc not in COUNTRIES or row["source_id"] not in d["postal_sources"]:
            raise ValueError("Unrecognized postal evidence source")
        if d["postal_sources"][row["source_id"]]["country"]!=cc:
            raise ValueError("Cross-country postal source")
        if row["record_id"] in ids:
            raise ValueError("Duplicate source record")
        ids.add(row["record_id"])
        if not re.fullmatch(SCHEMES[cc],row["code"]):
            raise ValueError("Invalid postal code syntax: "+cc+"/"+row["code"])
        if not row["place"] or row.get("verified_postcode_to_geonames_link") is not False:
            raise ValueError("Postal record missing place or overclaims GN identity")
        if row.get("verified_delivery") is not False:
            raise ValueError("No deliverability evidence imported")
        if row["admin_name"] is not None and row["admin_name"] not in known[cc]:
            raise ValueError("Invalid administrative name key")
        if cc=="AZ" and row["locale"] not in ("az-Latn","en"):
            raise ValueError("AZ name must use explicit locale")
        counts[cc]+=1
    if counts != {"AM":14,"GE":3,"AZ":24,"IL":2,"JO":3}:
        raise ValueError("Expected country source record inventory changed without review")
    return d


def load_gazetteer(country: str, root: Path = ASIA) -> tuple[list[dict],dict]:
    if country not in COUNTRIES:
        raise ValueError("Unknown country")
    inv=json.loads((root/"archives.json").read_text(encoding="utf-8"))
    found=[r for r in inv["archives"] if r["country"]==country]
    if len(found)!=1: raise ValueError("Missing or duplicate archive")
    entry=found[0]
    base="country-archives/"+country+".zip"
    if entry["path"]!=base or not entry["parts"]:
        raise ValueError("Invalid zip inventory")
    pieces=[]
    for i,part in enumerate(entry["parts"],1):
        suffix=base if len(entry["parts"])==1 else base+".part%03d"%i
        if part["path"]!=suffix:
            raise ValueError("Unexpected archive volume path")
        b=(root/suffix).read_bytes()
        if len(b)!=part["bytes"] or digest(b)!=part["sha256"]:
            raise ValueError("Archive volume checksum does not match")
        pieces.append(b)
    packed=b"".join(pieces)
    if len(packed)!=entry["bytes"] or digest(packed)!=entry["sha256"]:
        raise ValueError("Source archive checksum failure")
    with zipfile.ZipFile(io.BytesIO(packed)) as z:
        if set(z.namelist()) != set(entry["members"]):
            raise ValueError("Unexpected ZIP member structure")
        name=country+"/entities.csv.gz"
        blob=z.read(name)
        if len(blob)!=entry["members"][name]["bytes"] or digest(blob)!=entry["members"][name]["sha256"]:
            raise ValueError("Gazetteer member checksum failure")
    rows=list(csv.DictReader(io.StringIO(gzip.decompress(blob).decode("utf-8"))))
    if not rows or not NEEDED.issubset(rows[0]) or len(rows)!=entry["rows"]:
        raise ValueError("Unexpected GeoNames schema/row count")
    if len({x["id"] for x in rows})!=len(rows):
        raise ValueError("Duplicate GeoNames IDs")
    for row in rows:
        if row["country_code"]!=country or not re.fullmatch(r"gn:[1-9][0-9]*",row["id"]):
            raise ValueError("Bad source country or GeoNames identity")
    return rows, {"archive_sha256":entry["sha256"],"source_rows":len(rows)}


def _variants(row: dict) -> set[str]:
    strings=(row["name"],row["asciiname"],*(row["alternatenames"] or "").split(","))
    return {name_key(s) for s in strings if s}


def compare_admin(country: str, rows: list[dict], dataset: dict) -> list[dict]:
    admins=[r for r in rows if r["kind"]=="admin_subdivision"
            and r["admin_level"]=="1" and r["feature_code"]=="ADM1"]
    out=[]
    for official in dataset["country_administrations"][country]["records"]:
        primary=name_key(official["name"])
        aliases={name_key(s) for s in official["aliases"]}
        direct=[r["id"] for r in admins if primary in {name_key(r["name"]),name_key(r["asciiname"])}]
        alias=[r["id"] for r in admins if primary in _variants(r) or
               aliases.intersection(_variants(r))]
        candidates=sorted(set(direct if direct else alias))
        out.append({
            "source_key":official["source_key"],"source_name":official["name"],
            "source_url":dataset["country_administrations"][country]["url"],
            "geonames_candidate_ids":candidates,
            "status":"unmatched" if not candidates else
                     "unique_candidate" if len(candidates)==1 else "ambiguous_candidates",
            "match_basis":"source_name_exact" if direct else
                          "unlabelled_alias_or_curated_variant" if candidates else None,
            "government_identity_verified":False,"postal_assignment_verified":False
        })
    return out


def postcode_format(country: str, code: str) -> dict:
    """Checks input syntax; never says that code exists or belongs to a locality."""
    if country not in COUNTRIES:raise ValueError("Unknown country")
    if not isinstance(code,str): raise TypeError("Postcode must be string")
    if any(unicodedata.category(x).startswith("C") for x in code):
        raise ValueError("Control characters in postal code")
    raw=code.strip()
    canonical=raw.upper() if country=="AZ" else raw
    invalid=not bool(re.fullmatch(SCHEMES[country],canonical))
    return {
        "country":country,"input":raw,
        "code":canonical if not invalid else None,
        "status":"invalid_format" if invalid else "format_only",
        "postcode_assigned_verified":False,"locality_verified":False,
        "deliverability_verified":False,
        "normalization_note":"ISO AZ prefix retained" if country=="AZ" else "ASCII digits required",
    }


def _locality_index(rows: list[dict]) -> dict[str,dict[str,str]]:
    idx=defaultdict(dict)
    for r in rows:
        if r["kind"]!="locality" or r["address_candidate"]!="1":continue
        for v in _variants(r):
            idx[v][r["id"]]=r["state_id"]
    return idx


def compare_postal(country: str, rows: list[dict], dataset: dict,
                   government: list[dict]) -> list[dict]:
    idx=_locality_index(rows)
    by_name={entry["source_name"]:entry for entry in government}
    out=[]
    for rec in dataset["postal_evidence"]:
        if rec["country"]!=country:continue
        scope=by_name.get(rec["admin_name"]) if rec["admin_name"] else None
        # Narrow candidates only to a unique unverified GeoNames ADM1 candidate,
        # not to a guess from postcode prefixes. All links still unverified.
        filter_ids=set(scope["geonames_candidate_ids"]) if scope and scope["status"]=="unique_candidate" else None
        names=idx.get(name_key(rec["place"]),{})
        matches=sorted(gid for gid,state_id in names.items()
                       if filter_ids is None or state_id in filter_ids)
        code=postcode_format(country,rec["code"])
        if code["status"]!="format_only":raise ValueError("Saved source code fails syntax contract")
        out.append({
            "record_id":rec["record_id"],"source_id":rec["source_id"],
            "source_url":dataset["postal_sources"][rec["source_id"]]["url"],
            "code":rec["code"],"name":rec["place"],"language":rec["locale"],
            "source_grain":rec["grain"],"source_admin_label":rec["admin_name"],
            "gov_area_candidate":scope["status"] if scope else "not_provided",
            "candidate_geonames_ids":matches,
            "status":"unmatched" if not matches else
                     "unique_unreviewed" if len(matches)==1 else "ambiguous_unreviewed",
            "official_postal_value_transcribed":True,
            "postal_assignment_to_geonames_verified":False,
            "building_address_verified":False,
            "carrier_deliverability_verified":False
        })
    return out


def country_report(country: str, *, dataset: dict | None = None,
                   root: Path = ASIA) -> dict:
    dataset=dataset or load_sources()
    rows,meta=load_gazetteer(country,root)
    admin_candidates=compare_admin(country,rows,dataset)
    postal_candidates=compare_postal(country,rows,dataset,admin_candidates)
    admin_count=Counter(x["status"] for x in admin_candidates)
    postal_count=Counter(x["status"] for x in postal_candidates)
    codes=defaultdict(set)
    for item in postal_candidates:codes[item["code"]].add(name_key(item["name"]))
    return {
        "country":country,**meta,
        "official_admin_names":len(admin_candidates),
        "admin_unique_candidates_unreviewed":admin_count["unique_candidate"],
        "admin_ambiguous_candidates_unreviewed":admin_count["ambiguous_candidates"],
        "admin_names_unmatched":admin_count["unmatched"],
        "geonames_adm1_rows":sum(x["admin_level"]=="1" for x in rows),
        "geonames_localities_without_adm1":sum(x["kind"]=="locality" and not x["state_id"] for x in rows),
        "published_postal_source_rows":len(postal_candidates),
        "distinct_published_codes":len(codes),
        "postal_codes_with_multiple_place_names":sum(len(v)>1 for v in codes.values()),
        "postal_unique_candidates_unreviewed":postal_count["unique_unreviewed"],
        "postal_ambiguous_candidates_unreviewed":postal_count["ambiguous_unreviewed"],
        "postal_unmatched":postal_count["unmatched"],
        "approved_admin_geonames_identity_links":0,
        "approved_postal_geonames_identity_links":0,
        "official_original_bulk_datasets_imported":0,
        "delivery_verified":False,
        "government_admin_records":admin_candidates,
        "published_postal_records":postal_candidates,
    }


def summary() -> dict:
    dataset=load_sources()
    reports=[country_report(cc,dataset=dataset) for cc in COUNTRIES]
    return {
        "schema_version":1,"reviewed_at":dataset["reviewed_at"],
        "country_reports":reports,
        "total_postal_source_rows":sum(r["published_postal_source_rows"] for r in reports),
        "total_official_admin_names":sum(r["official_admin_names"] for r in reports),
        "approved_admin_geonames_links":0,
        "approved_postal_geonames_links":0,
        "status":"source_excerpts_to_unreviewed_candidates_only",
    }


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("command",choices=("report","postcode","find-code"))
    p.add_argument("--country",choices=(*COUNTRIES,"all"),default="all")
    p.add_argument("--code")
    p.add_argument("--output",type=Path)
    args=p.parse_args()
    if args.command=="report":
        out=summary() if args.country=="all" else country_report(args.country)
    elif args.command=="postcode":
        if args.country=="all" or args.code is None:p.error("--country and --code are needed")
        out=postcode_format(args.country,args.code)
    else:
        if args.country=="all" or args.code is None:p.error("--country and --code are needed")
        report=country_report(args.country)
        out={"country":args.country,"input_code":args.code,
             "source_records":[row for row in report["published_postal_records"]
                               if row["code"]==args.code],
             "no_source_result_does_not_mean_invalid":True}
    text=json.dumps(out,ensure_ascii=False,sort_keys=True,indent=2)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(text,encoding="utf-8")
    else:print(text,end="")


if __name__=="__main__":
    main()
