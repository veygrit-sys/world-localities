"""Build and query an offline exact-postcode address candidate index."""

import base64
import binascii
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unicodedata

from .postal import iter_postal_records, load_sources
from .postal_places import ELIGIBLE_KINDS, _source_code


_SCHEMA_VERSION = 2
_ROOT = b""
MAX_SIMILAR_POOL = 100
# The publisher's displayed separator may be omitted when typing these complete codes.
_COMPACT = {
    "AZ": (r"AZ[0-9]{4}", 2, " "), "BM": (r"[A-Z]{2}[A-Z0-9]{2}", 2, " "),
    "CZ": (r"[0-9]{5}", 3, " "), "LV": (r"LV[0-9]{4}", 2, "-"),
    "PL": (r"[0-9]{5}", 2, "-"), "PT": (r"[0-9]{7}", 4, "-"),
    "SE": (r"[0-9]{5}", 3, " "), "SK": (r"[0-9]{5}", 3, " "),
}
_INSERT = """
INSERT INTO edges(country, postcode, parent, label, kind, source, has_children)
VALUES (?, ?, ?, ?, ?, ?, ?)
ON CONFLICT DO UPDATE SET has_children = 1
WHERE excluded.has_children = 1 AND edges.has_children = 0
"""
_SCOPE = "country = ? AND postcode = ? AND parent = ?"
_OPTIONS_SQL = """
SELECT label, kind, MAX(has_children)
FROM edges WHERE {scope} {typed_filter}
GROUP BY label, kind
ORDER BY CASE WHEN kind = 'house_number' THEN CAST(label AS INTEGER) ELSE 0 END,
         label, kind LIMIT ? OFFSET ?
"""


_OPTIONS = _OPTIONS_SQL.format(scope=_SCOPE, typed_filter="")
_FILTERED_OPTIONS = _OPTIONS_SQL.format(scope=_SCOPE, typed_filter="AND matches_prefix(label, ?)")


class IndexUnavailable(RuntimeError):
    """The configured address index or ranking resource cannot serve requests."""


def _query_key(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _matches_prefix(label, query):
    # Include a prefix of the label or one starting at a word boundary (e.g.
    # a municipality after its prefecture). Punctuation is literal user text.
    value = _query_key(label)
    return value.startswith(query) or any(value.startswith(query, match.start())
                                          for match in re.finditer(r"(?<!\w)(?=\w)", value))


def _country(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]{2}", value):
        raise ValueError("country must contain two ASCII letters")
    return value.upper()


def _postcode(country, value):
    if not isinstance(value, str) or len(value) > 64 or not value.isprintable():
        raise ValueError("postcode must be a short, single-line string")
    code = unicodedata.normalize("NFKC", value).strip().upper()
    if not code:
        raise ValueError("empty postcode")
    if country == "JP" and re.fullmatch(r"[0-9]{3}-[0-9]{4}", code):
        return code.replace("-", "")
    compact = _COMPACT.get(country)
    if compact and re.fullmatch(compact[0], code):
        boundary, separator = compact[1:]
        return code[:boundary] + separator + code[boundary:]
    return _source_code(country, code)


def _payload(kind, label):
    return json.dumps([kind, label], ensure_ascii=False, separators=(",", ":")).encode()


def _digest(country, code, parent, payload):
    return hashlib.blake2s(b"\0".join((country.encode(), code.encode(), parent, payload)),
                           digest_size=12).digest()


def _option_id(country, code, parent, kind, label):
    data = _payload(kind, label)
    value = _digest(country, code, parent, data) + data
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _read_option(country, code, parent, value):
    if not isinstance(value, str) or not 16 < len(value) <= 2048:
        raise ValueError("invalid selection")
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        kind, label = json.loads(raw[12:])
        if not isinstance(kind, str) or not isinstance(label, str):
            raise ValueError
        if value != _option_id(country, code, parent, kind, label):
            raise ValueError
    except (ValueError, TypeError, RecursionError, binascii.Error) as error:
        raise ValueError("selection does not belong to this postcode and path") from error
    return kind, label, raw[:12]


def _geonames(countries):
    for source in load_sources()["sources"]:
        if source["format"] != "geonames_tsv_zip" or not source.get("active_for_lookup", True):
            continue
        if countries is not None:
            if source.get("expected_country") and source["expected_country"] not in countries:
                continue
            kinds = source.get("country_code_kinds", {})
            if not any(kinds.get(c, source["default_code_kind"]) in ELIGIBLE_KINDS for c in countries):
                continue
        for row in iter_postal_records(source):
            country = row["country_code"]
            if (countries is not None and country not in countries) or row["code_kind"] not in ELIGIBLE_KINDS:
                continue
            place = row["place_name"].strip()
            if not place:
                continue
            region = row["admin_code1" if country == "US" else "admin_name1"].strip()
            area = ", ".join(dict.fromkeys(part for part in (place, region) if part))
            yield country, row["code"], (("area", area),), source["id"]


def _records(countries):
    from .postal_picker_sources import iter_extra_records

    official = set()
    authoritative = set()
    for country, code, steps, source in iter_extra_records(countries):
        if source == "fr-laposte-hexasmal" or source.startswith("official-mu-"):
            official.add((country, _postcode(country, code)))
        elif country == "JP" and source.startswith("japanpost-postal-"):
            authoritative.add(country)
        yield country, code, steps, source
    if countries is not None:
        countries = countries - authoritative
        if not countries:
            return
    for country, code, steps, source in _geonames(countries):
        if country in authoritative or (country, code) in official:
            continue
        yield country, code, steps, source


def _write(connection, records):
    from .postal_picker_sources import source_descriptors

    connection.executescript("""
        PRAGMA journal_mode=OFF;
        PRAGMA synchronous=OFF;
        PRAGMA cache_size=-65536;
        CREATE TABLE edges(
            country TEXT, postcode TEXT, parent BLOB, label TEXT, kind TEXT,
            source INTEGER, has_children INTEGER NOT NULL,
            PRIMARY KEY(country, postcode, parent, label, kind, source)
        ) WITHOUT ROWID;
        CREATE TABLE sources(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE countries(code TEXT PRIMARY KEY) WITHOUT ROWID;
        CREATE TABLE source_metadata(name TEXT PRIMARY KEY, details TEXT NOT NULL) WITHOUT ROWID;
    """)
    sources = {}
    countries = set()
    batch = []
    record_count = 0
    for country, code, steps, source in records:
        if not steps:
            continue
        code = _postcode(country, code)
        countries.add(country)
        source_id = sources.setdefault(source, len(sources) + 1)
        parent = _ROOT
        for i, (kind, label) in enumerate(steps):
            has_children = i + 1 < len(steps)
            batch.append((country, code, parent, label, kind, source_id, has_children))
            if has_children:
                parent = _digest(country, code, parent, _payload(kind, label))
        record_count += 1
        if len(batch) >= 8192:
            connection.executemany(_INSERT, batch)
            batch.clear()
    connection.executemany(_INSERT, batch)
    connection.executemany("INSERT INTO sources(name, id) VALUES (?, ?)", sources.items())
    connection.executemany("INSERT INTO countries VALUES (?)", ((c,) for c in sorted(countries)))
    descriptors = source_descriptors()
    connection.executemany("INSERT INTO source_metadata VALUES (?, ?)", (
        (sid, json.dumps(descriptors[sid], ensure_ascii=False)) for sid in sources if sid in descriptors
    ))
    connection.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
    connection.commit()
    return {"country_count": len(countries), "countries": sorted(countries),
            "sources": sorted(sources), "source_records": record_count}


def build_index(path, countries=None):
    """Build from local pinned sources, replacing the previous index only on success."""
    if countries is not None:
        values = [countries] if isinstance(countries, str) else countries
        countries = {_country(value) for value in values}
        if not countries:
            raise ValueError("countries must contain at least one country")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(fd)
    try:
        with closing(sqlite3.connect(temporary)) as db:
            summary = _write(db, _records(countries))
        if not summary["country_count"]:
            raise ValueError("no eligible postcode sources; existing index retained")
        if countries is not None:
            summary["unavailable_countries"] = sorted(countries - set(summary["countries"]))
        os.replace(temporary, path)
        return summary
    finally:
        Path(temporary).unlink(missing_ok=True)


def _option_rows(db, params, rows):
    # Read supporting sources per option in this same snapshot. A parent's
    # provenance does not automatically transfer to each child.
    country, code, parent = params
    options = []
    for label, kind, children in rows:
        sources = [item[0] for item in db.execute(f"""
            SELECT name FROM edges JOIN sources ON edges.source = sources.id
            WHERE {_SCOPE} AND label = ? AND kind = ? ORDER BY name
        """, (*params, label, kind))]
        options.append({
            "id": _option_id(country, code, parent, kind, label),
            "kind": kind, "label": label, "has_children": bool(children),
            "supporting_sources": sources, "source_id": sources[0],
            "country_code": country, "postcode": code,
        })
    return options


class PostalPicker:
    """Each read opens its own read-only SQLite snapshot, safe to share across threads."""

    def __init__(self, path):
        self._uri = Path(path).resolve().as_uri() + "?mode=ro"
        with closing(self._connect()) as db:
            if db.execute("PRAGMA user_version").fetchone()[0] != _SCHEMA_VERSION:
                raise IndexUnavailable("unsupported postcode picker index, rebuild it")

    def _connect(self):
        return sqlite3.connect(self._uri, uri=True)

    def countries(self):
        with closing(self._connect()) as db:
            return [row[0] for row in db.execute("SELECT code FROM countries ORDER BY code")]

    def lookup(self, country, postcode, path=(), *, after=None, limit=50, query="", similar_filter=None):
        country = _country(country)
        code = _postcode(country, postcode)
        if not isinstance(path, (tuple, list)) or len(path) > 16:
            raise ValueError("invalid selection path")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if not isinstance(query, str) or len(query) > 128 or (query and not query.isprintable()):
            raise ValueError("query must be a single-line string of at most 128 characters")
        prefix = _query_key(query)
        offset = 0 if after is None else after
        if type(offset) is not int or not 0 <= offset <= 1000000:
            raise ValueError("invalid pagination offset")
        result = {"country": country, "postcode": code, "status": "not_found",
                  "selected": [], "options": [], "sources": [], "source_details": {}, "next_after": None,
                  "deliverability_verified": False, "match_mode": "none"}
        with closing(self._connect()) as db:
            db.execute("BEGIN")
            if not db.execute("SELECT 1 FROM countries WHERE code=?", (country,)).fetchone():
                if path:
                    raise ValueError("selection for an unsupported country")
                result["status"] = "unsupported_country"
                return result
            parent = _ROOT
            source_rows = ()
            for token in path:
                kind, label, next_parent = _read_option(country, code, parent, token)
                source_rows = db.execute(f"""
                    SELECT name FROM edges JOIN sources ON edges.source = sources.id
                    WHERE {_SCOPE} AND label = ? AND kind = ? ORDER BY name
                """, (country, code, parent, label, kind)).fetchall()
                if not source_rows:
                    raise ValueError("selection no longer exists in this index")
                result["selected"].append({"id": token, "kind": kind, "label": label})
                parent = next_parent
            if not path:
                source_rows = db.execute(f"""
                    SELECT DISTINCT name FROM edges JOIN sources ON edges.source = sources.id
                    WHERE {_SCOPE} ORDER BY name
                """, (country, code, parent)).fetchall()
            result["sources"] = [row[0] for row in source_rows]
            if not source_rows:
                return result
            for sid in result["sources"]:
                metadata = db.execute("SELECT details FROM source_metadata WHERE name = ?", (sid,)).fetchone()
                if metadata:
                    try:
                        result["source_details"][sid] = json.loads(metadata[0])
                    except ValueError as error:
                        raise IndexUnavailable("invalid source metadata in index") from error
            params = (country, code, parent)
            if prefix:
                # First seek the postcode and selected parent by primary key.
                # Only labels in that range can enter the filtered page.
                db.create_function("matches_prefix", 2, _matches_prefix, deterministic=True)
                rows = db.execute(_FILTERED_OPTIONS, (*params, prefix, limit + 1, offset)).fetchall()
            else:
                rows = db.execute(_OPTIONS, (*params, limit + 1, offset)).fetchall()
            if rows:
                result["match_mode"] = "prefix" if prefix else "browse"
                result["options"] = _option_rows(db, params, rows[:limit])
                if len(rows) > limit:
                    result["next_after"] = offset + limit
            elif prefix:
                # A past-end cursor on a real prefix result must not enter
                # spelling fallback, even when another similar label exists.
                if offset and db.execute(f"SELECT 1 FROM edges WHERE {_SCOPE} AND matches_prefix(label, ?) LIMIT 1",
                                         (*params, prefix)).fetchone():
                    raise ValueError("pagination offset outside available candidates")
                if similar_filter is not None:
                    siblings = db.execute(_OPTIONS, (*params, MAX_SIMILAR_POOL + 1, 0)).fetchall()
                    if 0 < len(siblings) <= MAX_SIMILAR_POOL:
                        candidates = similar_filter(country, query, _option_rows(db, params, siblings))
                        result["options"] = candidates[offset:offset + limit]
                        if result["options"]:
                            result["match_mode"] = "similar_spelling"
                            if len(candidates) > offset + limit:
                                result["next_after"] = offset + limit
            if offset and not result["options"]:
                raise ValueError("pagination offset outside available candidates")
            if result["options"]:
                result["status"] = "options"
            elif prefix and db.execute(f"SELECT 1 FROM edges WHERE {_SCOPE} LIMIT 1", params).fetchone():
                result["status"] = "no_matching_options"
            else:
                result["status"] = "leaf"
            return result
