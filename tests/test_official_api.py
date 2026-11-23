import io
import json
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from localities.__main__ import main
from localities.official_adapters import ADAPTERS
from localities.official_api import MAX_RESPONSE_BYTES, _get_json, _NoRedirect, lookup_official, official_sources


def replay(country, source, query, payload, **options):
    with patch("localities.official_api._get_json", return_value=payload) as fetch:
        result = lookup_official(country, query, source=source, **options)
    return result, parse_qs(urlsplit(fetch.call_args.args[0]).query)


class OfficialApiTests(unittest.TestCase):
    def test_catalog_and_cli_are_offline(self):
        with patch("localities.official_api._get_json", side_effect=AssertionError):
            sources = official_sources()
            self.assertEqual({s["id"] for s in sources if s["endpoint"]}, set(ADAPTERS))
            self.assertEqual(len(sources), len({s["id"] for s in sources}))
            for s in sources:
                self.assertTrue(s["documentation"].startswith("https://"))
                self.assertIn(s["authority"], {"government", "municipality", "postal_operator"})
                self.assertEqual(s["intake"] == "live_api", bool(s["endpoint"]))
                if not s["endpoint"]:
                    self.assertTrue(s["next_check"])
                self.assertTrue(all(c.isascii() and len(c) == 2 for c in s["countries"]))
                if s["status"] == "implemented":
                    self.assertTrue(s["endpoint"].startswith("https://"))
            with patch.object(sys, "argv", ["localities", "official-sources", "--country", "tw"]), redirect_stdout(io.StringIO()) as out:
                main()
            taipei = json.loads(out.getvalue())["sources"][0]
            self.assertEqual((taipei["status"], taipei["intake"]), ("candidate", "bundled_offline"))
            self.assertEqual(official_sources("JP"), [])

    def test_invalid_routes_never_send(self):
        with patch("localities.official_api._get_json", side_effect=AssertionError):
            for c, s, q, extra in [
                ("NO", "nl-pdok", "Road 1", {}), ("TW", "tw-taipei", "市府路", {}),
                ("NØ", "no-kartverket", "Oslo", {}), ("NL", "nl-pdok", "a\nb", {}),
                ("HK", "hk-als", "", {}), ("MC", "la-poste", "９８０００", {}),
                ("LI", "ch-swisstopo", "../1234", {}), ("US", "dc-mar", "a", {"limit": 11}),
                ("CA", "ca-vancouver", "Street only", {}), ("FR", "fr-ban", "rue", {"province": "02"})
            ]:
                with self.subTest(source=s, query=q), self.assertRaises(ValueError):
                    lookup_official(c, q, source=s, **extra)

    def test_empty_errors_and_provider_rejection(self):
        for payload, expected in [({"features": []}, "no_candidates"), ({}, "unavailable"),
                                  ({"features": {}}, "unavailable"), ({"error": {"code": 400}}, "unavailable")]:
            self.assertEqual(replay("US", "dc-mar", "a", payload)[0]["status"], expected)
        for failure, reason in [(HTTPError("https://example.invalid/personal", 429, "", {}, None), "http_error"),
                                (URLError("personal"), "connection_error"), (ValueError("personal"), "invalid_response")]:
            with patch("localities.official_api._get_json", side_effect=failure):
                result = lookup_official("US", "secret", source="dc-mar")
                self.assertEqual(result["reason"], reason)
                self.assertNotIn("secret", str(result))
                self.assertNotIn("personal", str(result))
        response = io.BytesIO(b" " * (MAX_RESPONSE_BYTES + 1))
        with patch("localities.official_api.build_opener") as opener:
            opener.return_value.open.return_value = response
            with self.assertRaises(ValueError):
                _get_json("https://example.invalid")
        self.assertIsNone(_NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.invalid"))

    def test_exact_label_street_and_fuzzy_hit(self):
        def feature(level, label, insee="75101"):
            return {"properties": {"type": level, "label": label, "citycode": insee}}
        payload = {"features": [feature("street", "Rue de Paris"), feature("housenumber", "2 Rue de Paris"),
                                feature("housenumber", "2 Rue de Paris", "97411")]}
        result, params = replay("fr", "fr-ban", "Rue de Paris", payload)
        self.assertEqual(params["index"], ["address"])
        self.assertEqual([(r["scope"], r["comparison"]) for r in result["candidates"]],
                         [("street", "exact_label"), ("address_point", "suggestion")])
        self.assertFalse(result["deliverability_verified"])

    def test_postcode_and_insee_must_both_match(self):
        def row(code, post="97150"):
            return {"code_postal": post, "code_commune_insee": code, "nom_de_la_commune": "Place"}
        data = {"results": [row("97101"), row("97801"), row("98901"), row("97801", "99999")]}
        result, params = replay("MF", "la-poste", "97150", data, limit=1)
        self.assertEqual(result["candidates"][0]["insee_code"], "97801")
        self.assertEqual(result["candidates"][0]["comparison"], "exact_postcode")
        self.assertEqual(params["qs"], ["code_postal:97150"])
        self.assertEqual(replay("MC", "la-poste", "97150", data)[0]["status"], "no_candidates")

    def test_dc_city_snapshot_and_query_escaping(self):
        path = Path(__file__).resolve().parents[1] / "localities/open_reference/us/address-points.json"
        data = json.loads(path.read_bytes())
        q = data["features"][0]["attributes"]["ADDRESS"]
        result, params = replay("US", "dc-mar", q, data, limit=1)
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["comparison"], "exact_label")
        self.assertIn("STATUS = 'ACTIVE'", params["where"][0])
        _, params = replay("US", "dc-mar", "1 O'Brien & A", {"features": []})
        self.assertIn("1 O''BRIEN & A", params["where"][0])

    def test_municipal_portals_preserve_quotes_in_street_names(self):
        for country, source, q in [("IT", "it-bologna", "Via dell'Indipendenza 1"),
                                   ("CA", "ca-vancouver", '1 W "A" St')]:
            result, params = replay(country, source, q, {"results": []})
            literal = params["where"][0].rsplit(" = ", 1)[1]
            expected = q if country == "IT" else q.partition(" ")[2]
            self.assertEqual(json.loads(literal), expected.upper())
            self.assertEqual(result["status"], "no_candidates")

    def test_cape_town_suburb_and_registered_label_must_agree(self):
        def row(suburb):
            return {"attributes": {"OBJECTID": 10, "FULL_ADR": "12  HERTZOG Boulevard " + suburb,
                                   "OFC_SBRB_NAME": suburb}}
        r, params = replay("ZA", "za-cape-town", "12 Hertzog Boulevard Foreshore",
                           {"features": [row("FORESHORE"), row("BERGVLIET")]})
        self.assertEqual(params["returnGeometry"], ["false"])
        self.assertIn("12  HERTZOG", params["where"][0])
        self.assertEqual([(h["locality"], h["comparison"]) for h in r["candidates"]],
                         [("FORESHORE", "exact_label")])

    def test_census_range_is_never_an_address_point(self):
        def hit(state):
            return {"matchedAddress": "100 AVE", "addressComponents": {"state": state, "fromAddress": "2", "toAddress": "200"}}
        result, _ = replay("US", "us-census", "100 AVE", {"result": {"addressMatches": [hit("DC"), hit("PR")]}})
        self.assertEqual(len(result["candidates"]), 1)
        self.assertEqual(result["candidates"][0]["scope"], "street_range")
        self.assertFalse(result["deliverability_verified"])

    def test_hong_kong_chinese_only_and_empty_response(self):
        p = {"ChiPremisesAddress": {"Region": "香港", "ChiStreet": {"StreetName": "測試道", "BuildingNoFrom": "5"}}}
        result, _ = replay("HK", "hk-als", "香港測試道5號", {"SuggestedAddress": [{"Address": {"PremisesAddress": p}}]})
        self.assertEqual(result["candidates"][0]["comparison"], "exact_label")
        self.assertEqual(result["candidates"][0]["label_zh_hant"], "香港測試道5號")
        self.assertEqual(replay("HK", "hk-als", "unknown", {"RequestAddress": {"AddressLine": ["unknown"]}})[0]["status"],
                         "no_candidates")

    def test_swiss_entrance_and_liechtenstein_use_register_municipality(self):
        p = {"feature": {"attributes": {"com_fosnr": 7001, "adr_egaid": 42, "adr_official": True,
                                        "stn_label": "Gasse", "adr_number": "2", "zip_label": "9490 Vaduz", "com_name": "Vaduz"}}}
        self.assertEqual(replay("CH", "ch-swisstopo", "42", p)[0]["status"], "no_candidates")
        self.assertEqual(replay("LI", "ch-swisstopo", "41", p)[0]["status"], "no_candidates")
        self.assertEqual(replay("LI", "ch-swisstopo", "42", p)[0]["candidates"][0]["comparison"], "exact_identifier")

    def test_sources_with_distinct_quality_levels(self):
        fixtures = [
            ("LU", "lu-act", "street", {"success": True, "results": [{"address": "Street", "accuracy": 6}]}, "street"),
            ("UY", "uy-ide", "route", [{"address": "route", "type": "CALLEyPORTAL", "state": 0, "stateMsg": "Aproximado"}], "approximate"),
            ("NL", "nl-pdok", "Dam 1", {"response": {"docs": [{"id": "1", "type": "adres", "weergavenaam": "Dam 1"}]}}, "address_point"),
            ("NO", "no-kartverket", "Gate 1", {"adresser": [{"adressetekst": "Gate 1", "kommunenummer": "0301", "kommunenavn": "OSLO"}]}, "address_point"),
            ("IT", "it-bologna", "Via 1", {"results": [{"indirizzo_completo": "VIA 1", "civkey": "001"}]}, "address_point"),
            ("CA", "ca-vancouver", "1 Abc St", {"results": [{"civic_number": "1", "std_street": "ABC ST"}]}, "property_address"),
            ("AU", "au-queensland", "1 St QLD", {"features": [{"attributes": {"address": "1 St QLD", "state": "QLD", "address_pid": 1, "locality": "City"}}]}, "property_address"),
        ]
        for country, source, q, payload, scope in fixtures:
            with self.subTest(source=source):
                result, _ = replay(country, source, q, payload)
                self.assertEqual(result["candidates"][0]["scope"], scope)
                self.assertFalse(result["deliverability_verified"])

    def test_argentina_province_is_applied_to_query_and_response(self):
        def hit(province):
            return {"nomenclatura": "Calle 50", "calle": {"id": "A"}, "localidad": {"nombre": "Town"},
                    "provincia": {"id": province, "nombre": "Province"}}
        result, params = replay("AR", "ar-georef", "Calle 50", {"direcciones": [hit("06"), hit("02")]}, province="02")
        self.assertEqual(params["provincia"], ["02"])
        self.assertEqual([r["province"] for r in result["candidates"]], ["02"])
        self.assertEqual(result["candidates"][0]["scope"], "normalized_street_address")

    def test_cli_uses_selected_source_and_exposes_errors_as_json(self):
        argv = ["localities", "official-lookup", "--country", "HK", "--source", "hk-als", "--query", "City Hall"]
        with patch.object(sys, "argv", argv), patch("localities.official_api._get_json", side_effect=TimeoutError), \
                redirect_stdout(io.StringIO()) as out, self.assertRaises(SystemExit) as ex:
            main()
        self.assertEqual(ex.exception.code, 1)
        self.assertEqual(json.loads(out.getvalue())["status"], "unavailable")
