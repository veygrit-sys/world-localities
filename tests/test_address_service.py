"""Transport and PII boundaries, independent of carrier connections."""
import io
import json
import unittest
from unittest.mock import patch

from addressing.address_ai import AddressInputError, MAX_BODY, decode_request, process_request
from addressing.address_service import create_app


class AddressServiceTest(unittest.TestCase):
    token = "a" * 40

    def call(self, payload=b"{}", **env):
        environ = {"REQUEST_METHOD": "POST", "PATH_INFO": "/v1/address",
                   "HTTP_AUTHORIZATION": "Bearer " + self.token, "CONTENT_TYPE": "application/json",
                   "CONTENT_LENGTH": str(len(payload)), "wsgi.input": io.BytesIO(payload), **env}
        reply = []
        body = b"".join(create_app(self.token)(environ, lambda *row: reply.extend(row)))
        self.assertEqual(dict(reply[1])["Cache-Control"], "no-store")
        return int(reply[0][:3]), json.loads(body)

    def test_private_endpoint_and_health(self):
        self.assertEqual(self.call(HTTP_AUTHORIZATION="")[0], 401)
        self.assertEqual(self.call(HTTP_AUTHORIZATION="Bearer " + "x" * 40)[0], 401)
        self.assertEqual(self.call(REQUEST_METHOD="GET")[0], 405)
        self.assertEqual(self.call(PATH_INFO="/healthz", REQUEST_METHOD="GET",
                                   HTTP_AUTHORIZATION=""), (200, {"status": "alive"}))
        with self.assertRaises(ValueError):
            create_app("")

    def test_bounded_inputs_and_no_request_data_in_errors(self):
        self.assertEqual(self.call(QUERY_STRING="unit=private")[0], 400)
        self.assertEqual(self.call(CONTENT_TYPE="text/plain")[0], 415)
        self.assertEqual(self.call(CONTENT_LENGTH="")[0], 411)
        self.assertEqual(self.call(CONTENT_LENGTH=str(MAX_BODY + 1))[0], 413)
        self.assertEqual(self.call(CONTENT_LENGTH="90")[0], 422)
        for raw in (b'{"country":"JP","country":"US"}', b'{"query":NaN}', b'[]', b'\xff'):
            self.assertEqual(self.call(raw), (422, {"error": "invalid_request"}))
        for value in ("room\n123", "12\u202e34"):
            data = {"operation": "validate", "country": "US", "components": {"unit": value}}
            self.assertEqual(self.call(json.dumps(data).encode()), (422, {"error": "invalid_request"}))
        with patch("addressing.address_service.process_request", side_effect=ValueError("private address")):
            self.assertEqual(self.call(), (500, {"error": "internal_error"}))

    def test_input_cannot_choose_index_or_register_a_contract(self):
        bad = [{"operation": "suggest", "postcode": "20001", "index_path": "/secret"},
               {"operation": "fit_label", "components": {"city": "X"}, "profile_id": "unknown"},
               {"operation": "validate", "components": {"zip": "12345", "postcode": "23456"}},
               {"operation": "translate", "components": {"city": "X"}, "source_language": "en"}]
        for case in bad:
            with self.subTest(case=case), self.assertRaises(AddressInputError):
                process_request({**case, "country": "US"})
        with self.assertRaises(AddressInputError):
            decode_request(b" " * (MAX_BODY + 1))

    def test_missing_index_does_not_look_like_an_address_rejection(self):
        data = {"operation": "suggest", "postcode": "00000", "country": "US"}
        self.assertEqual(self.call(json.dumps(data).encode()), (503, {"error": "reference_unavailable"}))

    def test_valid_http_json(self):
        data = {"operation": "validate", "country": "US", "components": {"postcode": "12ABC"}}
        status, result = self.call(json.dumps(data).encode())
        self.assertEqual((status, result["result"]["status"]), (200, "invalid_format"))
        self.assertFalse(result["result"]["deliverability_verified"])

    def test_public_japanese_office_fields_and_unknown_room_via_http(self):
        office = {"organization": "外務省", "state": "東京都", "city": "千代田区",
                  "neighbourhood": "霞が関", "house_number": "2丁目2-1", "postcode": "100-8919"}
        request = {"operation": "prepare_label", "country": "JP", "components": office,
                   "profile_id": "yamato-jp-b2"}
        status, reply = self.call(json.dumps(request).encode())
        self.assertEqual(status, 200)
        result = reply["result"]
        self.assertEqual(result["carrier_fields"]["お届け先住所"], "東京都千代田区霞が関2丁目2-1")
        self.assertEqual(result["status"], "prepared")
        self.assertFalse(result["submitted"])
        office["unit"] = "未確認101"
        status, reply = self.call(json.dumps(request).encode())
        self.assertEqual(status, 200)
        self.assertEqual(reply["result"]["status"], "review_required")
        self.assertIsNone(reply["result"]["carrier_fields"])
