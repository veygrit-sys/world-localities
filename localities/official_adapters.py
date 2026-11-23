"""Request parameters and interpretation of official address services."""

import re
from functools import cache

CENSUS_STATES = set("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT "
                    "NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY".split())


def text_value(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if type(value) in (str, int):
        return str(value).strip()
    return ""


def candidate(label, scope, **fields):
    if not isinstance(label, str) or not label.strip():
        raise ValueError("missing address label")
    record = {"label": label.strip(), "scope": scope}
    record.update({key: text_value(value) for key, value in fields.items() if text_value(value)})
    return record


def objects(rows):
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("invalid provider collection")
    return rows


def sql_literal(value):
    return "'" + value.replace("'", "''") + "'"


def arc_query(where, fields, limit):
    return {"where": where, "outFields": fields, "returnGeometry": "false",
            "resultRecordCount": limit, "f": "json"}


def arc_rows(payload):
    for feature in objects(payload["features"]):
        yield feature["attributes"]


def french_country(insee):
    from .open_reference.postal_eu import country_for_commune
    return country_for_commune(insee, _french_territories())


@cache
def _french_territories():
    from .open_reference.postal_eu import DIRECTORY, load_territories
    return load_territories(DIRECTORY)


def fr_query(query, limit):
    return {"q": query, "index": "address", "limit": limit}


def fr_rows(payload, country, query):
    scopes = {"housenumber": "address_point", "street": "street", "municipality": "locality",
              "locality": "locality"}
    for feature in objects(payload["features"]):
        p = feature["properties"]
        if french_country(p["citycode"]) != country or p["type"] not in scopes:
            continue
        yield candidate(p["label"], scopes[p["type"]], record_id=p.get("id"),
                        postcode=p.get("postcode"), locality=p.get("city"))


def postal_query(query, limit):
    if not re.fullmatch(r"[0-9]{5}", query):
        raise ValueError("la-poste takes a five-digit postcode")
    return {"qs": "code_postal:" + query, "size": 100,
            "select": "code_postal,code_commune_insee,nom_de_la_commune,libelle_d_acheminement,ligne_5"}


def postal_rows(payload, country, query):
    for row in objects(payload["results"]):
        postcode, insee, place = row["code_postal"], row["code_commune_insee"], row["nom_de_la_commune"]
        if postcode == query and french_country(insee) == country:
            yield candidate(postcode + " " + place, "postal_locality", postcode=postcode,
                            locality=place, insee_code=insee, routing_name=row.get("libelle_d_acheminement"),
                            supplementary_locality=row.get("ligne_5"))


def nl_query(query, limit):
    return {"q": query, "fq": "type:adres", "rows": limit,
            "fl": "id,type,weergavenaam,postcode,woonplaatsnaam"}


def nl_rows(payload, country, query):
    for row in objects(payload["response"]["docs"]):
        if row["type"] == "adres":
            yield candidate(row["weergavenaam"], "address_point", record_id=row["id"],
                            postcode=row.get("postcode"), locality=row.get("woonplaatsnaam"))


def no_query(query, limit):
    return {"sok": query, "treffPerSide": limit}


def no_rows(payload, country, query):
    for row in objects(payload["adresser"]):
        if str(row["kommunenummer"]).startswith(("21", "22")):
            continue  # Svalbard and Jan Mayen have a separate destination code.
        place = row.get("poststed") or row["kommunenavn"]
        label = " ".join(filter(None, (row["adressetekst"], row.get("postnummer"), place)))
        yield candidate(label, "address_point", record_id=row.get("adresseid"),
                        postcode=row.get("postnummer"), locality=place)


def hk_query(query, limit):
    return {"q": query, "n": limit}


def hk_label(address, lang):
    district = address.get(lang + "District", {}).get("DcDistrict")
    road = address.get(lang + "Street") or address.get(lang + "Village") or {}
    end, start = road.get("BuildingNoTo"), road.get("BuildingNoFrom")
    number = "-".join(filter(None, (start, end if end != start else None)))
    street = road.get("StreetName") or road.get("VillageName")
    estate = address.get(lang + "Estate", {}).get("EstateName")
    block = address.get(lang + "Block", {})
    block_parts = (block.get("BlockDescriptor"), block.get("BlockNo"))
    building = address.get("BuildingName")
    if not any((building, estate, street, *block_parts)):
        return ""
    if lang == "Chi":
        return "".join(filter(None, (address.get("Region"), district, street, number,
                                     "號" if number else "", estate, *reversed(block_parts), building)))
    return ", ".join(filter(None, (building, " ".join(filter(None, block_parts)), estate,
                                   " ".join(filter(None, (number, street))), district, address.get("Region"))))


def hk_rows(payload, country, query):
    # ALS omits SuggestedAddress completely on a successful empty lookup.
    if "SuggestedAddress" not in payload and isinstance(payload.get("RequestAddress"), dict):
        return
    for row in objects(payload["SuggestedAddress"]):
        p = row["Address"]["PremisesAddress"]
        en = hk_label(p.get("EngPremisesAddress", {}), "Eng")
        zh = hk_label(p.get("ChiPremisesAddress", {}), "Chi")
        yield candidate(en or zh, "premises", record_id=p.get("GeoAddress"), label_en=en, label_zh_hant=zh)


def lu_query(query, limit):
    return {"queryString": query}


def lu_rows(payload, country, query):
    if payload["success"] is not True:
        raise ValueError("provider reported failure")
    levels = {8: "address_point", 7: "point_of_interest", 6: "street", 5: "locality", 1: "country"}
    for row in objects(payload["results"]):
        if row["accuracy"] in levels and row.get("ratio", 1) > 0:
            details = row.get("AddressDetails", {})
            yield candidate(row["address"], levels[row["accuracy"]], postcode=details.get("zip"),
                            locality=details.get("locality"), record_id=details.get("id_caclr_building"))


def us_query(query, limit):
    return {"address": query, "benchmark": "Public_AR_Current", "format": "json"}


def us_rows(payload, country, query):
    for row in objects(payload["result"]["addressMatches"]):
        parts = row["addressComponents"]
        if parts["state"] in CENSUS_STATES:
            yield candidate(row["matchedAddress"], "street_range", postcode=parts.get("zip"),
                            locality=parts.get("city"), range_from=parts.get("fromAddress"),
                            range_to=parts.get("toAddress"))


def dc_query(query, limit):
    where = "STATUS = 'ACTIVE' AND ADDRESS_TYPE = 'ADDRESS' AND ADDRESS = " + sql_literal(query.upper())
    return arc_query(where, "MAR_ID,ADDRESS,CITY,STATE,ZIPCODE", limit)


def dc_rows(payload, country, query):
    for row in arc_rows(payload):
        if row["STATE"] == "DC":
            yield candidate(row["ADDRESS"], "address_point", record_id=row["MAR_ID"],
                            postcode=row.get("ZIPCODE"), locality=row["CITY"])


def bologna_query(query, limit):
    return {"where": "indirizzo_completo = " + sql_literal(query.upper()),
            "select": "indirizzo_completo,civkey,cap", "limit": limit}


def bologna_rows(payload, country, query):
    for row in objects(payload["results"]):
        yield candidate(row["indirizzo_completo"], "address_point", record_id=row["civkey"],
                        locality="Bologna", postcode=row.get("cap"))


def vancouver_query(query, limit):
    number, _, street = query.upper().partition(" ")
    if not re.fullmatch(r"[0-9]+[A-Z]?", number) or not street:
        raise ValueError("ca-vancouver takes a civic number followed by the registered street name")
    return {"where": f"civic_number = {sql_literal(number)} AND std_street = {sql_literal(street)}",
            "select": "civic_number,std_street,site_id", "limit": limit}


def vancouver_rows(payload, country, query):
    for row in objects(payload["results"]):
        yield candidate(row["civic_number"] + " " + row["std_street"], "property_address",
                        record_id=row.get("site_id"), locality="Vancouver")


def ar_query(query, limit):
    return {"direccion": query, "max": limit}


def ar_rows(payload, country, query):
    for row in objects(payload["direcciones"]):
        yield candidate(row["nomenclatura"], "normalized_street_address",
                        locality=row["localidad"].get("nombre"), street_id=row["calle"].get("id"),
                        province=row["provincia"]["id"], province_name=row["provincia"]["nombre"])


def qld_query(query, limit):
    return arc_query("UPPER(address) = " + sql_literal(query.upper()),
                     "address,address_pid,state,locality,address_status", limit)


def qld_rows(payload, country, query):
    for row in arc_rows(payload):
        if row["state"] == "QLD":
            yield candidate(row["address"], "property_address", record_id=row["address_pid"],
                            locality=row["locality"], register_status=row.get("address_status"))


def uy_query(query, limit):
    return {"q": query, "limit": limit}


def uy_rows(payload, country, query):
    for row in objects(payload):
        scope = "approximate"
        if row["type"] == "CALLEyPORTAL" and row.get("portalNumber") and row.get("state") == 1 and not row.get("stateMsg"):
            scope = "address_point"
        yield candidate(row["address"], scope, record_id=row.get("id"), postcode=row.get("postalCode"),
                        locality=row.get("localidad"), provider_message=row.get("stateMsg"))


def swiss_query(query, limit):
    if not re.fullmatch(r"[0-9]{1,12}", query):
        raise ValueError("ch-swisstopo takes the numeric building entrance identifier (EGAID)")
    return {"lang": "en", "returnGeometry": "false"}


def swiss_rows(payload, country, query):
    feature = payload["feature"]
    row = feature["attributes"]
    municipality = row["com_fosnr"]
    is_domestic = (0 < municipality < 7000 if country == "CH" else 7001 <= municipality <= 7011)
    if is_domestic and str(row["adr_egaid"]) == query and row["adr_official"] is True:
        label = f"{row['stn_label']} {row['adr_number']} {row['zip_label']}"
        yield candidate(label, "building_entrance", record_id=row["adr_egaid"], locality=row["com_name"],
                        register_status=row.get("adr_status"))


ADAPTERS = {
    "fr-ban": (fr_query, fr_rows), "la-poste": (postal_query, postal_rows),
    "nl-pdok": (nl_query, nl_rows), "no-kartverket": (no_query, no_rows),
    "hk-als": (hk_query, hk_rows), "lu-act": (lu_query, lu_rows),
    "us-census": (us_query, us_rows), "dc-mar": (dc_query, dc_rows),
    "it-bologna": (bologna_query, bologna_rows), "ca-vancouver": (vancouver_query, vancouver_rows),
    "ar-georef": (ar_query, ar_rows), "au-queensland": (qld_query, qld_rows),
    "uy-ide": (uy_query, uy_rows), "ch-swisstopo": (swiss_query, swiss_rows),
}
