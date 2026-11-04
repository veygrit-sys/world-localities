"""Shared filtering and pagination rules for regional locality queries."""

from __future__ import annotations

from collections.abc import Iterable, Iterator


def validate_country_code(country: str) -> None:
    if len(country) != 2 or not country.isalpha() or country != country.upper():
        raise ValueError("country must be an uppercase two-letter code")


def matching_rows(
    rows: Iterable[dict[str, str]],
    *,
    kind: str | None = None,
    level: int | None = None,
    state: str | None = None,
    parent: str | None = None,
    text: str | None = None,
    include_other: bool = False,
) -> Iterator[dict[str, str]]:
    """Filter rows without guessing identity, language, hierarchy, or spelling."""
    for row in rows:
        if kind and row["kind"] != kind:
            continue
        if level and row["admin_level"] != str(level):
            continue
        if state and row["state_id"] != state:
            continue
        if parent and row["parent_id"] != parent:
            continue
        if not include_other and not kind and not level and row["address_candidate"] != "1":
            continue
        if text:
            labels = [row["name"], row["asciiname"], *row["alternatenames"].split(",")]
            if not any(text.casefold() in label.casefold() for label in labels):
                continue
        yield row


def page(
    rows: Iterable[dict[str, str]], offset: int, limit: int
) -> tuple[int, list[dict[str, str]]]:
    if isinstance(limit, bool) or not 1 <= limit <= 10_000 or offset < 0:
        raise ValueError("limit must be 1..10000; offset must be nonnegative")
    total = 0
    selected: list[dict[str, str]] = []
    for row in rows:
        if offset <= total < offset + limit:
            selected.append(row)
        total += 1
    return total, selected
