#!/usr/bin/env python3
"""Western Asia final four: provenance-first locality + postcode validation.

LB, IQ, SY, YE. Source region and humanitarian P-codes are NOT postal codes.
GeoNames IDs and newly discovered administrative claims remain immutable and
must be crosswalk-reviewed. Standard library only; offline; no delivery claims.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata
import zipfile
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "registries" / "official" / "western-asia" / "remaining"
EVIDENCE = BASE / "country-evidence.json"
SYRIA = BASE / "syria-reference"
ASIA = ROOT / "registries" / "asia"
SCOPE = ("LB", "IQ", "SY", "YE")
BIDI_CONTROLS = re.compile(r"[\u202a-\u202e\u2066-\u2069]")
SCHEMES = {"LB": "no_confirmed_general_postcode",
           "IQ": "five_digit_post_office",
           "SY": "no_confirmed_national_postcode",
           "YE": "no_confirmed_national_postcode"}
FIELDS = {"id", "name", "asciiname", "alternatenames", "admin_level",
          "state_id", "country_code", "kind", "feature_code", "address_candidate"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(value: str | None, key: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be text")
    result = unicodedata.normalize("NFC", value.strip())
    if BIDI_CONTROLS.search(result) or any(
        ord(c) < 32 or ord(c) == 127 for c in result
    ):
        raise ValueError("Unsafe control in " + key)
    return result or None


def name_key(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    value = "".join(c for c in value if unicodedata.category(c) != "Mn")
    return " ".join(re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).split())


def source_inventory(path: Path = EVIDENCE) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or set(data.get("scope", ())) != set(SCOPE):
        raise ValueError("Western Asian final-four source scope changed")
    if data.get("data_quality", {}).get("postcodes_to_geonames_links_verified") != 0:
        raise ValueError("Unreviewed postal links cannot be called verified")
    for cc in SCOPE:
        spec = data["countries"][cc]
        if spec["postcode_mode"] != SCHEMES[cc]:
            raise ValueError("Postcode scheme mismatch: " + cc)
        expected = {"LB":8, "IQ":19, "SY":14, "YE":22}[cc]
        if len(spec["admin1"]) != expected:
            raise ValueError("Official/contextual governorate count changed: " + cc)
        ids = set()
        for row in spec["admin1"]:
            if row["id"] in ids or not row["display_en"]:
                raise ValueError("Duplicate/blank official-name source record")
            ids.add(row["id"])
            if row["official_id_link_to_geonames_verified"] is not False:
                raise ValueError("Name-based matching is not certified")
            if row["postal_assignment_verified"] is not False:
                raise ValueError("Unapproved official postal assignment")
            if cc == "YE" and (row.get("unlocode_subdivision_code") is None
                               or row.get("not_a_postal_code") is not True):
                raise ValueError("Yemen administrative code must not be postal")
        ids = [s["source_id"] for s in data["sources"][cc]]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate source references")
        if any(not s["url"].startswith("https://") for s in data["sources"][cc]):
            raise ValueError("Source URL must use HTTPS")
    postal_ids = set()
    for row in data["postal_evidence"]:
        if row["country"] != "IQ" or not re.fullmatch(r"[0-9]{5}", row["code"]):
            raise ValueError("Other countries have no official postal rows in this excerpt")
        if row["record_id"] in postal_ids:
            raise ValueError("Duplicate postal source fact")
        postal_ids.add(row["record_id"])
        if row["source_id"] not in {s["source_id"] for s in data["sources"]["IQ"]}:
            raise ValueError("Postal source reference missing")
        if row["geonames_identity_verified"] or row["delivery_verified"]:
            raise ValueError("Cannot claim official postcode-to-GeoNames assignment")
    if len(postal_ids) != 9:
        raise ValueError("Iraqi Post sample count changed without review")
    return data


def postcode_format(
    country: str, postcode: str | None = None, *, delivery_mode: str = "home",
    po_box: str | None = None, locality: str | None = None,
    district: str | None = None, governorate: str | None = None,
    landmark: str | None = None, humanitarian_pcode: str | None = None,
) -> dict:
    """Syntax / country scheme only; lack of a source row never proves invalidity."""
    cc = country.upper()
    if cc not in SCOPE:
        raise ValueError("Country must be LB, IQ, SY or YE")
    if delivery_mode not in ("home", "po_box"):
        raise ValueError("delivery_mode must be home or po_box")
    fields = {k:_text(v,k) for k,v in {
        "postcode":postcode, "po_box":po_box, "locality":locality,
        "district":district, "governorate":governorate,
        "landmark":landmark, "humanitarian_pcode":humanitarian_pcode
    }.items()}
    warnings = ["postcode_assignment_not_checked", "address_existence_not_checked",
                "carrier_deliverability_not_checked"]
    errors = []
    missing = []
    normalized = {"country_code":cc}
    for k,v in fields.items():
        if v and k != "postcode":
            normalized[k] = v
    if cc == "IQ":
        if fields["postcode"]:
            if re.fullmatch(r"[0-9]{5}", fields["postcode"]):
                normalized["postcode"] = fields["postcode"]
            else:
                errors.append("iraq_five_ascii_digit_postcode_required")
        else:
            warnings.append("post_office_code_not_provided")
    else:
        if fields["postcode"]:
            errors.append("national_postcode_not_confirmed_for_country")
        warnings.append("no_verified_national_postcode_scheme")
        if fields["postcode"] in {"0000", "00000", "12345"}:
            warnings.append("synthetic_placeholder_is_not_a_postcode")
    if delivery_mode == "po_box" and not fields["po_box"]:
        missing.append("po_box_missing")
    if cc == "LB" and delivery_mode == "home" and not fields["district"]:
        warnings.append("lebanon_kaza_not_provided")
    if cc in ("SY", "YE") and not fields["locality"]:
        warnings.append("locality_not_provided_for_descriptive_address")
    if cc == "YE" and not fields["landmark"]:
        warnings.append("landmark_not_provided")
    if fields["humanitarian_pcode"]:
        warnings.append("humanitarian_pcode_not_a_postcode")
    return {
        "country":cc,
        "scheme":SCHEMES[cc],
        "status":"invalid_format" if errors else "incomplete" if missing else
                 "format_only" if cc == "IQ" and fields["postcode"] else "format_unverified",
        "normalized":normalized,
        "errors":sorted(set(errors)),
        "missing":sorted(set(missing)),
        "warnings":sorted(set(warnings)),
        "checks":{
            "country_format_policy_checked":True, "postal_assignment_verified":False,
            "administrative_membership_verified":False,
            "building_verified":False,"carrier_deliverability_verified":False
        }
    }


def verify_geo(country: str, root: Path = ASIA) -> tuple[list[dict],dict]:
    if country not in SCOPE:
        raise ValueError("Country outside western Asia final-four scope")
    inv = json.loads((root/"archives.json").read_text(encoding="utf-8"))
    recs = [r for r in inv["archives"] if r["country"] == country]
    if len(recs) != 1:
        raise ValueError("Missing/duplicate GeoNames archive")
    rec = recs[0]
    path = f"country-archives/{country}.zip"
    if rec["path"] != path or not rec["parts"]:
        raise ValueError("Unexpected archive path")
    chunks = []
    for i, part in enumerate(rec["parts"], 1):
        expected = path if len(rec["parts"])==1 else path + (".part%03d" % i)
        if part["path"] != expected:
            raise ValueError("Part ordering violation")
        content = (root/expected).read_bytes()
        if len(content) != part["bytes"] or sha(content) != part["sha256"]:
            raise ValueError("Source ZIP part corrupted")
        chunks.append(content)
    packed = b"".join(chunks)
    if len(packed) != rec["bytes"] or sha(packed) != rec["sha256"]:
        raise ValueError("Source ZIP checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(packed)) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("Duplicate ZIP members")
        if set(archive.namelist()) != set(rec["members"]):
            raise ValueError("Unexpected ZIP member")
        name = country + "/entities.csv.gz"
        compressed = archive.read(name)
        if sha(compressed) != rec["members"][name]["sha256"]:
            raise ValueError("GeoNames entity SHA mismatch")
    rows = list(csv.DictReader(io.StringIO(gzip.decompress(compressed).decode("utf-8"))))
    if not rows or not FIELDS.issubset(rows[0]) or len(rows) != rec["rows"]:
        raise ValueError("Bad GeoNames record count/schema")
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("GeoNames IDs duplicated")
    for r in rows:
        if r["country_code"] != country or not re.fullmatch(r"gn:[1-9][0-9]*", r["id"]):
            raise ValueError("Record country / GN ID invalid")
    return rows, {"source_snapshot_sha256":rec["sha256"], "gazetteer_rows":len(rows)}


def match_administrative(country: str, rows: list[dict], evidence: dict) -> list[dict]:
    original = evidence["countries"][country]["admin1"]
    geoadm = [r for r in rows if r["feature_code"] == "ADM1" and r["admin_level"] == "1"]
    lookup = defaultdict(set)
    for row in geoadm:
        for v in (row["name"],row["asciiname"],*row["alternatenames"].split(",")):
            if v:
                lookup[name_key(v)].add(row["id"])
    by_id = {r["id"]:r for r in geoadm}
    out = []
    for item in original:
        direct = lookup.get(name_key(item["display_en"]), set())
        candidates = set(direct)
        if not candidates:
            for alt in item.get("search_aliases", ()):
                candidates.update(lookup.get(name_key(alt), ()))
        source_id = item.get("source_geonames_id_unreviewed")
        explicit_gn = ("gn:"+str(source_id)) if source_id and not str(source_id).startswith("gn:") else source_id
        explicit_present = bool(explicit_gn in by_id)
        # An explicit GN ID from a separate source is higher-priority evidence
        # of that source's claimed link, but is NOT a government certification.
        if explicit_present:
            candidates.add(explicit_gn)
        ids = sorted(candidates)
        state = "unmatched" if not ids else "unique_candidate" if len(ids)==1 else "ambiguous_candidates"
        out.append({
            "source_name_id":item["id"],"official_or_source_name":item["display_en"],
            "status":state,"geonames_candidates":ids,
            "source_provided_geonames_id":explicit_gn,
            "source_provided_geonames_id_present":explicit_present,
            "government_to_geonames_identity_verified":False,
            "postal_association_verified":False,
            "effective_from":item.get("effective_from"),
            "note":"A candidate is not an authenticated official entity link.",
        })
    return out


def verify_syria_source(root: Path = SYRIA) -> dict:
    manifest = json.loads((root/"manifest.json").read_text(encoding="utf-8"))
    if manifest["source_commit"] != "b4364ee892351671450f873c2e48901ae37a84be":
        raise ValueError("Upstream pinned source commit changed")
    if manifest["counts"] != {"governorates":14,"districts":62,"subdistricts":272}:
        raise ValueError("Syria administrative level snapshot incomplete")
    adm=json.loads((root/"admin-levels.json").read_text(encoding="utf-8"))["records"]
    counts=Counter(r["kind"] for r in adm)
    if counts != {"governorate":14,"district":62,"subdistrict":272}:
        raise ValueError("Administrative record counts changed")
    ids={r["id"] for r in adm}
    if len(ids)!=len(adm):
        raise ValueError("Duplicate Syrian administrative IDs")
    parents={r["id"]:r for r in adm}
    govs={r["id"] for r in adm if r["kind"]=="governorate"}
    for r in adm:
        if r["governorate_id"] not in govs:
            raise ValueError("Dangling Syrian governorate")
        if r["district_id"] and r["district_id"] not in parents:
            raise ValueError("Dangling Syrian district")
    village_ids = set()
    by_gov = Counter()
    for path in sorted((root/"localities").glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        if document["schema_version"]!=1 or document["governorate_id"] not in govs:
            raise ValueError("Unexpected Syrian locality batch")
        required=["id","district_id","subdistrict_id","en","ar","kind",
                  "ocha_pcode_not_postal","upstream_geonames_id_unreviewed"]
        if document["fields"]!=required:
            raise ValueError("Unexpected Syrian locality field layout")
        for line in document["rows"]:
            if len(line)!=8:
                raise ValueError("Syrian locality column count changed")
            id,district,subdistrict,en,ar,kind,pcode,geonames=line
            if id in village_ids or not id or not en or not ar:
                raise ValueError("Missing bilingual names / duplicate locality ID")
            village_ids.add(id)
            if district not in parents or subdistrict not in parents:
                raise ValueError("Missing source district/subdistrict")
            if parents[district]["governorate_id"]!=document["governorate_id"]:
                raise ValueError("Cross-governorate Syrian locality")
            if parents[subdistrict]["district_id"]!=district:
                raise ValueError("Cross-district Syrian locality")
            by_gov[document["governorate_id"]]+=1
    if len(village_ids)!=7605 or len(by_gov)!=14:
        raise ValueError("Syria locality data not complete for this pinned OpenSyria release")
    return {
        "upstream_source":"OpenSyria data-geography pinned Git commit",
        "source_gov":counts["governorate"],"source_districts":counts["district"],
        "source_subdistricts":counts["subdistrict"],"source_localities":len(village_ids),
        "native_english_pairs_count":len(village_ids),
        "source_geonames_ids_government_verified":False,
        "humanitarian_pcodes_are_postal_codes":False,
        "countrywide_postal_delivery_verified":False,
        "locality_rows_by_governorate":dict(sorted(by_gov.items())),
    }


def report_country(country: str) -> dict:
    catalogue=source_inventory()
    rows, snap=verify_geo(country)
    matched=match_administrative(country,rows,catalogue)
    stats=Counter(x["status"] for x in matched)
    geo_admin=[r for r in rows if r["feature_code"]=="ADM1" and r["admin_level"]=="1"]
    postal=[r for r in catalogue["postal_evidence"] if r["country"]==country]
    result={
        "country":country, **snap, "geonames_adm1_rows":len(geo_admin),
        "gazetteer_localities_without_adm1":sum(r["kind"]=="locality" and not r["state_id"] for r in rows),
        "source_admin1_labels":len(matched),
        "admin_unique_unreviewed":stats["unique_candidate"],
        "admin_ambiguous_unreviewed":stats["ambiguous_candidates"],
        "admin_unmatched":stats["unmatched"],
        "post_office_source_examples":len(postal),
        "official_nationwide_postcode_table_imported":False,
        "authenticated_postcode_to_geonames_links":0,
        "government_admin_to_geonames_links_verified":0,
        "carrier_deliverability_verified":False,
        "country_specific_validation":True,
        "postcode_policy":SCHEMES[country],
        "admin_candidate_records":matched
    }
    if country=="SY":
        result["syria_community_source"]=verify_syria_source()
    if country=="IQ":
        result["halabja_admin_2025"]=next(
            x for x in matched if x["official_or_source_name"]=="Halabja")
    return result


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("report","validate","syria-verify"))
    parser.add_argument("--country",choices=(*SCOPE,"all"),default="all")
    parser.add_argument("--postcode")
    parser.add_argument("--delivery-mode",choices=("home","po_box"),default="home")
    parser.add_argument("--po-box")
    parser.add_argument("--locality")
    parser.add_argument("--district")
    parser.add_argument("--governorate")
    parser.add_argument("--landmark")
    parser.add_argument("--humanitarian-pcode")
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    if args.command=="syria-verify":
        out=verify_syria_source()
    elif args.command=="report":
        countries=SCOPE if args.country=="all" else (args.country,)
        reports=[report_country(cc) for cc in countries]
        out={"schema_version":1,"countries":reports,
             "country_rules_present":len(reports),
             "nationwide_postal_existence_verified":False,
             "carrier_deliverability_verified":False,
             "automatically_approved_official_geonames_links":0}
    else:
        if args.country=="all":
            parser.error("validate requires a single --country")
        out=postcode_format(args.country,args.postcode,delivery_mode=args.delivery_mode,
                            po_box=args.po_box,locality=args.locality,
                            district=args.district,governorate=args.governorate,
                            landmark=args.landmark,humanitarian_pcode=args.humanitarian_pcode)
    result=json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(result,encoding="utf-8")
    else:print(result,end="")


if __name__=="__main__":
    main()
