#!/usr/bin/env python3
"""Immutable, source-qualified HMS Iceland address-point ingestion.

HNITNUM identifies a coordinate point; HEINUM identifies a source address, which
can have multiple points. Not a delivery-address or postcode certification.
Only allowlisted public location fields are copied: never ATH or NOTNR.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,re,sqlite3,tempfile
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation

URL="https://hmsstgsftpprodweu001.blob.core.windows.net/fasteignaskra/Stadfangaskra.csv"
REQUIRED={"HNITNUM","HEINUM","SVFNR","BYGGD","POSTNR","HEITI_NF","HUSNR",
          "BOKST","VIDSK","SERHEITI","N_HNIT_WGS84","E_HNIT_WGS84",
          "TEGHNIT","YFIRFARID","DAGS_INN","DAGS_LEIDR"}
COLUMNS=["hnitnum","heinum","municipality_code","settlement_code","postcode",
 "street_or_place","house_number","house_letter","house_suffix","special_name",
 "lat_wgs84","lon_wgs84","coordinate_kind","coordinate_review",
 "date_recorded","date_corrected","content_sha256"]
SCHEMA="""
CREATE TABLE address_points(
 hnitnum TEXT PRIMARY KEY NOT NULL, heinum TEXT NOT NULL,
 municipality_code TEXT NOT NULL, settlement_code TEXT NOT NULL,
 postcode TEXT NOT NULL, street_or_place TEXT NOT NULL,
 house_number TEXT NOT NULL, house_letter TEXT NOT NULL,
 house_suffix TEXT NOT NULL, special_name TEXT NOT NULL,
 lat_wgs84 REAL, lon_wgs84 REAL, coordinate_kind TEXT NOT NULL,
 coordinate_review TEXT NOT NULL, date_recorded TEXT NOT NULL,
 date_corrected TEXT NOT NULL, content_sha256 TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX ix_is_addr ON address_points(heinum);
CREATE INDEX ix_is_postcode_street ON address_points(postcode,street_or_place);
CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

def sha256(path):
 h=hashlib.sha256()
 with Path(path).open("rb") as f:
  for b in iter(lambda:f.read(1048576),b""):h.update(b)
 return h.hexdigest()

def coordinate(s,lat):
 if not s.strip():return None
 try:v=Decimal(s.strip().replace(",","."))
 except InvalidOperation as e:raise ValueError("Malformed WGS84 coordinate") from e
 if not v.is_finite() or not (-90<=v<=90 if lat else -180<=v<=180):
  raise ValueError("WGS84 coordinate outside allowed range")
 return float(v)

def project(row):
 def f(k):
  if k not in row or row[k] is None:raise ValueError("Missing HMS column "+k)
  return row[k].strip()
 point,address,municipality=f("HNITNUM"),f("HEINUM"),f("SVFNR")
 if not point.isdigit() or not address.isdigit() or not re.fullmatch(r"[0-9]{1,4}",municipality):
  raise ValueError("Missing/non-numeric HMS original identifiers")
 postcode=f("POSTNR")
 if postcode and not re.fullmatch(r"[0-9]{3}",postcode):
  raise ValueError("Invalid source postcode syntax")
 values=(point,address,municipality,f("BYGGD"),postcode,f("HEITI_NF"),
         f("HUSNR"),f("BOKST"),f("VIDSK"),f("SERHEITI"),
         coordinate(f("N_HNIT_WGS84"),True),coordinate(f("E_HNIT_WGS84"),False),
         f("TEGHNIT"),f("YFIRFARID"),f("DAGS_INN"),f("DAGS_LEIDR"))
 for v in values[12:14]:
  if v and not v.isdigit():raise ValueError("Invalid source coordinate quality value")
 identity_hash=hashlib.sha256(json.dumps(values,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
 return (*values,identity_hash)

def ingest(source,db_path,receipt_path,expected_hash=None):
 source,db_path,receipt_path=map(Path,(source,db_path,receipt_path))
 if not source.is_file():raise ValueError("Actual HMS CSV is missing")
 if db_path==receipt_path or any(p.exists() or p.is_symlink() for p in (db_path,receipt_path)):
  raise ValueError("Output already exists: never overwrite an accepted snapshot")
 digest=sha256(source)
 if expected_hash and digest!=expected_hash:raise ValueError("Source byte pin changed")
 db_path.parent.mkdir(parents=True,exist_ok=True);receipt_path.parent.mkdir(parents=True,exist_ok=True)
 fd,tmp=tempfile.mkstemp(prefix=".hms-",suffix=".sqlite",dir=db_path.parent);os.close(fd)
 stats={"rows":0,"missing_postcode":0,"missing_house_number":0,"missing_street_or_place":0,
        "missing_wgs84":0}
 kinds={};reviews={}
 try:
  db=sqlite3.connect(tmp)
  try:
   db.executescript(SCHEMA)
   with source.open("r",encoding="utf-8-sig",newline="") as stream:
    rows=csv.DictReader(stream)
    if not rows.fieldnames or len(set(rows.fieldnames))!=len(rows.fieldnames) or not REQUIRED<=set(rows.fieldnames):
     raise ValueError("HMS CSV schema differs from source contract")
    headers=rows.fieldnames
    insert="INSERT INTO address_points VALUES ("+",".join("?" for _ in COLUMNS)+")"
    with db:
     for line,row in enumerate(rows,2):
      if None in row or any(v is None for v in row.values()):
       raise ValueError("Malformed HMS source row "+str(line))
      entry=project(row)
      try:db.execute(insert,entry)
      except sqlite3.IntegrityError as e:raise ValueError("Duplicate HNITNUM source point ID") from e
      stats["rows"]+=1
      if not entry[4]:stats["missing_postcode"]+=1
      if not entry[6]:stats["missing_house_number"]+=1
      if not entry[5]:stats["missing_street_or_place"]+=1
      if entry[10] is None or entry[11] is None:stats["missing_wgs84"]+=1
      kinds[entry[12]]=kinds.get(entry[12],0)+1
      reviews[entry[13]]=reviews.get(entry[13],0)+1
   with db:
    for key,value in {"dataset":"HMS Staðfangaskrá","country":"IS","source_url":URL,
      "source_sha256":digest,"source_bytes":source.stat().st_size,
      "retrieved_at_utc":datetime.now(timezone.utc).isoformat(),
      "source_columns":headers,"primary_point_id":"HNITNUM","address_id":"HEINUM",
      "coordinate_crs":"WGS84","rights_reviewed_for_redistribution":False,
      "delivery_verified":False}.items():
     db.execute("INSERT INTO metadata VALUES (?,?)",(key,json.dumps(value,ensure_ascii=False)))
   count=db.execute("SELECT COUNT(*) FROM address_points").fetchone()[0]
   unique_address_ids=db.execute("SELECT COUNT(DISTINCT heinum) FROM address_points").fetchone()[0]
   if count!=stats["rows"] or db.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
    raise ValueError("HMS index count or integrity check failed")
  finally:db.close()
  report={"status":"PASS","country":"IS","source":"HMS Staðfangaskrá","source_url":URL,
          "source_bytes":source.stat().st_size,"source_sha256":digest,
          "source_columns":headers,"source_point_records":stats["rows"],
          "unique_point_ids":count,"distinct_source_address_ids":unique_address_ids,
          "statistics":stats,"coordinate_type_counts":kinds,"coordinate_review_counts":reviews,
          "source_uses_WGS84":True,"rights_reviewed_for_redistribution":False,
          "national_completeness_verified":False,"deliverability_verified":False}
  with tempfile.NamedTemporaryFile("w",encoding="utf-8",dir=receipt_path.parent,
                                   prefix=".hms-report-",delete=False) as f:
   f.write(json.dumps(report,ensure_ascii=False,indent=2)+"\n");tmp_report=f.name
  if db_path.exists() or receipt_path.exists():
   Path(tmp_report).unlink(missing_ok=True);raise ValueError("Concurrent output exists")
  Path(tmp).rename(db_path);Path(tmp_report).rename(receipt_path)
  return report
 except BaseException:
  Path(tmp).unlink(missing_ok=True);raise

def verify(db_path,receipt_path):
 report=json.loads(Path(receipt_path).read_text(encoding="utf-8"))
 if report["status"]!="PASS" or report["country"]!="IS":raise ValueError("Wrong source receipt")
 db=sqlite3.connect("file:"+str(Path(db_path).resolve())+"?mode=ro",uri=True)
 try:
  count,unique,addresses=db.execute("SELECT COUNT(*),COUNT(DISTINCT hnitnum),COUNT(DISTINCT heinum) FROM address_points").fetchone()
  if db.execute("PRAGMA integrity_check").fetchone()[0]!="ok" or count!=unique or count!=report["source_point_records"] or addresses!=report["distinct_source_address_ids"]:
   raise ValueError("HMS source vs index integrity mismatch")
  return {"status":"PASS","source_point_records":count,"distinct_source_address_ids":addresses,"delivery_verified":False}
 finally:db.close()

def diff(old,new):
 db=sqlite3.connect(":memory:")
 try:
  db.execute("ATTACH DATABASE ? AS a",(str(old),))
  db.execute("ATTACH DATABASE ? AS b",(str(new),))
  queries={"added":"SELECT COUNT(*) FROM b.address_points n LEFT JOIN a.address_points o USING(hnitnum) WHERE o.hnitnum IS NULL",
           "removed":"SELECT COUNT(*) FROM a.address_points o LEFT JOIN b.address_points n USING(hnitnum) WHERE n.hnitnum IS NULL",
           "modified":"SELECT COUNT(*) FROM a.address_points o INNER JOIN b.address_points n USING(hnitnum) WHERE o.content_sha256!=n.content_sha256"}
  return {"status":"PASS","source_point_changes":{k:db.execute(q).fetchone()[0] for k,q in queries.items()},"removed_is_not_verified_demolition":True,"delivery_verified":False}
 finally:db.close()

def main():
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest="cmd",required=True)
 a=sub.add_parser("ingest");a.add_argument("--input",required=True,type=Path);a.add_argument("--output",required=True,type=Path);a.add_argument("--receipt",required=True,type=Path);a.add_argument("--expected-sha256")
 a=sub.add_parser("verify");a.add_argument("--db",required=True,type=Path);a.add_argument("--receipt",required=True,type=Path)
 a=sub.add_parser("diff");a.add_argument("--old",required=True,type=Path);a.add_argument("--new",required=True,type=Path)
 x=p.parse_args()
 result=ingest(x.input,x.output,x.receipt,x.expected_sha256) if x.cmd=="ingest" else verify(x.db,x.receipt) if x.cmd=="verify" else diff(x.old,x.new)
 print(json.dumps(result,ensure_ascii=False,sort_keys=True))
if __name__=="__main__":main()
