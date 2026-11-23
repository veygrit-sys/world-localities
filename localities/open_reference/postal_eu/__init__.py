"""Offline postal-place associations published by La Poste, scoped by territory."""

import csv
from collections import defaultdict
from functools import cache
import hashlib
import io
import json
import lzma
from pathlib import Path
import re
import unicodedata

DIRECTORY = Path(__file__).resolve().parent
SOURCE = json.loads((DIRECTORY / "source.json").read_text(encoding="utf-8"))
COUNTRIES = tuple(SOURCE["country_counts"])
METROPOLITAN = {f"{number:02}" for number in range(1, 96) if number != 20} | {"2A", "2B"}
HEADER = ["#Code_commune_INSEE", "Nom_de_la_commune", "Code_postal", "Libellé_d_acheminement", "Ligne_5"]


def verified_bytes(raw: bytes) -> bytes:
    if len(raw) != SOURCE["raw_bytes"] or hashlib.sha256(raw).hexdigest() != SOURCE["raw_sha256"]:
        raise ValueError("La Poste source has changed; review the new version before updating the pin")
    return raw


def _key(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def load_territories(directory: Path) -> dict[str, str]:
    cog = SOURCE["territory_reference"]
    crosswalk = (directory / cog["projection_file"]).read_bytes()
    if hashlib.sha256(crosswalk).hexdigest() != cog["projection_sha256"]:
        raise ValueError("INSEE territorial crosswalk differs from its reviewed projection")
    return {row["insee_code"]: row["country"] for row in csv.DictReader(crosswalk.decode("utf-8").splitlines())}


def country_for_commune(insee: str, territories: dict[str, str]) -> str | None:
    if not re.fullmatch(r"(?:[0-9]{2}|2[AB])[0-9]{3}", insee):
        return None
    return "FR" if insee[:2] in METROPOLITAN else territories.get(insee)


@cache
def _index(directory: Path) -> dict[tuple[str, str], list[dict]]:
    territories = load_territories(directory)
    raw = verified_bytes(lzma.decompress((directory / SOURCE["stored_file"]).read_bytes()))
    rows = csv.reader(io.StringIO(raw.decode(SOURCE["encoding"]), newline=""), delimiter=";", strict=True)
    if next(rows) != HEADER:
        raise ValueError("Unexpected La Poste CSV columns")

    index = defaultdict(list)
    for insee, commune, postcode, routing_name, line5 in rows:
        country = country_for_commune(insee, territories)
        if country is None:
            if insee != "98901":
                raise ValueError(f"Unreviewed INSEE territory for {insee}")
            continue
        # Hash the full source row so aliases stay distinct and reordering does not change IDs.
        identity = json.dumps([insee, commune, postcode, routing_name, line5], ensure_ascii=False)
        record = {
            "record_id": "laposte:" + hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            "country": country,
            "source_id": SOURCE["source_id"],
            "source_url": SOURCE["source_url"],
            "source_row": rows.line_num,
            "source_updated_at": SOURCE["source_updated_at"],
            "scope": "postal_locality",
            "attribution": SOURCE["attribution"],
            "insee_code": insee,
            "locality": commune,
            "postcode": postcode,
            "routing_name": routing_name,
            "line_5": line5,
        }
        if country != "FR":
            record["territory_source_url"] = SOURCE["territory_reference"]["source_url"]
            record["territory_attribution"] = SOURCE["territory_reference"]["attribution"]
        # Numeric INSEE identifiers can equal an unrelated postcode. Tag that namespace.
        keys = {postcode, "insee:" + insee.casefold(), _key(commune), _key(routing_name), _key(line5)}
        for key in keys - {""}:
            index[country, key].append(record)
    return dict(index)


def _country(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch("[A-Za-z]{2}", value):
        raise ValueError("country must be a two-letter ASCII code")
    return value.upper()


def lookup(query: str, *, country: str = "FR") -> list[dict]:
    """Return all rows in the selected territory for an exact token."""
    return [row.copy() for row in _index(DIRECTORY).get((_country(country), _key(query)), ())]


def validate_place(country: str, postcode: str, locality: str, *, limit: int = 20,
                   directory: Path = DIRECTORY) -> dict:
    """Compare two typed fields within each La Poste record before truncating output."""
    country = _country(country)
    if not isinstance(postcode, str) or not re.fullmatch(r"[0-9]{5}", postcode):
        raise ValueError("postcode must contain exactly five ASCII digits")
    if (not isinstance(locality, str) or not locality.isprintable()
            or not any(c.isalpha() for c in locality) or _key(locality).startswith("insee:")
            or re.fullmatch(r"2[ab][0-9]{3}", _key(locality))):
        raise ValueError("locality must be a single-line place name, not a postal or INSEE code")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be an integer from 1 to 1000")

    eligible = country in COUNTRIES
    postal_rows = _index(Path(directory).resolve()).get((country, postcode), ()) if eligible else ()
    name = _key(locality)
    matches = [row for row in postal_rows
               if name in {_key(row[field]) for field in ("locality", "routing_name", "line_5")}]
    if not eligible:
        status = "no_eligible_source"
    elif not postal_rows:
        status = "postcode_not_observed"
    elif not matches:
        status = "no_match_in_source"
    else:
        status = "matched" if len(matches) == 1 else "ambiguous"
    return {
        "input": {"country": country, "code": postcode, "locality": locality},
        "country": country, "lookup_code": postcode, "status": status,
        "scope": "postcode_and_locality_in_la_poste_snapshot",
        "source_id": SOURCE["source_id"], "source_url": SOURCE["source_url"],
        "source_sha256": SOURCE["raw_sha256"],
        "attribution": [SOURCE["attribution"], SOURCE["territory_reference"]["attribution"]],
        "postcode_rows": len(postal_rows), "matching_rows": len(matches),
        "candidates": [row.copy() for row in matches[:limit]], "truncated": len(matches) > limit,
        "deliverability_verified": False,
    }
