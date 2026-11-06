"""Source-pinned government GeoJSON and Jordan post office CSV intake."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import western_asia_original_source_intake as x


class OriginalIntake(unittest.TestCase):
    def test_unacquired_source_catalogue_keeps_ambiguous_state(self):
        c=x.load_catalogue()
        self.assertFalse(c[x.AZ_SOURCE]["downloaded"])
        self.assertFalse(c[x.JO_SOURCE]["downloaded"])
        self.assertIsNone(c[x.AZ_SOURCE]["sha256"])
        self.assertIsNone(c[x.JO_SOURCE]["sha256"])

    def test_geojson_point_and_polygon_count_and_no_gn_assignment(self):
        geo={"type":"FeatureCollection","features":[
            {"type":"Feature","id":"one","properties":{"STATE_AZ":"Bakı"},
             "geometry":{"type":"Point","coordinates":[49.88,40.37]}},
            {"type":"Feature","id":"two","properties":{"STATE_AZ":"Abşeron"},
             "geometry":{"type":"Polygon","coordinates":[
                [[49.0,40.0],[50.0,40.0],[49.5,41.0],[49.0,40.0]]]}}
        ]}
        binary=json.dumps(geo,ensure_ascii=False).encode()
        report=x.audit_geojson(binary)
        self.assertEqual(report["feature_count"],2)
        self.assertEqual(report["geometry_types"]["Point"],1)
        self.assertEqual(report["geometry_types"]["Polygon"],1)
        self.assertEqual(report["coordinate_pairs_checked"],5)
        self.assertEqual(report["government_to_geonames_links_verified"],0)
        self.assertFalse(report["country_membership_inferred_from_coordinates"])

    def test_geojson_invalid_coordinates_rejected(self):
        geo={"type":"FeatureCollection","features":[
           {"type":"Feature","properties":{},"geometry":
             {"type":"Point","coordinates":[200,50]}}]}
        with self.assertRaisesRegex(ValueError,"WGS84"):
            x.audit_geojson(json.dumps(geo).encode())

    def test_geojson_duplicate_source_ids_counted_not_inferred(self):
        geo={"type":"FeatureCollection","features":[
           {"type":"Feature","id":"one","properties":{},"geometry":None},
           {"type":"Feature","id":"one","properties":{},"geometry":None}
        ]}
        r=x.audit_geojson(json.dumps(geo).encode())
        self.assertEqual(r["source_feature_ids_duplicated"],1)
        self.assertEqual(r["features_without_geometry"],2)

    def test_jordan_original_arabic_headers_mapped_by_explicit_grain(self):
        raw=("مكتب,الرمز,محافظة\n"
             "مكتب اول,11118,عمان\n"
             "مكتب ثان,11118,عمان\n"
             "مكتب ثالث,11937,عمان\n").encode()
        report=x.audit_jordan_csv(raw,postcode_field="الرمز",office_field="مكتب")
        self.assertEqual(report["source_rows"],3)
        self.assertEqual(report["counts"]["valid_five_digit_postcode_syntax"],3)
        self.assertEqual(report["postcodes_for_multiple_offices"],1)
        self.assertFalse(report["postcode_to_geonames_id_verified"])

    def test_no_postcode_field_does_not_fabricate_associations(self):
        raw=b"area,city\nOne,Amman\n"
        report=x.audit_jordan_csv(raw)
        self.assertEqual(report["distinct_mapped_postcodes"],0)
        self.assertEqual(report["warning"],
                         "postal_column_unmapped_no_postcode_verification_attempted")

    def test_postcodes_malformed_and_missing_detected(self):
        raw=b"office,postal\nfirst,123\nsecond,\nthird,01234\n"
        r=x.audit_jordan_csv(raw,postcode_field="postal",office_field="office")
        self.assertEqual(r["counts"]["missing_postcode"],1)
        self.assertEqual(r["counts"]["invalid_postcode_syntax"],1)
        self.assertEqual(r["counts"]["valid_five_digit_postcode_syntax"],1)

    def test_audit_requires_checksum_and_known_source(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"source.csv"
            raw=b"office,postal\nfirst,01234\n"
            p.write_bytes(raw)
            got=x.audit_file(x.JO_SOURCE,p,hashlib.sha256(raw).hexdigest(),
                             postcode_field="postal",office_field="office")
            self.assertEqual(got["original_file_sha256"],hashlib.sha256(raw).hexdigest())
            self.assertFalse(got["original_source_committed_to_repo"])
            with self.assertRaises(ValueError):
                x.audit_file(x.JO_SOURCE,p,"0"*64,postcode_field="postal")
            with self.assertRaises(ValueError):
                x.audit_file("INVALID",p,hashlib.sha256(raw).hexdigest())

    def test_azerbaijan_geojson_cannot_be_marked_postal_dataset(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"data.geojson"
            content=b'{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":null}]}'
            path.write_bytes(content)
            with self.assertRaises(ValueError):
                x.audit_file(x.AZ_SOURCE,path,hashlib.sha256(content).hexdigest(),
                             postcode_field="zipcode")


if __name__=="__main__": unittest.main()
