"""Source-bound civic address lookup for the Canadian ODA v1 NWT observations."""
from collections import defaultdict, namedtuple
import csv
from functools import cache
import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

from ..published_points import key


_DIR = Path(__file__).parent
_PLACES = {"yellowknife", "detah"}
_TERRITORY = {"nt", "ca-nt", "northwest territories", "territoires du nord-ouest"}
_Point = namedtuple("_Point", "rid place number road unit full_line")


@cache
def _index():
    source = json.loads((_DIR / "source.json").read_bytes())
    raw = (_DIR / "ODA_NT_v1.zip").read_bytes()
    if hashlib.sha256(raw).hexdigest() != source["sha256"]:
        raise ValueError("Statistics Canada NWT archive checksum mismatch")
    # Index full publisher lines (which can include units) and civic lines separately.
    # Two distinct ODA IDs at the same address must remain two candidates.
    lines = defaultdict(list)
    with ZipFile(io.BytesIO(raw)) as archive, archive.open("ODA_NT_v1.csv") as stream:
        for row in csv.DictReader(io.TextIOWrapper(stream, encoding="utf-8-sig", newline="")):
            point = _Point(row["id"], key(row["csdname"]), key(row["street_no"]),
                           key(row["street"]), key(row["unit"]), key(row["full_addr"]))
            for line in {point.full_line, point.number + " " + point.road}:
                lines[point.place, line].append(point)
    return source, lines


def validate_point(values, result):
    """Keep census subdivision, published civic address and optional unit on the same row."""
    entered_places = {key(values[field]) for field in {"city", "municipality"} & values.keys()}
    # The territorial names register links current Dettah to ODA's older Detah.
    places = {"detah" if place == "dettah" else place for place in entered_places}
    if len(places) != 1 or not places <= _PLACES or "po_box" in values:
        return None
    state_fields = {"state", "state_code"} & values.keys()
    if any(key(values[field]) not in _TERRITORY for field in state_fields):
        return None
    place, = places
    structured = "house_number" in values and "road" in values
    line = values.get("address_line1")
    if not line and not structured:
        return None
    source, lines = _index()
    rows = lines.get((place, key(line or values["house_number"] + " " + values["road"])), ())
    if not rows:
        return None
    checked = ({"city", "municipality", "address_line1"} & values.keys()) | state_fields
    typed = {"house_number": "number", "road": "road", "unit": "unit"}
    for field, column in typed.items():
        if field not in values:
            continue
        matching = [r for r in rows if getattr(r, column) == key(values[field])]
        if not matching:
            if field == "unit":
                # The extract may omit a real unit. Never certify one from an unmatched value.
                return result("not_observed", issues=["oda_unit_not_observed"], candidate_count=0)
            return result("conflict", issues=["inconsistent_street_representations"], candidate_count=0)
        rows = matching
        checked.add(field)
    inline_units = set()
    if "unit" not in checked:
        # The source has no parent-to-unit relationship table. Only a real
        # published, unitless row qualifies for a civic-only match; a lone
        # observed suite is not evidence of a corresponding parent record.
        unitless = [r for r in rows if not r.unit]
        if line:
            for r in rows:
                base = r.number + " " + r.road
                if r.unit and key(line) == r.full_line == r.unit + " " + base:
                    inline_units.add(r.rid)
        if inline_units:
            rows = [r for r in rows if r.rid in inline_units]
        elif unitless:
            rows = unitless
    evidence = [dict(source, record_id=r.rid) for r in rows]
    if "dettah" in entered_places:
        evidence.append({"source_id": "nwt-official-community-names", "record_id": "Dettah",
                         "url": "https://www.ece.gov.nt.ca/en/services/geographical-names/official-nwt-community-names",
                         "snapshot": "2026-11-26", "attribution": "Government of the Northwest Territories"})
    if "unit" not in checked and not inline_units and all(r.unit for r in rows):
        return result("ambiguous" if len(rows) > 1 else "partial", scope="published_district_street",
                      checked=checked - {"address_line1", "house_number"}, evidence=evidence,
                      issues=["unit_required_to_distinguish_address"], candidate_count=len(rows))
    return result("matched" if len(rows) == 1 else "ambiguous", scope="published_address_point",
                  checked=checked, evidence=evidence, candidate_count=len(rows), matched_unit=bool(inline_units))
