"""Synthetic regression tests; live HMS source is tested separately in Actions."""
from __future__ import annotations
import csv,json,sqlite3,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import hms_iceland_official as m

class HMSContracts(unittest.TestCase):
 def setUp(self):
  temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup);self.dir=Path(temp.name)
  self.src=self.dir/"source.csv";self.db=self.dir/"a.sqlite";self.receipt=self.dir/"a.json"
  self.cols=["HNITNUM","HEINUM","SVFNR","BYGGD","POSTNR","HEITI_NF","HUSNR",
   "BOKST","VIDSK","SERHEITI","N_HNIT_WGS84","E_HNIT_WGS84","TEGHNIT","YFIRFARID","DAGS_INN","DAGS_LEIDR"]
  self.rows=[
   dict(zip(self.cols,["12","0000011","0001","100","101","Reykjavík","3","A","","","64.15","-21.90","2","1","2021-01-01","2026-11-07"])),
   dict(zip(self.cols,["13","0000011","0001","100","","Reykjavík","","","","","64.1","-21.8","1","","",""]))]
  self.write()
 def write(self):
  with self.src.open("w",encoding="utf-8-sig",newline="") as f:
   w=csv.DictWriter(f,fieldnames=self.cols,extrasaction="ignore");w.writeheader();w.writerows(self.rows)
 def build(self):return m.ingest(self.src,self.db,self.receipt)
 def test_point_and_address_identity_differ(self):
  report=self.build();self.assertEqual(report["source_point_records"],2)
  self.assertEqual(report["distinct_source_address_ids"],1)
  self.assertEqual(m.verify(self.db,self.receipt)["status"],"PASS")
 def test_source_postcode_and_house_missing_are_not_invented(self):
  self.assertEqual(self.build()["statistics"]["missing_house_number"],1)
  with sqlite3.connect(self.db) as c:
   self.assertEqual(c.execute("SELECT postcode FROM address_points WHERE hnitnum='13'").fetchone()[0],"")
 def test_duplicate_point_fails(self):
  self.rows[1]["HNITNUM"]="12";self.write()
  with self.assertRaisesRegex(ValueError,"Duplicate HNITNUM"):self.build()
  self.assertFalse(self.db.exists())
 def test_missing_original_id_fails(self):
  self.rows[0]["HEINUM"]="";self.write()
  with self.assertRaises(ValueError):self.build()
 def test_postcode_syntax_fails(self):
  self.rows[0]["POSTNR"]="not-a-postcode";self.write()
  with self.assertRaises(ValueError):self.build()
 def test_invalid_wgs84_fails(self):
  self.rows[0]["N_HNIT_WGS84"]="Infinity";self.write()
  with self.assertRaises(ValueError):self.build()
 def test_reject_other_coordinate_crs_numeric_text(self):
  self.rows[0]["N_HNIT_WGS84"]="650000.4";self.write()
  with self.assertRaises(ValueError):self.build()
 def test_source_pin_prevents_silent_update(self):
  with self.assertRaisesRegex(ValueError,"byte pin changed"):
   m.ingest(self.src,self.db,self.receipt,"0"*64)
 def test_no_overwrite(self):
  self.build()
  with self.assertRaisesRegex(ValueError,"Output already exists"):self.build()
 def test_omit_staff_and_free_text_fields(self):
  self.cols.extend(["ATH","NOTNR"]);self.rows[0].update({"ATH":"private text","NOTNR":"employee id"});self.write()
  self.build()
  with sqlite3.connect(self.db) as c:
   names={x[1] for x in c.execute("PRAGMA table_info(address_points)")}
   self.assertNotIn("ATH",names);self.assertNotIn("NOTNR",names)
 def test_csv_schema_guard(self):
  self.cols.remove("HNITNUM");self.write()
  with self.assertRaisesRegex(ValueError,"CSV schema differs"):self.build()
 def test_weekly_diff(self):
  self.build()
  self.rows[0]["HUSNR"]="4";self.rows[1]["HNITNUM"]="14";self.write()
  new=self.dir/"next.sqlite";receipt=self.dir/"next.json"
  m.ingest(self.src,new,receipt)
  self.assertEqual(m.diff(self.db,new)["source_point_changes"],{"added":1,"removed":1,"modified":1})
if __name__=="__main__":unittest.main()
