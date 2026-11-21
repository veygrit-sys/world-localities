import http.client
import json
import sqlite3
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from addressing.postal_picker_server import make_server


class PostalPickerHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with patch("addressing.postal_picker_server.PostalPicker") as picker_type:
            cls.picker = picker_type.return_value
            cls.picker.countries.return_value = ["JP"]
            cls.server = make_server("test-index", port=0, allowed_origins=["https://wallet.example"])
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.worker.join()
        cls.server.server_close()

    def get(self, path, origin=None):
        client = http.client.HTTPConnection(*self.server.server_address, timeout=5)
        try:
            client.request("GET", path, headers={"Origin": origin} if origin else {})
            response = client.getresponse()
            return response.status, response.headers, response.read()
        finally:
            client.close()

    def test_catalog_distinguishes_available_countries(self):
        status, headers, body = self.get("/api/countries", "https://wallet.example")
        self.assertEqual(status, 200)
        self.assertIn("HK", json.loads(body)["countries"])
        self.assertEqual(json.loads(body)["available"], ["JP"])
        self.assertEqual(headers["Access-Control-Allow-Origin"], "https://wallet.example")
        self.assertEqual(headers["Vary"], "Origin")
        self.assertIsNone(self.get("/api/countries", "https://other.example")[1]["Access-Control-Allow-Origin"])

    def test_postal_route_preserves_order_pagination_and_unicode(self):
        query = urlencode([("country", "JP"), ("postcode", "０６４－０９４１"),
                           ("path", "selected-city"), ("path", "selected-town"),
                           ("after", 50), ("limit", 25)])
        self.picker.lookup.return_value = {"status": "leaf", "selected": [{"label": "札幌市"}]}
        status, headers, body = self.get("/api/postal?" + query)
        self.picker.lookup.assert_called_with("JP", "０６４－０９４１", ["selected-city", "selected-town"],
                                              after=50, limit=25)
        self.assertEqual(status, 200)
        self.assertIn("札幌市", body.decode())
        self.assertEqual(headers["Cache-Control"], "no-store")

    def test_invalid_query_and_stale_path(self):
        for suffix in ["country=JP", "country=JP&postcode=1&postcode=2",
                       "country=JP&postcode=1&test=1", "country=JP&postcode=1&limit=x",
                       "country=JP&postcode=1" + "&path=a" * 17]:
            with self.subTest(suffix=suffix):
                self.assertEqual(self.get("/api/postal?" + suffix)[0], 400)
        with patch.object(self.picker, "lookup", side_effect=ValueError("unknown selection")):
            self.assertEqual(self.get("/api/postal?country=JP&postcode=1&path=bad")[0], 400)

    def test_service_unavailable(self):
        for method, path in [("countries", "/api/countries"), ("lookup", "/api/postal?country=JP&postcode=1")]:
            with patch.object(self.picker, method, side_effect=sqlite3.OperationalError("private database path")):
                status, _, body = self.get(path)
                self.assertEqual(status, 503)
                self.assertNotIn(b"private database path", body)

    def test_static_entry_and_unknown_path(self):
        for path, mime in [("/", "text/html"), ("/sources", "text/html"), ("/app.js", "text/javascript"), ("/styles.css", "text/css")]:
            with self.subTest(path=path):
                status, headers, body = self.get(path)
                self.assertEqual(status, 200)
                self.assertTrue(headers["Content-Type"].startswith(mime))
                self.assertGreater(len(body), 100)
        self.assertEqual(self.get("/unknown")[0], 404)
