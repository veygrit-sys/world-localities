"""Private JSON endpoint. Run with a production WSGI server behind TLS."""
from __future__ import annotations

import hmac
import json
import os
import re
import sqlite3

from .address_ai import (MAX_BODY, AddressInputError, AddressServiceUnavailable,
                         decode_request, process_request)


def _response(start, status, data, extra=()):
    body = json.dumps(data, ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")
    headers = [("Content-Type", "application/json; charset=utf-8"),
               ("Content-Length", str(len(body))), ("Cache-Control", "no-store"),
               ("X-Content-Type-Options", "nosniff"), *extra]
    start(status, headers)
    return [body]


def create_app(token, *, index_path=None, label_profiles=None):
    """Only the server may choose index paths, credentials and carrier constraints."""
    if not isinstance(token, str) or not re.fullmatch(r"[!-~]{32,256}", token):
        raise ValueError("Configure a service token of 32-256 printable ASCII characters.")

    def application(env, start_response):
        def error(status, code, extra=()):
            return _response(start_response, status, {"error": code}, extra)

        path = env.get("PATH_INFO")
        method = env.get("REQUEST_METHOD")
        if path == "/healthz" and method == "GET" and not env.get("QUERY_STRING"):
            return _response(start_response, "200 OK", {"status": "alive"})
        if path != "/v1/address":
            return error("404 Not Found", "not_found")
        bearer = env.get("HTTP_AUTHORIZATION", "")
        if not (isinstance(bearer, str) and bearer.isascii() and len(bearer) <= 263
                and hmac.compare_digest(bearer, "Bearer " + token)):
            return error("401 Unauthorized", "unauthorized", [("WWW-Authenticate", "Bearer")])
        if method != "POST":
            return error("405 Method Not Allowed", "method_not_allowed", [("Allow", "POST")])
        if env.get("QUERY_STRING"):
            return error("400 Bad Request", "use_request_body")
        if env.get("CONTENT_TYPE", "").split(";", 1)[0].strip().lower() != "application/json":
            return error("415 Unsupported Media Type", "json_required")
        raw_length = env.get("CONTENT_LENGTH", "")
        if not raw_length:
            return error("411 Length Required", "length_required")
        if not re.fullmatch(r"[0-9]{1,10}", raw_length):
            return error("400 Bad Request", "invalid_length")
        length = int(raw_length)
        if length > MAX_BODY:
            return error("413 Content Too Large", "request_too_large")
        try:
            raw = env["wsgi.input"].read(length)
            if len(raw) != length:
                raise AddressInputError()
            result = process_request(decode_request(raw), index_path=index_path, label_profiles=label_profiles)
            return _response(start_response, "200 OK", result)
        except AddressInputError:
            return error("422 Unprocessable Content", "invalid_request")
        except (AddressServiceUnavailable, sqlite3.Error, OSError):
            return error("503 Service Unavailable", "reference_unavailable")
        except Exception:
            # JSON/source/worker errors must not expose an original address in a log or response.
            return error("500 Internal Server Error", "internal_error")

    return application


def from_environment():
    profiles = None
    if profile_file := os.environ.get("ADDRESS_AI_PROFILES"):
        with open(profile_file, encoding="utf-8") as stream:
            profiles = json.load(stream)
        if not isinstance(profiles, dict):
            raise ValueError("invalid service profile map")
    return create_app(os.environ.get("ADDRESS_AI_TOKEN"), index_path=os.environ.get("ADDRESS_AI_INDEX"),
                      label_profiles=profiles)
