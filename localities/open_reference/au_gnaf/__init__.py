"""Offline G-NAF physical address context for three bounded Australian localities."""
from collections import defaultdict
import csv
from functools import cache
import gzip
import hashlib
import io
import json
from pathlib import Path

from ..published_points import key


_DIR = Path(__file__).parent
_STATES = {"act": "ACT", "australian capital territory": "ACT",
           "ot": "OT", "jervis bay territory": "OT"}
_LOCALITIES = {"acton": "ACT", "barton": "ACT", "jervis bay": "OT"}


@cache
def _index():
    manifest = json.loads((_DIR / "source.json").read_bytes())

    def rows(filename):
        raw = (_DIR / filename).read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest["sha256"][filename]:
            raise ValueError("G-NAF projection checksum mismatch: " + filename)
        return csv.DictReader(io.StringIO(gzip.decompress(raw).decode("utf-8"), newline=""))

    lines, links = defaultdict(list), {}
    for row in rows("points.csv.gz"):
        road = " ".join(row[k] for k in ("street_name", "street_type", "street_suffix") if row[k])
        number = "-".join(row[k] for k in ("number_first", "number_last") if row[k])
        row.update(road=key(road), house_number=key(number))
        forms = {key(row["address"])}
        if number:
            forms.add(key(number + " " + road))
        for form in forms:
            lines[key(row["locality_name"]), form].append(row)
    for edge in rows("links.csv.gz"):
        links[edge["secondary_pid"]] = {"primary_pid": edge["primary_pid"], "join_type": edge["join_type"]}
    return manifest, lines, links


def validate_point(values, result):
    """Report source observations; a G-NAF-only match cannot prepare a mailing label."""
    where = "suburb" if "suburb" in values else "city"
    locality = key(values.get(where, ""))
    if locality not in _LOCALITIES or "po_box" in values:
        return None
    state_fields = {"state", "state_code"} & values.keys()
    if any(_STATES.get(key(values[f])) != _LOCALITIES[locality] for f in state_fields):
        return None
    line = values.get("address_line1")
    if not line and not {"road", "house_number"} <= values.keys():
        return None
    manifest, lines, links = _index()
    observed = lines.get((locality, key(line or values["house_number"] + " " + values["road"])))
    if not observed:
        return None
    checked = {where} | state_fields | ({"address_line1"} & values.keys())
    for field in {"road", "house_number", "unit", "floor"} & values.keys():
        column = {"unit": "flat_number", "floor": "level_number"}.get(field, field)
        observed = [row for row in observed if key(row[column]) == key(values[field])]
        if not observed:
            return result("not_observed", issues=["gnaf_components_not_observed_together"], candidate_count=0)
        checked.add(field)
    evidence = []
    for row in observed:
        receipt = {k: manifest[k] for k in ("source_id", "snapshot", "attribution", "terms_url", "license")}
        receipt.update(record_id=row["gnaf_pid"], url=manifest["inputs"]["principals"]["url"],
                       sha256=manifest["inputs"]["principals"]["sha256"],
                       geography={"latitude": float(row["latitude"]), "longitude": float(row["longitude"]),
                                  "geocode_type": row["geocode_type"], "reliability": int(row["reliability"])},
                       locality_pid=row["locality_pid"], street_locality_pid=row["street_locality_pid"],
                       confidence=int(row["confidence"]), use="physical_context_only")
        if row["primary_secondary"]:
            receipt["primary_secondary"] = row["primary_secondary"]
        if row["gnaf_pid"] in links:
            receipt["primary_address_relation"] = dict(links[row["gnaf_pid"]],
                url=manifest["inputs"]["secondary_links"]["url"],
                sha256=manifest["inputs"]["secondary_links"]["sha256"])
        evidence.append(receipt)
    issues = ["gnaf_independent_mailing_source_required"]
    matched_unit = False
    if len(observed) == 1 and observed[0]["flat_number"]:
        # A single published subaddress in a bounded extract is not a unitless
        # parent. The specific unit must be entered, or present in the full line.
        row = observed[0]
        full_unit_line = bool(line and key(line) == key(row["address"]) and key(row["flat_number"]) in key(line))
        matched_unit = "unit" in checked or full_unit_line
        if not matched_unit:
            issues.append("unit_required_to_distinguish_address")
    return result("partial" if len(observed) == 1 else "ambiguous", scope="physical_address_context",
                  checked=checked, evidence=evidence, candidate_count=len(observed),
                  matched_unit=matched_unit, issues=issues)
