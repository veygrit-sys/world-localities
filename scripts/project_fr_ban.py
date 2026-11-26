"""Rebuild the offline French BAN projection from pinned departmental CSV archives."""

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import io
import json
from pathlib import Path
import re

if __package__:
    from .address_point_projection import sha, write_projection
else:
    from address_point_projection import sha, write_projection


def project(manifest, raw_dir, output):
    records = {}
    counters = Counter()
    departments = {}
    commune_links = defaultdict(set)
    for pin in manifest["inputs"]:
        data = (raw_dir / pin["file"]).read_bytes()
        if sha(data) != pin["sha256"]:
            raise ValueError(f"publisher bytes differ: {pin['file']}")
        department = pin["department"]
        seen = Counter()
        communes, postcodes = set(), set()
        reader = csv.DictReader(io.StringIO(gzip.decompress(data).decode("utf-8-sig")), delimiter=";")
        for row in reader:
            seen["published_rows"] += 1
            if not (re.fullmatch(r"[0-9]{5}", row["code_insee"]) and row["code_insee"].startswith(department)):
                raise ValueError("unexpected commune in departmental file")
            n = row["numero"]
            if n in {"0", "99999"}:
                seen["non_premise_number"] += 1
                continue
            if not re.fullmatch(r"[0-9]{1,5}", n):
                raise ValueError("unrecognized house number")
            code, commune, road = row["code_postal"], row["nom_commune"], row["nom_voie"]
            if not re.fullmatch(r"[0-9]{5}", code) or not commune or not road:
                raise ValueError("incomplete published location")
            number = n + (" " + row["rep"] if row["rep"] else "")
            uuid = row.get("id_ban_adresse")
            rid = uuid or row["id"]
            if not rid or rid in records:
                raise ValueError("missing or duplicate BAN address identifier")
            records[rid] = (code, commune, road, number, commune, rid)
            seen["ban_uuid" if uuid else "bal_interop_key"] += 1
            commune_links[(code, commune)].add(row["code_insee"])
            communes.add(row["code_insee"])
            postcodes.add(code)
        counters.update(seen)
        departments[department] = dict(seen, communes=len(communes), postcodes=len(postcodes))
    # A shared postal code and commune label may only resolve one INSEE code.
    links = [[code, commune, next(iter(ids))] for (code, commune), ids in sorted(commune_links.items())
             if len(ids) == 1]
    write_projection(records.values(), dict(manifest, departments=departments, commune_links=links),
                     counters, output, 6000)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    project(json.loads(args.manifest.read_text(encoding="utf-8")), args.raw_dir, args.output)
