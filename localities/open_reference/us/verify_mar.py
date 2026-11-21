"""Verify checked-in citywide projections and the separately retrieved corridor records."""

import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from . import _CITYWIDE, _DIRECTORY, _index, get_record
from .build import _file_hash, build, download


def verify_corridor() -> int:
    """Verify all 101 features from the independent single-street query."""
    source = json.loads((_DIRECTORY / "source.json").read_bytes())
    snapshots = {}
    for entry in source["snapshots"]:
        path = _DIRECTORY / entry["filename"]
        if path.stat().st_size != entry["bytes"] or _file_hash(path) != entry["sha256"]:
            raise ValueError(f"DC MAR corridor original differs from source.json: {path.name}")
        snapshots[entry["filename"]] = json.loads(path.read_bytes())
    response = snapshots["address-points.json"]
    features = response["features"]
    if (response.get("exceededTransferLimit") or len(features) != source["row_count"]
            or len(features) != snapshots["count.json"]["count"]):
        raise ValueError("Incomplete DC MAR corridor response")
    for feature in features:
        row = feature["attributes"]
        record = get_record(f"US-DC-MAR:{int(row['MAR_ID'])}")
        if ((record["address"], record["city"], record["state"], record["postal_code"],
             record["latitude"], record["longitude"]) !=
            (row["ADDRESS"], row["CITY"], row["STATE"], str(int(row["ZIPCODE"])),
             row["LATITUDE"], row["LONGITUDE"])):
            raise ValueError(f"Corridor record differs from citywide bulk CSV: {record['record_id']}")
    return len(features)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--online", action="store_true", help="verify live full CSV, ID and count responses")
    args = parser.parse_args()
    records, _ = _index()
    corridor = verify_corridor()
    if args.online:
        with TemporaryDirectory() as temp:
            inputs = Path(temp)
            download(inputs)
            original = json.loads((_CITYWIDE / "citywide.json").read_bytes())
            candidate = build(inputs, inputs / "candidate", retrieved_utc=original["retrieved_utc"])
            if (candidate["sources"] != original["sources"]
                    or candidate["independent_object_id_set_sha256"] != original["independent_object_id_set_sha256"]
                    or [s["csv_sha256"] for s in candidate["shards"]] != [s["csv_sha256"] for s in original["shards"]]):
                raise SystemExit("Live DC MAR source changed. Review the candidate as a new snapshot.")
    print(json.dumps({"matched_rows": len(records), "corridor_rows_cross_checked": corridor,
                      "live_bytes_compared": args.online}))


if __name__ == "__main__":
    main()
