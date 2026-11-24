"""Reproduce an offline address-point projection from the raw files named in its manifest."""

import argparse
from collections import Counter
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re


FIELDS = ("postcode", "locality", "road", "number", "municipality", "record_id")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def project(country, raw_dir, source, target):
    records = {}
    counts = Counter()
    for pin in source["inputs"]:
        data = (raw_dir / pin["file"]).read_bytes()
        if sha(data) != pin["sha256"]:
            raise ValueError(f"publisher bytes differ: {pin['file']}")
        if country == "LU":
            rows = csv.DictReader(io.StringIO(data.decode("utf-8-sig")), delimiter=";")
        else:
            rows = (f["properties"] for f in json.loads(data)["features"])
        for r in rows:
            counts["source_rows"] += 1
            if country == "LU":
                pc, city, road, number, municipality, rid = (
                    r[k].strip() for k in ("code_postal", "localite", "rue", "numero", "commune", "id_geoportail")
                )
                postcode = "L-" + pc if re.fullmatch(r"[0-9]{4}", pc) else ""
            else:
                if r["bronhouder_identificatie"] != pin["authority"]:
                    raise ValueError("unexpected publisher in regional extract")
                if (r["status"], r["openbare_ruimte_status"], r["woonplaats_status"]) != (
                    "Naamgeving uitgegeven", "Naamgeving uitgegeven", "Woonplaats aangewezen"
                ):
                    counts["inactive"] += 1
                    continue
                pc = r["postcode"] or ""
                postcode = pc[:4] + " " + pc[4:] if re.fullmatch(r"[1-9][0-9]{3}[A-Z]{2}", pc) else ""
                city, road, rid = r["woonplaats_naam"], r["openbare_ruimte_naam"], r["identificatie"]
                municipality = ""
                number = str(r["huisnummer"] or "") + (r["huisletter"] or "")
                if r["toevoeging"]:
                    number += "-" + r["toevoeging"]
            if not all((postcode, city, road, number, rid)):
                counts["missing_required_field"] += 1
                continue
            item = (postcode, city, road, number, municipality, rid)
            if rid in records:
                if records[rid] != item:
                    raise ValueError(f"inconsistent address components for {rid}")
                counts["duplicate_id_same_address"] += 1
                continue
            records[rid] = item
    items = sorted(records.values())
    if not items:
        raise ValueError("empty projection")
    target.mkdir(parents=True, exist_ok=False)
    shards = []
    combined = hashlib.sha256()
    for offset in range(0, len(items), 20000):
        batch = items[offset:offset + 20000]
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(FIELDS)
        writer.writerows(batch)
        raw = buffer.getvalue().encode()
        combined.update(raw)
        out = io.BytesIO()
        with gzip.GzipFile(fileobj=out, mode="wb", mtime=0) as zipped:
            zipped.write(raw)
        filename = f"points-{len(shards) + 1:02}.csv.gz"
        (target / filename).write_bytes(out.getvalue())
        shards.append({"file": filename, "rows": len(batch), "sha256": sha(out.getvalue())})
    result = dict(source, counts=dict(counts, retained_ids=len(items),
                                      postcodes=len({r[0] for r in items})),
                  projection_sha256=combined.hexdigest(), shards=shards)
    (target / "source.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="A new directory for the selected country")
    args = parser.parse_args()
    source = json.loads(args.manifest.read_text(encoding="utf-8"))
    project(source["country"], args.raw_dir, source, args.output)
