"""Montenegro office replay selects code fields rather than nearby numbers."""

import gzip
import hashlib
from html import escape
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from localities.postal_europe_sources import iter_europe_records


def widget(identity, value, *, raw=False):
    content = value if raw else escape(value)
    return (f'<div data-id="{identity}" data-widget_type="jet-listing-dynamic-field.default">'
            f'<div class="jet-listing-dynamic-field__content">{content}</div></div>')


def card(post_id, code="84001", *, place="Bijelo Polje", address="Trg slobode bb", extra=""):
    fields = widget("6d2832a", code)
    if place is not None:
        fields += widget("0af2775", place)
    if address is not None:
        fields += widget("9a91ea7", address)
    return (f'<div class="other jet-listing-grid__item" data-post-id="{post_id}">'
            + fields + extra + '</div>')


class MontenegroPostalSources(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "source.json"
        self.source = {
            "format": "official_postal_source", "adapter": "me_postacg_offices", "expected_country": "ME",
        }

    def records(self, markup, *, compressed=False):
        payload = json.dumps({"success": True, "data": {
            "html": markup, "scripts": {"untrusted": "https://invalid.example/never-load.js"},
        }}, ensure_ascii=False).encode("utf-8")
        source = dict(self.source)
        if compressed:
            source.update(compression="gzip", uncompressed_bytes=len(payload),
                          uncompressed_sha256=hashlib.sha256(payload).hexdigest())
            self.path.write_bytes(gzip.compress(payload, mtime=0))
        else:
            self.path.write_bytes(payload)
        return list(iter_europe_records(source, self.path))

    def test_duplicate_office_codes_keep_order_identity_and_source_fields(self):
        rows = self.records(card(13291, place="Bijelo Polje – Pošta", address="Trg & ulica <1>")
                            + card(2258, "84001", place="Druga poslovnica")
                            + card(2250, "81410"))
        self.assertEqual([row["code"] for row in rows], ["84001", "84001", "81410"])
        self.assertEqual(rows[0]["source_locator"], "card:1/post_id:13291")
        self.assertEqual(rows[1]["source_locator"], "card:2/post_id:2258")
        self.assertEqual(rows[0]["source_post_id"], "13291")
        self.assertEqual(rows[0]["place_name"], "Bijelo Polje – Pošta")
        self.assertEqual(rows[0]["source_address"], "Trg & ulica <1>")
        self.assertEqual(rows[0]["country_code"], "ME")
        self.assertEqual(rows[0]["postal_use"], "post_office")
        self.assertTrue(all(isinstance(value, str) for row in rows for value in row.values()))

    def test_other_numbers_annotations_scripts_and_class_lookalikes_are_ignored(self):
        extra = (widget("telephone", "12345") + widget("790c30d", "true dostavna pošta")
                 + '<script>const fake = \'<div data-id="6d2832a">99999</div>\';</script>')
        lookalike = '<div class="jet-listing-grid__item-extra" data-post-id="54321">54321</div>'
        outside = widget("6d2832a", "99999")
        rows = self.records(outside + lookalike + card(13291, extra=extra))
        self.assertEqual([row["code"] for row in rows], ["84001"])

    def test_optional_fields_and_nested_text_remain_source_text(self):
        markup = card(1, "01234", place=None, address=None)
        markup += ('<div class="jet-listing-grid__item" data-post-id="2">'
                   + widget("6d2832a", '<span>84</span>001', raw=True)
                   + widget("0af2775", '  Pošta <span>č</span>  ', raw=True) + '</div>')
        rows = self.records(markup, compressed=True)
        self.assertEqual(rows[0]["code"], "01234")
        self.assertEqual(rows[0]["place_name"], "")
        self.assertEqual(rows[0]["source_address"], "")
        self.assertEqual(rows[1]["code"], "84001")
        self.assertEqual(rows[1]["source_place"], "  Pošta č  ")

    def test_missing_duplicate_or_lookalike_code_fields_are_rejected(self):
        bad = [
            '<div class="jet-listing-grid__item" data-post-id="1">' + widget("telephone", "84001") + '</div>',
            card(1, extra=widget("6d2832a", "84002")),
            '<div class="jet-listing-grid__item" data-post-id="1"><div data-id="6d2832a">'
            '<div class="jet-listing-dynamic-field__content">84001</div>'
            '<div class="jet-listing-dynamic-field__content">84002</div></div></div>',
            '<div class="jet-listing-grid__item" data-post-id="1"><div data-id="6d2832a">'
            '<div class="jet-listing-dynamic-field__content-extra">84001</div></div></div>',
        ]
        for markup in bad:
            with self.subTest(markup=markup), self.assertRaisesRegex(ValueError, "field|code"):
                self.records(markup)

    def test_codes_are_validated_without_trimming_or_number_repair(self):
        for code in (" 84001", "84001 ", "84001 true dostavna pošta", "8400", "840001", "８４００１", ""):
            with self.subTest(code=code), self.assertRaisesRegex(ValueError, "five-digit"):
                self.records(card(1, code))

    def test_incomplete_nested_cards_and_invalid_identity_are_rejected(self):
        for markup in (card(1)[:-6], card(1, extra=card(2)), card(""), card("abc"), card("１")):
            with self.subTest(markup=markup), self.assertRaises(ValueError):
                self.records(markup)
        nested = '<div class="jet-listing-grid__item" data-post-id="1">' + widget(
            "6d2832a", widget("9a91ea7", "84001"), raw=True) + '</div>'
        with self.assertRaisesRegex(ValueError, "widget"):
            self.records(nested)

    def test_active_markup_inside_code_is_rejected_without_evaluation(self):
        markup = '<div class="jet-listing-grid__item" data-post-id="1">' + widget(
            "6d2832a", '<script>84001</script>', raw=True) + '</div>'
        with self.assertRaisesRegex(ValueError, "active markup"):
            self.records(markup)

    def test_response_schema_and_duplicate_json_keys_are_rejected(self):
        for value in ([], {}, {"success": 1, "data": {"html": card(1)}},
                      {"success": False, "data": {"html": card(1)}},
                      {"success": True, "data": []}, {"success": True, "data": {"html": []}},
                      {"success": True, "data": {"html": ""}}):
            self.path.write_text(json.dumps(value), encoding="utf-8")
            with self.subTest(value=value), self.assertRaises(ValueError):
                list(iter_europe_records(self.source, self.path))
        self.path.write_text('{"success":true,"success":true,"data":{"html":"x"}}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate field"):
            list(iter_europe_records(self.source, self.path))
        self.path.write_bytes(b"\xff")
        with self.assertRaisesRegex(ValueError, "JSON"):
            list(iter_europe_records(self.source, self.path))

    def test_adapter_and_country_are_explicit(self):
        for change in ({"adapter": "other"}, {"format": "html"}, {"expected_country": "BA"},
                       {"expected_country": None}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                list(iter_europe_records({**self.source, **change}, self.path))


if __name__ == "__main__":
    unittest.main()
