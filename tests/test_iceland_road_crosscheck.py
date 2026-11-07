"""Iceland separate-source spatial quality: synthetic geographic regression tests."""
import math,sqlite3,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
import iceland_road_crosscheck as m

class Crosscheck(unittest.TestCase):
 def setUp(self):
  try:
   from shapely.geometry import LineString
   from pyproj import Transformer
  except ImportError:self.skipTest("shapely/pyproj optional for independent integration check")
  t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.db=Path(t.name)/"hms.sqlite"
  with sqlite3.connect(self.db) as c:
   c.executescript("CREATE TABLE address_points(hnitnum TEXT PRIMARY KEY,lat_wgs84 REAL,lon_wgs84 REAL,coordinate_review TEXT,coordinate_kind TEXT);")
  self.tx=Transformer.from_crs("EPSG:4326","EPSG:3057",always_xy=True)
  x,y=self.tx.transform(-21.9,64.15)
  self.line=LineString([(x-200,y),(x+200,y)])
 def add(self,records):
  with sqlite3.connect(self.db) as c:
   c.executemany("INSERT INTO address_points VALUES(?,?,?,?,?)",records)
 def test_distance_buckets_have_stable_boundaries(self):
  self.assertEqual(m.bucket(0),"up_to_50m")
  self.assertEqual(m.bucket(50),"up_to_50m")
  self.assertEqual(m.bucket(50.01),"up_to_100m")
  self.assertEqual(m.bucket(250),"up_to_250m")
  self.assertEqual(m.bucket(2000.1),"over_2000m")
 def test_reject_negative_and_nonfinite_distance(self):
  for d in (-1,math.nan,math.inf):
   with self.assertRaises(ValueError):m.bucket(d)
 def test_accept_exact_point_and_unknown_quality_without_promotion(self):
  self.add([("1",64.15,-21.9,"0","2"),("2",64.15,-21.9,"1","2"),("3",None,None,"2","")])
  r=m.audit(self.db,[self.line],{"test":"synthetic"})
  self.assertEqual(r["status"],"PASS")
  self.assertEqual(r["hms_address_point_count"],3)
  self.assertEqual(r["within_250m_of_topographic_road"],2)
  self.assertEqual(r["hms_coordinate_review_counts"],{"0":1,"1":1,"2":1})
  self.assertFalse(r["address_location_verified"])
  self.assertFalse(r["carrier_deliverability_verified"])
  self.assertEqual(r["missing_hms_coordinates"],1)
 def test_outside_wgs84_rejected(self):
  self.add([("1",92,-21.9,"1","2")])
  with self.assertRaisesRegex(ValueError,"WGS84"):m.audit(self.db,[self.line],{})
 def test_empty_source_is_never_success(self):
  with self.assertRaises(ValueError):m.audit(self.db,[self.line],{})
 def test_missing_required_sqlite_columns_rejected(self):
  with sqlite3.connect(self.db) as db:db.execute("DROP TABLE address_points")
  with self.assertRaises((sqlite3.OperationalError,ValueError)):m.audit(self.db,[self.line],{})
 def test_no_address_id_or_house_number_in_aggregate_report(self):
  self.add([("test-id",64.15,-21.9,"1","2")])
  result=m.audit(self.db,[self.line],{})
  self.assertNotIn("test-id",str(result))
  self.assertNotIn("heinum",str(result))
if __name__=="__main__":unittest.main()
