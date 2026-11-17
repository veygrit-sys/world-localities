"""Replay fixed European postal snapshots without executing page scripts."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any

from .postal_source_io import read_source_text


_WIDGET_FIELDS = {"6d2832a": "code", "0af2775": "place", "9a91ea7": "address"}


@dataclass
class _Div:
    card: bool = False
    widget: str | None = None
    content: bool = False


@dataclass
class _Office:
    post_id: str
    widgets: set[str] = field(default_factory=set)
    values: dict[str, str] = field(default_factory=dict)


class _MontenegroOffices(HTMLParser):
    """Recognize exact listing cards and the published postal-field widget."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[_Div] = []
        self.office: _Office | None = None
        self.widget: str | None = None
        self.parts: list[str] | None = None
        self.records: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"} and self.parts is not None:
            raise ValueError("active markup inside Montenegro postal field")
        if tag == "br" and self.parts is not None:
            self.parts.append("\n")
        if tag != "div":
            return
        attributes = dict(attrs)
        for name in ("class", "data-id", "data-post-id"):
            if sum(key == name for key, _ in attrs) > 1:
                raise ValueError("duplicate Montenegro office HTML attribute")
        classes = set((attributes.get("class") or "").split())
        frame = _Div()
        if "jet-listing-grid__item" in classes:
            if self.office is not None:
                raise ValueError("nested Montenegro office card")
            post_id = attributes.get("data-post-id") or ""
            if not re.fullmatch(r"[1-9][0-9]*", post_id):
                raise ValueError("Montenegro office card requires a numeric post_id")
            self.office = _Office(post_id)
            frame.card = True
        if self.office is not None:
            widget = _WIDGET_FIELDS.get(attributes.get("data-id"))
            if widget is not None:
                if self.widget is not None or widget in self.office.widgets:
                    raise ValueError("duplicate or nested Montenegro office field widget")
                self.office.widgets.add(widget)
                self.widget = frame.widget = widget
            elif self.widget is not None and "data-widget_type" in attributes:
                raise ValueError("nested widget inside Montenegro office field")
            if "jet-listing-dynamic-field__content" in classes and self.widget is not None:
                if self.parts is not None or self.widget in self.office.values:
                    raise ValueError("multiple content nodes in Montenegro office field")
                self.parts = []
                frame.content = True
        self.stack.append(frame)

    def handle_endtag(self, tag: str) -> None:
        if tag != "div":
            return
        if not self.stack:
            raise ValueError("unbalanced Montenegro office HTML")
        frame = self.stack.pop()
        if frame.content:
            if self.office is None or self.widget is None or self.parts is None:
                raise ValueError("incomplete Montenegro office field")
            self.office.values[self.widget] = "".join(self.parts)
            self.parts = None
        if frame.widget is not None:
            if self.office is None or frame.widget not in self.office.values:
                raise ValueError("Montenegro office field requires one content node")
            self.widget = None
        if frame.card:
            if self.office is None or self.widget is not None or self.parts is not None:
                raise ValueError("incomplete Montenegro office card")
            values = self.office.values
            code = values.get("code", "")
            if not re.fullmatch(r"[0-9]{5}", code):
                raise ValueError("Montenegro office requires one five-digit postal code field")
            self.records.append({
                "country_code": "ME", "code": code,
                "place_name": values.get("place", ""), "admin_name1": "",
                "source_place": values.get("place", ""),
                "source_address": values.get("address", ""),
                "source_post_id": self.office.post_id,
                "source_locator": f"card:{len(self.records) + 1}/post_id:{self.office.post_id}",
                "postal_use": "post_office",
            })
            self.office = None

    def handle_data(self, data: str) -> None:
        if self.parts is not None:
            self.parts.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag == "div":
            self.handle_endtag(tag)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field in Montenegro postal response JSON")
        result[key] = value
    return result


def iter_europe_records(source: Mapping[str, Any], path: Path) -> Iterator[dict[str, str]]:
    """Read exact published field text, preserving duplicate office codes.

    The fixed public response covers the operator's office listing, rather than
    establishing nationally complete address-level postcode coverage. Only the
    content of widget 6d2832a is a postal code; phone numbers, office IDs, scripts
    and the separate delivery-office annotation are never alternative code data.
    """
    if source.get("format") != "official_postal_source" or source.get("adapter") != "me_postacg_offices":
        raise ValueError("unsupported Europe postal source format")
    if source.get("expected_country") != "ME":
        raise ValueError("Montenegro office response requires expected_country ME")
    try:
        response = json.loads(read_source_text(source, Path(path), encoding="utf-8-sig"),
                              object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("cannot replay Montenegro postal response JSON") from error
    if (not isinstance(response, dict) or response.get("success") is not True
            or not isinstance(response.get("data"), dict)
            or not isinstance(response["data"].get("html"), str)
            or not response["data"]["html"].strip()):
        raise ValueError("Montenegro postal response requires successful data.html")
    parser = _MontenegroOffices()
    parser.feed(response["data"]["html"])
    parser.close()
    if parser.stack or parser.office is not None or not parser.records:
        raise ValueError("Montenegro postal response requires complete office cards")
    yield from parser.records
