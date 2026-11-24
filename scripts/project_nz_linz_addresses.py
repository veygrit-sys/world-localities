"""Capture current LINZ physical addresses for the supported territorial authorities."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

LAYER = "https://services.arcgis.com/xdsHIIxuCWByZiCB/ArcGIS/rest/services/LINZ_NZ_Addresses/FeatureServer/0"
ITEM_ID = "3632c8130f034ff8bbfb122a50533550"
AUTHORITIES = ("Chatham Islands Territory", "Gore District", "Kaikoura District", "Kawerau District", "Mackenzie District")
FIELDS = ("address_id", "full_address_number", "full_road_name", "suburb_locality", "town_city",
          "territorial_authority", "unit", "address_number", "address_number_suffix", "address_number_high")


def read_json(url, **params):
    with urlopen(url + "?" + urlencode(dict(params, f="json")), timeout=65) as response:
        value = json.load(response)
    if "error" in value:
        raise ValueError(f"LINZ ArcGIS query failed: {value['error']}")
    return value


def capture(authority):
    query = LAYER + "/query"
    where = f"territorial_authority = '{authority}' AND address_lifecycle = 'Current'"
    inventory = read_json(query, where=where, returnIdsOnly="true")
    expected = set(inventory["objectIds"])
    if not expected or len(expected) != len(inventory["objectIds"]):
        raise ValueError(f"Invalid LINZ inventory for {authority}")
    counted = read_json(query, where=where, returnCountOnly="true")["count"]
    if counted != len(expected):
        raise ValueError("LINZ inventory count differs")
    page_size = 1000
    observed = set()
    rows = []
    for offset in range(0, counted, page_size):
        response = read_json(query, where=where, orderByFields="OBJECTID ASC", resultOffset=offset,
                             resultRecordCount=page_size, returnGeometry="false",
                             outFields=",".join(("OBJECTID", "address_lifecycle", *FIELDS)))
        for feature in response["features"]:
            row = feature["attributes"]
            oid = row["OBJECTID"]
            if oid in observed or row["territorial_authority"] != authority or row["address_lifecycle"] != "Current":
                raise ValueError("Unexpected LINZ record in paginated response")
            observed.add(oid)
            rows.append(tuple("" if row[field] is None else str(row[field]) for field in FIELDS))
    if observed != expected or len({r[0] for r in rows}) != counted:
        raise ValueError(f"LINZ pagination or address-ID mismatch for {authority}")
    if any(not all(row[:3]) for row in rows):
        raise ValueError("Incomplete address identity")
    rows.sort(key=lambda row: int(row[0]))
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(FIELDS)
    writer.writerows(rows)
    data = buffer.getvalue().encode("utf-8")
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as stream:
        stream.write(data)
    return {"authority": authority, "rows": counted, "where": where,
            "object_ids_sha256": hashlib.sha256(",".join(map(str, sorted(expected))).encode()).hexdigest(),
            "csv_sha256": hashlib.sha256(data).hexdigest(),
            "file": authority.replace(" ", "-").lower() + ".csv.gz"}, output.getvalue()


def main(target):
    before = read_json(LAYER)["editingInfo"]["dataLastEditDate"]
    with ThreadPoolExecutor(max_workers=3) as pool:
        captures = list(pool.map(capture, AUTHORITIES))
    if read_json(LAYER)["editingInfo"]["dataLastEditDate"] != before:
        raise ValueError("LINZ changed during collection; repeat the capture")
    target.mkdir(parents=True, exist_ok=False)
    manifest = {
        "source_id": "nz-linz-addresses", "publisher": "Toitū Te Whenua Land Information New Zealand",
        "attribution": "© Crown copyright. Sourced from the LINZ Data Service and licensed for reuse under CC BY 4.0.",
        "license": "CC BY 4.0", "terms_url": "https://creativecommons.org/licenses/by/4.0/",
        "dataset_url": "https://data.linz.govt.nz/layer/123113-nz-addresses/",
        "item_url": f"https://www.arcgis.com/home/item.html?id={ITEM_ID}", "layer_url": LAYER,
        "retrieved": datetime.now(timezone.utc).date().isoformat(),
        "data_last_edited": datetime.fromtimestamp(before / 1000, timezone.utc).isoformat(),
        "changes": "Selected current addresses of five territorial authorities. Projected source fields, sorted by LINZ address ID and compressed as CSV; no postcodes or coordinates.",
        "shards": [],
    }
    for shard, binary in captures:
        (target / shard["file"]).write_bytes(binary)
        manifest["shards"].append(shard)
    (target / "source.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New directory for data shards and the source manifest")
    main(parser.parse_args().output)
