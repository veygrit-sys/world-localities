"""Project the pinned IDE Uruguay department exports into offline point-index shards."""
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
SHARD_ROWS = 30000
MISSING = {"", "N/A", "N/N", "S/N", "NN", "SIN NOMBRE", "CALLE SIN NOMBRE", "CALLE", "SIN DATO"}
# IDE also publishes unnamed roads with internal designations such as UYCA_SN_760.
UNSPECIFIED_ROADS = {"RUTA", "CAMINO", "CAMINO VECINAL", "CALLEJON", "PASAJE", "SERVIDUMBRE",
                     "ACCESO", "ENTRADA", "PROYECTADA", "CAMINERIA"}
REQUIRED = {"codigo_postal", "codigo_via", "nombre_via", "num_puerta", "letra_puerta",
            "localidad", "codigo_localidad", "departamento", "km"}


def project_row(row, department, line):
    if row["departamento"].strip() != department:
        raise ValueError(f"{department}:{line}: wrong department")
    postcode = row["codigo_postal"].strip()
    city = row["localidad"].strip()
    road = row["nombre_via"].strip()
    number = row["num_puerta"].strip()
    suffix = row["letra_puerta"].strip()
    if not re.fullmatch(r"[1-9][0-9]{4}", postcode):
        return "missing_full_postcode", None
    if city.upper() in MISSING or road.upper() in MISSING:
        return "missing_locality_or_road", None
    if "_SN_" in road.upper() or road.upper() in UNSPECIFIED_ROADS:
        return "unidentified_road", None
    # In the pinned export 9999 can identify dozens of different entrances
    # on one street. Keep it available for manual entry, outside point evidence.
    if number in {"9999", "99999", "999999"}:
        return "unconfirmed_number_marker", None
    if not re.fullmatch(r"[1-9][0-9]*", number):
        return "missing_or_unspecified_door_number", None
    if row["km"].strip() not in ("", "N/A"):
        return "kilometre_qualified", None
    # A separate, optional door letter must not be dropped or treated as a unit.
    # Do not turn 'S/N' or a complex secondary locator into an exact premise.
    if suffix not in ("", "N/A"):
        if not re.fullmatch(r"(?:[a-zA-Z]|[Bb][Ii][Ss]|[0-9]{1,3}|[a-zA-Z][0-9]{1,2}|[0-9]{1,2}[a-zA-Z])", suffix):
            return "unparsed_door_suffix", None
        number += " " + suffix
    # department is not an address municipality; it is preserved in the
    # snapshot-specific locator, which references the original CSV's physical line.
    return None, (postcode, city, road, number, "", f"{department}:{line}")


def write_shard(target, name, rows, digest):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(FIELDS)
    writer.writerows(sorted(rows))
    body = stream.getvalue().encode()
    digest.update(body)
    compressed = io.BytesIO()
    with gzip.GzipFile(fileobj=compressed, mode="wb", mtime=0) as f:
        f.write(body)
    data = compressed.getvalue()
    (target / name).write_bytes(data)
    return {"file": name, "rows": len(rows), "sha256": hashlib.sha256(data).hexdigest()}


def project(source, raw_dir, target):
    target.mkdir(parents=True, exist_ok=False)
    shards, totals, postcodes, localities = [], Counter(), set(), set()
    digest = hashlib.sha256()
    department_counts = {}
    for pin in source["inputs"]:
        data = (raw_dir / pin["file"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != pin["sha256"]:
            raise ValueError(f"{pin['file']}: publisher bytes differ")
        reader = csv.DictReader(io.StringIO(data.decode("cp1252"), newline=""))
        if not REQUIRED <= set(reader.fieldnames or ()):
            raise ValueError(f"{pin['file']}: missing source columns")
        department = pin["department"]
        batch, counts = [], Counter()
        for row in reader:
            counts["source_rows"] += 1
            reason, point = project_row(row, department, reader.line_num)
            if reason:
                counts[reason] += 1
                continue
            counts["retained_rows"] += 1
            postcodes.add(point[0])
            localities.add((department, row["codigo_localidad"], point[1]))
            batch.append(point)
            if len(batch) == SHARD_ROWS:
                shards.append(write_shard(target, f"points-{len(shards) + 1:02}.csv.gz", batch, digest))
                batch.clear()
        if batch:
            shards.append(write_shard(target, f"points-{len(shards) + 1:02}.csv.gz", batch, digest))
        totals.update(counts)
        department_counts[department] = counts
    result = dict(source, counts=dict(totals, postcodes=len(postcodes), department_localities=len(localities)),
                  department_counts=department_counts, shards=shards, projection_sha256=digest.hexdigest())
    (target / "source.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--raw-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New output directory")
    args = parser.parse_args()
    project(json.loads(args.manifest.read_text(encoding="utf-8")), args.raw_dir, args.output)
