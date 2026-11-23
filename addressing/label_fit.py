"""Lossless, offline fitting of a destination address to label field limits.

A fit describes printable routing fields, not a booked/validated shipment.
`None` selects a preview, never a carrier contract. Named profile constraints are
not caller-overridable. Supply a separate, server-owned mapping for other contracts.
Unrecognized, ambiguous, unencodable and oversized components fail closed.
"""
from __future__ import annotations

from collections.abc import Mapping
from functools import lru_cache
import re
import unicodedata

from .components import canonicalize_components
from .profiles import ProfileRegistry


_UPS_SOURCE = ("https://github.com/UPS-API/api-documentation/blob/"
               "b4aa85d841ae4ef130b06516ebee17a8578eea1c/Shipping.yaml")
_YAMATO_SOURCE = "https://bmypage.kuronekoyamato.co.jp/bmypage/pdf/new_exchange1.pdf"
_FIELDS = {"country_code", "city", "state", "postcode", "recipient", "organization", "attention"}
_PREVIEW = {
    "id": "preview", "unit": "codepoints", "line_limit": 40, "max_lines": 3,
    "field_limits": {f: 80 for f in _FIELDS} | {"country_code": 2},
}
# ShipTo_Address / Shipment_ShipTo: 3 x 35, City accepts 30 but PRINTS 15.
# US only; local policy is ASCII, 50 states + DC. The addressee/contact are
# NOT a complete UPS shipment object. No contract, service or printer is implied.
_UPS = {
    "id": "ups-us-shipto", "countries": ["US"], "unit": "codepoints",
    "line_limit": 35, "max_lines": 3, "ascii_only": True,
    "field_limits": {"country_code": 2, "city": 15, "state": 2, "postcode": 9,
                     "organization": 35, "recipient": 35, "attention": 35},
    "required_fields": ["city", "state", "postcode"],
}
# B2 Cloud 送り状発行データレイアウト, pp. 1, rows 11–16; address only.
# PDF SHA-256: b9189fab61ca61f38122af6989795a2da75c235d5534ebb3f6a9145ebe5356cc
# https://b-faq.kuronekoyamato.co.jp/app/answers/detail/a_id/406
# Prefecture + municipality + town/street share column 12, building is 13.
_YAMATO = {
    "id": "yamato-jp-b2", "countries": ["JP"], "unit": "shift_jis_bytes",
    "line_limit": 64, "max_lines": 2,
    "field_limits": {"country_code": 2, "city": 24, "state": 8, "postcode": 8,
                     "recipient": 32, "organization": 50},
    "required_fields": ["city", "state", "postcode"],
}
_STATES = frozenset("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT "
                    "NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
# https://pe.usps.com/text/pub28/28apc_002.htm
# Restricted subset of USPS Publication 28, Appendix C1. Only a final whole
# suffix of a structured, multiword street is eligible; never names/free text.
_SUFFIX = dict(zip("avenue boulevard circle court drive highway lane parkway place road street terrace trail"
                   .split(), "AVE BLVD CIR CT DR HWY LN PKWY PL RD ST TER TRL".split()))
_STREET = {"address_line1", "address_line2", "road", "house_number", "house", "subpremise",
           "unit", "floor", "entrance", "neighbourhood", "city_district", "block", "lot", "po_box"}
_UNSAFE = {"Cc", "Cs", "Zl", "Zp"}
_BIDI = {chr(i) for i in (0x061C, 0x200E, 0x200F, *range(0x202A, 0x202F), *range(0x2066, 0x206A))}


class _Review(ValueError):
    pass


@lru_cache(maxsize=1)
def _registry():
    return ProfileRegistry(extension_paths=())


def _bounded_int(n, maximum):
    return type(n) is int and 1 <= n <= maximum


def _list_of_strings(items, allowed=None):
    return (isinstance(items, (tuple, list)) and len(items) <= 256
            and all(isinstance(x, str) and (allowed is None or x in allowed) for x in items))


def _profile(profile):
    if profile is None or profile == "preview":
        return _PREVIEW
    if profile == "ups-us-shipto":
        return _UPS
    if profile == "yamato-jp-b2":
        return _YAMATO
    if not isinstance(profile, Mapping):
        raise _Review("unknown_profile")
    allowed = {"id", "unit", "line_limit", "max_lines", "field_limits",
               "required_fields", "countries", "ascii_only"}
    if set(profile) - allowed:
        raise _Review("invalid_profile")
    p = dict(profile)
    limits = p.get("field_limits")
    if (not isinstance(p.get("id"), str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", p["id"])
        or p["id"] in {"preview", "ups-us-shipto", "yamato-jp-b2"}
        or p.get("unit") not in ("codepoints", "utf8_bytes", "shift_jis_bytes")
        or not _bounded_int(p.get("line_limit"), 1024)
        or not _bounded_int(p.get("max_lines"), 16)
        or not isinstance(limits, Mapping) or set(limits) - _FIELDS
        or "country_code" not in limits
        or not all(_bounded_int(n, 1024) for n in limits.values())
        or not _list_of_strings(p.get("required_fields", []), limits)
        or type(p.get("ascii_only", False)) is not bool
        or ("countries" in p and (not p["countries"] or not _list_of_strings(p["countries"])
            or not all(re.fullmatch(r"[A-Z]{2}", c) for c in p["countries"])))):
        raise _Review("invalid_profile")
    return p


def _read(values):
    if not isinstance(values, Mapping) or len(values) > 64:
        raise _Review("invalid_components")
    for k, v in values.items():
        if not isinstance(k, str) or len(k) > 64:
            raise _Review("invalid_components")
        if v is None:
            continue
        if not isinstance(v, str) or len(v) > 4096:
            raise _Review("invalid_components")
        if any(unicodedata.category(c) in _UNSAFE or c in _BIDI for c in v):
            raise _Review("unsafe_characters")
    try:
        addr = canonicalize_components(values)
    except (ValueError, TypeError):
        raise _Review("invalid_or_conflicting_components") from None
    if addr.extras or set(addr.values) - (_FIELDS | _STREET | {
        "state_code", "postal_city", "language", "script", "country",
    }):
        raise _Review("unmapped_component")
    return addr.values


def _field_values(v, cc, p, edits):
    fields = {k: v[k] for k in sorted(_FIELDS) if k in v}
    fields["country_code"] = cc
    if v.get("country_code", cc) != cc:
        raise _Review("country_mismatch")
    if "country" in v:
        # Never throw away a possibly conflicting supplied country name.
        known = {"US": {"united states", "united states of america", "usa"},
                 "JP": {"japan", "日本", "日本国"}, "CN": {"china", "中国", "中华人民共和国"}}
        if v["country"].casefold() not in known.get(cc, set()) | {cc.lower()}:
            raise _Review("country_name_needs_review")
    if "postal_city" in v:
        if "city" in v and v["postal_city"] != v["city"]:
            raise _Review("conflicting_city_fields")
        fields["city"] = v["postal_city"]
    if "state_code" in v:
        if "state" in v and v["state"] != v["state_code"]:
            code = _registry().subdivision_code((cc,), v["state"])
            if code is None or code.casefold() != v["state_code"].casefold():
                raise _Review("conflicting_state_fields")
        fields["state"] = v["state_code"]
    if p is _UPS:
        if "po_box" in v:
            raise _Review("po_box_needs_review")
        if "state" in fields:
            code = _registry().subdivision_code(("US",), fields["state"])
            if code not in _STATES:
                raise _Review("state_outside_profile")
            if fields["state"] != code:
                fields["state"] = code
                edits.append("us_state_code")
        if "postcode" in fields:
            z = fields["postcode"]
            if re.fullmatch(r"[0-9]{5}-[0-9]{4}", z):
                fields["postcode"] = z.replace("-", "")
                edits.append("zip4_separator_removed")
            elif not re.fullmatch(r"[0-9]{5}(?:[0-9]{4})?", z):
                raise _Review("invalid_us_postcode")
        # Two UPS name slots: Name and AttentionName. Three different parties
        # cannot be transmitted as two; never move a contact into a street line.
        if all(k in fields for k in ("recipient", "organization", "attention")):
            raise _Review("ambiguous_contact_fields")
    return fields


def _segments(v, cc, shorten=False):
    primary = []
    if "address_line1" in v:
        if set(v) & {"road", "house_number", "po_box", "neighbourhood", "city_district", "block", "lot"}:
            raise _Review("ambiguous_street_components")
        primary.append(v["address_line1"])
    elif "po_box" in v:
        if cc != "US" or set(v) & {"road", "house_number", "neighbourhood", "city_district", "block", "lot"}:
            raise _Review("ambiguous_po_box")
        box = v["po_box"]
        if re.fullmatch(r"[0-9]+[A-Za-z]?", box):
            box = "PO BOX " + box
        elif not re.match(r"(?i)^P\.?\s*O\.?\s+BOX\s+\S", box):
            raise _Review("unrecognized_po_box")
        primary.append(box)
    elif cc == "US":
        if set(v) & {"neighbourhood", "city_district", "block", "lot"}:
            raise _Review("unmapped_street_components")
        if "road" not in v or "house_number" not in v:
            raise _Review("missing_street")
        road = v["road"]
        name, space, suffix = road.rpartition(" ")
        if shorten and space and suffix.lower() in _SUFFIX:
            road = name + space + _SUFFIX[suffix.lower()]
        primary.append(v["house_number"] + " " + road)
    elif cc in ("JP", "CN"):
        if not ({"neighbourhood", "road"} & set(v)) or not ({"house_number", "lot", "block"} & set(v)):
            raise _Review("missing_street")
        # Native address order; the supplied tokens already carry their local
        # designators. Spaces preserve boundaries of romanized and numeric parts.
        primary.append(" ".join(v[k] for k in ("city_district", "neighbourhood", "road", "block",
                                                 "lot", "house_number") if k in v))
    else:
        raise _Review("explicit_address_line_required")
    secondary = [v[k] for k in ("address_line2", "house", "subpremise") if k in v]
    for k, tag in (("entrance", "ENTRANCE"), ("floor", "FL"), ("unit", "UNIT")):
        if k not in v:
            continue
        value = v[k]
        if cc == "US" and not re.match(
            r"(?i)^(?:unit|suite|ste|apt|apartment|room|rm|floor|fl|entrance)\b|^#", value
        ):
            value = tag + " " + value
        elif cc in ("CN", "JP") and re.fullmatch(r"[0-9A-Za-z.-]+", value):
            suffix = ({"entrance": "入口", "floor": "階", "unit": "号室"} if cc == "JP"
                      else {"entrance": "入口", "floor": "层", "unit": "室"})[k]
            value += suffix
        elif cc not in ("US", "CN", "JP"):
            # No reviewed rule to express the meaning of bare identifiers here.
            raise _Review("explicit_secondary_line_required")
        secondary.append(value)
    return primary + secondary


def _shift_jis_size(s):
    # Use JIS, not Windows-31J vendor extensions. Reject lossy codec aliases.
    try:
        encoded = s.encode("shift_jis")
        if encoded.decode("shift_jis") == s:
            return len(encoded)
    except UnicodeError:
        pass
    raise _Review("unsupported_charset")


# B2 recommends half-width digits/letters if needed. Only these width forms are
# eligible; never normalize arbitrary kanji, names, numbers or kana by NFKC.
_JP_NARROW = {i: i - 0xFEE0 for a, b in [(0xFF10, 0xFF19), (0xFF21, 0xFF3A),
                (0xFF41, 0xFF5A), (0xFF0D, 0xFF0D)] for i in range(a, b + 1)}


def _yamato_piece(s, budget, edits, field):
    try:
        if _shift_jis_size(s) <= budget:
            return s
    except _Review:
        if s == s.translate(_JP_NARROW):
            raise
    narrow = s.translate(_JP_NARROW)
    if _shift_jis_size(narrow) > budget:
        raise _Review("field_overflow:" + field)
    if s != narrow:
        edits.append("halfwidth_ascii:" + field)
    return narrow


def _yamato_fields(fields, parts, v, edits):
    if not re.fullmatch(r"[0-9]{3}-?[0-9]{4}", fields["postcode"]):
        raise _Review("invalid_jp_postcode")
    state, city = fields["state"], fields["city"]
    if state not in _jp_prefecture_names():
        raise _Review("invalid_jp_prefecture")
    if "address_line1" in v:
        street = parts[0]
    else:
        # Reassemble only typed, native-order components. A bare block/lot
        # could mean a different number (丁目/街区/番/号); don't infer its role.
        if any(k in v and re.fullmatch(r"[0-9０-９-]+", v[k]) for k in ("block", "lot")):
            raise _Review("explicit_address_line_required")
        street = "".join(v[k] for k in ("city_district", "neighbourhood", "road", "block",
                                        "lot", "house_number") if k in v)
    if (city.startswith(state) or street.startswith((city, state))
            or re.search(r"[\s.．]", state + city + street)):
        raise _Review("ambiguous_yamato_address")
    street = _yamato_piece(street, 32, edits, "town_street")
    lines = [state + city + street]
    carrier = {"お届け先郵便番号": fields["postcode"], "お届け先住所": lines[0]}
    if len(parts) > 1:
        # Never fill a short address or name field with an overflowing building.
        building = _yamato_piece(" ".join(parts[1:]), 32, edits, "building")
        lines.append(building)
        carrier["お届け先住所（アパートマンション名）"] = building
    if "recipient" in fields:
        carrier["お届け先名"] = fields["recipient"]
    if "organization" in fields:
        carrier["お届け先会社・部門名１"] = fields["organization"]
    return lines, carrier


@lru_cache(maxsize=1)
def _jp_prefecture_names():
    # Exact names, including administrative suffix; do not infer from postcode.
    return frozenset("北海道 東京都 京都府 大阪府".split()) | {
        n + "県" for n in ("青森 岩手 宮城 秋田 山形 福島 茨城 栃木 群馬 埼玉 千葉 神奈川 新潟 富山 石川 "
                         "福井 山梨 長野 岐阜 静岡 愛知 三重 滋賀 兵庫 奈良 和歌山 鳥取 島根 岡山 広島 "
                         "山口 徳島 香川 愛媛 高知 福岡 佐賀 長崎 熊本 大分 宮崎 鹿児島 沖縄").split()}


def _ups_fields(fields, lines):
    ship_to = {"Address": {"AddressLine": lines, "City": fields["city"],
               "StateProvinceCode": fields["state"], "PostalCode": fields["postcode"], "CountryCode": "US"}}
    name = fields.get("organization") or fields.get("recipient")
    contact = fields.get("attention") or (fields.get("recipient") if fields.get("organization") else None)
    if name:
        ship_to["Name"] = name
    if contact:
        ship_to["AttentionName"] = contact
    return {"ShipTo": ship_to}


def _pack(parts, p, size):
    # Never split inside an opaque field; greedy packing of ordered semantic
    # segments is optimal for this single uniform line budget.
    if any(size(s) > p["line_limit"] for s in parts):
        return None
    if len(parts) <= p["max_lines"]:
        return parts
    out = []
    for part in parts:
        if out and size(out[-1] + " " + part) <= p["line_limit"]:
            out[-1] += " " + part
        else:
            out.append(part)
    return out if len(out) <= p["max_lines"] else None


def fit_label(country_code: str, components: Mapping[str, str | None],
              profile: str | Mapping | None = None) -> dict:
    """Return fitted destination fields, or a review result with *no* payload.

    Profile mapping: id, unit ('codepoints'/'utf8_bytes'/'shift_jis_bytes'), line_limit, max_lines,
    field_limits (including country_code); optional countries, required_fields,
    ascii_only. Every nonempty carrier field must have an explicit bound.
    """
    result = {"status": "review_required", "profile_id": None, "fields": None,
              "carrier_fields": None, "edits": [], "issues": [], "deliverability_verified": False}
    try:
        p = _profile(profile)
        result["profile_id"] = p["id"]
        result["profile_source"] = _UPS_SOURCE if p is _UPS else _YAMATO_SOURCE if p is _YAMATO else None
        if not isinstance(country_code, str) or not re.fullmatch(r"[A-Za-z]{2}", country_code):
            raise _Review("invalid_country")
        cc = country_code.upper()
        if cc not in _registry().country_codes or ("countries" in p and cc not in p["countries"]):
            raise _Review("country_outside_profile")
        v = _read(components)
        edits = []
        fields = _field_values(v, cc, p, edits)
        missing = sorted(set(p.get("required_fields", ())) - set(fields))
        if missing:
            raise _Review("missing_field:" + missing[0])
        size = {"codepoints": len, "utf8_bytes": lambda s: len(s.encode("utf-8")),
                "shift_jis_bytes": _shift_jis_size}[p["unit"]]
        for k, value in fields.items():
            if k not in p["field_limits"]:
                raise _Review("unsupported_field:" + k)
            if size(value) > p["field_limits"][k]:
                raise _Review("field_overflow:" + k)
        parts = _segments(v, cc)
        if p.get("ascii_only") and any(not s.isascii() for s in [*parts, *fields.values()]):
            raise _Review("unsupported_charset")
        if p is _YAMATO:
            lines, carrier = _yamato_fields(fields, parts, v, edits)
            result.update(status="fits", fields=fields | {"address_lines": lines},
                          carrier_fields=carrier, edits=edits)
            return result
        lines = _pack(parts, p, size)
        if lines is None and cc == "US" and "road" in v:
            short = _segments(v, cc, shorten=True)
            if parts != short:
                lines = _pack(short, p, size)
                if lines is not None:
                    edits.append("us_street_suffix")
        if lines is None and p is _UPS:
            # UPS prints all three streets in order. Wrap only at whitespace,
            # without ever splitting a unit/building token or changing spelling.
            for candidate, abbr in [(parts, False), (_segments(v, cc, shorten=True), True)]:
                tokens = [token for part in candidate for token in part.split(" ")]
                lines = _pack(tokens, p, size)
                if lines is not None:
                    edits.append("wrapped_words")
                    if abbr:
                        edits.append("us_street_suffix")
                    break
        if lines is None:
            raise _Review("address_lines_overflow")
        if len(lines) < len(parts):
            edits.append("combined_segments")
        result.update(status="fits", fields=fields | {"address_lines": lines}, edits=edits,
                      carrier_fields=_ups_fields(fields, lines) if p is _UPS else None)
    except _Review as error:
        result["issues"] = [str(error)]
    return result
