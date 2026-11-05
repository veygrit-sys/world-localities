#!/usr/bin/env python3
"""Official Azerbaijan IABT 2024 8-digit administrative classification audit.

Acquisition is opt-in, from the exact government URL. Original bytes remain in
the caller's temporary directory until licence/republication review. Source
IDs and GeoNames IDs are separate; matches are review-only name candidates.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import urlparse
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
SOURCE="https://www.azstat.gov.az/tesnifat/cedeveller/arazi.jsp?parm=arazi"
CLASSIFICATION="AZ-IABT-2024"
MAX_BYTES=12000000
CODE=re.compile(r"[0-9]{8}")

class Table(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows=[]
        self.row=None
        self.cell=None
    def handle_starttag(self, tag, attrs):
        tag=tag.lower()
        if tag=="tr":self.row=[]
        elif tag in ("td","th") and self.row is not None:self.cell=[]
        elif tag=="br" and self.cell is not None:self.cell.append(" ")
    def handle_data(self, txt):
        if self.cell is not None:self.cell.append(txt)
    def handle_endtag(self, tag):
        tag=tag.lower()
        if tag in ("td","th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell=None
        elif tag=="tr" and self.row is not None:
            if self.row:self.rows.append(self.row)
            self.row=None
            self.cell=None

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def decode_html(blob: bytes) -> str:
    if len(blob)>MAX_BYTES:raise ValueError("Unexpected official source size")
    for enc in ("utf-8-sig","utf-8","windows-1254","cp1251"):
        try:
            text=blob.decode(enc)
            if "<tr" in text.lower() and ("Kod" in text or "Ad" in text):
                return text
        except UnicodeDecodeError:pass
    raise ValueError("HTML format/encoding changed or no official table")

def parse(blob: bytes, minimum: int=1) -> list[dict]:
    parser=Table()
    parser.feed(decode_html(blob))
    records=[]
    seen=set()
    for row in parser.rows:
        cells=[x.strip() for x in row if x.strip()]
        ids=[x for x in cells if CODE.fullmatch(x)]
        if len(ids)!=1:continue
        code=ids[0]
        name=" ".join(x for x in cells if x!=code).strip()
        if not name or code in seen:
            if code in seen:raise ValueError("Duplicate official code")
            continue
        seen.add(code)
        records.append({"official_ref":CLASSIFICATION+":"+code,
          "code":code,"name_az_source":name,"admin1_prefix":code[:3],
          "admin2_slice":code[3:5],"admin3_slice":code[5:7],
          "status_digit":code[7],"official_to_geonames_verified":False,
          "official_to_postcode_verified":False})
    if len(records)<minimum:
        raise ValueError("Classification too small; source changed: "+str(len(records)))
    return records

def key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC",value).casefold().split())

def variants(value: str) -> set[str]:
    s=key(value)
    out={s}
    base=re.sub(r"^(?:(?:[0-9]+|[ivxlcdm]+)[.)]\s*)+", "",s,flags=re.I).strip()
    out.add(base)
    for ending in (" rayonu"," şəhəri"," qəsəbəsi"," kəndi"," q."," k."," ş."):
        if base.endswith(ending):out.add(base[:-len(ending)].strip())
    t=re.sub(r"\s+(?:q|k|ş)\.$","",base)
    pieces=t.split()
    if len(pieces)>=4 and all(len(p)==1 for p in pieces):
        out.add("".join(pieces))
    return {x for x in out if x}

def candidate_counts(records: list[dict], geonames: list[dict]) -> tuple[dict,list[dict]]:
    index=defaultdict(set)
    for row in geonames:
        if row["kind"] not in ("locality","admin_subdivision"):
            continue
        for name in (row["name"],row["asciiname"],*(row.get("alternatenames") or "").split(",")):
            if name:index[key(name)].add(row["id"])
    totals=Counter()
    samples=[]
    for item in records:
        ids=sorted(set().union(*(index.get(name,set()) for name in variants(item["name_az_source"]))))
        state="none" if not ids else "unique_unreviewed" if len(ids)==1 else "ambiguous_unreviewed"
        totals[state]+=1
        if state=="unique_unreviewed" and len(samples)<20:
            samples.append({"code":item["code"],"name":item["name_az_source"],
                            "gn_id_candidate":ids[0],"approved":False})
    return dict(sorted(totals.items())),samples

def audit(blob: bytes, minimum:int, geonames: list[dict]|None=None) -> dict:
    rows=parse(blob,minimum)
    report={"source":SOURCE,"edition":2024,"original_sha256":sha(blob),
      "original_bytes":len(blob),"rows":len(rows),
      "distinct_8_digit_codes":len(set(r["code"] for r in rows)),
      "distinct_level1_prefixes":len(set(r["admin1_prefix"] for r in rows)),
      "last_digit_status_distribution":dict(sorted(Counter(r["status_digit"] for r in rows).items())),
      "source_sample":[{"code":r["code"],"name":r["name_az_source"]} for r in rows[:8]],
      "official_code_to_geonames_verified":0,
      "official_code_to_postcode_verified":0,
      "is_postcode_source":False,
      "2026_national_completeness_verified":False,
      "redistribution_license_approved":False}
    if geonames is not None:
        counts,examples=candidate_counts(rows,geonames)
        report["geonames_review_candidates"]=counts
        report["review_examples"]=examples
    return report

def fetch(path:Path) -> dict:
    req=Request(SOURCE,headers={"User-Agent":"WorldLocalitiesOfficialSourceAudit/1.0"})
    with urlopen(req,timeout=40) as response:
        if urlparse(response.geturl()).hostname not in ("azstat.gov.az","www.azstat.gov.az"):
            raise ValueError("Unexpected redirect from official origin")
        data=response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES:raise ValueError("Unexpected source size")
        metadata={"source_url":response.geturl(),"retrieved_at":datetime.now(timezone.utc).isoformat(),
                  "content_type":response.headers.get("Content-Type"),
                  "bytes":len(data),"sha256":sha(data)}
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)
    return metadata

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("fetch","audit"))
    parser.add_argument("--source",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--min-rows",type=int,default=1)
    parser.add_argument("--geonames",action="store_true")
    args=parser.parse_args()
    if args.command=="fetch":
        result=fetch(args.output)
    else:
        if args.source is None:parser.error("--source is required for audit")
        gn=None
        if args.geonames:
            import western_asia_caucasus_levant_join as core
            gn,_=core.load_gazetteer("AZ")
        result=audit(args.source.read_bytes(),args.min_rows,gn)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("AZSTAT2024_OFFICIAL_SOURCE_AUDIT "+json.dumps(result,ensure_ascii=False,sort_keys=True))

if __name__=="__main__":main()
