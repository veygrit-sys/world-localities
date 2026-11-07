#!/usr/bin/env python3
"""Compare HMS Iceland address coordinate POINTS with independent agency's IS 50V roads.

IS 50V 1:50,000 transport network: a *separate publisher evidence layer*, not a
building/address ground truth and not a certified independent address dataset.
Road distance is a diagnostic: a valid rural property can be >1 km from mapped
roads, and zero distance does not prove that an address or building exists.
No person-level, point-level or household information is exported to reports.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,math,sqlite3,time,urllib.parse,urllib.request,tempfile
from pathlib import Path
from datetime import datetime,timezone

SERVICE="https://portal.land.is/server/rest/services/Hosted/LMI_is50v_Samgongur/FeatureServer/72/query"
METADATA="https://geoportal.gis.is/geonetwork/srv/api/records/41D3314D-55AF-4FE3-9A9F-B9CB18AC5CAA?language=eng"
LIMIT=1000
BINS=(50,100,250,500,1000,2000)
def source_json(params, opener=None, retries=1):
    if opener is None: opener=urllib.request.urlopen
    url=SERVICE+"?"+urllib.parse.urlencode(params)
    error=None
    for attempt in range(retries+1):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Veygrit-world-localities-IS50V-quality-audit/1.0","Accept":"application/json"})
            with opener(req,timeout=20) as resp:
                if resp.status!=200:raise ValueError("External source HTTP "+str(resp.status))
                if resp.url.split("/")[2]!="portal.land.is":raise ValueError("Source redirect origin changed")
                raw=resp.read(35_000_001)
            if len(raw)>35_000_000:raise ValueError("Over-sized source response")
            val=json.loads(raw.decode("utf-8"))
            if not isinstance(val,dict) or "error" in val:raise ValueError("External source ArcGIS error "+str(val.get("error",{}))[:250])
            return val,raw
        except (OSError,ValueError,UnicodeDecodeError,json.JSONDecodeError) as exc:
            error=exc
            if attempt<retries:time.sleep(attempt+1)
    raise ValueError("Separate public road source could not be retrieved: "+str(error))
def query_road_lines():
    try:
        from shapely.geometry import LineString
    except ImportError as e:
        raise RuntimeError("shapely 2.x required for independent official road comparison") from e
    count_obj,_=source_json({"where":"1=1","returnCountOnly":"true","f":"json"})
    total=count_obj.get("count")
    if type(total)!=int or total<1 or total>3_000_000:
        raise ValueError("Provider did not report a safe national count")
    roads=[]; seen=set();source_hash=hashlib.sha256(); page_n=0;seg_n=0
    for start in range(0,total,LIMIT):
        obj,raw=source_json({"where":"1=1","outFields":"objectid","returnGeometry":"true",
          "outSR":"3057","resultRecordCount":str(LIMIT),"resultOffset":str(start),
          "orderByFields":"objectid","f":"json"})
        feats=obj.get("features")
        if not isinstance(feats,list) or len(feats)!=min(LIMIT,total-start):
            raise ValueError("Incomplete official road page at offset "+str(start))
        source_hash.update(start.to_bytes(8,"big"));source_hash.update(raw)
        page_n+=1
        for v in feats:
            attrs=v.get("attributes") or {}
            oid=attrs.get("objectid")
            if oid is None or oid in seen:raise ValueError("Repeated official road feature id")
            seen.add(oid)
            paths=(v.get("geometry") or {}).get("paths",[])
            if not isinstance(paths,list):raise ValueError("Road source geometry missing")
            for path in paths:
                if not isinstance(path,list) or len(path)<2:continue
                pts=[]
                for xy in path:
                    if not isinstance(xy,list) or len(xy)<2:raise ValueError("Malformed road coordinates")
                    x,y=xy[:2]
                    if not (math.isfinite(x) and math.isfinite(y) and 0<=x<=1_000_000 and 0<=y<=1_000_000):
                        raise ValueError("Unexpected LMI projected coordinate")
                    pts.append((x,y))
                ln=LineString(pts)
                if not ln.is_empty and ln.length>0:roads.append(ln);seg_n+=1
    if len(seen)!=total or not roads:raise ValueError("Incomplete IS 50V road coverage")
    return roads,{"source":"IS 50V Transportation", "source_authority":"Náttúrufræðistofnun",
      "source_metadata":METADATA, "official_feature_service":SERVICE, "dataset_role":"separate published topographic roads, 1:50,000",
      "declared_road_features":total,"read_road_features":len(seen),"line_geometries":seg_n,
      "source_page_count":page_n,"page_payload_sha256_in_order":source_hash.hexdigest(),
      "source_crs":"EPSG:3057","license":"CC BY 4.0 per dataset metadata","official_address_ground_truth":False}


WFS_SERVICE="https://gis.lmi.is/geoserver/IS_50V/ows"
def wfs_road_lines():
    """Stream every published nationwide IS50V transportation way via the official
    WFS 2.0.0 GeoJSON interface, explicitly reprojection EPSG:3057.
    The 1:50k map is NOT an address register or perfect road coverage.
    """
    try:
        from shapely.geometry import LineString
    except ImportError as e:raise RuntimeError("shapely required for IS50V WFS") from e
    pages=0; seen=set(); roads=[];raw_hash=hashlib.sha256();reported=None
    limit=1500
    for start in range(0,2_000_000,limit):
        params={"service":"WFS","version":"2.0.0","request":"GetFeature",
          "typeNames":"IS_50V:samgongur_linur","count":str(limit),
          "startIndex":str(start),"outputFormat":"application/json","srsName":"EPSG:3057"}
        url=WFS_SERVICE+"?"+urllib.parse.urlencode(params)
        data=None; error=None; raw=None
        for attempt in range(2):
            try:
                req=urllib.request.Request(url,headers={
                  "User-Agent":"Veygrit-world-localities-geospatial-evidence/1.0","Accept":"application/json"})
                with urllib.request.urlopen(req,timeout=45) as response:
                    if response.status!=200 or urllib.parse.urlsplit(response.url).hostname!="gis.lmi.is":
                        raise ValueError("Unexpected official geodata response origin/status")
                    raw=response.read(40_000_001)
                if len(raw)>40_000_000:raise ValueError("Official WFS page too large")
                data=json.loads(raw.decode("utf-8"))
                if not isinstance(data,dict) or data.get("type")!="FeatureCollection":
                    raise ValueError("Official WFS did not return GeoJSON FeatureCollection")
                break
            except (OSError,ValueError,UnicodeDecodeError,json.JSONDecodeError) as exc:
                error=exc
                if attempt==0:time.sleep(1)
        if data is None:raise ValueError("Official Iceland WFS source unavailable "+str(error))
        features=data.get("features")
        if not isinstance(features,list) or len(features)>limit:
            raise ValueError("Unexpected official WFS features count")
        if reported is None:
            n=data.get("numberMatched")
            if isinstance(n,int) and 0<n<=2_000_000:reported=n
            elif isinstance(n,str) and n.isdigit():reported=int(n)
        raw_hash.update(start.to_bytes(8,"big"));raw_hash.update(raw)
        pages+=1
        for feature in features:
            ident=feature.get("id") or (feature.get("properties") or {}).get("uuid")
            if not ident or ident in seen:raise ValueError("Duplicate/missing IS 50V geometry id")
            seen.add(ident)
            geom=feature.get("geometry") or {}
            gtype=geom.get("type")
            if gtype=="LineString": paths=[geom.get("coordinates")]
            elif gtype=="MultiLineString": paths=geom.get("coordinates")
            else:raise ValueError("Unexpected IS 50V GeoJSON geometry: "+str(gtype))
            if not isinstance(paths,list):raise ValueError("Malformed WFS geometry")
            for path in paths:
                if not path or len(path)<2:continue
                pts=[]
                for xy in path:
                    if not isinstance(xy,(list,tuple)) or len(xy)<2:
                        raise ValueError("Malformed WFS projected coordinate")
                    x,y=xy[:2]
                    if not (isinstance(x,(float,int)) and isinstance(y,(float,int)) and
                            math.isfinite(x) and math.isfinite(y) and
                            0<=x<=1_000_000 and 0<=y<=1_000_000):
                        raise ValueError("IS 50V response CRS not EPSG:3057 or malformed")
                    pts.append((x,y))
                line=LineString(pts)
                if not line.is_empty and line.length>0:roads.append(line)
        if not features or (reported is not None and len(seen)==reported):break
        if len(features)<limit:break
    if reported is not None and len(seen)!=reported:raise ValueError("Incomplete nationwide WFS transport dataset")
    if not seen or not roads:raise ValueError("No official WFS road geometries fetched")
    return roads,{"source":"IS 50V Transportation - road polylines",
      "source_provider":"Náttúrufræðistofnun / IS 50V",
      "source_url":WFS_SERVICE,"source_metadata":METADATA,
      "published_feature_count":reported,
      "downloaded_feature_count":len(seen),"road_line_geometries":len(roads),
      "wfs_pages":pages,"ordered_page_payload_sha256":raw_hash.hexdigest(),
      "source_crs":"EPSG:3057 (explicit WFS request)",
      "license":"CC BY 4.0 per NLSI public metadata",
      "official_road_data":True,
      "separate_publisher_independence_not_certified":"IS 50V maintained by separate national institute but upstream input overlaps possible."}

def osm_road_lines(pbf, expected_sha256):
    """OpenStreetMap road geometry reference. Some Icelandic OSM addresses were
    imported from HMS; OSM is not proven independent address ground truth.
    Roads are an external mapping source, not a government register.
    """
    try:
        import osmium
        from shapely.geometry import LineString
        from pyproj import Transformer
    except ImportError as exc:
        raise RuntimeError("osmium, shapely, pyproj required for OSM road evidence") from exc
    pbf=Path(pbf)
    if not pbf.is_file() or not 1_000_000<pbf.stat().st_size<500_000_000:
        raise ValueError("Missing/invalid bounded Iceland OSM PBF")
    digest=hashlib.sha256()
    with pbf.open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""): digest.update(block)
    sha=digest.hexdigest()
    if not expected_sha256 or sha!=expected_sha256:raise ValueError("Original OSM extract hash differs")
    xform=Transformer.from_crs("EPSG:4326","EPSG:3057",always_xy=True)
    roadtypes={"motorway","trunk","primary","secondary","tertiary","unclassified",
               "residential","service","living_street","track","motorway_link",
               "trunk_link","primary_link","secondary_link","tertiary_link"}
    roads=[];count=collections.Counter()
    class Handler(osmium.SimpleHandler):
        def way(self,way):
            highway=way.tags.get("highway")
            if highway not in roadtypes: return
            count["tagged_ways"]+=1
            if not (len(way.nodes)>=2 and all(node.location.valid() for node in way.nodes)):
                count["missing_way_coords"]+=1
                return
            pts=[]
            for node in way.nodes:
                x,y=xform.transform(node.location.lon,node.location.lat)
                if not math.isfinite(x) or not math.isfinite(y):raise ValueError("Malformed OSM projected coordinate")
                pts.append((x,y))
            road=LineString(pts)
            if road.length>0:roads.append(road);count["valid_road_lines"]+=1
    with tempfile.TemporaryDirectory(prefix="osm-is-nodes-") as temp:
        Handler().apply_file(str(pbf),locations=True,idx="sparse_file_array,"+str(Path(temp)/"osm-nodes"))
    if not roads:raise ValueError("No road geometries in separate OSM snapshot")
    return roads,{"source":"OpenStreetMap Iceland",
       "source_provider":"Geofabrik Iceland PBF","source_url":"https://download.geofabrik.de/europe/iceland-latest.osm.pbf",
       "source_sha256":sha,"bytes":pbf.stat().st_size, "feature_types":"OSM drivable highway-tagged ways",
       "source_road_ways":count["tagged_ways"],"usable_road_lines":count["valid_road_lines"],
       "missing_road_way_geometries":count["missing_way_coords"],
       "source_crs":"EPSG:4326 converted to EPSG:3057 with pyproj",
       "license":"ODbL-1.0 — © OpenStreetMap contributors, Geofabrik extract",
       "official_road_data":False,
       "separate_source_but_not_proven_independent":"Icelandic OSM address imports from Staðfangaskrá documented; road geometry is only a plausibility comparator."}

def bucket(distance):
    if not math.isfinite(distance) or distance<0:raise ValueError("Invalid distance")
    for lim in BINS:
        if distance<=lim:return "up_to_"+str(lim)+"m"
    return "over_2000m"
def audit(db_path,roads,source):
    try:
        from shapely.geometry import Point
        from shapely.strtree import STRtree
        from pyproj import Transformer
    except ImportError as e:raise RuntimeError("pyproj and shapely required") from e
    tree=STRtree(roads)
    transformer=Transformer.from_crs("EPSG:4326","EPSG:3057",always_xy=True)
    conn=sqlite3.connect("file:"+str(Path(db_path).resolve())+"?mode=ro",uri=True)
    groups=collections.defaultdict(collections.Counter)
    stats=collections.Counter()
    try:
        if conn.execute("PRAGMA integrity_check").fetchone()[0]!="ok":raise ValueError("HMS SQLite integrity failed")
        cols={r[1] for r in conn.execute("PRAGMA table_info(address_points)")}
        if not {"hnitnum","lat_wgs84","lon_wgs84","coordinate_review","coordinate_kind"}<=cols:raise ValueError("Not an accepted HMS SQLite index")
        for lat,lon,review,kind in conn.execute("SELECT lat_wgs84,lon_wgs84,coordinate_review,coordinate_kind FROM address_points"):
            stats["hms_point_count"]+=1
            state=review if review in ("0","1","2","9") else "unknown_"+str(review)
            stats["review_"+state]+=1
            if lat is None or lon is None:
                stats["missing_coordinates"]+=1;continue
            if not (-90<=lat<=90 and -180<=lon<=180):raise ValueError("Invalid WGS84 point")
            xx,yy=transformer.transform(lon,lat)
            if not(math.isfinite(xx) and math.isfinite(yy)):raise ValueError("Invalid projected coordinate")
            point=Point(xx,yy); ix=tree.nearest(point)
            if ix is None:raise ValueError("No road geometry")
            d=point.distance(roads[int(ix)])
            groups["review_"+state][bucket(d)]+=1
            groups["kind_"+str(kind)][bucket(d)]+=1
            stats["within_250m"]+=d<=250
            stats["over_2000m"]+=d>2000
        if stats["hms_point_count"]==0 or stats["hms_point_count"]!=sum(v for k,v in stats.items() if k.startswith("review_")):
            raise ValueError("HMS records not fully scanned")
    finally:conn.close()
    return {"status":"PASS","country":"IS","comparison":"HMS address point versus separately published road polylines (not address ground truth)",
      "hms_address_point_count":stats["hms_point_count"],"hms_coordinate_review_counts":{k[7:]:v for k,v in stats.items() if k.startswith("review_")},
      "missing_hms_coordinates":stats["missing_coordinates"],"within_250m_of_topographic_road":stats["within_250m"],
      "farther_than_2000m_from_topographic_road":stats["over_2000m"],"grouped_distance_counts":{k:dict(v) for k,v in sorted(groups.items())},
      "spatial_reference_source":source,"source_independence":"source-separated road geometry; provenance/independence must be judged from the selected reference",
      "warning":"1:50,000 road generalization and sparse rural roads; distance bins are NOT geocoding errors or confirmation of an address",
      "address_location_verified":False,"carrier_deliverability_verified":False,
      "completed_utc":datetime.now(timezone.utc).isoformat()}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--hms-db",required=True,type=Path);p.add_argument("--report",required=True,type=Path);p.add_argument("--osm-pbf",type=Path);p.add_argument("--expected-pbf-sha256");p.add_argument("--arcgis",action="store_true")
    args=p.parse_args()
    if args.report.exists():raise ValueError("Never overwrite a previously accepted cross-check report")
    roads,source=osm_road_lines(args.osm_pbf,args.expected_pbf_sha256) if args.osm_pbf else (query_road_lines() if args.arcgis else wfs_road_lines())
    report=audit(args.hms_db,roads,source)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    road_count=source.get("downloaded_feature_count",source.get("read_road_features",source.get("source_road_ways")))
    print(json.dumps({"status":report["status"],"hms_points":report["hms_address_point_count"],
      "road_features":road_count,"within_250m":report["within_250m_of_topographic_road"],
      "over_2000m":report["farther_than_2000m_from_topographic_road"]},ensure_ascii=False))
if __name__=="__main__":main()
