"""Serve the postal-picker form and its read-only JSON endpoints."""

from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

from localities.postal_picker import PostalPicker


_ROOT = Path(__file__).resolve().parents[1]
_WEB = Path(__file__).with_name("postal_picker_web")
_ASSETS = {
    "/": ("index.html", "text/html"),
    "/index.html": ("index.html", "text/html"),
    "/sources": ("sources.html", "text/html"),
    "/styles.css": ("styles.css", "text/css"),
    "/app.js": ("app.js", "text/javascript"),
}


class PickerHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, picker, catalogue, allowed_origins=(), **kwargs):
        self.picker = picker
        self.catalogue = catalogue
        self.allowed_origins = allowed_origins
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        # The default handler includes the full user query in its access log.
        pass

    def send_content(self, status, content_type, data):
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        if self.allowed_origins:
            self.send_header("Vary", "Origin")
            origin = self.headers.get("Origin")
            if origin in self.allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass  # The browser can cancel a lookup when the postal code changes.

    def send_json(self, status, obj):
        self.send_content(status, "application/json", json.dumps(
            obj, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ).encode("utf-8"))

    def do_GET(self):
        try:
            url = urlsplit(self.path)
        except ValueError:
            self.send_json(400, {"error": "Invalid request path"})
            return
        if url.path in _ASSETS:
            name, content_type = _ASSETS[url.path]
            self.send_content(200, content_type, (_WEB / name).read_bytes())
            return
        if url.path == "/api/countries":
            try:
                available = self.picker.countries()
            except (sqlite3.Error, OSError):
                self.send_json(503, {"error": "Postal index unavailable"})
                return
            self.send_json(200, {"countries": self.catalogue, "available": available})
            return
        if url.path != "/api/postal":
            self.send_json(404, {"error": "Unknown resource"})
            return
        try:
            fields = parse_qs(url.query, keep_blank_values=True, max_num_fields=20)
            if (fields.keys() - {"country", "postcode", "path", "after", "limit"}
                    or not {"country", "postcode"} <= fields.keys()
                    or any(len(values) != 1 for key, values in fields.items() if key != "path")):
                raise ValueError("Supply one country and postcode; only path may repeat")
            path = fields.get("path", [])
            if len(path) > 16 or any(len(value) > 2048 for value in path):
                raise ValueError("Invalid candidate path")
            after = int(fields["after"][0]) if "after" in fields else None
            limit = int(fields.get("limit", ["50"])[0])
            result = self.picker.lookup(fields["country"][0], fields["postcode"][0],
                                        path, after=after, limit=limit)
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
            return
        except (sqlite3.Error, OSError):
            self.send_json(503, {"error": "Postal index unavailable"})
            return
        self.send_json(200, result)


def make_server(index, host="127.0.0.1", port=8765, *, allowed_origins=()):
    picker = PostalPicker(index)
    picker.countries()
    catalogue = json.loads((_ROOT / "countries/catalog.json").read_text(encoding="utf-8"))
    handler = partial(PickerHandler, picker=picker, catalogue=sorted(
        row["code"] for row in catalogue["countries"]), allowed_origins=frozenset(allowed_origins))
    return ThreadingHTTPServer((host, port), handler)
