"""Reproduce an offline address-point projection from the raw files named in its manifest."""

import argparse
from collections import Counter
import csv
import io
import json
from pathlib import Path
import re


if __package__:
    from .address_point_projection import sha, write_projection
else:
    from address_point_projection import sha, write_projection


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
    write_projection(records.values(), source, counts, target)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="A new directory for the selected country")
    args = parser.parse_args()
    source = json.loads(args.manifest.read_text(encoding="utf-8"))
    project(source["country"], args.raw_dir, source, args.output)
