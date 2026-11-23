"""Opt-in, single-provider lookups. The catalog itself never needs a network connection."""

import csv
from functools import cache
from http.client import HTTPException
import json
from pathlib import Path
import re
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .official_adapters import ADAPTERS

CATALOG = Path(__file__).with_name("official_api_sources.csv")
MAX_RESPONSE_BYTES = 1024 * 1024


def country_code(value):
    if not isinstance(value, str) or not re.fullmatch("[a-zA-Z]{2}", value):
        raise ValueError("country must contain two ASCII letters")
    return value.upper()


@cache
def _catalog():
    with CATALOG.open(encoding="utf-8", newline="") as stream:
        return {row["id"]: row for row in csv.DictReader(stream)}


def official_sources(country=None):
    """List implemented routes and research candidates, including geographic limitations."""
    selected = country_code(country) if country is not None else None
    result = []
    for key, row in _catalog().items():
        countries = row["countries"].split()
        if selected is None or selected in countries:
            result.append({**row, "countries": countries,
                           "status": "implemented" if key in ADAPTERS else "candidate"})
    return result


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # The caller only authorized a request to the explicitly selected endpoint.
        return None


def _get_json(url):
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "world-localities/1"})
    with build_opener(_NoRedirect()).open(request, timeout=25) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("oversized response")
    return json.loads(raw)


def _comparison(query, row):
    def normalized(label):
        return " ".join(unicodedata.normalize("NFC", label).casefold().split())
    if row["scope"] == "postal_locality" and row.get("postcode") == query:
        return "exact_postcode"
    if row["scope"] == "building_entrance" and row.get("record_id") == query:
        return "exact_identifier"
    if any(normalized(row[key]) == normalized(query) for key in ("label", "label_en", "label_zh_hant") if key in row):
        return "exact_label"
    return "suggestion"


def lookup_official(country, query, *, source, limit=5, province=None):
    """Send a single query directly to the selected public authority and return scoped evidence."""
    country = country_code(country)
    if (not isinstance(query, str) or not query.strip() or len(query) > 250
            or any(unicodedata.category(ch) in {"Cc", "Cs", "Zl", "Zp"} for ch in query)):
        raise ValueError("query must contain 1 to 250 printable characters on one line")
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("limit must be an integer from 1 to 10")
    if not isinstance(source, str) or source not in ADAPTERS:
        raise ValueError("select an implemented official source")
    service = _catalog()[source]
    if country not in service["countries"].split():
        raise ValueError("source does not cover the selected country or territory")

    query = query.strip()
    prepare, parse = ADAPTERS[source]
    params = prepare(query, limit)
    if province is not None:
        if source != "ar-georef" or not isinstance(province, str) or not re.fullmatch("[0-9]{2}", province):
            raise ValueError("province is a two-digit INDEC code for ar-georef")
        params["provincia"] = province
    endpoint = service["endpoint"]
    if source == "ch-swisstopo":
        endpoint += query  # prepare() accepts only a numeric EGAID.
    result = {"source": source, "country": country, "area": service["area"],
              "publisher": service["publisher"], "documentation": service["documentation"],
              "deliverability_verified": False, "candidates": []}
    try:
        payload = _get_json(endpoint + "?" + urlencode(params))
        if isinstance(payload, dict) and "error" in payload:
            return {**result, "status": "unavailable", "reason": "provider_error"}
        rows = list(parse(payload, country, query))
        if province is not None:
            rows = [row for row in rows if row["province"] == province]
        for row in rows[:limit]:
            row["comparison"] = _comparison(query, row)
    except HTTPError as error:
        error.close()
        return {**result, "status": "unavailable", "reason": "http_error", "http_status": error.code}
    except (URLError, OSError, HTTPException):
        return {**result, "status": "unavailable", "reason": "connection_error"}
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return {**result, "status": "unavailable", "reason": "invalid_response"}
    return {**result, "status": "candidates" if rows else "no_candidates", "candidates": rows[:limit]}


def add_official_cli(commands):
    sources = commands.add_parser("official-sources", help="list official address API sources offline")
    sources.add_argument("--country", help="filter by destination country or territory")
    lookup = commands.add_parser("official-lookup", help="send a query to one selected keyless official API")
    lookup.add_argument("--country", required=True)
    lookup.add_argument("--source", required=True)
    lookup.add_argument("--query", required=True)
    lookup.add_argument("--province", help="two-digit INDEC province code for ar-georef")
    lookup.add_argument("--limit", type=int, default=5, help="maximum candidates, from 1 to 10")
