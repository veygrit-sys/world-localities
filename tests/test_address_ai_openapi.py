"""Run OpenAPI request examples at the authenticated WSGI boundary, offline."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator

from addressing.address_ai import MAX_BODY, OPERATIONS
from addressing.address_service import create_app
from localities.postal_picker import build_index


SPEC = json.loads((Path(__file__).resolve().parents[1] / "docs/api/address-ai.openapi.json").read_bytes())


def validator(name):
    # Local-only resolution: use the spec's actual JSON pointers without a URI fetch.
    return Draft202012Validator({"$ref": "#/components/schemas/" + name, "components": SPEC["components"]})


class AddressOpenAPITest(unittest.TestCase):
    def test_documented_examples_and_safety_constraints_match_wire_results(self):
        endpoint = SPEC["paths"]["/v1/address"]["post"]
        examples = endpoint["requestBody"]["content"]["application/json"]["examples"]
        replies = endpoint["responses"]["200"]["content"]["application/json"]["examples"]
        self.assertEqual(SPEC["security"], [{"serviceBearer": []}])
        self.assertEqual(SPEC["paths"]["/healthz"]["get"]["security"], [])
        self.assertEqual(endpoint["requestBody"]["x-max-body-bytes"], MAX_BODY)
        self.assertEqual(set(OPERATIONS), {e["value"]["operation"] for e in examples.values()})
        for schema in SPEC["components"]["schemas"].values():
            Draft202012Validator.check_schema(schema)
        req, res = validator("AddressRequest"), validator("AddressResponse")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fixture.sqlite"
            rows = [("US", "02116", (("area", "Fixture town"),), "openapi-test")]
            with patch("localities.postal_picker._records", return_value=rows):
                build_index(path)
            token = "documentation-fixture-bearer-token-only"
            app = create_app(token, index_path=path)
            for key, example in examples.items():
                with self.subTest(example=key):
                    payload = example["value"]
                    req.validate(payload)
                    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    env = {"REQUEST_METHOD": "POST", "PATH_INFO": "/v1/address",
                           "HTTP_AUTHORIZATION": "Bearer " + token, "CONTENT_TYPE": "application/json",
                           "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw)}
                    response = []
                    with patch("socket.socket.connect", side_effect=AssertionError("unexpected network call")):
                        wire = b"".join(app(env, lambda status, headers: response.extend((status, headers))))
                    self.assertEqual(response[0], "200 OK")
                    self.assertEqual(dict(response[1])["Cache-Control"], "no-store")
                    doc = json.loads(wire)
                    res.validate(doc)
                    self.assertEqual(doc["result"]["status"], example["x-expected-status"])
                    if key in replies:
                        self.assertEqual(doc, replies[key]["value"])
                    # A consumer validating the response must reject an unsupported claim.
                    bad = copy.deepcopy(doc)
                    flag = "delivery_verified" if doc["operation"] == "translate" else "deliverability_verified"
                    bad["result"][flag] = True
                    self.assertFalse(res.is_valid(bad))
                    if doc["operation"] == "prepare_label":
                        bad = copy.deepcopy(doc)
                        bad["result"]["submitted"] = True
                        self.assertFalse(res.is_valid(bad))
                        if doc["result"]["status"] == "review_required":
                            for field, value in (("fields", {"address_lines": ["1"], "country_code": "US"}),
                                                 ("carrier_fields", {"ShipTo": {}})):
                                bad = copy.deepcopy(doc)
                                bad["result"][field] = value
                                self.assertFalse(res.is_valid(bad))
        self.assertTrue(set(replies) <= set(examples))
        base = examples["preparePoint"]["value"]
        for extra in ({"source_language": "en"}, {"index_path": "a.sqlite"}, {"label_profiles": {}}):
            self.assertFalse(req.is_valid(base | extra))


if __name__ == "__main__":
    unittest.main()
